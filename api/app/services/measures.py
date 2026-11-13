"""The four measures of a month, and fair comparisons (ADR-073).

- Money in: income.
- Spent: purchases, bills, fees and interest, less refunds. In the workbook's months, paying a
  card counts as spent too, since the workbook didn't have the card's purchases.
- Set aside: savings, investing, the new house and loan payments. Money you still have, in
  another form.
- Free cash = money in - spent: what was there to set aside.
- Left over = free cash - set aside: what stayed in the bank accounts (what "Kept" showed).

A month still running is compared with the same days of the month before ("Nov 1-11 vs Oct
1-11"); a finished month with the whole month before.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction
from app.services.cashflow import counted
from app.services.recurring import add_months, first

ZERO = Decimal(0)
CARD_PAYMENT = "Card Payment"  # the workbook's card payments: spending it couldn't itemize
SPENT = ("expense", "fee_interest", "refund")


@dataclass
class Measures:
    money_in: Decimal = ZERO
    spent: Decimal = ZERO
    set_aside: Decimal = ZERO

    @property
    def free_cash(self) -> Decimal:
        return self.money_in - self.spent

    @property
    def left_over(self) -> Decimal:
        return self.free_cash - self.set_aside

    def out(self) -> dict[str, Decimal]:
        return {
            "money_in": self.money_in,
            "spent": self.spent,
            "set_aside": self.set_aside,
            "free_cash": self.free_cash,
            "left_over": self.left_over,
        }


@dataclass
class Period:
    month: date
    start: date
    end: date
    measures: Measures


@dataclass
class Month:
    month: date
    through: date  # the last day counted: today in a running month, else the month's end
    running: bool
    this: Period
    before: Period  # the same days of the month before, or the whole month when finished
    months: list[Period] = field(default_factory=list)  # whole months, oldest first


def month_end(m: date) -> date:
    return m.replace(day=monthrange(m.year, m.month)[1])


def window(
    db: Session, month: date, last_day: int | None = None, person: str | None = None
) -> Measures:
    """The month's measures, counting only its first `last_day` days when given (the workbook's
    months have no days: they count whole)."""
    t = Transaction
    q = (
        select(t.type, Category.name, func.sum(t.amount))
        .outerjoin(Category, Category.category_id == t.category_id)
        .where(t.cash_month == month)
        .group_by(t.type, Category.name)
    )
    if last_day is not None:
        cut = month.replace(day=min(last_day, monthrange(month.year, month.month)[1]))
        q = q.where(or_(t.txn_date <= cut, t.source == "excel_history"))
    m = Measures()
    for typ, cname, total in db.execute(counted(q, person)):
        _count(m, typ, cname, Decimal(str(total or 0)))
    return m


def _count(m: Measures, typ: str, category: str | None, amount: Decimal) -> None:
    """Add one total to the measure it belongs to (the rules at the top of this module)."""
    if typ == "income":
        m.money_in += amount
    elif typ in SPENT or (typ == "debt_payment" and category == CARD_PAYMENT):
        m.spent -= amount
    elif typ in ("savings", "debt_payment"):
        m.set_aside -= amount


def spent_by_month(db: Session, months: list[date]) -> dict[date, Decimal]:
    """What was spent in each of `months`, on the same terms as `window`, in one query. The
    workbook's months and the statements' read alike (a card payment there, its purchases
    here), which is what makes them comparable month to month (ADR-096)."""
    t = Transaction
    q = (
        select(t.cash_month, t.type, Category.name, func.sum(t.amount))
        .outerjoin(Category, Category.category_id == t.category_id)
        .where(t.cash_month.in_(months))
        .group_by(t.cash_month, t.type, Category.name)
    )
    found: dict[date, Measures] = {}
    for month, typ, cname, total in db.execute(counted(q, None)).all():
        _count(found.setdefault(month, Measures()), typ, cname, Decimal(str(total or 0)))
    return {month: m.spent for month, m in found.items()}


def month(db: Session, m: date, today: date, person: str | None = None, months: int = 12) -> Month:
    m = first(m)
    end = month_end(m)
    running = m <= today <= end
    through = today if running else end
    prev = add_months(m, -1)
    if running:
        this = Period(m, m, through, window(db, m, through.day, person))
        prev_end = prev.replace(day=min(through.day, month_end(prev).day))
        before = Period(prev, prev, prev_end, window(db, prev, through.day, person))
    else:
        this = Period(m, m, end, window(db, m, None, person))
        before = Period(prev, prev, month_end(prev), window(db, prev, None, person))
    history = []
    for i in range(months - 1, -1, -1):
        k = add_months(m, -i)
        k_end = month_end(k)
        if k > today:
            continue
        cut = today.day if k <= today <= k_end else None
        history.append(Period(k, k, min(k_end, today), window(db, k, cut, person)))
    return Month(m, through, running, this, before, history)
