"""Session CRUD service backed by Redis hashes."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from shared.events import STREAM_SESSIONS, publish_event
from shared.exceptions import NotFoundError
from shared.logging import get_logger

from app.config import get_config
from app.models.domain import Session, SessionStatus

logger = get_logger("session_service")

SESSION_KEY_PREFIX = "session:"
SESSION_INDEX_KEY = "sessions:index"
CLINIC_INDEX_PREFIX = "sessions:clinic:"


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _clinic_index_key(clinic_id: str) -> str:
    return f"{CLINIC_INDEX_PREFIX}{clinic_id}"


def _serialize_session(session: Session) -> dict[str, str]:
    """Serialize a Session to flat string dict for Redis HSET."""
    data = session.to_dict()
    return {
        k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        for k, v in data.items()
    }


def _deserialize_session(data: dict[str, str]) -> Session:
    """Deserialize a Redis hash dict back to a Session."""
    parsed: dict[str, Any] = {}
    for k, v in data.items():
        if k in ("metadata", "patient_context"):
            try:
                parsed[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed[k] = {}
        elif k == "turn_count":
            parsed[k] = int(v)
        else:
            parsed[k] = v
    return Session.from_dict(parsed)


async def create_session(
    redis: aioredis.Redis,
    patient_id: str,
    language: str = "en",
    channel: str = "voice",
    clinic_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> Session:
    """Create a new session and store it in Redis.

    Args:
        redis: Async Redis client.
        patient_id: Patient identifier.
        language: Session language code.
        channel: Communication channel (voice, chat, etc.).
        clinic_id: Clinic identifier.
        metadata: Optional additional metadata.

    Returns:
        The newly created Session.
    """
    config = get_config()
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    session = Session(
        id=session_id,
        patient_id=patient_id,
        language=language,
        channel=channel,
        clinic_id=clinic_id,
        status=SessionStatus.ACTIVE,
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
        turn_count=0,
    )

    key = _session_key(session_id)
    pipe = redis.pipeline()
    pipe.hset(key, mapping=_serialize_session(session))
    pipe.expire(key, config.session_ttl_seconds)
    # Index by clinic for listing
    if clinic_id:
        pipe.sadd(_clinic_index_key(clinic_id), session_id)
    # Global session index
    pipe.zadd(SESSION_INDEX_KEY, {session_id: datetime.now(timezone.utc).timestamp()})
    await pipe.execute()

    logger.info(
        "session_created",
        session_id=session_id,
        patient_id=patient_id,
        language=language,
        channel=channel,
    )

    await publish_event(
        redis,
        STREAM_SESSIONS,
        "session.created",
        {"session_id": session_id, "patient_id": patient_id, "clinic_id": clinic_id},
        source="session-manager",
        correlation_id=session_id,
    )

    return session


async def get_session(redis: aioredis.Redis, session_id: str) -> Session:
    """Retrieve a session by ID.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.

    Returns:
        The Session object.

    Raises:
        NotFoundError: If session does not exist.
    """
    key = _session_key(session_id)
    data = await redis.hgetall(key)

    if not data:
        raise NotFoundError("Session", session_id)

    return _deserialize_session(data)


async def update_session(
    redis: aioredis.Redis,
    session_id: str,
    language: str | None = None,
    patient_context: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Session:
    """Update an existing session's mutable fields.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.
        language: New language code.
        patient_context: New patient context data.
        metadata: New metadata.

    Returns:
        The updated Session.

    Raises:
        NotFoundError: If session does not exist.
    """
    session = await get_session(redis, session_id)
    now = datetime.now(timezone.utc).isoformat()

    updates: dict[str, str] = {"updated_at": now}

    if language is not None:
        session.language = language
        updates["language"] = language

    if patient_context is not None:
        session.patient_context = patient_context
        updates["patient_context"] = json.dumps(patient_context)

    if metadata is not None:
        merged = {**session.metadata, **metadata}
        session.metadata = merged
        updates["metadata"] = json.dumps(merged)

    session.updated_at = now
    key = _session_key(session_id)
    await redis.hset(key, mapping=updates)

    logger.info("session_updated", session_id=session_id, fields=list(updates.keys()))
    return session


async def end_session(redis: aioredis.Redis, session_id: str) -> Session:
    """Mark a session as ended.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.

    Returns:
        The ended Session.

    Raises:
        NotFoundError: If session does not exist.
    """
    session = await get_session(redis, session_id)
    now = datetime.now(timezone.utc).isoformat()

    session.status = SessionStatus.ENDED
    session.updated_at = now

    key = _session_key(session_id)
    await redis.hset(key, mapping={
        "status": SessionStatus.ENDED.value,
        "updated_at": now,
    })

    # Keep ended sessions for a longer period (24 hours) for auditing
    await redis.expire(key, 86400)

    logger.info("session_ended", session_id=session_id)

    await publish_event(
        redis,
        STREAM_SESSIONS,
        "session.ended",
        {
            "session_id": session_id,
            "patient_id": session.patient_id,
            "turn_count": session.turn_count,
        },
        source="session-manager",
        correlation_id=session_id,
    )

    return session


async def list_sessions(
    redis: aioredis.Redis,
    clinic_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Session], int]:
    """List sessions with optional filtering and pagination.

    Args:
        redis: Async Redis client.
        clinic_id: Filter by clinic ID.
        status: Filter by session status.
        page: Page number (1-based).
        limit: Page size.

    Returns:
        Tuple of (session list, total count).
    """
    if clinic_id:
        session_ids = list(await redis.smembers(_clinic_index_key(clinic_id)))
    else:
        # Use the sorted set index (most recent first)
        session_ids = await redis.zrevrange(SESSION_INDEX_KEY, 0, -1)

    # Fetch all sessions (filter in memory for simplicity with Redis)
    sessions: list[Session] = []
    for sid in session_ids:
        try:
            session = await get_session(redis, sid)
            if status and session.status.value != status:
                continue
            sessions.append(session)
        except NotFoundError:
            # Session expired or deleted, clean up index
            await redis.zrem(SESSION_INDEX_KEY, sid)
            if clinic_id:
                await redis.srem(_clinic_index_key(clinic_id), sid)

    total = len(sessions)
    start = (page - 1) * limit
    end = start + limit
    return sessions[start:end], total


async def delete_session(redis: aioredis.Redis, session_id: str) -> None:
    """Delete a session and all associated data.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.

    Raises:
        NotFoundError: If session does not exist.
    """
    session = await get_session(redis, session_id)

    key = _session_key(session_id)
    turns_key = f"{key}:turns"
    summary_key = f"{key}:summary"

    pipe = redis.pipeline()
    pipe.delete(key, turns_key, summary_key)
    pipe.zrem(SESSION_INDEX_KEY, session_id)
    if session.clinic_id:
        pipe.srem(_clinic_index_key(session.clinic_id), session_id)
    await pipe.execute()

    logger.info("session_deleted", session_id=session_id)

    await publish_event(
        redis,
        STREAM_SESSIONS,
        "session.deleted",
        {"session_id": session_id, "patient_id": session.patient_id},
        source="session-manager",
        correlation_id=session_id,
    )


async def increment_turn_count(redis: aioredis.Redis, session_id: str) -> int:
    """Atomically increment the turn count for a session.

    Args:
        redis: Async Redis client.
        session_id: Session identifier.

    Returns:
        The new turn count.
    """
    key = _session_key(session_id)
    new_count = await redis.hincrby(key, "turn_count", 1)
    await redis.hset(key, "updated_at", datetime.now(timezone.utc).isoformat())
    return int(new_count)
