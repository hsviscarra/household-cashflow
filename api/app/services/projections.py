"""Projections (F15, ADR-013): the next three months, the lowest cash balance between paydays,
and spending categories running more than 30% above their recent average.

For each of the next three months:
- income and fixed outflows are the recurring items (F11): the month's entry when it exists (a
  skip counts nothing, a one-month change counts as changed), else the template's amount;
- variable spending is the average of the last three complete months of spending lines that
  no recurring item paid (mart.v_spending_line), in cash terms: card purchases are left out
  because the card payments, recurring items themselves, carry them;
- a recurring item that pays a loan with an amortization table (ADR-014) uses the table's
  installment for the month, and nothing once the loan is paid off;
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
from app.services import loans, networth, payday, people, recurring, tax_projection

MONTHS_AHEAD = 3
AVERAGE_OVER = 3
HORIZONS = (1, 3, 12)  # months ahead the page offers (ADR-033)
AVERAGES = (3, 6, 12)  # months of everyday spending to average
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
    kind: str  # income, fixed, purchase, variable, change (a what-if)
    account_id: int | None = None  # the bank account it moves, when known
    # The month it counts in when that isn't the month of its day: a salary arrives the month
    # before the one it pays for (ADR-084).
    month: date | None = None


@dataclass
class Change:
    """A what-if (ADR-033): an amount (signed, money in positive) monthly from a day of the
    month, or once on a date, optionally in one account."""

    name: str
    amount: Decimal
    every: str = "month"  # month or once
    day: int = 1
    on: date | None = None
    account_id: int | None = None


@dataclass
class AccountRun:
    """One bank account day by day: its balance moved only by the items paid from or into it
    (everyday spending isn't split by account; it's in the total)."""

    account_id: int
    name: str
    start: Decimal
    as_of: date | None
    daily: list[tuple[date, Decimal]]
    lowest: tuple[date, Decimal]
    under_floor: date | None  # the first day under the floor
    move: Decimal  # how much to move in before that day to stay at the floor


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
    # ADR-033: the choices it was made with, per-account runs and money left out.
    horizon: int = MONTHS_AHEAD
    average_over: int = AVERAGE_OVER
    floor: Decimal = ZERO
    held: Decimal = ZERO  # money held for others, left out of the cash unless asked
    include_held: bool = False
    accounts: list[AccountRun] = field(default_factory=list)
    first_short: date | None = None  # the first day total cash is under the floor
    end_cash: Decimal = ZERO


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


def variable_average(
    db: Session, today: date, over: int = AVERAGE_OVER
) -> tuple[Decimal, list[date]]:
    """Average monthly spending no recurring item paid, over the last complete months, in cash
    terms: card purchases are left out because the card payments (recurring items) carry them."""
    current = recurring.first(today)
    months = [recurring.add_months(current, -i) for i in range(over, 0, -1)]
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


def _recurring_events(
    db: Session,
    month: date,
    days: dict[int, int],
    due: dict[int, dict[date, Decimal]] | None = None,
) -> list[Event]:
    due = due or {}
    salaries = payday.salary_categories(db)
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
        if t.template_id in due:  # a loan with a table: its installment, none after payoff
            if month not in due[t.template_id]:
                continue
            amount = -due[t.template_id][month]
        kind = "income" if t.type in INCOME else "fixed"
        day = t.due_day or days.get(t.template_id, 1)
        if t.category_id in salaries and amount > 0 and day >= payday.NEXT_FROM_DAY:
            # This month's salary arrived last month, on its usual day (ADR-084).
            when = _on(recurring.add_months(month, -1), day)
            out.append(Event(when, t.name, amount, kind, t.account_id, month))
            continue
        out.append(Event(_on(month, day), t.name, amount, kind, t.account_id))
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
        last = (
            db.execute(
                select(Transaction.txn_date, Transaction.account_id)
                .where(Transaction.category_id == item.category_id)
                .order_by(Transaction.txn_date.desc())
                .limit(1)
            ).first()
            if item.category_id
            else None
        )
        day = last[0].day if last else 1
        account_id = last[1] if last else None
        left = p.installments_left
        for m in months:
            if left <= 0:
                break
            when = _on(m, day)
            if when < today:
                continue
            out.append(
                Event(when, f"{item.name} installment", -p.installment, "purchase", account_id)
            )
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


def _change_events(changes: list[Change], today: date, end: date) -> list[Event]:
    out = []
    for c in changes:
        if c.every == "once":
            if c.on is not None and today <= c.on <= end:
                out.append(Event(c.on, c.name, c.amount, "change", c.account_id))
            continue
        m = recurring.first(today)
        while m <= end:
            when = _on(m, c.day)
            if today <= when <= end:
                out.append(Event(when, c.name, c.amount, "change", c.account_id))
            m = recurring.add_months(m, 1)
    return out


def project(
    db: Session,
    today: date | None = None,
    *,
    horizon: int = MONTHS_AHEAD,
    average_over: int = AVERAGE_OVER,
    floor: Decimal = ZERO,
    include_held: bool = False,
    changes: list[Change] | None = None,
) -> Projection:
    """The next `horizon` months (ADR-013, ADR-033): every day's cash in total and in each bank
    account, with what-if changes added on top."""
    today = today or date.today()
    current = recurring.first(today)
    months = [recurring.add_months(current, i) for i in range(1, horizon + 1)]
    end = recurring.add_months(months[-1], 1) - timedelta(days=1)

    cash_items = [
        i for i in networth.accounts(db, today) if i.holding_class == "cash" and i.is_active
    ]
    start_cash = sum((i.value or ZERO for i in cash_items), ZERO)
    cash_as_of = min((i.as_of for i in cash_items if i.as_of), default=None)
    # Money held for a person sits in the bank accounts but isn't yours to spend.
    linked = people.linked_holdings(db)
    held = sum(
        (
            i.value or ZERO
            for i in networth.holdings(db, today)
            if i.is_active and i.holding_id in linked and i.side == "liability"
        ),
        ZERO,
    )
    if not include_held:
        start_cash -= held

    variable, avg_months = variable_average(db, today, average_over)
    days = _usual_days(db)
    paid_categories = {t.category_id for t in db.scalars(select(RecurringTemplate))}

    # Events from today to the end of the third month: what is left of this month, then the
    # three months.
    due = loans.due_by_month(db)
    events = [e for e in _recurring_events(db, current, days, due) if e.day >= today]
    for m in months:
        events += _recurring_events(db, m, days, due)
    # The salary of the month after the last one arrives inside it (ADR-084): cash, not plan.
    after = recurring.add_months(months[-1], 1) if months else None
    if after is not None:
        events += [e for e in _recurring_events(db, after, days, due) if e.month is not None]
    events += _purchase_events(db, today, [current, *months], paid_categories)
    events += _change_events(changes or [], today, end)
    # The income tax each person is projected to pay with the return (ADR-088).
    events += [
        Event(day, name, -amount, "fixed")
        for day, name, amount in tax_projection.payments(db, today, end)
    ]

    plans = {m: MonthPlan(m) for m in months}
    for e in events:
        plan = plans.get(e.month or recurring.first(e.day))
        if plan is None:
            continue
        plan.items.append(e)
        if e.kind == "income" or (e.kind == "change" and e.amount > 0):
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
    first_short = next((d for d, b in daily if b < floor), None)

    # Each bank account: its own items only.
    runs = []
    for item in cash_items:
        if item.account_id is None:
            continue
        mine: dict[date, Decimal] = defaultdict(Decimal)
        for e in events:
            if e.account_id == item.account_id:
                mine[e.day] += e.amount
        if not mine:
            continue
        bal = item.value or ZERO
        run = []
        d = today
        while d <= end:
            bal += mine.get(d, ZERO)
            run.append((d, bal.quantize(CENT)))
            d += timedelta(days=1)
        low = min(run, key=lambda x: (x[1], x[0]))
        under = next((d for d, b in run if b < floor), None)
        runs.append(
            AccountRun(
                item.account_id,
                item.name,
                (item.value or ZERO).quantize(CENT),
                item.as_of,
                run,
                low,
                under,
                max(ZERO, floor - low[1]).quantize(CENT) if under else ZERO,
            )
        )
    runs.sort(key=lambda r: (r.under_floor is None, r.lowest[1]))
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
        horizon=horizon,
        average_over=average_over,
        floor=floor,
        held=held.quantize(CENT),
        include_held=include_held,
        accounts=runs,
        first_short=first_short,
        end_cash=daily[-1][1] if daily else start_cash,
    )
