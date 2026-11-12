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

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
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
    TransferNote,
)
from app.services import bank_sync, classify, recurring, transfers

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
    kind: str  # statement, import, uncategorized, transfer, recurring, balance, note
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
    opened_on: date | None
    start_day: int | None  # the day of the month its statements usually start
    statements: list[TimelineStatement]
    gaps: list[Gap]


@dataclass
class Source:
    """How an account's data arrives and where it stands today (ADR-072)."""

    account_id: int
    name: str
    how: str  # bank_sync, email, upload
    last_day: date | None  # the last day its loaded data covers
    state: str  # up_to_date, on_its_way, on_import, you_upload, late
    note: str
    expected: date | None = None  # when the next data should be there


@dataclass
class Status:
    today: date
    excel_through: date | None
    accounts: list[Account]
    months: list[MonthStatus]
    loads: list[Load]
    timeline: list[AccountTimeline] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)


# Banks whose statements reach Gmail and the Apps Script posts them (ADR-020).
EMAILED = ("PICHINCHA", "PACIFICARD", "DINERS")
EMAIL_LAG = 7  # days after a statement closes by which its email has usually arrived


def how_it_arrives(a: Account) -> str:
    if a.sync_id:
        return "bank_sync"
    text = f"{a.institution} {a.name}".upper()
    return "email" if any(e in text for e in EMAILED) else "upload"


def _short(d: date) -> str:
    return f"{d:%b} {d.day}"


def sources(
    accounts: list[Account],
    timeline: list[AccountTimeline],
    waiting: dict[int, list[tuple[date, date, str]]],
    today: date,
) -> list[Source]:
    """Every open account: how its data arrives, the last day it covers, and whether the next
    piece is on its way, late, or waiting on a person."""
    lines = {t.account_id: t for t in timeline}
    out = []
    for a in accounts:
        if a.closed_on is not None and a.closed_on < today - timedelta(days=45):
            continue
        t = lines.get(a.account_id)
        if t is None:
            continue
        how = how_it_arrives(a)
        last = max((x.end for x in t.statements if x.state in ("loaded", "synced")), default=None)
        open_gaps = [g for g in t.gaps if g.start <= today]
        on_import = [
            w
            for w_start, w_end, w in waiting.get(a.account_id, [])
            for g in open_gaps
            if w_start <= g.end and w_end >= g.start
        ]
        closes = sorted(c for g in open_gaps for c in g.closes if c < today)
        if not open_gaps or (how == "bank_sync" and last is not None and last >= today):
            src = Source(a.account_id, a.name, how, last, "up_to_date", "Nothing to do")
        elif on_import:
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "on_import",
                f"On Import, {on_import[0]}: open it and approve",
            )
        elif how == "bank_sync":
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "late",
                f"Bank sync hasn't run since {_short(last)}" if last else "Bank sync hasn't run",
            )
        elif not closes:
            due = next((g.due for g in open_gaps if g.due), None)
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "on_its_way",
                f"The bank issues it around {_short(due)}" if due else "Not issued yet",
                due,
            )
        elif how == "email":
            by = closes[0] + timedelta(days=EMAIL_LAG)
            if by >= today:
                src = Source(
                    a.account_id,
                    a.name,
                    how,
                    last,
                    "on_its_way",
                    f"Closed {_short(closes[0])}; its email usually arrives by {_short(by)}",
                    by,
                )
            else:
                src = Source(
                    a.account_id,
                    a.name,
                    how,
                    last,
                    "late",
                    f"Closed {_short(closes[0])} and hasn't arrived: check the Gmail script,"
                    " or upload it on Import",
                    by,
                )
        else:
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "you_upload",
                f"Download the statement closing {_short(closes[0])} and upload it on Import",
                closes[0],
            )
        out.append(src)
    order = {"late": 0, "you_upload": 1, "on_import": 2, "on_its_way": 3, "up_to_date": 4}
    return sorted(out, key=lambda x: (order[x.state], x.name))


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


SHOWN_BILLS = 4  # names spelled out in "N recurring items not paid yet"
SYNC_FRESH = 3  # days: a sync older than this no longer counts up to today


