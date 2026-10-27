"""Subscriptions and the cost of debt (F14, ADR-011)."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas import ChargeOut, DebtAccountOut, DebtOut, SubscriptionOut, SubscriptionsOut
from app.services import debt, subscriptions

router = APIRouter(prefix="/api", tags=["costs"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(description="For tests: the day to look back from")]


@router.get("/subscriptions", response_model=SubscriptionsOut)
def get_subscriptions(db: DB, today: Today = None) -> SubscriptionsOut:
    found = subscriptions.find(db, today)
    steady = [s for s in found if s.active and s.cadence != "possible"]
    return SubscriptionsOut(
        monthly_cost=sum((s.monthly_cost for s in steady), Decimal(0)),
        weekly_monthly_cost=sum(
            (s.monthly_cost for s in steady if s.cadence == "weekly"), Decimal(0)
        ),
        subscriptions=[
            SubscriptionOut(
                merchant=s.merchant,
                cadence=s.cadence,  # type: ignore[arg-type]
                typical=s.typical,
                monthly_cost=s.monthly_cost,
                yearly_cost=s.yearly_cost,
                category_path=s.category_path,
                accounts=s.accounts,
                charges=[ChargeOut(**asdict(c)) for c in s.charges],
                last=s.last,
                next_expected=s.next_expected,
                active=s.active,
            )
            for s in found
        ],
    )


@router.get("/debt", response_model=DebtOut)
def get_debt(
    db: DB,
    year: Annotated[int | None, Query(ge=2019, le=2100)] = None,
    today: Today = None,
) -> DebtOut:
    d = debt.cost(db, year, today)
    return DebtOut(
        year=d.year,
        years=d.years,
        through=d.through,
        months=d.months,
        interest=d.interest,
        fees=d.fees,
        accounts=[
            DebtAccountOut(
                account_id=a.account_id,
                name=a.name,
                kind=a.kind,
                interest=a.interest,
                fees=a.fees,
                total=a.total,
                last_12=a.last_12,
                by_category=a.by_category,
                by_month=a.by_month,
                balance=a.balance,
                balance_date=a.balance_date,
            )
            for a in d.accounts
        ],
    )
