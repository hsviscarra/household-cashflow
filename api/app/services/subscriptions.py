"""Recurring charges (F14, ADR-011): subscriptions found in the statement lines.

Lines are grouped by merchant the way the review queue groups them (reference numbers and
confirmation codes dropped, F9). A merchant is a subscription when it repeats at a steady
interval with a similar amount:
- weekly (every 5 to 9 days), as app stores bill some apps;
- monthly (25 to 35 days), quarterly (80 to 100) or yearly (350 to 380).
"Similar" means every charge within 25% of the typical (median) amount. A merchant in a
Subscriptions & Software category that doesn't repeat yet (seen once, or at uneven intervals) is
listed as possible. A subscription is active while its last charge is no older than one and a half
intervals before the end of its card's latest approved statement; a card whose statements stop
earlier can't tell, so the subscription stays active. Fees, interest and the tax on digital
services (Financial Costs) are the cost of debt, not subscriptions.
"""

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import NamedTuple

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.models import Account, Category, Transaction
from app.services import status
from app.services.classify import merchant_key

LOOKBACK_DAYS = 400
SUBSCRIPTIONS_GROUP = "Subscriptions & Software"
COSTS_GROUP = "Financial Costs"
CADENCES: list[tuple[str, int, int, Decimal]] = [
    # name, shortest and longest interval in days, charges per month
    ("weekly", 5, 9, Decimal(52) / 12),
    ("monthly", 25, 35, Decimal(1)),
    ("quarterly", 80, 100, Decimal(1) / 3),
    ("yearly", 350, 380, Decimal(1) / 12),
]
SIMILAR = Decimal("0.25")
# A price increase worth saying (ADR-097): the last charge over the earlier ones by 3% and 0.50.
PRICE_UP_SHARE = Decimal("0.03")
PRICE_UP_MIN = Decimal("0.50")
CENT = Decimal("0.01")


@dataclass
class Charge:
    """One charge of a subscription."""

    transaction_id: int
    txn_date: date
    amount: Decimal  # positive: what it cost
    description: str
    account_name: str | None


@dataclass
class Subscription:
    """A repeating charge: its cadence, usual amount and yearly cost."""

    merchant: str
    cadence: str  # weekly, monthly, quarterly, yearly or possible
    typical: Decimal
    monthly_cost: Decimal
    yearly_cost: Decimal
    category_path: str | None
    accounts: list[str]
    charges: list[Charge] = field(default_factory=list)
    next_expected: date | None = None
    active: bool = True
    price_up: Decimal | None = None  # how much the last charge is over the earlier ones

    @property
    def last(self) -> date:
        """The day of the latest charge."""
        return self.charges[-1].txn_date


class Line(NamedTuple):
    """The columns of a statement line this module needs (not the whole row: ADR-086)."""

    transaction_id: int
    txn_date: date
    amount: Decimal
    description_raw: str
    merchant_key: str | None
    type: str
    category_id: int | None
    account_id: int | None


def _lines(db: Session, since: date) -> list[tuple[Line, str | None]]:
    part = aliased(Transaction)
    has_parts = exists().where(part.parent_transaction_id == Transaction.transaction_id)
    rows = db.execute(
        select(
            Transaction.transaction_id,
            Transaction.txn_date,
            Transaction.amount,
            Transaction.description_raw,
            Transaction.merchant_key,
            Transaction.type,
            Transaction.category_id,
            Transaction.account_id,
            Account.name,
        )
        .outerjoin(Account, Account.account_id == Transaction.account_id)
        .where(
            Transaction.source.in_(("statement", "manual")),
            Transaction.type.in_(("expense", "fee_interest")),
            Transaction.amount < 0,
            Transaction.txn_date >= since,
            ~has_parts,
        )
        .order_by(Transaction.txn_date, Transaction.transaction_id)
    )
    return [(Line(*r[:8]), r[8]) for r in rows]


def _paths(db: Session) -> tuple[dict[int, str], set[int], set[int]]:
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    paths, subs, costs = {}, set(), set()
    for c in cats.values():
        parent = cats.get(c.parent_id) if c.parent_id is not None else None
        paths[c.category_id] = f"{parent.name} / {c.name}" if parent else c.name
        group = parent.name if parent else c.name
        if group == SUBSCRIPTIONS_GROUP:
            subs.add(c.category_id)
        elif group == COSTS_GROUP:
            costs.add(c.category_id)
    return paths, subs, costs


