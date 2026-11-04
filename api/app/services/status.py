"""Month status (F12, ADR-009): is each month complete, and if not, what is missing.

A month the Excel history covers is complete by definition (ADR-004). From the month after it up
to the current month, a month is complete when nothing below is open:
- statements: every active account has approved statements covering every day of the month (card
  statements run mid-month to mid-month, so coverage is counted by day);
- imports: no statement for the month waits for approval or fails its tie-out;
- lines without a category, and transfers without their other side (F10);
- recurring items expected and not paid (F11);
- balance breaks: a statement's opening balance differs from the previous statement's closing
  balance for the same account.
"""

import itertools
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    ImportBatch,
    LoadLog,
    RecurringEntry,
    RecurringTemplate,
    StatementFile,
    StatementFileAccount,
    StatementHeader,
    Transaction,
)
from app.services import classify, recurring, transfers

DAY = timedelta(days=1)
DASH = "\u2013"


def month_end(month: date) -> date:
    return recurring.add_months(month, 1) - DAY


def _days(start: date, end: date) -> str:
    """'Oct 22-31', 'Oct 5', 'Sep 28-Oct 3' (with an en dash)."""
    if start == end:
        return f"{start:%b} {start.day}"
    if start.month == end.month:
        return f"{start:%b} {start.day}{DASH}{end.day}"
    return f"{start:%b} {start.day}{DASH}{end:%b} {end.day}"


@dataclass
class Item:
    kind: str  # statement, import, uncategorized, transfer, recurring, balance
    text: str
    link: str
    count: int = 1


@dataclass
class Coverage:
    account_id: int
    covered_days: int
    days: int

    @property
    def state(self) -> str:
        if self.covered_days >= self.days:
            return "full"
        return "partial" if self.covered_days else "none"


@dataclass
class MonthStatus:
    month: date
    source: str  # excel or statements
    items: list[Item] = field(default_factory=list)
    coverage: list[Coverage] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.items


@dataclass
class Load:
    loaded_at: datetime
    source: str
    file_name: str | None
    rows: int
    loaded_by: str


@dataclass
class TimelineStatement:
    file_id: int
    file_name: str
    start: date
    end: date
    state: str  # loaded, waiting, problems (read, doesn't tie out), not_read
    batch_id: int | None


@dataclass
class Gap:
    start: date
    end: date
    # Set when the gap is the current cycle, whose statement the bank hasn't issued yet.
    due: date | None = None
    # The statements that fill it, by the day each closes, and their usual file names where the
    # bank puts the date in them ("Statement_112026_4003.pdf" closes in November 2026).
    closes: list[date] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass
class AccountTimeline:
    account_id: int
    name: str
    closed_on: date | None
    start_day: int | None  # the day of the month its statements usually start
    statements: list[TimelineStatement]
    gaps: list[Gap]


@dataclass
class Status:
    today: date
    excel_through: date | None
    accounts: list[Account]
    months: list[MonthStatus]
    loads: list[Load]
    timeline: list[AccountTimeline] = field(default_factory=list)


@dataclass
class _Stmt:
    file_id: int
    file_name: str
    account_id: int
    start: date
    end: date
    opening: Decimal | None
    closing: Decimal | None


def approved_statements(db: Session) -> list[_Stmt]:
    approved = set(
        db.scalars(select(ImportBatch.statement_file_id).where(ImportBatch.status == "approved"))
    )
    if not approved:
        return []
    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    files = {
        f.statement_file_id: f
        for f in db.scalars(
            select(StatementFile).where(StatementFile.statement_file_id.in_(approved))
        )
    }
    links: dict[int, list[int]] = defaultdict(list)
    for fa in db.scalars(
        select(StatementFileAccount).where(StatementFileAccount.statement_file_id.in_(approved))
    ):
        links[fa.statement_file_id].append(fa.account_id)
    out = []
    for h in db.scalars(
        select(StatementHeader).where(StatementHeader.statement_file_id.in_(approved))
    ):
        balances = json.loads(h.totals_json).get("balances", {})
        ids = links[h.statement_file_id]
        for account_id in ids:
            account = accounts[account_id]
            opening: Decimal | None
            closing: Decimal | None
            if len(ids) > 1 and account.last4 in balances:
                pair = balances[account.last4]
                opening, closing = Decimal(pair[0]), Decimal(pair[1])
            else:
                opening, closing = h.opening_balance, h.closing_balance
            out.append(
                _Stmt(
                    h.statement_file_id,
                    files[h.statement_file_id].file_name,
                    account_id,
                    h.period_start,
                    h.period_end,
                    opening,
                    closing,
                )
            )
    return sorted(out, key=lambda s: (s.account_id, s.start, s.file_id))


