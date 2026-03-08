"""Audio processing utilities for PCM audio manipulation."""

import struct

import numpy as np

# Audio constants
SAMPLE_RATE_16K = 16000
SAMPLE_RATE_24K = 24000
CHANNELS_MONO = 1
BYTES_PER_SAMPLE_PCM16 = 2
CHUNK_DURATION_MS = 20
CHUNK_SIZE_16K = int(SAMPLE_RATE_16K * CHUNK_DURATION_MS / 1000) * BYTES_PER_SAMPLE_PCM16  # 640 bytes


def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert PCM16 bytes to float32 numpy array.

    Args:
        pcm_bytes: Raw PCM16 audio bytes.

    Returns:
        Float32 array normalized to [-1.0, 1.0].
    """
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def float32_to_pcm16(audio: np.ndarray) -> bytes:
    """Convert float32 numpy array to PCM16 bytes.

    Args:
        audio: Float32 audio array [-1.0, 1.0].

    Returns:
        Raw PCM16 bytes.
    """
    audio = np.clip(audio, -1.0, 1.0)
    samples = (audio * 32767).astype(np.int16)
    return samples.tobytes()


def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear interpolation resampling.

    Args:
        audio: Input audio array.
        orig_sr: Original sample rate.
        target_sr: Target sample rate.

    Returns:
        Resampled audio array.
    """
    if orig_sr == target_sr:
        return audio

    ratio = target_sr / orig_sr
    new_length = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, new_length)
    return np.interp(indices, np.arange(len(audio)), audio)


def calculate_rms(pcm_bytes: bytes) -> float:
    """Calculate RMS energy of PCM16 audio.

    Args:
        pcm_bytes: Raw PCM16 audio bytes.

    Returns:
        RMS energy value.
    """
    if not pcm_bytes:
        return 0.0
    audio = pcm16_to_float32(pcm_bytes)
    return float(np.sqrt(np.mean(audio**2)))


def is_silence(pcm_bytes: bytes, threshold: float = 0.01) -> bool:
    """Check if audio chunk is silence.

    Args:
        pcm_bytes: Raw PCM16 audio bytes.
        threshold: RMS threshold below which audio is considered silence.

    Returns:
        True if audio is below silence threshold.
    """
    return calculate_rms(pcm_bytes) < threshold


def split_audio_chunks(pcm_bytes: bytes, chunk_size: int = CHUNK_SIZE_16K) -> list[bytes]:
    """Split audio bytes into fixed-size chunks.

    Args:
        pcm_bytes: Raw PCM16 audio bytes.
        chunk_size: Size of each chunk in bytes.

    Returns:
        List of audio chunks.
    """
    chunks = []
    for i in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[i : i + chunk_size]
        if len(chunk) == chunk_size:
            chunks.append(chunk)
        else:
            # Pad last chunk with silence
            chunk += b"\x00" * (chunk_size - len(chunk))
            chunks.append(chunk)
    return chunks
