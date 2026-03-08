"""OpenTelemetry distributed tracing setup."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(service_name: str, otlp_endpoint: str = "http://jaeger:4317") -> None:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Name of the service for trace context.
        otlp_endpoint: OTLP collector endpoint.
    """
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance.

    Args:
        name: Tracer name (typically module name).

    Returns:
        OpenTelemetry Tracer.
    """
    return trace.get_tracer(name)
