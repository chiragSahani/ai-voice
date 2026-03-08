"""gRPC server and client utilities."""

import time
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from shared.logging import get_logger

logger = get_logger("grpc")


def create_grpc_server(
    port: int = 50051,
    max_workers: int = 10,
    max_message_length: int = 10 * 1024 * 1024,
) -> grpc.aio.Server:
    """Create an async gRPC server with health checking.

    Args:
        port: Port to listen on.
        max_workers: Maximum thread pool workers.
        max_message_length: Max message size in bytes.

    Returns:
        Configured gRPC async server (not yet started).
    """
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ("grpc.max_send_message_length", max_message_length),
            ("grpc.max_receive_message_length", max_message_length),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
        ],
    )

    # Add health service
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    server.add_insecure_port(f"[::]:{port}")

    logger.info("grpc_server_created", port=port, max_workers=max_workers)
    return server


def create_grpc_channel(
    target: str,
    timeout_ms: int = 5000,
) -> grpc.aio.Channel:
    """Create an async gRPC channel with keepalive.

    Args:
        target: Service address (host:port).
        timeout_ms: Default timeout in milliseconds.

    Returns:
        gRPC async channel.
    """
    options = [
        ("grpc.keepalive_time_ms", 30000),
        ("grpc.keepalive_timeout_ms", 10000),
        ("grpc.keepalive_permit_without_calls", True),
        ("grpc.default_timeout_ms", timeout_ms),
        ("grpc.max_receive_message_length", 10 * 1024 * 1024),
    ]

    channel = grpc.aio.insecure_channel(target, options=options)
    logger.info("grpc_channel_created", target=target)
    return channel


class TimingInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Client interceptor that logs request duration."""

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        start = time.monotonic()
        response = await continuation(client_call_details, request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.debug(
            "grpc_client_call",
            method=client_call_details.method,
            duration_ms=round(duration_ms, 2),
        )
        return response
