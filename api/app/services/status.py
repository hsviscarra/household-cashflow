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
from collections import defaultdict
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
class Status:
    today: date
    excel_through: date | None
    accounts: list[Account]
    months: list[MonthStatus]
    loads: list[Load]


@dataclass
class _Stmt:
    file_id: int
    file_name: str
    account_id: int
    start: date
    end: date
    opening: Decimal | None
    closing: Decimal | None


def _approved_statements(db: Session) -> list[_Stmt]:
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
    accounts = list(
        db.scalars(select(Account).where(Account.is_active.is_(True)).order_by(Account.name))
    )
    stmts = _approved_statements(db)
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

    out: list[MonthStatus] = []
    for m in months:
        ms = MonthStatus(m, "statements")
        end = month_end(m)
        last = min(end, today)  # the current month is checked up to today
        for a in accounts:
            periods = [(s.start, s.end) for s in by_account[a.account_id]]
            gaps = _gaps(periods, m, end)
            uncovered = sum((g_end - g_start).days + 1 for g_start, g_end in gaps)
            days = (end - m).days + 1
            ms.coverage.append(Coverage(a.account_id, days - uncovered, days))
            open_gaps = [(g_start, min(g_end, last)) for g_start, g_end in gaps if g_start <= last]
            if not open_gaps:
                continue
            if (
                len(open_gaps) == 1
                and open_gaps[0] == (m, last)
                and not any(p_start <= end and p_end >= m for p_start, p_end in periods)
            ):
                text = f"{a.name}: no statement for {m:%B}"
            else:
                text = f"{a.name}: no statement for " + ", ".join(
                    _days(g_start, g_end) for g_start, g_end in open_gaps
                )
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
    return Status(today, excel_through, accounts, out, loads(db))


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
