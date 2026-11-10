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
