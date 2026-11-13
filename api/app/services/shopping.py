"""Where the spending went, one level deeper (ADR-028): merchants with visits, average ticket and
invoices; products from the SRI invoices with their price three months ago and a cheaper store;
and ways to save, read from the month's own lines. Spending lines come from mart.v_spending_line
(so the same lines count as everywhere else), the person switch included (ADR-026)."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine
from app.models import v_spending_line as v
from app.services import classify
from app.services.recurring import add_months, first

ZERO = Decimal(0)
CENT = Decimal("0.01")
DELIVERY = re.compile(r"\b(RAPPI|TIPTI|UBER ?EATS|PEDIDOS ?YA|GLOVO|DIDI ?FOOD)\b")
SMALL_TICKET = Decimal(15)  # "small, frequent": at most this on average...
SMALL_VISITS = 5  # ...at least this many times in the month
NEW_MIN = Decimal(50)  # a merchant new this month, worth a look from this much
NEW_LOOKBACK = 6  # months without it before
RISING_MIN = Decimal(100)  # a group up this much...
RISING_OVER = 3  # months before that make a group's usual
RISING_SHARE = Decimal("0.25")  # ...and this share over its average of the 3 months before
CHEAPER_SHARE = Decimal("0.05")  # another store at least 5% cheaper per unit
PRICE_MONTHS = 3
CHEAPER_MONTHS = 6


def _q(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def key_of(merchant: str) -> str:
    """A merchant's key for grouping; the merchant itself when it has none."""
    return classify.merchant_key(merchant) or merchant


def _lines(
    db: Session,
    start: date,
    end: date,
    person: str | None,
    group_id: int | None = None,
    category_id: int | None = None,
) -> list[Any]:
    q = select(
        v.c.transaction_id,
        v.c.cash_month,
        v.c.type,
        v.c.amount,
        v.c.group_id,
        v.c.group_name,
        v.c.category_id,
        v.c.merchant,
        v.c.source,
    ).where(v.c.cash_month >= start, v.c.cash_month <= end)
    if person:
        q = q.where(v.c.person == person)
    if group_id is not None:
        q = q.where(v.c.group_id == group_id)
    if category_id is not None:
        q = q.where(v.c.category_id == category_id)
    return list(db.execute(q))


# ---------- merchants ----------


@dataclass
class MerchantRow:
    """A merchant's spending, visits and average ticket."""

    merchant: str
    group_id: int
    group_name: str
    amount: Decimal = ZERO
    visits: int = 0
    avg_ticket: Decimal = ZERO
    invoices: int = 0
    transaction_ids: list[int] = field(default_factory=list)


def merchants(
    db: Session,
    month: date,
    person: str | None = None,
    group_id: int | None = None,
    category_id: int | None = None,
) -> list[MerchantRow]:
    """A month's merchants (statement lines only: a workbook month has none), biggest first.
    A visit is a charge; refunds reduce the amount, not the visits."""
    m = first(month)
    found: dict[str, MerchantRow] = {}
    for r in _lines(db, m, m, person, group_id, category_id):
        if r.source == "excel_history":
            continue
        key = key_of(str(r.merchant))
        row = found.setdefault(key, MerchantRow(key, int(r.group_id), str(r.group_name)))
        row.amount += Decimal(str(r.amount))
        row.visits += 1 if r.amount > 0 else 0
        row.transaction_ids.append(int(r.transaction_id))
    ids = [i for row in found.values() for i in row.transaction_ids]
    invoiced: dict[int, int] = defaultdict(int)
    for start in range(0, len(ids), 1000):  # SQL Server takes up to 2,100 parameters
        chunk = ids[start : start + 1000]
        for tid, n in db.execute(
            select(Invoice.transaction_id, func.count())
            .where(Invoice.transaction_id.in_(chunk))
            .group_by(Invoice.transaction_id)
        ):
            if tid is not None:
                invoiced[int(tid)] = int(n)
    for row in found.values():
        row.amount = _q(row.amount)
        row.avg_ticket = _q(row.amount / row.visits) if row.visits else ZERO
        row.invoices = sum(invoiced[i] for i in row.transaction_ids)
    return sorted(
        (r for r in found.values() if r.amount > 0), key=lambda r: (-r.amount, r.merchant)
    )


# ---------- products ----------


@dataclass
class ProductRow:
    """A product's times bought, quantity, amount and unit price."""

    product_key: str
    description: str
    product_group: str | None
    times: int
    quantity: Decimal
    amount: Decimal
    unit_price: Decimal  # what was paid per unit, tax included
    before: Decimal | None  # the same, over the three months before
    change: Decimal | None  # share, e.g. 0.12 for 12% more
    stores: list[str]
    cheaper_store: str | None = None
    cheaper_price: Decimal | None = None
    could_save: Decimal = ZERO


