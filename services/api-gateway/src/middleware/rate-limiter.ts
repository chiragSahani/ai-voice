/**
 * Express rate-limiting middleware backed by the RateLimiterService.
 *
 * Three tiers:
 *   auth  — 5 requests / minute  (login, refresh)
 *   api   — 30 requests / second (general API proxy)
 *   heavy — 10 requests / minute (bulk exports, reports)
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger } from '@shared/logger';
import { RateLimiterService } from '../services/rate-limiter.service';
import { RateLimitTier } from '../config';

const logger = getLogger();

export type RateLimitKeyFn = (req: Request) => string;

/**
 * Create a rate-limiting Express middleware for a given tier.
 */
export function createRateLimiter(
  rateLimiter: RateLimiterService,
  tier: RateLimitTier,
  keyFn?: RateLimitKeyFn,
) {
  const resolveKey = keyFn ?? defaultKeyFn;

  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    const key = resolveKey(req);

    try {
      const result = await rateLimiter.checkLimit(key, tier.windowMs, tier.maxRequests);

      // Always set rate-limit headers
      res.setHeader('X-RateLimit-Limit', result.limit);
      res.setHeader('X-RateLimit-Remaining', Math.max(0, result.remaining));
      res.setHeader('X-RateLimit-Reset', Math.ceil(result.resetAt / 1000));

      if (!result.allowed) {
        const retryAfter = Math.ceil((result.resetAt - Date.now()) / 1000);
        res.setHeader('Retry-After', Math.max(1, retryAfter));

        logger.warn({ key, tier: tier.windowMs, limit: tier.maxRequests }, 'Rate limit exceeded');

        res.status(429).json({
          error: {
            code: 'RATE_LIMIT_EXCEEDED',
            message: 'Too many requests — please try again later',
            retryAfter: Math.max(1, retryAfter),
          },
        });
        return;
      }

      next();
    } catch (err) {
      // Fail open — let the request through if rate limiter is broken
      logger.error({ error: (err as Error).message }, 'Rate limiter middleware error — failing open');
      next();
    }
  };
}

/**
 * Default key derivation: IP address (respects X-Forwarded-For).
 */
function defaultKeyFn(req: Request): string {
  const forwarded = req.headers['x-forwarded-for'];
  const ip = forwarded
    ? (Array.isArray(forwarded) ? forwarded[0] : forwarded.split(',')[0]).trim()
    : req.ip || req.socket.remoteAddress || 'unknown';
  return `ip:${ip}`;
}

/**
 * Key function that combines IP with user ID when authenticated.
 */
export function userKeyFn(req: Request): string {
  const base = defaultKeyFn(req);
  if (req.user?.sub) {
    return `user:${req.user.sub}`;
  }
  return base;
}

/**
 * Key function for auth endpoints — uses IP only to prevent brute force.
 */
export function authKeyFn(req: Request): string {
  return `auth:${defaultKeyFn(req)}`;
}
