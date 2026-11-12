"""Closing a month (ADR-087): the exceptions on one screen, and the record that it was closed."""

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.preview import category_paths
from app.services import month_close

router = APIRouter(prefix="/api/close", tags=["close"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(include_in_schema=False)]


class OpenOut(BaseModel):
    kind: str
    text: str
    link: str


class UnusualOut(BaseModel):
    group: str
    amount: Decimal
    average: Decimal


class DecidedOut(BaseModel):
    rule_id: int
    pattern: str
    category_path: str
    lines: int
    is_active: bool


class CloseOut(BaseModel):
    month: date
    ready_on: date
    ready: bool
    closed_at: datetime | None
    closed_by: str | None
    missing: list[OpenOut]
    unusual: list[UnusualOut]
    decided: list[DecidedOut]
    invoices: int
    has_report: bool
    sri_url: str


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _month(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m").date()
    except ValueError as exc:
        raise HTTPException(422, "Months look like 2026-10.") from exc


def _out(db: Session, c: month_close.Close) -> CloseOut:
    paths = category_paths(db)
    return CloseOut(
        month=c.month,
        ready_on=c.ready_on,
        ready=c.ready,
        closed_at=c.closed_at,
        closed_by=c.closed_by,
        missing=[OpenOut(**asdict(m)) for m in c.missing],
        unusual=[UnusualOut(**asdict(u)) for u in c.unusual],
        decided=[
            DecidedOut(
                rule_id=d.rule_id,
                pattern=d.pattern,
                category_path=paths.get(d.category_id, "?"),
                lines=d.lines,
                is_active=d.is_active,
            )
            for d in c.decided
        ],
        invoices=c.invoices,
        has_report=c.has_report,
        sri_url=c.sri_url,
    )


@router.get("/{month}", response_model=CloseOut)
def get_close(month: str, db: DB, today: Today = None) -> CloseOut:
    """What a month (YYYY-MM) still misses, what looks unusual in it, what the app decided on
    its own, and whether it has been closed."""
    try:
        return _out(db, month_close.view(db, _month(month), today))
    except month_close.CloseError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/{month}", response_model=CloseOut)
def close_month(month: str, db: DB, request: Request, today: Today = None) -> CloseOut:
    """Close the month: its report is written if it has none, and who closed it is recorded."""
    try:
        return _out(db, month_close.close(db, _month(month), _user(request), today))
    except month_close.CloseError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.delete("/{month}", response_model=CloseOut)
def reopen_month(month: str, db: DB, today: Today = None) -> CloseOut:
    """Take the closed mark off; nothing else changes."""
    try:
        return _out(db, month_close.reopen(db, _month(month), today))
    except month_close.CloseError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
