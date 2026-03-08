"""LLM Agent service configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings

from shared.config import BaseServiceConfig, GrpcServerConfig, GrpcClientConfig


class LLMAgentConfig(BaseServiceConfig, GrpcServerConfig):
    """Configuration for the LLM Agent service."""

    service_name: str = "llm-agent"

    # LLM model settings
    primary_model: str = "gemini/gemini-2.5-flash"
    fallback_model: str = "gemini/gemini-2.0-flash"
    temperature: float = 0.3
    max_tokens: int = 1024
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    # Streaming
    stream: bool = True

    # Token budget per session
    max_context_tokens: int = 8192
    max_history_turns: int = 20

    # Timeout per LLM call (ms)
    llm_timeout_ms: int = 15000

    # Fallback settings
    enable_fallback: bool = True
    fallback_on_status_codes: list[int] = [429, 500, 502, 503]

    # Tool orchestrator gRPC target
    tool_orchestrator_host: str = "tool-orchestrator"
    tool_orchestrator_port: int = 8091
    tool_orchestrator_timeout_ms: int = 5000

    # Safety filter
    safety_filter_enabled: bool = True
    max_input_length: int = 4096
    max_message_count: int = 50

    # Circuit breaker
    circuit_breaker_fail_max: int = 3
    circuit_breaker_reset_timeout: int = 30

    # gRPC
    grpc_port: int = 8090
    grpc_max_workers: int = 10

    # FastAPI health/metrics HTTP port
    http_port: int = 8190

    # Summarization
    summary_model: str = "gemini/gemini-2.0-flash"
    summary_max_tokens: int = 512

    model_config = {"env_prefix": "LLM_", "case_sensitive": False}


def get_config() -> LLMAgentConfig:
    """Get cached LLM Agent configuration instance."""
    return LLMAgentConfig()
