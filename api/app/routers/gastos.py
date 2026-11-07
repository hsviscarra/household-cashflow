"""Gastos personales (ADR-036): the deductible expenses per person and year, the invoices behind
them, the choices people make and the numbers for the SRI annex."""

import csv
import io
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.services import gastos

router = APIRouter(prefix="/api", tags=["gastos"])
DB = Annotated[Session, Depends(get_session)]
Year = Annotated[int, Path(ge=2020, le=2100)]
Person = Literal["Hernan", "Lauren"]
GpCategory = Literal[
    "vivienda", "educacion", "salud", "alimentacion", "vestimenta", "turismo", "none"
]


class CategoryTotalOut(BaseModel):
    category: str
    label: str
    invoices: int
    amount: Decimal


class PersonSummaryOut(BaseModel):
    person: str
    cargas: int
    catastrophic: bool
    cap: Decimal | None
    total: Decimal
    deductible: Decimal
    rebate: Decimal
    by_category: list[CategoryTotalOut]
    to_classify: int
    not_deductible: int


class GastosSummaryOut(BaseModel):
    year: int
    canasta: Decimal | None
    rate: Decimal
    people: list[PersonSummaryOut]
    unassigned: int
    unassigned_amount: Decimal
    labels: dict[str, str]


class GastosInvoiceOut(BaseModel):
    invoice_id: int
    issue_date: date
    issuer_ruc: str
    issuer_name: str
    number: str
    subtotal: Decimal
    total: Decimal
    person: str | None
    person_source: str | None
    category: str | None
    category_source: str | None
    transaction_id: int | None
    paid_as: str | None


class GastosChoiceIn(BaseModel):
    """Send only what changes: `person` and/or `category` (null clears a choice)."""

    person: Person | None = None
    category: GpCategory | None = None
    remember_issuer: bool = False


class GpProfileIn(BaseModel):
    cargas: int = Field(ge=0, le=20)
    catastrophic: bool = False


class GpProfileOut(GpProfileIn):
    person: str
    year: int
    cap: Decimal | None


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


@router.get("/gastos/{year}", response_model=GastosSummaryOut)
def summary(year: Year, db: DB) -> GastosSummaryOut:
    s = gastos.summary(db, year)
    return GastosSummaryOut(**asdict(s), labels=gastos.LABELS)


@router.get("/gastos/{year}/invoices", response_model=list[GastosInvoiceOut])
def invoices(
    year: Year,
    db: DB,
    person: Annotated[Literal["Hernan", "Lauren", "none"] | None, Query()] = None,
    status: Annotated[Literal["all", "to_classify"], Query()] = "all",
) -> list[GastosInvoiceOut]:
    """The year's invoices, newest first; `person=none` = not assigned to anyone yet;
    `status=to_classify` = no category yet."""
    out = []
    for r in gastos.rows(db, year):
        if person == "none" and r.person is not None:
            continue
        if person in gastos.PEOPLE and r.person != person:
            continue
        if status == "to_classify" and r.category is not None:
            continue
        out.append(GastosInvoiceOut(**asdict(r)))
    return out


@router.put("/invoices/{invoice_id}/gastos", response_model=GastosInvoiceOut)
def choose(invoice_id: int, body: GastosChoiceIn, db: DB, request: Request) -> GastosInvoiceOut:
    sent = body.model_fields_set
    try:
        inv = gastos.choose(
            db,
            invoice_id,
            _user(request),
            set_person="person" in sent,
            person=body.person,
            set_category="category" in sent,
            category=body.category,
            remember_issuer=body.remember_issuer,
        )
    except gastos.GastosError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    row = next(r for r in gastos.rows(db, inv.issue_date.year) if r.invoice_id == invoice_id)
    return GastosInvoiceOut(**asdict(row))


@router.put("/gastos/{year}/profile/{person}", response_model=GpProfileOut)
def set_profile(year: Year, person: Person, body: GpProfileIn, db: DB) -> GpProfileOut:
    p = gastos.set_profile(db, person, year, body.cargas, body.catastrophic)
    return GpProfileOut(
        person=p.person,
        year=p.year,
        cargas=p.cargas,
        catastrophic=p.catastrophic,
        cap=gastos.cap(year, p.cargas, p.catastrophic),
    )


@router.get("/gastos/{year}/{person}.csv")
def export(year: Year, person: Person, db: DB) -> Response:
    """One row per issuer and category: RUC, name, category, invoices, base and total."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["RUC", "Proveedor", "Categoría", "Comprobantes", "Base imponible", "Total"])
    for line in gastos.by_issuer(db, year, person):
        w.writerow(
            [
                line.issuer_ruc,
                line.issuer_name,
                gastos.LABELS[line.category],
                line.invoices,
                f"{line.subtotal:.2f}",
                f"{line.total:.2f}",
            ]
        )
    return Response(
        buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="gastos-{person}-{year}.csv"'},
    )
