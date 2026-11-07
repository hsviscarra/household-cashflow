"""A monthly budget per spending group (ADR-039). Each group can have an amount from a month on;
with rollover, what was left (or overspent) in earlier months carries into this one, YNAB style.
Spending comes from the same view as the Spending page, so the numbers match it."""

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BudgetPlan, Category, RecurringTemplate
from app.services import recurring, spending
from app.services.recurring import add_months, first

ZERO = Decimal(0)
AVERAGE_OVER = 3
ROUND_TO = Decimal(10)


class BudgetError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _spent_by_group(db: Session, month: date) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for (group_id, _), (amount, _) in spending._by_category(db, month).items():
        out[group_id] = out.get(group_id, ZERO) + amount
    return out


def _plans(db: Session) -> dict[int, list[BudgetPlan]]:
    out: dict[int, list[BudgetPlan]] = {}
    for p in db.scalars(select(BudgetPlan).order_by(BudgetPlan.start_month)):
        out.setdefault(p.category_id, []).append(p)
    return out


def _at(plans: list[BudgetPlan], month: date) -> BudgetPlan | None:
    """The plan in force in a month: the latest start on or before it."""
    current = None
    for p in plans:
        if p.start_month <= month:
            current = p
    return current


def suggestion(db: Session, month: date) -> dict[int, Decimal]:
    """Each group's average over the 3 months before, rounded up to the next $10."""
    totals: dict[int, Decimal] = {}
    for k in range(1, AVERAGE_OVER + 1):
        for g, amount in _spent_by_group(db, add_months(month, -k)).items():
            totals[g] = totals.get(g, ZERO) + amount
    return {
        g: ((t / AVERAGE_OVER) / ROUND_TO).to_integral_value(ROUND_CEILING) * ROUND_TO
        for g, t in totals.items()
        if t > 0
    }


@dataclass
class GroupBudget:
    group_id: int
    name: str
    color: str | None
    budget: Decimal | None  # None = no budget for this group this month
    rollover: bool
    carried: Decimal  # from earlier months (rollover only); negative = overspent before
    spent: Decimal
    available: Decimal  # budget + carried
    left: Decimal  # available - spent
    expected: Decimal  # what pace allows by today (the whole budget for a past month)
    status: str  # over, ahead (spending faster than the month), on_track, none
    suggested: Decimal | None
    since: date | None  # when this amount started


@dataclass
class MonthBudget:
    month: date
    day_share: Decimal  # how much of the month has passed (1 for a past month)
    groups: list[GroupBudget] = field(default_factory=list)
    budgeted: Decimal = ZERO
    spent: Decimal = ZERO  # in groups with a budget
    unbudgeted: Decimal = ZERO  # spending in groups without one
    left: Decimal = ZERO
    has_plans: bool = False


def _carried(
    plans: list[BudgetPlan], month: date, spent_in: dict[date, dict[int, Decimal]]
) -> Decimal:
    """What rolled into this month: for every earlier month since the group's first budget, the
    budget minus what was spent, while that month's plan had rollover on. A month with rollover
    off starts the count again."""
    if not plans:
        return ZERO
    carry = ZERO
    m = plans[0].start_month
    group = plans[0].category_id
    while m < month:
        p = _at(plans, m)
        if p is None or not p.rollover:
            carry = ZERO
        else:
            carry += p.amount - spent_in[m].get(group, ZERO)
        m = add_months(m, 1)
    return carry