def _unit(amount: Decimal, quantity: Decimal) -> Decimal:
    return _q(amount / quantity) if quantity else _q(amount)


def _product_lines(db: Session, start: date, end_exclusive: date) -> list[Any]:
    q = (
        select(
            InvoiceLine.product_key,
            InvoiceLine.description,
            InvoiceLine.product_group,
            InvoiceLine.quantity,
            InvoiceLine.total,
            Invoice.issuer_name,
            Invoice.issue_date,
        )
        .join(Invoice, Invoice.invoice_id == InvoiceLine.invoice_id)
        .where(Invoice.issue_date >= start, Invoice.issue_date < end_exclusive)
    )
    return list(db.execute(q))


def products(
    db: Session, month: date, product_group: str | None = None, store: str | None = None
) -> list[ProductRow]:
    """A month's products from its invoices (by invoice date), biggest first: how often, how
    much, the unit price against the three months before, and a store that sold it for less in
    the last six months."""
    m = first(month)
    nxt = add_months(m, 1)
    now: dict[str, list[Any]] = defaultdict(list)
    for r in _product_lines(db, m, nxt):
        if product_group and r.product_group != product_group:
            continue
        if store and r.issuer_name != store:
            continue
        now[r.product_key].append(r)
    if not now:
        return []
    before: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    by_store: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for r in _product_lines(db, add_months(m, -CHEAPER_MONTHS), nxt):
        if r.product_key not in now:
            continue
        qty = Decimal(str(r.quantity)) or Decimal(1)
        total = Decimal(str(r.total))
        if r.issue_date >= add_months(m, -PRICE_MONTHS) and r.issue_date < m:
            before[r.product_key][0] += total
            before[r.product_key][1] += qty
        by_store[(r.product_key, r.issuer_name)][0] += total
        by_store[(r.product_key, r.issuer_name)][1] += qty
    out = []
    for key, rows in now.items():
        qty = sum((Decimal(str(r.quantity)) or Decimal(1) for r in rows), ZERO)
        amount = _q(sum((Decimal(str(r.total)) for r in rows), ZERO))
        unit = _unit(amount, qty)
        b = before.get(key)
        was = _unit(b[0], b[1]) if b and b[1] else None
        change = (
            ((unit - was) / was).quantize(Decimal("0.0001")) if was is not None and was else None
        )
        stores = sorted({r.issuer_name for r in rows})
        row = ProductRow(
            product_key=key,
            description=rows[-1].description,
            product_group=rows[-1].product_group,
            times=len(rows),
            quantity=qty,
            amount=amount,
            unit_price=unit,
            before=was,
            change=change,
            stores=stores,
        )
        best = min(
            (
                (_unit(t, q), s)
                for (k, s), (t, q) in by_store.items()
                if k == key and s not in stores and q
            ),
            default=None,
        )
        if best and best[0] < unit * (1 - CHEAPER_SHARE):
            row.cheaper_price, row.cheaper_store = best
            row.could_save = _q((unit - best[0]) * qty)
        out.append(row)
    return sorted(out, key=lambda p: (-p.amount, p.description))


# ---------- ways to save ----------


@dataclass
class Idea:
    """A saving worth a look, with where to see it."""

    key: str
    title: str
    detail: str
    amount: Decimal  # the money this is about in the month (not a promise of savings)
    count: int
    link: str | None = None


def _money(x: Decimal) -> str:
    return f"${_q(x):,.2f}"


def _total(rs: list[Any]) -> Decimal:
    return sum((Decimal(str(r.amount)) for r in rs), ZERO)


