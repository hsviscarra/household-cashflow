"""Explore: a view of spending by two dimensions and a measure (ADR-099)."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas import Owner
from app.services import explore

router = APIRouter(prefix="/api/explore", tags=["explore"])
DB = Annotated[Session, Depends(get_session)]


class ExploreOut(BaseModel):
    measure: str
    rows_by: str
    cols_by: str | None
    rows: list[str]
    cols: list[str]
    cells: list[list[Decimal]]
    row_totals: list[Decimal]
    col_totals: list[Decimal]
    total: Decimal
    folded: int


@router.get("", response_model=ExploreOut)
def get_explore(
    db: DB,
    start: Annotated[date, Query(description="First month (any day of it)")],
    end: Annotated[date, Query(description="Last month (any day of it)")],
    rows: str = "group",
    cols: str | None = None,
    measure: str = "amount",
    person: Owner | None = None,
    group_id: int | None = None,
    category_id: int | None = None,
    account_id: int | None = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> ExploreOut:
    spec = explore.Spec(
        measure, rows, cols or None, start, end, person, group_id, category_id, account_id, country
    )
    try:
        p = explore.build(db, spec)
    except explore.ExploreError as e:
        raise HTTPException(422, str(e)) from e
    return ExploreOut(
        measure=measure,
        rows_by=rows,
        cols_by=cols or None,
        rows=p.rows,
        cols=p.cols,
        cells=p.cells,
        row_totals=p.row_totals,
        col_totals=p.col_totals,
        total=p.total,
        folded=p.folded,
    )
