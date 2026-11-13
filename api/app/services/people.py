"""People and transfer notes (ADR-023).

A statement often says only "TRANSFERENCIA": who it went to and why are in the bank's email or in
Hernan's head. Two things put them back:

- **People** (core.counterparty): a name, texts to find in statement descriptions ("RUBEN
  MIRANDA; NAPOLES TRANSPORT") and a category (Transfers / Held for Others). A line whose
  description contains one of the texts gets the person and, unless someone chose its category by
  hand, the person's category.
- **Transfer notes** (core.transfer_note): a transfer told to the app (typed, or read from the
  bank's email): date, signed amount, optionally the account, the person, a category and the
  description typed at the bank. A note is matched to the statement line with the same amount,
  in the note's account when it has one, at most 5 days apart, closest date first; the line gets
  the person, the category (the note's, else the person's) and the description in its notes.

A person's balance (money held for them, or lent to them) is the personal-loan item linked to
them on Debt & Net Worth: its latest value plus their transfer lines after it (money received for
them raises it, money paid out for them lowers it).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.ingestion import transfer_email
from app.models import (
    FROM_BANKS,
    Account,
    BalanceSnapshot,
    Category,
    Counterparty,
    Holding,
    StgTransaction,
    Transaction,
    TransferNote,
)
from app.services import classify

WINDOW = timedelta(days=5)
ZERO = Decimal(0)
# Categories someone chose stay; everything else (a rule, a statement section) gives way to a
# person or a note, which say more about the line.
KEEP = ("manual", "suggestion", "split", "excel")


class PeopleError(Exception):
    """A change to a person that can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def patterns(person: Counterparty) -> list[str]:
    """The texts that identify a person's transfers, upper case."""
    return [p.strip().upper() for p in (person.patterns or "").split(";") if p.strip()]


def _free_lines() -> object:
    part = aliased(Transaction)
    return ~exists().where(part.parent_transaction_id == Transaction.transaction_id)


def _apply(
    db: Session,
    row: Transaction,
    person: Counterparty | None,
    category_id: int | None,
    source: str,
    reason: str,
    user: str,
) -> None:
    if person is not None and row.counterparty_id != person.counterparty_id:
        classify._log(
            db, row, "counterparty_id", row.counterparty_id, person.counterparty_id, reason, user
        )
        row.counterparty_id = person.counterparty_id
    if category_id is None or row.category_source in KEEP or row.category_id == category_id:
        return
    category = db.get(Category, category_id)
    if category is not None:
        classify.set_category(db, row, category, source, reason, user)


# ---------------------------------------------------------------- people
def tag_lines(db: Session, user: str, person: Counterparty | None = None) -> int:
    """Give statement lines without a person the person whose text their description contains.
    Returns how many lines got one."""
    people = (
        [person]
        if person is not None
        else list(db.scalars(select(Counterparty).where(Counterparty.is_active == True)))  # noqa: E712
    )
    texts = [(p, t) for p in people for t in patterns(p)]
    if not texts:
        return 0
    rows = db.scalars(
        select(Transaction).where(
            Transaction.source.in_(FROM_BANKS),
            Transaction.counterparty_id.is_(None),
            Transaction.parent_transaction_id.is_(None),
        )
    )
    count = 0
    for row in rows:
        text = row.description_raw.upper()
        hit = next((p for p, t in texts if t in text), None)
        if hit is None:
            continue
        _apply(db, row, hit, hit.category_id, "person", f"person: {hit.name}", user)
        count += 1
    db.commit()
    return count


def create_person(db: Session, fields: dict[str, object], user: str) -> Counterparty:
    """Add a person, optionally with a balance of their own on the balance sheet."""
    name = str(fields.get("name") or "").strip()
    if not name:
        raise PeopleError("Give the person a name.")
    if db.scalar(select(Counterparty).where(Counterparty.name == name)):
        raise PeopleError(f"{name} is already in the list.", 409)
    person = Counterparty(name=name[:100])
    _set(db, person, fields)
    db.add(person)
    db.flush()
    tag_lines(db, user, person)
    return person


