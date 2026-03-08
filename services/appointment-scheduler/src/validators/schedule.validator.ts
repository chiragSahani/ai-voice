/**
 * Request validation middleware for slot/schedule endpoints.
 */

import { Request, Response, NextFunction } from 'express';
import {
  GenerateSlotsSchema,
  HoldSlotSchema,
  ListSlotsQuerySchema,
} from '../models/requests';

/**
 * Validate slot generation request body.
 */
export function validateGenerateSlots(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.body = GenerateSlotsSchema.parse(req.body);
    next();
  } catch (err) {
    next(err);
  }
}

/**
 * Validate hold slot request body.
 */
export function validateHoldSlot(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.body = HoldSlotSchema.parse(req.body);
    next();
  } catch (err) {
    next(err);
  }
}

/**
 * Validate list slots query parameters.
 */
export function validateListSlots(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.query = ListSlotsQuerySchema.parse(req.query) as any;
    next();
  } catch (err) {
    next(err);
  }
}
