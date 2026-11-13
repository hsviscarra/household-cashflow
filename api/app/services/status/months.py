"""Month by month: what each month still needs (statements, imports, categories, bills,
balances that don't follow)."""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    ImportBatch,
    LoadLog,
    RecurringEntry,
    RecurringTemplate,
    StatementFile,
    Transaction,
    TransferNote,
)
from app.services import classify, recurring, transfers
from app.services.status.arrival import sources
from app.services.status.base import (
    AccountTimeline,
    Coverage,
    Item,
    Load,
    MonthStatus,
    Status,
    TimelineStatement,
    _days,
    month_end,
)
from app.services.status.statements import (
    SHOWN_BILLS,
    _gaps,
    _Stmt,
    approved_statements,
    next_cycle_end,
    not_loaded,
    prev_cycle_end,
    statement_files,
    sync_coverage,
    timeline,
)

EXCEL_MONTHS_SHOWN = 36  # workbook months listed under the statement months

Period = tuple[date, date]


@dataclass
class _Known:
    """What is known about the statements when the months are checked."""

    today: date
    covered: dict[int, list[Period]]  # by account: days an approved statement or the sync covers
    waiting: dict[int, list[tuple[date, date, str]]]  # uploaded, not approved yet
    files: dict[int, list[TimelineStatement]]
    lines: dict[int, AccountTimeline]


def _coverage(
    db: Session,
    accounts: list[Account],
    stmts: list[_Stmt],
    files: dict[int, list[TimelineStatement]],
    today: date,
) -> dict[int, list[Period]]:
    """The days each account's data covers. Bank sync covers its accounts' days like a statement
    does (ADR-072), so no PDF is asked for; it is added to `files` to show on the timeline."""
    covered: dict[int, list[Period]] = defaultdict(list)
    for s in stmts:
        covered[s.account_id].append((s.start, s.end))
    for aid, (s_start, s_end) in sync_coverage(db, accounts, today).items():
        covered[aid].append((s_start, s_end))
        files[aid].append(TimelineStatement(0, "Bank sync", s_start, s_end, "synced", None))
    return covered


def _first_month(excel_through: date | None, stmts: list[_Stmt], current: date) -> date:
    """The first month checked against statements: the one after the workbook's last, or the
    month of the first statement."""
    if excel_through is not None:
        return recurring.add_months(excel_through, 1)
    if stmts:
        return recurring.first(min(s.start for s in stmts))
    return current


def _open_window(a: Account, m: date) -> Period | None:
    """The days of a month an account was open, or None when nothing is expected from it:
    closed before the month or opened after it."""
    end = month_end(m)
    if a.closed_on is not None and a.closed_on < m:
        return None
    if a.opened_on is not None and a.opened_on > end:
        return None
    return (
        max(m, a.opened_on) if a.opened_on else m,
        min(end, a.closed_on) if a.closed_on else end,
    )


def _missing_text(a: Account, m: date, open_gaps: list[Period], window: Period, k: _Known) -> str:
    """The sentence for an account's missing days in a month, with what is known about them:
    already on Import, not issued by the bank yet, or which statement to bring."""
    a_end = window[1]
    periods = k.covered[a.account_id]
    whole_month = len(open_gaps) == 1 and open_gaps[0] == (m, min(a_end, k.today))
    if whole_month and not any(p_start <= a_end and p_end >= m for p_start, p_end in periods):
        text = f"{a.name}: no statement for {m:%B}"
    else:
        text = f"{a.name}: no statement for " + ", ".join(_days(s, e) for s, e in open_gaps)
    if a_end < month_end(m):  # closed this month
        text += f" (until it closed on {a_end:%b} {a_end.day})"
    here = sorted(
        {
            w
            for w_start, w_end, w in k.waiting[a.account_id]
            for g_start, g_end in open_gaps
            if w_start <= g_end and w_end >= g_start
        }
    )
    if here:  # on the Import page already: say where it stands
        return text + f": on Import, {' / '.join(here)}"
    due = _not_issued(k.files.get(a.account_id, []), open_gaps, k.today)
    if due is not None:
        return text + f" (the bank issues it around {due:%b} {due.day})"
    return text + _which(k.lines[a.account_id], open_gaps)


def _statements_of(ms: MonthStatus, a: Account, k: _Known) -> None:
    """One account in one month: how many of its days are covered, and an item for the rest."""
    m = ms.month
    window = _open_window(a, m)
    if window is None:
        return
    a_start, a_end = window  # closed or opened during the month: expected only while open
    gaps = _gaps(k.covered[a.account_id], a_start, a_end)
    uncovered = sum((g_end - g_start).days + 1 for g_start, g_end in gaps)
    days = (a_end - a_start).days + 1
    ms.coverage.append(Coverage(a.account_id, days - uncovered, days))
    a_last = min(a_end, k.today)  # the current month is checked up to today
    open_gaps = [(g_start, min(g_end, a_last)) for g_start, g_end in gaps if g_start <= a_last]
    if open_gaps:
        ms.items.append(Item("statement", _missing_text(a, m, open_gaps, window, k), "/import"))