def update_person(db: Session, person: Counterparty, fields: dict[str, object], user: str) -> None:
    """Change a person's details; names stay unique."""
    if "name" in fields:
        name = str(fields["name"] or "").strip()
        if not name:
            raise PeopleError("Give the person a name.")
        clash = db.scalar(
            select(Counterparty).where(
                Counterparty.name == name, Counterparty.counterparty_id != person.counterparty_id
            )
        )
        if clash is not None:
            raise PeopleError(f"{name} is already in the list.", 409)
        person.name = name[:100]
    _set(db, person, fields)
    db.flush()
    tag_lines(db, user, person)


def _set(db: Session, person: Counterparty, fields: dict[str, object]) -> None:  # noqa: C901 - baseline, docs/refactors.md #15
    if "patterns" in fields:
        texts = [t.strip() for t in str(fields["patterns"] or "").split(";") if t.strip()]
        if any(len(t) < 4 for t in texts):
            raise PeopleError("Each text to find needs at least 4 letters.")
        joined = "; ".join(texts)
        if len(joined) > 400:
            raise PeopleError("Keep the texts to find under 400 characters.")
        person.patterns = joined or None
    if "category_id" in fields:
        cid = fields["category_id"]
        if cid is not None and db.get(Category, cid) is None:
            raise PeopleError("Category not found.", 404)
        person.category_id = cid  # type: ignore[assignment]
    if "holding_id" in fields:
        hid = fields["holding_id"]
        if hid is not None:
            h = db.get(Holding, hid)
            if h is None:
                raise PeopleError("Debt & Net Worth item not found.", 404)
            if h.holding_class != "personal_loan":
                raise PeopleError("Link a personal loan item (money held for or owed by them).")
        person.holding_id = hid  # type: ignore[assignment]
    if "is_active" in fields:
        person.is_active = bool(fields["is_active"])
    if "notes" in fields:
        person.notes = (str(fields["notes"]).strip()[:400] or None) if fields["notes"] else None


def delete_person(db: Session, person: Counterparty) -> None:
    """Lines and notes keep their category; they only lose the name."""
    for note in db.scalars(
        select(TransferNote).where(TransferNote.counterparty_id == person.counterparty_id)
    ):
        note.counterparty_id = None
    for row in db.scalars(
        select(Transaction).where(Transaction.counterparty_id == person.counterparty_id)
    ):
        row.counterparty_id = None
    db.delete(person)
    db.commit()


@dataclass
class Totals:
    """What a person received and paid over a period."""

    lines: int
    received: Decimal
    paid: Decimal


def totals(db: Session) -> dict[int, Totals]:
    """For each person: how many lines, how much received and how much sent."""
    rows = db.execute(
        select(
            Transaction.counterparty_id,
            func.count(),
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
            func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)),
        )
        .where(Transaction.counterparty_id.is_not(None))
        .group_by(Transaction.counterparty_id)
    )
    return {cid: Totals(n, Decimal(str(r or 0)), Decimal(str(p or 0))) for cid, n, r, p in rows}


def balance_lines(db: Session, holding_id: int, after: date | None, until: date) -> Decimal:
    """The transfer lines of the people linked to a balance item, from the day after its latest
    value to `until`: money in (received for them) raises what is held, money out lowers it."""
    people = list(
        db.scalars(
            select(Counterparty.counterparty_id).where(Counterparty.holding_id == holding_id)
        )
    )
    if not people:
        return ZERO
    q = select(func.sum(Transaction.amount)).where(
        Transaction.counterparty_id.in_(people),
        Transaction.type == "transfer",
        Transaction.txn_date <= until,
        _free_lines(),  # type: ignore[arg-type]
    )
    if after is not None:
        q = q.where(Transaction.txn_date > after)
    total = db.scalar(q)
    return Decimal(str(total)) if total else ZERO


