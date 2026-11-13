"""What every part of recurring shares: months, the error, and a template's amounts over time."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ChangeLog,
    RecurringAmount,
    RecurringEntry,
    RecurringTemplate,
)

MIN_TOLERANCE = Decimal("1.00")
EXCEL_SHEET = "Cash Flow {year}"
INCOME_TYPES = ("income", "refund")
CENT = Decimal("0.01")


class RecurringError(Exception):
    """A recurring change that can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- months
def first(d: date) -> date:
    """The first day of a date's month."""
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    """The first day of the month `n` months after (or before) a date's."""
    i = d.year * 12 + d.month - 1 + n
    return date(i // 12, i % 12 + 1, 1)


def months(start: date, end: date) -> list[date]:
    """Every month from one date's month to another's, both included."""
    out, m = [], first(start)
    while m <= first(end):
        out.append(m)
        m = add_months(m, 1)
    return out


def _log(
    db: Session, table: str, row_id: int, column: str, old: object, new: object, why: str, user: str
) -> None:
    if old != new:
        db.add(
            ChangeLog(
                table_name=table,
                row_id=row_id,
                column_name=column,
                old_value=None if old is None else str(old)[:400],
                new_value=None if new is None else str(new)[:400],
                reason=why,
                changed_by=user,
            )
        )


# ---------------------------------------------------------------- templates and amounts
def amounts(db: Session, template_ids: list[int] | None = None) -> dict[int, list[RecurringAmount]]:
    """Each recurring item's amounts over time (from which month each applies), oldest first."""
    q = select(RecurringAmount).order_by(RecurringAmount.from_month)
    if template_ids is not None:
        q = q.where(RecurringAmount.template_id.in_(template_ids))
    out: dict[int, list[RecurringAmount]] = defaultdict(list)
    for a in db.scalars(q):
        out[a.template_id].append(a)
    return out


def amount_for(history: list[RecurringAmount], month: date) -> Decimal | None:
    """The amount in force in a month: the latest change on or before it."""
    hit = None
    for a in history:
        if a.from_month <= month:
            hit = a.amount
    return hit


EVERY = (0, 1, 2, 3, 4, 6, 12)  # 0: once


def due_in(t: RecurringTemplate, month: date) -> bool:
    """Whether the item falls in `month` by how often it repeats (ADR-031): monthly every month,
    every N months counted from its first month, once only then."""
    every = t.every_months if t.every_months is not None else 1
    if every == 0:
        return month == t.start_month
    gap = (month.year - t.start_month.year) * 12 + month.month - t.start_month.month
    return gap % every == 0


def active_in(t: RecurringTemplate, month: date) -> bool:
    """Whether a recurring item is due in a month: active, within its dates and on its frequency."""
    return (
        t.is_active
        and t.start_month <= month
        and (t.end_month is None or month <= t.end_month)
        and due_in(t, month)
    )


def signed(type_: str, amount: Decimal) -> Decimal:
    """Templates are entered as positive numbers; income is money in, everything else out."""
    value = abs(amount)
    return value if type_ in INCOME_TYPES else -value


def get_template(db: Session, template_id: int) -> RecurringTemplate:
    """The recurring item, or RecurringError 404."""
    t = db.get(RecurringTemplate, template_id)
    if t is None:
        raise RecurringError(f"Template {template_id} not found.", 404)
    return t


def get_entry(db: Session, entry_id: int) -> RecurringEntry:
    """One month of a recurring item, or RecurringError 404."""
    e = db.get(RecurringEntry, entry_id)
    if e is None:
        raise RecurringError(f"Entry {entry_id} not found.", 404)
    return e
