/**
 * Health check router for the Appointment Scheduler service.
 */

import {
  createHealthRouter,
  mongoHealthCheck,
  redisHealthCheck,
} from '../../../shared/typescript/src';
import { getRedisClient } from '../../../shared/typescript/src';

const VERSION = process.env.npm_package_version || '1.0.0';

export function createAppHealthRouter() {
  const redis = getRedisClient();

  return createHealthRouter(VERSION, [
    mongoHealthCheck(),
    redisHealthCheck(redis),
  ]);
}