@dataclass
class _Lines:
    """A month's lines, and the months before it, as the ideas read them."""

    month: date
    rows: list[Any]  # the month and the NEW_LOOKBACK months before
    by_merchant: dict[str, list[Any]] = field(default_factory=dict)  # statement lines, no fees
    delivery: dict[str, list[Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Group the month's statement lines by merchant and pick out the delivery apps."""
        grouped: dict[str, list[Any]] = defaultdict(list)
        for r in self.this:
            if r.source != "excel_history" and r.type != "fee_interest":
                grouped[key_of(str(r.merchant))].append(r)
        self.by_merchant = dict(grouped)
        self.delivery = {k: rs for k, rs in grouped.items() if DELIVERY.search(k)}

    @property
    def this(self) -> list[Any]:
        """The month's own lines."""
        return [r for r in self.rows if r.cash_month == self.month]

    def link(self, group_id: object = None, view: str = "merchants") -> str:
        """Where on Spending an idea's lines are."""
        group = f"&g={group_id}" if group_id is not None else ""
        return f"/spending?month={self.month:%Y-%m}&view={view}{group}"


def _fees(ln: _Lines) -> list[Idea]:
    fees = [r for r in ln.this if r.type == "fee_interest"]
    if not fees:
        return []
    return [
        Idea(
            "fees",
            f"Bank fees and interest: {len(fees)} charges",
            "Each one is small, so they add up unseen. Open them to see which habit drives "
            "them (transfers, withdrawals, a card's interest).",
            _q(_total(fees)),
            len(fees),
            ln.link(fees[0].group_id),
        )
    ]


def _delivery(ln: _Lines) -> list[Idea]:
    if not ln.delivery:
        return []
    orders = [r for rs in ln.delivery.values() for r in rs]
    n = sum(1 for r in orders if r.amount > 0)
    shown = ", ".join(sorted(ln.delivery)[:3])
    return [
        Idea(
            "delivery",
            f"Delivery apps: {n} orders",
            f"{shown}. Delivery fees and markups are inside these totals; the same basket "
            "at the store usually costs less.",
            _q(_total(orders)),
            n,
            ln.link(),
        )
    ]


def _small_and_frequent(ln: _Lines) -> list[Idea]:
    out = []
    for key, rs in ln.by_merchant.items():
        visits = [r for r in rs if r.amount > 0]
        total = _total(rs)
        if key in ln.delivery or len(visits) < SMALL_VISITS or total / len(visits) > SMALL_TICKET:
            continue
        out.append(
            Idea(
                f"small:{key}",
                f"{key}: {len(visits)} small charges",
                f"About {_money(total / len(visits))} each. Small and frequent is where a "
                "habit hides.",
                _q(total),
                len(visits),
                ln.link(rs[0].group_id),
            )
        )
    return out


def _new_merchants(ln: _Lines) -> list[Idea]:
    seen_before = {
        key_of(str(r.merchant))
        for r in ln.rows
        if r.cash_month < ln.month and r.source != "excel_history"
    }
    if not seen_before:  # no statement history: everything would be "new"
        return []
    out = []
    for key, rs in ln.by_merchant.items():
        total = _total(rs)
        if key in seen_before or key in ln.delivery or total < NEW_MIN:
            continue
        out.append(
            Idea(
                f"new:{key}",
                f"New this month: {key}",
                f"Not seen in the {NEW_LOOKBACK} months before. One-off, or the start of "
                "something that repeats?",
                _q(total),
                len(rs),
                ln.link(rs[0].group_id),
            )
        )
    return out


def _rising_groups(ln: _Lines) -> list[Idea]:
    groups: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    names: dict[int, str] = {}
    for r in ln.rows:
        groups[int(r.group_id)][r.cash_month] += Decimal(str(r.amount))
        names[int(r.group_id)] = str(r.group_name)
    out = []
    for gid, by_month in groups.items():
        prior = [by_month.get(add_months(ln.month, -i), ZERO) for i in range(1, RISING_OVER + 1)]
        if not all(prior):
            continue
        usual = sum(prior, ZERO) / RISING_OVER
        now = by_month.get(ln.month, ZERO)
        if now - usual >= RISING_MIN and now >= usual * (1 + RISING_SHARE):
            out.append(
                Idea(
                    f"rising:{gid}",
                    f"{names[gid]} is up {_money(now - usual)} on its usual",
                    f"{_money(now)} this month against about {_money(usual)} a month over the "
                    "three before.",
                    _q(now - usual),
                    0,
                    ln.link(gid),
                )
            )
    return out


def _cheaper_elsewhere(db: Session, ln: _Lines) -> list[Idea]:
    cheaper = [p for p in products(db, ln.month) if p.cheaper_store]
    if not cheaper:
        return []
    top = max(cheaper, key=lambda p: p.could_save)
    return [
        Idea(
            "cheaper",
            f"Same product, cheaper store: {len(cheaper)} products",
            f"For example {top.description}: {_money(top.unit_price)} at "
            f"{', '.join(top.stores)}, {_money(top.cheaper_price or ZERO)} at "
            f"{top.cheaper_store}.",
            _q(sum((p.could_save for p in cheaper), ZERO)),
            len(cheaper),
            ln.link(view="products"),
        )
    ]


def ideas(db: Session, month: date, person: str | None = None) -> list[Idea]:
    """Patterns in a month's lines worth a look, biggest first: fees and interest, delivery
    apps, small frequent charges, merchants new this month, groups well above their usual, and
    products another store sold for less."""
    m = first(month)
    ln = _Lines(m, _lines(db, add_months(m, -NEW_LOOKBACK), m, person))
    out = [
        *_fees(ln),
        *_delivery(ln),
        *_small_and_frequent(ln),
        *_new_merchants(ln),
        *_rising_groups(ln),
        *_cheaper_elsewhere(db, ln),
    ]
    return sorted(out, key=lambda i: (-i.amount, i.title))
