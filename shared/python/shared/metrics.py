"""Prometheus metrics helpers for all services."""

from prometheus_client import Counter, Gauge, Histogram, Info


def create_request_metrics(service_name: str) -> dict:
    """Create standard request metrics for a service.

    Args:
        service_name: Service name for metric labels.

    Returns:
        Dict of metric objects.
    """
    return {
        "info": Info(
            f"{service_name}_info",
            f"Service info for {service_name}",
        ),
        "requests_total": Counter(
            f"{service_name}_requests_total",
            "Total requests",
            ["method", "endpoint", "status"],
        ),
        "request_duration": Histogram(
            f"{service_name}_request_duration_seconds",
            "Request duration in seconds",
            ["method", "endpoint"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        ),
        "active_connections": Gauge(
            f"{service_name}_active_connections",
            "Number of active connections",
        ),
        "errors_total": Counter(
            f"{service_name}_errors_total",
            "Total errors",
            ["error_type"],
        ),
    }


def create_grpc_metrics(service_name: str) -> dict:
    """Create gRPC-specific metrics.

    Args:
        service_name: Service name for metric labels.

    Returns:
        Dict of gRPC metric objects.
    """
    return {
        "grpc_requests_total": Counter(
            f"{service_name}_grpc_requests_total",
            "Total gRPC requests",
            ["method", "status"],
        ),
        "grpc_duration": Histogram(
            f"{service_name}_grpc_duration_seconds",
            "gRPC request duration",
            ["method"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        ),
        "grpc_stream_messages": Counter(
            f"{service_name}_grpc_stream_messages_total",
            "Total gRPC stream messages",
            ["method", "direction"],
        ),
    }
