"""The monthly IVA return (ADR-062)."""

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.session import get_session
from app.models import SaleInvoice
from app.services import iva

router = APIRouter(prefix="/api/taxes/iva", tags=["taxes"])
DB = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _month(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m").date()
    except ValueError as exc:
        raise HTTPException(422, "Months look like 2026-10.") from exc


def _person(db: Session, person: str | None) -> str:
    """Whose return: as asked, else whoever issues invoices, else Hernan."""
    if person:
        return person[:20]
    found = db.execute(
        select(SaleInvoice.person, func.count())
        .group_by(SaleInvoice.person)
        .order_by(func.count().desc())
    ).first()
    return str(found[0]) if found else "Hernan"


@router.get("")
def get_month(db: DB, month: str, person: str | None = None) -> dict[str, Any]:
    """The month's sales, purchases, retenciones and Form 104 figures."""
    return asdict(iva.month(db, _person(db, person), _month(month)))


@router.get("/excel")
def get_excel(db: DB, month: str, person: str | None = None) -> Response:
    """The month as the accountant's workbook."""
    r = iva.month(db, _person(db, person), _month(month))
    return Response(
        iva.workbook(r),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="IVA_{r.month:%Y-%m}.xlsx"'},
    )


class IssuerIn(BaseModel):
    """How an issuer's purchases count for IVA."""

    issuer_ruc: str = Field(min_length=10, max_length=13)
    iva_use: str


@router.put("/issuers", status_code=204)
def put_issuer(body: IssuerIn, db: DB, request: Request) -> Response:
    """How this issuer's invoices count: business (IVA credit), personal or none."""
    try:
        iva.set_issuer(db, body.issuer_ruc, body.iva_use, current_user(request))
    except iva.IvaError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return Response(status_code=204)


class OpeningIn(BaseModel):
    """A person's opening IVA credit."""

    person: str = Field(min_length=1, max_length=20)
    month: str
    purchase_credit: Decimal = Decimal(0)
    retention_credit: Decimal = Decimal(0)


@router.put("/opening", status_code=204)
def put_opening(body: OpeningIn, db: DB, request: Request) -> Response:
    """The credit carried into a month from returns filed before the app (fields 605 and 606)."""
    try:
        iva.set_opening(
            db,
            body.person,
            _month(body.month),
            body.purchase_credit,
            body.retention_credit,
            current_user(request),
        )
    except iva.IvaError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return Response(status_code=204)
