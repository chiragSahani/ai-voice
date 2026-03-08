/**
 * BullMQ queue definitions for outbound call processing.
 */

import { Queue, QueueEvents } from 'bullmq';
import { getLogger } from '../../../shared/typescript/src';
import { config } from '../config';

const logger = getLogger();

export interface CallJobData {
  callId: string;
  campaignId: string;
  patientId: string;
  clinicId: string;
  messageTemplate: string;
  language: string;
  attemptNumber: number;
}

export const CALL_QUEUE_NAME = 'campaign-calls';

let callQueue: Queue<CallJobData> | null = null;
let callQueueEvents: QueueEvents | null = null;

export function getCallQueue(): Queue<CallJobData> {
  if (callQueue) return callQueue;

  callQueue = new Queue<CallJobData>(CALL_QUEUE_NAME, {
    connection: {
      host: config.redis.host,
      port: config.redis.port,
      password: config.redis.password || undefined,
      db: config.redis.db,
    },
    defaultJobOptions: {
      attempts: 1, // Retries are handled explicitly via retry-queue
      timeout: config.bullmq.defaultJobTimeout,
      removeOnComplete: {
        count: 1000,
        age: 24 * 3600, // Keep for 24 hours
      },
      removeOnFail: {
        count: 5000,
        age: 7 * 24 * 3600, // Keep failures for 7 days
      },
    },
  });

  callQueue.on('error', (err) => {
    logger.error({ error: err.message }, 'Call queue error');
  });

  logger.info('Call queue initialized');
  return callQueue;
}

export function getCallQueueEvents(): QueueEvents {
  if (callQueueEvents) return callQueueEvents;

  callQueueEvents = new QueueEvents(CALL_QUEUE_NAME, {
    connection: {
      host: config.redis.host,
      port: config.redis.port,
      password: config.redis.password || undefined,
      db: config.redis.db,
    },
  });

  return callQueueEvents;
}

export async function closeCallQueue(): Promise<void> {
  if (callQueueEvents) {
    await callQueueEvents.close();
    callQueueEvents = null;
  }
  if (callQueue) {
    await callQueue.close();
    callQueue = null;
  }
  logger.info('Call queue closed');
}
