"""Balance sheet (F14, ADR-012): what the household owns and owes on a date.

- Bank accounts and cards: each one's latest approved statement closing balance on or before the
  date (cash for checking and savings, a liability for a card).
- Holdings (property, vehicle, investments, loans, personal loans...): their latest balance
  snapshot on or before the date, whether from the workbook, entered on the page or read from a
  loan's payment history.
- A purchase in progress (the new house's down payment): what has been paid so far, as an asset:
  the latest "paid so far" snapshot plus later lines in the purchase's category. What is left of
  the down payment, and what will be financed at delivery, are commitments: they are shown but
  not counted, because the house and its loan don't exist until delivery.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    Account,
    BalanceSnapshot,
    Holding,
    RecurringEntry,
    RecurringTemplate,
    Transaction,
)
from app.services import recurring, status

ZERO = Decimal(0)
ASSET_CLASSES = ("property", "vehicle", "investment", "cash", "purchase")
LIABILITY_CLASSES = ("loan", "personal_loan", "card")
MANUAL = "manual"


class NetWorthError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def side_of(holding_class: str, side: str | None = None) -> str:
    if holding_class in ASSET_CLASSES:
        return "asset"
    if holding_class in LIABILITY_CLASSES:
        return "liability"
    if side not in ("asset", "liability"):
        raise NetWorthError("Say whether it is something you own or owe.")
    return side


@dataclass
class Value:
    snapshot_id: int | None
    as_of: date
    amount: Decimal
    source: str
    notes: str | None = None


@dataclass
class Purchase:
    target: Decimal
    paid: Decimal
    remaining: Decimal
    installment: Decimal | None
    installments_left: int | None
    full_price: Decimal | None
    at_delivery: Decimal | None
    lines: Decimal  # paid through categorized lines after the latest "paid so far"


@dataclass
class Loan:
    monthly_payment: Decimal | None
    paid_this_year: Decimal
    payments_this_year: int


@dataclass
class Item:
    key: str
    name: str
    side: str
    holding_class: str
    value: Decimal | None
    as_of: date | None
    source: str | None
    holding_id: int | None = None
    account_id: int | None = None
    is_active: bool = True
    notes: str | None = None
    history: list[Value] = field(default_factory=list)
    purchase: Purchase | None = None
    loan: Loan | None = None
    category_id: int | None = None
    recurring_template_id: int | None = None


@dataclass
class Point:
    month: date
    assets: Decimal
    liabilities: Decimal

    @property
    def net(self) -> Decimal:
        return self.assets - self.liabilities


@dataclass
class BalanceSheet:
    as_of: date
    items: list[Item]
    series: list[Point]

    def total(self, side: str) -> Decimal:
        return sum((i.value or ZERO for i in self.items if i.side == side and i.is_active), ZERO)

    @property
    def commitments(self) -> Decimal:
        out = ZERO
        for i in self.items:
            if i.purchase and i.is_active:
                out += i.purchase.remaining + (i.purchase.at_delivery or ZERO)
        return out


# ---------------------------------------------------------------- reading
def _accounts(db: Session, as_of: date) -> list[Item]:
    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    latest: dict[int, tuple[date, Decimal | None, str]] = {}
    history: dict[int, list[Value]] = defaultdict(list)
    for s in status.approved_statements(db):
        if s.end > as_of or s.closing is None:
            continue
        history[s.account_id].append(Value(None, s.end, s.closing, "statement", s.file_name))
        if s.account_id not in latest or s.end >= latest[s.account_id][0]:
            latest[s.account_id] = (s.end, s.closing, s.file_name)
    out = []
    for account_id, (end, closing, _) in latest.items():
        a = accounts[account_id]
        card = a.kind == "credit_card"
        out.append(
            Item(
                key=f"account-{account_id}",
                name=a.name,
                side="liability" if card else "asset",
                holding_class="card" if card else "cash",
                value=closing,
                as_of=end,
                source="statement",
                account_id=account_id,
                is_active=a.is_active,
                history=sorted(history[account_id], key=lambda v: v.as_of),
            )
        )
    return out


def _paid_by_lines(db: Session, category_id: int, after: date | None, until: date) -> Decimal:
    part = aliased(Transaction)
    has_parts = exists().where(part.parent_transaction_id == Transaction.transaction_id)
    q = select(func.sum(Transaction.amount)).where(
        Transaction.category_id == category_id, Transaction.txn_date <= until, ~has_parts
    )
    if after is not None:
        q = q.where(Transaction.txn_date > after)
    total = db.scalar(q)
    return -Decimal(str(total)) if total else ZERO


def _loan(db: Session, h: Holding, as_of: date) -> Loan:
    if h.recurring_template_id is None:
        return Loan(None, ZERO, 0)
    history = recurring.amounts(db, [h.recurring_template_id])[h.recurring_template_id]
    monthly = recurring.amount_for(history, recurring.first(as_of))
    rows = db.execute(
        select(Transaction.amount)
        .join(RecurringEntry, RecurringEntry.entry_id == Transaction.recurring_entry_id)
        .where(
            RecurringEntry.template_id == h.recurring_template_id,
            RecurringEntry.month >= date(as_of.year, 1, 1),
            RecurringEntry.month <= as_of,
        )
    ).all()
    return Loan(
        abs(monthly) if monthly is not None else None,
        -sum((Decimal(str(r[0])) for r in rows), ZERO),
        len(rows),
    )


def _holdings(db: Session, as_of: date) -> list[Item]:
    snaps: dict[int, list[BalanceSnapshot]] = defaultdict(list)
    for s in db.scalars(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.holding_id.is_not(None))
        .order_by(BalanceSnapshot.as_of, BalanceSnapshot.snapshot_id)
    ):
        snaps[s.holding_id or 0].append(s)
    out = []
    for h in db.scalars(select(Holding).order_by(Holding.sort_order, Holding.name)):
        upto = [s for s in snaps[h.holding_id] if s.as_of <= as_of]
        last = upto[-1] if upto else None
        item = Item(
            key=f"holding-{h.holding_id}",
            name=h.name,
            side=h.side,
            holding_class=h.holding_class,
            value=last.amount if last else None,
            as_of=last.as_of if last else None,
            source=last.source if last else None,
            holding_id=h.holding_id,
            is_active=h.is_active,
            notes=h.notes,
            history=[Value(s.snapshot_id, s.as_of, s.amount, s.source, s.notes) for s in upto],
            category_id=h.category_id,
            recurring_template_id=h.recurring_template_id,
        )
        if h.holding_class == "purchase":
            base = last.amount if last else ZERO
            lines = (
                _paid_by_lines(db, h.category_id, last.as_of if last else None, as_of)
                if h.category_id
                else ZERO
            )
            paid = base + lines
            target = h.target_amount or paid
            remaining = max(target - paid, ZERO)
            left = (
                math.ceil(remaining / h.installment)
                if h.installment and h.installment > 0
                else None
            )
            item.value = paid
            item.purchase = Purchase(
                target,
                paid,
                remaining,
                h.installment,
                left,
                h.full_price,
                (h.full_price - target) if h.full_price is not None else None,
                lines,
            )
            if lines and not last:
                item.as_of, item.source = as_of, "lines"
        if h.holding_class == "loan":
            item.loan = _loan(db, h, as_of)
        out.append(item)
    return out


def sheet(db: Session, as_of: date | None = None, months: int = 24) -> BalanceSheet:
    as_of = as_of or date.today()
    items = _accounts(db, as_of) + _holdings(db, as_of)
    series = []
    end = recurring.first(as_of)
    for i in range(months - 1, -1, -1):
        m = recurring.add_months(end, -i)
        day = min(recurring.add_months(m, 1) - timedelta(days=1), as_of)
        point_items = _accounts(db, day) + _holdings(db, day)
        assets = sum(
            (x.value or ZERO for x in point_items if x.side == "asset" and x.is_active), ZERO
        )
        debts = sum(
            (x.value or ZERO for x in point_items if x.side == "liability" and x.is_active), ZERO
        )
        series.append(Point(m, assets, debts))
    order = {c: n for n, c in enumerate((*ASSET_CLASSES, *LIABILITY_CLASSES, "other"))}
    items.sort(
        key=lambda x: (x.side != "asset", order[x.holding_class], -(x.value or ZERO), x.name)
    )
    return BalanceSheet(as_of, items, series)


# ---------------------------------------------------------------- writing
def link_snapshots(db: Session) -> int:
    """Point workbook snapshots without a holding to the holding of the same name, creating it
    when it doesn't exist (after the workbook is reloaded)."""
    loose = list(db.scalars(select(BalanceSnapshot).where(BalanceSnapshot.holding_id.is_(None))))
    if not loose:
        return 0
    by_name = {h.name: h for h in db.scalars(select(Holding))}
    for s in loose:
        h = by_name.get(s.name)
        if h is None:
            h = Holding(name=s.name, side=s.kind, holding_class=_guess(s.name, s.kind))
            db.add(h)
            db.flush()
            by_name[s.name] = h
        s.holding_id = h.holding_id
    db.commit()
    return len(loose)


