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

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.models import FROM_BANKS, Account, AppSetting, Category, ChangeLog, Transaction
from app.services import rules as rule_engine

WINDOW = timedelta(days=5)
# Between countries (an exchange through people, ADR-055) the other side can take longer.
ABROAD = timedelta(days=10)
CARD_PAYMENT = ("Transfers", "Card Payment")
OWN_ACCOUNTS = ("Transfers", "Between Own Accounts")
EXCHANGE = ("Transfers", "Exchange through people")


class TransferError(Exception):
    """A transfer change that can't be done; `status` is the HTTP status."""

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
                Transaction.source.in_(FROM_BANKS),
                Transaction.account_id.is_not(None),
                Transaction.transfer_group_id.is_(None),
                Transaction.parent_transaction_id.is_(None),
                ~has_parts,
            )
            .order_by(Transaction.txn_date, Transaction.transaction_id)
        )
    )


def _may_pair(t: Transaction, paired: list[int], exchange: int | None = None) -> bool:
    """A leg that matching may (re)classify: a transfer between own accounts (or one without a
    category), or a line nobody categorized yet. Money held for someone or lent, and lines that
    belong to a person (ADR-023), stay what they are: received for Rubén and paid out for him the
    same week look like two legs, but they aren't."""
    if t.counterparty_id is not None:
        # A person who exchanges money (ADR-055) is a leg like any own-account move.
        return exchange is not None and t.category_id == exchange
    if t.type == "transfer":
        return t.category_id is None or t.category_id in paired
    return t.category_id is None


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
    """What matching did: pairs linked and card payments settled."""

    pairs: int
    settled: int = 0  # settled on their own, where a person said the other side is (ADR-080)


def match(db: Session, user: str = "system") -> MatchResult:
    """Pair every unmatched transfer leg with its other side, where one is loaded."""
    accounts = list(db.scalars(select(Account)))
    kinds = {a.account_id: a.kind for a in accounts}
    countries = {a.account_id: a.country for a in accounts}
    card = _category(db, *CARD_PAYMENT)
    own = _category(db, *OWN_ACCOUNTS)
    swap = _category(db, *EXCHANGE)
    swap_id = swap.category_id if swap else None
    paired = _paired_categories(db)
    rows = [t for t in _candidates(db) if _may_pair(t, paired, swap_id)]
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
                or abs(o.txn_date - t.txn_date)
                > (
                    ABROAD
                    if countries.get(o.account_id or 0) != countries.get(t.account_id or 0)
                    else WINDOW
                )
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
        is_swap = swap_id is not None and swap_id in (t.category_id, best.category_id)
        target = swap if is_swap else card if is_card else own
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
    return MatchResult(pairs, _settle_learned(db, user))


def one_sided(db: Session, transaction_id: int, user: str) -> Transaction:
    """The other side is an account the app doesn't follow (ADR-058): the line is settled on its
    own, as a group of one, so it stops asking for a pair. Unlinking the group asks again."""
    t = db.get(Transaction, transaction_id)
    if t is None:
        raise TransferError(f"Line {transaction_id} not found.", 404)
    if t.transfer_group_id is not None:
        raise TransferError("This line is already paired.", 409)
    if t.type != "transfer":
        _log(db, t, "type", t.type, "transfer", user)
        t.type = "transfer"
    _log(db, t, "transfer_group_id", None, t.transaction_id, user)
    t.transfer_group_id = t.transaction_id
    t.status = "confirmed"
    db.commit()
    return t


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
    """One side of a transfer."""

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


def _paired_categories(db: Session) -> list[int]:
    """Transfer categories whose other leg is in another of the household's accounts: card
    payments, moves between own accounts and the Transfers group itself. Money held for others
    or lent out has no such leg."""
    found = (_category(db, *CARD_PAYMENT), _category(db, *OWN_ACCOUNTS), _category(db, *EXCHANGE))
    ids = [c.category_id for c in found if c]
    group = db.scalar(
        select(Category.category_id).where(
            Category.parent_id.is_(None), Category.name == CARD_PAYMENT[0]
        )
    )
    return ids + ([group] if group is not None else [])


def unmatched(db: Session, month: date | None = None) -> list[Transaction]:
    """Transfers whose other side isn't loaded (or doesn't fit): usually a statement to upload."""
    paired = _paired_categories(db)
    q = select(Transaction).where(
        Transaction.source.in_(FROM_BANKS),
        Transaction.type == "transfer",
        Transaction.transfer_group_id.is_(None),
        Transaction.parent_transaction_id.is_(None),
        Transaction.category_id.is_(None) | Transaction.category_id.in_(paired),
    )
    if month:
        q = q.where(Transaction.cash_month == month.replace(day=1))
    return list(db.scalars(q.order_by(Transaction.txn_date, Transaction.transaction_id)))


