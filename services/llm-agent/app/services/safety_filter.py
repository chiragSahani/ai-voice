"""Content safety filter for LLM inputs and outputs."""

import re
from typing import Optional

from shared.logging import get_logger

from app.models.domain import SafetyCheckResult

logger = get_logger("safety_filter")

# Patterns that may indicate PHI leakage
_PHI_PATTERNS = [
    # SSN
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Credit card numbers (basic)
    re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
    # Email addresses (flag but don't block -- may be legitimate)
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    # Aadhaar number (Indian ID)
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
]

# Patterns indicating medical advice attempts
_MEDICAL_ADVICE_PATTERNS = [
    re.compile(r"\byou\s+should\s+take\b", re.IGNORECASE),
    re.compile(r"\bi\s+recommend\s+(?:taking|using|trying)\b", re.IGNORECASE),
    re.compile(r"\byour\s+diagnosis\s+(?:is|might\s+be|could\s+be)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:have|likely\s+have|probably\s+have)\s+(?:a\s+)?(?:condition|disease|disorder|infection)\b", re.IGNORECASE),
    re.compile(r"\bprescri(?:be|ption)\b", re.IGNORECASE),
    re.compile(r"\bdosage\b", re.IGNORECASE),
    re.compile(r"\bstart\s+(?:taking|using)\s+\w+\s*(?:mg|ml)\b", re.IGNORECASE),
]

# Emergency keywords that should trigger escalation
_EMERGENCY_KEYWORDS = [
    re.compile(r"\bchest\s+pain\b", re.IGNORECASE),
    re.compile(r"\bdifficulty\s+breathing\b", re.IGNORECASE),
    re.compile(r"\bcan'?t\s+breathe\b", re.IGNORECASE),
    re.compile(r"\bsevere\s+bleeding\b", re.IGNORECASE),
    re.compile(r"\bstroke\b", re.IGNORECASE),
    re.compile(r"\bunconscious\b", re.IGNORECASE),
    re.compile(r"\bheart\s+attack\b", re.IGNORECASE),
    re.compile(r"\bseizure\b", re.IGNORECASE),
    re.compile(r"\boverdose\b", re.IGNORECASE),
    re.compile(r"\bsuicid(?:e|al)\b", re.IGNORECASE),
    re.compile(r"\bself[- ]?harm\b", re.IGNORECASE),
]

# Profanity / abuse patterns (basic set)
_ABUSE_PATTERNS = [
    re.compile(r"\b(?:fuck|shit|damn|ass|bitch|bastard|crap)\b", re.IGNORECASE),
    re.compile(r"\b(?:idiot|stupid|dumb|useless)\s+(?:bot|machine|system|ai)\b", re.IGNORECASE),
]

# Replacement for PHI data
_PHI_REDACTION = "[REDACTED]"


class SafetyFilter:
    """Checks content for safety issues including PHI leakage,
    medical advice, emergencies, and abuse."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    def check_input(self, text: str) -> SafetyCheckResult:
        """Check user input for safety concerns.

        Args:
            text: User input text to check.

        Returns:
            SafetyCheckResult indicating whether the input is safe.
        """
        if not self._enabled or not text:
            return SafetyCheckResult(is_safe=True)

        # Check for emergency situations (high priority)
        for pattern in _EMERGENCY_KEYWORDS:
            if pattern.search(text):
                logger.warning("emergency_detected", pattern=pattern.pattern, text_length=len(text))
                return SafetyCheckResult(
                    is_safe=True,  # Allow through but flag
                    reason="emergency_detected",
                    severity="critical",
                )

        # Check for abuse / profanity
        for pattern in _ABUSE_PATTERNS:
            if pattern.search(text):
                logger.info("abuse_detected", text_length=len(text))
                return SafetyCheckResult(
                    is_safe=True,  # Allow but note it
                    reason="profanity_detected",
                    severity="low",
                )

        return SafetyCheckResult(is_safe=True)

    def check_output(self, text: str) -> SafetyCheckResult:
        """Check LLM output for safety issues before sending to user.

        Args:
            text: LLM-generated text to check.

        Returns:
            SafetyCheckResult with filtered text if needed.
        """
        if not self._enabled or not text:
            return SafetyCheckResult(is_safe=True)

        filtered_text = text
        reasons = []

        # Check for PHI leakage in output
        for pattern in _PHI_PATTERNS:
            if pattern.search(filtered_text):
                filtered_text = pattern.sub(_PHI_REDACTION, filtered_text)
                reasons.append("phi_redacted")
                logger.warning("phi_detected_in_output", pattern=pattern.pattern)

        # Check for medical advice in output
        for pattern in _MEDICAL_ADVICE_PATTERNS:
            if pattern.search(filtered_text):
                reasons.append("medical_advice_detected")
                logger.warning("medical_advice_in_output", pattern=pattern.pattern)
                # Replace the problematic text with a safe alternative
                filtered_text = _replace_medical_advice(filtered_text)
                break

        if reasons:
            severity = "high" if "phi_redacted" in reasons else "medium"
            return SafetyCheckResult(
                is_safe=False,
                reason="; ".join(reasons),
                filtered_text=filtered_text,
                severity=severity,
            )

        return SafetyCheckResult(is_safe=True)

    def check_emergency(self, text: str) -> bool:
        """Quick check if text contains emergency indicators.

        Args:
            text: Text to check for emergency keywords.

        Returns:
            True if emergency keywords detected.
        """
        if not text:
            return False
        return any(pattern.search(text) for pattern in _EMERGENCY_KEYWORDS)


def _replace_medical_advice(text: str) -> str:
    """Replace medical advice in text with a safe disclaimer.

    Args:
        text: Text containing medical advice.

    Returns:
        Text with medical advice replaced by disclaimer.
    """
    disclaimer = (
        "I'm not able to provide medical advice. "
        "Please consult with your doctor for medical guidance."
    )

    # For short responses that are mostly medical advice, replace entirely
    if len(text) < 100:
        return disclaimer

    # For longer responses, append disclaimer
    return text + f" (Note: {disclaimer})"
