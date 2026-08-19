import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response

from app.core.logging import reset_request_id, set_request_id

logger = logging.getLogger("app.request")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _resolve_request_id(request: Request) -> str:
    incoming_request_id = request.headers.get("X-Request-ID", "").strip()

    if _REQUEST_ID_PATTERN.fullmatch(incoming_request_id):
        return incoming_request_id

    return uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _resolve_request_id(request)
        request.state.request_id = request_id

        token = set_request_id(request_id)
        started_at = perf_counter()

        try:
            response = await call_next(request)
            duration_ms = round((perf_counter() - started_at) * 1000, 2)

            response.headers["X-Request-ID"] = request_id

            logger.info(
                "Request completed: %s %s -> %s in %.2f ms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response
        finally:
            reset_request_id(token)
