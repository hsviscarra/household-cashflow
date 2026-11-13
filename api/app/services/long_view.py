"""Five to ten years ahead (ADR-098, plan item C4): net worth by year.

Year by year, in today's money:
- what you keep a year (money in less spent, as in the last twelve months) pays the loans first
  and the rest stays as cash or goes to investments, by the share you choose;
- investments grow at a yearly return: three lines, for a low, an expected and a high return;
- a loan with an amortization table follows it (its balance at each year's end, and the interest
  the year costs); a loan without one goes down by its payments and no interest is counted;
- property and vehicles change by the yearly rates you choose; cards and other debts stay as
  they are (the monthly forecast is where cards live).

It is arithmetic on the assumptions shown, not a prediction, and it recommends nothing.
The functions here are pure; `services/outlook.py` reads the household's numbers and calls
them.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# Assumptions (ADR-098): defaults, all of them choices on the page.
YEARS = (5, 10)
RATE_RANGE = (Decimal("-0.5"), Decimal("0.5"))  # a yearly rate the page accepts: -50% to 50%
DEFAULT_RETURNS = (Decimal("0.02"), Decimal("0.05"), Decimal("0.08"))  # low, expected, high
DEFAULT_PROPERTY = Decimal(0)  # a year: houses hold their value in today's money
DEFAULT_VEHICLE = Decimal("-0.10")  # a year: a car loses a tenth
DEFAULT_INVEST_SHARE = Decimal(0)  # of what is kept after the loans, invested
CASES = ("low", "expected", "high")

ZERO = Decimal(0)
CENT = Decimal("0.01")
ONE = Decimal(1)
MONTHS_IN_YEAR = 12


@dataclass(frozen=True)
class Assumptions:
    """The choices a projection is made with; every one is on the page."""

    years: int = 5
    returns: tuple[Decimal, Decimal, Decimal] = DEFAULT_RETURNS
    property_growth: Decimal = DEFAULT_PROPERTY
    vehicle_growth: Decimal = DEFAULT_VEHICLE
    invest_share: Decimal = DEFAULT_INVEST_SHARE


@dataclass(frozen=True)
class LoanPath:
    """A loan year by year. With a table: `balances[i]` and `interest[i]` are the balance at the
    end of year i and the interest paid in it (i = 0 is the rest of this year). Without one,
    only the balance today and what is paid a year are known."""

    name: str
    balance: Decimal
    balances: tuple[Decimal, ...] = ()
    interest: tuple[Decimal, ...] = ()
    yearly_payment: Decimal = ZERO
    paid_off: date | None = None  # from the table


@dataclass(frozen=True)
class Start:
    """What there is today, and what a year adds."""

    cash: Decimal
    investments: Decimal
    property: Decimal
    vehicles: Decimal
    other_assets: Decimal  # purchases in progress and anything else owned
    other_debts: Decimal  # cards, personal loans: kept as they are
    kept_a_year: Decimal  # money in less spent, over the last twelve months
    loans: tuple[LoanPath, ...] = ()


@dataclass
class Year:
    """Where things stand at the end of one year, by kind of asset and debt."""

    year: int
    end: date
    cash: Decimal
    investments: dict[str, Decimal]  # by case
    property: Decimal
    vehicles: Decimal
    other_assets: Decimal
    loans: Decimal
    other_debts: Decimal
    kept: Decimal  # what the year adds, after the loans' interest
    milestones: list[str] = field(default_factory=list)

    def net(self, case: str) -> Decimal:
        owned = (
            self.cash + self.investments[case] + self.property + self.vehicles + self.other_assets
        )
        return owned - self.loans - self.other_debts


def loan_balances(loan: LoanPath, first_months: int, years: int) -> list[tuple[Decimal, Decimal]]:
    """A loan's (balance, interest paid) at the end of each of `years` years, the first one
    holding `first_months` months. After its table ends the loan is paid."""
    if loan.balances:
        return [
            (loan.balances[i], loan.interest[i]) if i < len(loan.balances) else (ZERO, ZERO)
            for i in range(years)
        ]
    out: list[tuple[Decimal, Decimal]] = []
    balance = loan.balance
    for i in range(years):
        months = first_months if i == 0 else MONTHS_IN_YEAR
        balance = max(ZERO, balance - loan.yearly_payment * months / MONTHS_IN_YEAR)
        out.append((balance, ZERO))
    return out


def project(start: Start, a: Assumptions, today: date) -> list[Year]:
    """Net worth at the end of this year and of each of the `a.years` after it."""
    first_months = MONTHS_IN_YEAR - today.month  # whole months left this year
    count = a.years + 1
    paths = [loan_balances(loan, first_months, count) for loan in start.loans]
    cash = start.cash
    invested = dict(zip(CASES, [start.investments] * 3, strict=True))
    prop, cars = start.property, start.vehicles
    owed_before = sum((loan.balance for loan in start.loans), ZERO)
    out = []
    for i in range(count):
        part = Decimal(first_months if i == 0 else MONTHS_IN_YEAR) / MONTHS_IN_YEAR
        owed = sum((p[i][0] for p in paths), ZERO)
        interest = sum((p[i][1] for p in paths), ZERO)
        kept = start.kept_a_year * part - interest
        # What is kept pays the loans down first; the rest is free to stay or be invested.
        free = kept - (owed_before - owed)
        to_invest = max(ZERO, free) * a.invest_share
        cash += free - to_invest
        for case, rate in zip(CASES, a.returns, strict=True):
            invested[case] = invested[case] * (ONE + rate * part) + to_invest
        prop *= ONE + a.property_growth * part
        cars *= ONE + a.vehicle_growth * part
        out.append(
            Year(
                today.year + i,
                date(today.year + i, 12, 31),
                cash.quantize(CENT),
                {c: v.quantize(CENT) for c, v in invested.items()},
                prop.quantize(CENT),
                cars.quantize(CENT),
                start.other_assets,
                owed.quantize(CENT),
                start.other_debts,
                kept.quantize(CENT),
            )
        )
        owed_before = owed
    return out


def place(years: list[Year], milestones: list[tuple[date, str]]) -> None:
    """Put each milestone in its year (those outside the years shown are left out)."""
    by_year = {y.year: y for y in years}
    for when, name in sorted(milestones):
        if when.year in by_year:
            by_year[when.year].milestones.append(name)
