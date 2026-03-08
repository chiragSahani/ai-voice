/**
 * Appointment controller — handles HTTP requests for appointment CRUD operations.
 */

import { Request, Response, NextFunction } from 'express';
import { successResponse } from '../../../../shared/typescript/src';
import {
  bookAppointment,
  cancelAppointment,
  rescheduleAppointment,
  getAppointment,
  listAppointments,
} from '../services/booking.service';
import {
  checkAvailability,
  getAvailableSlotsBySpecialization,
} from '../services/availability.service';

/**
 * GET /availability
 * Check available slots by doctor or specialization.
 */
export async function getAvailability(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { doctorId, specialization, date, timeRange, clinicId } = req.query as Record<string, any>;

    if (doctorId) {
      const result = await checkAvailability(
        doctorId as string,
        date as string,
        timeRange ? JSON.parse(timeRange as string) : undefined,
      );
      res.json(successResponse(result));
    } else if (specialization) {
      const results = await getAvailableSlotsBySpecialization(
        specialization as string,
        date as string,
        clinicId as string | undefined,
      );
      res.json(successResponse(results));
    } else {
      res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: 'Either doctorId or specialization is required' },
      });
    }
  } catch (err) {
    next(err);
  }
}

/**
 * POST /appointments
 * Book a new appointment.
 */
export async function createAppointment(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const appointment = await bookAppointment(req.body);
    res.status(201).json(successResponse(appointment));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /appointments/:id
 * Get a single appointment by ID.
 */
export async function getAppointmentById(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const appointment = await getAppointment(req.params.id);
    res.json(successResponse(appointment));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /appointments
 * List appointments with optional filters.
 */
export async function listAppointmentsHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { patientId, doctorId, date, status, page, limit } = req.query as Record<string, any>;
    const result = await listAppointments({
      patientId,
      doctorId,
      date,
      status,
      page: parseInt(page as string, 10) || 1,
      limit: parseInt(limit as string, 10) || 20,
    });
    res.json(successResponse(result.appointments, {
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
 * DELETE /appointments/:id
 * Cancel an appointment.
 */
export async function cancelAppointmentHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const appointment = await cancelAppointment(req.body.appointmentId, req.body.reason);
    res.json(successResponse(appointment));
  } catch (err) {
    next(err);
  }
}

/**
 * PUT /appointments/:id/reschedule
 * Reschedule an appointment to a new slot.
 */
export async function rescheduleAppointmentHandler(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const appointment = await rescheduleAppointment(req.body.appointmentId, req.body.newSlotId);
    res.json(successResponse(appointment));
  } catch (err) {
    next(err);
  }
}
