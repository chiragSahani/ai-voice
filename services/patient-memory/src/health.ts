/**
 * Health check router for the Patient Memory service.
 * Checks MongoDB and Redis connectivity.
 */

import { createHealthRouter, mongoHealthCheck, redisHealthCheck } from '../../shared/typescript/src/health-check';
import { getRedisClient } from '../../shared/typescript/src/redis-client';

const SERVICE_VERSION = process.env.npm_package_version || '1.0.0';

export function createPatientMemoryHealthRouter() {
  const redis = getRedisClient();

  return createHealthRouter(SERVICE_VERSION, [
    mongoHealthCheck(),
    redisHealthCheck(redis),
  ]);
}
