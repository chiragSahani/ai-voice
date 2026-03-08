"""Request ID middleware for gRPC calls."""

import uuid

import grpc
import structlog

from shared.logging import get_logger

logger = get_logger("request_id")


class RequestIdInterceptor(grpc.aio.ServerInterceptor):
    """Server interceptor that assigns a unique request ID to each RPC.

    The request ID is added to structlog context for correlation across logs.
    Clients can pass a request ID via the 'x-request-id' metadata header;
    otherwise one is generated.
    """

    async def intercept_service(self, continuation, handler_call_details):
        """Extract or generate request ID and bind to log context.

        Args:
            continuation: Next handler in chain.
            handler_call_details: RPC metadata.

        Returns:
            Handler with request ID context.
        """
        # Try to extract request ID from metadata
        request_id = None
        if handler_call_details.invocation_metadata:
            for key, value in handler_call_details.invocation_metadata:
                if key == "x-request-id":
                    request_id = value
                    break

        if not request_id:
            request_id = str(uuid.uuid4())

        # Bind to structlog context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        return await continuation(handler_call_details)
