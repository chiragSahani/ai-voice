/**
 * Campaign Service — CRUD operations and lifecycle management for campaigns.
 */

import { Types } from 'mongoose';
import {
  getLogger,
  getRedisClient,
  publishEvent,
  STREAM_CAMPAIGNS,
  NotFoundError,
  ConflictError,
  AppError,
} from '../../../shared/typescript/src';
import { Campaign, CampaignCall } from '../models/domain';
import type { ICampaign, CampaignStatus } from '../models/domain';
import { ACTION_TO_STATUS, CAMPAIGN_STATUS_TRANSITIONS } from '../models/domain';
import type { CreateCampaignInput, UpdateCampaignInput, CampaignFilterInput } from '../models/requests';
import type { CampaignStatsResponse } from '../models/responses';
import { CallSchedulerService } from './call-scheduler.service';
import { CallStateMachine } from '../state-machine/call-state';
import { config } from '../config';

const logger = getLogger();

export class CampaignService {
  /**
   * Create a new campaign in draft status.
   */
  static async createCampaign(data: CreateCampaignInput, createdBy: string): Promise<ICampaign> {
    const campaign = new Campaign({
      name: data.name,
      type: data.type,
      clinicId: data.clinicId,
      status: 'draft' as CampaignStatus,
      schedule: {
        startDate: new Date(data.schedule.startDate),
        endDate: data.schedule.endDate ? new Date(data.schedule.endDate) : undefined,
        callWindowStart: data.schedule.callWindowStart,
        callWindowEnd: data.schedule.callWindowEnd,
        timezone: data.schedule.timezone,
        maxConcurrentCalls: data.schedule.maxConcurrentCalls,
      },
      targetPatientIds: data.targetPatientIds.map((id) => new Types.ObjectId(id)),
      messageTemplate: data.messageTemplate,
      language: data.language,
      maxRetries: data.maxRetries,
      retryDelayMinutes: data.retryDelayMinutes,
      createdBy,
      stats: {
        totalCalls: 0,
        completed: 0,
        failed: 0,
        pending: 0,
        answeredRate: 0,
      },
    });

    const saved = await campaign.save();

    logger.info({ campaignId: saved._id.toString(), name: saved.name }, 'Campaign created');
    return saved;
  }

  /**
   * Get a campaign by ID.
   */
  static async getCampaign(id: string): Promise<ICampaign> {
    const campaign = await Campaign.findById(id);
    if (!campaign) {
      throw new NotFoundError('Campaign', id);
    }
    return campaign;
  }

  /**
   * Update a campaign. Only allowed in draft or scheduled status.
   */
  static async updateCampaign(id: string, data: UpdateCampaignInput): Promise<ICampaign> {
    const campaign = await Campaign.findById(id);
    if (!campaign) {
      throw new NotFoundError('Campaign', id);
    }

    if (!['draft', 'scheduled'].includes(campaign.status)) {
      throw new ConflictError(
        `Cannot update campaign in '${campaign.status}' status. Must be draft or scheduled.`,
      );
    }

    const update: Record<string, any> = {};

    if (data.name !== undefined) update.name = data.name;
    if (data.messageTemplate !== undefined) update.messageTemplate = data.messageTemplate;
    if (data.language !== undefined) update.language = data.language;
    if (data.maxRetries !== undefined) update.maxRetries = data.maxRetries;
    if (data.retryDelayMinutes !== undefined) update.retryDelayMinutes = data.retryDelayMinutes;
    if (data.targetPatientIds !== undefined) {
      update.targetPatientIds = data.targetPatientIds.map((pid) => new Types.ObjectId(pid));
    }

    if (data.schedule) {
      const scheduleUpdate: Record<string, any> = {};
      if (data.schedule.startDate) scheduleUpdate['schedule.startDate'] = new Date(data.schedule.startDate);
      if (data.schedule.endDate) scheduleUpdate['schedule.endDate'] = new Date(data.schedule.endDate);
      if (data.schedule.callWindowStart) scheduleUpdate['schedule.callWindowStart'] = data.schedule.callWindowStart;
      if (data.schedule.callWindowEnd) scheduleUpdate['schedule.callWindowEnd'] = data.schedule.callWindowEnd;
      if (data.schedule.timezone) scheduleUpdate['schedule.timezone'] = data.schedule.timezone;
      if (data.schedule.maxConcurrentCalls !== undefined) {
        scheduleUpdate['schedule.maxConcurrentCalls'] = data.schedule.maxConcurrentCalls;
      }
      Object.assign(update, scheduleUpdate);
    }

    const updated = await Campaign.findByIdAndUpdate(id, { $set: update }, { new: true });
    if (!updated) {
      throw new NotFoundError('Campaign', id);
    }

    logger.info({ campaignId: id }, 'Campaign updated');
    return updated;
  }