def _covered_until(db: Session, rows: list[tuple[Line, str | None]]) -> dict[int, date]:
    """Per account, the last day its approved statements cover (else its newest line)."""
    out: dict[int, date] = {}
    for st in status.approved_statements(db):
        out[st.account_id] = max(out.get(st.account_id, st.end), st.end)
    for t, _ in rows:
        if t.account_id is not None and t.account_id not in out:
            out[t.account_id] = t.txn_date
        elif t.account_id is not None:
            out[t.account_id] = max(out[t.account_id], t.txn_date)
    return out


def cadence_of(dates: list[date]) -> tuple[str, int] | None:
    """The cadence whose interval range holds every gap between the charges, and the median
    gap in days; None when there is no steady interval."""
    if len(dates) < 2:
        return None
    gaps = [(b - a).days for a, b in itertools.pairwise(dates)]
    for name, lo, hi, _ in CADENCES:
        if all(lo <= g <= hi for g in gaps):
            return name, int(median(gaps))
    return None


def _similar(amounts: list[Decimal]) -> bool:
    mid = Decimal(str(median(amounts)))
    return all(abs(a - mid) <= mid * SIMILAR for a in amounts)


def price_up(amounts: list[Decimal]) -> Decimal | None:
    """How much the last charge is over what the earlier ones typically were, when that is a
    real increase and not a few cents of exchange rate."""
    if len(amounts) < 2:
        return None
    before = Decimal(str(median(amounts[:-1])))
    more = amounts[-1] - before
    return more.quantize(CENT) if more >= max(PRICE_UP_MIN, before * PRICE_UP_SHARE) else None


def find(db: Session, today: date | None = None) -> list[Subscription]:
    """The recurring charges in the last 400 days of lines, by cadence, with what each costs."""
    today = today or date.today()
    paths, subs, costs = _paths(db)
    rows = [
        (t, name)
        for t, name in _lines(db, today - timedelta(days=LOOKBACK_DAYS))
        if t.category_id not in costs and t.type != "fee_interest"
    ]
    if not rows:
        return []
    covered = _covered_until(db, rows)
    groups: dict[str, list[tuple[Line, str | None]]] = defaultdict(list)
    for t, name in rows:
        key = t.merchant_key if t.merchant_key is not None else merchant_key(t.description_raw)
        groups[key or t.description_raw].append((t, name))

    found = []
    for key, items in groups.items():
        charges = [
            Charge(t.transaction_id, t.txn_date, -t.amount, t.description_raw, name)
            for t, name in items
        ]
        amounts = [c.amount for c in charges]
        cats = [t.category_id for t, _ in items if t.category_id is not None]
        category = max(set(cats), key=cats.count) if cats else None
        steady = cadence_of([c.txn_date for c in charges])
        typical = Decimal(str(median(amounts))).quantize(CENT)
        accounts = sorted({c.account_name for c in charges if c.account_name})
        if steady and _similar(amounts):
            name, gap = steady
            per_month = next(p for n, _, _, p in CADENCES if n == name)
            monthly = (typical * per_month).quantize(CENT)
            nxt = charges[-1].txn_date + timedelta(days=gap)
            last_line = items[-1][0]
            until = covered.get(last_line.account_id or -1, last_line.txn_date)
            active = (until - charges[-1].txn_date).days <= gap * 3 // 2
            found.append(
                Subscription(
                    key,
                    name,
                    typical,
                    monthly,
                    (monthly * 12).quantize(CENT),
                    paths.get(category) if category else None,
                    accounts,
                    charges,
                    nxt,
                    active,
                    price_up(amounts) if active else None,
                )
            )
        elif category in subs:
            found.append(
                Subscription(
                    key,
                    "possible",
                    typical,
                    typical,
                    (typical * 12).quantize(CENT),
                    paths.get(category),
                    accounts,
                    charges,
                    None,
                    True,
                )
            )
    order = {"weekly": 0, "monthly": 1, "quarterly": 2, "yearly": 3, "possible": 4}
    return sorted(
        found, key=lambda s: (order[s.cadence], not s.active, -s.monthly_cost, s.merchant)
    )
