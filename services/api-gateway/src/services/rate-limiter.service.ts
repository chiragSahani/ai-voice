/**
 * Redis-backed sliding window rate limiter.
 *
 * Uses a sorted set per key where each member is a request timestamp (ms).
 * On each check we trim entries outside the window, count remaining, and
 * decide whether the request is allowed.
 */

import { Redis } from 'ioredis';
import { getLogger } from '@shared/logger';
import { RateLimitResult } from '../models/domain';

const KEY_PREFIX = 'gateway:ratelimit:';

export class RateLimiterService {
  private readonly logger = getLogger();

  constructor(private readonly redis: Redis) {}

  /**
   * Check whether a request identified by `key` is within the rate limit.
   *
   * @param key       Unique identifier (e.g. IP, userId, or route group)
   * @param windowMs  Sliding window size in milliseconds
   * @param maxRequests Maximum requests allowed within the window
   * @returns RateLimitResult with allowed flag, remaining quota, and reset time
   */
  async checkLimit(
    key: string,
    windowMs: number,
    maxRequests: number,
  ): Promise<RateLimitResult> {
    const redisKey = `${KEY_PREFIX}${key}`;
    const now = Date.now();
    const windowStart = now - windowMs;

    try {
      // Execute as a pipeline for atomicity
      const pipeline = this.redis.pipeline();

      // 1. Remove entries outside the current window
      pipeline.zremrangebyscore(redisKey, 0, windowStart);

      // 2. Count current entries in the window
      pipeline.zcard(redisKey);

      // 3. Add the current request (optimistically)
      pipeline.zadd(redisKey, now.toString(), `${now}:${Math.random().toString(36).slice(2, 8)}`);

      // 4. Set expiry on the key so it auto-cleans
      pipeline.pexpire(redisKey, windowMs);

      const results = await pipeline.exec();

      if (!results) {
        this.logger.error({ key }, 'Rate limiter pipeline returned null');
        // Fail open — allow the request
        return { allowed: true, remaining: maxRequests - 1, resetAt: now + windowMs, limit: maxRequests };
      }

      // zcard result is at index 1
      const currentCount = (results[1][1] as number) || 0;

      if (currentCount >= maxRequests) {
        // Remove the optimistically added entry
        const lastResult = results[2];
        if (lastResult && !lastResult[0]) {
          // We added an entry but the user is over limit — remove it
          await this.redis.zremrangebyscore(redisKey, now, now + 1);
        }

        return {
          allowed: false,
          remaining: 0,
          resetAt: now + windowMs,
          limit: maxRequests,
        };
      }

      return {
        allowed: true,
        remaining: maxRequests - currentCount - 1,
        resetAt: now + windowMs,
        limit: maxRequests,
      };
    } catch (err) {
      this.logger.error({ error: (err as Error).message, key }, 'Rate limiter error — failing open');
      // Fail open so the gateway does not block requests when Redis is down
      return { allowed: true, remaining: maxRequests, resetAt: now + windowMs, limit: maxRequests };
    }
  }

  /**
   * Reset rate limit counters for a given key (admin / testing use).
   */
  async resetLimit(key: string): Promise<void> {
    await this.redis.del(`${KEY_PREFIX}${key}`);
  }
}
