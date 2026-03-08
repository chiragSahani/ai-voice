/**
 * Redis client wrapper for the API Gateway.
 */

import { getRedisClient, closeRedis } from '@shared/redis-client';
import { GatewayConfig } from '../config';

export function initRedis(config: GatewayConfig) {
  return getRedisClient({
    host: config.redis.host,
    port: config.redis.port,
    password: config.redis.password || undefined,
    db: config.redis.db,
  });
}

export { closeRedis };