# --- Settling transfers by hand (ADR-075) ---

PLACES = ("Lauren's flexible savings", "Wise", "Money exchanger", "Cash", "Someone else")
CANDIDATES = 4
NEAR = timedelta(days=7)  # a person looks a little wider than automatic matching

# --- Smarter pairing (ADR-080) ---
# A transfer can arrive smaller than it left: the bank on the way kept a fee. The other side is
# offered when the two amounts differ by no more than this, and by no more than FEE_SHARE of it.
FEE_HOME = Decimal("1.00")  # between two accounts in one country
FEE_ABROAD = Decimal("50.00")  # a wire between countries
FEE_SHARE = Decimal("0.05")
FEES = ("Financial Costs", "Bank Fees")
PLACE_KEY = "transfer-place:"  # + a hash of the text and amount: where a person said it goes


def _fee_cap(amount: Decimal, abroad: bool) -> Decimal:
    return min(FEE_ABROAD if abroad else FEE_HOME, abs(amount) * FEE_SHARE)


def _place_key(t: Transaction) -> str:
    amount = abs(Decimal(t.amount)).quantize(Decimal("0.01"))  # 300.00 and 300.0000 are one
    text = f"{rule_engine.key(t.description_raw or '')}|{amount}"
    return PLACE_KEY + hashlib.sha1(text.encode()).hexdigest()[:30]


def _settle_learned(db: Session, user: str) -> int:
    """Transfers a person already explained once: a line with the same text and amount as one
    settled "the other side is ..." gets the same answer, once its real other side has had time
    to arrive (ABROAD days) and didn't."""
    places = {
        r.setting_key: r.setting_value
        for r in db.scalars(select(AppSetting).where(AppSetting.setting_key.like(f"{PLACE_KEY}%")))
    }
    if not places:
        return 0
    done = 0
    for t in unmatched(db):
        place = places.get(_place_key(t))
        if place is None or t.txn_date > date.today() - ABROAD:
            continue
        one_sided(db, t.transaction_id, user)
        if not t.notes:
            note = f"Other side: {place} (as you said before)"
            _log(db, t, "notes", None, note, user)
            t.notes = note
        done += 1
    db.commit()
    return done


@dataclass
class Candidate:
    """A line that could be a transfer's other side."""

    transaction_id: int
    txn_date: date
    amount: object
    description: str
    account_name: str | None
    days: int
    difference: object = 0  # how much less arrived than left: a fee on the way (ADR-080)


@dataclass
class Unsettled:
    """A transfer with no other side yet."""

    transaction_id: int
    txn_date: date
    amount: object
    description: str
    account_name: str | None
    category_id: int | None
    statement_file_id: int | None
    candidates: list[Candidate]


@dataclass
class Bunch:
    """Unsettled lines that look alike (the same text and amount): one answer can settle them."""

    key: str
    description: str
    amount: object
    lines: list[Unsettled]


def workbench(db: Session, since: date | None = None) -> list[Bunch]:
    """Every transfer still missing its other side, newest first, bunched by text and amount,
    each with the lines that could be its other side (opposite amount, another account, near in
    time, not paired yet)."""
    names = {a.account_id: a.name for a in db.scalars(select(Account))}
    countries = {a.account_id: a.country for a in db.scalars(select(Account))}
    rows = [t for t in unmatched(db) if since is None or t.txn_date >= since]
    if not rows:
        return []
    lo = min(t.txn_date for t in rows) - ABROAD
    hi = max(t.txn_date for t in rows) + ABROAD
    pool = list(
        db.scalars(
            select(Transaction).where(
                Transaction.transfer_group_id.is_(None),
                Transaction.parent_transaction_id.is_(None),
                Transaction.txn_date >= lo,
                Transaction.txn_date <= hi,
                Transaction.source.in_(FROM_BANKS),
            )
        )
    )
    by_amount: dict[object, list[Transaction]] = {}
    for o in pool:
        by_amount.setdefault(o.amount, []).append(o)
    bunches: dict[str, Bunch] = {}
    for t in sorted(rows, key=lambda r: (r.txn_date, r.transaction_id), reverse=True):

        def near(o: Transaction, t: Transaction = t) -> bool:
            abroad = countries.get(o.account_id or 0) != countries.get(t.account_id or 0)
            return abs(o.txn_date - t.txn_date) <= (ABROAD if abroad else NEAR)

        cands = sorted(
            (o for o in by_amount.get(-t.amount, []) if o.account_id != t.account_id and near(o)),
            key=lambda o: (abs(o.txn_date - t.txn_date), o.transaction_id),
        )[:CANDIDATES]
        if not cands:  # nothing of the exact amount: one that differs by a fee (ADR-080)

            def by_fee(o: Transaction, t: Transaction = t) -> bool:
                abroad = countries.get(o.account_id or 0) != countries.get(t.account_id or 0)
                gap = abs(abs(o.amount) - abs(t.amount))
                return (
                    o.account_id != t.account_id
                    and (o.amount > 0) != (t.amount > 0)
                    and 0 < gap <= _fee_cap(max(abs(o.amount), abs(t.amount)), abroad)
                    and near(o)
                )

            cands = sorted(
                (o for o in pool if by_fee(o)),
                key=lambda o: (abs(abs(o.amount) - abs(t.amount)), abs(o.txn_date - t.txn_date)),
            )[:CANDIDATES]
        u = Unsettled(
            t.transaction_id,
            t.txn_date,
            t.amount,
            t.description_raw,
            names.get(t.account_id or 0),
            t.category_id,
            t.statement_file_id,
            [
                Candidate(
                    o.transaction_id,
                    o.txn_date,
                    o.amount,
                    o.description_raw,
                    names.get(o.account_id or 0),
                    abs((o.txn_date - t.txn_date).days),
                    abs(abs(o.amount) - abs(t.amount)),
                )
                for o in cands
            ],
        )
        key = f"{rule_engine.key(t.description_raw)}|{abs(t.amount)}"
        b = bunches.get(key)
        if b is None:
            b = bunches[key] = Bunch(key, t.description_raw, abs(t.amount), [])
        b.lines.append(u)
    return list(bunches.values())