def linked_holdings(db: Session) -> set[int]:
    """The balance-sheet items that are a person's balance."""
    return set(
        db.scalars(select(Counterparty.holding_id).where(Counterparty.holding_id.is_not(None)))
    )


def new_balance_item(
    db: Session, person: Counterparty, opening: Decimal | None, as_of: date
) -> Holding:
    """Create "Holding for <name>" on Debt & Net Worth and link it, starting from `opening`."""
    name = f"Holding for {person.name}"[:100]
    if db.scalar(select(Holding).where(Holding.name == name)):
        raise PeopleError(f"{name} already exists on Debt & Net Worth: link it instead.", 409)
    h = Holding(name=name, side="liability", holding_class="personal_loan")
    db.add(h)
    db.flush()
    if opening is not None:
        db.add(
            BalanceSnapshot(
                holding_id=h.holding_id,
                name=name,
                kind="liability",
                as_of=as_of,
                amount=opening,
                source="manual",
            )
        )
    person.holding_id = h.holding_id
    return h


# ---------------------------------------------------------------- notes
def match_note(db: Session, note: TransferNote, user: str) -> Transaction | None:
    """Link a note to its statement line and pass on the person, category and description."""
    if note.transaction_id is not None:
        return db.get(Transaction, note.transaction_id)
    taken = select(TransferNote.transaction_id).where(TransferNote.transaction_id.is_not(None))
    q = select(Transaction).where(
        Transaction.source.in_(FROM_BANKS),
        Transaction.amount == note.amount,
        Transaction.txn_date >= note.txn_date - WINDOW,
        Transaction.txn_date <= note.txn_date + WINDOW,
        Transaction.parent_transaction_id.is_(None),
        Transaction.transaction_id.not_in(taken),
        _free_lines(),  # type: ignore[arg-type]
    )
    if note.account_id is not None:
        q = q.where(Transaction.account_id == note.account_id)
    candidates = list(db.scalars(q))
    if not candidates:
        return None
    row = min(candidates, key=lambda t: (abs((t.txn_date - note.txn_date).days), t.transaction_id))
    note.transaction_id = row.transaction_id
    person = db.get(Counterparty, note.counterparty_id) if note.counterparty_id else None
    category_id = note.category_id or (person.category_id if person else None)
    reason = f"transfer note {note.note_id}"
    if note.share and person and person.category_id and row.category_source not in KEEP:
        _split_share(db, row, note, person, user)
    else:
        _apply(db, row, person, category_id, "note", reason, user)
    text = " · ".join(x for x in (note.other_party, note.description) if x)
    if text and text not in (row.notes or ""):
        new = f"{row.notes} · {text}" if row.notes else text
        classify._log(db, row, "notes", row.notes, new[:1000], reason, user)
        row.notes = new[:1000]
    return row


def _split_share(
    db: Session, row: Transaction, note: TransferNote, person: Counterparty, user: str
) -> None:
    """A payment that is partly someone else's (Lopes pays Rubén's work and Hernan's together):
    the line becomes two parts, the person's share in their category and the rest in the
    note's."""
    sign = Decimal(1) if row.amount > 0 else Decimal(-1)
    theirs = sign * abs(note.share or ZERO)
    parts = [
        classify.Part(theirs, person.category_id or 0, f"{person.name}'s share"),
        classify.Part(row.amount - theirs, note.category_id or 0, None),
    ]
    made = classify.split(db, row, parts, user)
    made[0].counterparty_id = person.counterparty_id
    if row.counterparty_id != person.counterparty_id:
        classify._log(
            db, row, "counterparty_id", row.counterparty_id, person.counterparty_id, "note", user
        )
        row.counterparty_id = person.counterparty_id


def match_all(db: Session, user: str) -> int:
    """Match every open note; returns how many found their line."""
    notes = list(
        db.scalars(
            select(TransferNote)
            .where(TransferNote.transaction_id.is_(None))
            .order_by(TransferNote.txn_date, TransferNote.note_id)
        )
    )
    found = sum(1 for n in notes if match_note(db, n, user) is not None)
    db.commit()
    return found


