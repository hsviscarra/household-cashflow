"""Ask Claude inside the app (ADR-100)."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.services import ask

router = APIRouter(prefix="/api/ask", tags=["ask"])
DB = Annotated[Session, Depends(get_session)]
Today = Annotated[date | None, Query(description="For tests; default today")]


class QuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=ask.MAX_QUESTION)
    page: str | None = Field(default=None, max_length=100, pattern=r"^/[A-Za-z0-9/_-]*$")
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    deep: bool = False  # the larger model, for analysis


class UsageOut(BaseModel):
    available: bool
    month: date
    spent: Decimal
    questions: int
    cap: Decimal
    left: Decimal


class AnswerOut(BaseModel):
    answer: str
    cost: Decimal
    tools_used: list[str]
    usage: UsageOut


class CapIn(BaseModel):
    cap: Decimal = Field(ge=0, le=1000, max_digits=7, decimal_places=2)


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()[:200]


def _usage(u: ask.Usage) -> UsageOut:
    return UsageOut(
        available=ask.available(),
        month=u.month,
        spent=u.spent,
        questions=u.questions,
        cap=u.cap,
        left=u.left,
    )


@router.get("/usage", response_model=UsageOut)
def get_usage(db: DB, today: Today = None) -> UsageOut:
    return _usage(ask.usage(db, today or date.today()))


@router.put("/cap", response_model=UsageOut)
def set_cap(body: CapIn, db: DB, request: Request, today: Today = None) -> UsageOut:
    ask.set_cap(db, body.cap, _user(request))
    return _usage(ask.usage(db, today or date.today()))


@router.post("", response_model=AnswerOut)
def post_question(body: QuestionIn, db: DB, request: Request, today: Today = None) -> AnswerOut:
    try:
        a = ask.ask(
            db,
            body.question,
            _user(request),
            today=today,
            page=body.page,
            month=body.month,
            deep=body.deep,
        )
    except ask.AskError as e:
        raise HTTPException(e.status, str(e)) from e
    return AnswerOut(answer=a.text, cost=a.cost, tools_used=a.tools_used, usage=_usage(a.usage))
