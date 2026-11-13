"""The FastAPI app: its routers, its start-up and the built web app it serves."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app import __version__
from app.auth import allow_list
from app.config import get_settings
from app.mcp_server import http_endpoint
from app.routers import (
    ask,
    bank_sync,
    batches,
    budget,
    classify,
    close,
    costs,
    explore,
    gastos,
    goals,
    health,
    history,
    inbox,
    investments,
    invoices,
    iva,
    me,
    networth,
    outlook,
    people,
    projections,
    reconcile,
    recurring,
    reference,
    report,
    savings,
    spending,
    statements,
    status,
    tax_projection,
    todo,
    transfers,
)


class SPAStaticFiles(StaticFiles):
    """Serves the React build; unknown paths fall back to index.html for client-side routes.

    The page itself (index.html) is never reused without asking the server, so a new release
    shows up on the next visit; the hashed files under assets/ never change and are kept a year.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve the file asked for, or the web app's index for any path that isn't a file or the
        API."""
        try:
            resp = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            resp = await super().get_response("index.html", scope)
        if path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif resp.media_type == "text/html" or "text/html" in resp.headers.get("content-type", ""):
            resp.headers["Cache-Control"] = "no-cache"
        return resp


def create_app() -> FastAPI:
    # Claude's read-only MCP endpoint (F18): its session manager runs with the app.
    """Build the app: the API's routers, the allow-list, Claude's MCP endpoint and the built web
    app."""
    mcp_route, mcp_manager = http_endpoint()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp_manager.run():
            yield

    app = FastAPI(title="Household Cash Flow", version=__version__, lifespan=lifespan)
    app.middleware("http")(allow_list)
    app.include_router(health.router)
    app.include_router(reference.router)
    app.include_router(history.router)
    app.include_router(statements.router)
    app.include_router(batches.router)
    app.include_router(classify.router)
    app.include_router(transfers.router)
    app.include_router(people.router)
    app.include_router(me.router)
    app.include_router(recurring.router)
    app.include_router(status.router)
    app.include_router(spending.router)
    app.include_router(costs.router)
    app.include_router(inbox.router)
    app.include_router(networth.router)
    app.include_router(projections.router)
    app.include_router(investments.router)
    app.include_router(invoices.router)
    app.include_router(gastos.router)
    app.include_router(iva.router)
    app.include_router(budget.router)
    app.include_router(goals.router)
    app.include_router(report.router)
    app.include_router(bank_sync.router)
    app.include_router(todo.router)
    app.include_router(close.router)
    app.include_router(tax_projection.router)
    app.include_router(reconcile.router)
    app.include_router(savings.router)
    app.include_router(outlook.router)
    app.include_router(explore.router)
    app.include_router(ask.router)

    app.router.routes.append(mcp_route)

    # The built React app is served from the same origin, so one Container App hosts both.
    dist = Path(get_settings().web_dist_dir)
    if dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
