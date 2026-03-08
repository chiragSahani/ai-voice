"""Request ID middleware for distributed tracing."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

import structlog


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Injects a request ID into every request for tracing.

    Checks for an existing X-Request-ID header (from upstream gateways)
    or generates a new UUID.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))

        # Bind request ID to structured logging context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # Clear per-request context
        structlog.contextvars.unbind_contextvars("request_id")

        return response
