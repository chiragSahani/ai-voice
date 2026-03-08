/**
 * Campaign validators — Zod parsing + business rule validation.
 */

import { Request } from 'express';
import { ValidationError } from '../../../shared/typescript/src';
import {
  CreateCampaignSchema,
  UpdateCampaignSchema,
  CampaignActionSchema,
  CampaignFilterSchema,
  CallFilterSchema,
} from '../models/requests';
import type {
  CreateCampaignInput,
  UpdateCampaignInput,
  CampaignActionInput,
  CampaignFilterInput,
  CallFilterInput,
} from '../models/requests';
import { ACTION_TO_STATUS } from '../models/domain';

/**
 * Validate and parse create campaign request body.
 */
export function validateCreateCampaign(req: Request): CreateCampaignInput {
  const parsed = CreateCampaignSchema.parse(req.body);

  // Business rule: startDate must be in the future
  const startDate = new Date(parsed.schedule.startDate);
  if (startDate < new Date()) {
    throw new ValidationError('schedule.startDate must be in the future');
  }

  // Business rule: endDate must be after startDate
  if (parsed.schedule.endDate) {
    const endDate = new Date(parsed.schedule.endDate);
    if (endDate <= startDate) {
      throw new ValidationError('schedule.endDate must be after schedule.startDate');
    }
  }

  // Business rule: call window validation
  validateScheduleWindow(parsed.schedule.callWindowStart, parsed.schedule.callWindowEnd);

  return parsed;
}

/**
 * Validate and parse update campaign request body.
 */
export function validateUpdateCampaign(req: Request): UpdateCampaignInput {
  const parsed = UpdateCampaignSchema.parse(req.body);

  // Validate schedule window if both start and end are provided
  if (parsed.schedule?.callWindowStart && parsed.schedule?.callWindowEnd) {
    validateScheduleWindow(parsed.schedule.callWindowStart, parsed.schedule.callWindowEnd);
  }

  // Validate date ordering if both are provided
  if (parsed.schedule?.startDate && parsed.schedule?.endDate) {
    const start = new Date(parsed.schedule.startDate);
    const end = new Date(parsed.schedule.endDate);
    if (end <= start) {
      throw new ValidationError('schedule.endDate must be after schedule.startDate');
    }
  }

  return parsed;
}

/**
 * Validate campaign action request body.
 */
export function validateCampaignAction(req: Request): CampaignActionInput {
  const parsed = CampaignActionSchema.parse(req.body);

  // Verify the action is known
  if (!ACTION_TO_STATUS[parsed.action]) {
    throw new ValidationError(`Unknown campaign action: ${parsed.action}`);
  }

  return parsed;
}

/**
 * Validate campaign list/filter query parameters.
 */
export function validateCampaignFilter(req: Request): CampaignFilterInput {
  return CampaignFilterSchema.parse(req.query);
}

/**
 * Validate call list/filter query parameters.
 */
export function validateCallFilter(req: Request): CallFilterInput {
  return CallFilterSchema.parse(req.query);
}

/**
 * Validate that the call window start is before end.
 */
function validateScheduleWindow(start: string, end: string): void {
  const [startH, startM] = start.split(':').map(Number);
  const [endH, endM] = end.split(':').map(Number);

  const startMinutes = startH * 60 + startM;
  const endMinutes = endH * 60 + endM;

  if (endMinutes <= startMinutes) {
    throw new ValidationError(
      `callWindowEnd (${end}) must be after callWindowStart (${start})`,
    );
  }

  // Minimum 1 hour window
  if (endMinutes - startMinutes < 60) {
    throw new ValidationError('Call window must be at least 1 hour');
  }
}
