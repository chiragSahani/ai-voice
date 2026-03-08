"""Validation logic for LLM Agent gRPC requests."""

from typing import Optional

from shared.logging import get_logger

logger = get_logger("agent_validator")

SUPPORTED_LANGUAGES = {"en", "hi", "ta"}
VALID_ROLES = {"system", "user", "assistant", "tool"}
MAX_SESSION_ID_LENGTH = 128
MAX_CONTENT_LENGTH = 8192
MAX_MESSAGE_COUNT = 100
MAX_TRANSCRIPT_LENGTH = 4096


class ChatValidator:
    """Validates incoming Chat and Summarize gRPC requests."""

    def __init__(
        self,
        max_content_length: int = MAX_CONTENT_LENGTH,
        max_message_count: int = MAX_MESSAGE_COUNT,
        max_transcript_length: int = MAX_TRANSCRIPT_LENGTH,
    ):
        self._max_content_length = max_content_length
        self._max_message_count = max_message_count
        self._max_transcript_length = max_transcript_length

    def validate_chat_request(self, request) -> Optional[str]:
        """Validate a ChatRequest proto message.

        Args:
            request: ChatRequest protobuf message.

        Returns:
            Error message string if invalid, None if valid.
        """
        # Validate session_id
        error = self._validate_session_id(request.session_id)
        if error:
            return error

        # Validate transcript
        if not request.transcript or not request.transcript.strip():
            return "transcript must not be empty"

        if len(request.transcript) > self._max_transcript_length:
            return (
                f"transcript exceeds maximum length of {self._max_transcript_length} characters"
            )

        # Validate language
        error = self._validate_language(request.language)
        if error:
            return error

        # Validate history
        if len(request.history) > self._max_message_count:
            return (
                f"history exceeds maximum of {self._max_message_count} turns"
            )

        for i, turn in enumerate(request.history):
            error = self._validate_conversation_turn(turn, i)
            if error:
                return error

        return None

    def validate_summarize_request(self, request) -> Optional[str]:
        """Validate a SummarizeRequest proto message.

        Args:
            request: SummarizeRequest protobuf message.

        Returns:
            Error message string if invalid, None if valid.
        """
        error = self._validate_session_id(request.session_id)
        if error:
            return error

        if not request.turns:
            return "turns must not be empty"

        if len(request.turns) > self._max_message_count:
            return f"turns exceeds maximum of {self._max_message_count}"

        for i, turn in enumerate(request.turns):
            error = self._validate_conversation_turn(turn, i)
            if error:
                return error

        if request.language:
            error = self._validate_language(request.language)
            if error:
                return error

        return None

    def _validate_session_id(self, session_id: str) -> Optional[str]:
        """Validate session ID format.

        Args:
            session_id: Session identifier.

        Returns:
            Error message or None.
        """
        if not session_id or not session_id.strip():
            return "session_id must not be empty"

        if len(session_id) > MAX_SESSION_ID_LENGTH:
            return f"session_id exceeds maximum length of {MAX_SESSION_ID_LENGTH}"

        return None

    def _validate_language(self, language: str) -> Optional[str]:
        """Validate language code.

        Args:
            language: ISO 639-1 language code.

        Returns:
            Error message or None.
        """
        if language and language not in SUPPORTED_LANGUAGES:
            return (
                f"Unsupported language '{language}'. "
                f"Supported languages: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )
        return None

    def _validate_conversation_turn(self, turn, index: int) -> Optional[str]:
        """Validate a single conversation turn.

        Args:
            turn: ConversationTurn proto message.
            index: Turn index for error reporting.

        Returns:
            Error message or None.
        """
        if not turn.role:
            return f"history[{index}].role must not be empty"

        if turn.role not in VALID_ROLES:
            return (
                f"history[{index}].role '{turn.role}' is invalid. "
                f"Must be one of: {', '.join(sorted(VALID_ROLES))}"
            )

        # Tool messages must have content
        if turn.role == "tool" and not turn.content:
            return f"history[{index}]: tool messages must have content"

        # User messages must have content
        if turn.role == "user" and not turn.content:
            return f"history[{index}]: user messages must have content"

        # Content length check
        if turn.content and len(turn.content) > self._max_content_length:
            return (
                f"history[{index}].content exceeds maximum length of "
                f"{self._max_content_length} characters"
            )

        return None
