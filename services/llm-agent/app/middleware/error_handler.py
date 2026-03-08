"""gRPC error handling interceptor for the LLM Agent service."""

import traceback

import grpc

from shared.exceptions import (
    BaseServiceError,
    CircuitOpenError,
    ServiceUnavailableError,
    ValidationError,
)
from shared.logging import get_logger

logger = get_logger("error_handler")

# Map internal error codes to gRPC status codes
_ERROR_CODE_MAP = {
    "VALIDATION_ERROR": grpc.StatusCode.INVALID_ARGUMENT,
    "NOT_FOUND": grpc.StatusCode.NOT_FOUND,
    "CONFLICT": grpc.StatusCode.ALREADY_EXISTS,
    "UNAUTHORIZED": grpc.StatusCode.UNAUTHENTICATED,
    "FORBIDDEN": grpc.StatusCode.PERMISSION_DENIED,
    "RATE_LIMITED": grpc.StatusCode.RESOURCE_EXHAUSTED,
    "SERVICE_UNAVAILABLE": grpc.StatusCode.UNAVAILABLE,
    "CIRCUIT_OPEN": grpc.StatusCode.UNAVAILABLE,
    "INTERNAL_ERROR": grpc.StatusCode.INTERNAL,
}


class ErrorHandlerInterceptor(grpc.aio.ServerInterceptor):
    """Server-side interceptor that catches exceptions and converts them to gRPC status codes."""

    async def intercept_service(self, continuation, handler_call_details):
        """Intercept incoming RPCs to handle errors uniformly.

        Args:
            continuation: Next handler in the chain.
            handler_call_details: RPC call metadata.

        Returns:
            Handler with error wrapping.
        """
        handler = await continuation(handler_call_details)

        if handler is None:
            return handler

        if handler.unary_unary:
            return _wrap_unary_handler(handler)
        elif handler.unary_stream:
            return _wrap_stream_handler(handler)

        return handler


def _wrap_unary_handler(handler):
    """Wrap a unary-unary handler with error handling."""

    async def wrapper(request, context):
        try:
            return await handler.unary_unary(request, context)
        except BaseServiceError as err:
            grpc_code = _ERROR_CODE_MAP.get(err.code, grpc.StatusCode.INTERNAL)
            logger.error(
                "service_error",
                error_code=err.code,
                message=err.message,
                grpc_status=grpc_code.name,
            )
            await context.abort(grpc_code, err.message)
        except Exception as err:
            logger.error(
                "unhandled_error",
                error=str(err),
                traceback=traceback.format_exc(),
            )
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Internal server error",
            )

    return grpc.unary_unary_rpc_method_handler(
        wrapper,
        request_deserializer=handler.request_deserializer,
        response_serializer=handler.response_serializer,
    )


def _wrap_stream_handler(handler):
    """Wrap a unary-stream handler with error handling."""

    async def wrapper(request, context):
        try:
            async for response in handler.unary_stream(request, context):
                yield response
        except BaseServiceError as err:
            grpc_code = _ERROR_CODE_MAP.get(err.code, grpc.StatusCode.INTERNAL)
            logger.error(
                "service_error_stream",
                error_code=err.code,
                message=err.message,
            )
            await context.abort(grpc_code, err.message)
        except Exception as err:
            logger.error(
                "unhandled_error_stream",
                error=str(err),
                traceback=traceback.format_exc(),
            )
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Internal server error",
            )

    return grpc.unary_stream_rpc_method_handler(
        wrapper,
        request_deserializer=handler.request_deserializer,
        response_serializer=handler.response_serializer,
    )
