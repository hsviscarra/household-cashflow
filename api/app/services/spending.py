"""Spending analytics (F13, ADR-010): one month's spending, read from mart.v_spending_line.

Spending is expenses plus fees and interest, less refunds (the Overview's spending view).
Every figure comes with last month (MoM) and the same month a year before (YoY).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import v_spending_line as v
from app.services import classify
from app.services.recurring import add_months, first

TOP_MERCHANTS = 10
TREND_MONTHS = 12
MAX_SERIES_MONTHS = 36  # the longest period the chart with controls can ask for
ZERO = Decimal(0)


@dataclass
class Compare:
    """An amount with the month before and the same month last year."""

    amount: Decimal = ZERO
    prev: Decimal = ZERO  # last month
    last_year: Decimal = ZERO  # same month a year before
    transactions: int = 0


@dataclass
class CategoryRow(Compare):
    """A category's spending."""

    category_id: int = 0
    name: str = ""


@dataclass
class GroupRow(Compare):
    """A group's spending, with its categories."""

    group_id: int = 0
    name: str = ""
    color: str | None = None
    categories: list[CategoryRow] = field(default_factory=list)


@dataclass
class Slice:
    """A share of the month's spending, by person or by country."""

    key: str
    amount: Decimal
    transactions: int


@dataclass
class Merchant:
    """A merchant's spending in the month."""

    merchant: str
    group_name: str
    amount: Decimal
    transactions: int


@dataclass
class Spending:
    """A month's spending as the page shows it."""

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
    """The months that have spending, newest first."""
    return list(db.scalars(select(v.c.cash_month).distinct().order_by(v.c.cash_month.desc())))


def _who(q: Select[Any], person: str | None) -> Select[Any]:
    """Only one person's lines (the Both/Hernan/Lauren switch, ADR-026); None keeps everyone."""
    return q if person is None else q.where(v.c.person == person)


def _by_category(
    db: Session, month: date, person: str | None = None
) -> dict[tuple[int, int], tuple[Decimal, int]]:
    q = (
        select(v.c.group_id, v.c.category_id, func.sum(v.c.amount), func.count())
        .where(v.c.cash_month == month)
        .group_by(v.c.group_id, v.c.category_id)
    )
    return {
        (int(g), int(c)): (Decimal(str(t)), int(n)) for g, c, t, n in db.execute(_who(q, person))
    }


def _slices(db: Session, month: date, column: str, person: str | None = None) -> list[Slice]:
    col = v.c[column]
    q = select(col, func.sum(v.c.amount), func.count()).where(v.c.cash_month == month).group_by(col)
    q = _who(q, person)
    out = [
        Slice(_label(column, key), Decimal(str(total)), int(n)) for key, total, n in db.execute(q)
    ]
    return sorted(out, key=lambda s: (-s.amount, s.key))


def _label(column: str, key: object) -> str:
    if column == "is_fixed":
        return "fixed" if key else "variable"
    return str(key) if key else "Unknown"


def analyze(db: Session, month: date | None = None, person: str | None = None) -> Spending:
    """A month's spending: totals against the month and the year before, groups and categories,
    who, where, fixed or variable, merchants and the trend."""
    available = months(db)
    month = first(month) if month else (available[0] if available else first(date.today()))
    prev_month, year_ago = add_months(month, -1), add_months(month, -12)
    now, prev, ago = (_by_category(db, m, person) for m in (month, prev_month, year_ago))

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
    sources = set(
        db.scalars(_who(select(v.c.source).where(v.c.cash_month == month).distinct(), person))
    )
    source = "excel" if "excel_history" in sources else "statements" if sources else "none"
    return Spending(
        month=month,
        months=available,
        source=source,
        total=total,
        groups=ordered,
        by_person=_slices(db, month, "person", person),
        by_country=_slices(db, month, "country", person),
        fixed=_slices(db, month, "is_fixed", person),
        merchants=top_merchants(db, month, person=person) if source == "statements" else [],
        trend=trend(db, month, person=person),
    )


