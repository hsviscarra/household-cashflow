"""Classification (F9): the review queue, categorizing a merchant (and saving a rule), Claude's
suggestions, editing a line, splits and each line's change history."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.preview import category_paths
from app.ingestion.storage import StatementStore, get_store
from app.models import Account, Category, ImportBatch, StgTransaction, Transaction
from app.schemas import (
    AcceptedOut,
    ChangeOut,
    LineSourceOut,
    ResolveIn,
    ResolveOut,
    ReviewGroupOut,
    ReviewLineOut,
    ReviewOut,
    SimilarOut,
    SourceTextOut,
    SplitIn,
    SuggestionOut,
    SuggestOut,
    TransactionOut,
    TransactionPatch,
    TransferLegOut,
)
from app.services import classify, inbox, line_source, recurring, transfers
from app.services import suggest as suggestions

router = APIRouter(prefix="/api", tags=["classification"])
DB = Annotated[Session, Depends(get_session)]
Month = Annotated[date | None, Query(description="Any day of the month; all months if left out")]
# "Likely" or better, as the Review page labels confidence (ADR-006).
HIGH = Decimal("0.8")


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _row(db: Session, transaction_id: int) -> Transaction:
    row = db.get(Transaction, transaction_id)
    if row is None:
        raise HTTPException(404, f"Transaction {transaction_id} not found.")
    return row


def transaction_out(
    t: Transaction,
    account_name: str | None,
    paths: dict[int, str],
    parts: int = 0,
    other: transfers.Leg | None = None,
) -> TransactionOut:
    return TransactionOut(
        transaction_id=t.transaction_id,
        txn_date=t.txn_date,
        post_date=t.post_date,
        cash_month=t.cash_month,
        account_id=t.account_id,
        account_name=account_name,
        description=t.description_raw,
        merchant=t.merchant,
        amount=t.amount,
        type=t.type,
        category_id=t.category_id,
        category_path=paths.get(t.category_id) if t.category_id else None,
        person=t.person,
        country=t.country,
        source=t.source,
        statement_file_id=t.statement_file_id,
        notes=t.notes,
        category_source=t.category_source,
        parent_transaction_id=t.parent_transaction_id,
        parts=parts,
        transfer_group_id=t.transfer_group_id,
        transfer_with=TransferLegOut(**vars(other)) if other else None,
        recurring_entry_id=t.recurring_entry_id,
        counterparty_id=t.counterparty_id,
    )


def _one_out(db: Session, t: Transaction) -> TransactionOut:
    name = db.scalar(select(Account.name).where(Account.account_id == t.account_id))
    parts = classify.part_counts(db, [t.transaction_id]).get(t.transaction_id, 0)
    other = transfers.other_legs(db, [t]).get(t.transaction_id)
    return transaction_out(t, name, category_paths(db), parts, other)


def _fail(exc: classify.ClassifyError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


# ---------------- review queue ----------------
@router.get("/review", response_model=ReviewOut)
def review(
    db: DB,
    month: Annotated[
        date | None, Query(description="Any day of the month; all months if left out")
    ] = None,
) -> ReviewOut:
    return _review_out(db, classify.review_groups(db, month), month)


def _review_out(db: Session, groups: list[classify.ReviewGroup], month: date | None) -> ReviewOut:
    paths = category_paths(db)
    return ReviewOut(
        month=month.replace(day=1) if month else None,
        groups=[
            ReviewGroupOut(
                merchant_key=g.merchant_key,
                lines=[ReviewLineOut(**vars(ln)) for ln in g.lines],
                total=g.total,
                suggestion=(
                    SuggestionOut(
                        category_id=g.suggestion.category_id,
                        category_path=paths.get(g.suggestion.category_id, "?"),
                        confidence=g.suggestion.confidence,
                        reason=g.suggestion.reason,
                        model=g.suggestion.model,
                    )
                    if g.suggestion
                    else None
                ),
            )
            for g in groups
        ],
        uncategorized_lines=sum(len(g.lines) for g in groups),
        suggestions_available=suggestions.available(),
    )


@router.post("/review/resolve", response_model=ResolveOut)
def resolve(body: ResolveIn, db: DB, request: Request) -> ResolveOut:
    try:
        done = classify.resolve(
            db,
            body.merchant_key,
            body.category_id,
            _user(request),
            transaction_ids=body.transaction_ids,
            save_rule=body.save_rule,
            pattern=body.pattern,
            match_type=body.match_type,
            amount_min=body.amount_min,
            amount_max=body.amount_max,
            from_suggestion=body.from_suggestion,
        )
    except classify.ClassifyError as exc:
        db.rollback()
        raise _fail(exc) from exc
    return ResolveOut(
        categorized=done.categorized,
        rule_id=done.rule_id,
        also_by_rule=done.also_by_rule,
        waiting_by_rule=done.waiting_by_rule,
    )


@router.post("/review/suggest", response_model=SuggestOut)
def suggest(
    db: DB,
    month: Annotated[
        date | None, Query(description="Any day of the month; all months if left out")
    ] = None,
) -> SuggestOut:
    """Ask Claude about this month's merchants that have no suggestion yet (ADR-006)."""
    from app.config import get_settings

    try:
        asked, stored = suggestions.suggest(db, month)
    except suggestions.SuggestError as exc:
        db.rollback()
        raise HTTPException(exc.status, str(exc)) from exc
    return SuggestOut(asked=asked, suggested=stored, model=get_settings().anthropic_model)