def _first_synced(db: Session, linked: set[int]) -> dict[int, date]:
    """The day of the first sync that reached each linked account (from the sync log)."""
    out: dict[int, date] = {}
    runs = db.scalars(
        select(LoadLog).where(LoadLog.source == "bank_sync").order_by(LoadLog.load_id)
    )
    for run in runs:
        try:
            seen = json.loads(run.summary).get("accounts") or []
        except (ValueError, AttributeError):
            continue  # an older log line without the account list
        for a in seen:
            aid = a.get("account_id") if isinstance(a, dict) else None
            if aid in linked:
                out.setdefault(aid, run.loaded_at.date())
        if len(out) == len(linked):
            break
    return out


def sync_coverage(
    db: Session, accounts: list[Account], today: date
) -> dict[int, tuple[date, date]]:
    """The days bank sync covers for each linked account, up to the last sync (to today while
    the last sync is fresh). It starts where the first sync started asking: the bank was asked
    for every movement since then, so a day without one is covered, not missing (ADR-085). With
    no record of that, it starts at the first synced line."""
    linked = {a.account_id for a in accounts if a.sync_id}
    if not linked:
        return {}
    last = db.scalars(
        select(LoadLog)
        .where(LoadLog.source == "bank_sync")
        .order_by(LoadLog.load_id.desc())
        .limit(1)
    ).first()
    if last is None:
        return {}
    synced = last.loaded_at.date()
    end = today if (today - synced).days <= SYNC_FRESH else synced
    asked_from = {aid: day - bank_sync.LOOKBACK for aid, day in _first_synced(db, linked).items()}
    first_line: dict[int, date] = {
        aid: day
        for aid, day in db.execute(
            select(Transaction.account_id, func.min(Transaction.txn_date))
            .where(Transaction.account_id.in_(linked), Transaction.source == "bank_sync")
            .group_by(Transaction.account_id)
        )
        if aid is not None and day is not None
    }
    out: dict[int, tuple[date, date]] = {}
    for aid in linked:
        starts = [d for d in (asked_from.get(aid), first_line.get(aid)) if d is not None]
        if starts and min(starts) <= end:
            out[aid] = (min(starts), end)
    return out


def statement_files(db: Session) -> dict[int, list[TimelineStatement]]:
    """Every uploaded statement with a period, per linked account, and where it stands."""
    latest: dict[int, ImportBatch] = {}
    for b in db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)):
        latest[b.statement_file_id] = b
    out: dict[int, list[TimelineStatement]] = defaultdict(list)
    # The period the parser read, for files whose period upload couldn't read from the first
    # page (a Pacificard statement printing "hasta 2VOCT/2026").
    read = {
        h.statement_file_id: (h.period_start, h.period_end)
        for h in db.scalars(select(StatementHeader))
    }
    rows = db.execute(
        select(StatementFile, StatementFileAccount.account_id).join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementFile.statement_file_id,
        )
    )
    for sf, account_id in list(rows):
        start, end = sf.period_start, sf.period_end
        if start is None or end is None:
            start, end = read.get(sf.statement_file_id, (None, None))
        if start is None or end is None:
            continue
        batch = latest.get(sf.statement_file_id)
        state = _standing(batch)
        out[account_id].append(
            TimelineStatement(
                sf.statement_file_id,
                sf.file_name,
                start,
                end,
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
        since = max(expected_from, a.opened_on) if a.opened_on else expected_from
        gaps = [Gap(s, e) for s, e in _gaps([(t.start, t.end) for t in stmts], since, horizon)]
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
                a.opened_on,
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
    # Bank sync covers its accounts' days like a statement does (ADR-072): no PDF is asked for.
    covered: dict[int, list[tuple[date, date]]] = defaultdict(list)
    for s in stmts:
        covered[s.account_id].append((s.start, s.end))
    for aid, (s_start, s_end) in sync_coverage(db, accounts, today).items():
        covered[aid].append((s_start, s_end))
        files[aid].append(TimelineStatement(0, "Bank sync", s_start, s_end, "synced", None))

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
            if a.opened_on is not None and a.opened_on > end:
                continue  # opened after this month: nothing expected
            # Closed or opened during the month: expected only while it was open.
            a_end = min(end, a.closed_on) if a.closed_on else end
            a_start = max(m, a.opened_on) if a.opened_on else m
            periods = covered[a.account_id]
            gaps = _gaps(periods, a_start, a_end)
            uncovered = sum((g_end - g_start).days + 1 for g_start, g_end in gaps)
            days = (a_end - a_start).days + 1
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
        _recurring(db, ms, today)
        _notes(db, ms, by_account)
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