  /**
   * Start a campaign — transitions to 'running' and enqueues calls.
   */
  static async startCampaign(id: string): Promise<ICampaign> {
    const campaign = await CampaignService.getCampaign(id);
    CampaignService.validateTransition(campaign.status, 'start');

    // Schedule all calls into BullMQ
    const callCount = await CallSchedulerService.scheduleCalls(id);

    const updated = await Campaign.findByIdAndUpdate(
      id,
      {
        $set: {
          status: 'running' as CampaignStatus,
          'stats.totalCalls': callCount,
          'stats.pending': callCount,
        },
      },
      { new: true },
    );

    if (!updated) {
      throw new NotFoundError('Campaign', id);
    }

    // Publish event
    try {
      const redis = getRedisClient({
        host: config.redis.host,
        port: config.redis.port,
        password: config.redis.password || undefined,
      });
      await publishEvent(
        redis,
        STREAM_CAMPAIGNS,
        'campaign.started',
        {
          campaignId: id,
          clinicId: updated.clinicId,
          type: updated.type,
          totalCalls: callCount,
        },
        'campaign-engine',
        id,
      );
    } catch (err: any) {
      logger.error({ error: err.message, campaignId: id }, 'Failed to publish campaign.started event');
    }

    logger.info({ campaignId: id, callCount }, 'Campaign started');
    return updated;
  }

  /**
   * Pause a running campaign.
   */
  static async pauseCampaign(id: string): Promise<ICampaign> {
    const campaign = await CampaignService.getCampaign(id);
    CampaignService.validateTransition(campaign.status, 'pause');

    const updated = await Campaign.findByIdAndUpdate(
      id,
      { $set: { status: 'paused' as CampaignStatus } },
      { new: true },
    );

    if (!updated) {
      throw new NotFoundError('Campaign', id);
    }

    logger.info({ campaignId: id }, 'Campaign paused');
    return updated;
  }

  /**
   * Resume a paused campaign.
   */
  static async resumeCampaign(id: string): Promise<ICampaign> {
    const campaign = await CampaignService.getCampaign(id);
    CampaignService.validateTransition(campaign.status, 'resume');

    const updated = await Campaign.findByIdAndUpdate(
      id,
      { $set: { status: 'running' as CampaignStatus } },
      { new: true },
    );

    if (!updated) {
      throw new NotFoundError('Campaign', id);
    }

    logger.info({ campaignId: id }, 'Campaign resumed');
    return updated;
  }

  /**
   * Cancel a campaign and cancel all pending/queued calls.
   */
  static async cancelCampaign(id: string): Promise<ICampaign> {
    const campaign = await CampaignService.getCampaign(id);
    CampaignService.validateTransition(campaign.status, 'cancel');

    // Cancel all pending/queued calls
    const cancelledCount = await CallStateMachine.cancelAllPending(id);

    const updated = await Campaign.findByIdAndUpdate(
      id,
      {
        $set: { status: 'cancelled' as CampaignStatus },
        $inc: { 'stats.pending': -cancelledCount },
      },
      { new: true },
    );

    if (!updated) {
      throw new NotFoundError('Campaign', id);
    }

    logger.info({ campaignId: id, cancelledCalls: cancelledCount }, 'Campaign cancelled');
    return updated;
  }

