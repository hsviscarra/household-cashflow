"""Which month a line's money counts in (ADR-084, replacing ADR-070's early-pay rule).

Every line counts in the month of its date, except a salary: it counts in the month it pays for.
Hernan is paid around the 20th and Lauren on the last day of the month, both for the month that
follows, so a salary received on the 15th or later counts in the next month and one received
before the 15th (a payroll that slipped to the 1st) in its own. Without this a month shows no
income until the 20th, and what came in then was the next month's money.

A salary is a line with money in whose category is under the income group "Salary". The month is
kept in `core.transaction.cash_month`; `settle` sets it whenever a line is added or changed
(a listener in app.models calls it before every flush), so a category chosen later, by a rule,
Claude or a person, moves the line at that moment. The line's date never changes.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import Category, ChangeLog, Transaction

SALARY_GROUP = "Salary"
NEXT_FROM_DAY = 15  # paid on or after this day: the pay of the month that follows
MOVE_MONTHS = 1  # a line may be moved this many months before or after the month of its date


class MonthError(Exception):
    """A month a line can't be moved to."""


def first(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def month_for(txn_date: date, salary: bool) -> date:
    if salary and txn_date.day >= NEXT_FROM_DAY:
        return next_month(txn_date)
    return first(txn_date)


def cash_month(txn_date: date, description: str, amount: Decimal) -> date:
    """The month of a line just read, before it has a category: the month of its date. `settle`
    moves it when it turns out to be a salary."""
    return first(txn_date)


def salary_categories(db: Session) -> set[int]:
    group = aliased(Category)
    return set(
        db.scalars(
            select(Category.category_id)
            .join(group, group.category_id == Category.parent_id)
            .where(group.name == SALARY_GROUP, group.parent_id.is_(None))
        )
    )


def settle(db: Session) -> None:
    """Before a flush: give every new or changed line from a bank its month. The workbook's
    months are left as loaded (they have no days)."""
    rows = [
        o
        for o in (*db.new, *db.dirty)
        if isinstance(o, Transaction) and o.source != "excel_history" and o.txn_date is not None
    ]
    if not rows:
        return
    with db.no_autoflush:
        salaries = salary_categories(db)
    for t in rows:
        is_salary = t.amount is not None and t.amount > 0 and t.category_id in salaries
        # A month a person chose for the line wins over the rule (ADR-089).
        month = t.month_override or month_for(t.txn_date, is_salary)
        if t.cash_month != month:
            t.cash_month = month


def months_apart(a: date, b: date) -> int:
    return abs((a.year - b.year) * 12 + a.month - b.month)


def move(db: Session, t: Transaction, month: date | None, user: str) -> None:
    """Say which month a line counts in (ADR-089), or with None hand it back to the rule. Only
    the month of its date and the ones next to it: further away is a mistake, not a choice.
    The change is logged; `settle` applies it to cash_month at the flush. The caller commits."""
    if month is not None:
        month = first(month)
        if months_apart(month, first(t.txn_date)) > MOVE_MONTHS:
            raise MonthError(
                f"A line dated {t.txn_date:%b %d} can count in {t.txn_date:%B} or the month "
                "before or after it."
            )
    if month == t.month_override:
        return
    db.add(
        ChangeLog(
            table_name="core.transaction",
            row_id=t.transaction_id,
            column_name="month_override",
            old_value=t.month_override.isoformat() if t.month_override else None,
            new_value=month.isoformat() if month else None,
            reason="Counts in another month",
            changed_by=user,
        )
    )
    t.month_override = month
