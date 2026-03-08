/**
 * Campaign Controller — Express request handlers for campaign CRUD and lifecycle.
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger, successResponse } from '../../../shared/typescript/src';
import { CampaignService } from '../services/campaign.service';
import { CampaignCall } from '../models/domain';
import { toCampaignResponse, toCampaignCallResponse } from '../models/responses';
import {
  validateCreateCampaign,
  validateUpdateCampaign,
  validateCampaignAction,
  validateCampaignFilter,
  validateCallFilter,
} from '../validators';

const logger = getLogger();

/**
 * POST /api/v1/campaigns — Create a new campaign.
 */
export async function createCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const data = validateCreateCampaign(req);
    const createdBy = req.user?.sub || 'system';

    const campaign = await CampaignService.createCampaign(data, createdBy);
    const response = toCampaignResponse(campaign);

    res.status(201).json(successResponse(response));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/campaigns/:id — Get a campaign by ID.
 */
export async function getCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const campaign = await CampaignService.getCampaign(req.params.id);
    const response = toCampaignResponse(campaign);

    res.json(successResponse(response));
  } catch (err) {
    next(err);
  }
}

/**
 * PUT /api/v1/campaigns/:id — Update a campaign.
 */
export async function updateCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const data = validateUpdateCampaign(req);
    const campaign = await CampaignService.updateCampaign(req.params.id, data);
    const response = toCampaignResponse(campaign);

    res.json(successResponse(response));
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/v1/campaigns/:id/action — Execute a campaign action (start, pause, resume, cancel).
 */
export async function campaignAction(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { action } = validateCampaignAction(req);
    const id = req.params.id;

    let campaign;
    switch (action) {
      case 'start':
        campaign = await CampaignService.startCampaign(id);
        break;
      case 'pause':
        campaign = await CampaignService.pauseCampaign(id);
        break;
      case 'resume':
        campaign = await CampaignService.resumeCampaign(id);
        break;
      case 'cancel':
        campaign = await CampaignService.cancelCampaign(id);
        break;
    }

    const response = toCampaignResponse(campaign);
    res.json(successResponse(response));
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/v1/campaigns/:id/start — Start a campaign.
 */
export async function startCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const campaign = await CampaignService.startCampaign(req.params.id);
    res.json(successResponse(toCampaignResponse(campaign)));
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/v1/campaigns/:id/pause — Pause a campaign.
 */
export async function pauseCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const campaign = await CampaignService.pauseCampaign(req.params.id);
    res.json(successResponse(toCampaignResponse(campaign)));
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/v1/campaigns/:id/resume — Resume a campaign.
 */
export async function resumeCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const campaign = await CampaignService.resumeCampaign(req.params.id);
    res.json(successResponse(toCampaignResponse(campaign)));
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/v1/campaigns/:id/cancel — Cancel a campaign.
 */
export async function cancelCampaign(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const campaign = await CampaignService.cancelCampaign(req.params.id);
    res.json(successResponse(toCampaignResponse(campaign)));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/campaigns — List campaigns with filters.
 */
export async function listCampaigns(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const filter = validateCampaignFilter(req);
    const result = await CampaignService.listCampaigns(filter);

    const items = result.items.map(toCampaignResponse);

    res.json(successResponse(items, {
      page: result.page,
      limit: result.limit,
      total: result.total,
      totalPages: result.totalPages,
    }));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/campaigns/:id/stats — Get campaign statistics.
 */
export async function getCampaignStats(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const stats = await CampaignService.getCampaignStats(req.params.id);
    res.json(successResponse(stats));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/campaigns/:id/calls — List calls for a campaign.
 */
export async function listCampaignCalls(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const filter = validateCallFilter(req);
    const campaignId = req.params.id;

    // Verify campaign exists
    await CampaignService.getCampaign(campaignId);

    const query: Record<string, any> = { campaignId };
    if (filter.status) query.status = filter.status;

    const skip = (filter.page - 1) * filter.limit;

    const [calls, total] = await Promise.all([
      CampaignCall.find(query)
        .sort({ scheduledAt: 1 })
        .skip(skip)
        .limit(filter.limit)
        .lean(),
      CampaignCall.countDocuments(query),
    ]);

    const items = calls.map(toCampaignCallResponse);

    res.json(successResponse(items, {
      page: filter.page,
      limit: filter.limit,
      total,
      totalPages: Math.ceil(total / filter.limit),
    }));
  } catch (err) {
    next(err);
  }
}
