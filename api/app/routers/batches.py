"""Read a statement into staging, preview, approve or discard; list transactions (F4)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion import stage
from app.ingestion.preview import batch_out, category_paths
from app.ingestion.storage import StatementStore, get_store
from app.models import Account, ImportBatch, StatementFile, Transaction
from app.schemas import ApproveOut, BatchOut, TransactionOut

router = APIRouter(prefix="/api", tags=["batches"])
DB = Annotated[Session, Depends(get_session)]
Store = Annotated[StatementStore, Depends(get_store)]


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _batch(db: Session, batch_id: int) -> ImportBatch:
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(404, f"Batch {batch_id} not found.")
    return b


@router.post("/statements/{statement_id}/read", response_model=BatchOut)
def read_statement(statement_id: int, request: Request, db: DB, store: Store) -> BatchOut:
    sf = db.get(StatementFile, statement_id)
    if sf is None:
        raise HTTPException(404, f"Statement {statement_id} not found.")
    try:
        batch = stage.parse_statement(db, store, sf, _user(request))
    except stage.StageError as exc:
        db.rollback()
        raise HTTPException(exc.status, str(exc)) from exc
    return batch_out(db, batch)


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: int, db: DB) -> BatchOut:
    return batch_out(db, _batch(db, batch_id))


@router.post("/batches/{batch_id}/approve", response_model=ApproveOut)
def approve_batch(batch_id: int, request: Request, db: DB) -> ApproveOut:
    batch = _batch(db, batch_id)
    try:
        loaded, skipped = stage.approve(db, batch, _user(request))
    except stage.StageError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ApproveOut(batch_id=batch_id, loaded=loaded, skipped_duplicates=skipped)


@router.post("/batches/{batch_id}/reject", response_model=BatchOut)
def reject_batch(batch_id: int, request: Request, db: DB) -> BatchOut:
    batch = _batch(db, batch_id)
    try:
        stage.reject(db, batch, _user(request))
    except stage.StageError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return batch_out(db, batch)


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    db: DB,
    month: Annotated[
        date | None, Query(description="Any day of the month, e.g. 2026-09-01")
    ] = None,
    account_id: int | None = None,
    source: str | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[TransactionOut]:
    q = (
        select(Transaction, Account.name)
        .outerjoin(Account, Account.account_id == Transaction.account_id)
        .order_by(Transaction.txn_date.desc(), Transaction.transaction_id.desc())
        .limit(limit)
    )
    if month:
        q = q.where(Transaction.cash_month == month.replace(day=1))
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if source:
        q = q.where(Transaction.source == source)
    paths = category_paths(db)
    return [
        TransactionOut(
            transaction_id=t.transaction_id,
            txn_date=t.txn_date,
            post_date=t.post_date,
            cash_month=t.cash_month,
            account_id=t.account_id,
            account_name=name,
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
        )
        for t, name in db.execute(q)
    ]
