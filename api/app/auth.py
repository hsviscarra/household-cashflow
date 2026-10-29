"""Allow-list on top of Azure Container Apps built-in authentication.

Container Apps auth signs people in and passes their identity in the
X-MS-CLIENT-PRINCIPAL-NAME header; this middleware only lets the household's
accounts through. Health stays open so deploy smoke tests and probes work. Two endpoints check a
bearer token instead of a person: Claude's /mcp (F18) and the Gmail script's /api/inbox (F20).
"""

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings

OPEN_PATHS = frozenset({"/api/health"})
MCP_PATH = "/mcp"  # Claude's endpoint (F18): a bearer token instead of a signed-in person
INBOX_PATH = "/api/inbox"  # the Gmail script's statement drop (F20): its own bearer token
PRINCIPAL_HEADER = "x-ms-client-principal-name"


async def allow_list(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    settings = get_settings()
    path = request.url.path.rstrip("/")
    if path == MCP_PATH:
        return await _bearer(request, call_next, settings.mcp_token, "The MCP endpoint is off.")
    if path == INBOX_PATH:
        return await _bearer(request, call_next, settings.inbox_token, "The inbox is off.")
    allowed = settings.allowed_email_set
    if not allowed or request.url.path in OPEN_PATHS:
        return await call_next(request)
    principal = (request.headers.get(PRINCIPAL_HEADER) or "").strip().lower()
    if principal not in allowed:
        return JSONResponse({"detail": "This account is not allowed."}, status_code=403)
    return await call_next(request)


async def _bearer(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    token: str,
    off: str,
) -> Response:
    """A token endpoint needs its bearer token; without one configured the endpoint is off."""
    if not token:
        return JSONResponse({"detail": off}, status_code=404)
    given = request.headers.get("authorization", "")
    expected = f"Bearer {token}"
    if not hmac.compare_digest(given.encode(), expected.encode()):
        return JSONResponse(
            {"detail": "A valid bearer token is required."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)
