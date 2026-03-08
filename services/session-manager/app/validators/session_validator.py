"""Validation functions for session operations."""

from __future__ import annotations

import redis.asyncio as aioredis

from shared.exceptions import NotFoundError, ValidationError

from app.models.domain import TurnRole
from app.models.requests import AddTurnRequest, CreateSessionRequest
from app.services.session_service import _session_key

# Valid language codes supported by the platform
SUPPORTED_LANGUAGES = {"en", "hi", "ta"}

# Valid channels
SUPPORTED_CHANNELS = {"voice", "chat", "web", "api"}

# Valid turn roles
VALID_ROLES = {r.value for r in TurnRole}


def validate_create_session(request: CreateSessionRequest) -> None:
    """Validate a session creation request.

    Args:
        request: The create session request to validate.

    Raises:
        ValidationError: If validation fails.
    """
    if not request.patient_id or not request.patient_id.strip():
        raise ValidationError("patient_id is required and cannot be empty", field="patient_id")

    if len(request.patient_id) > 128:
        raise ValidationError(
            "patient_id must be 128 characters or fewer", field="patient_id"
        )

    if request.language and request.language not in SUPPORTED_LANGUAGES:
        raise ValidationError(
            f"Unsupported language: {request.language}. Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
            field="language",
        )

    if request.channel and request.channel not in SUPPORTED_CHANNELS:
        raise ValidationError(
            f"Unsupported channel: {request.channel}. Supported: {', '.join(sorted(SUPPORTED_CHANNELS))}",
            field="channel",
        )


def validate_turn(request: AddTurnRequest) -> None:
    """Validate a turn addition request.

    Args:
        request: The add turn request to validate.

    Raises:
        ValidationError: If validation fails.
    """
    if request.role not in VALID_ROLES:
        raise ValidationError(
            f"Invalid role: {request.role}. Must be one of: {', '.join(sorted(VALID_ROLES))}",
            field="role",
        )

    if not request.content and request.role != TurnRole.TOOL.value:
        raise ValidationError(
            "content is required for non-tool turns",
            field="content",
        )

    if request.role == TurnRole.TOOL.value and not request.tool_results and not request.content:
        raise ValidationError(
            "Tool turns must include content or tool_results",
            field="tool_results",
        )

    # Validate tool_calls structure if present
    if request.tool_calls:
        for i, tc in enumerate(request.tool_calls):
            if not isinstance(tc, dict):
                raise ValidationError(
                    f"tool_calls[{i}] must be a dictionary",
                    field="tool_calls",
                )
            if "name" not in tc:
                raise ValidationError(
                    f"tool_calls[{i}] must include a 'name' field",
                    field="tool_calls",
                )


async def validate_session_exists(redis: aioredis.Redis, session_id: str) -> None:
    """Validate that a session exists in Redis.

    Args:
        redis: Async Redis client.
        session_id: Session identifier to check.

    Raises:
        NotFoundError: If session does not exist.
    """
    key = _session_key(session_id)
    exists = await redis.exists(key)
    if not exists:
        raise NotFoundError("Session", session_id)
