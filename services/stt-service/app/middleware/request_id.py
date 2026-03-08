"""Request ID middleware for HTTP request tracing."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

import structlog


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Injects a unique request ID into each HTTP request for tracing.

    If the client sends an X-Request-ID header, it is reused.
    Otherwise, a new UUID is generated.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid.uuid4())

        # Bind request_id to structlog context for all downstream log calls
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
            response.headers[self.HEADER_NAME] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