# ---------------- one line ----------------
@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def edit_transaction(
    transaction_id: int, body: TransactionPatch, db: DB, request: Request
) -> TransactionOut:
    row = _row(db, transaction_id)
    fields = body.model_fields_set
    try:
        classify.edit(
            db,
            row,
            _user(request),
            category_id=body.category_id,
            notes=body.notes,
            person=body.person,
            counterparty_id=body.counterparty_id,
            fields=fields,
        )
    except classify.ClassifyError as exc:
        db.rollback()
        raise _fail(exc) from exc
    if "category_id" in fields:
        recurring.recategorized(db, row, _user(request))
    return _one_out(db, row)


@router.put("/transactions/{transaction_id}/split", response_model=list[TransactionOut])
def split_transaction(
    transaction_id: int, body: SplitIn, db: DB, request: Request
) -> list[TransactionOut]:
    row = _row(db, transaction_id)
    parts = [classify.Part(p.amount, p.category_id, p.notes) for p in body.parts]
    try:
        made = classify.split(db, row, parts, _user(request))
    except classify.ClassifyError as exc:
        db.rollback()
        raise _fail(exc) from exc
    return [_one_out(db, p) for p in made]


@router.delete("/transactions/{transaction_id}/split", status_code=status.HTTP_204_NO_CONTENT)
def remove_split(transaction_id: int, db: DB, request: Request) -> Response:
    row = _row(db, transaction_id)
    if not classify.unsplit(db, row, _user(request)):
        raise HTTPException(404, "This line isn't split.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


Store = Annotated[StatementStore, Depends(get_store)]


def _source_out(db: Session, src: line_source.Source) -> LineSourceOut:
    paths = category_paths(db)
    data = vars(src) | {
        "around": [SourceTextOut(**vars(t)) for t in src.around],
        "similar": [
            SimilarOut(
                **vars(x),
                category_path=paths.get(x.category_id) if x.category_id else None,
            )
            for x in src.similar
        ],
    }
    return LineSourceOut(**data)


@router.get("/transactions/{transaction_id}/source", response_model=LineSourceOut)
def transaction_source(transaction_id: int, db: DB, store: Store) -> LineSourceOut:
    """Everything the statement says about a line, the text around it and earlier lines of the
    same merchant (ADR-034)."""
    return _source_out(db, line_source.of_transaction(db, store, _row(db, transaction_id)))


@router.get("/batches/{batch_id}/lines/{stg_id}/source", response_model=LineSourceOut)
def staged_source(batch_id: int, stg_id: int, db: DB, store: Store) -> LineSourceOut:
    row = db.get(StgTransaction, stg_id)
    if row is None or row.batch_id != batch_id:
        raise HTTPException(404, f"Line {stg_id} not found in this statement.")
    return _source_out(db, line_source.of_staged(db, store, row))


@router.get("/transactions/{transaction_id}/history", response_model=list[ChangeOut])
def transaction_history(transaction_id: int, db: DB) -> list[ChangeOut]:
    return [ChangeOut.model_validate(c) for c in classify.history(db, _row(db, transaction_id))]


# ---------------- F23: accepting Claude's suggestions in one click ----------------
MinConfidence = Annotated[
    Decimal, Query(ge=0, le=1, description="Accept suggestions at least this sure (0 to 1)")
]


@router.post("/review/accept-suggestions", response_model=AcceptedOut)
def accept_suggestions(
    db: DB, request: Request, month: Month = None, min_confidence: MinConfidence = HIGH
) -> AcceptedOut:
    done = classify.accept_suggestions(
        db, _user(request), min_confidence=min_confidence, month=month
    )
    return AcceptedOut(**vars(done))


# ---------------- F23: categorizing a statement before it is approved ----------------
def _waiting(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404, f"Import {batch_id} not found.")
    return batch


@router.get("/batches/{batch_id}/review", response_model=ReviewOut)
def batch_review(batch_id: int, db: DB) -> ReviewOut:
    """The statement's uncategorized lines grouped by merchant, like the Review page."""
    _waiting(db, batch_id)
    return _review_out(db, classify.batch_groups(db, batch_id), None)


@router.post("/batches/{batch_id}/resolve", response_model=ResolveOut)
def batch_resolve(batch_id: int, body: ResolveIn, db: DB, request: Request) -> ResolveOut:
    try:
        done = classify.resolve_staged(
            db,
            batch_id,
            body.merchant_key,
            body.category_id,
            _user(request),
            stg_ids=body.transaction_ids,  # on a statement's page, the staged lines' ids
            save_rule=body.save_rule,
            pattern=body.pattern,
            match_type=body.match_type,
            amount_min=body.amount_min,
            amount_max=body.amount_max,
            from_suggestion=body.from_suggestion,
        )
    except classify.ClassifyError as exc:
        db.rollback()
        raise _fail(exc) from exc
    return ResolveOut(
        categorized=done.categorized,
        rule_id=done.rule_id,
        also_by_rule=done.also_by_rule,
        waiting_by_rule=done.waiting_by_rule,
    )


@router.post("/batches/{batch_id}/suggest", response_model=SuggestOut)
def batch_suggest(batch_id: int, db: DB) -> SuggestOut:
    """Ask Claude about this statement's merchants that have no suggestion yet (ADR-006)."""
    from app.config import get_settings

    _waiting(db, batch_id)
    try:
        asked, stored = suggestions.suggest(db, batch_id=batch_id)
    except suggestions.SuggestError as exc:
        db.rollback()
        raise HTTPException(exc.status, str(exc)) from exc
    return SuggestOut(asked=asked, suggested=stored, model=get_settings().anthropic_model)


@router.post("/batches/{batch_id}/accept-suggestions", response_model=AcceptedOut)
def batch_accept_suggestions(
    batch_id: int, db: DB, request: Request, min_confidence: MinConfidence = HIGH
) -> AcceptedOut:
    batch = _waiting(db, batch_id)
    if batch.status != "preview":
        raise HTTPException(409, f"This statement is already {batch.status}.")
    done = classify.accept_suggestions(
        db, _user(request), min_confidence=min_confidence, batch_id=batch_id
    )
    return AcceptedOut(**vars(done))


# ---------------- ADR-029: the Inbox doing more of the work ----------------
class AutoRuleOut(BaseModel):
    rule_id: int
    pattern: str
    category_id: int
    category_path: str
    lines: int
    accepted_at: datetime
    is_active: bool


class AutoOut(BaseModel):
    threshold: Decimal
    on: bool
    rules: list[AutoRuleOut]


class UndoneOut(BaseModel):
    lines: int


class ManyIn(BaseModel):
    merchant_keys: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=200
    )
    category_id: int | None = None  # None: each merchant to its suggestion
    save_rule: bool = True


