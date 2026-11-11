"""Transfers between own accounts (F10): match on demand, unlink a wrong pair, and list the
transfers whose other side isn't loaded."""

from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.preview import category_paths
from app.models import Account
from app.routers.classify import transaction_out
from app.schemas import MatchOut, TransactionOut
from app.services import transfers

router = APIRouter(prefix="/api/transfers", tags=["transfers"])
DB = Annotated[Session, Depends(get_session)]


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


@router.post("/match", response_model=MatchOut)
def match(db: DB, request: Request) -> MatchOut:
    return MatchOut(pairs=transfers.match(db, _user(request)).pairs)


@router.post("/{transaction_id}/one-sided", status_code=status.HTTP_204_NO_CONTENT)
def one_sided(transaction_id: int, db: DB, request: Request) -> Response:
    """The other side is in an account the app doesn't follow: stop asking for it."""
    try:
        transfers.one_sided(db, transaction_id, _user(request))
    except transfers.TransferError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{group}", status_code=status.HTTP_204_NO_CONTENT)
def unlink(group: int, db: DB, request: Request) -> Response:
    try:
        transfers.unlink(db, group, _user(request))
    except transfers.TransferError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/unmatched", response_model=list[TransactionOut])
def unmatched(
    db: DB,
    month: Annotated[
        date | None, Query(description="Any day of the month; all if left out")
    ] = None,
) -> list[TransactionOut]:
    names = {a.account_id: a.name for a in db.scalars(select(Account))}
    paths = category_paths(db)
    return [
        transaction_out(t, names.get(t.account_id or 0), paths)
        for t in transfers.unmatched(db, month)
    ]


class PairIn(BaseModel):
    a: int
    b: int


@router.post("/pair")
def pair(body: PairIn, db: DB, request: Request) -> dict[str, int]:
    """These two lines are the two sides of one transfer (ADR-075)."""
    try:
        return {"group": transfers.pair(db, body.a, body.b, _user(request))}
    except transfers.TransferError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


class OutsideIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    place: str = Field(min_length=1, max_length=100)


@router.post("/outside")
def outside(body: OutsideIn, db: DB, request: Request) -> dict[str, int]:
    """The other side is somewhere the app doesn't follow (ADR-075)."""
    return {"settled": transfers.settle_outside(db, body.ids, body.place, _user(request))}


@router.get("/workbench")
def workbench(db: DB, since: Annotated[date | None, Query()] = None) -> dict[str, Any]:
    """Transfers missing their other side, bunched by text and amount, with candidates (ADR-075)."""
    return {
        "places": list(transfers.PLACES),
        "bunches": [asdict(b) for b in transfers.workbench(db, since)],
    }
