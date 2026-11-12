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

from app.models import Category, Transaction

SALARY_GROUP = "Salary"
NEXT_FROM_DAY = 15  # paid on or after this day: the pay of the month that follows


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
        month = month_for(t.txn_date, is_salary)
        if t.cash_month != month:
            t.cash_month = month
