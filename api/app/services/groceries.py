"""Groceries (ADR-059): what the supermarket money buys.

The statements say how much went to Groceries each month; the supermarkets' electronic invoices
(Supermaxi, Megamaxi, Mi Comisariato…) say what it bought, product by product. This puts the two
side by side for a month: spending against the months before, how much of it has its invoice,
spending by aisle (product group), the top products with their price against the months before,
the stores, and the grocery charges whose invoice hasn't arrived.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import PRODUCT_GROUPS, Category, Invoice
from app.models import v_spending_line as v
from app.services import shopping
from app.services.recurring import add_months, first

ZERO = Decimal(0)
GROUP = "Groceries"
TREND_MONTHS = 6
AVERAGE_OF = 3  # months before, for "usual"
TOP_PRODUCTS = 20
NOT_GROUPED = "Not grouped yet"
# Supermarket chains in Ecuador, as their invoices name them (whole words).
STORES = re.compile(
    r"\b(FAVORITA|SUPERMAXI|MEGAMAXI|AKI|GRAN AKI|ROSADO|COMISARIATO|TIENDAS INDUSTRIALES"
    r"|TIA|SANTA MARIA|MEGASANTAMARIA|GERARDO ORTIZ|CORAL|FRESH MARKET|MEGAMARKET)\b"
)
# Aisles that are food or the household shop; the rest (pharmacy, pets, other) also count once
# the invoice is a supermarket's.
FOOD = set(PRODUCT_GROUPS[:9])


@dataclass
class MonthPoint:
    month: date
    spent: Decimal
    invoiced: Decimal


@dataclass
class Aisle:
    name: str
    amount: Decimal
    lines: int
    usual: Decimal  # average of the months before


@dataclass
class Store:
    name: str
    invoices: int
    amount: Decimal


@dataclass
class Charge:
    transaction_id: int
    txn_date: date
    merchant: str
    amount: Decimal
    account_name: str | None


@dataclass
class Groceries:
    month: date
    spent: Decimal
    usual: Decimal  # average of the three months before
    invoiced: Decimal
    trend: list[MonthPoint]
    aisles: list[Aisle]
    products: list[shopping.ProductRow]
    stores: list[Store]
    missing: list[Charge]
    ungrouped_products: int
    weeks: Decimal = field(default=ZERO)  # weeks in the month, for "a week"


def _group_id(db: Session) -> int | None:
    return db.scalar(
        select(Category.category_id).where(Category.parent_id.is_(None), Category.name == GROUP)
    )


def _spent(db: Session, gid: int | None, start: date, end: date) -> dict[date, Decimal]:
    out: dict[date, Decimal] = defaultdict(lambda: ZERO)
    if gid is None:
        return out
    q = select(v.c.cash_month, v.c.amount).where(
        v.c.group_id == gid, v.c.cash_month >= start, v.c.cash_month <= end
    )
    for m, amount in db.execute(q):
        out[m] += Decimal(str(amount))
    return out


def _grocery_txns(db: Session, gid: int | None, start: date, end: date) -> set[int]:
    if gid is None:
        return set()
    q = select(v.c.transaction_id).where(
        v.c.group_id == gid, v.c.cash_month >= start, v.c.cash_month <= end
    )
    return set(db.scalars(q))


def is_store(name: str) -> bool:
    return bool(STORES.search(name.upper()))


def _invoices(db: Session, start: date, end_exclusive: date, txns: set[int]) -> list[Invoice]:
    """A supermarket's invoices: paid by a Groceries line, from a supermarket chain, or mostly
    food by its products."""
    rows = list(
        db.scalars(
            select(Invoice)
            .options(selectinload(Invoice.lines))  # one query for every invoice's lines
            .where(Invoice.issue_date >= start, Invoice.issue_date < end_exclusive)
        )
    )
    out = []
    for inv in rows:
        food = sum(1 for ln in inv.lines if ln.product_group in FOOD)
        if (
            (inv.transaction_id is not None and inv.transaction_id in txns)
            or is_store(inv.issuer_name)
            or (inv.lines and food * 2 >= len(inv.lines))
        ):
            out.append(inv)
    return out


def build(db: Session, month: date) -> Groceries:
    m = first(month)
    start = add_months(m, -(TREND_MONTHS - 1))
    nxt = add_months(m, 1)
    gid = _group_id(db)
    spent = _spent(db, gid, start, m)
    txns = _grocery_txns(db, gid, add_months(start, -1), add_months(m, 1))
    invoices = _invoices(db, start, nxt, txns)

    invoiced: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for inv in invoices:
        invoiced[first(inv.issue_date)] += inv.total
    trend = [
        MonthPoint(
            add_months(start, i), spent[add_months(start, i)], invoiced[add_months(start, i)]
        )
        for i in range(TREND_MONTHS)
    ]
    before = [p.spent for p in trend[-1 - AVERAGE_OF : -1] if p.spent]
    usual = (sum(before, ZERO) / len(before)).quantize(Decimal("0.01")) if before else ZERO

    now = [inv for inv in invoices if first(inv.issue_date) == m]
    earlier = [inv for inv in invoices if add_months(m, -AVERAGE_OF) <= first(inv.issue_date) < m]
    aisle_now: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for inv in now:
        for ln in inv.lines:
            a = aisle_now[ln.product_group or NOT_GROUPED]
            a[0] += ln.total
            a[1] += 1
    aisle_before: dict[str, Decimal] = defaultdict(lambda: ZERO)
    months_before = len({first(i.issue_date) for i in earlier}) or 1
    for inv in earlier:
        for ln in inv.lines:
            aisle_before[ln.product_group or NOT_GROUPED] += ln.total
    aisles = sorted(
        (
            Aisle(
                name,
                amount,
                int(n),
                (aisle_before[name] / months_before).quantize(Decimal("0.01")),
            )
            for name, (amount, n) in aisle_now.items()
        ),
        key=lambda a: (a.name == NOT_GROUPED, -a.amount),
    )

    names = {inv.issuer_name for inv in now}
    keys = {ln.product_key for inv in now for ln in inv.lines}
    products = [
        p
        for p in shopping.products(db, m)
        if p.product_key in keys and any(s in names for s in p.stores)
    ][:TOP_PRODUCTS]
    ungrouped = len({ln.product_key for inv in now for ln in inv.lines if not ln.product_group})

    by_store: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for inv in now:
        by_store[inv.issuer_name][0] += 1
        by_store[inv.issuer_name][1] += inv.total
    stores = sorted(
        (Store(n, int(c), t) for n, (c, t) in by_store.items()), key=lambda s: -s.amount
    )

    paid = {inv.transaction_id for inv in invoices if inv.transaction_id is not None}
    missing = []
    if gid is not None:
        q = select(v).where(v.c.group_id == gid, v.c.cash_month == m, v.c.source != "excel")
        for r in db.execute(q.order_by(v.c.txn_date, v.c.transaction_id)):
            if r.transaction_id not in paid and Decimal(str(r.amount)) > 0:
                missing.append(
                    Charge(
                        r.transaction_id,
                        r.txn_date,
                        str(r.merchant or r.description),
                        Decimal(str(r.amount)),
                        r.account_name,
                    )
                )
    days = (nxt - m).days
    return Groceries(
        month=m,
        spent=spent[m],
        usual=usual,
        invoiced=invoiced[m],
        trend=trend,
        aisles=aisles,
        products=products,
        stores=stores,
        missing=missing,
        ungrouped_products=ungrouped,
        weeks=(Decimal(days) / 7).quantize(Decimal("0.01")),
    )


# --- Trends (ADR-067): a year of groceries, month against month, and the patterns in it. ---

TREND_YEAR = 12
MOVERS = 8
REGULAR_OF = 3  # bought in at least this many of the months before → a regular


@dataclass
class TrendMonth:
    month: date
    spent: Decimal  # statements
    invoiced: Decimal
    trips: int  # supermarket invoices
    basket: Decimal  # invoiced ÷ trips
    aisles: dict[str, Decimal]


@dataclass
class Cell:
    """What one aisle, type and brand cost in a month: the client compares any two months."""

    month: date
    aisle: str
    type: str | None
    brand: str | None
    amount: Decimal
    lines: int


@dataclass
class Weekday:
    day: int  # 0 = Monday
    trips: int
    amount: Decimal


@dataclass
class Mover:
    product_key: str
    description: str
    aisle: str
    first_month: date
    first_price: Decimal
    last_month: date
    last_price: Decimal
    change: Decimal  # last ÷ first - 1
    amount: Decimal  # spent on it in the period


@dataclass
class Regular:
    product_key: str
    description: str
    aisle: str
    months: int  # of the months before it was bought in
    usual: Decimal  # average a month when bought


@dataclass
class Trends:
    month: date
    months: list[TrendMonth]
    aisles: list[str]  # most spent first
    cells: list[Cell]
    weekdays: list[Weekday]
    risers: list[Mover]  # unit price went up the most
    fallers: list[Mover]
    new: list[Regular]  # first bought this month
    skipped: list[Regular]  # regulars not bought this month


def _unit(total: Decimal, qty: Decimal) -> Decimal:
    return (total / qty).quantize(Decimal("0.01")) if qty > 0 else ZERO


def trends(db: Session, month: date, months: int = TREND_YEAR) -> Trends:
    m = first(month)
    n = max(2, min(months, 36))
    start = add_months(m, -(n - 1))
    nxt = add_months(m, 1)
    gid = _group_id(db)
    spent = _spent(db, gid, start, m)
    txns = _grocery_txns(db, gid, add_months(start, -1), nxt)
    invoices = _invoices(db, start, nxt, txns)
    keys = [add_months(start, i) for i in range(n)]

    per: dict[date, TrendMonth] = {
        k: TrendMonth(k, spent[k], ZERO, 0, ZERO, defaultdict(lambda: ZERO)) for k in keys
    }
    cells: dict[tuple[date, str, str | None, str | None], list[Decimal]] = defaultdict(
        lambda: [ZERO, ZERO]
    )
    weekdays = [Weekday(d, 0, ZERO) for d in range(7)]
    # product → month → [amount, quantity]; and its description and aisle
    bought: dict[str, dict[date, list[Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: [ZERO, ZERO])
    )
    names: dict[str, tuple[str, str]] = {}
    for inv in invoices:
        k = first(inv.issue_date)
        p = per[k]
        p.invoiced += inv.total
        p.trips += 1
        w = weekdays[inv.issue_date.weekday()]
        w.trips += 1
        w.amount += inv.total
        for ln in inv.lines:
            aisle = ln.product_group or NOT_GROUPED
            p.aisles[aisle] += ln.total
            c = cells[(k, aisle, ln.product_type, ln.brand)]
            c[0] += ln.total
            c[1] += 1
            b = bought[ln.product_key][k]
            b[0] += ln.total
            b[1] += ln.quantity
            names[ln.product_key] = (ln.description, aisle)

    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in per.values():
        p.basket = (p.invoiced / p.trips).quantize(Decimal("0.01")) if p.trips else ZERO
        for a, amt in p.aisles.items():
            totals[a] += amt
        p.aisles = dict(p.aisles)
    aisles = sorted(totals, key=lambda a: (a == NOT_GROUPED, -totals[a]))

    movers: list[Mover] = []
    for key, by in bought.items():
        seen = sorted(k for k, (amt, q) in by.items() if q > 0 and amt > 0)
        if len(seen) < 2:
            continue
        f, last = seen[0], seen[-1]
        fp, lp = _unit(*by[f]), _unit(*by[last])
        if fp <= 0:
            continue
        movers.append(
            Mover(
                key,
                names[key][0],
                names[key][1],
                f,
                fp,
                last,
                lp,
                (lp / fp - 1).quantize(Decimal("0.0001")),
                sum((v[0] for v in by.values()), ZERO),
            )
        )
    risers = sorted((x for x in movers if x.change > 0), key=lambda x: (-x.change, -x.amount))
    fallers = sorted((x for x in movers if x.change < 0), key=lambda x: (x.change, -x.amount))

    before = keys[-1 - min(6, n - 1) : -1]  # up to six months before this one
    new, skipped = [], []
    for key, by in bought.items():
        had = [k for k in before if by.get(k, [ZERO])[0] > 0]
        now = by.get(m, [ZERO])[0] > 0
        desc, aisle = names[key]
        if now and not any(by.get(k, [ZERO])[0] > 0 for k in keys[:-1]):
            new.append(Regular(key, desc, aisle, 0, by[m][0]))
        elif not now and len(had) >= REGULAR_OF:
            usual = (sum((by[k][0] for k in had), ZERO) / len(had)).quantize(Decimal("0.01"))
            skipped.append(Regular(key, desc, aisle, len(had), usual))
    new.sort(key=lambda r: -r.usual)
    skipped.sort(key=lambda r: (-r.months, -r.usual))

    return Trends(
        month=m,
        months=[per[k] for k in keys],
        aisles=aisles,
        cells=[
            Cell(k, a, t, b, amt, int(c))
            for (k, a, t, b), (amt, c) in sorted(
                cells.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1][0])
            )
        ],
        weekdays=weekdays,
        risers=risers[:MOVERS],
        fallers=fallers[:MOVERS],
        new=new[:MOVERS],
        skipped=skipped[:MOVERS],
    )
