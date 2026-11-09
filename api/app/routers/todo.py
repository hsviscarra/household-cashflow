"""To do (ADR-047): everything that needs someone, in one list."""

from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.services import todo

router = APIRouter(prefix="/api/todo", tags=["to do"])
DB = Annotated[Session, Depends(get_session)]


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


@router.get("")
def to_do(
    db: DB, today: Annotated[date | None, Query(include_in_schema=False)] = None
) -> dict[str, Any]:
    """Sections of things to do, each task with its kind, what it is, where it is and what the
    page needs to act on it; total counts every thing, also those past the first 25 shown."""
    t = todo.build(db, today)
    return {
        "today": t.today,
        "total": t.total,
        "sections": [asdict(s) for s in t.sections],
    }


class DismissIn(BaseModel):
    key: str = Field(min_length=1, max_length=400)


@router.post("/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss(body: DismissIn, db: DB, request: Request) -> Response:
    """Let a suggestion or an out-of-date value go (ADR-058): it isn't asked again."""
    todo.dismiss(db, body.key, _user(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
