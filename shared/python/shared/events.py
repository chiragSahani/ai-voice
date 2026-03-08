"""Redis Streams event bus for async inter-service communication."""

import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.logging import get_logger

logger = get_logger("events")

# Stream names
STREAM_APPOINTMENTS = "events:appointments"
STREAM_SESSIONS = "events:sessions"
STREAM_CAMPAIGNS = "events:campaigns"
STREAM_AUDIT = "events:audit"
STREAM_ALERTS = "events:alerts"
STREAM_ANALYTICS = "events:analytics"


async def publish_event(
    redis_client: aioredis.Redis,
    stream: str,
    event_type: str,
    payload: dict,
    source: str,
    correlation_id: str | None = None,
) -> str:
    """Publish an event to a Redis Stream.

    Args:
        redis_client: Async Redis client.
        stream: Stream name to publish to.
        event_type: Event type identifier.
        payload: Event payload dictionary.
        source: Source service name.
        correlation_id: Optional correlation ID for tracing.

    Returns:
        Message ID assigned by Redis.
    """
    event_id = str(uuid.uuid4())
    message = {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "correlation_id": correlation_id or "",
        "payload": json.dumps(payload),
    }

    msg_id = await redis_client.xadd(stream, message, maxlen=100000)
    logger.debug("event_published", stream=stream, event_type=event_type, msg_id=msg_id)
    return msg_id


async def create_consumer_group(
    redis_client: aioredis.Redis,
    stream: str,
    group: str,
) -> None:
    """Create a consumer group for a stream.

    Args:
        redis_client: Async Redis client.
        stream: Stream name.
        group: Consumer group name.
    """
    try:
        await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("consumer_group_created", stream=stream, group=group)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass  # Group already exists
        else:
            raise


async def consume_events(
    redis_client: aioredis.Redis,
    stream: str,
    group: str,
    consumer: str,
    count: int = 10,
    block_ms: int = 5000,
) -> list[dict]:
    """Consume events from a stream as part of a consumer group.

    Args:
        redis_client: Async Redis client.
        stream: Stream name to consume from.
        group: Consumer group name.
        consumer: Consumer name within the group.
        count: Max messages to read.
        block_ms: Block timeout in milliseconds.

    Returns:
        List of event dictionaries.
    """
    results = await redis_client.xreadgroup(
        group,
        consumer,
        {stream: ">"},
        count=count,
        block=block_ms,
    )

    events = []
    for _stream_name, messages in results:
        for msg_id, data in messages:
            event = dict(data)
            event["_msg_id"] = msg_id
            if "payload" in event:
                event["payload"] = json.loads(event["payload"])
            events.append(event)

    return events


async def ack_event(
    redis_client: aioredis.Redis,
    stream: str,
    group: str,
    msg_id: str,
) -> None:
    """Acknowledge a consumed event.

    Args:
        redis_client: Async Redis client.
        stream: Stream name.
        group: Consumer group name.
        msg_id: Message ID to acknowledge.
    """
    await redis_client.xack(stream, group, msg_id)
