"""Five to ten years ahead, from the household's own numbers (ADR-098): reads the balance
sheet, the loans' tables, what was kept in the last twelve months and the goals' dates, and
hands them to `long_view`."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services import goals, loans, long_view, networth, savings

ZERO = Decimal(0)
LOAN_CLASSES = ("loan", "personal_loan")


def _loan_path(db: Session, item: networth.Item, today: date, years: int) -> long_view.LoanPath:
    balance = item.value or ZERO
    rows = loans.installments(db, item.holding_id) if item.holding_id is not None else []
    due = [r for r in rows if r.status == "due"]
    if not due:
        payment = item.loan.monthly_payment if item.loan and item.loan.monthly_payment else ZERO
        return long_view.LoanPath(
            item.name, balance, yearly_payment=payment * long_view.MONTHS_IN_YEAR
        )
    balances, interest = [], []
    last = balance
    for i in range(years):
        year = today.year + i
        in_year = [r for r in due if r.period.year == year]
        through = [r for r in due if r.period.year <= year]
        last = through[-1].balance_after if through else last
        balances.append(last)
        interest.append(sum((r.interest for r in in_year), ZERO))
    return long_view.LoanPath(
        item.name, balance, tuple(balances), tuple(interest), paid_off=due[-1].period
    )


def kept_a_year(db: Session, today: date) -> Decimal:
    """What a year keeps at the pace of the last complete months (money in less spent)."""
    whole = [m for m in savings.rate_months(db, today) if not m.running and m.money_in > 0]
    if not whole:
        return ZERO
    return sum((m.kept for m in whole), ZERO) / len(whole) * long_view.MONTHS_IN_YEAR


def start(db: Session, today: date, years: int) -> long_view.Start:
    by_class: dict[str, Decimal] = {}
    paths = []
    other_assets = other_debts = ZERO
    for item in networth.accounts(db, today) + networth.holdings(db, today):
        if not item.is_active or not item.value:
            continue
        if item.side == "liability":
            if item.holding_class in LOAN_CLASSES:
                paths.append(_loan_path(db, item, today, years))
            else:
                other_debts += item.value
        elif item.holding_class in ("cash", "investment", "property", "vehicle"):
            by_class[item.holding_class] = by_class.get(item.holding_class, ZERO) + item.value
        else:
            other_assets += item.value
    return long_view.Start(
        by_class.get("cash", ZERO),
        by_class.get("investment", ZERO),
        by_class.get("property", ZERO),
        by_class.get("vehicle", ZERO),
        other_assets,
        other_debts,
        kept_a_year(db, today),
        tuple(paths),
    )


def milestones(db: Session, s: long_view.Start, today: date) -> list[tuple[date, str]]:
    """Dates the app already knows: each loan's last installment and each goal's date."""
    out = [(loan.paid_off, f"{loan.name} paid off") for loan in s.loans if loan.paid_off]
    out += [
        (g.target_date, f"Goal: {g.name}")
        for g in goals.all_goals(db, today)
        if g.is_active and g.target_date and g.status != "reached"
    ]
    return out


def ahead(
    db: Session, today: date, a: long_view.Assumptions
) -> tuple[long_view.Start, list[long_view.Year]]:
    s = start(db, today, a.years + 1)
    years = long_view.project(s, a, today)
    long_view.place(years, milestones(db, s, today))
    return s, years
