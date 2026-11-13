"""Net worth five to ten years ahead (ADR-098)."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services import long_view, outlook

router = APIRouter(prefix="/api/networth", tags=["networth"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(description="For tests; default today")]
# Yearly rates as fractions: 0.05 is 5% a year.
Rate = Annotated[Decimal, Query(ge=-0.5, le=0.5)]
Share = Annotated[Decimal, Query(ge=0, le=1)]


class YearOut(BaseModel):
    year: int
    end: date
    cash: Decimal
    investments_low: Decimal
    investments: Decimal
    investments_high: Decimal
    property: Decimal
    vehicles: Decimal
    other_assets: Decimal
    loans: Decimal
    other_debts: Decimal
    kept: Decimal
    net_low: Decimal
    net: Decimal
    net_high: Decimal
    milestones: list[str]


class LoanOut(BaseModel):
    name: str
    balance: Decimal
    from_table: bool
    paid_off: date | None


class AheadOut(BaseModel):
    today: date
    kept_a_year: Decimal
    net_today: Decimal
    loans: list[LoanOut]
    years: list[YearOut]


@router.get("/ahead", response_model=AheadOut)
def get_ahead(
    db: DB,
    today: Today = None,
    years: Annotated[int, Query(description="5 or 10")] = 5,
    low: Rate = long_view.DEFAULT_RETURNS[0],
    expected: Rate = long_view.DEFAULT_RETURNS[1],
    high: Rate = long_view.DEFAULT_RETURNS[2],
    property_growth: Rate = long_view.DEFAULT_PROPERTY,
    vehicle_growth: Rate = long_view.DEFAULT_VEHICLE,
    invest_share: Share = long_view.DEFAULT_INVEST_SHARE,
) -> AheadOut:
    if years not in long_view.YEARS:
        raise HTTPException(422, "Years ahead is 5 or 10.")
    if not low <= expected <= high:
        raise HTTPException(422, "The returns go from low to high.")
    day = today or date.today()
    a = long_view.Assumptions(
        years, (low, expected, high), property_growth, vehicle_growth, invest_share
    )
    s, rows = outlook.ahead(db, day, a)
    owned = s.cash + s.investments + s.property + s.vehicles + s.other_assets
    owed = sum((loan.balance for loan in s.loans), Decimal(0)) + s.other_debts
    return AheadOut(
        today=day,
        kept_a_year=s.kept_a_year.quantize(long_view.CENT),
        net_today=owned - owed,
        loans=[
            LoanOut(
                name=loan.name,
                balance=loan.balance,
                from_table=bool(loan.balances),
                paid_off=loan.paid_off,
            )
            for loan in s.loans
        ],
        years=[
            YearOut(
                year=y.year,
                end=y.end,
                cash=y.cash,
                investments_low=y.investments["low"],
                investments=y.investments["expected"],
                investments_high=y.investments["high"],
                property=y.property,
                vehicles=y.vehicles,
                other_assets=y.other_assets,
                loans=y.loans,
                other_debts=y.other_debts,
                kept=y.kept,
                net_low=y.net("low"),
                net=y.net("expected"),
                net_high=y.net("high"),
                milestones=y.milestones,
            )
            for y in rows
        ],
    )
