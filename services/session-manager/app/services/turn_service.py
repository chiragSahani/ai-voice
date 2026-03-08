"""Turn management service for conversation history stored in Redis lists."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.logging import get_logger

from app.config import get_config
from app.models.domain import Turn, TurnRole
from app.services.session_service import _session_key, increment_turn_count
from app.services.summarizer import summarize_turns, get_summary, store_summary

logger = get_logger("turn_service")

TURNS_SUFFIX = ":turns"


def _turns_key(session_id: str) -> str:
    return f"{_session_key(session_id)}{TURNS_SUFFIX}"


async def add_turn(
    redis: aioredis.Redis,
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
    tool_results: list[dict] | None = None,
    timestamp: str | None = None,
) -> tuple[Turn, int]:
    """Add a conversation turn to a session.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.
        role: Turn role (user, assistant, system, tool).
        content: Turn text content.
        tool_calls: Optional list of tool call descriptors.
        tool_results: Optional list of tool call results.
        timestamp: Optional explicit timestamp.

    Returns:
        Tuple of (created Turn, turn index).
    """
    config = get_config()

    turn = Turn(
        role=TurnRole(role),
        content=content,
        tool_calls=tool_calls,
        tool_results=tool_results,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
    )

    key = _turns_key(session_id)
    serialized = json.dumps(turn.to_dict())

    pipe = redis.pipeline()
    pipe.rpush(key, serialized)
    pipe.expire(key, config.session_ttl_seconds)
    results = await pipe.execute()

    # results[0] is the new list length (= index + 1)
    index = int(results[0]) - 1
    new_count = await increment_turn_count(redis, session_id)

    logger.debug(
        "turn_added",
        session_id=session_id,
        role=role,
        index=index,
        turn_count=new_count,
    )

    # Auto-summarize if turn count exceeds threshold
    if new_count > config.summarize_threshold:
        await _auto_summarize(redis, session_id, config.summary_keep_recent)

    return turn, index


async def get_turns(
    redis: aioredis.Redis,
    session_id: str,
    limit: int = 0,
    offset: int = 0,
) -> tuple[list[Turn], int]:
    """Get turns from a session with pagination.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.
        limit: Max turns to return (0 = all).
        offset: Number of turns to skip from the start.

    Returns:
        Tuple of (list of Turns, total turn count).
    """
    key = _turns_key(session_id)
    total = await redis.llen(key)

    if limit > 0:
        start = offset
        end = offset + limit - 1
    else:
        start = offset
        end = -1

    raw_turns = await redis.lrange(key, start, end)

    turns: list[Turn] = []
    for raw in raw_turns:
        data = json.loads(raw)
        turns.append(Turn.from_dict(data))

    return turns, int(total)


async def get_recent_turns(
    redis: aioredis.Redis,
    session_id: str,
    n: int = 10,
) -> list[Turn]:
    """Get the most recent n turns from a session.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.
        n: Number of recent turns to retrieve.

    Returns:
        List of the most recent Turns.
    """
    key = _turns_key(session_id)
    # LRANGE with negative indices: -n to -1 gives last n elements
    raw_turns = await redis.lrange(key, -n, -1)

    turns: list[Turn] = []
    for raw in raw_turns:
        data = json.loads(raw)
        turns.append(Turn.from_dict(data))

    return turns


async def _auto_summarize(
    redis: aioredis.Redis,
    session_id: str,
    keep_recent: int,
) -> None:
    """Auto-summarize older turns when threshold is exceeded.

    Summarizes all turns except the most recent `keep_recent` turns,
    stores the summary, and trims the turn list.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.
        keep_recent: Number of recent turns to preserve verbatim.
    """
    key = _turns_key(session_id)
    total = await redis.llen(key)

    if total <= keep_recent:
        return

    # Get older turns that should be summarized
    older_count = total - keep_recent
    raw_older = await redis.lrange(key, 0, older_count - 1)

    older_turns: list[Turn] = []
    for raw in raw_older:
        data = json.loads(raw)
        older_turns.append(Turn.from_dict(data))

    if not older_turns:
        return

    # Get existing summary to append to
    existing_summary = await get_summary(redis, session_id)

    # Generate summary of older turns
    new_summary = await summarize_turns(older_turns, existing_summary)
    await store_summary(redis, session_id, new_summary)

    # Trim the list to keep only recent turns
    await redis.ltrim(key, older_count, -1)

    logger.info(
        "turns_auto_summarized",
        session_id=session_id,
        summarized_count=older_count,
        kept_recent=keep_recent,
    )
