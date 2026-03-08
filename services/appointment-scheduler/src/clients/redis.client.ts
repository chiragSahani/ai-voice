/**
 * Redis client initialization for the Appointment Scheduler service.
 */

import { getRedisClient, closeRedis } from '../../../../shared/typescript/src';
import { getConfig } from '../config';

export function initRedis() {
  const config = getConfig();
  return getRedisClient({
    host: config.redis.host,
    port: config.redis.port,
    password: config.redis.password || undefined,
    db: config.redis.db,
  });
}

export { closeRedis };
