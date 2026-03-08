/**
 * Call State Machine — validates and applies state transitions for campaign calls.
 */

import { getLogger } from '../../../shared/typescript/src';
import { CampaignCall, CALL_STATUS_TRANSITIONS } from '../models/domain';
import type { CallStatus, ICampaignCall } from '../models/domain';

const logger = getLogger();

export interface TransitionMetadata {
  outcome?: string;
  sessionId?: string;
  transcript?: string;
  durationSeconds?: number;
  errorMessage?: string;
}

export class CallStateMachine {
  /**
   * Check whether a transition from currentStatus to newStatus is valid.
   */
  static isValidTransition(currentStatus: string, newStatus: string): boolean {
    const allowed = CALL_STATUS_TRANSITIONS[currentStatus];
    if (!allowed) return false;
    return allowed.includes(newStatus);
  }

  /**
   * Transition a call to a new status, recording timestamps and metadata.
   * Throws if the transition is invalid.
   */
  static async transition(
    callId: string,
    newStatus: CallStatus,
    metadata: TransitionMetadata = {},
  ): Promise<ICampaignCall> {
    const call = await CampaignCall.findById(callId);
    if (!call) {
      throw new Error(`CampaignCall not found: ${callId}`);
    }

    const currentStatus = call.status;

    if (!CallStateMachine.isValidTransition(currentStatus, newStatus)) {
      throw new Error(
        `Invalid call state transition: ${currentStatus} -> ${newStatus} for call ${callId}`,
      );
    }

    // Build update payload
    const update: Record<string, any> = {
      status: newStatus,
    };

    // Record timestamps based on target status
    const now = new Date();

    if (newStatus === 'ringing' || newStatus === 'in_progress') {
      if (!call.startedAt) {
        update.startedAt = now;
      }
    }

    if (['completed', 'failed', 'no_answer', 'busy'].includes(newStatus)) {
      update.endedAt = now;

      // Calculate duration if we have a start time
      if (call.startedAt) {
        update.durationSeconds = Math.round((now.getTime() - call.startedAt.getTime()) / 1000);
      }
    }

    // Apply metadata
    if (metadata.outcome) update.outcome = metadata.outcome;
    if (metadata.sessionId) update.sessionId = metadata.sessionId;
    if (metadata.transcript) update.transcript = metadata.transcript;
    if (metadata.durationSeconds !== undefined) update.durationSeconds = metadata.durationSeconds;
    if (metadata.errorMessage) update.errorMessage = metadata.errorMessage;

    const updatedCall = await CampaignCall.findByIdAndUpdate(
      callId,
      { $set: update },
      { new: true },
    );

    if (!updatedCall) {
      throw new Error(`Failed to update call ${callId}`);
    }

    logger.info(
      { callId, from: currentStatus, to: newStatus, campaignId: call.campaignId.toString() },
      'Call state transition',
    );

    return updatedCall;
  }

  /**
   * Batch-cancel all pending/queued calls for a campaign.
   */
  static async cancelAllPending(campaignId: string): Promise<number> {
    const result = await CampaignCall.updateMany(
      {
        campaignId,
        status: { $in: ['pending', 'queued'] },
      },
      {
        $set: { status: 'cancelled', endedAt: new Date() },
      },
    );

    logger.info({ campaignId, count: result.modifiedCount }, 'Cancelled pending calls');
    return result.modifiedCount;
  }

  /**
   * Mark a failed/no_answer/busy call as pending for retry, incrementing attempt number.
   */
  static async scheduleRetry(
    callId: string,
    scheduledAt: Date,
  ): Promise<ICampaignCall> {
    const call = await CampaignCall.findById(callId);
    if (!call) {
      throw new Error(`CampaignCall not found: ${callId}`);
    }

    if (!['failed', 'no_answer', 'busy'].includes(call.status)) {
      throw new Error(
        `Cannot retry call in status ${call.status}. Must be failed, no_answer, or busy.`,
      );
    }

    const updatedCall = await CampaignCall.findByIdAndUpdate(
      callId,
      {
        $set: {
          status: 'pending',
          scheduledAt,
          startedAt: undefined,
          endedAt: undefined,
          durationSeconds: undefined,
          sessionId: undefined,
          transcript: undefined,
          errorMessage: undefined,
        },
        $inc: { attemptNumber: 1 },
      },
      { new: true },
    );

    if (!updatedCall) {
      throw new Error(`Failed to schedule retry for call ${callId}`);
    }

    logger.info(
      { callId, attemptNumber: updatedCall.attemptNumber, scheduledAt: scheduledAt.toISOString() },
      'Call scheduled for retry',
    );

    return updatedCall;
  }
}
