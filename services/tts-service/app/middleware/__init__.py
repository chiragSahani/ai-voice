"""TTS service middleware."""

from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_id import RequestIdMiddleware

__all__ = ["ErrorHandlerMiddleware", "RequestIdMiddleware"]
