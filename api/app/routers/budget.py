"""The monthly budget per group (ADR-039)."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.session import get_session
from app.services import budget

router = APIRouter(prefix="/api/budget", tags=["budget"])
DB = Annotated[Session, Depends(get_session)]
Month = Annotated[str, Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class GroupBudgetOut(BaseModel):
    """A group's budget in a month: planned, carried over and spent."""

    group_id: int
    name: str
    color: str | None
    budget: Decimal | None
    rollover: bool
    carried: Decimal
    spent: Decimal
    available: Decimal
    left: Decimal
    expected: Decimal
    status: str
    suggested: Decimal | None
    since: date | None


class MonthBudgetOut(BaseModel):
    """A month's budget with its groups and totals."""

    month: date
    day_share: Decimal
    groups: list[GroupBudgetOut]
    budgeted: Decimal
    spent: Decimal
    unbudgeted: Decimal
    left: Decimal
    has_plans: bool


class PlanIn(BaseModel):
    """A group's budget from a month on, and whether what is left rolls over."""

    from_month: date
    amount: Decimal = Field(ge=0, le=1_000_000)
    rollover: bool = False


class SinkingFundOut(BaseModel):
    """A bill that comes less than monthly, as an amount to set aside each month."""

    template_id: int
    name: str
    every_months: int
    amount: Decimal
    monthly: Decimal
    next_due: date
    months_to_go: int
    should_have: Decimal


class StartedOut(BaseModel):
    """How many groups got a first budget."""

    added: int


def _month(m: str) -> date:
    return date.fromisoformat(f"{m}-01")


@router.get("/{month}", response_model=MonthBudgetOut)
def month_budget(
    month: Month, db: DB, today: Annotated[date | None, Query()] = None
) -> MonthBudgetOut:
    """A month's budget by group: planned, spent, pace and what carries over."""
    return MonthBudgetOut(**asdict(budget.month_view(db, _month(month), today)))


@router.put("/groups/{group_id}", status_code=204)
def set_plan(group_id: int, body: PlanIn, db: DB, request: Request) -> None:
    """A group's budget from a month on (0 = none from then); later changes are replaced."""
    try:
        budget.set_plan(
            db, group_id, body.from_month, body.amount, body.rollover, current_user(request)
        )
    except budget.BudgetError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/{month}/start-from-average", response_model=StartedOut)
def start_from_average(month: Month, db: DB, request: Request) -> StartedOut:
    """Every group with spending and no budget yet: its 3-month average from this month on."""
    return StartedOut(added=budget.start_from_average(db, _month(month), current_user(request)))


@router.get("/{month}/yearly-bills", response_model=list[SinkingFundOut])
def yearly_bills(month: Month, db: DB) -> list[SinkingFundOut]:
    """Bills that come every 2 to 12 months, as a monthly amount to set aside (ADR-041)."""
    return [SinkingFundOut(**asdict(f)) for f in budget.sinking_funds(db, _month(month))]
