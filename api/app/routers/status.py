"""Month status (F12, ADR-009): each month complete, or what is missing."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas import (
    CoverageOut,
    LoadOut,
    MonthStatusOut,
    StatusAccountOut,
    StatusItemOut,
    StatusOut,
)
from app.services import status as month_status

router = APIRouter(prefix="/api", tags=["status"])
DB = Annotated[Session, Depends(get_session)]


@router.get("/status", response_model=StatusOut)
def get_status(
    db: DB,
    today: Annotated[date | None, Query(description="For tests: the day to check up to")] = None,
) -> StatusOut:
    s = month_status.month_status(db, today)
    return StatusOut(
        today=s.today,
        excel_through=s.excel_through,
        accounts=[
            StatusAccountOut(account_id=a.account_id, name=a.name, kind=a.kind, owner=a.owner)
            for a in s.accounts
        ],
        months=[
            MonthStatusOut(
                month=m.month,
                source=m.source,  # type: ignore[arg-type]
                complete=m.complete,
                items=[StatusItemOut(**vars(i)) for i in m.items],
                coverage=[
                    CoverageOut(
                        account_id=c.account_id,
                        state=c.state,  # type: ignore[arg-type]
                        covered_days=c.covered_days,
                        days=c.days,
                    )
                    for c in m.coverage
                ],
            )
            for m in s.months
        ],
        loads=[LoadOut(**vars(x)) for x in s.loads],
    )
