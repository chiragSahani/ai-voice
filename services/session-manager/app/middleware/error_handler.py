"""Global error handling middleware for the Session Manager service."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from shared.exceptions import BaseServiceError
from shared.logging import get_logger

logger = get_logger("error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catches exceptions and returns structured JSON error responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            response = await call_next(request)
            return response
        except BaseServiceError as e:
            logger.warning(
                "service_error",
                code=e.code,
                message=e.message,
                status_code=e.status_code,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": e.code,
                    "code": e.code,
                    "detail": e.message,
                },
            )
        except Exception as e:
            logger.exception(
                "unhandled_error",
                error=str(e),
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_ERROR",
                    "code": "INTERNAL_ERROR",
                    "detail": "An unexpected error occurred",
                },
            )
