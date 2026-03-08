"""Text preprocessing for TTS synthesis.

Handles sentence splitting, text normalization, and multilingual text
(English, Hindi Devanagari, Tamil script).
"""

import re
import unicodedata

from shared.logging import get_logger

logger = get_logger("text_processor")

# Sentence-ending punctuation patterns per language
_SENTENCE_ENDINGS_EN = re.compile(r'(?<=[.!?])\s+')
_SENTENCE_ENDINGS_HI = re.compile(r'(?<=[।!?])\s*')
_SENTENCE_ENDINGS_TA = re.compile(r'(?<=[.!?।])\s*')

# Number words for basic normalization
_DIGIT_WORDS_EN = [
    "zero", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine",
]

_DIGIT_WORDS_HI = [
    "\u0936\u0942\u0928\u094d\u092f", "\u090f\u0915", "\u0926\u094b", "\u0924\u0940\u0928", "\u091a\u093e\u0930",
    "\u092a\u093e\u0901\u091a", "\u091b\u0939", "\u0938\u093e\u0924", "\u0906\u0920", "\u0928\u094c",
]

# Common medical/clinical abbreviations
_ABBREVIATIONS = {
    "Dr.": "Doctor",
    "dr.": "doctor",
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "Ms.": "Miss",
    "Jr.": "Junior",
    "Sr.": "Senior",
    "St.": "Saint",
    "appt.": "appointment",
    "apt.": "apartment",
    "dept.": "department",
    "mgmt.": "management",
    "approx.": "approximately",
    "no.": "number",
    "No.": "Number",
    "vs.": "versus",
    "etc.": "etcetera",
    "min.": "minutes",
    "hr.": "hour",
    "hrs.": "hours",
    "mg": "milligrams",
    "ml": "milliliters",
    "kg": "kilograms",
    "bp": "blood pressure",
    "BP": "blood pressure",
    "OPD": "O P D",
    "ICU": "I C U",
    "ENT": "E N T",
}


def split_sentences(text: str, language: str = "en") -> list[str]:
    """Split text into sentences using language-appropriate rules.

    Uses punctuation-based splitting optimized for low latency. Falls back
    to comma/semicolon splitting for very long segments.

    Args:
        text: Input text to split.
        language: ISO 639-1 language code (en, hi, ta).

    Returns:
        List of sentence strings, stripped and non-empty.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Choose pattern based on language
    if language == "hi":
        pattern = _SENTENCE_ENDINGS_HI
    elif language == "ta":
        pattern = _SENTENCE_ENDINGS_TA
    else:
        pattern = _SENTENCE_ENDINGS_EN

    sentences = pattern.split(text)

    # Further split long sentences on commas/semicolons for streaming latency
    result = []
    max_segment_len = 200  # characters

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) <= max_segment_len:
            result.append(sentence)
        else:
            # Split on commas, semicolons, colons, or em-dashes
            sub_parts = re.split(r'(?<=[,;:\u2014])\s+', sentence)
            current = ""
            for part in sub_parts:
                if current and len(current) + len(part) > max_segment_len:
                    result.append(current.strip())
                    current = part
                else:
                    current = f"{current} {part}".strip() if current else part
            if current.strip():
                result.append(current.strip())

    # Filter empty strings
    result = [s for s in result if s.strip()]

    logger.debug(
        "sentences_split",
        language=language,
        input_length=len(text),
        sentence_count=len(result),
    )
    return result


def normalize_text(text: str, language: str = "en") -> str:
    """Normalize text for TTS synthesis.

    Expands abbreviations, converts standalone digits to words,
    normalizes whitespace, and handles Unicode normalization.

    Args:
        text: Raw input text.
        language: ISO 639-1 language code.

    Returns:
        Cleaned and normalized text.
    """
    if not text:
        return ""

    # Unicode NFC normalization (composes characters)
    text = unicodedata.normalize("NFC", text)

    # Expand abbreviations (English only)
    if language == "en":
        for abbrev, expansion in _ABBREVIATIONS.items():
            text = text.replace(abbrev, expansion)

    # Convert standalone digits to words
    text = _convert_digits(text, language)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Remove control characters but keep normal punctuation
    text = ''.join(
        c for c in text
        if not unicodedata.category(c).startswith('C') or c in '\n\t'
    )

    # Collapse multiple punctuation
    text = re.sub(r'([.!?]){2,}', r'\1', text)

    logger.debug("text_normalized", language=language, length=len(text))
    return text


def _convert_digits(text: str, language: str) -> str:
    """Convert isolated digit sequences to spoken words.

    Handles single digits and simple multi-digit numbers. Does not attempt
    complex number-to-word conversion for very large numbers.

    Args:
        text: Input text.
        language: Language code for digit word lookup.

    Returns:
        Text with digits replaced by words where appropriate.
    """
    words = _DIGIT_WORDS_HI if language == "hi" else _DIGIT_WORDS_EN

    def _replace_number(match: re.Match) -> str:
        num_str = match.group(0)
        # Only convert small numbers (0-9) to words
        if len(num_str) == 1:
            digit = int(num_str)
            return words[digit]
        # For multi-digit, spell out each digit
        if len(num_str) <= 4:
            return ' '.join(words[int(d)] for d in num_str)
        # Leave large numbers as-is (phone numbers, IDs, etc.)
        return num_str

    # Match standalone numbers (not part of words/identifiers)
    return re.sub(r'\b\d+\b', _replace_number, text)


def prepare_for_synthesis(text: str, language: str = "en") -> list[str]:
    """Full preprocessing pipeline: normalize then split into sentences.

    Args:
        text: Raw input text.
        language: ISO 639-1 language code.

    Returns:
        List of normalized, sentence-split text segments ready for synthesis.
    """
    normalized = normalize_text(text, language)
    return split_sentences(normalized, language)
