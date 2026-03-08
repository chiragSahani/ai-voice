/**
 * Call Scheduler Service — creates CampaignCall documents and enqueues BullMQ jobs.
 * Respects call windows (e.g., 9am–6pm) and distributes calls evenly within the window.
 */

import { Types } from 'mongoose';
import { DateTime } from 'luxon';
import { getLogger } from '../../../shared/typescript/src';
import { Campaign, CampaignCall } from '../models/domain';
import type { ICampaign } from '../models/domain';
import { getCallQueue } from '../queues/call-queue';
import type { CallJobData } from '../queues/call-queue';

const logger = getLogger();

export class CallSchedulerService {
  /**
   * Schedule calls for all target patients of a campaign.
   * Creates CampaignCall documents and enqueues BullMQ jobs.
   * Returns the number of calls queued.
   */
  static async scheduleCalls(campaignId: string): Promise<number> {
    const campaign = await Campaign.findById(campaignId);
    if (!campaign) {
      throw new Error(`Campaign not found: ${campaignId}`);
    }

    const { targetPatientIds, schedule, clinicId, messageTemplate, language } = campaign;

    if (!targetPatientIds || targetPatientIds.length === 0) {
      logger.warn({ campaignId }, 'No target patients to schedule');
      return 0;
    }

    // Calculate scheduled times distributed within the call window
    const scheduledTimes = CallSchedulerService.distributeCallTimes(
      targetPatientIds.length,
      schedule,
    );

    const callQueue = getCallQueue();
    let queuedCount = 0;

    // Batch create CampaignCall documents
    const callDocs = targetPatientIds.map((patientId, index) => ({
      campaignId: new Types.ObjectId(campaignId),
      patientId,
      clinicId,
      status: 'queued' as const,
      attemptNumber: 1,
      scheduledAt: scheduledTimes[index],
    }));

    const insertedCalls = await CampaignCall.insertMany(callDocs);

    // Enqueue jobs into BullMQ
    const jobs = insertedCalls.map((call, index) => {
      const delay = Math.max(0, scheduledTimes[index].getTime() - Date.now());

      const jobData: CallJobData = {
        callId: call._id.toString(),
        campaignId,
        patientId: call.patientId.toString(),
        clinicId,
        messageTemplate,
        language,
        attemptNumber: 1,
      };

      return {
        name: `call-${call._id.toString()}`,
        data: jobData,
        opts: {
          delay,
          jobId: call._id.toString(),
          priority: 1,
        },
      };
    });

    // Add jobs in bulk for performance
    await callQueue.addBulk(jobs);
    queuedCount = jobs.length;

    logger.info(
      { campaignId, queuedCount, firstCall: scheduledTimes[0]?.toISOString() },
      'Calls scheduled',
    );

    return queuedCount;
  }

  /**
   * Distribute call times evenly within the campaign's call window.
   * If the start date is in the past, uses the current time as start.
   * Respects the daily call window hours in the campaign's timezone.
   */
  static distributeCallTimes(
    count: number,
    schedule: ICampaign['schedule'],
  ): Date[] {
    const tz = schedule.timezone || 'Asia/Kolkata';
    const windowStart = schedule.callWindowStart || '09:00';
    const windowEnd = schedule.callWindowEnd || '18:00';

    const [startHour, startMin] = windowStart.split(':').map(Number);
    const [endHour, endMin] = windowEnd.split(':').map(Number);

    // Window duration in minutes
    const windowDurationMinutes = (endHour * 60 + endMin) - (startHour * 60 + startMin);

    if (windowDurationMinutes <= 0) {
      throw new Error('callWindowEnd must be after callWindowStart');
    }

    const now = DateTime.now().setZone(tz);
    let campaignStart = DateTime.fromJSDate(schedule.startDate).setZone(tz);

    // If campaign start is in the past, use now
    if (campaignStart < now) {
      campaignStart = now;
    }

    const scheduledTimes: Date[] = [];
    let currentDay = campaignStart.startOf('day');
    let remaining = count;

    // Max calls per day based on window and reasonable pacing (1 call per minute minimum)
    const maxCallsPerDay = windowDurationMinutes;

    while (remaining > 0) {
      const callsToday = Math.min(remaining, maxCallsPerDay);
      const intervalMinutes = callsToday > 1
        ? windowDurationMinutes / callsToday
        : 0;

      for (let i = 0; i < callsToday; i++) {
        let callTime = currentDay.set({
          hour: startHour,
          minute: startMin,
          second: 0,
          millisecond: 0,
        }).plus({ minutes: Math.round(intervalMinutes * i) });

        // Skip times in the past
        if (callTime < now) {
          // Push to next available minute after now
          callTime = now.plus({ minutes: i + 1 });

          // If pushed beyond today's window, stop for today
          const todayEnd = currentDay.set({
            hour: endHour,
            minute: endMin,
            second: 0,
            millisecond: 0,
          });

          if (callTime > todayEnd) {
            remaining -= i;
            break;
          }
        }

        scheduledTimes.push(callTime.toJSDate());
        remaining--;

        if (remaining <= 0) break;
      }

      // Move to next day
      currentDay = currentDay.plus({ days: 1 });

      // Respect campaign endDate
      if (schedule.endDate) {
        const endDate = DateTime.fromJSDate(schedule.endDate).setZone(tz);
        if (currentDay > endDate) {
          logger.warn(
            { campaignEnd: schedule.endDate, unscheduled: remaining },
            'Campaign end date reached before all calls could be scheduled',
          );
          break;
        }
      }

      // Safety: prevent infinite loop
      if (scheduledTimes.length >= count) break;
    }

    return scheduledTimes;
  }
}
