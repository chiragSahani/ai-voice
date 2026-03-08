"""Audio Gateway service configuration."""

from pydantic_settings import BaseSettings

from shared.config import BaseServiceConfig, GrpcClientConfig


class AudioGatewayConfig(BaseServiceConfig):
    """Audio Gateway configuration with WebSocket and gRPC client settings."""

    service_name: str = "audio-gateway"
    service_version: str = "0.1.0"

    # HTTP / WebSocket server
    host: str = "0.0.0.0"
    port: int = 8080
    ws_max_connections: int = 200
    ws_ping_interval: float = 20.0
    ws_ping_timeout: float = 10.0
    ws_max_message_size: int = 65536  # 64KB per WS frame

    # gRPC upstream targets
    stt_host: str = "stt-service"
    stt_port: int = 50051
    tts_host: str = "tts-service"
    tts_port: int = 50052
    llm_host: str = "llm-agent"
    llm_port: int = 8090

    # Session manager (REST)
    session_manager_url: str = "http://session-manager:6380"

    # Audio pipeline
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 640  # 20ms at 16kHz PCM16 (320 samples * 2 bytes)
    audio_channels: int = 1
    tts_output_sample_rate: int = 24000

    # Pipeline timeouts (milliseconds)
    stt_timeout_ms: int = 5000
    llm_timeout_ms: int = 10000
    tts_timeout_ms: int = 5000
    turn_timeout_ms: int = 15000

    # Circuit breaker
    cb_fail_max: int = 3
    cb_reset_timeout: int = 30

    # Auth
    auth_token_secret: str = "dev-secret-change-in-production"

    model_config = {"env_prefix": "AUDIO_GATEWAY_", "case_sensitive": False}

    @property
    def stt_target(self) -> str:
        return f"{self.stt_host}:{self.stt_port}"

    @property
    def tts_target(self) -> str:
        return f"{self.tts_host}:{self.tts_port}"

    @property
    def llm_target(self) -> str:
        return f"{self.llm_host}:{self.llm_port}"


# Singleton
settings = AudioGatewayConfig()
