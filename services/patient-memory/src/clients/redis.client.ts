/**
 * Redis client initialization for Patient Memory service.
 */

import { getRedisClient, closeRedis } from '../../../shared/typescript/src/redis-client';
import { getConfig } from '../config';
import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

export function initRedis() {
  const config = getConfig();
  logger.info({ host: config.redis.host, port: config.redis.port }, 'Initializing Redis client');
  return getRedisClient({
    host: config.redis.host,
    port: config.redis.port,
    password: config.redis.password || undefined,
    db: config.redis.db,
  });
}

export async function shutdownRedis(): Promise<void> {
  await closeRedis();
}
