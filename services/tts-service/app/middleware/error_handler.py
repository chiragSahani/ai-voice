"""Global error handling middleware for the FastAPI HTTP layer.

Catches unhandled exceptions and maps shared exception types to
appropriate HTTP responses with structured JSON bodies.
"""

import traceback

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from shared.exceptions import BaseServiceError
from shared.logging import get_logger

logger = get_logger("error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catches exceptions and returns structured JSON error responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
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
                    "error": {
                        "code": e.code,
                        "message": e.message,
                    }
                },
            )
        except Exception as e:
            logger.error(
                "unhandled_error",
                error=str(e),
                path=request.url.path,
                traceback=traceback.format_exc(),
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An internal error occurred",
                    }
                },
            )
