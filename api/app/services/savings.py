"""Saving, on one page (ADR-097, plan items C5 and C6): the savings rate by month, what the
goals need each month, the debts and the order to pay them in, and what is safe to spend for
the rest of this month.

Everything here is a calculation from the household's own numbers. It doesn't recommend an
investment or a product.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppSetting, Transaction
from app.services import debt, goals, measures, networth, payoff, projections
from app.services.cashflow import counted
from app.services.recurring import add_months, first

# Assumptions (ADR-097).
RATE_MONTHS = 12  # months of savings rate shown
CARD_MINIMUM_SHARE = Decimal("0.03")  # a card's minimum payment when none was typed: 3%…
CARD_MINIMUM_FLOOR = Decimal(25)  # …and never under 25.00
TERMS_KEY = "debt-terms:"  # + the balance-sheet item's key
MAX_RATE = Decimal(2)  # 200% a year: anything over is a typing mistake
MAX_AMOUNT = Decimal(1_000_000)  # the largest payment or extra a month the page accepts

ZERO = Decimal(0)
CENT = Decimal("0.01")
RATE = Decimal("0.0001")


class SavingsError(Exception):
    """Something asked of this page that can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


# ---------------- savings rate ----------------
@dataclass
class RateMonth:
    """One month of the savings rate: what came in, what was spent and what was set aside."""

    month: date
    money_in: Decimal
    spent: Decimal
    set_aside: Decimal
    running: bool  # this month so far

    @property
    def kept(self) -> Decimal:
        """Free cash: what was there to set aside."""
        return self.money_in - self.spent

    @property
    def rate(self) -> Decimal | None:
        """The share of the money that came in that wasn't spent; None with no income."""
        return (self.kept / self.money_in).quantize(RATE) if self.money_in > 0 else None


def rate_of(months: list[RateMonth]) -> Decimal | None:
    """The savings rate of several months together: all that was kept over all that came in."""
    came = sum((m.money_in for m in months), ZERO)
    return (sum((m.kept for m in months), ZERO) / came).quantize(RATE) if came > 0 else None


def rate_months(db: Session, today: date) -> list[RateMonth]:
    """The last `RATE_MONTHS` months, oldest first; the running month counts to today."""
    current = first(today)
    return [
        RateMonth(
            p.month,
            p.measures.money_in,
            p.measures.spent,
            p.measures.set_aside,
            running=p.month == current,
        )
        for p in measures.month(db, today, today, None, RATE_MONTHS).months
    ]


# ---------------- the goals' plan ----------------
@dataclass
class GoalPlan:
    """What the open goals need a month against what is planned and already saved."""

    needed: Decimal  # a month, for every dated goal to arrive on time
    planned: Decimal  # a month, as typed on the goals
    saved: Decimal  # put into savings this month so far
    open_goals: list[goals.GoalView] = field(default_factory=list)

    @property
    def to_go(self) -> Decimal:
        """Of what is planned, what hasn't been set aside yet this month."""
        return max(ZERO, self.planned - self.saved)

    @property
    def short(self) -> Decimal:
        """How far the plan is from what the goals need."""
        return max(ZERO, self.needed - self.planned)


def saved_in(db: Session, month: date) -> Decimal:
    """Money put into savings in a month (lines in a savings category)."""
    q = select(func.sum(Transaction.amount)).where(
        Transaction.cash_month == month, Transaction.type == "savings"
    )
    return -Decimal(str(db.scalar(counted(q, None)) or 0))


def goal_plan(db: Session, today: date) -> GoalPlan:
    """The plan over the goals that are active and not reached yet."""
    live = [g for g in goals.all_goals(db, today) if g.is_active and g.status != "reached"]
    return GoalPlan(
        sum((g.needed_monthly or ZERO for g in live), ZERO),
        sum((g.monthly_amount or ZERO for g in live), ZERO),
        saved_in(db, first(today)),
        live,
    )


# ---------------- safe to spend ----------------
@dataclass
class Safe:
    """What can still be spent this month without touching the bills or the goals."""

    month: date
    left_so_far: Decimal  # money in, less spent and set aside, to today
    income_to_come: Decimal
    bills_to_come: Decimal
    goals_to_go: Decimal
    days_left: int  # today included

    @property
    def amount(self) -> Decimal:
        """What is safe to spend: what is left, plus income to come, less bills and goals to go."""
        return self.left_so_far + self.income_to_come - self.bills_to_come - self.goals_to_go

    @property
    def a_day(self) -> Decimal:
        """The same per day left in the month, never under zero."""
        return (max(ZERO, self.amount) / self.days_left).quantize(CENT)


def safe_to_spend(db: Session, today: date, plan: GoalPlan | None = None) -> Safe:
    """What is left so far this month, plus income still to come, less the bills still due
    and what the goals' plan still needs. `plan` avoids reading the goals twice."""
    month = first(today)
    so_far = measures.window(db, month, today.day)
    ahead = projections.rest_of_month(db, today)
    plan = plan or goal_plan(db, today)
    return Safe(
        month,
        so_far.left_over,
        sum((e.amount for e in ahead if e.amount > 0), ZERO),
        -sum((e.amount for e in ahead if e.amount < 0), ZERO),
        plan.to_go,
        (add_months(month, 1) - today).days,
    )