def month_status(db: Session, today: date | None = None, with_loads: bool = True) -> Status:
    """with_loads=False skips the load history (audit.load_log), which the read-only MCP login
    can't read."""
    today = today or date.today()
    current = recurring.first(today)
    excel = sorted(recurring.excel_months(db))
    excel_through = excel[-1] if excel else None
    accounts = list(db.scalars(select(Account).where(Account.is_active).order_by(Account.name)))
    stmts = approved_statements(db)
    waiting = not_loaded(db)
    files = statement_files(db)
    by_account: dict[int, list[_Stmt]] = defaultdict(list)
    for s in stmts:
        by_account[s.account_id].append(s)
    covered = _coverage(db, accounts, stmts, files, today)

    first = _first_month(excel_through, stmts, current)
    months = list(recurring.months(first, current)) if first <= current else []
    checked_from = first if months else current
    lines = {t.account_id: t for t in timeline(accounts, files, checked_from, today)}
    known = _Known(today, covered, waiting, files, lines)

    out: list[MonthStatus] = []
    for m in months:
        ms = MonthStatus(m, "statements")
        for a in accounts:
            _statements_of(ms, a, known)
        _pending_imports(db, ms)
        _lines(db, ms)
        _recurring(db, ms, today)
        _notes(db, ms, by_account)
        out.append(ms)
    _balance_breaks(db, by_account, {a.account_id: a for a in accounts}, out)

    since = recurring.add_months(current, -EXCEL_MONTHS_SHOWN)
    out += [MonthStatus(m, "excel") for m in excel if m >= since]
    out.sort(key=lambda s: s.month, reverse=True)
    return Status(
        today,
        excel_through,
        accounts,
        out,
        loads(db) if with_loads else [],
        list(lines.values()),
        sources(accounts, list(lines.values()), waiting, today),
    )


def _which(line: AccountTimeline, open_gaps: list[tuple[date, date]]) -> str:
    """ " · download the statement closing Nov 3 (Statement_112026_4003.pdf)" for the statements
    that cover a month's missing days."""
    found: list[tuple[date, str | None]] = []
    for g in line.gaps:
        for i, c in enumerate(g.closes):
            starts = prev_cycle_end(c) + timedelta(days=1)
            if any(starts <= g_end and c >= g_start for g_start, g_end in open_gaps):
                found.append((c, g.files[i] if i < len(g.files) else None))
    if not found:
        return ""
    days = " and ".join(f"{c:%b} {c.day}" for c, _ in found)
    names = [f for _, f in found if f]
    word = "statement" if len(found) == 1 else "statements"
    return f" · download the {word} closing {days}" + (f" ({', '.join(names)})" if names else "")


def _not_issued(
    stmts: list[TimelineStatement], gaps: list[tuple[date, date]], today: date
) -> date | None:
    """When every missing day comes after the account's last statement and the next one isn't
    due yet, the day it's due (the item says the bank hasn't issued it, not that it's missing)."""
    if not stmts or not gaps:
        return None
    last_end = max(t.end for t in stmts)
    due = next_cycle_end(last_end)
    return due if all(g_start > last_end for g_start, _ in gaps) and due > today else None


def _pending_imports(db: Session, ms: MonthStatus) -> None:
    end = month_end(ms.month)
    rows = db.execute(
        select(ImportBatch, StatementFile)
        .join(StatementFile, StatementFile.statement_file_id == ImportBatch.statement_file_id)
        .where(ImportBatch.status == "preview")
    )
    for batch, sf in rows:
        if sf.period_start is None or sf.period_end is None:
            continue
        if sf.period_start > end or sf.period_end < ms.month:
            continue
        why = "waits for approval" if batch.tieout_ok else "doesn't tie out"
        ms.items.append(
            Item("import", f"{sf.file_name} {why}", f"/import/batches/{batch.batch_id}")
        )


def _lines(db: Session, ms: MonthStatus) -> None:
    month = ms.month.isoformat()[:7]
    n = len(classify.uncategorized(db, ms.month))
    if n:
        word = "line needs" if n == 1 else "lines need"
        ms.items.append(
            Item("uncategorized", f"{n} {word} a category", f"/review?month={month}", n)
        )
    t = len(transfers.unmatched(db, ms.month))
    if t:
        word = "transfer is" if t == 1 else "transfers are"
        ms.items.append(
            Item("transfer", f"{t} {word} missing the other side", f"/review?month={month}", t)
        )


