"""TTS service configuration using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

from shared.config import BaseServiceConfig, GrpcServerConfig


class TTSConfig(BaseServiceConfig, GrpcServerConfig):
    """Configuration for the Text-to-Speech service."""

    service_name: str = "tts-service"

    # XTTS v2 model settings
    model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    model_path: str = "/models/xtts_v2"
    device: Literal["cuda", "cpu"] = "cuda"
    compute_type: Literal["float16", "float32"] = "float16"

    # Audio output settings
    sample_rate: int = 24000
    output_channels: int = 1
    audio_format: Literal["pcm16", "opus"] = "pcm16"

    # Voice profiles
    speaker_wav_dir: str = "/voices"
    default_language: str = "en"
    supported_languages: list[str] = ["en", "hi", "ta"]

    # Synthesis limits
    max_text_length: int = 5000
    max_sentence_length: int = 500
    min_sentence_length: int = 2

    # Streaming configuration
    stream_chunk_size: int = 4800  # 200ms at 24kHz
    sentence_silence_ms: int = 150  # Pause between sentences
    max_concurrent_syntheses: int = 4

    # Speed / pitch bounds
    speed_min: float = 0.5
    speed_max: float = 2.0
    pitch_min: float = 0.5
    pitch_max: float = 2.0

    # Performance
    enable_gpu_cache: bool = True
    warmup_on_startup: bool = True

    # gRPC
    grpc_port: int = 50052
    grpc_max_workers: int = 10

    # FastAPI health/metrics HTTP port
    http_port: int = 8052

    model_config = {"env_prefix": "TTS_", "case_sensitive": False}


def get_config() -> TTSConfig:
    """Get cached TTS configuration instance."""
    return TTSConfig()