def top_merchants(
    db: Session, month: date, limit: int = TOP_MERCHANTS, person: str | None = None
) -> list[Merchant]:
    """The biggest merchants of a statement month, grouped like the review queue (reference
    numbers and confirmation codes dropped, F9); refunds reduce them."""
    q = (
        select(v.c.merchant, v.c.group_name, func.sum(v.c.amount), func.count())
        .where(v.c.cash_month == month, v.c.source != "excel_history")
        .group_by(v.c.merchant, v.c.group_name)
    )
    found: dict[str, Merchant] = {}
    for merchant, group_name, total, n in db.execute(_who(q, person)):
        key = classify.merchant_key(str(merchant)) or str(merchant)
        m = found.get(key)
        if m is None:
            found[key] = Merchant(key, group_name, Decimal(str(total)), int(n))
        else:
            m.amount += Decimal(str(total))
            m.transactions += int(n)
    ranked = sorted(found.values(), key=lambda m: (-m.amount, m.merchant))
    return [m for m in ranked if m.amount > 0][:limit]


def trend(
    db: Session, month: date, count: int = TREND_MONTHS, person: str | None = None
) -> list[tuple[date, Decimal]]:
    """Spending for each of the `count` months up to `month`."""
    start = add_months(month, -(count - 1))
    totals: dict[date, Decimal] = defaultdict(Decimal)
    q = (
        select(v.c.cash_month, func.sum(v.c.amount))
        .where(v.c.cash_month >= start, v.c.cash_month <= month)
        .group_by(v.c.cash_month)
    )
    for m, total in db.execute(_who(q, person)):
        totals[m] = Decimal(str(total))
    return [(add_months(start, i), totals[add_months(start, i)]) for i in range(count)]


SERIES_BY = ("none", "group", "category", "person", "account", "country")
MAX_SERIES = 7  # the chart's palette; what is left goes together as "Everything else"
REST = "Everything else"


@dataclass
class Series:
    """One line or bar series of the spending chart."""

    key: str
    label: str
    color: str | None  # the group's color when the split is by group
    values: list[Decimal]  # one per month, oldest first


@dataclass
class SeriesSet:
    """The spending chart's months and series."""

    months: list[date]
    by: str
    series: list[Series]


def series(
    db: Session, month: date, count: int, by: str = "none", person: str | None = None
) -> SeriesSet:
    """Spending for each of `count` months up to `month`, split by a dimension (ADR-094): the
    chart with controls reads this. The MAX_SERIES largest over the period keep their own
    series, the rest add up into one. Grouped by the database; the same lines as `trend`."""
    if by not in SERIES_BY:
        raise ValueError(f"by must be one of {', '.join(SERIES_BY)}")
    start = add_months(first(month), -(count - 1))
    months = [add_months(start, i) for i in range(count)]
    at = {m: i for i, m in enumerate(months)}
    label = {
        "none": None,
        "group": v.c.group_name,
        "category": v.c.category_name,
        "person": v.c.person,
        "account": v.c.account_name,
        "country": v.c.country,
    }[by]
    cols = [v.c.cash_month, func.sum(v.c.amount)]
    if label is not None:
        cols += [label, func.max(v.c.group_color)]
    q = select(*cols).where(v.c.cash_month >= start, v.c.cash_month <= first(month))
    q = q.group_by(v.c.cash_month) if label is None else q.group_by(v.c.cash_month, label)
    found: dict[str, Series] = {}
    for row in db.execute(_who(q, person)).all():
        name = "Spending" if label is None else (row[2] or "Not set")
        one = found.setdefault(
            name,
            Series(name, name, row[3] if by == "group" else None, [ZERO] * count),
        )
        one.values[at[row[0]]] += Decimal(str(row[1]))
    ranked = sorted(found.values(), key=lambda x: (-sum(x.values, ZERO), x.label))
    kept, rest = ranked[:MAX_SERIES], ranked[MAX_SERIES:]
    if rest:
        kept.append(
            Series(REST, REST, None, [sum((r.values[i] for r in rest), ZERO) for i in range(count)])
        )
    return SeriesSet(months, by, kept)


@dataclass
class Line:
    """A line behind a spending amount."""

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
