"""People and transfer notes (ADR-023): who a transfer's money belongs to, and transfers told to
the app before their statement arrives."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.preview import category_paths
from app.models import Account, Counterparty, Holding, Transaction, TransferNote
from app.services import people, transfers

router = APIRouter(prefix="/api", tags=["people"])
DB = Annotated[Session, Depends(get_session)]


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _fail(db: Session, exc: people.PeopleError) -> HTTPException:
    db.rollback()
    return HTTPException(exc.status, str(exc))


# ---------------------------------------------------------------- people
class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    patterns: str | None = Field(default=None, max_length=400)
    category_id: int | None = None
    holding_id: int | None = None
    notes: str | None = Field(default=None, max_length=400)
    # Instead of holding_id: create "Holding for <name>" on Debt & Net Worth, starting here.
    new_balance: bool = False
    opening_balance: Decimal | None = None
    opening_as_of: date | None = None


class PersonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    patterns: str | None = Field(default=None, max_length=400)
    category_id: int | None = None
    holding_id: int | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=400)


class PersonOut(BaseModel):
    counterparty_id: int
    name: str
    patterns: str | None
    category_id: int | None
    category_path: str | None
    holding_id: int | None
    holding_name: str | None
    is_active: bool
    notes: str | None
    lines: int
    received: Decimal
    paid: Decimal


def _person_out(db: Session, p: Counterparty, totals: dict[int, people.Totals]) -> PersonOut:
    t = totals.get(p.counterparty_id, people.Totals(0, Decimal(0), Decimal(0)))
    h = db.get(Holding, p.holding_id) if p.holding_id else None
    return PersonOut(
        counterparty_id=p.counterparty_id,
        name=p.name,
        patterns=p.patterns,
        category_id=p.category_id,
        category_path=category_paths(db).get(p.category_id) if p.category_id else None,
        holding_id=p.holding_id,
        holding_name=h.name if h else None,
        is_active=p.is_active,
        notes=p.notes,
        lines=t.lines,
        received=t.received,
        paid=t.paid,
    )


def _person(db: Session, counterparty_id: int) -> Counterparty:
    p = db.get(Counterparty, counterparty_id)
    if p is None:
        raise HTTPException(404, f"Person {counterparty_id} not found.")
    return p


@router.get("/people", response_model=list[PersonOut])
def list_people(db: DB) -> list[PersonOut]:
    totals = people.totals(db)
    rows = db.scalars(
        select(Counterparty).order_by(Counterparty.is_active.desc(), Counterparty.name)
    )
    return [_person_out(db, p, totals) for p in rows]


@router.post("/people", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(body: PersonIn, db: DB, request: Request) -> PersonOut:
    fields = body.model_dump(exclude={"new_balance", "opening_balance", "opening_as_of"})
    if body.new_balance:
        fields.pop("holding_id", None)
    try:
        p = people.create_person(db, fields, _user(request))
        if body.new_balance:
            people.new_balance_item(db, p, body.opening_balance, body.opening_as_of or date.today())
        db.commit()
        transfers.match(db, _user(request))
    except people.PeopleError as exc:
        raise _fail(db, exc) from exc
    return _person_out(db, p, people.totals(db))


@router.patch("/people/{counterparty_id}", response_model=PersonOut)
def update_person(counterparty_id: int, body: PersonPatch, db: DB, request: Request) -> PersonOut:
    p = _person(db, counterparty_id)
    try:
        people.update_person(db, p, body.model_dump(exclude_unset=True), _user(request))
        db.commit()
        transfers.match(db, _user(request))  # an exchanger's lines pair with their other side
    except people.PeopleError as exc:
        raise _fail(db, exc) from exc
    return _person_out(db, p, people.totals(db))


@router.delete("/people/{counterparty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(counterparty_id: int, db: DB) -> Response:
    people.delete_person(db, _person(db, counterparty_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PersonLineOut(BaseModel):
    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None
    category_path: str | None
    notes: str | None


@router.get("/people/{counterparty_id}/lines", response_model=list[PersonLineOut])
def person_lines(counterparty_id: int, db: DB) -> list[PersonLineOut]:
    _person(db, counterparty_id)
    names = {a.account_id: a.name for a in db.scalars(select(Account))}
    paths = category_paths(db)
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.counterparty_id == counterparty_id)
        .order_by(Transaction.txn_date.desc(), Transaction.transaction_id.desc())
    )
    return [
        PersonLineOut(
            transaction_id=t.transaction_id,
            txn_date=t.txn_date,
            amount=t.amount,
            description=t.description_raw,
            account_name=names.get(t.account_id) if t.account_id else None,
            category_path=paths.get(t.category_id) if t.category_id else None,
            notes=t.notes,
        )
        for t in rows
    ]


# ---------------------------------------------------------------- transfer notes
class NoteIn(BaseModel):
    txn_date: date
    direction: Literal["sent", "received"]
    amount: Decimal = Field(gt=0, description="Positive; direction says which way it went")
    account_id: int | None = None
    counterparty_id: int | None = None
    category_id: int | None = None
    other_party: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=400)
    # The person's part of a shared payment: their category; the rest goes to category_id.
    share: Decimal | None = Field(default=None, gt=0)


class NoteOut(BaseModel):
    note_id: int
    txn_date: date
    amount: Decimal
    account_id: int | None
    account_name: str | None
    counterparty_id: int | None
    person: str | None
    category_id: int | None
    category_path: str | None
    other_party: str | None
    description: str | None
    share: Decimal | None
    source: str
    transaction_id: int | None
    line_date: date | None
    line_description: str | None
    created_by: str


def _note_out(db: Session, n: TransferNote) -> NoteOut:
    account = db.get(Account, n.account_id) if n.account_id else None
    person = db.get(Counterparty, n.counterparty_id) if n.counterparty_id else None
    line = db.get(Transaction, n.transaction_id) if n.transaction_id else None
    return NoteOut(
        note_id=n.note_id,
        txn_date=n.txn_date,
        amount=n.amount,
        account_id=n.account_id,
        account_name=account.name if account else None,
        counterparty_id=n.counterparty_id,
        person=person.name if person else None,
        category_id=n.category_id,
        category_path=category_paths(db).get(n.category_id) if n.category_id else None,
        other_party=n.other_party,
        description=n.description,
        share=n.share,
        source=n.source,
        transaction_id=n.transaction_id,
        line_date=line.txn_date if line else None,
        line_description=line.description_raw if line else None,
        created_by=n.created_by,
    )


def _note(db: Session, note_id: int) -> TransferNote:
    n = db.get(TransferNote, note_id)
    if n is None:
        raise HTTPException(404, f"Note {note_id} not found.")
    return n


@router.get("/transfer-notes", response_model=list[NoteOut])
def list_notes(
    db: DB,
    state: Annotated[Literal["open", "matched", "all"], Query()] = "all",
    days: Annotated[int, Query(ge=1, le=3660)] = 120,
) -> list[NoteOut]:
    q = select(TransferNote).where(TransferNote.txn_date >= date.today() - timedelta(days=days))
    if state == "open":
        q = q.where(TransferNote.transaction_id.is_(None))
    elif state == "matched":
        q = q.where(TransferNote.transaction_id.is_not(None))
    rows = db.scalars(q.order_by(TransferNote.txn_date.desc(), TransferNote.note_id.desc()))
    return [_note_out(db, n) for n in rows]


@router.post("/transfer-notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def add_note(body: NoteIn, db: DB, request: Request) -> NoteOut:
    fields = body.model_dump(exclude={"direction", "amount"})
    fields["amount"] = body.amount if body.direction == "received" else -body.amount
    try:
        note, _ = people.add_note(db, fields, _user(request))
    except people.PeopleError as exc:
        raise _fail(db, exc) from exc
    return _note_out(db, note)


@router.delete("/transfer-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, db: DB) -> Response:
    """The matched line keeps what the note gave it; edit it on Transactions."""
    db.delete(_note(db, note_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class MatchedOut(BaseModel):
    matched: int
    tagged: int


@router.post("/transfer-notes/match", response_model=MatchedOut)
def match_notes(db: DB, request: Request) -> MatchedOut:
    """Match open notes and tag lines with people (also runs after each approved statement)."""
    user = _user(request)
    return MatchedOut(matched=people.match_all(db, user), tagged=people.tag_lines(db, user))
