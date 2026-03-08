"""Tool Orchestrator service configuration."""

from pydantic_settings import BaseSettings

from shared.config import BaseServiceConfig, GrpcServerConfig


class ToolOrchestratorConfig(BaseServiceConfig, GrpcServerConfig):
    """Configuration for the Tool Orchestrator service."""

    service_name: str = "tool-orchestrator"

    # gRPC server
    grpc_port: int = 8091
    grpc_max_workers: int = 10

    # FastAPI health/metrics HTTP port
    http_port: int = 8092

    # Downstream service URLs
    appointment_scheduler_url: str = "http://appointment-scheduler:3010"
    patient_memory_url: str = "http://patient-memory:3020"

    # HTTP client settings
    request_timeout: float = 5.0
    request_max_retries: int = 2
    request_retry_backoff: float = 0.5

    # Circuit breaker settings
    circuit_breaker_fail_max: int = 3
    circuit_breaker_reset_timeout: int = 30

    # Tool execution settings
    tool_execution_timeout: float = 10.0
    batch_max_concurrent: int = 5

    model_config = {"env_prefix": "TOOL_", "case_sensitive": False}


def get_config() -> ToolOrchestratorConfig:
    """Get cached Tool Orchestrator configuration instance."""
    return ToolOrchestratorConfig()
