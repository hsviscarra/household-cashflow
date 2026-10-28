"""Projections (F15, ADR-013): the next three months, cash timing and spending alerts."""

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas import (
    ProjectionAlertOut,
    ProjectionDayOut,
    ProjectionEventOut,
    ProjectionMonthOut,
    ProjectionOut,
)
from app.services import projections

router = APIRouter(prefix="/api", tags=["projections"])
DB = Annotated[Session, Depends(get_session)]


@router.get("/projections", response_model=ProjectionOut)
def get_projections(
    db: DB, today: Annotated[date | None, Query(description="For tests: the day to start")] = None
) -> ProjectionOut:
    p = projections.project(db, today)
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
    )
