/**
 * BullMQ Worker for retry queue — processes call retries with exponential backoff.
 * Checks if campaign is still active before retrying.
 */

import { Worker, Job } from 'bullmq';
import { getLogger } from '../../../shared/typescript/src';
import { config } from '../config';
import { RETRY_QUEUE_NAME } from '../queues/retry-queue';
import type { RetryJobData } from '../queues/retry-queue';
import { getCallQueue } from '../queues/call-queue';
import type { CallJobData } from '../queues/call-queue';
import { CallStateMachine } from '../state-machine/call-state';
import { Campaign } from '../models/domain';

const logger = getLogger();

let retryWorker: Worker<RetryJobData> | null = null;

/**
 * Process a retry job: validate campaign state, reset call status, and re-enqueue.
 */
async function processRetryJob(job: Job<RetryJobData>): Promise<void> {
  const {
    callId,
    campaignId,
    patientId,
    clinicId,
    messageTemplate,
    language,
    attemptNumber,
    maxRetries,
  } = job.data;

  logger.info(
    { callId, campaignId, attemptNumber, maxRetries },
    'Processing retry job',
  );

  // Check if campaign is still active
  const campaign = await Campaign.findById(campaignId);
  if (!campaign || !['running'].includes(campaign.status)) {
    logger.warn(
      { callId, campaignId, status: campaign?.status },
      'Campaign not running, skipping retry',
    );
    await CallStateMachine.transition(callId, 'cancelled').catch(() => {
      // Call might already be in a terminal state
    });
    return;
  }

  // Check attempt limit
  if (attemptNumber > maxRetries) {
    logger.info(
      { callId, attemptNumber, maxRetries },
      'Max retries exceeded, not retrying',
    );
    return;
  }

  // Schedule the call for retry — reset it to pending with incremented attempt
  const scheduledAt = new Date(); // Retry now (delay was handled by BullMQ)

  try {
    await CallStateMachine.scheduleRetry(callId, scheduledAt);
  } catch (err: any) {
    logger.error({ error: err.message, callId }, 'Failed to schedule retry via state machine');
    return;
  }

  // Re-enqueue in the call queue
  const callQueue = getCallQueue();
  const callJobData: CallJobData = {
    callId,
    campaignId,
    patientId,
    clinicId,
    messageTemplate,
    language,
    attemptNumber,
  };

  await callQueue.add(`call-retry-${callId}-${attemptNumber}`, callJobData, {
    jobId: `call-retry-${callId}-${attemptNumber}`,
    priority: 2, // Lower priority than first attempts
  });

  logger.info(
    { callId, campaignId, attemptNumber },
    'Call re-enqueued after retry',
  );
}

/**
 * Start the retry worker.
 */
export function startRetryWorker(): Worker<RetryJobData> {
  if (retryWorker) return retryWorker;

  retryWorker = new Worker<RetryJobData>(RETRY_QUEUE_NAME, processRetryJob, {
    connection: {
      host: config.redis.host,
      port: config.redis.port,
      password: config.redis.password || undefined,
      db: config.redis.db,
    },
    concurrency: 5, // Lower concurrency for retries
  });

  retryWorker.on('completed', (job) => {
    logger.debug({ jobId: job?.id, callId: job?.data.callId }, 'Retry job completed');
  });

  retryWorker.on('failed', (job, err) => {
    logger.error(
      { jobId: job?.id, callId: job?.data.callId, error: err.message },
      'Retry job failed',
    );
  });

  retryWorker.on('error', (err) => {
    logger.error({ error: err.message }, 'Retry worker error');
  });

  logger.info('Retry worker started');
  return retryWorker;
}

/**
 * Stop the retry worker gracefully.
 */
export async function stopRetryWorker(): Promise<void> {
  if (retryWorker) {
    await retryWorker.close();
    retryWorker = null;
    logger.info('Retry worker stopped');
  }
}
