"""STT service configuration using Pydantic Settings."""

from typing import Literal

from pydantic_settings import BaseSettings

from shared.config import BaseServiceConfig, GrpcServerConfig


class STTConfig(BaseServiceConfig, GrpcServerConfig):
    """Configuration for the Speech-to-Text service."""

    service_name: str = "stt-service"

    # Whisper model settings
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: Literal[
        "float16", "float32", "int8", "int8_float16"
    ] = "float16"
    whisper_beam_size: int = 5
    whisper_best_of: int = 1
    whisper_patience: float = 1.0
    whisper_no_speech_threshold: float = 0.6
    whisper_log_prob_threshold: float = -1.0
    whisper_compression_ratio_threshold: float = 2.4

    # When latency matters more than accuracy, fall back to greedy
    whisper_greedy_fallback: bool = True
    whisper_greedy_beam_size: int = 1

    # VAD settings
    vad_threshold: float = 0.5
    vad_min_speech_duration_ms: int = 250
    vad_min_silence_duration_ms: int = 300
    vad_speech_pad_ms: int = 100
    vad_window_size_samples: int = 512

    # Language detection
    fasttext_model_path: str = "/models/lid.176.bin"
    language_detection_threshold: float = 0.6
    supported_languages: list[str] = ["en", "hi", "ta"]
    default_language: str = "en"

    # Audio settings
    target_sample_rate: int = 16000
    max_chunk_size_bytes: int = 64000
    min_chunk_size_bytes: int = 320
    max_audio_buffer_seconds: float = 30.0

    # Streaming settings
    partial_result_interval_ms: int = 300
    max_session_duration_seconds: int = 300

    # gRPC
    grpc_port: int = 50051
    grpc_max_workers: int = 10

    # FastAPI health/metrics HTTP port
    http_port: int = 8051

    model_config = {"env_prefix": "STT_", "case_sensitive": False}


def get_config() -> STTConfig:
    """Get cached STT configuration instance."""
    return STTConfig()