def add_note(db: Session, fields: dict[str, object], user: str) -> tuple[TransferNote, bool]:  # noqa: C901 - baseline, docs/refactors.md #15
    """Save a note (once per bank reference) and match it. Returns (note, created)."""
    reference = fields.get("reference")
    if reference:
        same = db.scalar(select(TransferNote).where(TransferNote.reference == reference))
        if same is not None:
            return same, False
    amount = Decimal(str(fields["amount"]))
    if amount == 0:
        raise PeopleError("The amount can't be zero.")
    for key, model, what in (
        ("account_id", Account, "Account"),
        ("counterparty_id", Counterparty, "Person"),
        ("category_id", Category, "Category"),
    ):
        if fields.get(key) is not None and db.get(model, fields[key]) is None:
            raise PeopleError(f"{what} not found.", 404)
    share = fields.get("share")
    if share is not None:
        share = abs(Decimal(str(share)))
        person = (
            db.get(Counterparty, fields["counterparty_id"])
            if fields.get("counterparty_id")
            else None
        )
        if person is None or person.category_id is None:
            raise PeopleError("A share needs a person with a category (their part goes there).")
        if fields.get("category_id") is None:
            raise PeopleError("A share needs a category for the rest (your part).")
        if not 0 < share < abs(amount):
            raise PeopleError("The share must be more than 0 and less than the amount.")
    note = TransferNote(
        share=share,
        txn_date=fields["txn_date"],
        amount=amount,
        account_id=fields.get("account_id"),
        counterparty_id=fields.get("counterparty_id"),
        category_id=fields.get("category_id"),
        other_party=_text(fields.get("other_party"), 100),
        description=_text(fields.get("description"), 400),
        source=str(fields.get("source") or "manual"),
        reference=str(reference)[:64] if reference else None,
        created_by=user[:320],
    )
    if note.counterparty_id is None and note.other_party:
        note.counterparty_id = person_for(db, note.other_party)
    db.add(note)
    db.flush()
    match_note(db, note, user)
    db.commit()
    return note, True


def person_for(db: Session, text: str) -> int | None:
    """The person whose name or one of whose texts is in `text` (an email's "Enviada por")."""
    upper = text.upper()
    for p in db.scalars(select(Counterparty).where(Counterparty.is_active == True)):  # noqa: E712
        if p.name.upper() in upper or any(t in upper for t in patterns(p)):
            return p.counterparty_id
    return None


def _text(value: object, size: int) -> str | None:
    text = str(value or "").strip()
    return text[:size] or None


def unlink_note(db: Session, note: TransferNote) -> None:
    """Forget the match; the line keeps what it got (edit it on Transactions)."""
    note.transaction_id = None


def open_notes(db: Session, older_than: date) -> list[TransferNote]:
    """Notes still without a line whose day is before `older_than` (their statement is probably
    loaded): Data Status lists them."""
    return list(
        db.scalars(
            select(TransferNote)
            .where(TransferNote.transaction_id.is_(None), TransferNote.txn_date < older_than)
            .order_by(TransferNote.txn_date)
        )
    )


# ---------------------------------------------------------------- notes from the banks' emails
@dataclass
class EmailResult:
    """What sending a person's summary did."""

    status: str  # noted, matched, duplicate, skipped
    message: str
    note_id: int | None = None


def _our_account(db: Session, bank: str, last4: str | None) -> Account | None:
    accounts = [
        a
        for a in db.scalars(
            select(Account).where(Account.institution == bank, Account.is_active == True)  # noqa: E712
        )
        if a.kind != "credit_card"
    ]
    if last4 is not None:
        return next((a for a in accounts if a.last4 == last4), None)
    # Produbanco's "enviada" doesn't print the account: the email goes to Hernan, so his.
    mine = [a for a in accounts if a.owner == "Hernan"]
    return mine[0] if len(mine) == 1 else None