  /**
   * List campaigns with filtering and pagination.
   */
  static async listCampaigns(filter: CampaignFilterInput) {
    const query: Record<string, any> = {};
    if (filter.clinicId) query.clinicId = filter.clinicId;
    if (filter.status) query.status = filter.status;
    if (filter.type) query.type = filter.type;

    const sortDir = filter.sortOrder === 'asc' ? 1 : -1;
    const skip = (filter.page - 1) * filter.limit;

    const [items, total] = await Promise.all([
      Campaign.find(query)
        .sort({ [filter.sortBy]: sortDir })
        .skip(skip)
        .limit(filter.limit)
        .lean(),
      Campaign.countDocuments(query),
    ]);

    return {
      items,
      total,
      page: filter.page,
      limit: filter.limit,
      totalPages: Math.ceil(total / filter.limit),
    };
  }

  /**
   * Get campaign statistics by recalculating from calls.
   */
  static async getCampaignStats(id: string): Promise<CampaignStatsResponse> {
    const campaign = await CampaignService.getCampaign(id);

    const [statusCounts, durationAgg] = await Promise.all([
      CampaignCall.aggregate([
        { $match: { campaignId: new Types.ObjectId(id) } },
        { $group: { _id: '$status', count: { $sum: 1 } } },
      ]),
      CampaignCall.aggregate([
        {
          $match: {
            campaignId: new Types.ObjectId(id),
            status: 'completed',
            durationSeconds: { $exists: true, $ne: null },
          },
        },
        { $group: { _id: null, avgDuration: { $avg: '$durationSeconds' } } },
      ]),
    ]);

    let totalCalls = 0;
    let completed = 0;
    let failed = 0;
    let pending = 0;

    for (const item of statusCounts) {
      totalCalls += item.count;
      if (item._id === 'completed') completed = item.count;
      if (item._id === 'failed') failed = item.count;
      if (['pending', 'queued'].includes(item._id)) pending += item.count;
    }

    const answeredRate = totalCalls > 0 ? Math.round((completed / totalCalls) * 10000) / 100 : 0;
    const avgDuration = durationAgg.length > 0
      ? Math.round(durationAgg[0].avgDuration * 100) / 100
      : undefined;

    // Update campaign stats in background
    Campaign.findByIdAndUpdate(id, {
      $set: {
        'stats.totalCalls': totalCalls,
        'stats.completed': completed,
        'stats.failed': failed,
        'stats.pending': pending,
        'stats.answeredRate': answeredRate,
      },
    }).catch((err) => {
      logger.error({ error: err.message, campaignId: id }, 'Failed to update campaign stats');
    });

    return { totalCalls, completed, failed, pending, answeredRate, avgDuration };
  }

  /**
   * Update campaign stats after a call completes (called by workers).
   */
  static async updateStatsAfterCall(
    campaignId: string,
    callStatus: string,
  ): Promise<void> {
    const inc: Record<string, number> = {};

    if (callStatus === 'completed') {
      inc['stats.completed'] = 1;
      inc['stats.pending'] = -1;
    } else if (callStatus === 'failed') {
      inc['stats.failed'] = 1;
      inc['stats.pending'] = -1;
    } else if (['no_answer', 'busy'].includes(callStatus)) {
      inc['stats.failed'] = 1;
      inc['stats.pending'] = -1;
    }

    if (Object.keys(inc).length > 0) {
      await Campaign.findByIdAndUpdate(campaignId, { $inc: inc });
    }

    // Check if all calls are processed
    const pendingCount = await CampaignCall.countDocuments({
      campaignId: new Types.ObjectId(campaignId),
      status: { $in: ['pending', 'queued', 'ringing', 'in_progress'] },
    });

    if (pendingCount === 0) {
      const campaign = await Campaign.findById(campaignId);
      if (campaign && campaign.status === 'running') {
        await Campaign.findByIdAndUpdate(campaignId, {
          $set: { status: 'completed' as CampaignStatus },
        });
        logger.info({ campaignId }, 'Campaign auto-completed (all calls processed)');
      }
    }
  }

  // --- Private helpers ---

  private static validateTransition(currentStatus: string, action: string): void {
    const mapping = ACTION_TO_STATUS[action];
    if (!mapping) {
      throw new AppError(`Unknown action: ${action}`, 'INVALID_ACTION', 400);
    }

    if (!mapping.from.includes(currentStatus)) {
      throw new ConflictError(
        `Cannot '${action}' campaign in '${currentStatus}' status. Allowed from: ${mapping.from.join(', ')}`,
      );
    }
  }
}
