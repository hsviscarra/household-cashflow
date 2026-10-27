"""Spending analytics (F13, ADR-010): one month's spending with MoM, YoY and drill-down."""

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas import (
    SpendCategoryOut,
    SpendGroupOut,
    SpendingOut,
    SpendLineOut,
    SpendMerchantOut,
    SpendMonthOut,
    SpendSliceOut,
    SpendTotalOut,
)
from app.services import spending

router = APIRouter(prefix="/api/spending", tags=["spending"])
DB = Annotated[Session, Depends(get_session)]
Month = Annotated[date | None, Query(description="Any day of the month; default the latest")]


@router.get("", response_model=SpendingOut)
def get_spending(db: DB, month: Month = None) -> SpendingOut:
    s = spending.analyze(db, month)
    return SpendingOut(
        month=s.month,
        months=s.months,
        source=s.source,  # type: ignore[arg-type]
        total=SpendTotalOut(**asdict(s.total)),
        groups=[
            SpendGroupOut(
                group_id=g.group_id,
                name=g.name,
                color=g.color,
                amount=g.amount,
                prev=g.prev,
                last_year=g.last_year,
                transactions=g.transactions,
                categories=[SpendCategoryOut(**asdict(c)) for c in g.categories],
            )
            for g in s.groups
        ],
        by_person=[SpendSliceOut(**asdict(x)) for x in s.by_person],
        by_country=[SpendSliceOut(**asdict(x)) for x in s.by_country],
        fixed=[SpendSliceOut(**asdict(x)) for x in s.fixed],
        merchants=[SpendMerchantOut(**asdict(m)) for m in s.merchants],
        trend=[SpendMonthOut(month=m, amount=a) for m, a in s.trend],
    )


@router.get("/lines", response_model=list[SpendLineOut])
def get_lines(
    db: DB,
    month: date,
    group_id: int | None = None,
    category_id: int | None = None,
    merchant: str | None = None,
    person: str | None = None,
    country: str | None = None,
    fixed: bool | None = None,
) -> list[SpendLineOut]:
    found = spending.lines(
        db,
        month,
        group_id=group_id,
        category_id=category_id,
        merchant=merchant,
        person=person,
        country=country,
        fixed=fixed,
    )
    return [SpendLineOut(**asdict(x)) for x in found]
