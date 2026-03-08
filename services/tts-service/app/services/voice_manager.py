"""Voice profile management for TTS service.

Loads, indexes, and serves voice profiles from the speaker WAV directory.
Each language has a default voice; custom voices can be added by placing
WAV files in the appropriate language subdirectory.
"""

from pathlib import Path

from app.config import TTSConfig
from app.models.domain import VoiceProfile
from shared.logging import get_logger

logger = get_logger("voice_manager")

# Default voice definitions per language
_DEFAULT_VOICES: dict[str, dict] = {
    "en": {
        "id": "en_default",
        "name": "English Default",
        "gender": "female",
        "description": "Default English female voice",
        "filename": "en_default.wav",
    },
    "hi": {
        "id": "hi_default",
        "name": "Hindi Default",
        "gender": "female",
        "description": "Default Hindi female voice",
        "filename": "hi_default.wav",
    },
    "ta": {
        "id": "ta_default",
        "name": "Tamil Default",
        "gender": "female",
        "description": "Default Tamil female voice",
        "filename": "ta_default.wav",
    },
}


class VoiceManager:
    """Manages voice profiles loaded from speaker WAV files.

    Voice directory structure:
        speaker_wav_dir/
            en/
                en_default.wav
                en_doctor_male.wav
            hi/
                hi_default.wav
            ta/
                ta_default.wav
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        self._speaker_wav_dir = Path(config.speaker_wav_dir)
        self._voices: dict[str, VoiceProfile] = {}
        self._default_voices: dict[str, str] = {}  # language -> voice_id
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_voices(self) -> None:
        """Scan the speaker WAV directory and load all voice profiles.

        Creates default voice entries even if WAV files are missing (they
        will be flagged as unavailable). Custom voices are discovered by
        scanning language subdirectories for .wav files.
        """
        self._voices.clear()
        self._default_voices.clear()

        # Register default voices
        for lang, voice_def in _DEFAULT_VOICES.items():
            wav_path = self._speaker_wav_dir / lang / voice_def["filename"]
            profile = VoiceProfile(
                id=voice_def["id"],
                name=voice_def["name"],
                language=lang,
                speaker_wav_path=wav_path,
                gender=voice_def["gender"],
                description=voice_def["description"],
                is_default=True,
            )
            self._voices[profile.id] = profile
            self._default_voices[lang] = profile.id

            if profile.exists():
                logger.info("default_voice_loaded", voice_id=profile.id, language=lang)
            else:
                logger.warning(
                    "default_voice_wav_missing",
                    voice_id=profile.id,
                    path=str(wav_path),
                )

        # Discover custom voices from filesystem
        if self._speaker_wav_dir.exists():
            for lang_dir in self._speaker_wav_dir.iterdir():
                if not lang_dir.is_dir():
                    continue
                lang = lang_dir.name
                if lang not in self._config.supported_languages:
                    continue

                for wav_file in lang_dir.glob("*.wav"):
                    voice_id = wav_file.stem
                    if voice_id in self._voices:
                        continue  # Skip already-registered defaults

                    profile = VoiceProfile(
                        id=voice_id,
                        name=voice_id.replace("_", " ").title(),
                        language=lang,
                        speaker_wav_path=wav_file,
                        gender=_infer_gender(voice_id),
                        description=f"Custom {lang} voice: {voice_id}",
                        is_default=False,
                    )
                    self._voices[profile.id] = profile
                    logger.info(
                        "custom_voice_loaded",
                        voice_id=profile.id,
                        language=lang,
                    )

        self._loaded = True
        logger.info("voices_loaded", total=len(self._voices))

    def get_voice(self, voice_id: str) -> VoiceProfile | None:
        """Get a voice profile by ID.

        Args:
            voice_id: Voice profile identifier.

        Returns:
            VoiceProfile if found, None otherwise.
        """
        return self._voices.get(voice_id)

    def get_default_voice(self, language: str) -> VoiceProfile | None:
        """Get the default voice for a language.

        Args:
            language: ISO 639-1 language code.

        Returns:
            Default VoiceProfile for the language, or None.
        """
        voice_id = self._default_voices.get(language)
        if voice_id:
            return self._voices.get(voice_id)
        return None

    def resolve_voice(self, voice_id: str, language: str) -> VoiceProfile | None:
        """Resolve a voice ID, falling back to language default.

        Args:
            voice_id: Requested voice ID (may be empty).
            language: Language to use for default fallback.

        Returns:
            Resolved VoiceProfile, or None if no voice is available.
        """
        if voice_id:
            voice = self.get_voice(voice_id)
            if voice:
                return voice
            logger.warning("voice_not_found_falling_back", voice_id=voice_id, language=language)

        return self.get_default_voice(language)

    def list_voices(self, language: str = "") -> list[VoiceProfile]:
        """List available voices, optionally filtered by language.

        Args:
            language: Filter by language (empty string returns all).

        Returns:
            List of VoiceProfile instances.
        """
        if language:
            return [v for v in self._voices.values() if v.language == language]
        return list(self._voices.values())


def _infer_gender(voice_id: str) -> str:
    """Infer gender from voice ID naming convention.

    Args:
        voice_id: Voice identifier string.

    Returns:
        Inferred gender string.
    """
    lower = voice_id.lower()
    if "male" in lower and "female" not in lower:
        return "male"
    if "female" in lower:
        return "female"
    return "neutral"
