"""Allow-list on top of Azure Container Apps built-in authentication.

Container Apps auth signs people in and passes their identity in the
X-MS-CLIENT-PRINCIPAL-NAME header; this middleware only lets the household's
accounts through. Health stays open so deploy smoke tests and probes work.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings

OPEN_PATHS = frozenset({"/api/health"})
PRINCIPAL_HEADER = "x-ms-client-principal-name"


async def allow_list(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    allowed = get_settings().allowed_email_set
    if not allowed or request.url.path in OPEN_PATHS:
        return await call_next(request)
    principal = (request.headers.get(PRINCIPAL_HEADER) or "").strip().lower()
    if principal not in allowed:
        return JSONResponse({"detail": "This account is not allowed."}, status_code=403)
    return await call_next(request)
