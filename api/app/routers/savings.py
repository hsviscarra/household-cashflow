"""Saving on one page, and what is safe to spend (ADR-097)."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.session import get_session
from app.services import payoff, savings

router = APIRouter(prefix="/api/savings", tags=["savings"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(description="For tests; default today")]
Extra = Annotated[
    Decimal, Query(ge=0, le=savings.MAX_AMOUNT, description="Extra toward debts each month")
]


class RateMonthOut(BaseModel):
    """One month of the savings rate."""

    month: date
    money_in: Decimal
    spent: Decimal
    set_aside: Decimal
    kept: Decimal
    rate: Decimal | None
    running: bool


class GoalNeedOut(BaseModel):
    """What one goal needs a month."""

    goal_id: int
    name: str
    target_date: date | None
    left: Decimal
    needed_monthly: Decimal | None
    monthly_amount: Decimal | None
    status: str


class GoalPlanOut(BaseModel):
    """The goals together: needed, planned, saved and still to go."""

    needed: Decimal
    planned: Decimal
    saved: Decimal
    to_go: Decimal
    short: Decimal
    goals: list[GoalNeedOut]


class SafeOut(BaseModel):
    """Safe to spend, with the four amounts it is made of."""

    month: date
    left_so_far: Decimal
    income_to_come: Decimal
    bills_to_come: Decimal
    goals_to_go: Decimal
    days_left: int
    amount: Decimal
    a_day: Decimal


class DebtOut(BaseModel):
    """One debt with its terms and where each came from."""

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
    """One way of paying the debts off."""

    months: int | None
    interest: Decimal
    order: list[str]
    paid_in: dict[str, int]


class PayoffOut(BaseModel):
    """The three ways compared, for an extra amount a month."""

    extra: Decimal
    minimums: PlanOut
    avalanche: PlanOut
    snowball: PlanOut
    saved: Decimal


class SavingsOut(BaseModel):
    """Everything the Saving page shows."""

    today: date
    months: list[RateMonthOut]
    rate_12: Decimal | None
    goals: GoalPlanOut
    safe: SafeOut
    debts: list[DebtOut]
    payoff: PayoffOut | None


class TermsIn(BaseModel):
    """A debt's yearly rate (a fraction: 0.156) and monthly payment; null forgets what was typed."""

    rate: Decimal | None = Field(
        default=None, ge=0, le=savings.MAX_RATE, max_digits=6, decimal_places=4
    )
    minimum: Decimal | None = Field(
        default=None, ge=0, le=savings.MAX_AMOUNT, max_digits=12, decimal_places=2
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
    """The Saving page: rate by month, goals, safe to spend, debts and the payoff orders
    for `extra` a month on top of the payments."""
    day = today or date.today()
    months = savings.rate_months(db, day)
    plan = savings.goal_plan(db, day)
    lines = savings.debts(db, day)
    compared = savings.payoff_plans(lines, extra)
    return SavingsOut(
        today=day,
        months=[_month(m) for m in months],
        rate_12=savings.rate_of([m for m in months if not m.running]),
        goals=_goals(plan),
        safe=_safe(savings.safe_to_spend(db, day, plan)),
        debts=[_debt(d) for d in lines],
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


def _month(m: savings.RateMonth) -> RateMonthOut:
    return RateMonthOut(
        month=m.month,
        money_in=m.money_in,
        spent=m.spent,
        set_aside=m.set_aside,
        kept=m.kept,
        rate=m.rate,
        running=m.running,
    )


def _goals(plan: savings.GoalPlan) -> GoalPlanOut:
    return GoalPlanOut(
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
    )


def _debt(d: savings.DebtLine) -> DebtOut:
    return DebtOut(
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


@router.get("/safe-to-spend", response_model=SafeOut)
def safe_to_spend(db: DB, today: Today = None) -> SafeOut:
    """One number for Home: what is left for the rest of the month after bills and goals."""
    return _safe(savings.safe_to_spend(db, today or date.today()))


@router.put("/debts/{key}", status_code=status.HTTP_204_NO_CONTENT)
def set_terms(key: str, body: TermsIn, db: DB, request: Request, today: Today = None) -> None:
    """Keep a debt's yearly rate and monthly payment as typed; both null forgets them."""
    try:
        savings.set_terms(
            db, key, body.rate, body.minimum, current_user(request), today or date.today()
        )
    except savings.SavingsError as e:
        raise HTTPException(e.status, str(e)) from e
