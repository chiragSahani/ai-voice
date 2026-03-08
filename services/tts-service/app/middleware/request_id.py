"""Request ID middleware for tracing HTTP requests.

Extracts or generates a unique request ID for each incoming HTTP request
and binds it to the structured logging context.
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

import structlog


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Adds a unique request ID to every HTTP request/response cycle."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Use existing X-Request-ID header or generate a new one
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))

        # Bind to structlog context for all log entries in this request
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # Clear the request-scoped context
        structlog.contextvars.unbind_contextvars("request_id")

        return response
