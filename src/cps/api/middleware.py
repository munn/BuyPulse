"""Custom middleware for the admin API."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_CSRF_EXEMPT = {"/api/v1/auth/login"}
_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject mutating requests without X-Requested-With header."""

    async def dispatch(self, request: Request, call_next):
        if (
            request.method in _MUTATING_METHODS
            and request.url.path not in _CSRF_EXEMPT
            and request.headers.get("x-requested-with") != "XMLHttpRequest"
        ):
            return JSONResponse(
                {"detail": "CSRF validation failed", "code": "CSRF_FAILED"},
                status_code=403,
            )
        return await call_next(request)
