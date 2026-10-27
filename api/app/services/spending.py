"""Spending analytics (F13, ADR-010): one month's spending, read from mart.v_spending_line.

Spending is expenses plus fees and interest, less refunds (the Overview's spending view).
Every figure comes with last month (MoM) and the same month a year before (YoY).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import v_spending_line as v
from app.services import classify
from app.services.recurring import add_months, first

TOP_MERCHANTS = 10
TREND_MONTHS = 12
ZERO = Decimal(0)


@dataclass
class Compare:
    amount: Decimal = ZERO
    prev: Decimal = ZERO  # last month
    last_year: Decimal = ZERO  # same month a year before
    transactions: int = 0


@dataclass
class CategoryRow(Compare):
    category_id: int = 0
    name: str = ""


@dataclass
class GroupRow(Compare):
    group_id: int = 0
    name: str = ""
    color: str | None = None
    categories: list[CategoryRow] = field(default_factory=list)


@dataclass
class Slice:
    key: str
    amount: Decimal
    transactions: int


@dataclass
class Merchant:
    merchant: str
    group_name: str
    amount: Decimal
    transactions: int


@dataclass
class Spending:
    month: date
    months: list[date]  # every month with spending, newest first
    source: str  # excel, statements or none
    total: Compare
    groups: list[GroupRow]
    by_person: list[Slice]
    by_country: list[Slice]
    fixed: list[Slice]
    merchants: list[Merchant]
    trend: list[tuple[date, Decimal]]


def months(db: Session) -> list[date]:
    return list(db.scalars(select(v.c.cash_month).distinct().order_by(v.c.cash_month.desc())))


def _by_category(db: Session, month: date) -> dict[tuple[int, int], tuple[Decimal, int]]:
    q = (
        select(v.c.group_id, v.c.category_id, func.sum(v.c.amount), func.count())
        .where(v.c.cash_month == month)
        .group_by(v.c.group_id, v.c.category_id)
    )
    return {(int(g), int(c)): (Decimal(str(t)), int(n)) for g, c, t, n in db.execute(q)}


def _slices(db: Session, month: date, column: str) -> list[Slice]:
    col = v.c[column]
    q = select(col, func.sum(v.c.amount), func.count()).where(v.c.cash_month == month).group_by(col)
    out = [
        Slice(_label(column, key), Decimal(str(total)), int(n)) for key, total, n in db.execute(q)
    ]
    return sorted(out, key=lambda s: (-s.amount, s.key))


def _label(column: str, key: object) -> str:
    if column == "is_fixed":
        return "fixed" if key else "variable"
    return str(key) if key else "Unknown"


def analyze(db: Session, month: date | None = None) -> Spending:
    available = months(db)
    month = first(month) if month else (available[0] if available else first(date.today()))
    prev_month, year_ago = add_months(month, -1), add_months(month, -12)
    now, prev, ago = (_by_category(db, m) for m in (month, prev_month, year_ago))

    names = {
        (r.group_id, r.category_id): r
        for r in db.execute(
            select(
                v.c.group_id, v.c.group_name, v.c.group_color, v.c.category_id, v.c.category_name
            )
            .where(v.c.cash_month.in_([month, prev_month, year_ago]))
            .distinct()
        )
    }
    groups: dict[int, GroupRow] = {}
    for key in set(now) | set(prev) | set(ago):
        info = names[key]
        g = groups.setdefault(
            key[0], GroupRow(group_id=key[0], name=info.group_name, color=info.group_color)
        )
        amount, n = now.get(key, (ZERO, 0))
        c = CategoryRow(
            category_id=key[1],
            name=info.category_name,
            amount=amount,
            prev=prev.get(key, (ZERO, 0))[0],
            last_year=ago.get(key, (ZERO, 0))[0],
            transactions=n,
        )
        g.categories.append(c)
        g.amount += c.amount
        g.prev += c.prev
        g.last_year += c.last_year
        g.transactions += c.transactions
    for g in groups.values():
        g.categories.sort(key=lambda c: (-c.amount, c.name))
    ordered = sorted(groups.values(), key=lambda g: (-g.amount, g.name))

    total = Compare(
        amount=sum((g.amount for g in ordered), ZERO),
        prev=sum((g.prev for g in ordered), ZERO),
        last_year=sum((g.last_year for g in ordered), ZERO),
        transactions=sum(g.transactions for g in ordered),
    )
    sources = set(db.scalars(select(v.c.source).where(v.c.cash_month == month).distinct()))
    source = "excel" if "excel_history" in sources else "statements" if sources else "none"
    return Spending(
        month=month,
        months=available,
        source=source,
        total=total,
        groups=ordered,
        by_person=_slices(db, month, "person"),
        by_country=_slices(db, month, "country"),
        fixed=_slices(db, month, "is_fixed"),
        merchants=top_merchants(db, month) if source == "statements" else [],
        trend=trend(db, month),
    )


def top_merchants(db: Session, month: date, limit: int = TOP_MERCHANTS) -> list[Merchant]:
    """The biggest merchants of a statement month, grouped like the review queue (reference
    numbers and confirmation codes dropped, F9); refunds reduce them."""
    q = (
        select(v.c.merchant, v.c.group_name, func.sum(v.c.amount), func.count())
        .where(v.c.cash_month == month, v.c.source != "excel_history")
        .group_by(v.c.merchant, v.c.group_name)
    )
    found: dict[str, Merchant] = {}
    for merchant, group_name, total, n in db.execute(q):
        key = classify.merchant_key(str(merchant)) or str(merchant)
        m = found.get(key)
        if m is None:
            found[key] = Merchant(key, group_name, Decimal(str(total)), int(n))
        else:
            m.amount += Decimal(str(total))
            m.transactions += int(n)
    ranked = sorted(found.values(), key=lambda m: (-m.amount, m.merchant))
    return [m for m in ranked if m.amount > 0][:limit]


def trend(db: Session, month: date, count: int = TREND_MONTHS) -> list[tuple[date, Decimal]]:
    start = add_months(month, -(count - 1))
    totals: dict[date, Decimal] = defaultdict(Decimal)
    for m, total in db.execute(
        select(v.c.cash_month, func.sum(v.c.amount))
        .where(v.c.cash_month >= start, v.c.cash_month <= month)
        .group_by(v.c.cash_month)
    ):
        totals[m] = Decimal(str(total))
    return [(add_months(start, i), totals[add_months(start, i)]) for i in range(count)]


@dataclass
class Line:
    transaction_id: int
    txn_date: date
    merchant: str
    description: str
    amount: Decimal
    category_name: str
    group_name: str
    person: str
    account_name: str | None
    source: str


def lines(
    db: Session,
    month: date,
    *,
    group_id: int | None = None,
    category_id: int | None = None,
    merchant: str | None = None,
    person: str | None = None,
    country: str | None = None,
    fixed: bool | None = None,
) -> list[Line]:
    """The lines behind one number of the page, biggest first."""
    q = select(v).where(v.c.cash_month == first(month))
    if group_id is not None:
        q = q.where(v.c.group_id == group_id)
    if category_id is not None:
        q = q.where(v.c.category_id == category_id)
    if person is not None:
        q = q.where(v.c.person == person)
    if country is not None:
        q = q.where(v.c.country == country)
    if fixed is not None:
        q = q.where(v.c.is_fixed == fixed)
    rows = [
        r
        for r in db.execute(q.order_by(v.c.amount.desc(), v.c.transaction_id))
        if merchant is None
        or (classify.merchant_key(str(r.merchant)) or str(r.merchant)) == merchant
    ]
    return [
        Line(
            r.transaction_id,
            r.txn_date,
            r.merchant,
            r.description,
            Decimal(str(r.amount)),
            r.category_name,
            r.group_name,
            r.person,
            r.account_name,
            r.source,
        )
        for r in rows
    ]
