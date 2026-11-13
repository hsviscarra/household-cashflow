"""Income tax projected for the year (ADR-088)."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.session import get_session
from app.services import tax_projection

router = APIRouter(prefix="/api/taxes", tags=["taxes"])
DB = Annotated[Session, Depends(get_session)]
Year = Annotated[int, Path(ge=2020, le=2100)]
Person = Literal["Hernan", "Lauren"]
Amount = Annotated[Decimal, Field(ge=0, le=Decimal("10000000"), max_digits=12, decimal_places=2)]


class TaxProfile(BaseModel):
    """How the person is taxed, and the three yearly figures a bank line can't tell."""

    regime: Literal["employee", "foreign", "independent"]
    withheld: Amount = Decimal(0)
    exempt: Amount = Decimal(0)
    deductions: Amount = Decimal(0)


class PersonTaxOut(BaseModel):
    """A person's projected income tax for a year."""

    person: str
    year: int
    profile: TaxProfile
    received: Decimal
    typical_month: Decimal
    projected_income: Decimal
    taxable: Decimal
    tax: Decimal
    expenses: Decimal
    cap: Decimal | None
    rebate: Decimal
    room: Decimal
    more_rebate: Decimal
    due: Decimal
    to_pay: Decimal
    pay_on: date
    months_left: int
    set_aside: Decimal
    notes: list[str]


def _out(t: tax_projection.PersonTax) -> PersonTaxOut:
    return PersonTaxOut(**{**asdict(t), "profile": TaxProfile(**asdict(t.profile))})


@router.get("/{year}/projection", response_model=list[PersonTaxOut])
def projection(
    year: Year, db: DB, today: Annotated[date | None, Query(include_in_schema=False)] = None
) -> list[PersonTaxOut]:
    """Each person's income tax for the year as it stands today: income received and still to
    come, the tax on it, the rebate for personal expenses, and what is left to pay."""
    try:
        return [_out(t) for t in tax_projection.projection(db, year, today)]
    except tax_projection.TaxError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.put("/{year}/projection/{person}", response_model=PersonTaxOut)
def set_profile(
    year: Year,
    person: Person,
    body: TaxProfile,
    db: DB,
    request: Request,
    today: Annotated[date | None, Query(include_in_schema=False)] = None,
) -> PersonTaxOut:
    """Save how the person is taxed and the year's withheld, exempt and deductible amounts."""
    try:
        tax_projection.set_profile(
            db,
            person,
            year,
            tax_projection.Profile(body.regime, body.withheld, body.exempt, body.deductions),
            current_user(request),
        )
        return _out(tax_projection.person_tax(db, person, year, today))
    except tax_projection.TaxError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