def note_from_email(
    db: Session, notice: transfer_email.Notice, sent_on: date, user: str
) -> EmailResult:
    """Turn a bank's transfer notice into a note (once per bank reference) and match it."""
    account = _our_account(db, notice.bank, notice.our_last4)
    if account is None:
        return EmailResult("skipped", "Not one of the household's accounts.")
    own = {a.last4 for a in db.scalars(select(Account).where(Account.last4.is_not(None)))}
    if notice.other_last4 is not None and notice.other_last4 in own:
        return EmailResult(
            "skipped", "Between the household's own accounts: matched as a transfer."
        )
    reference = f"{notice.bank}:{notice.reference}" if notice.reference else None
    amount = notice.amount if notice.direction == "received" else -notice.amount
    note, created = add_note(
        db,
        {
            "txn_date": notice.day or sent_on,
            "amount": amount,
            "account_id": account.account_id,
            "other_party": notice.other_party,
            "description": notice.description,
            "source": "email",
            "reference": reference,
        },
        user,
    )
    if not created:
        return EmailResult("duplicate", "Already noted.", note.note_id)
    who = note.other_party or "someone"
    if note.transaction_id is not None:
        return EmailResult("matched", f"Noted ({who}) and matched to its line.", note.note_id)
    return EmailResult(
        "noted", f"Noted ({who}); it will be matched when the statement is read.", note.note_id
    )


# ---------------------------------------------------------------- the import preview
@dataclass
class Hint:
    """What a note or a person will do to a waiting statement line once it's approved."""

    source: Literal["note", "person"]
    person: str | None
    category_id: int | None
    text: str | None  # the other party and the description, as they'll reach the line's notes
    share: Decimal | None
    note_id: int | None = None


def preview(db: Session, rows: list[StgTransaction]) -> dict[int, Hint]:
    """The same matching approval will do, on a statement still waiting: open notes first (same
    amount, the note's account, 5 days, closest), then people's texts. Keyed by stg_id."""
    people_by_id = {p.counterparty_id: p for p in db.scalars(select(Counterparty))}
    free = [r for r in rows if not r.is_duplicate]
    hints: dict[int, Hint] = {}
    notes = db.scalars(
        select(TransferNote)
        .where(TransferNote.transaction_id.is_(None))
        .order_by(TransferNote.txn_date, TransferNote.note_id)
    )
    for note in notes:
        candidates = [
            r
            for r in free
            if r.stg_id not in hints
            and r.amount == note.amount
            and abs((r.txn_date - note.txn_date).days) <= WINDOW.days
            and (note.account_id is None or r.account_id == note.account_id)
        ]
        if not candidates:
            continue
        row = min(candidates, key=lambda r: (abs((r.txn_date - note.txn_date).days), r.stg_id))
        person = people_by_id.get(note.counterparty_id) if note.counterparty_id else None
        text = " · ".join(x for x in (note.other_party, note.description) if x) or None
        hints[row.stg_id] = Hint(
            "note",
            person.name if person else None,
            note.category_id or (person.category_id if person else None),
            text,
            note.share if person and person.category_id else None,
            note.note_id,
        )
    texts = [(p, t) for p in people_by_id.values() if p.is_active for t in patterns(p)]
    for r in free:
        if r.stg_id in hints:
            continue
        upper = r.description_raw.upper()
        hit = next((p for p, t in texts if t in upper), None)
        if hit is not None:
            hints[r.stg_id] = Hint("person", hit.name, hit.category_id, None, None)
    return hints


def apply_preview(db: Session, rows: list[StgTransaction]) -> None:
    """Give waiting lines the category their note or person will give them, so the preview's
    totals show it. A shared payment keeps its own category until it's split at approval."""
    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    for stg_id, hint in preview(db, rows).items():
        row = next(r for r in rows if r.stg_id == stg_id)
        cat = cats.get(hint.category_id) if hint.category_id else None
        if cat is None or hint.share is not None:
            continue
        row.category_id, row.rule_id = cat.category_id, None
        row.category_source = hint.source
        row.type = classify.rule_type(cat.kind, accounts[row.account_id], row.amount)