def _guess(name: str, kind: str) -> str:
    upper = name.upper()
    if "BIESS" in upper:
        return "loan"
    if upper.startswith("REMAINING TO PAY"):
        return "personal_loan"
    if kind == "liability":
        return "card"
    return "investment" if "STOCK" in upper else "cash"


def get_holding(db: Session, holding_id: int) -> Holding:
    h = db.get(Holding, holding_id)
    if h is None:
        raise NetWorthError(f"Item {holding_id} not found.", 404)
    return h


def create_holding(db: Session, fields: dict[str, object]) -> Holding:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise NetWorthError("Give it a name.")
    if db.scalar(select(Holding).where(Holding.name == name)):
        raise NetWorthError(f"{name} already exists.", 409)
    holding_class = str(fields["holding_class"])
    h = Holding(
        name=name[:100],
        side=side_of(holding_class, fields.get("side")),  # type: ignore[arg-type]
        holding_class=holding_class,
        target_amount=fields.get("target_amount"),
        installment=fields.get("installment"),
        full_price=fields.get("full_price"),
        category_id=fields.get("category_id"),
        recurring_template_id=fields.get("recurring_template_id"),
        notes=fields.get("notes"),
        sort_order=(db.scalar(select(func.max(Holding.sort_order))) or 0) + 1,
    )
    db.add(h)
    db.flush()
    if fields.get("value") is not None:
        set_value(db, h.holding_id, fields.get("as_of") or date.today(), fields["value"])  # type: ignore[arg-type]
    db.commit()
    return h


