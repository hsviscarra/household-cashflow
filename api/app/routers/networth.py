"""Balance sheet (F14, ADR-012): what the household owns and owes, and the items behind it."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.schemas import (
    BalanceSheetOut,
    HoldingIn,
    HoldingPatch,
    LoanImportOut,
    LoanPaymentOut,
    SheetItemOut,
    SheetPointOut,
    ValueIn,
    ValueOut,
)
from app.services import loans, networth

router = APIRouter(prefix="/api", tags=["networth"])
DB = Annotated[Session, Depends(get_session)]


def _run[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except (networth.NetWorthError, loans.LoanError) as exc:
        raise HTTPException(exc.status, str(exc)) from exc


MAX_BYTES = 10 * 1024 * 1024


@router.get("/networth", response_model=BalanceSheetOut)
def get_networth(
    db: DB,
    as_of: Annotated[date | None, Query(description="The day to value; default today")] = None,
) -> BalanceSheetOut:
    s = networth.sheet(db, as_of)
    assets, debts = s.total("asset"), s.total("liability")
    return BalanceSheetOut(
        as_of=s.as_of,
        assets=assets,
        liabilities=debts,
        net_worth=assets - debts,
        commitments=s.commitments,
        items=[SheetItemOut(**asdict(i)) for i in s.items],
        series=[
            SheetPointOut(month=p.month, assets=p.assets, liabilities=p.liabilities, net=p.net)
            for p in s.series
        ],
    )


@router.post("/holdings", status_code=status.HTTP_201_CREATED)
def create_holding(body: HoldingIn, db: DB) -> dict[str, int]:
    h = _run(lambda: networth.create_holding(db, body.model_dump()))
    return {"holding_id": h.holding_id}


@router.patch("/holdings/{holding_id}")
def update_holding(holding_id: int, body: HoldingPatch, db: DB) -> dict[str, int]:
    changes = body.model_dump(exclude_unset=True)
    h = _run(lambda: networth.update_holding(db, holding_id, changes))
    return {"holding_id": h.holding_id}


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(holding_id: int, db: DB) -> Response:
    _run(lambda: networth.delete_holding(db, holding_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/holdings/{holding_id}/values", response_model=ValueOut)
def set_value(holding_id: int, body: ValueIn, db: DB) -> ValueOut:
    s = _run(lambda: networth.set_value(db, holding_id, body.as_of, body.amount, body.notes))
    return ValueOut(
        snapshot_id=s.snapshot_id, as_of=s.as_of, amount=s.amount, source=s.source, notes=s.notes
    )


@router.delete("/holdings/values/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_value(snapshot_id: int, db: DB) -> Response:
    _run(lambda: networth.delete_value(db, snapshot_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/holdings/{holding_id}/schedule", response_model=LoanImportOut)
async def upload_schedule(
    holding_id: int, file: UploadFile, request: Request, db: DB
) -> LoanImportOut:
    """Read a lender's amortization table (PDF) into the loan's installments. Only the numbers
    are kept; the file itself is not stored."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    user = (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()
    r = _run(lambda: loans.import_table(db, holding_id, data, user))
    return LoanImportOut(**asdict(r))


@router.get("/holdings/{holding_id}/payments", response_model=list[LoanPaymentOut])
def loan_payments(
    holding_id: int,
    db: DB,
    today: Annotated[date | None, Query(description="Default today")] = None,
) -> list[LoanPaymentOut]:
    """The last 12 installments and the next 3, each with the bank line that paid it."""
    rows = _run(lambda: loans.payments(db, holding_id, today or date.today()))
    return [LoanPaymentOut(**asdict(p)) for p in rows]