class ManyOut(BaseModel):
    merchants: int
    lines: int
    also_by_rule: int
    skipped: int


class WhoIn(BaseModel):
    transaction_id: int
    counterparty_id: int


def _inbox_fail(exc: inbox.InboxError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.get("/review/auto", response_model=AutoOut)
def recently_auto(db: DB) -> AutoOut:
    """Rules saved on their own from Claude's sure suggestions in the last 30 days."""
    from app.config import get_settings

    paths = category_paths(db)
    threshold = get_settings().auto_accept_confidence
    return AutoOut(
        threshold=threshold,
        on=threshold > 0 and suggestions.available(),
        rules=[
            AutoRuleOut(**vars(r), category_path=paths.get(r.category_id, "?"))
            for r in inbox.recent_auto(db)
        ],
    )


@router.post("/review/auto/{rule_id}/undo", response_model=UndoneOut)
def undo_auto(rule_id: int, db: DB, request: Request) -> UndoneOut:
    """Turn the rule off and put its lines back in the Inbox."""
    try:
        return UndoneOut(lines=inbox.undo_auto(db, rule_id, _user(request)))
    except inbox.InboxError as exc:
        db.rollback()
        raise _inbox_fail(exc) from exc


@router.post("/review/resolve-many", response_model=ManyOut)
def resolve_many(body: ManyIn, db: DB, request: Request) -> ManyOut:
    """Several merchants at once: to one category, or each to its suggestion."""
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise HTTPException(404, f"Category {body.category_id} not found.")
    done = inbox.resolve_many(
        db, body.merchant_keys, body.category_id, _user(request), body.save_rule
    )
    return ManyOut(**vars(done))


@router.get("/review/who", response_model=list[TransactionOut])
def who(db: DB, month: Month = None) -> list[TransactionOut]:
    """Transfers that don't say who they were for (last 90 days, or a month)."""
    names = {a.account_id: a.name for a in db.scalars(select(Account))}
    paths = category_paths(db)
    return [
        transaction_out(t, names.get(t.account_id or 0), paths) for t in inbox.who_lines(db, month)
    ]


@router.post("/review/who", response_model=TransactionOut)
def set_who(body: WhoIn, db: DB, request: Request) -> TransactionOut:
    try:
        row = inbox.set_who(db, body.transaction_id, body.counterparty_id, _user(request))
    except inbox.InboxError as exc:
        db.rollback()
        raise _inbox_fail(exc) from exc
    return _one_out(db, row)
