"""Sentence boundary detection for streaming TTS.

This module provides a streaming-aware sentence splitter that accumulates
text deltas and emits complete sentences as they are detected. Used by the
bidirectional streaming RPC to start synthesis before the LLM finishes
generating text.
"""

import re

from app.models.domain import SentenceChunk
from shared.logging import get_logger

logger = get_logger("sentence_splitter")

# Sentence-ending patterns per language
_ENDINGS = {
    "en": re.compile(r'[.!?]\s'),
    "hi": re.compile(r'[\u0964!?]\s*'),  # Devanagari danda
    "ta": re.compile(r'[.!?\u0964]\s*'),
}


class StreamingSentenceSplitter:
    """Accumulates text deltas and yields complete sentences.

    Used in bidirectional streaming mode where text arrives incrementally
    from the LLM. Detects sentence boundaries and emits SentenceChunks
    for each complete sentence, keeping any trailing partial sentence
    in the buffer.
    """

    def __init__(self, language: str = "en", min_length: int = 2) -> None:
        self._language = language
        self._min_length = min_length
        self._buffer = ""
        self._chunk_index = 0
        self._pattern = _ENDINGS.get(language, _ENDINGS["en"])

    @property
    def buffer(self) -> str:
        """Current unprocessed text in the buffer."""
        return self._buffer

    def add_text(self, text_delta: str) -> list[SentenceChunk]:
        """Add a text delta and return any complete sentences.

        Args:
            text_delta: Incremental text fragment.

        Returns:
            List of SentenceChunk for each detected complete sentence.
            May be empty if no sentence boundary is found yet.
        """
        self._buffer += text_delta
        chunks: list[SentenceChunk] = []

        while True:
            match = self._pattern.search(self._buffer)
            if not match:
                break

            # Split at the sentence boundary
            end_pos = match.end()
            sentence = self._buffer[:end_pos].strip()
            self._buffer = self._buffer[end_pos:]

            if len(sentence) >= self._min_length:
                chunk = SentenceChunk(
                    text=sentence,
                    index=self._chunk_index,
                    is_last=False,
                )
                chunks.append(chunk)
                self._chunk_index += 1

        return chunks

    def flush(self) -> SentenceChunk | None:
        """Flush any remaining text in the buffer as the final chunk.

        Should be called when the text stream signals completion (is_final=True).

        Returns:
            Final SentenceChunk if buffer has content, None otherwise.
        """
        remaining = self._buffer.strip()
        self._buffer = ""

        if remaining and len(remaining) >= self._min_length:
            chunk = SentenceChunk(
                text=remaining,
                index=self._chunk_index,
                is_last=True,
            )
            self._chunk_index += 1
            return chunk
        return None

    def reset(self) -> None:
        """Reset the splitter state for a new synthesis session."""
        self._buffer = ""
        self._chunk_index = 0
