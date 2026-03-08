/**
 * IoRedis connection factory.
 */

import Redis from 'ioredis';
import { getLogger } from './logger';

export type { Redis };

let client: Redis | null = null;

export function getRedisClient(options?: {
  host?: string;
  port?: number;
  password?: string;
  db?: number;
}): Redis {
  if (client) return client;

  const logger = getLogger();

  client = new Redis({
    host: options?.host || process.env.REDIS_HOST || 'localhost',
    port: options?.port || parseInt(process.env.REDIS_PORT || '6379', 10),
    password: options?.password || process.env.REDIS_PASSWORD || undefined,
    db: options?.db ?? parseInt(process.env.REDIS_DB || '0', 10),
    maxRetriesPerRequest: 3,
    retryStrategy(times: number) {
      const delay = Math.min(times * 200, 5000);
      return delay;
    },
    lazyConnect: false,
  });

  client.on('connect', () => {
    logger.info('Redis connected');
  });

  client.on('error', (err: Error) => {
    logger.error({ error: err.message }, 'Redis error');
  });

  client.on('close', () => {
    logger.warn('Redis connection closed');
  });

  return client;
}

export async function closeRedis(): Promise<void> {
  if (client) {
    await client.quit();
    client = null;
  }
}

export async function pingRedis(redis: Redis): Promise<boolean> {
  try {
    const result = await redis.ping();
    return result === 'PONG';
  } catch {
    return false;
  }
}
