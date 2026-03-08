"""Base configuration using Pydantic Settings for all Python services."""

from pydantic_settings import BaseSettings


class BaseServiceConfig(BaseSettings):
    """Base configuration shared across all Python services."""

    # Service identity
    service_name: str = "unknown"
    service_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "info"

    # Redis
    redis_url: str = "redis://redis:6379"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017/clinic_db"
    mongodb_database: str = "clinic_db"

    # Observability
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"
    metrics_enabled: bool = True

    model_config = {"env_prefix": "", "case_sensitive": False}


class RedisConfig(BaseSettings):
    """Redis-specific configuration."""

    redis_url: str = "redis://redis:6379"
    redis_password: str = ""
    redis_max_connections: int = 10
    redis_socket_timeout: float = 5.0
    redis_retry_on_timeout: bool = True

    model_config = {"env_prefix": "", "case_sensitive": False}


class GrpcServerConfig(BaseSettings):
    """gRPC server configuration."""

    grpc_port: int = 50051
    grpc_max_workers: int = 10
    grpc_max_message_length: int = 10 * 1024 * 1024  # 10MB

    model_config = {"env_prefix": "", "case_sensitive": False}


class GrpcClientConfig(BaseSettings):
    """gRPC client configuration."""

    grpc_target: str = "localhost:50051"
    grpc_timeout_ms: int = 5000
    grpc_max_retries: int = 2

    model_config = {"env_prefix": "", "case_sensitive": False}