EDITABLE = (
    "name",
    "holding_class",
    "side",
    "target_amount",
    "installment",
    "full_price",
    "category_id",
    "recurring_template_id",
    "is_active",
    "notes",
)


def update_holding(db: Session, holding_id: int, changes: dict[str, object]) -> Holding:
    h = get_holding(db, holding_id)
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        clash = db.scalar(
            select(Holding).where(Holding.name == name, Holding.holding_id != holding_id)
        )
        if not name or clash:
            raise NetWorthError("Choose a name no other item has.", 409 if clash else 422)
        changes["name"] = name
    for key in EDITABLE:
        if key in changes:
            setattr(h, key, changes[key])
    h.side = side_of(h.holding_class, h.side)
    db.commit()
    return h


def delete_holding(db: Session, holding_id: int) -> None:
    h = get_holding(db, holding_id)
    for s in db.scalars(select(BalanceSnapshot).where(BalanceSnapshot.holding_id == holding_id)):
        db.delete(s)
    db.delete(h)
    db.commit()


def set_value(
    db: Session, holding_id: int, as_of: date, amount: Decimal, notes: str | None = None
) -> BalanceSnapshot:
    """The holding's value on a date, entered on the page; replaces one entered the same day."""
    h = get_holding(db, holding_id)
    if amount < 0:
        raise NetWorthError("Enter the value as a positive amount.")
    s = db.scalar(
        select(BalanceSnapshot).where(
            BalanceSnapshot.holding_id == holding_id,
            BalanceSnapshot.as_of == as_of,
            BalanceSnapshot.source == MANUAL,
        )
    )
    if s is None:
        s = BalanceSnapshot(
            as_of=as_of, name=h.name[:100], kind=h.side, source=MANUAL, holding_id=holding_id
        )
        db.add(s)
    s.amount = amount
    s.notes = (notes or "").strip()[:400] or None
    db.commit()
    return s


def delete_value(db: Session, snapshot_id: int) -> None:
    s = db.get(BalanceSnapshot, snapshot_id)
    if s is None or s.holding_id is None:
        raise NetWorthError(f"Value {snapshot_id} not found.", 404)
    db.delete(s)
    db.commit()


def template_names(db: Session) -> dict[int, str]:
    return {t.template_id: t.name for t in db.scalars(select(RecurringTemplate))}
