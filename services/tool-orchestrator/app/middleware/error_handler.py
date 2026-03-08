"""Global error-handling middleware for the FastAPI application."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from shared.exceptions import BaseServiceError
from shared.logging import get_logger

logger = get_logger("error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured JSON error responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        try:
            return await call_next(request)
        except BaseServiceError as exc:
            logger.warning(
                "service_error",
                code=exc.code,
                message=exc.message,
                status=exc.status_code,
                path=str(request.url.path),
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": exc.code,
                    "message": exc.message,
                },
            )
        except Exception as exc:
            logger.exception(
                "unhandled_error",
                error=str(exc),
                path=str(request.url.path),
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                },
            )
