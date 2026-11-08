"""Where's the money (ADR-051): what the cash flow says was kept over some months, against what
the bank and card balances actually did, and what usually explains the difference.

Kept = money in - money out (counted lines, card purchases when made). If every line is classified
right and every account is loaded, kept equals the change in cash minus the change in what's owed
on cards, plus whatever went to places the app doesn't follow (an investment account, cash). The
gap is where to look."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FROM_BANKS, Account, Category, Transaction
from app.services import cashflow, networth, status, transfers
from app.services.recurring import add_months, first

ZERO = Decimal(0)


@dataclass
class AccountChange:
    account_id: int
    name: str
    kind: str  # "cash" | "card"
    start: Decimal | None
    start_on: date | None
    end: Decimal | None
    end_on: date | None
    change: Decimal | None  # what it adds to the money you have (cards: less owed is positive)


@dataclass
class Cause:
    key: str
    title: str
    detail: str
    amount: Decimal
    link: str


@dataclass
class Reconcile:
    start: date  # first month
    end: date  # last month
    money_in: Decimal
    money_out: Decimal
    kept: Decimal
    balances_change: Decimal
    gap: Decimal
    accounts: list[AccountChange]
    causes: list[Cause] = field(default_factory=list)
    workbook_months: int = 0


def _value(items: list[networth.Item], account_id: int) -> networth.Item | None:
    return next((i for i in items if i.account_id == account_id), None)


def build(db: Session, start: date, end: date) -> Reconcile:
    start, end = first(start), first(end)
    last_day = add_months(end, 1) - timedelta(days=1)
    before = start - timedelta(days=1)
    t = Transaction

    totals = [
        m for m in cashflow.trend(db, end, None, count=_months(start, end)) if m.month >= start
    ]
    money_in = sum((m.money_in for m in totals), ZERO)
    money_out = sum((m.money_out for m in totals), ZERO)
    kept = money_in - money_out

    at_start, at_end = networth.accounts(db, before), networth.accounts(db, last_day)
    changes: list[AccountChange] = []
    for a in db.scalars(select(Account).where(Account.is_active).order_by(Account.name)):
        s, e = _value(at_start, a.account_id), _value(at_end, a.account_id)
        if s is None and e is None:
            continue
        card = a.kind == "credit_card"
        sv, ev = (s.value if s else None), (e.value if e else None)
        change = None
        if sv is not None and ev is not None:
            change = (sv - ev) if card else (ev - sv)  # less owed on a card is money kept
        changes.append(
            AccountChange(
                a.account_id,
                a.name,
                "card" if card else "cash",
                sv,
                s.as_of if s else None,
                ev,
                e.as_of if e else None,
                change,
            )
        )
    balances = sum((c.change for c in changes if c.change is not None), ZERO)

    causes: list[Cause] = []
    missing = [c.name for c in changes if c.change is None]
    if missing:
        causes.append(
            Cause(
                "accounts",
                "Balances missing for part of the period",
                ", ".join(missing) + ": no statement at the start or the end, so its change "
                "isn't counted.",
                ZERO,
                "/todo#books",
            )
        )
    stale = [
        c.name for c in changes if c.end_on is not None and c.end_on < last_day - timedelta(days=40)
    ]
    if stale:
        causes.append(
            Cause(
                "stale",
                "Statements missing at the end",
                ", ".join(stale) + ": the latest statement is well before the end of the period.",
                ZERO,
                "/todo#books",
            )
        )
    open_transfers = [x for x in transfers.unmatched(db) if start <= x.cash_month <= end]
    if open_transfers:
        causes.append(
            Cause(
                "transfers",
                "Transfers with only one side loaded",
                f"{len(open_transfers)} lines: money that left one account and the other side "
                "isn't here, or the other way round.",
                sum((x.amount for x in open_transfers), ZERO),
                "/todo#transfers",
            )
        )
    period = (t.cash_month >= start, t.cash_month <= end, t.source.in_(FROM_BANKS))
    people = db.scalar(
        select(func.coalesce(func.sum(t.amount), 0)).where(
            *period, t.type == "transfer", t.counterparty_id.is_not(None)
        )
    )
    if people:
        causes.append(
            Cause(
                "people",
                "Money with people",
                "Transfers to or from people (money held for them, loans, reimbursements) move "
                "your balances but aren't income or spending.",
                Decimal(str(people)),
                "/people",
            )
        )
    income_cats = select(Category.category_id).where(Category.kind == "income")
    looks_transfer = db.scalar(
        select(func.coalesce(func.sum(t.amount), 0)).where(
            *period,
            t.type == "income",
            t.category_id.in_(income_cats),
            t.description_raw.ilike("%transfer%"),
            t.counterparty_id.is_(None),
        )
    )
    if looks_transfer:
        causes.append(
            Cause(
                "income_transfers",
                "Income that came by transfer",
                "Check these are really income (salary, a client) and not money moved from your "
                "own account or someone else's money.",
                Decimal(str(looks_transfer)),
                "/cashflow",
            )
        )
    uncategorized = db.scalar(
        select(func.coalesce(func.sum(t.amount), 0)).where(*period, t.category_id.is_(None))
    )
    if uncategorized:
        causes.append(
            Cause(
                "uncategorized",
                "Lines without a category",
                "Counted as money out until they get one.",
                Decimal(str(uncategorized)),
                "/todo#categorize",
            )
        )
    months = status.month_status(db, with_loads=False).months
    workbook = sum(1 for m in months if start <= m.month <= end and m.source == "excel")
    gap = kept - balances
    return Reconcile(
        start, end, money_in, money_out, kept, balances, gap, changes, causes, workbook
    )


def _months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1
