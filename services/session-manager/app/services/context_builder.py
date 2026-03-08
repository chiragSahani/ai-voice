"""LLM context assembly service.

Builds a ConversationContext that fits within the configured token budget,
combining system prompt, patient info, conversation summary, and recent turns.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from shared.logging import get_logger

from app.config import get_config
from app.models.domain import ConversationContext, Turn
from app.services.session_service import get_session
from app.services.turn_service import get_recent_turns
from app.services.summarizer import get_summary

logger = get_logger("context_builder")

# Approximate tokens per character ratio for estimation
CHARS_PER_TOKEN = 4

SYSTEM_PROMPT_TEMPLATE = """You are a multilingual clinical appointment booking assistant.
You help patients book, reschedule, and cancel appointments at healthcare clinics.

Language: {language}
Clinic ID: {clinic_id}

Guidelines:
- Be polite, professional, and empathetic
- Collect required information: patient name, preferred date/time, doctor preference, reason for visit
- Confirm all details before booking
- Handle rescheduling and cancellation requests
- Support English, Hindi, and Tamil
- If unsure about medical terminology, ask for clarification
- Never provide medical advice or diagnoses
- Protect patient privacy at all times"""


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


def _turn_to_message(turn: Turn) -> dict[str, Any]:
    """Convert a Turn to an LLM message dict.

    Args:
        turn: Conversation turn.

    Returns:
        Message dictionary with role and content.
    """
    message: dict[str, Any] = {
        "role": turn.role.value if hasattr(turn.role, "value") else turn.role,
        "content": turn.content,
    }

    # Include tool calls inline for assistant turns
    if turn.tool_calls:
        message["tool_calls"] = turn.tool_calls

    # Include tool results for tool turns
    if turn.tool_results:
        message["tool_results"] = turn.tool_results

    return message


async def build_context(
    redis: aioredis.Redis,
    session_id: str,
) -> ConversationContext:
    """Assemble a complete LLM context for a session.

    Combines system prompt, patient information, conversation summary,
    and recent turns, fitting within the configured token budget.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.

    Returns:
        Assembled ConversationContext.
    """
    config = get_config()
    max_tokens = config.context_max_tokens

    # 1. Get session data
    session = await get_session(redis, session_id)

    # 2. Build system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        language=session.language,
        clinic_id=session.clinic_id,
    )
    token_budget = max_tokens - _estimate_tokens(system_prompt)

    # 3. Include patient context if available
    patient_info = session.patient_context
    if patient_info:
        patient_text = f"Patient context: {patient_info}"
        patient_tokens = _estimate_tokens(patient_text)
        token_budget -= patient_tokens

    # 4. Include conversation summary if available
    summary = await get_summary(redis, session_id)
    if summary:
        summary_tokens = _estimate_tokens(summary)
        token_budget -= summary_tokens

    # 5. Get recent turns that fit within remaining budget
    recent_turns = await get_recent_turns(redis, session_id, n=config.max_turns)

    messages: list[dict[str, Any]] = []
    total_turn_tokens = 0

    # Add turns from most recent backward, respecting token budget
    for turn in reversed(recent_turns):
        turn_msg = _turn_to_message(turn)
        turn_text = turn.content or ""
        turn_tokens = _estimate_tokens(turn_text)

        if total_turn_tokens + turn_tokens > token_budget:
            break

        messages.insert(0, turn_msg)
        total_turn_tokens += turn_tokens

    # Prepend summary as a system message if we have one
    if summary:
        messages.insert(0, {
            "role": "system",
            "content": f"Previous conversation summary: {summary}",
        })

    total_tokens = _estimate_tokens(system_prompt) + total_turn_tokens
    if patient_info:
        total_tokens += _estimate_tokens(str(patient_info))
    if summary:
        total_tokens += _estimate_tokens(summary)

    context = ConversationContext(
        system_prompt=system_prompt,
        messages=messages,
        patient_info=patient_info,
        summary=summary,
        turn_count=session.turn_count,
        token_estimate=total_tokens,
    )

    logger.debug(
        "context_built",
        session_id=session_id,
        message_count=len(messages),
        token_estimate=total_tokens,
        has_summary=summary is not None,
    )

    return context
