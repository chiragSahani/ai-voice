/**
 * BullMQ queue for scheduling call retries with exponential backoff.
 */

import { Queue } from 'bullmq';
import { getLogger } from '../../../shared/typescript/src';
import { config } from '../config';

const logger = getLogger();

export interface RetryJobData {
  callId: string;
  campaignId: string;
  patientId: string;
  clinicId: string;
  messageTemplate: string;
  language: string;
  attemptNumber: number;
  maxRetries: number;
  retryDelayMinutes: number;
}

export const RETRY_QUEUE_NAME = 'campaign-call-retries';

let retryQueue: Queue<RetryJobData> | null = null;

export function getRetryQueue(): Queue<RetryJobData> {
  if (retryQueue) return retryQueue;

  retryQueue = new Queue<RetryJobData>(RETRY_QUEUE_NAME, {
    connection: {
      host: config.redis.host,
      port: config.redis.port,
      password: config.redis.password || undefined,
      db: config.redis.db,
    },
    defaultJobOptions: {
      attempts: 1,
      removeOnComplete: {
        count: 500,
        age: 24 * 3600,
      },
      removeOnFail: {
        count: 2000,
        age: 7 * 24 * 3600,
      },
    },
  });

  retryQueue.on('error', (err) => {
    logger.error({ error: err.message }, 'Retry queue error');
  });

  logger.info('Retry queue initialized');
  return retryQueue;
}

export async function closeRetryQueue(): Promise<void> {
  if (retryQueue) {
    await retryQueue.close();
    retryQueue = null;
  }
  logger.info('Retry queue closed');
}

/**
 * Calculate exponential backoff delay in milliseconds.
 * Formula: baseDelayMinutes * 2^(attempt-1), capped at 24 hours.
 */
export function calculateBackoffDelay(attemptNumber: number, baseDelayMinutes: number): number {
  const backoffMultiplier = Math.pow(2, attemptNumber - 1);
  const delayMinutes = baseDelayMinutes * backoffMultiplier;
  const maxDelayMinutes = 24 * 60; // 24 hours cap
  const cappedMinutes = Math.min(delayMinutes, maxDelayMinutes);
  return cappedMinutes * 60 * 1000; // Convert to ms
}
