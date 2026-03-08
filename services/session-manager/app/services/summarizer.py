"""Turn summarization service.

Summarizes older conversation turns to reduce context size while
preserving important information for the LLM.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from shared.logging import get_logger

from app.models.domain import Turn
from app.services.session_service import _session_key

logger = get_logger("summarizer")

SUMMARY_SUFFIX = ":summary"


def _summary_key(session_id: str) -> str:
    return f"{_session_key(session_id)}{SUMMARY_SUFFIX}"


async def summarize_turns(
    turns: list[Turn],
    existing_summary: str | None = None,
) -> str:
    """Summarize a list of conversation turns into a concise text summary.

    This implementation uses extractive summarization (key content extraction)
    without requiring an external LLM call, keeping latency low. For
    production use with higher quality requirements, this can be replaced
    with an LLM-based summarizer.

    Args:
        turns: List of turns to summarize.
        existing_summary: Optional existing summary to prepend.

    Returns:
        Summary string combining existing and new summaries.
    """
    if not turns:
        return existing_summary or ""

    summary_parts: list[str] = []

    if existing_summary:
        summary_parts.append(existing_summary)

    # Extract key information from turns
    user_requests: list[str] = []
    assistant_actions: list[str] = []
    tool_results_summary: list[str] = []

    for turn in turns:
        content = turn.content.strip()
        if not content:
            continue

        if turn.role.value == "user":
            # Keep user intents concise
            truncated = content[:200] if len(content) > 200 else content
            user_requests.append(truncated)

        elif turn.role.value == "assistant":
            # Summarize assistant responses
            truncated = content[:150] if len(content) > 150 else content
            assistant_actions.append(truncated)

        elif turn.role.value == "tool":
            # Capture tool outcomes
            if turn.tool_results:
                for result in turn.tool_results:
                    outcome = result.get("result", result.get("output", str(result)))
                    truncated = str(outcome)[:100]
                    tool_results_summary.append(truncated)
            elif content:
                truncated = content[:100]
                tool_results_summary.append(truncated)

    # Build structured summary
    new_parts: list[str] = []

    if user_requests:
        new_parts.append(f"Patient said: {'; '.join(user_requests[-5:])}")

    if assistant_actions:
        new_parts.append(f"Assistant responded: {'; '.join(assistant_actions[-5:])}")

    if tool_results_summary:
        new_parts.append(f"Tool results: {'; '.join(tool_results_summary[-3:])}")

    if new_parts:
        summary_parts.append(" | ".join(new_parts))

    combined = " || ".join(summary_parts)

    # Cap total summary length to prevent unbounded growth
    max_summary_length = 2000
    if len(combined) > max_summary_length:
        combined = combined[-max_summary_length:]

    logger.debug(
        "turns_summarized",
        input_turns=len(turns),
        summary_length=len(combined),
    )

    return combined


async def get_summary(redis: aioredis.Redis, session_id: str) -> str | None:
    """Retrieve the stored summary for a session.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.

    Returns:
        Summary string if exists, None otherwise.
    """
    key = _summary_key(session_id)
    summary = await redis.get(key)
    return summary if summary else None


async def store_summary(
    redis: aioredis.Redis,
    session_id: str,
    summary: str,
) -> None:
    """Store a summary for a session.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.
        summary: Summary text to store.
    """
    from app.config import get_config

    config = get_config()
    key = _summary_key(session_id)
    await redis.set(key, summary, ex=config.session_ttl_seconds)

    logger.debug("summary_stored", session_id=session_id, length=len(summary))
