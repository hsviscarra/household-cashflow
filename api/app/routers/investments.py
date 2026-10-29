"""Interactive Brokers portfolio (F22, ADR-019)."""

from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.schemas import PortfolioOut, PortfolioReadOut, PositionOut
from app.services import ibkr

router = APIRouter(prefix="/api/investments/ibkr", tags=["investments"])
DB = Annotated[Session, Depends(get_session)]
MAX_BYTES = 10 * 1024 * 1024


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _run(fn: Callable[[], ibkr.Imported]) -> PortfolioReadOut:
    try:
        return PortfolioReadOut(**asdict(fn()))
    except ibkr.IbkrError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.get("", response_model=PortfolioOut)
def get_portfolio(db: DB) -> PortfolioOut:
    """The latest positions, total and cash; stale when IBKR is set up and the last read is more
    than 20 hours old (the page then refreshes it)."""
    p = ibkr.portfolio(db)
    return PortfolioOut(
        configured=p.configured,
        holding_id=p.holding_id,
        as_of=p.as_of,
        total=p.total,
        cash=p.cash,
        previous_total=p.previous_total,
        previous_as_of=p.previous_as_of,
        stale=p.stale,
        positions=[
            PositionOut(
                symbol=x.symbol,
                description=x.description,
                asset_class=x.asset_class,
                currency=x.currency,
                quantity=x.quantity,
                price=x.price,
                value=x.value,
                cost_basis=x.cost_basis,
                unrealized=x.unrealized,
            )
            for x in p.positions
        ],
    )


@router.post("/refresh", response_model=PortfolioReadOut)
def refresh(request: Request, db: DB) -> PortfolioReadOut:
    """Download today's report from IBKR's Flex Web Service."""
    return _run(lambda: ibkr.refresh(db, _user(request)))


@router.post("/upload", response_model=PortfolioReadOut)
async def upload(file: UploadFile, request: Request, db: DB) -> PortfolioReadOut:
    """Read a Flex report (XML) downloaded from Client Portal."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    user = _user(request)
    return _run(lambda: ibkr.store(db, ibkr.parse(data), user))
