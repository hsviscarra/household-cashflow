"""Saving goals (ADR-040)."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.services import goals

router = APIRouter(prefix="/api/goals", tags=["goals"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(description="For tests; default today")]


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_amount: Decimal = Field(gt=0, le=100_000_000)
    target_date: date | None = None
    item_key: str | None = Field(default=None, max_length=40)
    saved_amount: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    monthly_amount: Decimal | None = Field(default=None, ge=0, le=10_000_000)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=400)


class GoalPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_amount: Decimal | None = Field(default=None, gt=0, le=100_000_000)
    target_date: date | None = None
    item_key: str | None = Field(default=None, max_length=40)
    saved_amount: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    monthly_amount: Decimal | None = Field(default=None, ge=0, le=10_000_000)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=400)


class GoalOut(BaseModel):
    goal_id: int
    name: str
    target_amount: Decimal
    target_date: date | None
    item_key: str | None
    place_name: str | None
    saved_amount: Decimal | None
    monthly_amount: Decimal | None
    is_active: bool
    notes: str | None
    current: Decimal
    as_of: date | None
    share: Decimal
    left: Decimal
    months_left: int | None
    needed_monthly: Decimal | None
    projected: Decimal | None
    status: str


class PlaceOut(BaseModel):
    key: str
    name: str
    value: Decimal | None
    as_of: date | None


class GoalsOut(BaseModel):
    goals: list[GoalOut]
    places: list[PlaceOut]


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


@router.get("", response_model=GoalsOut)
def list_goals(db: DB, today: Today = None) -> GoalsOut:
    day = today or date.today()
    return GoalsOut(
        goals=[GoalOut(**asdict(g)) for g in goals.all_goals(db, day)],
        places=[PlaceOut(**asdict(p)) for p in goals.places(db, day).values()],
    )


def _one(db: Session, goal_id: int, today: date | None) -> GoalOut:
    return GoalOut(**asdict(next(g for g in goals.all_goals(db, today) if g.goal_id == goal_id)))


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(body: GoalIn, db: DB, request: Request, today: Today = None) -> GoalOut:
    try:
        g = goals.create(db, body.model_dump(), _user(request), today)
    except goals.GoalError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _one(db, g.goal_id, today)


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalPatch, db: DB, today: Today = None) -> GoalOut:
    """Only the fields sent change; send null to clear a date, a link or an amount."""
    try:
        goals.update(db, goal_id, body.model_dump(exclude_unset=True), today)
    except goals.GoalError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _one(db, goal_id, today)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, db: DB) -> None:
    try:
        goals.delete(db, goal_id)
    except goals.GoalError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
