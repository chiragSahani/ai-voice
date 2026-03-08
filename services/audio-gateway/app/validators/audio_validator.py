"""Validation logic for WebSocket connections and audio data."""

from __future__ import annotations

import hashlib
import hmac
import time

from shared.exceptions import AuthenticationError, ValidationError
from shared.logging import get_logger

from app.config import settings

logger = get_logger("validator")

SUPPORTED_LANGUAGES = {"en", "hi", "ta"}
SUPPORTED_ENCODINGS = {"pcm16", "opus", "flac"}
VALID_SAMPLE_RATES = {8000, 16000, 24000, 44100, 48000}


def validate_auth_token(token: str) -> dict:
    """Validate an authentication token and return user info.

    Uses HMAC-based token validation for low-latency verification.
    In production, replace with JWT / OAuth2 token introspection.

    Args:
        token: Bearer token from the WebSocket query string.

    Returns:
        Dict with user_id, roles, and expiry.

    Raises:
        AuthenticationError: If the token is missing, expired, or invalid.
    """
    if not token or not token.strip():
        raise AuthenticationError("Missing authentication token")

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("Malformed token: expected 3 parts")

        payload_part = parts[1]
        signature_part = parts[2]

        # Verify HMAC signature
        expected_sig = hmac.new(
            settings.auth_token_secret.encode("utf-8"),
            f"{parts[0]}.{payload_part}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]

        if not hmac.compare_digest(signature_part, expected_sig):
            raise AuthenticationError("Invalid token signature")

        # Decode payload (simple base64-like — in production use proper JWT)
        import base64
        import json

        # Pad base64
        padded = payload_part + "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        # Check expiry
        exp = payload.get("exp", 0)
        if exp and time.time() > exp:
            raise AuthenticationError("Token expired")

        return {
            "user_id": payload.get("sub", "unknown"),
            "roles": payload.get("roles", []),
            "patient_id": payload.get("patient_id"),
        }

    except AuthenticationError:
        raise
    except Exception as exc:
        logger.warning("token_validation_failed", error=str(exc))
        raise AuthenticationError(f"Token validation failed: {exc}") from exc


def validate_audio_format(
    sample_rate: int = 16000,
    encoding: str = "pcm16",
    channels: int = 1,
) -> None:
    """Validate audio format parameters.

    Args:
        sample_rate: Audio sample rate in Hz.
        encoding: Audio encoding format.
        channels: Number of audio channels.

    Raises:
        ValidationError: If any parameter is unsupported.
    """
    if sample_rate not in VALID_SAMPLE_RATES:
        raise ValidationError(
            f"Unsupported sample rate: {sample_rate}. Supported: {VALID_SAMPLE_RATES}",
            field="sample_rate",
        )
    if encoding not in SUPPORTED_ENCODINGS:
        raise ValidationError(
            f"Unsupported encoding: {encoding}. Supported: {SUPPORTED_ENCODINGS}",
            field="encoding",
        )
    if channels not in (1, 2):
        raise ValidationError(
            f"Unsupported channel count: {channels}. Use 1 (mono) or 2 (stereo).",
            field="channels",
        )


def validate_session_params(
    session_id: str | None,
    language: str,
) -> None:
    """Validate session creation / resume parameters.

    Args:
        session_id: Optional session ID for resumption.
        language: Requested language.

    Raises:
        ValidationError: If parameters are invalid.
    """
    if session_id is not None:
        if len(session_id) < 8 or len(session_id) > 128:
            raise ValidationError(
                "session_id must be 8-128 characters",
                field="session_id",
            )
        # Only allow alphanumeric, hyphens, underscores
        if not all(c.isalnum() or c in "-_" for c in session_id):
            raise ValidationError(
                "session_id contains invalid characters",
                field="session_id",
            )

    if language not in SUPPORTED_LANGUAGES:
        raise ValidationError(
            f"Unsupported language: {language}. Supported: {SUPPORTED_LANGUAGES}",
            field="language",
        )


def validate_audio_chunk(data: bytes) -> None:
    """Validate a raw audio chunk received over WebSocket.

    Args:
        data: Raw bytes from a binary WebSocket frame.

    Raises:
        ValidationError: If the chunk is empty or too large.
    """
    if not data:
        raise ValidationError("Empty audio chunk", field="audio")
    # Max 1 second of audio at 48kHz stereo PCM16 = 192,000 bytes
    if len(data) > 192_000:
        raise ValidationError(
            f"Audio chunk too large: {len(data)} bytes (max 192000)",
            field="audio",
        )
