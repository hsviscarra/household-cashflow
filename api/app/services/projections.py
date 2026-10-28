"""Projections (F15, ADR-013): the next three months, the lowest cash balance between paydays,
and spending categories running more than 30% above their recent average.

For each of the next three months:
- income and fixed outflows are the recurring items (F11): the month's entry when it exists (a
  skip counts nothing, a one-month change counts as changed), else the template's amount;
- variable spending is the average of the last three complete months of spending lines that
  no recurring item paid (mart.v_spending_line), in cash terms: card purchases are left out
  because the card payments, recurring items themselves, carry them;
- purchase installments are each purchase in progress's installment (F14) while installments are
  left, unless a recurring item already pays its category.
Cash starts from the bank accounts' latest statement balances. Day by day, each recurring item
lands on the day of the month it was last paid (the 1st when it never was), installments on the
day of their last payment, and variable spending is spread evenly over the days.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, RecurringEntry, RecurringTemplate, Transaction
from app.models import v_spending_line as v
from app.services import networth, recurring

MONTHS_AHEAD = 3
AVERAGE_OVER = 3
ALERT_RATIO = Decimal("1.30")
ALERT_MIN = Decimal(25)
ZERO = Decimal(0)
CENT = Decimal("0.01")
INCOME = ("income", "refund")


@dataclass
class Event:
    day: date
    name: str
    amount: Decimal  # signed: money in positive
    kind: str  # income, fixed, purchase, variable


@dataclass
class MonthPlan:
    month: date
    income: Decimal = ZERO
    fixed: Decimal = ZERO  # positive: money out
    variable: Decimal = ZERO
    purchases: Decimal = ZERO
    end_cash: Decimal = ZERO
    items: list[Event] = field(default_factory=list)

    @property
    def net(self) -> Decimal:
        return self.income - self.fixed - self.variable - self.purchases


@dataclass
class Alert:
    month: date
    group_id: int
    group_name: str
    amount: Decimal
    average: Decimal

    @property
    def change(self) -> Decimal | None:
        if not self.average:
            return None
        return ((self.amount - self.average) / self.average).quantize(Decimal("0.0001"))


@dataclass
class Projection:
    today: date
    start_cash: Decimal
    cash_as_of: date | None
    variable_per_month: Decimal
    average_months: list[date]
    months: list[MonthPlan]
    daily: list[tuple[date, Decimal]]
    lowest: tuple[date, Decimal] | None
    next_payday: Event | None
    alerts: list[Alert]


def _usual_days(db: Session) -> dict[int, int]:
    """The day of the month each recurring item was last paid."""
    out: dict[int, tuple[date, int]] = {}
    for template_id, txn_date in db.execute(
        select(RecurringEntry.template_id, Transaction.txn_date)
        .join(Transaction, Transaction.recurring_entry_id == RecurringEntry.entry_id)
        .where(Transaction.source != "excel_history")
    ):
        if template_id not in out or txn_date > out[template_id][0]:
            out[template_id] = (txn_date, txn_date.day)
    return {k: day for k, (_, day) in out.items()}


def _on(month: date, day: int) -> date:
    return min(
        month.replace(day=1) + timedelta(days=day - 1),
        recurring.add_months(month, 1) - timedelta(days=1),
    )


def variable_average(db: Session, today: date) -> tuple[Decimal, list[date]]:
    """Average monthly spending no recurring item paid, over the last complete months, in cash
    terms: card purchases are left out because the card payments (recurring items) carry them."""
    current = recurring.first(today)
    months = [recurring.add_months(current, -i) for i in range(AVERAGE_OVER, 0, -1)]
    t = Transaction.__table__
    a = Account.__table__
    total = db.scalar(
        select(func.sum(v.c.amount))
        .select_from(
            v.join(t, t.c.transaction_id == v.c.transaction_id).outerjoin(
                a, a.c.account_id == v.c.account_id
            )
        )
        .where(
            v.c.cash_month.in_(months),
            t.c.recurring_entry_id.is_(None),
            (a.c.kind.is_(None)) | (a.c.kind != "credit_card"),
        )
    )
    have = list(db.scalars(select(v.c.cash_month).where(v.c.cash_month.in_(months)).distinct()))
    if not have:
        return ZERO, []
    return (Decimal(str(total or 0)) / len(have)).quantize(CENT), sorted(have)


def _recurring_events(db: Session, month: date, days: dict[int, int]) -> list[Event]:
    entries = {
        e.template_id: e
        for e in db.scalars(select(RecurringEntry).where(RecurringEntry.month == month))
    }
    linked = set(
        db.scalars(
            select(Transaction.recurring_entry_id).where(
                Transaction.recurring_entry_id.in_([e.entry_id for e in entries.values()] or [-1])
            )
        )
    )
    history = recurring.amounts(db)
    out = []
    for t in db.scalars(select(RecurringTemplate)):
        e = entries.get(t.template_id)
        if e is not None:
            if e.status == "skipped" or e.entry_id in linked:
                continue  # skipped, or already paid
            amount = e.amount
        elif recurring.active_in(t, month):
            found = recurring.amount_for(history[t.template_id], month)
            if found is None:
                continue
            amount = found
        else:
            continue
        kind = "income" if t.type in INCOME else "fixed"
        out.append(Event(_on(month, days.get(t.template_id, 1)), t.name, amount, kind))
    return out


def _purchase_events(
    db: Session, today: date, months: list[date], paid_categories: set[int]
) -> list[Event]:
    out = []
    for item in networth.holdings(db, today):
        p = item.purchase
        if not item.is_active or p is None or not p.installment or not p.installments_left:
            continue
        if item.category_id in paid_categories:
            continue  # a recurring item pays it already
        last_day = (
            db.scalar(
                select(func.max(Transaction.txn_date)).where(
                    Transaction.category_id == item.category_id
                )
            )
            if item.category_id
            else None
        )
        day = last_day.day if last_day else 1
        left = p.installments_left
        for m in months:
            if left <= 0:
                break
            when = _on(m, day)
            if when < today:
                continue
            out.append(Event(when, f"{item.name} installment", -p.installment, "purchase"))
            left -= 1
    return out


def alerts(db: Session, today: date) -> list[Alert]:
    """Groups that spent more than 30% (and at least 25.00) above their average of the three
    months before, in the last complete month. The average counts the months that have any
    spending; a group new this month has no average and no alert."""
    month = recurring.add_months(recurring.first(today), -1)
    before = [recurring.add_months(month, -i) for i in range(AVERAGE_OVER, 0, -1)]
    by: dict[tuple[int, date], Decimal] = defaultdict(Decimal)
    names: dict[int, str] = {}
    for gid, gname, m, total in db.execute(
        select(v.c.group_id, v.c.group_name, v.c.cash_month, func.sum(v.c.amount))
        .where(v.c.cash_month.in_([*before, month]))
        .group_by(v.c.group_id, v.c.group_name, v.c.cash_month)
    ):
        by[(gid, m)] += Decimal(str(total))
        names[gid] = gname
    have = {m for (_, m) in by if m in before}
    if not have:
        return []
    out = []
    for gid, name in names.items():
        amount = by.get((gid, month), ZERO)
        average = (sum((by.get((gid, m), ZERO) for m in have), ZERO) / len(have)).quantize(CENT)
        # A group with no spending before can't be "30% above" anything: only real increases.
        if average > 0 and amount - average >= ALERT_MIN and amount > average * ALERT_RATIO:
            out.append(Alert(month, gid, name, amount, average))
    return sorted(out, key=lambda a: -(a.amount - a.average))


def project(db: Session, today: date | None = None) -> Projection:
    today = today or date.today()
    current = recurring.first(today)
    months = [recurring.add_months(current, i) for i in range(1, MONTHS_AHEAD + 1)]
    end = recurring.add_months(months[-1], 1) - timedelta(days=1)

    cash_items = [
        i for i in networth.accounts(db, today) if i.holding_class == "cash" and i.is_active
    ]
    start_cash = sum((i.value or ZERO for i in cash_items), ZERO)
    cash_as_of = min((i.as_of for i in cash_items if i.as_of), default=None)

    variable, avg_months = variable_average(db, today)
    days = _usual_days(db)
    paid_categories = {t.category_id for t in db.scalars(select(RecurringTemplate))}

    # Events from today to the end of the third month: what is left of this month, then the
    # three months.
    events = [e for e in _recurring_events(db, current, days) if e.day >= today]
    for m in months:
        events += _recurring_events(db, m, days)
    events += _purchase_events(db, today, [current, *months], paid_categories)

    plans = {m: MonthPlan(m) for m in months}
    for e in events:
        plan = plans.get(recurring.first(e.day))
        if plan is None:
            continue
        plan.items.append(e)
        if e.kind == "income":
            plan.income += e.amount
        elif e.kind == "purchase":
            plan.purchases -= e.amount
        else:
            plan.fixed -= e.amount
    for plan in plans.values():
        plan.variable = variable
        plan.items.sort(key=lambda e: (e.day, e.name))

    # Day by day.
    by_day: dict[date, Decimal] = defaultdict(Decimal)
    for e in events:
        by_day[e.day] += e.amount
    daily: list[tuple[date, Decimal]] = []
    balance = start_cash
    day = today
    while day <= end:
        month_days = (recurring.add_months(recurring.first(day), 1) - recurring.first(day)).days
        balance += by_day.get(day, ZERO) - variable / month_days
        daily.append((day, balance.quantize(CENT)))
        if day == recurring.add_months(recurring.first(day), 1) - timedelta(days=1):
            p = plans.get(recurring.first(day))
            if p is not None:
                p.end_cash = balance.quantize(CENT)
        day += timedelta(days=1)

    lowest = min(daily, key=lambda d: (d[1], d[0])) if daily else None
    payday = None
    if lowest is not None:
        later = sorted(
            (e for e in events if e.kind == "income" and e.day > lowest[0]), key=lambda e: e.day
        )
        payday = later[0] if later else None
    return Projection(
        today,
        start_cash,
        cash_as_of,
        variable,
        avg_months,
        list(plans.values()),
        daily,
        lowest,
        payday,
        alerts(db, today),
    )
