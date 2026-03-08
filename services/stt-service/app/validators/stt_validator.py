"""Input validation for STT service audio and configuration."""

from typing import Optional

from shared.logging import get_logger

from app.config import STTConfig

logger = get_logger("audio_validator")

SUPPORTED_ENCODINGS = {"pcm16", "opus", "flac"}
VALID_SAMPLE_RATES = {8000, 16000, 22050, 24000, 44100, 48000}
SUPPORTED_LANGUAGES = {"en", "hi", "ta"}


class AudioValidationError(Exception):
    """Raised when audio input fails validation."""

    def __init__(self, message: str, field: str = "") -> None:
        self.message = message
        self.field = field
        super().__init__(message)


class AudioValidator:
    """Validates audio input parameters and data."""

    def __init__(self, config: STTConfig) -> None:
        self._config = config

    def validate_audio_config(
        self,
        sample_rate: int,
        encoding: str,
        channels: int,
    ) -> None:
        """Validate audio configuration parameters.

        Args:
            sample_rate: Audio sample rate in Hz.
            encoding: Audio encoding format.
            channels: Number of audio channels.

        Raises:
            AudioValidationError: If any parameter is invalid.
        """
        self.validate_sample_rate(sample_rate)
        self.validate_encoding(encoding)
        self.validate_channels(channels)

    def validate_sample_rate(self, sample_rate: int) -> None:
        """Validate audio sample rate."""
        if sample_rate not in VALID_SAMPLE_RATES:
            raise AudioValidationError(
                f"Unsupported sample rate: {sample_rate}. "
                f"Valid rates: {sorted(VALID_SAMPLE_RATES)}",
                field="sample_rate",
            )

    def validate_encoding(self, encoding: str) -> None:
        """Validate audio encoding format."""
        if encoding.lower() not in SUPPORTED_ENCODINGS:
            raise AudioValidationError(
                f"Unsupported encoding: '{encoding}'. "
                f"Supported: {sorted(SUPPORTED_ENCODINGS)}",
                field="encoding",
            )

    def validate_channels(self, channels: int) -> None:
        """Validate number of audio channels."""
        if channels < 1 or channels > 2:
            raise AudioValidationError(
                f"Invalid channel count: {channels}. Must be 1 (mono) or 2 (stereo).",
                field="channels",
            )

    def validate_chunk_size(self, chunk_bytes: bytes) -> None:
        """Validate audio chunk size is within acceptable bounds.

        Args:
            chunk_bytes: Raw audio bytes.

        Raises:
            AudioValidationError: If chunk is too small or too large.
        """
        size = len(chunk_bytes)

        if size == 0:
            raise AudioValidationError(
                "Audio chunk is empty (0 bytes).",
                field="audio_data",
            )

        if size < self._config.min_chunk_size_bytes:
            raise AudioValidationError(
                f"Audio chunk too small: {size} bytes. "
                f"Minimum: {self._config.min_chunk_size_bytes} bytes.",
                field="audio_data",
            )

        if size > self._config.max_chunk_size_bytes:
            raise AudioValidationError(
                f"Audio chunk too large: {size} bytes. "
                f"Maximum: {self._config.max_chunk_size_bytes} bytes.",
                field="audio_data",
            )

        # PCM16 chunks must have even byte count (2 bytes per sample)
        if size % 2 != 0:
            raise AudioValidationError(
                f"PCM16 audio chunk has odd byte count ({size}). "
                "PCM16 requires 2 bytes per sample.",
                field="audio_data",
            )

    def validate_language_hint(self, language: Optional[str]) -> Optional[str]:
        """Validate and normalize a language hint.

        Args:
            language: ISO 639-1 language code or None.

        Returns:
            Normalized language code or None.

        Raises:
            AudioValidationError: If language is not supported.
        """
        if language is None or language == "":
            return None

        lang = language.strip().lower()

        if lang not in SUPPORTED_LANGUAGES:
            raise AudioValidationError(
                f"Unsupported language: '{lang}'. "
                f"Supported: {sorted(SUPPORTED_LANGUAGES)}",
                field="language_hint",
            )

        return lang

    def validate_session_id(self, session_id: str) -> str:
        """Validate session identifier.

        Args:
            session_id: Session ID string.

        Returns:
            Validated session ID.

        Raises:
            AudioValidationError: If session ID is invalid.
        """
        if not session_id or not session_id.strip():
            raise AudioValidationError(
                "Session ID is required and cannot be empty.",
                field="session_id",
            )

        session_id = session_id.strip()

        if len(session_id) > 128:
            raise AudioValidationError(
                f"Session ID too long: {len(session_id)} chars. Maximum: 128.",
                field="session_id",
            )

        return session_id
