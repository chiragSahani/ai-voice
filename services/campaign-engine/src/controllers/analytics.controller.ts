/**
 * Analytics Controller — Express request handlers for campaign and clinic analytics.
 */

import { Request, Response, NextFunction } from 'express';
import { successResponse, ValidationError } from '../../../shared/typescript/src';
import { AnalyticsService } from '../services/analytics.service';

/**
 * GET /api/v1/campaigns/:id/analytics — Get detailed analytics for a campaign.
 */
export async function getCampaignAnalytics(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const analytics = await AnalyticsService.getCampaignAnalytics(req.params.id);
    res.json(successResponse(analytics));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/analytics/clinic/:clinicId — Get aggregate analytics for a clinic.
 */
export async function getClinicAnalytics(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { clinicId } = req.params;
    const { from, to } = req.query;

    if (!from || !to) {
      throw new ValidationError('Query parameters "from" and "to" are required (ISO date strings)');
    }

    const analytics = await AnalyticsService.getClinicAnalytics(clinicId, {
      from: from as string,
      to: to as string,
    });

    res.json(successResponse(analytics));
  } catch (err) {
    next(err);
  }
}
