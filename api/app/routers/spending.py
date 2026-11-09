"""Spending analytics (F13, ADR-010): one month's spending with MoM, YoY and drill-down."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
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
from app.services import groceries, shopping, spending

router = APIRouter(prefix="/api/spending", tags=["spending"])
DB = Annotated[Session, Depends(get_session)]
Month = Annotated[date | None, Query(description="Any day of the month; default the latest")]
# The Both/Hernan/Lauren switch (ADR-026): one person's lines, or everyone's when left out.
Person = Annotated[Literal["Hernan", "Lauren", "Joint"] | None, Query()]


@router.get("", response_model=SpendingOut)
def get_spending(db: DB, month: Month = None, person: Person = None) -> SpendingOut:
    s = spending.analyze(db, month, person)
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


# ---------- one level deeper (ADR-028): merchants, products and ways to save ----------


class MerchantRowOut(BaseModel):
    merchant: str
    group_id: int
    group_name: str
    amount: Decimal
    visits: int
    avg_ticket: Decimal
    invoices: int


class ProductRowOut(BaseModel):
    product_key: str
    description: str
    product_group: str | None
    times: int
    quantity: Decimal
    amount: Decimal
    unit_price: Decimal
    before: Decimal | None
    change: Decimal | None
    stores: list[str]
    cheaper_store: str | None
    cheaper_price: Decimal | None
    could_save: Decimal


class IdeaOut(BaseModel):
    key: str
    title: str
    detail: str
    amount: Decimal
    count: int
    link: str | None


@router.get("/merchants", response_model=list[MerchantRowOut])
def get_merchants(
    db: DB,
    month: date,
    person: Person = None,
    group_id: int | None = None,
    category_id: int | None = None,
) -> list[MerchantRowOut]:
    """A month's merchants with visits, average ticket and how many invoices back them."""
    rows = shopping.merchants(db, month, person, group_id, category_id)
    return [
        MerchantRowOut(**{k: v for k, v in asdict(r).items() if k != "transaction_ids"})
        for r in rows
    ]


@router.get("/products", response_model=list[ProductRowOut])
def get_products(
    db: DB, month: date, product_group: str | None = None, store: str | None = None
) -> list[ProductRowOut]:
    """A month's products from the SRI invoices, with the price before and a cheaper store."""
    return [ProductRowOut(**asdict(p)) for p in shopping.products(db, month, product_group, store)]


@router.get("/groceries")
def get_groceries(db: DB, month: date) -> dict[str, Any]:
    """Groceries (ADR-059): the month's supermarket spending next to what its invoices say it
    bought: by aisle, top products, stores, and the charges whose invoice hasn't arrived."""
    return asdict(groceries.build(db, month))


@router.get("/ideas", response_model=list[IdeaOut])
def get_ideas(db: DB, month: date, person: Person = None) -> list[IdeaOut]:
    """Ways to save, read from the month's own lines."""
    return [IdeaOut(**asdict(i)) for i in shopping.ideas(db, month, person)]
