/**
 * BullMQ Worker — processes outbound call jobs.
 * For each call:
 *   1. Update status to 'ringing'
 *   2. Initiate outbound call via audio-gateway WebSocket
 *   3. Monitor call progress
 *   4. Update status based on outcome
 *   5. Record transcript and duration
 * On failure: enqueue retry if attempts < maxRetries.
 */

import { Worker, Job } from 'bullmq';
import WebSocket from 'ws';
import { v4 as uuidv4 } from 'uuid';
import {
  getLogger,
  getRedisClient,
  publishEvent,
  STREAM_CAMPAIGNS,
} from '../../../shared/typescript/src';
import { config } from '../config';
import { CALL_QUEUE_NAME } from '../queues/call-queue';
import type { CallJobData } from '../queues/call-queue';
import { getRetryQueue, calculateBackoffDelay } from '../queues/retry-queue';
import type { RetryJobData } from '../queues/retry-queue';
import { CallStateMachine } from '../state-machine/call-state';
import { CampaignService } from '../services/campaign.service';
import { Campaign, CampaignCall } from '../models/domain';
import type { CallStatus, CallOutcome } from '../models/domain';

const logger = getLogger();

let callWorker: Worker<CallJobData> | null = null;

/**
 * Process a single call job.
 */
async function processCallJob(job: Job<CallJobData>): Promise<void> {
  const { callId, campaignId, patientId, clinicId, messageTemplate, language, attemptNumber } = job.data;

  logger.info({ callId, campaignId, patientId, attemptNumber }, 'Processing call job');

  // Check campaign is still active
  const campaign = await Campaign.findById(campaignId);
  if (!campaign || !['running'].includes(campaign.status)) {
    logger.warn({ callId, campaignId, status: campaign?.status }, 'Campaign not running, skipping call');
    await CallStateMachine.transition(callId, 'cancelled');
    return;
  }

  // Transition to ringing
  await CallStateMachine.transition(callId, 'ringing');

  try {
    // Initiate outbound call via audio-gateway WebSocket
    const callResult = await initiateOutboundCall({
      callId,
      campaignId,
      patientId,
      clinicId,
      messageTemplate,
      language,
    });

    // Process result
    if (callResult.connected) {
      // Transition to in_progress
      await CallStateMachine.transition(callId, 'in_progress', {
        sessionId: callResult.sessionId,
      });

      // Wait for call completion (the WebSocket handler manages this)
      // Transition to completed
      await CallStateMachine.transition(callId, 'completed', {
        outcome: callResult.outcome as CallOutcome,
        transcript: callResult.transcript,
        durationSeconds: callResult.durationSeconds,
        sessionId: callResult.sessionId,
      });

      // Update campaign stats
      await CampaignService.updateStatsAfterCall(campaignId, 'completed');

      // Publish completion event
      try {
        const redis = getRedisClient({
          host: config.redis.host,
          port: config.redis.port,
          password: config.redis.password || undefined,
        });
        await publishEvent(
          redis,
          STREAM_CAMPAIGNS,
          'campaign.call.completed',
          {
            campaignId,
            callId,
            patientId,
            outcome: callResult.outcome,
            durationSeconds: callResult.durationSeconds,
          },
          'campaign-engine',
          campaignId,
        );
      } catch (err: any) {
        logger.error({ error: err.message }, 'Failed to publish call completed event');
      }
    } else {
      // Call not connected — no_answer or busy
      const failStatus: CallStatus = callResult.reason === 'busy' ? 'busy' : 'no_answer';

      await CallStateMachine.transition(callId, failStatus, {
        errorMessage: callResult.reason,
      });

      await CampaignService.updateStatsAfterCall(campaignId, failStatus);

      // Schedule retry if applicable
      await scheduleRetryIfNeeded(job.data, campaign.maxRetries, campaign.retryDelayMinutes);
    }
  } catch (err: any) {
    logger.error({ error: err.message, callId, campaignId }, 'Call processing failed');

    try {
      await CallStateMachine.transition(callId, 'failed', {
        errorMessage: err.message,
      });
    } catch (transitionErr: any) {
      logger.error(
        { error: transitionErr.message, callId },
        'Failed to transition call to failed status',
      );
    }

    await CampaignService.updateStatsAfterCall(campaignId, 'failed');

    // Schedule retry
    const campaign2 = await Campaign.findById(campaignId);
    if (campaign2) {
      await scheduleRetryIfNeeded(job.data, campaign2.maxRetries, campaign2.retryDelayMinutes);
    }
  }
}

/**
 * Initiate an outbound call via the audio-gateway WebSocket.
 */
interface OutboundCallResult {
  connected: boolean;
  sessionId: string;
  outcome: string;
  transcript?: string;
  durationSeconds: number;
  reason?: string;
}

