"""Transfers between the household's own accounts (F10, ADR-007).

A card payment or a move between own accounts shows up twice: money out of one account and money
into another. Matching links the two legs (transfer_group_id = the smaller transaction id), makes
both transfers and gives them "Transfers / Card Payment" when one side is a card, otherwise
"Transfers / Between Own Accounts". The spending view leaves transfers out; the cash view counts a
bank-to-card payment as cash leaving the household (mart.v_monthly_cash).

Two lines are paired only when all of these hold:
- opposite amounts of the same size, on two different accounts, at most 5 days apart;
- at least one of them is already a transfer (a card payment, an automatic transfer…);
- the other is a transfer too or still has no category. A category Hernan chose is never
  overridden, and lines already matched, split, or parts of a split are left alone.
When several lines qualify, the closest date wins, then the oldest line.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.models import Account, Category, ChangeLog, Transaction

WINDOW = timedelta(days=5)
CARD_PAYMENT = ("Transfers", "Card Payment")
OWN_ACCOUNTS = ("Transfers", "Between Own Accounts")


class TransferError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _category(db: Session, group: str, name: str) -> Category | None:
    parent = aliased(Category)
    return db.scalar(
        select(Category)
        .join(parent, parent.category_id == Category.parent_id)
        .where(parent.name == group, Category.name == name)
    )


def _candidates(db: Session) -> list[Transaction]:
    part = aliased(Transaction)
    has_parts = exists().where(part.parent_transaction_id == Transaction.transaction_id)
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.source == "statement",
                Transaction.account_id.is_not(None),
                Transaction.transfer_group_id.is_(None),
                Transaction.parent_transaction_id.is_(None),
                ~has_parts,
            )
            .order_by(Transaction.txn_date, Transaction.transaction_id)
        )
    )


def _may_pair(t: Transaction) -> bool:
    """A leg that matching may (re)classify: a transfer, or a line nobody categorized yet."""
    return t.type == "transfer" or t.category_id is None


def _log(db: Session, row: Transaction, column: str, old: object, new: object, user: str) -> None:
    if old != new:
        db.add(
            ChangeLog(
                table_name="core.transaction",
                row_id=row.transaction_id,
                column_name=column,
                old_value=None if old is None else str(old),
                new_value=None if new is None else str(new),
                reason="Matched transfer",
                changed_by=user,
            )
        )


@dataclass
class MatchResult:
    pairs: int


def match(db: Session, user: str = "system") -> MatchResult:
    """Pair every unmatched transfer leg with its other side, where one is loaded."""
    kinds = {a.account_id: a.kind for a in db.scalars(select(Account))}
    card = _category(db, *CARD_PAYMENT)
    own = _category(db, *OWN_ACCOUNTS)
    rows = [t for t in _candidates(db) if _may_pair(t)]
    taken: set[int] = set()
    pairs = 0
    for t in rows:
        if t.transaction_id in taken or t.type != "transfer":
            continue
        best: Transaction | None = None
        for o in rows:
            if (
                o.transaction_id in taken
                or o.transaction_id == t.transaction_id
                or o.account_id == t.account_id
                or o.amount != -t.amount
                or abs(o.txn_date - t.txn_date) > WINDOW
            ):
                continue
            if best is None or (abs(o.txn_date - t.txn_date), o.transaction_id) < (
                abs(best.txn_date - t.txn_date),
                best.transaction_id,
            ):
                best = o
        if best is None:
            continue
        group = min(t.transaction_id, best.transaction_id)
        is_card = "credit_card" in (kinds.get(t.account_id or 0), kinds.get(best.account_id or 0))
        target = card if is_card else own
        for leg in (t, best):
            _log(db, leg, "transfer_group_id", None, group, user)
            _log(db, leg, "type", leg.type, "transfer", user)
            leg.transfer_group_id = group
            leg.type = "transfer"
            leg.status = "matched"
            if target is not None and leg.category_id != target.category_id:
                _log(db, leg, "category_id", leg.category_id, target.category_id, user)
                leg.category_id = target.category_id
                leg.category_source = "match"
                leg.is_fixed = False
        taken |= {t.transaction_id, best.transaction_id}
        pairs += 1
    db.commit()
    return MatchResult(pairs)


def unlink(db: Session, group: int, user: str) -> int:
    """Separate a wrongly matched pair. Both lines keep their category (edit it if needed)."""
    legs = list(db.scalars(select(Transaction).where(Transaction.transfer_group_id == group)))
    if not legs:
        raise TransferError(f"Transfer {group} not found.", 404)
    for leg in legs:
        _log(db, leg, "transfer_group_id", group, None, user)
        leg.transfer_group_id = None
        leg.status = "confirmed"
    db.commit()
    return len(legs)


@dataclass
class Leg:
    transaction_id: int
    txn_date: date
    amount: object
    description: str
    account_id: int | None
    account_name: str | None
    account_kind: str | None


def other_legs(db: Session, rows: list[Transaction]) -> dict[int, Leg]:
    """For each matched line, the other side of its transfer."""
    groups = {t.transfer_group_id for t in rows if t.transfer_group_id is not None}
    if not groups:
        return {}
    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    legs = list(db.scalars(select(Transaction).where(Transaction.transfer_group_id.in_(groups))))
    out: dict[int, Leg] = {}
    for t in rows:
        if t.transfer_group_id is None:
            continue
        for o in legs:
            if o.transfer_group_id == t.transfer_group_id and o.transaction_id != t.transaction_id:
                a = accounts.get(o.account_id) if o.account_id else None
                out[t.transaction_id] = Leg(
                    o.transaction_id,
                    o.txn_date,
                    o.amount,
                    o.description_raw,
                    o.account_id,
                    a.name if a else None,
                    a.kind if a else None,
                )
    return out


def unmatched(db: Session, month: date | None = None) -> list[Transaction]:
    """Transfers whose other side isn't loaded (or doesn't fit): usually a statement to upload."""
    q = select(Transaction).where(
        Transaction.source == "statement",
        Transaction.type == "transfer",
        Transaction.transfer_group_id.is_(None),
        Transaction.parent_transaction_id.is_(None),
    )
    if month:
        q = q.where(Transaction.cash_month == month.replace(day=1))
    return list(db.scalars(q.order_by(Transaction.txn_date, Transaction.transaction_id)))