def _notes(db: Session, ms: MonthStatus, by_account: dict[int, list[_Stmt]]) -> None:
    """Transfer notes (ADR-023) whose statement is loaded but which found no line: a wrong
    amount, date or account on the note, or a line someone already classified by hand."""
    end = month_end(ms.month)
    late = [
        n
        for n in db.scalars(
            select(TransferNote).where(
                TransferNote.transaction_id.is_(None),
                TransferNote.txn_date >= ms.month,
                TransferNote.txn_date <= end,
            )
        )
        if any(
            s.start <= n.txn_date and s.end >= n.txn_date + timedelta(days=5)
            for a, stmts in by_account.items()
            if n.account_id in (None, a)
            for s in stmts
        )
    ]
    if late:
        word = "transfer note has" if len(late) == 1 else "transfer notes have"
        ms.items.append(Item("note", f"{len(late)} {word} no statement line", "/people", len(late)))


def _recurring(db: Session, ms: MonthStatus, today: date) -> None:
    """Bills expected and not paid. A month that's over lists every one; the current month only
    those past their day (as the Bills page calls late), so a bill due on the 28th isn't asked
    for on the 12th (ADR-085)."""
    if ms.month == recurring.first(today):
        names = [b.name for b in recurring.bills(db, ms.month, today) if b.status == "late"]
        what = "past {} day with no line yet".format("its" if len(names) == 1 else "their")
    else:
        linked = set(
            db.scalars(
                select(Transaction.recurring_entry_id).where(
                    Transaction.recurring_entry_id.is_not(None),
                    Transaction.cash_month == ms.month,
                )
            )
        )
        names = [
            name
            for entry_id, name in db.execute(
                select(RecurringEntry.entry_id, RecurringTemplate.name)
                .join(
                    RecurringTemplate, RecurringTemplate.template_id == RecurringEntry.template_id
                )
                .where(RecurringEntry.month == ms.month, RecurringEntry.status == "planned")
                .order_by(RecurringTemplate.sort_order, RecurringTemplate.name)
            )
            if entry_id not in linked
        ]
        what = "not paid yet"
    if names:
        shown = ", ".join(names[:SHOWN_BILLS]) + (
            f" and {len(names) - SHOWN_BILLS} more" if len(names) > SHOWN_BILLS else ""
        )
        word = "item" if len(names) == 1 else "items"
        ms.items.append(
            Item(
                "recurring",
                f"{len(names)} recurring {word} {what}: {shown}",
                f"/recurring?month={ms.month:%Y-%m}",
                len(names),
            )
        )


def _balance_breaks(
    db: Session,
    by_account: dict[int, list[_Stmt]],
    accounts: dict[int, Account],
    months: list[MonthStatus],
) -> None:
    """Consecutive statements of an account whose balances don't chain, shown in the month the
    later statement starts. Gaps between statements are already statement items."""
    index = {ms.month: ms for ms in months}
    for account_id, stmts in by_account.items():
        account = accounts.get(account_id)
        if account is None:
            continue
        for i, nxt in enumerate(stmts):
            # The statement before is the latest one that ends before this one starts: the same
            # period uploaded twice (two files) or overlapping ranges aren't a break.
            before = [s for s in stmts[:i] + stmts[i + 1 :] if s.end < nxt.start]
            if not before:
                continue
            prev = max(before, key=lambda s: (s.end, s.file_id))
            if nxt.start > prev.end + timedelta(days=7):
                continue
            if prev.closing is None or nxt.opening is None or prev.closing == nxt.opening:
                continue
            ms = index.get(recurring.first(nxt.start))
            if ms is None:
                continue
            ms.items.append(
                Item(
                    "balance",
                    f"{account.name}: opens at {nxt.opening:,.2f} on {nxt.start:%b} {nxt.start.day}"
                    f" but the previous statement closed at {prev.closing:,.2f}",
                    "/import",
                )
            )


def loads(db: Session, limit: int = 30) -> list[Load]:
    """The latest loads (statements, history, syncs) with what each did."""
    names = {f.sha256: f.file_name for f in db.scalars(select(StatementFile))}
    out = []
    for log in db.scalars(select(LoadLog).order_by(LoadLog.load_id.desc()).limit(limit)):
        try:
            summary = json.loads(log.summary)
        except ValueError:
            summary = {}
        name = summary.get("file_name") or names.get(log.file_sha256 or "")
        out.append(Load(log.loaded_at, log.source, name, log.rows_loaded, log.loaded_by))
    return out