def month_view(db: Session, month: date, today: date | None = None) -> MonthBudget:
    today = today or date.today()
    month = first(month)
    if month > first(today):
        share = ZERO
    elif month == first(today):
        days = calendar.monthrange(month.year, month.month)[1]
        share = Decimal(today.day) / Decimal(days)
    else:
        share = Decimal(1)
    plans = _plans(db)
    groups = {
        c.category_id: c
        for c in db.scalars(
            select(Category).where(Category.parent_id.is_(None), Category.kind == "expense")
        )
    }
    earliest = min((ps[0].start_month for ps in plans.values()), default=month)
    spent_in: dict[date, dict[int, Decimal]] = {}
    m = min(earliest, month)
    while m <= month:
        spent_in[m] = _spent_by_group(db, m)
        m = add_months(m, 1)
    now = spent_in[month]
    hints = suggestion(db, month)
    out = MonthBudget(month, share, has_plans=bool(plans))
    for gid, cat in groups.items():
        ps = plans.get(gid, [])
        p = _at(ps, month)
        budget = p.amount if p is not None and p.amount > 0 else None
        spent = now.get(gid, ZERO)
        if budget is None and not spent and gid not in hints:
            continue
        carried = _carried(ps, month, spent_in) if budget is not None and p and p.rollover else ZERO
        available = (budget or ZERO) + carried
        left = available - spent
        expected = (available * share).quantize(Decimal("0.01"))
        if budget is None:
            status = "none"
        elif spent > available:
            status = "over"
        elif share < 1 and spent > expected * Decimal("1.1") and spent > expected + 10:
            status = "ahead"
        else:
            status = "on_track"
        out.groups.append(
            GroupBudget(
                gid,
                cat.name,
                cat.color,
                budget,
                bool(p.rollover) if p is not None else False,
                carried,
                spent,
                available,
                left,
                expected,
                status,
                hints.get(gid),
                p.start_month if p is not None else None,
            )
        )
        if budget is not None:
            out.budgeted += available
            out.spent += spent
        else:
            out.unbudgeted += spent
    out.left = out.budgeted - out.spent
    order = {"over": 0, "ahead": 1, "on_track": 2, "none": 3}
    out.groups.sort(key=lambda g: (order[g.status], -(g.spent)))
    return out


def set_plan(
    db: Session, group_id: int, from_month: date, amount: Decimal, rollover: bool, user: str
) -> BudgetPlan:
    """A group's budget from a month on; later plans of that group are replaced by this one."""
    group = db.get(Category, group_id)
    if group is None:
        raise BudgetError(f"Group {group_id} not found.", 404)
    if group.parent_id is not None or group.kind != "expense":
        raise BudgetError(f"{group.name} isn't a spending group: budgets are set per group.")
    if amount < 0:
        raise BudgetError("A budget can't be negative.")
    from_month = first(from_month)
    for later in db.scalars(
        select(BudgetPlan).where(
            BudgetPlan.category_id == group_id, BudgetPlan.start_month >= from_month
        )
    ):
        db.delete(later)
    db.flush()
    plan = BudgetPlan(
        category_id=group_id,
        start_month=from_month,
        amount=amount,
        rollover=rollover,
        created_by=user[:320],
    )
    db.add(plan)
    db.commit()
    return plan


def start_from_average(db: Session, month: date, user: str) -> int:
    """Every group with spending and no budget yet gets its 3-month average from this month on."""
    month = first(month)
    plans = _plans(db)
    n = 0
    for gid, amount in suggestion(db, month).items():
        if _at(plans.get(gid, []), month) is not None:
            continue
        group = db.get(Category, gid)
        if group is None or group.parent_id is not None or group.kind != "expense":
            continue
        db.add(
            BudgetPlan(
                category_id=gid, start_month=month, amount=amount, rollover=False, created_by=user
            )
        )
        n += 1
    db.commit()
    return n


@dataclass
class SinkingFund:
    """A bill that comes every few months, as an amount to set aside each month (ADR-041)."""

    template_id: int
    name: str
    every_months: int
    amount: Decimal  # what the bill costs each time
    monthly: Decimal  # amount / every_months
    next_due: date
    months_to_go: int  # this month through the due month
    should_have: Decimal  # set aside by now since the last time it was due


def sinking_funds(db: Session, month: date) -> list[SinkingFund]:
    """Every active bill that repeats every 2 to 12 months: its share per month, when it's next
    due and how much should already be put aside for it."""
    month = first(month)
    templates = [
        t
        for t in db.scalars(select(RecurringTemplate).where(RecurringTemplate.is_active))
        if (t.every_months or 1) > 1
        and t.type not in recurring.INCOME_TYPES
        and (t.end_month is None or t.end_month >= month)
    ]
    history = recurring.amounts(db, [t.template_id for t in templates])
    out = []
    for t in templates:
        every = t.every_months
        nxt = max(month, t.start_month)
        while not recurring.due_in(t, nxt):
            nxt = add_months(nxt, 1)
        amount = abs(recurring.amount_for(history.get(t.template_id, []), nxt) or ZERO)
        if not amount:
            continue
        to_go = (nxt.year - month.year) * 12 + nxt.month - month.month + 1
        monthly = (amount / every).quantize(Decimal("0.01"), ROUND_CEILING)
        out.append(
            SinkingFund(
                t.template_id,
                t.name,
                every,
                amount,
                monthly,
                nxt,
                to_go,
                min(amount, monthly * (every - to_go + 1)) if t.start_month < nxt else ZERO,
            )
        )
    return sorted(out, key=lambda f: (f.next_due, f.name))
