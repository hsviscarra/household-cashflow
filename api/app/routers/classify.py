"""Classification (F9): the review queue, categorizing a merchant (and saving a rule), Claude's
suggestions, editing a line, splits and each line's change history."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.preview import category_paths
from app.models import Account, Transaction
from app.schemas import (
    ChangeOut,
    ResolveIn,
    ResolveOut,
    ReviewGroupOut,
    ReviewLineOut,
    ReviewOut,
    SplitIn,
    SuggestionOut,
    SuggestOut,
    TransactionOut,
    TransactionPatch,
    TransferLegOut,
)
from app.services import classify, transfers
from app.services import suggest as suggestions

router = APIRouter(prefix="/api", tags=["classification"])
DB = Annotated[Session, Depends(get_session)]
Month = Annotated[date | None, Query(description="Any day of the month; all months if left out")]


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
    paths = category_paths(db)
    groups = classify.review_groups(db, month)
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
        categorized=done.categorized, rule_id=done.rule_id, also_by_rule=done.also_by_rule
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
            fields=fields,
        )
    except classify.ClassifyError as exc:
        db.rollback()
        raise _fail(exc) from exc
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


@router.get("/transactions/{transaction_id}/history", response_model=list[ChangeOut])
def transaction_history(transaction_id: int, db: DB) -> list[ChangeOut]:
    return [ChangeOut.model_validate(c) for c in classify.history(db, _row(db, transaction_id))]
