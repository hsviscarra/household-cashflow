from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app import __version__
from app.auth import allow_list
from app.config import get_settings
from app.routers import (
    batches,
    classify,
    health,
    history,
    recurring,
    reference,
    statements,
    transfers,
)


class SPAStaticFiles(StaticFiles):
    """Serves the React build; unknown paths fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def create_app() -> FastAPI:
    app = FastAPI(title="Household Cash Flow", version=__version__)
    app.middleware("http")(allow_list)
    app.include_router(health.router)
    app.include_router(reference.router)
    app.include_router(history.router)
    app.include_router(statements.router)
    app.include_router(batches.router)
    app.include_router(classify.router)
    app.include_router(transfers.router)
    app.include_router(recurring.router)

    # The built React app is served from the same origin, so one Container App hosts both.
    dist = Path(get_settings().web_dist_dir)
    if dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