# ---------------- debts ----------------
@dataclass
class DebtLine:
    """One thing owed, with its rate and payment where known and where each came from."""

    key: str
    name: str
    kind: str  # card or loan
    balance: Decimal
    as_of: date | None
    rate: Decimal | None  # a year, as a fraction
    minimum: Decimal | None
    rate_from: str | None  # typed, or table (the amortization table)
    minimum_from: str | None  # typed, table, payment (the monthly payment), assumed
    interest_12: Decimal = ZERO  # interest and fees in the last 12 months (cards)

    @property
    def planned(self) -> bool:
        """It has what the comparison needs."""
        return self.rate is not None and self.minimum is not None and self.minimum > 0


def _typed(db: Session, key: str) -> tuple[Decimal | None, Decimal | None]:
    row = db.get(AppSetting, TERMS_KEY + key)
    if row is None:
        return None, None
    try:
        saved = json.loads(row.setting_value)
        rate, minimum = saved.get("rate"), saved.get("minimum")
        return (
            Decimal(rate) if rate is not None else None,
            Decimal(minimum) if minimum is not None else None,
        )
    except (ValueError, TypeError, ArithmeticError, AttributeError):
        return None, None  # a setting that can't be read is as if nothing was typed


def set_terms(
    db: Session, key: str, rate: Decimal | None, minimum: Decimal | None, user: str, today: date
) -> None:
    """Keep a debt's yearly rate and monthly payment as typed; both empty forgets them."""
    if key not in {d.key for d in debts(db, today)}:
        raise SavingsError("That debt isn't on the balance sheet.", 404)
    if rate is not None and not ZERO <= rate <= MAX_RATE:
        raise SavingsError("The rate is a year's, as a fraction: 0.156 for 15.6%.")
    if minimum is not None and minimum < 0:
        raise SavingsError("The monthly payment can't be negative.")
    row = db.get(AppSetting, TERMS_KEY + key)
    if rate is None and minimum is None:
        if row is not None:
            db.delete(row)
    else:
        value = json.dumps(
            {
                "rate": str(rate) if rate is not None else None,
                "minimum": str(minimum) if minimum is not None else None,
            }
        )
        if row is None:
            db.add(AppSetting(setting_key=TERMS_KEY + key, setting_value=value, updated_by=user))
        else:
            row.setting_value, row.updated_by = value, user
    db.commit()


def loan_terms(item: networth.Item) -> tuple[Decimal | None, Decimal | None, str | None]:
    """A loan's rate and payment: (rate, payment, where the payment is from)."""
    s = item.loan.schedule if item.loan else None
    if s is not None and s.next_total is not None and s.balance and s.left:
        # The table's interest still to pay, spread over the balance and the time left, is a
        # fair yearly rate for comparing debts (the balance halves on the way, hence the 2).
        years = Decimal(s.left) / payoff.MONTHS_IN_YEAR
        rate = (2 * s.interest_left / s.balance / years).quantize(RATE)
        return rate, s.next_total, "table"
    if item.loan and item.loan.monthly_payment:
        return None, item.loan.monthly_payment, "payment"
    return None, None, None


def debts(db: Session, today: date) -> list[DebtLine]:
    """What is owed: cards with a balance and loans, with the rate and the monthly payment
    where they can be known (typed wins). Cards have neither until their rate is typed."""
    costs = {a.account_id: a for a in debt.cost(db, today.year, today).accounts}
    out = []
    for item in networth.accounts(db, today) + networth.holdings(db, today):
        if item.side != "liability" or not item.is_active or not item.value or item.value <= 0:
            continue
        typed_rate, typed_minimum = _typed(db, item.key)
        if item.account_id is not None or item.holding_class == "card":
            kind = "card"
            cost = costs.get(item.account_id) if item.account_id is not None else None
            interest = cost.last_12 if cost else ZERO
            # A card's balance is this month's purchases unless it is carried, and the app
            # can't tell which: a card is planned only once its rate is typed. Its payment is
            # then assumed until that is typed too.
            rate, rate_from = None, None
            minimum: Decimal | None = None
            minimum_from: str | None = None
            if typed_rate is not None:
                minimum = max(CARD_MINIMUM_FLOOR, (item.value * CARD_MINIMUM_SHARE).quantize(CENT))
                minimum_from = "assumed"
        else:
            kind, interest = "loan", ZERO
            rate, minimum, minimum_from = loan_terms(item)
            rate_from = "table" if rate is not None else None
        if typed_rate is not None:
            rate, rate_from = typed_rate, "typed"
        if typed_minimum is not None:
            minimum, minimum_from = typed_minimum, "typed"
        out.append(
            DebtLine(
                item.key,
                item.name,
                kind,
                item.value,
                item.as_of,
                rate,
                minimum,
                rate_from,
                minimum_from,
                interest,
            )
        )
    return sorted(out, key=lambda d: (-(d.rate or ZERO), -d.balance, d.name))


def payoff_plans(lines: list[DebtLine], extra: Decimal) -> payoff.Comparison | None:
    """The two orders compared, over the debts that have a rate and a payment."""
    planned = [
        payoff.Debt(d.key, d.name, d.balance, d.rate or ZERO, d.minimum or ZERO)
        for d in lines
        if d.planned
    ]
    return payoff.compare(planned, extra) if planned else None
