"""Saving on one page, and what is safe to spend (ADR-097)."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.services import payoff, savings

router = APIRouter(prefix="/api/savings", tags=["savings"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(description="For tests; default today")]
Extra = Annotated[Decimal, Query(ge=0, le=1_000_000, description="Extra toward debts each month")]


class RateMonthOut(BaseModel):
    month: date
    money_in: Decimal
    spent: Decimal
    set_aside: Decimal
    kept: Decimal
    rate: Decimal | None
    running: bool


class GoalNeedOut(BaseModel):
    goal_id: int
    name: str
    target_date: date | None
    left: Decimal
    needed_monthly: Decimal | None
    monthly_amount: Decimal | None
    status: str


class GoalPlanOut(BaseModel):
    needed: Decimal
    planned: Decimal
    saved: Decimal
    to_go: Decimal
    short: Decimal
    goals: list[GoalNeedOut]


class SafeOut(BaseModel):
    month: date
    left_so_far: Decimal
    income_to_come: Decimal
    bills_to_come: Decimal
    goals_to_go: Decimal
    days_left: int
    amount: Decimal
    a_day: Decimal


class DebtOut(BaseModel):
    key: str
    name: str
    kind: str
    balance: Decimal
    as_of: date | None
    rate: Decimal | None
    minimum: Decimal | None
    rate_from: str | None
    minimum_from: str | None
    interest_12: Decimal
    planned: bool


class PlanOut(BaseModel):
    months: int | None
    interest: Decimal
    order: list[str]
    paid_in: dict[str, int]


class PayoffOut(BaseModel):
    extra: Decimal
    minimums: PlanOut
    avalanche: PlanOut
    snowball: PlanOut
    saved: Decimal


class SavingsOut(BaseModel):
    today: date
    months: list[RateMonthOut]
    rate_12: Decimal | None
    goals: GoalPlanOut
    safe: SafeOut
    debts: list[DebtOut]
    payoff: PayoffOut | None


class TermsIn(BaseModel):
    """A debt's yearly rate (a fraction: 0.156) and monthly payment; null forgets what was typed."""

    rate: Decimal | None = Field(default=None, ge=0, le=2, max_digits=6, decimal_places=4)
    minimum: Decimal | None = Field(
        default=None, ge=0, le=1_000_000, max_digits=12, decimal_places=2
    )


def _safe(s: savings.Safe) -> SafeOut:
    return SafeOut(
        month=s.month,
        left_so_far=s.left_so_far,
        income_to_come=s.income_to_come,
        bills_to_come=s.bills_to_come,
        goals_to_go=s.goals_to_go,
        days_left=s.days_left,
        amount=s.amount,
        a_day=s.a_day,
    )


def _plan(p: payoff.Plan) -> PlanOut:
    return PlanOut(months=p.months, interest=p.interest, order=p.order, paid_in=p.paid_in)


@router.get("", response_model=SavingsOut)
def get_savings(db: DB, today: Today = None, extra: Extra = Decimal(0)) -> SavingsOut:
    day = today or date.today()
    months = savings.rate_months(db, day)
    plan = savings.goal_plan(db, day)
    lines = savings.debts(db, day)
    compared = savings.payoff_plans(lines, extra)
    return SavingsOut(
        today=day,
        months=[
            RateMonthOut(
                month=m.month,
                money_in=m.money_in,
                spent=m.spent,
                set_aside=m.set_aside,
                kept=m.kept,
                rate=m.rate,
                running=m.running,
            )
            for m in months
        ],
        rate_12=savings.rate_of([m for m in months if not m.running]),
        goals=GoalPlanOut(
            needed=plan.needed,
            planned=plan.planned,
            saved=plan.saved,
            to_go=plan.to_go,
            short=plan.short,
            goals=[
                GoalNeedOut(
                    goal_id=g.goal_id,
                    name=g.name,
                    target_date=g.target_date,
                    left=g.left,
                    needed_monthly=g.needed_monthly,
                    monthly_amount=g.monthly_amount,
                    status=g.status,
                )
                for g in plan.open_goals
            ],
        ),
        safe=_safe(savings.safe_to_spend(db, day, plan)),
        debts=[
            DebtOut(
                key=d.key,
                name=d.name,
                kind=d.kind,
                balance=d.balance,
                as_of=d.as_of,
                rate=d.rate,
                minimum=d.minimum,
                rate_from=d.rate_from,
                minimum_from=d.minimum_from,
                interest_12=d.interest_12,
                planned=d.planned,
            )
            for d in lines
        ],
        payoff=PayoffOut(
            extra=extra,
            minimums=_plan(compared.minimums),
            avalanche=_plan(compared.avalanche),
            snowball=_plan(compared.snowball),
            saved=compared.saved,
        )
        if compared
        else None,
    )


@router.get("/safe-to-spend", response_model=SafeOut)
def safe_to_spend(db: DB, today: Today = None) -> SafeOut:
    """One number for Home: what is left for the rest of the month after bills and goals."""
    return _safe(savings.safe_to_spend(db, today or date.today()))


@router.put("/debts/{key}", status_code=status.HTTP_204_NO_CONTENT)
def set_terms(key: str, body: TermsIn, db: DB, request: Request, today: Today = None) -> None:
    user = (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()[:200]
    try:
        savings.set_terms(db, key, body.rate, body.minimum, user, today or date.today())
    except savings.SavingsError as e:
        raise HTTPException(e.status, str(e)) from e
