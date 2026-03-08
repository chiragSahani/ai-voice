/**
 * Health check router for campaign engine.
 * Checks MongoDB, Redis, and BullMQ queue status.
 */

import { createHealthRouter, mongoHealthCheck, redisHealthCheck } from '../../shared/typescript/src';
import type { HealthDependency } from '../../shared/typescript/src';
import { getCallQueue } from './queues/call-queue';
import { getRetryQueue } from './queues/retry-queue';
import type Redis from 'ioredis';

function bullmqHealthCheck(queueName: string, getQueue: () => any): HealthDependency {
  return {
    name: `bullmq-${queueName}`,
    check: async () => {
      try {
        const queue = getQueue();
        // Verify queue is connected by checking waiting count
        await queue.getWaitingCount();
        return true;
      } catch {
        return false;
      }
    },
  };
}

export function createCampaignHealthRouter(redis: Redis) {
  return createHealthRouter('1.0.0', [
    mongoHealthCheck(),
    redisHealthCheck(redis),
    bullmqHealthCheck('calls', getCallQueue),
    bullmqHealthCheck('retries', getRetryQueue),
  ]);
}
