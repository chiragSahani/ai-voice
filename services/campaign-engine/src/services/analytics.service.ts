/**
 * Analytics Service — campaign and clinic-level analytics and reporting.
 */

import { Types } from 'mongoose';
import { getLogger, NotFoundError } from '../../../shared/typescript/src';
import { Campaign, CampaignCall } from '../models/domain';
import type { CampaignAnalyticsResponse, ClinicAnalyticsResponse } from '../models/responses';

const logger = getLogger();

export class AnalyticsService {
  /**
   * Get detailed analytics for a single campaign.
   */
  static async getCampaignAnalytics(campaignId: string): Promise<CampaignAnalyticsResponse> {
    const campaign = await Campaign.findById(campaignId);
    if (!campaign) {
      throw new NotFoundError('Campaign', campaignId);
    }

    const campaignOid = new Types.ObjectId(campaignId);

    // Run aggregations in parallel
    const [statusAgg, outcomeAgg, durationAgg, hourlyAgg] = await Promise.all([
      // Status distribution
      CampaignCall.aggregate([
        { $match: { campaignId: campaignOid } },
        { $group: { _id: '$status', count: { $sum: 1 } } },
      ]),
      // Outcome distribution
      CampaignCall.aggregate([
        { $match: { campaignId: campaignOid, outcome: { $exists: true, $ne: null } } },
        { $group: { _id: '$outcome', count: { $sum: 1 } } },
      ]),
      // Average duration
      CampaignCall.aggregate([
        {
          $match: {
            campaignId: campaignOid,
            status: 'completed',
            durationSeconds: { $exists: true, $ne: null },
          },
        },
        {
          $group: {
            _id: null,
            avgDuration: { $avg: '$durationSeconds' },
            totalDuration: { $sum: '$durationSeconds' },
          },
        },
      ]),
      // Calls per hour of day
      CampaignCall.aggregate([
        {
          $match: {
            campaignId: campaignOid,
            startedAt: { $exists: true, $ne: null },
          },
        },
        {
          $group: {
            _id: { $hour: '$startedAt' },
            count: { $sum: 1 },
          },
        },
        { $sort: { _id: 1 } },
      ]),
    ]);

    // Parse status counts
    let totalCalls = 0;
    let completed = 0;
    let failed = 0;
    let pending = 0;

    for (const item of statusAgg) {
      totalCalls += item.count;
      if (item._id === 'completed') completed = item.count;
      if (item._id === 'failed') failed = item.count;
      if (['pending', 'queued'].includes(item._id)) pending += item.count;
    }

    const answeredRate = totalCalls > 0
      ? Math.round((completed / totalCalls) * 10000) / 100
      : 0;

    // Outcome distribution
    const outcomeDistribution: Record<string, number> = {};
    for (const item of outcomeAgg) {
      outcomeDistribution[item._id] = item.count;
    }

    // Calls per hour
    const callsPerHour: Record<string, number> = {};
    for (const item of hourlyAgg) {
      const hourLabel = `${String(item._id).padStart(2, '0')}:00`;
      callsPerHour[hourLabel] = item.count;
    }

    // Duration stats
    const avgDurationSeconds = durationAgg.length > 0
      ? Math.round(durationAgg[0].avgDuration * 100) / 100
      : 0;

    // Completion rate: completed / (total - pending)
    const processedCalls = totalCalls - pending;
    const completionRate = processedCalls > 0
      ? Math.round((completed / processedCalls) * 10000) / 100
      : 0;

    return {
      campaignId,
      name: campaign.name,
      status: campaign.status,
      stats: {
        totalCalls,
        completed,
        failed,
        pending,
        answeredRate,
        avgDuration: avgDurationSeconds || undefined,
      },
      outcomeDistribution,
      callsPerHour,
      avgDurationSeconds,
      completionRate,
    };
  }

  /**
   * Get aggregate analytics for a clinic across a date range.
   */
  static async getClinicAnalytics(
    clinicId: string,
    dateRange: { from: string; to: string },
  ): Promise<ClinicAnalyticsResponse> {
    const fromDate = new Date(dateRange.from);
    const toDate = new Date(dateRange.to);

    // Get all campaigns for this clinic within date range
    const campaigns = await Campaign.find({
      clinicId,
      createdAt: { $gte: fromDate, $lte: toDate },
    }).lean();

    const campaignIds = campaigns.map((c) => c._id);

    // Aggregate call stats across all campaigns
    const [totalCallsAgg, outcomeAgg, durationAgg] = await Promise.all([
      CampaignCall.aggregate([
        { $match: { campaignId: { $in: campaignIds } } },
        {
          $group: {
            _id: '$status',
            count: { $sum: 1 },
          },
        },
      ]),
      CampaignCall.aggregate([
        {
          $match: {
            campaignId: { $in: campaignIds },
            outcome: { $exists: true, $ne: null },
          },
        },
        { $group: { _id: '$outcome', count: { $sum: 1 } } },
      ]),
      CampaignCall.aggregate([
        {
          $match: {
            campaignId: { $in: campaignIds },
            status: 'completed',
            durationSeconds: { $exists: true, $ne: null },
          },
        },
        { $group: { _id: null, avgDuration: { $avg: '$durationSeconds' } } },
      ]),
    ]);

    let totalCalls = 0;
    let completedCalls = 0;

    for (const item of totalCallsAgg) {
      totalCalls += item.count;
      if (item._id === 'completed') completedCalls = item.count;
    }

    const overallAnsweredRate = totalCalls > 0
      ? Math.round((completedCalls / totalCalls) * 10000) / 100
      : 0;

    const overallAvgDuration = durationAgg.length > 0
      ? Math.round(durationAgg[0].avgDuration * 100) / 100
      : 0;

    const outcomeDistribution: Record<string, number> = {};
    for (const item of outcomeAgg) {
      outcomeDistribution[item._id] = item.count;
    }

    // Per-campaign summaries
    const campaignSummaries = campaigns.map((c) => ({
      campaignId: c._id.toString(),
      name: c.name,
      type: c.type,
      status: c.status,
      totalCalls: c.stats?.totalCalls ?? 0,
      answeredRate: c.stats?.answeredRate ?? 0,
    }));

    return {
      clinicId,
      dateRange: { from: dateRange.from, to: dateRange.to },
      totalCampaigns: campaigns.length,
      totalCalls,
      overallAnsweredRate,
      overallAvgDuration,
      outcomeDistribution,
      campaignSummaries,
    };
  }
}
