"""Read a statement into staging, preview, approve or discard; list transactions (F4)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion import stage
from app.ingestion.preview import batch_out, category_paths
from app.ingestion.storage import StatementStore, get_store
from app.models import Account, ImportBatch, StatementFile, StatementHeader, Transaction
from app.routers.classify import transaction_out
from app.schemas import ApplyRulesOut, ApproveOut, BatchOut, TransactionOut
from app.services import classify, inbox, recurring, transfers

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
        stage.auto_approve(db, batch, _user(request))
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


class WaitingOut(BaseModel):
    batch_id: int
    file_name: str
    reason: str


class ApproveReadyOut(BaseModel):
    approved: int
    loaded: int
    waiting: list[WaitingOut]
    # Merchants and lines Claude's sure suggestions categorized right after (ADR-029).
    auto_merchants: int = 0
    auto_lines: int = 0


@router.post("/batches/approve-ready", response_model=ApproveReadyOut)
def approve_ready(request: Request, db: DB) -> ApproveReadyOut:
    """Approve every waiting statement that ties out, oldest period first (so each opening
    balance follows the previous closing). The rest are listed with what they need."""
    rows = db.execute(
        select(ImportBatch, StatementFile.file_name)
        .join(StatementFile, StatementFile.statement_file_id == ImportBatch.statement_file_id)
        .outerjoin(
            StatementHeader, StatementHeader.statement_file_id == ImportBatch.statement_file_id
        )
        .where(ImportBatch.status == "preview")
        .order_by(StatementHeader.period_start, ImportBatch.batch_id)
    ).all()
    approved = loaded = 0
    waiting = []
    for batch, name in rows:
        reason = stage.not_ready(db, batch)
        if reason is None:
            try:
                n, _ = stage.approve(db, batch, _user(request))
            except stage.StageError as exc:
                reason = str(exc)
            else:
                approved += 1
                loaded += n
                continue
        waiting.append(WaitingOut(batch_id=batch.batch_id, file_name=name, reason=reason))
    auto = inbox.autopilot(db, _user(request)) if approved else inbox.Autopilot()
    return ApproveReadyOut(
        approved=approved,
        loaded=loaded,
        waiting=waiting,
        auto_merchants=auto.merchants,
        auto_lines=auto.lines,
    )


@router.post("/batches/{batch_id}/apply-rules", response_model=ApplyRulesOut)
def apply_rules(batch_id: int, db: DB) -> ApplyRulesOut:
    """Run today's rules on the batch's uncategorized lines (rules saved after it was read)."""
    batch = _batch(db, batch_id)
    if batch.status != "preview":
        raise HTTPException(409, f"This batch is already {batch.status}.")
    count = classify.classify_waiting(db, batch_id=batch_id)
    db.commit()
    return ApplyRulesOut(categorized=count, batch=batch_out(db, batch))


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
    person: Annotated[
        Literal["Hernan", "Lauren", "Joint"] | None,
        Query(description="Only this person's lines (the Both/Hernan/Lauren switch)"),
    ] = None,
    counterparty_id: Annotated[
        int | None, Query(description="Only lines for this person (People, ADR-023)")
    ] = None,
    months: Annotated[
        int, Query(ge=1, le=36, description="With month: this many months up to it (ADR-030)")
    ] = 1,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[TransactionOut]:
    q = (
        select(Transaction, Account.name)
        .outerjoin(Account, Account.account_id == Transaction.account_id)
        .order_by(Transaction.txn_date.desc(), Transaction.transaction_id.desc())
        .limit(limit)
    )
    if month:
        end = month.replace(day=1)
        q = q.where(
            Transaction.cash_month >= recurring.add_months(end, 1 - months),
            Transaction.cash_month <= end,
        )
    if counterparty_id:
        q = q.where(Transaction.counterparty_id == counterparty_id)
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if source:
        q = q.where(Transaction.source == source)
    if person == "Joint":
        q = q.where((Transaction.person == "Joint") | Transaction.person.is_(None))
    elif person:
        q = q.where(Transaction.person == person)
    paths = category_paths(db)
    found = list(db.execute(q))
    parts = classify.part_counts(db, [t.transaction_id for t, _ in found])
    others = transfers.other_legs(db, [t for t, _ in found])
    return [
        transaction_out(
            t, name, paths, parts.get(t.transaction_id, 0), others.get(t.transaction_id)
        )
        for t, name in found
    ]
