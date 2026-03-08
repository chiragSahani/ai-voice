"""Audio processing: resampling, format conversion, noise gate, gain normalization."""

from __future__ import annotations

import numpy as np

from shared.audio_utils import (
    SAMPLE_RATE_16K,
    calculate_rms,
    float32_to_pcm16,
    pcm16_to_float32,
    resample,
)
from shared.logging import get_logger

from app.config import settings

logger = get_logger("audio_processor")

# Noise gate threshold (RMS below this is zeroed)
NOISE_GATE_THRESHOLD = 0.008
# Target RMS for gain normalization
TARGET_RMS = 0.12
# Maximum gain to apply (prevents amplifying noise)
MAX_GAIN = 6.0
# Minimum chunk length in bytes to process (avoids artifacts on tiny fragments)
MIN_PROCESSABLE_BYTES = 64


def prepare_for_stt(
    audio_bytes: bytes,
    source_sample_rate: int = 16000,
    source_encoding: str = "pcm16",
) -> bytes:
    """Prepare incoming client audio for the STT service.

    Steps:
        1. Convert to float32.
        2. Resample to 16kHz if needed.
        3. Apply noise gate.
        4. Normalize gain.
        5. Convert back to PCM16.

    Args:
        audio_bytes: Raw audio from the client.
        source_sample_rate: Client-side sample rate.
        source_encoding: Client audio encoding.

    Returns:
        PCM16 16kHz mono bytes ready for STT.
    """
    if len(audio_bytes) < MIN_PROCESSABLE_BYTES:
        return audio_bytes

    # Decode to float32
    audio = pcm16_to_float32(audio_bytes)

    # Resample to 16kHz if the client sends a different rate
    if source_sample_rate != SAMPLE_RATE_16K:
        audio = resample(audio, source_sample_rate, SAMPLE_RATE_16K)

    # Noise gate: zero out very quiet frames to reduce STT hallucinations
    audio = _apply_noise_gate(audio)

    # Gain normalization: bring consistent volume to STT
    audio = _normalize_gain(audio)

    return float32_to_pcm16(audio)


def prepare_for_client(
    tts_audio: bytes,
    tts_sample_rate: int = 24000,
    client_sample_rate: int = 16000,
) -> bytes:
    """Convert TTS output audio to the client's expected format.

    Args:
        tts_audio: Raw PCM16 bytes from TTS service.
        tts_sample_rate: Sample rate of TTS output.
        client_sample_rate: Client's expected sample rate.

    Returns:
        PCM16 bytes at the client sample rate.
    """
    if len(tts_audio) < MIN_PROCESSABLE_BYTES:
        return tts_audio

    if tts_sample_rate == client_sample_rate:
        return tts_audio

    audio = pcm16_to_float32(tts_audio)
    audio = resample(audio, tts_sample_rate, client_sample_rate)
    return float32_to_pcm16(audio)


def compute_audio_duration_ms(audio_bytes: bytes, sample_rate: int = 16000) -> int:
    """Calculate duration of PCM16 audio in milliseconds.

    Args:
        audio_bytes: Raw PCM16 bytes.
        sample_rate: Sample rate in Hz.

    Returns:
        Duration in milliseconds.
    """
    num_samples = len(audio_bytes) // 2  # 2 bytes per PCM16 sample
    return int(num_samples * 1000 / sample_rate)


def _apply_noise_gate(audio: np.ndarray) -> np.ndarray:
    """Zero out audio below the noise gate threshold.

    Operates on 10ms frames to preserve transients.
    """
    frame_size = int(SAMPLE_RATE_16K * 0.010)  # 10ms frames = 160 samples
    result = audio.copy()

    for i in range(0, len(audio), frame_size):
        frame = audio[i : i + frame_size]
        rms = float(np.sqrt(np.mean(frame ** 2)))
        if rms < NOISE_GATE_THRESHOLD:
            result[i : i + frame_size] = 0.0

    return result


def _normalize_gain(audio: np.ndarray) -> np.ndarray:
    """Normalize audio gain to a target RMS level.

    Applies a gentle gain adjustment so STT receives consistent volume.
    """
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 1e-6:
        return audio  # Silence, nothing to normalize

    gain = min(TARGET_RMS / rms, MAX_GAIN)
    # Only amplify — never attenuate (user might be speaking quietly intentionally)
    if gain < 1.0:
        return audio

    return np.clip(audio * gain, -1.0, 1.0)