def not_loaded(db: Session) -> dict[int, list[tuple[date, date, str]]]:
    """Per account, statements uploaded but not approved yet: (start, end, where it stands).
    A month without an approved statement says so instead of "no statement" (Hernan uploaded a
    batch and saw every month unchanged: only approved statements count)."""
    latest: dict[int, str] = {}
    for b in db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)):
        latest[b.statement_file_id] = b.status
    out: dict[int, list[tuple[date, date, str]]] = defaultdict(list)
    rows = db.execute(
        select(StatementFile, StatementFileAccount.account_id).join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementFile.statement_file_id,
        )
    )
    for sf, account_id in rows:
        state = latest.get(sf.statement_file_id)
        if state == "approved" or sf.period_start is None or sf.period_end is None:
            continue
        where = "waiting for approval" if state == "preview" else "uploaded, not read yet"
        out[account_id].append((sf.period_start, sf.period_end, where))
    return out


def next_cycle_end(end: date) -> date:
    """The same day a month later (clamped): when the statement after one ending on `end` ends."""
    m = recurring.add_months(end.replace(day=1), 1)
    last = (recurring.add_months(m, 1) - timedelta(days=1)).day
    if end == month_end(end):  # month-end statements (Produbanco): the next month's last day
        return m.replace(day=last)
    return m.replace(day=min(end.day, last))


def statement_files(db: Session) -> dict[int, list[TimelineStatement]]:
    """Every uploaded statement with a period, per linked account, and where it stands."""
    latest: dict[int, ImportBatch] = {}
    for b in db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)):
        latest[b.statement_file_id] = b
    out: dict[int, list[TimelineStatement]] = defaultdict(list)
    rows = db.execute(
        select(StatementFile, StatementFileAccount.account_id).join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementFile.statement_file_id,
        )
    )
    for sf, account_id in rows:
        if sf.period_start is None or sf.period_end is None:
            continue
        batch = latest.get(sf.statement_file_id)
        state = _standing(batch)
        out[account_id].append(
            TimelineStatement(
                sf.statement_file_id,
                sf.file_name,
                sf.period_start,
                sf.period_end,
                state,
                batch.batch_id if batch is not None and batch.status != "rejected" else None,
            )
        )
    for items in out.values():
        items.sort(key=lambda t: (t.start, t.end, t.file_id))
    return out


def _standing(batch: ImportBatch | None) -> str:
    if batch is None or batch.status == "rejected":
        return "not_read"
    if batch.status == "approved":
        return "loaded"
    return "waiting" if batch.tieout_ok else "problems"


def prev_cycle_end(end: date) -> date:
    """The same day a month earlier (clamped; month ends stay month ends)."""
    m = recurring.add_months(end.replace(day=1), -1)
    last = (end.replace(day=1) - timedelta(days=1)).day
    if end == month_end(end):
        return m.replace(day=last)
    return m.replace(day=min(end.day, last))


def statement_closes(
    gap_start: date, gap_end: date, before: date | None, after: date | None, issued_by: date
) -> list[date]:
    """The closing days of the statements that would fill a gap, from the statement right after
    it (each one closes the day before the next starts, a month apart) or the one right before
    it; only those already issued."""
    out: list[date] = []
    if after is not None:
        c = gap_end
        while c >= gap_start:
            out.append(c)
            c = prev_cycle_end(c)
    elif before is not None:
        c = next_cycle_end(before)
        while c <= issued_by:
            out.append(c)
            if c >= gap_end:
                break
            c = next_cycle_end(c)
    return sorted(out)


# How each bank names its statement file, where the name carries the closing date.
FILE_NAMES = {
    "Capital One": lambda close, last4: f"Statement_{close:%m%Y}_{last4}.pdf",
    "Bank of America": lambda close, last4: f"eStmt_{close:%Y-%m-%d}.pdf",
    "Pacificard": lambda close, last4: f"ESTADOCUENTA{close:%Y%m}.pdf",
}


def _file_names(a: Account, closes: list[date]) -> list[str]:
    name = FILE_NAMES.get(a.institution)
    return [name(c, a.last4 or "") for c in closes] if name else []


def timeline(
    accounts: list[Account],
    files: dict[int, list[TimelineStatement]],
    expected_from: date,
    today: date,
) -> list[AccountTimeline]:
    """Per account: its statements in order and the days no statement covers, from the first
    month Data Status checks up to today (or the day it closed). The last gap is the current
    cycle, not missing, while the bank hasn't issued its statement yet."""
    out = []
    for a in accounts:
        stmts = files.get(a.account_id, [])
        horizon = min(today, a.closed_on) if a.closed_on else today
        gaps = [
            Gap(s, e) for s, e in _gaps([(t.start, t.end) for t in stmts], expected_from, horizon)
        ]
        if stmts and gaps and gaps[-1].start > max(t.end for t in stmts):
            last_end = max(t.end for t in stmts)
            due = next_cycle_end(last_end)
            if due > horizon and not (a.closed_on and a.closed_on <= today):
                gaps[-1].due = due
        for g in gaps:
            if g.due:
                continue
            before = next((t.end for t in stmts if t.end == g.start - timedelta(days=1)), None)
            after = next((t.start for t in stmts if t.start == g.end + timedelta(days=1)), None)
            g.closes = statement_closes(g.start, g.end, before, after, today)
            g.files = _file_names(a, g.closes)
        days = Counter(t.start.day for t in stmts)
        out.append(
            AccountTimeline(
                a.account_id,
                a.name,
                a.closed_on,
                days.most_common(1)[0][0] if days else None,
                stmts,
                gaps,
            )
        )
    return out