async function initiateOutboundCall(params: {
  callId: string;
  campaignId: string;
  patientId: string;
  clinicId: string;
  messageTemplate: string;
  language: string;
}): Promise<OutboundCallResult> {
  const sessionId = uuidv4();
  const wsUrl = config.audioGatewayWsUrl;

  return new Promise<OutboundCallResult>((resolve, reject) => {
    const timeout = setTimeout(() => {
      ws.close();
      resolve({
        connected: false,
        sessionId,
        outcome: 'no_response',
        durationSeconds: 0,
        reason: 'timeout',
      });
    }, config.bullmq.defaultJobTimeout);

    let ws: WebSocket;

    try {
      ws = new WebSocket(wsUrl, {
        headers: {
          'x-session-id': sessionId,
          'x-campaign-id': params.campaignId,
          'x-call-id': params.callId,
        },
      });
    } catch (err: any) {
      clearTimeout(timeout);
      reject(new Error(`Failed to connect to audio gateway: ${err.message}`));
      return;
    }

    const startTime = Date.now();
    let transcript = '';
    let outcome = 'no_response';
    let connected = false;

    ws.on('open', () => {
      logger.info({ callId: params.callId, sessionId }, 'WebSocket connected to audio gateway');

      // Send outbound call initiation message
      ws.send(JSON.stringify({
        type: 'outbound_call',
        session_id: sessionId,
        patient_id: params.patientId,
        clinic_id: params.clinicId,
        campaign_id: params.campaignId,
        call_id: params.callId,
        message_template: params.messageTemplate,
        language: params.language,
      }));
    });

    ws.on('message', (data: WebSocket.Data) => {
      try {
        const msg = JSON.parse(data.toString());

        switch (msg.type) {
          case 'call_connected':
            connected = true;
            logger.info({ callId: params.callId }, 'Call connected');
            break;

          case 'call_busy':
            clearTimeout(timeout);
            ws.close();
            resolve({
              connected: false,
              sessionId,
              outcome: 'no_response',
              durationSeconds: 0,
              reason: 'busy',
            });
            break;

          case 'call_no_answer':
            clearTimeout(timeout);
            ws.close();
            resolve({
              connected: false,
              sessionId,
              outcome: 'no_response',
              durationSeconds: 0,
              reason: 'no_answer',
            });
            break;

          case 'transcript_update':
            if (msg.text) {
              transcript += (transcript ? '\n' : '') + msg.text;
            }
            break;

          case 'call_outcome':
            outcome = msg.outcome || 'no_response';
            break;

          case 'call_ended':
            clearTimeout(timeout);
            const durationSeconds = Math.round((Date.now() - startTime) / 1000);
            ws.close();
            resolve({
              connected: true,
              sessionId,
              outcome: msg.outcome || outcome,
              transcript: transcript || msg.transcript,
              durationSeconds: msg.duration_seconds || durationSeconds,
            });
            break;

          default:
            logger.debug({ type: msg.type, callId: params.callId }, 'Unhandled WS message');
        }
      } catch (err: any) {
        logger.error({ error: err.message }, 'Failed to parse WS message');
      }
    });

    ws.on('error', (err) => {
      clearTimeout(timeout);
      logger.error({ error: err.message, callId: params.callId }, 'WebSocket error');
      reject(new Error(`WebSocket error: ${err.message}`));
    });

    ws.on('close', (code) => {
      clearTimeout(timeout);
      if (!connected) {
        resolve({
          connected: false,
          sessionId,
          outcome: 'no_response',
          durationSeconds: 0,
          reason: `ws_closed_${code}`,
        });
      }
    });
  });
}

/**
 * Schedule a retry via the retry queue if attempts are not exhausted.
 */
async function scheduleRetryIfNeeded(
  jobData: CallJobData,
  maxRetries: number,
  retryDelayMinutes: number,
): Promise<void> {
  if (jobData.attemptNumber >= maxRetries) {
    logger.info(
      { callId: jobData.callId, attempts: jobData.attemptNumber, maxRetries },
      'Max retries reached, not scheduling retry',
    );
    return;
  }

  const delay = calculateBackoffDelay(jobData.attemptNumber, retryDelayMinutes);

  const retryData: RetryJobData = {
    callId: jobData.callId,
    campaignId: jobData.campaignId,
    patientId: jobData.patientId,
    clinicId: jobData.clinicId,
    messageTemplate: jobData.messageTemplate,
    language: jobData.language,
    attemptNumber: jobData.attemptNumber + 1,
    maxRetries,
    retryDelayMinutes,
  };

  const retryQueue = getRetryQueue();
  await retryQueue.add(`retry-${jobData.callId}-${jobData.attemptNumber + 1}`, retryData, {
    delay,
    jobId: `retry-${jobData.callId}-${jobData.attemptNumber + 1}`,
  });

  logger.info(
    { callId: jobData.callId, nextAttempt: jobData.attemptNumber + 1, delayMs: delay },
    'Retry scheduled',
  );
}

/**
 * Start the call worker.
 */
export function startCallWorker(): Worker<CallJobData> {
  if (callWorker) return callWorker;

  callWorker = new Worker<CallJobData>(CALL_QUEUE_NAME, processCallJob, {
    connection: {
      host: config.redis.host,
      port: config.redis.port,
      password: config.redis.password || undefined,
      db: config.redis.db,
    },
    concurrency: config.maxConcurrentCalls,
    limiter: {
      max: config.maxConcurrentCalls,
      duration: 1000,
    },
  });

  callWorker.on('completed', (job) => {
    logger.debug({ jobId: job?.id, callId: job?.data.callId }, 'Call job completed');
  });

  callWorker.on('failed', (job, err) => {
    logger.error(
      { jobId: job?.id, callId: job?.data.callId, error: err.message },
      'Call job failed',
    );
  });

  callWorker.on('error', (err) => {
    logger.error({ error: err.message }, 'Call worker error');
  });

  logger.info({ concurrency: config.maxConcurrentCalls }, 'Call worker started');
  return callWorker;
}

/**
 * Stop the call worker gracefully.
 */
export async function stopCallWorker(): Promise<void> {
  if (callWorker) {
    await callWorker.close();
    callWorker = null;
    logger.info('Call worker stopped');
  }
}
