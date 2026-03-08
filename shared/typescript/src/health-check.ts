/**
 * Health check route factory for Express services.
 */

import { Router, Request, Response } from 'express';
import { pingRedis, Redis } from './redis-client';
import { pingMongo } from './mongo-client';

export interface HealthDependency {
  name: string;
  check: () => Promise<boolean>;
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  uptime_s: number;
  checks: Record<string, 'ok' | 'fail'>;
}

const startTime = Date.now();

export function createHealthRouter(
  version: string,
  dependencies: HealthDependency[] = [],
): Router {
  const router = Router();

  router.get('/health', async (_req: Request, res: Response) => {
    const checks: Record<string, 'ok' | 'fail'> = {};
    let allHealthy = true;

    for (const dep of dependencies) {
      try {
        const ok = await dep.check();
        checks[dep.name] = ok ? 'ok' : 'fail';
        if (!ok) allHealthy = false;
      } catch {
        checks[dep.name] = 'fail';
        allHealthy = false;
      }
    }

    const status: HealthStatus = {
      status: allHealthy ? 'healthy' : 'degraded',
      version,
      uptime_s: Math.floor((Date.now() - startTime) / 1000),
      checks,
    };

    res.status(allHealthy ? 200 : 503).json(status);
  });

  return router;
}

export function mongoHealthCheck(): HealthDependency {
  return {
    name: 'mongodb',
    check: pingMongo,
  };
}

export function redisHealthCheck(redis: Redis): HealthDependency {
  return {
    name: 'redis',
    check: () => pingRedis(redis),
  };
}
