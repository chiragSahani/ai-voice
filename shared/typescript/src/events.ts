/**
 * Redis Streams event bus for async inter-service communication.
 */

import { v4 as uuidv4 } from 'uuid';
import type Redis from 'ioredis';
import { getLogger } from './logger';

const logger = getLogger();

// Stream names
export const STREAM_APPOINTMENTS = 'events:appointments';
export const STREAM_SESSIONS = 'events:sessions';
export const STREAM_CAMPAIGNS = 'events:campaigns';
export const STREAM_AUDIT = 'events:audit';
export const STREAM_ALERTS = 'events:alerts';
export const STREAM_ANALYTICS = 'events:analytics';

export interface EventEnvelope {
  event_id: string;
  event_type: string;
  timestamp: string;
  source: string;
  correlation_id: string;
  payload: string; // JSON-encoded
}

export async function publishEvent(
  redis: Redis,
  stream: string,
  eventType: string,
  payload: Record<string, unknown>,
  source: string,
  correlationId?: string,
): Promise<string> {
  const message: EventEnvelope = {
    event_id: uuidv4(),
    event_type: eventType,
    timestamp: new Date().toISOString(),
    source,
    correlation_id: correlationId || '',
    payload: JSON.stringify(payload),
  };

  const msgId = await redis.xadd(
    stream,
    'MAXLEN',
    '~',
    '100000',
    '*',
    ...Object.entries(message).flat(),
  );

  logger.debug({ stream, eventType, msgId }, 'Event published');
  return msgId as string;
}

export async function createConsumerGroup(
  redis: Redis,
  stream: string,
  group: string,
): Promise<void> {
  try {
    await redis.xgroup('CREATE', stream, group, '0', 'MKSTREAM');
    logger.info({ stream, group }, 'Consumer group created');
  } catch (err: any) {
    if (err.message?.includes('BUSYGROUP')) {
      // Group already exists
    } else {
      throw err;
    }
  }
}

export async function consumeEvents(
  redis: Redis,
  stream: string,
  group: string,
  consumer: string,
  count: number = 10,
  blockMs: number = 5000,
): Promise<EventEnvelope[]> {
  const results = await redis.xreadgroup(
    'GROUP',
    group,
    consumer,
    'COUNT',
    count.toString(),
    'BLOCK',
    blockMs.toString(),
    'STREAMS',
    stream,
    '>',
  );

  if (!results) return [];

  const events: EventEnvelope[] = [];
  for (const [, messages] of results) {
    for (const [msgId, fields] of messages as [string, string[]][]) {
      const data: Record<string, string> = {};
      for (let i = 0; i < fields.length; i += 2) {
        data[fields[i]] = fields[i + 1];
      }
      events.push({ ...data, event_id: data.event_id || msgId } as EventEnvelope);
    }
  }

  return events;
}

export async function ackEvent(
  redis: Redis,
  stream: string,
  group: string,
  msgId: string,
): Promise<void> {
  await redis.xack(stream, group, msgId);
}
