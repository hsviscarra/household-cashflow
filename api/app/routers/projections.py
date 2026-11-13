"""Projections (F15, ADR-013): the next three months, cash timing and spending alerts."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas import (
    ProjectionAccountOut,
    ProjectionAlertOut,
    ProjectionBandOut,
    ProjectionDayOut,
    ProjectionEventOut,
    ProjectionMonthOut,
    ProjectionOut,
    ScenarioBaseOut,
    ScenarioIn,
    SeasonalNoteOut,
)
from app.services import projections

router = APIRouter(prefix="/api", tags=["projections"])
DB = Annotated[Session, Depends(get_session)]


Today = Annotated[date | None, Query(description="For tests: the day to start")]


@router.get("/projections", response_model=ProjectionOut)
def get_projections(
    db: DB,
    today: Today = None,
    horizon: Annotated[int, Query(description="Months ahead: 1, 3 or 12")] = 3,
    average_over: Annotated[int, Query(description="Months to average: 3, 6 or 12")] = 3,
    floor: Annotated[Decimal, Query(ge=0, description="Warn under this balance")] = Decimal(0),
    include_held: Annotated[bool, Query(description="Count money held for others")] = False,
    seasons: Annotated[bool, Query(description="Everyday spending follows the seasons")] = True,
) -> ProjectionOut:
    if horizon not in projections.HORIZONS or average_over not in projections.AVERAGES:
        raise HTTPException(422, "Horizon is 1, 3 or 12 months; the average 3, 6 or 12.")
    p = projections.project(
        db,
        today,
        horizon=horizon,
        average_over=average_over,
        floor=floor,
        include_held=include_held,
        follow_seasons=seasons,
    )
    return _out(p)


@router.post("/projections/scenario", response_model=ProjectionOut)
def scenario(body: ScenarioIn, db: DB, today: Today = None) -> ProjectionOut:
    """The forecast with what-ifs added (ADR-033), and the same without them to compare."""
    opts = {
        "horizon": body.horizon,
        "average_over": body.average_over,
        "floor": body.floor,
        "include_held": body.include_held,
        "follow_seasons": body.seasons,
    }
    changes = [projections.Change(**c.model_dump()) for c in body.changes]
    p = projections.project(db, today, changes=changes, **opts)  # type: ignore[arg-type]
    out = _out(p)
    if changes:
        b = projections.project(db, today, **opts)  # type: ignore[arg-type]
        out.base = ScenarioBaseOut(
            lowest=ProjectionDayOut(day=b.lowest[0], balance=b.lowest[1]) if b.lowest else None,
            first_short=b.first_short,
            end_cash=b.end_cash,
        )
    return out


def _out(p: projections.Projection) -> ProjectionOut:
    return ProjectionOut(
        today=p.today,
        start_cash=p.start_cash,
        cash_as_of=p.cash_as_of,
        variable_per_month=p.variable_per_month,
        average_months=p.average_months,
        months=[
            ProjectionMonthOut(
                month=m.month,
                income=m.income,
                fixed=m.fixed,
                variable=m.variable,
                purchases=m.purchases,
                net=m.net,
                end_cash=m.end_cash,
                items=[ProjectionEventOut(**asdict(e)) for e in m.items],
                end_cash_low=m.end_cash_low,
                end_cash_high=m.end_cash_high,
                seasonal=[SeasonalNoteOut(group_name=n, extra=x) for n, x in m.seasonal],
            )
            for m in p.months
        ],
        daily=[ProjectionDayOut(day=d, balance=b) for d, b in p.daily],
        lowest=ProjectionDayOut(day=p.lowest[0], balance=p.lowest[1]) if p.lowest else None,
        next_payday=ProjectionEventOut(**asdict(p.next_payday)) if p.next_payday else None,
        alerts=[
            ProjectionAlertOut(
                month=a.month,
                group_id=a.group_id,
                group_name=a.group_name,
                amount=a.amount,
                average=a.average,
                change=a.change,
            )
            for a in p.alerts
        ],
        horizon=p.horizon,
        average_over=p.average_over,
        floor=p.floor,
        held=p.held,
        include_held=p.include_held,
        accounts=[
            ProjectionAccountOut(
                account_id=r.account_id,
                name=r.name,
                start=r.start,
                as_of=r.as_of,
                daily=[ProjectionDayOut(day=d, balance=b) for d, b in r.daily],
                lowest=ProjectionDayOut(day=r.lowest[0], balance=r.lowest[1]),
                under_floor=r.under_floor,
                move=r.move,
            )
            for r in p.accounts
        ],
        first_short=p.first_short,
        end_cash=p.end_cash,
        band=[ProjectionBandOut(day=d, low=lo, high=hi) for d, lo, hi in p.band],
        chance_under_floor=p.chance_under_floor,
        seasons=p.seasons,
        seasonal_groups=p.seasonal_groups,
        seasons_from=p.seasons_from,
    )
