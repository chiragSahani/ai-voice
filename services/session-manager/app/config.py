"""Session Manager service configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings

from shared.config import BaseServiceConfig, RedisConfig


class SessionManagerConfig(BaseServiceConfig, RedisConfig):
    """Configuration for the Session Manager service."""

    service_name: str = "session-manager"

    # HTTP server
    port: int = 6380
    host: str = "0.0.0.0"

    # Session settings
    session_ttl_seconds: int = 3600
    max_turns: int = 50
    context_max_tokens: int = 4000

    # Summarization
    summarize_threshold: int = 30
    summary_keep_recent: int = 10

    # Pagination defaults
    default_page_size: int = 20
    max_page_size: int = 100

    model_config = {"env_prefix": "SESSION_", "case_sensitive": False}


def get_config() -> SessionManagerConfig:
    """Get cached Session Manager configuration instance."""
    return SessionManagerConfig()