def pair(db: Session, a_id: int, b_id: int, user: str) -> int:
    """Pair two lines a person says are the two sides of one transfer."""
    a, b = db.get(Transaction, a_id), db.get(Transaction, b_id)
    if a is None or b is None:
        raise TransferError("Line not found.", 404)
    if a.account_id == b.account_id:
        raise TransferError("Both lines are in the same account.", 422)
    if (a.amount > 0) == (b.amount > 0):
        raise TransferError("One line must be money out and the other money in.", 422)
    if a.transfer_group_id is not None or b.transfer_group_id is not None:
        raise TransferError("One of the lines is already paired: unlink it first.", 409)
    accounts = list(db.scalars(select(Account)))
    kinds = {x.account_id: x.kind for x in accounts}
    countries = {x.account_id: x.country for x in accounts}
    is_card = "credit_card" in (kinds.get(a.account_id or 0), kinds.get(b.account_id or 0))
    target = _category(db, *(CARD_PAYMENT if is_card else OWN_ACCOUNTS))
    group = min(a.transaction_id, b.transaction_id)
    legs = [a, b]
    # Less arrived than left, by what a bank keeps on the way: the difference is a bank fee
    # (ADR-080). The line that left is split into the transfer and the fee, so the fee counts.
    sent, got = (a, b) if a.amount < 0 else (b, a)
    fee = abs(sent.amount) - abs(got.amount)
    abroad = countries.get(a.account_id or 0) != countries.get(b.account_id or 0)
    fees = _category(db, *FEES)
    if target and fees and 0 < fee <= _fee_cap(sent.amount, abroad):
        from app.services import classify  # classify imports this module: each needs the other

        parts = classify.split(
            db,
            sent,
            [
                classify.Part(-abs(got.amount), target.category_id, None),
                classify.Part(-fee, fees.category_id, "Kept on the way by the bank"),
            ],
            user,
        )
        legs.append(parts[0])
    for leg in legs:
        _log(db, leg, "transfer_group_id", None, group, user)
        if leg.type != "transfer":
            _log(db, leg, "type", leg.type, "transfer", user)
            leg.type = "transfer"
        leg.transfer_group_id = group
        leg.status = "matched"
        if target is not None and leg.category_id != target.category_id:
            _log(db, leg, "category_id", leg.category_id, target.category_id, user)
            leg.category_id = target.category_id
            leg.category_source = "manual"
    db.commit()
    return group


def settle_outside(db: Session, ids: list[int], place: str, user: str) -> int:
    """The other side is somewhere the app doesn't follow (a named place): each line is settled
    on its own and says where."""
    done = 0
    for i in ids:
        t = db.get(Transaction, i)
        if t is None or t.transfer_group_id is not None:
            continue
        one_sided(db, i, user)
        key = _place_key(t)  # the next line like this one is settled the same way (ADR-080)
        known = db.get(AppSetting, key)
        if known is None:
            db.add(AppSetting(setting_key=key, setting_value=place[:200], updated_by=user[:200]))
            db.flush()  # lines of one bunch share the key
        else:
            known.setting_value, known.updated_by = place[:200], user[:200]
        note = f"Other side: {place}"[:1000]
        if not t.notes:
            _log(db, t, "notes", None, note, user)
            t.notes = note
        done += 1
    db.commit()
    return done
