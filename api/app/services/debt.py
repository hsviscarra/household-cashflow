"""Cost of debt (F14, ADR-011): interest and fees per account, year to date and by month, read
from mart.v_debt_cost, with each card's latest statement balance."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account
from app.models import v_debt_cost as v
from app.services import status
from app.services.recurring import add_months, first

ZERO = Decimal(0)
SHEET = "Cash Flow sheet"


@dataclass
class AccountCost:
    account_id: int | None
    name: str
    kind: str | None
    interest: Decimal = ZERO  # year to date
    fees: Decimal = ZERO
    last_12: Decimal = ZERO
    by_category: dict[str, Decimal] = field(default_factory=dict)
    by_month: dict[date, Decimal] = field(default_factory=dict)  # the last 12 months
    balance: Decimal | None = None  # latest statement closing balance, as printed
    balance_date: date | None = None

    @property
    def total(self) -> Decimal:
        return self.interest + self.fees


@dataclass
class DebtCost:
    year: int
    through: date
    months: list[date]
    accounts: list[AccountCost]
    years: list[int]

    @property
    def interest(self) -> Decimal:
        return sum((a.interest for a in self.accounts), ZERO)

    @property
    def fees(self) -> Decimal:
        return sum((a.fees for a in self.accounts), ZERO)


def years(db: Session) -> list[int]:
    found = {m.year for m in db.scalars(select(v.c.cash_month).distinct())}
    return sorted(found, reverse=True)


def cost(db: Session, year: int | None = None, today: date | None = None) -> DebtCost:
    today = today or date.today()
    available = years(db)
    year = year or (available[0] if available else today.year)
    latest = db.scalar(
        select(func.max(v.c.cash_month)).where(
            v.c.cash_month >= date(year, 1, 1), v.c.cash_month <= date(year, 12, 1)
        )
    )
    through = latest or (first(today) if year == today.year else date(year, 12, 1))
    months = [add_months(through, -i) for i in range(11, -1, -1)]

    accounts: dict[int | None, AccountCost] = {}

    def row(account_id: int | None, name: str | None, kind: str | None) -> AccountCost:
        if account_id not in accounts:
            accounts[account_id] = AccountCost(account_id, name or SHEET, kind)
        return accounts[account_id]

    q = select(v).where(
        v.c.cash_month >= min(months[0], date(year, 1, 1)), v.c.cash_month <= through
    )
    for r in db.execute(q):
        a = row(r.account_id, r.account_name, r.account_kind)
        amount = Decimal(str(r.amount))
        if r.cash_month.year == year:
            if r.kind == "interest":
                a.interest += amount
            else:
                a.fees += amount
            a.by_category[r.category_name] = a.by_category.get(r.category_name, ZERO) + amount
        if r.cash_month >= months[0]:
            a.last_12 += amount
            a.by_month[r.cash_month] = a.by_month.get(r.cash_month, ZERO) + amount

    # Each card's latest statement balance (cards only: a bank balance isn't a debt).
    cards = {a.account_id for a in db.scalars(select(Account).where(Account.kind == "credit_card"))}
    last: dict[int, tuple[date, Decimal | None]] = {}
    for s in status.approved_statements(db):
        if s.account_id in cards and (s.account_id not in last or s.end >= last[s.account_id][0]):
            last[s.account_id] = (s.end, s.closing)
    names = {a.account_id: a for a in db.scalars(select(Account))}
    for account_id, (end, closing) in last.items():
        acct = names[account_id]
        a = row(account_id, acct.name, acct.kind)
        a.balance, a.balance_date = closing, end

    ordered = sorted(accounts.values(), key=lambda a: (-a.total, -a.last_12, a.name))
    return DebtCost(year, through, months, ordered, available or [year])


def by_month_totals(d: DebtCost) -> dict[date, Decimal]:
    out: dict[date, Decimal] = defaultdict(Decimal)
    for a in d.accounts:
        for m, amount in a.by_month.items():
            out[m] += amount
    return out
