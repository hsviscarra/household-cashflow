"""Where's the money (ADR-051)."""

from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services import reconcile

router = APIRouter(prefix="/api/reconcile", tags=["where's the money"])
DB = Annotated[Session, Depends(get_session)]


@router.get("")
def where_is_the_money(
    db: DB,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict[str, Any]:
    """Kept (money in - money out) from `from` to `to` (months), against how the bank and card
    balances changed, per account, with what usually explains the gap."""
    if end < start:
        raise HTTPException(422, "'to' is before 'from'.")
    return asdict(reconcile.build(db, start, end))
