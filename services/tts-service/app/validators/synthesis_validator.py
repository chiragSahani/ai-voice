"""Input validation for TTS synthesis requests.

Validates text length, language support, voice availability, sample rate,
and speed/pitch parameters before synthesis begins.
"""

from app.config import TTSConfig
from app.services.voice_manager import VoiceManager
from shared.exceptions import ValidationError
from shared.logging import get_logger

logger = get_logger("synthesis_validator")

# Valid sample rates for output audio
_VALID_SAMPLE_RATES = {8000, 16000, 22050, 24000, 44100, 48000}

# Valid audio formats
_VALID_AUDIO_FORMATS = {"pcm16", "opus"}


def validate_text(text: str, config: TTSConfig) -> str:
    """Validate and sanitize synthesis input text.

    Args:
        text: Raw input text.
        config: TTS configuration with limits.

    Returns:
        Validated text string.

    Raises:
        ValidationError: If text is empty or exceeds max length.
    """
    if not text or not text.strip():
        raise ValidationError("Text must not be empty", field="text")

    text = text.strip()

    if len(text) > config.max_text_length:
        raise ValidationError(
            f"Text length {len(text)} exceeds maximum {config.max_text_length}",
            field="text",
        )

    if len(text) < config.min_sentence_length:
        raise ValidationError(
            f"Text too short (minimum {config.min_sentence_length} characters)",
            field="text",
        )

    return text


def validate_language(language: str, config: TTSConfig) -> str:
    """Validate that the requested language is supported.

    Args:
        language: ISO 639-1 language code.
        config: TTS configuration with supported languages.

    Returns:
        Validated language code.

    Raises:
        ValidationError: If language is not supported.
    """
    if not language:
        return config.default_language

    language = language.lower().strip()

    if language not in config.supported_languages:
        raise ValidationError(
            f"Unsupported language '{language}'. Supported: {config.supported_languages}",
            field="language",
        )

    return language


def validate_voice_id(
    voice_id: str,
    language: str,
    voice_manager: VoiceManager,
) -> str:
    """Validate that the requested voice exists and is available.

    Args:
        voice_id: Voice profile identifier (may be empty for default).
        language: Language for default voice fallback.
        voice_manager: Voice manager instance.

    Returns:
        Resolved voice ID.

    Raises:
        ValidationError: If specified voice does not exist.
    """
    if not voice_id:
        # Use language default
        default = voice_manager.get_default_voice(language)
        if default:
            return default.id
        return ""

    voice = voice_manager.get_voice(voice_id)
    if voice is None:
        available = [v.id for v in voice_manager.list_voices(language)]
        raise ValidationError(
            f"Voice '{voice_id}' not found. Available for '{language}': {available}",
            field="voice_id",
        )

    return voice_id


def validate_sample_rate(sample_rate: int) -> int:
    """Validate the requested output sample rate.

    Args:
        sample_rate: Requested sample rate in Hz.

    Returns:
        Validated sample rate.

    Raises:
        ValidationError: If sample rate is not in the allowed set.
    """
    if sample_rate <= 0:
        raise ValidationError(
            "Sample rate must be positive",
            field="sample_rate",
        )

    if sample_rate not in _VALID_SAMPLE_RATES:
        raise ValidationError(
            f"Unsupported sample rate {sample_rate}. Valid: {sorted(_VALID_SAMPLE_RATES)}",
            field="sample_rate",
        )

    return sample_rate


def validate_speed(speed: float, config: TTSConfig) -> float:
    """Validate the speech rate multiplier.

    Args:
        speed: Speed multiplier (0.5 - 2.0).
        config: TTS configuration with speed bounds.

    Returns:
        Validated speed value.

    Raises:
        ValidationError: If speed is out of range.
    """
    if speed < config.speed_min or speed > config.speed_max:
        raise ValidationError(
            f"Speed {speed} out of range [{config.speed_min}, {config.speed_max}]",
            field="speed",
        )
    return speed


def validate_pitch(pitch: float, config: TTSConfig) -> float:
    """Validate the pitch adjustment multiplier.

    Args:
        pitch: Pitch multiplier (0.5 - 2.0).
        config: TTS configuration with pitch bounds.

    Returns:
        Validated pitch value.

    Raises:
        ValidationError: If pitch is out of range.
    """
    if pitch < config.pitch_min or pitch > config.pitch_max:
        raise ValidationError(
            f"Pitch {pitch} out of range [{config.pitch_min}, {config.pitch_max}]",
            field="pitch",
        )
    return pitch


def validate_audio_format(audio_format: str) -> str:
    """Validate the requested audio encoding format.

    Args:
        audio_format: Audio format string.

    Returns:
        Validated format string.

    Raises:
        ValidationError: If format is not supported.
    """
    if not audio_format:
        return "pcm16"

    audio_format = audio_format.lower().strip()

    if audio_format not in _VALID_AUDIO_FORMATS:
        raise ValidationError(
            f"Unsupported audio format '{audio_format}'. Valid: {sorted(_VALID_AUDIO_FORMATS)}",
            field="audio_format",
        )

    return audio_format


def validate_synthesis_request(
    text: str,
    language: str,
    voice_id: str,
    speed: float,
    pitch: float,
    sample_rate: int,
    audio_format: str,
    config: TTSConfig,
    voice_manager: VoiceManager,
) -> dict:
    """Validate all fields of a synthesis request.

    Args:
        text: Input text.
        language: Language code.
        voice_id: Voice profile ID.
        speed: Speed multiplier.
        pitch: Pitch multiplier.
        sample_rate: Output sample rate.
        audio_format: Audio encoding format.
        config: TTS configuration.
        voice_manager: Voice manager.

    Returns:
        Dict of validated parameters.

    Raises:
        ValidationError: If any parameter is invalid.
    """
    validated_lang = validate_language(language, config)
    return {
        "text": validate_text(text, config),
        "language": validated_lang,
        "voice_id": validate_voice_id(voice_id, validated_lang, voice_manager),
        "speed": validate_speed(speed, config),
        "pitch": validate_pitch(pitch, config),
        "sample_rate": validate_sample_rate(sample_rate),
        "audio_format": validate_audio_format(audio_format),
    }
