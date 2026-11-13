"""Debt payoff order, compared (ADR-097, plan item C5).

Every month each debt grows by a twelfth of its yearly rate and gets its minimum payment. What
is left of the monthly budget (the extra, plus the minimums of debts already paid off) goes to
one debt at a time:
- "avalanche": the highest rate first, which costs the least interest;
- "snowball": the smallest balance first, which closes debts soonest.
"Minimums only" pays each debt its minimum until it is done and rolls nothing over: what happens
without a plan.

A calculation from the numbers given, not a recommendation. Pure functions, Decimal throughout.
"""

from dataclasses import dataclass, field
from decimal import Decimal

# Assumptions (ADR-097).
MAX_MONTHS = 600  # fifty years: a debt that isn't gone by then isn't being paid off
MONTHS_IN_YEAR = 12
STRATEGIES = ("avalanche", "snowball")

ZERO = Decimal(0)
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Debt:
    key: str
    name: str
    balance: Decimal
    rate: Decimal  # a year, as a fraction: 0.1560 is 15.60%
    minimum: Decimal  # paid every month


@dataclass
class Plan:
    months: int | None  # until every debt is paid; None when the payments never get there
    interest: Decimal  # paid along the way (through MAX_MONTHS when it never ends)
    order: list[str] = field(default_factory=list)  # debts in the order they are paid off
    paid_in: dict[str, int] = field(default_factory=dict)  # debt -> the month it is paid off


def priority(debts: list[Debt], strategy: str) -> list[Debt]:
    """The order the spare money goes in."""
    if strategy == "avalanche":
        return sorted(debts, key=lambda d: (-d.rate, d.balance, d.name))
    if strategy == "snowball":
        return sorted(debts, key=lambda d: (d.balance, -d.rate, d.name))
    raise ValueError(f"Unknown strategy: {strategy}")


def simulate(debts: list[Debt], extra: Decimal = ZERO, strategy: str | None = None) -> Plan:
    """Month by month until every debt is paid. Without a strategy: minimums only, nothing
    rolled over."""
    owed = {d.key: d.balance for d in debts if d.balance > 0}
    live = [d for d in debts if d.key in owed]
    order = priority(live, strategy) if strategy else []
    budget = extra + sum((d.minimum for d in live), ZERO)
    plan = Plan(0, ZERO)
    for month in range(1, MAX_MONTHS + 1):
        if not owed:
            break
        spare = budget
        for d in live:
            if d.key not in owed:
                continue
            charged = (owed[d.key] * d.rate / MONTHS_IN_YEAR).quantize(CENT)
            plan.interest += charged
            paying = min(d.minimum, owed[d.key] + charged)
            owed[d.key] += charged - paying
            spare -= paying
        for d in order:
            if d.key in owed and spare > 0:
                paying = min(spare, owed[d.key])
                owed[d.key] -= paying
                spare -= paying
        for d in live:
            if d.key in owed and owed[d.key] <= 0:
                del owed[d.key]
                plan.order.append(d.key)
                plan.paid_in[d.key] = month
        plan.months = month
    if owed:
        plan.months = None
    return plan


@dataclass
class Comparison:
    minimums: Plan
    avalanche: Plan
    snowball: Plan

    @property
    def saved(self) -> Decimal:
        """Interest the cheaper order saves over the other one."""
        return abs(self.avalanche.interest - self.snowball.interest)


def compare(debts: list[Debt], extra: Decimal) -> Comparison:
    return Comparison(
        simulate(debts),
        simulate(debts, extra, "avalanche"),
        simulate(debts, extra, "snowball"),
    )
