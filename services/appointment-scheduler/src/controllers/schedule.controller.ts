/**
 * Slot controller — handles HTTP requests for slot generation and management.
 */

import { Request, Response, NextFunction } from 'express';
import { successResponse } from '../../../../shared/typescript/src';
import { generateSlots, listSlots } from '../services/slot-generator.service';
import { holdSlot, releaseSlot } from '../services/availability.service';

/**
 * POST /slots/generate
 * Generate slots for a doctor within a date range.
 */
export async function generateSlotsHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { doctorId, startDate, endDate } = req.body;
    const slots = await generateSlots(doctorId, startDate, endDate);
    res.status(201).json(successResponse(slots));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /slots
 * List slots with optional filters.
 */
export async function listSlotsHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { doctorId, date, status, page, limit } = req.query as Record<string, any>;
    const result = await listSlots({
      doctorId,
      date,
      status,
      page: parseInt(page as string, 10) || 1,
      limit: parseInt(limit as string, 10) || 20,
    });
    res.json(successResponse(result.slots, {
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
 * PATCH /slots/:id/hold
 * Temporarily hold a slot.
 */
export async function holdSlotHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const slot = await holdSlot(req.params.id, req.body.heldBy);
    res.json(successResponse(slot));
  } catch (err) {
    next(err);
  }
}

/**
 * PATCH /slots/:id/release
 * Release a held slot.
 */
export async function releaseSlotHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const slot = await releaseSlot(req.params.id);
    res.json(successResponse(slot));
  } catch (err) {
    next(err);
  }
}
