/**
 * Request validation middleware for appointment endpoints.
 * Uses Zod schemas for structure validation plus business rule checks.
 */

import { Request, Response, NextFunction } from 'express';
import {
  BookAppointmentSchema,
  CancelAppointmentSchema,
  RescheduleAppointmentSchema,
  CheckAvailabilitySchema,
  ListAppointmentsQuerySchema,
} from '../models/requests';

/**
 * Validate booking request body.
 */
export function validateBooking(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.body = BookAppointmentSchema.parse(req.body);
    next();
  } catch (err) {
    next(err);
  }
}

/**
 * Validate cancellation request body.
 */
export function validateCancel(req: Request, _res: Response, next: NextFunction): void {
  try {
    const data = CancelAppointmentSchema.parse({
      appointmentId: req.params.id,
      reason: req.body.reason,
    });
    req.body = data;
    next();
  } catch (err) {
    next(err);
  }
}

/**
 * Validate reschedule request body.
 */
export function validateReschedule(req: Request, _res: Response, next: NextFunction): void {
  try {
    const data = RescheduleAppointmentSchema.parse({
      appointmentId: req.params.id,
      newSlotId: req.body.newSlotId,
    });
    req.body = data;
    next();
  } catch (err) {
    next(err);
  }
}

/**
 * Validate availability query parameters.
 */
export function validateAvailabilityQuery(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.query = CheckAvailabilitySchema.parse(req.query) as any;
    next();
  } catch (err) {
    next(err);
  }
}

/**
 * Validate list appointments query parameters.
 */
export function validateListAppointments(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.query = ListAppointmentsQuerySchema.parse(req.query) as any;
    next();
  } catch (err) {
    next(err);
  }
}
