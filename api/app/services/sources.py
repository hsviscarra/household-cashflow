"""Which source counts for a month (F19, ADR-018): the Cash Flow workbook or the statements.

"statements_from" (core.app_setting) is the first month whose statements count; every workbook
month before it keeps the workbook (ADR-004). From that month on the workbook stays as a
reference: the check below puts its totals next to the statements' for each month both cover,
so a missing statement or a wrongly categorized line shows up as a gap. Moving the month never
deletes anything; it only changes which source the views count.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session, aliased

from app.models import AppSetting, Category, Transaction
from app.services import recurring

KEY = "statements_from"
ZERO = Decimal(0)
SPENDING = ("expense", "fee_interest", "refund")


class SourceError(Exception):
    """The comparison can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def statements_from(db: Session) -> date | None:
    """The first month whose statements count in place of the workbook; None when not set."""
    s = db.get(AppSetting, KEY)
    return date.fromisoformat(s.setting_value) if s else None


def workbook_months(db: Session) -> list[date]:
    """The months the workbook has rows for."""
    return sorted(
        db.scalars(
            select(Transaction.cash_month).where(Transaction.source == "excel_history").distinct()
        )
    )


def set_statements_from(db: Session, month: date | None, user: str) -> date | None:
    """Set (or clear, with None) the first month whose statements count. Recurring items that
    were matched to workbook rows in months that now use statements are matched again, to the
    statements."""
    if month is not None:
        month = recurring.first(month)
        if month > recurring.first(date.today()):
            raise SourceError("That month hasn't started yet.")
    current = db.get(AppSetting, KEY)
    if month is None:
        if current is not None:
            db.delete(current)
    elif current is None:
        db.add(AppSetting(setting_key=KEY, setting_value=month.isoformat(), updated_by=user))
    else:
        current.setting_value, current.updated_by = month.isoformat(), user
        current.updated_at = datetime.now()
    db.flush()
    # Workbook rows in statement months no longer pay recurring items; statements can.
    if month is not None:
        db.execute(
            update(Transaction)
            .where(
                Transaction.source == "excel_history",
                Transaction.cash_month >= month,
                Transaction.recurring_entry_id.is_not(None),
            )
            .values(recurring_entry_id=None)
        )
    db.commit()
    for m in workbook_months(db):
        if month is None or m >= month:
            recurring.match(db, m, user)
    db.commit()
    return month


# ---------------------------------------------------------------- workbook vs statements
@dataclass
class GroupGap:
    """A group's spending in the workbook and in the statements."""

    group: str
    workbook: Decimal = ZERO
    statements: Decimal = ZERO

    @property
    def difference(self) -> Decimal:
        """Statements less workbook for the group."""
        return self.statements - self.workbook


@dataclass
class MonthCheck:
    """A month in the workbook against the same month in the statements."""

    month: date
    workbook_income: Decimal = ZERO
    statements_income: Decimal = ZERO
    workbook_spending: Decimal = ZERO
    statements_spending: Decimal = ZERO
    statement_lines: int = 0
    groups: list[GroupGap] = field(default_factory=list)


def _group_names(db: Session) -> dict[int, str]:
    """category_id -> the name of its group (its parent, or itself when it has none)."""
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    return {c.category_id: (cats.get(c.parent_id or -1) or c).name for c in cats.values()}


def _count(c: MonthCheck, gaps: dict[str, GroupGap], row: tuple[str, str, str, Decimal]) -> None:
    """Add one line to its month, on the workbook's side or the statements'."""
    source, kind, group, amount = row
    workbook = source == "excel_history"
    if not workbook:
        c.statement_lines += 1
    if kind == "income":
        if workbook:
            c.workbook_income += amount
        else:
            c.statements_income += amount
    elif kind in SPENDING:
        g = gaps.setdefault(group, GroupGap(group))
        if workbook:
            c.workbook_spending -= amount
            g.workbook -= amount
        else:
            c.statements_spending -= amount
            g.statements -= amount


def check(db: Session) -> list[MonthCheck]:
    """For each month that has workbook rows and counts statements: income and spending from
    each source, and spending per group, biggest gap first. Spending as on the Spending page
    (expenses, fees and interest, less refunds); transfers left out; split lines through their
    parts."""
    since = statements_from(db)
    months = [m for m in workbook_months(db) if m >= since] if since is not None else []
    if not months:
        return []
    groups = _group_names(db)
    part = aliased(Transaction)
    has_parts = exists().where(part.parent_transaction_id == Transaction.transaction_id)
    rows = db.execute(
        select(
            Transaction.cash_month,
            Transaction.source,
            Transaction.type,
            Transaction.category_id,
            Transaction.amount,
        ).where(
            Transaction.cash_month.in_(months),
            Transaction.type != "transfer",
            ~has_parts,
        )
    )
    checks = {m: MonthCheck(m) for m in months}
    gaps: dict[date, dict[str, GroupGap]] = defaultdict(dict)
    for m, source, kind, category_id, amount in rows:
        group = groups.get(category_id or -1, "Uncategorized")
        _count(checks[m], gaps[m], (source, kind, group, Decimal(str(amount))))
    for m, c in checks.items():
        c.groups = sorted(
            (g for g in gaps[m].values() if g.workbook or g.statements),
            key=lambda g: (-abs(g.difference), g.group),
        )
    return [checks[m] for m in months]
