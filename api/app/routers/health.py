"""Health checks: the app alone (liveness) and the app with its database (readiness)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.config import get_settings
from app.db import get_engine, ping

router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    """Whether the app and the database answer, and which version runs."""

    status: str
    version: str
    git_sha: str
    environment: str
    database: str


class Me(BaseModel):
    """Who is signed in."""

    name: str | None
    authenticated: bool


def database_check() -> Callable[[], bool]:
    """Returns a callable so tests can swap the database probe without a real server."""

    def _check() -> bool:
        try:
            with get_engine().connect() as conn:
                return ping(conn)
        # Not configured, asleep, unreachable or refusing: all of them mean "not ready".
        except (SQLAlchemyError, OSError, RuntimeError):
            return False

    return _check


@router.get("/health", response_model=Health)
def health(
    response: Response, check: Annotated[Callable[[], bool], Depends(database_check)]
) -> Health:
    """Whether the app and its database answer; 503 while the database is asleep or unreachable."""
    settings = get_settings()
    db_ok = check()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Health(
        status="ok" if db_ok else "degraded",
        version=__version__,
        git_sha=settings.git_sha,
        environment=settings.app_env,
        database="ok" if db_ok else "unavailable",
    )


@router.get("/me", response_model=Me)
def me(request: Request) -> Me:
    # Azure Container Apps built-in auth injects this header for signed-in users.
    """Who is signed in, as Container Apps reports it."""
    name = request.headers.get("x-ms-client-principal-name")
    return Me(name=name, authenticated=name is not None)