def _gaps(periods: list[tuple[date, date]], start: date, end: date) -> list[tuple[date, date]]:
    """The day ranges of start..end that no period covers."""
    gaps, cursor = [], start
    for p_start, p_end in sorted(periods):
        if p_end < cursor or p_start > end:
            continue
        if p_start > cursor:
            gaps.append((cursor, min(p_start - DAY, end)))
        cursor = max(cursor, p_end + DAY)
        if cursor > end:
            break
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps


def month_status(db: Session, today: date | None = None) -> Status:
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

    if excel_through is not None:
        first = recurring.add_months(excel_through, 1)
    elif stmts:
        first = recurring.first(min(s.start for s in stmts))
    else:
        first = current
    months = [m for m in recurring.months(first, current)] if first <= current else []
    checked_from = first if months else current
    lines = {t.account_id: t for t in timeline(accounts, files, checked_from, today)}

    out: list[MonthStatus] = []
    for m in months:
        ms = MonthStatus(m, "statements")
        end = month_end(m)
        for a in accounts:
            if a.closed_on is not None and a.closed_on < m:
                continue  # closed before this month: nothing expected
            # Closed during the month: expected only up to the closing day.
            a_end = min(end, a.closed_on) if a.closed_on else end
            periods = [(s.start, s.end) for s in by_account[a.account_id]]
            gaps = _gaps(periods, m, a_end)
            uncovered = sum((g_end - g_start).days + 1 for g_start, g_end in gaps)
            days = (a_end - m).days + 1
            ms.coverage.append(Coverage(a.account_id, days - uncovered, days))
            a_last = min(a_end, today)  # the current month is checked up to today
            open_gaps = [
                (g_start, min(g_end, a_last)) for g_start, g_end in gaps if g_start <= a_last
            ]
            if not open_gaps:
                continue
            if (
                len(open_gaps) == 1
                and open_gaps[0] == (m, a_last)
                and not any(p_start <= a_end and p_end >= m for p_start, p_end in periods)
            ):
                text = f"{a.name}: no statement for {m:%B}"
            else:
                text = f"{a.name}: no statement for " + ", ".join(
                    _days(g_start, g_end) for g_start, g_end in open_gaps
                )
            if a_end < end:  # closed this month
                text += f" (until it closed on {a_end:%b} {a_end.day})"
            here = sorted(
                {
                    w
                    for w_start, w_end, w in waiting[a.account_id]
                    for g_start, g_end in open_gaps
                    if w_start <= g_end and w_end >= g_start
                }
            )
            if here:  # on the Import page already: say where it stands
                text += f": on Import, {' / '.join(here)}"
            elif (due := _not_issued(files.get(a.account_id, []), open_gaps, today)) is not None:
                text += f" (the bank issues it around {due:%b} {due.day})"
            else:
                text += _which(lines[a.account_id], open_gaps)
            ms.items.append(Item("statement", text, "/import"))
        _pending_imports(db, ms)
        _lines(db, ms)
        _recurring(db, ms)
        out.append(ms)
    _balance_breaks(db, by_account, {a.account_id: a for a in accounts}, out)

    if excel_through is not None:
        for m in reversed(excel):
            if m >= recurring.add_months(current, -36):
                out.append(MonthStatus(m, "excel"))
    out.sort(key=lambda s: s.month, reverse=True)
    return Status(
        today,
        excel_through,
        accounts,
        out,
        loads(db),
        list(lines.values()),
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


def _recurring(db: Session, ms: MonthStatus) -> None:
    linked = set(
        db.scalars(
            select(Transaction.recurring_entry_id).where(
                Transaction.recurring_entry_id.is_not(None), Transaction.cash_month == ms.month
            )
        )
    )
    names = [
        name
        for entry_id, name in db.execute(
            select(RecurringEntry.entry_id, RecurringTemplate.name)
            .join(RecurringTemplate, RecurringTemplate.template_id == RecurringEntry.template_id)
            .where(RecurringEntry.month == ms.month, RecurringEntry.status == "planned")
            .order_by(RecurringTemplate.sort_order, RecurringTemplate.name)
        )
        if entry_id not in linked
    ]
    if names:
        shown = ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
        word = "item" if len(names) == 1 else "items"
        ms.items.append(
            Item(
                "recurring",
                f"{len(names)} recurring {word} not paid yet: {shown}",
                f"/recurring?year={ms.month.year}",
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
        for prev, nxt in itertools.pairwise(stmts):
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
