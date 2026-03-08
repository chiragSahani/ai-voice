"""Language detection service using FastText."""

import os
import time
from typing import Optional

import fasttext

from shared.logging import get_logger

from app.config import STTConfig

logger = get_logger("language_detector")

# Suppress FastText warnings about deprecated model loading
fasttext.FastText.eprint = lambda x: None


class LanguageDetector:
    """FastText-based language identification for multilingual STT."""

    def __init__(self, config: STTConfig) -> None:
        self._config = config
        self._model: Optional[fasttext.FastText._FastText] = None
        self._is_loaded = False
        self._supported = set(config.supported_languages)

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load_model(self) -> None:
        """Load the FastText language identification model."""
        model_path = self._config.fasttext_model_path

        if not os.path.exists(model_path):
            logger.warning(
                "fasttext_model_not_found",
                path=model_path,
                message="Language detection will use fallback logic",
            )
            self._is_loaded = False
            return

        logger.info("loading_fasttext_model", path=model_path)
        start = time.monotonic()

        try:
            self._model = fasttext.load_model(model_path)
            self._is_loaded = True
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "fasttext_model_loaded", duration_ms=round(duration_ms, 1)
            )
        except Exception as exc:
            logger.error("fasttext_model_load_failed", error=str(exc))
            self._is_loaded = False

    def unload_model(self) -> None:
        """Release model resources."""
        self._model = None
        self._is_loaded = False
        logger.info("fasttext_model_unloaded")

    def detect(
        self, text: str, hint: Optional[str] = None
    ) -> tuple[str, float, dict[str, float]]:
        """Detect language of the given text.

        Args:
            text: Text to identify the language of.
            hint: Optional language hint to prefer if confidence is low.

        Returns:
            Tuple of (language_code, confidence, alternatives_dict).
        """
        if not text or not text.strip():
            fallback = hint or self._config.default_language
            return fallback, 0.0, {}

        # Clean text for FastText (single line, no newlines)
        cleaned = text.replace("\n", " ").replace("\r", " ").strip()

        if not self._is_loaded or self._model is None:
            return self._heuristic_detect(cleaned, hint)

        try:
            predictions = self._model.predict(cleaned, k=len(self._supported) + 2)
            labels, scores = predictions

            # FastText labels are like "__label__en"
            alternatives: dict[str, float] = {}
            primary_lang = self._config.default_language
            primary_conf = 0.0

            for label, score in zip(labels, scores):
                lang_code = label.replace("__label__", "")
                conf = float(score)

                # Only track supported languages
                if lang_code in self._supported:
                    alternatives[lang_code] = conf
                    if conf > primary_conf:
                        primary_lang = lang_code
                        primary_conf = conf

            # If confidence is below threshold and we have a hint, prefer the hint
            if (
                primary_conf < self._config.language_detection_threshold
                and hint
                and hint in self._supported
            ):
                logger.debug(
                    "language_detection_low_confidence_using_hint",
                    detected=primary_lang,
                    confidence=round(primary_conf, 3),
                    hint=hint,
                )
                primary_lang = hint
                # Boost the hint confidence slightly
                primary_conf = max(primary_conf, 0.5)

            return primary_lang, primary_conf, alternatives

        except Exception as exc:
            logger.warning("language_detection_failed", error=str(exc))
            return self._heuristic_detect(cleaned, hint)

    def detect_code_switching(
        self, text: str
    ) -> tuple[bool, list[tuple[str, float]]]:
        """Detect if text contains multiple languages (code-switching).

        Args:
            text: Text to analyze.

        Returns:
            Tuple of (is_code_switched, list of (language, confidence) pairs).
        """
        if not text or not self._is_loaded or self._model is None:
            return False, []

        # Split text into sentences/clauses and detect each
        clauses = _split_into_clauses(text)
        if len(clauses) <= 1:
            return False, []

        detected_langs: list[tuple[str, float]] = []
        for clause in clauses:
            if len(clause.strip()) < 3:
                continue
            lang, conf, _ = self.detect(clause)
            detected_langs.append((lang, conf))

        unique_langs = set(lang for lang, conf in detected_langs if conf > 0.4)
        is_switched = len(unique_langs) > 1

        return is_switched, detected_langs

    def _heuristic_detect(
        self, text: str, hint: Optional[str] = None
    ) -> tuple[str, float, dict[str, float]]:
        """Simple heuristic language detection based on script analysis.

        Used as fallback when FastText model is unavailable.
        """
        if hint and hint in self._supported:
            return hint, 0.5, {}

        tamil_chars = sum(1 for c in text if "\u0B80" <= c <= "\u0BFF")
        devanagari_chars = sum(1 for c in text if "\u0900" <= c <= "\u097F")
        latin_chars = sum(1 for c in text if c.isascii() and c.isalpha())
        total = len(text) or 1

        scores: dict[str, float] = {
            "en": latin_chars / total,
            "hi": devanagari_chars / total,
            "ta": tamil_chars / total,
        }

        best_lang = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_lang]

        # Low confidence for heuristic results
        confidence = min(best_score * 0.8, 0.7)

        return best_lang, confidence, scores


def _split_into_clauses(text: str) -> list[str]:
    """Split text into clauses for code-switching detection."""
    import re

    # Split on sentence boundaries and common clause separators
    parts = re.split(r"[.!?,;:\n]+", text)
    return [p.strip() for p in parts if p.strip()]
