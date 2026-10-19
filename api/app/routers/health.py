from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app import __version__
from app.config import get_settings
from app.db import get_engine, ping

router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    status: str
    version: str
    git_sha: str
    environment: str
    database: str


class Me(BaseModel):
    name: str | None
    authenticated: bool


def database_check() -> Callable[[], bool]:
    """Returns a callable so tests can swap the database probe without a real server."""

    def _check() -> bool:
        try:
            with get_engine().connect() as conn:
                return ping(conn)
        except Exception:
            return False

    return _check


@router.get("/health", response_model=Health)
def health(
    response: Response, check: Annotated[Callable[[], bool], Depends(database_check)]
) -> Health:
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
    name = request.headers.get("x-ms-client-principal-name")
    return Me(name=name, authenticated=name is not None)
