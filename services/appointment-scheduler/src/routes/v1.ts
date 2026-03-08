/**
 * API v1 routes for the Appointment Scheduler service.
 * All routes are prefixed with /api/v1.
 */

import { Router } from 'express';
import {
  getAvailability,
  createAppointment,
  getAppointmentById,
  listAppointmentsHandler,
  cancelAppointmentHandler,
  rescheduleAppointmentHandler,
} from '../controllers/appointment.controller';
import {
  generateSlotsHandler,
  listSlotsHandler,
  holdSlotHandler,
  releaseSlotHandler,
} from '../controllers/schedule.controller';
import { getDoctorById } from '../controllers/doctor.controller';
import {
  validateBooking,
  validateCancel,
  validateReschedule,
  validateAvailabilityQuery,
  validateListAppointments,
} from '../validators/appointment.validator';
import {
  validateGenerateSlots,
  validateHoldSlot,
  validateListSlots,
} from '../validators/schedule.validator';
import { validateDoctorId } from '../validators/doctor.validator';

export function createV1Router(): Router {
  const router = Router();

  // --- Availability ---
  router.get('/availability', validateAvailabilityQuery, getAvailability);

  // --- Appointments ---
  router.post('/appointments', validateBooking, createAppointment);
  router.get('/appointments', validateListAppointments, listAppointmentsHandler);
  router.get('/appointments/:id', getAppointmentById);
  router.delete('/appointments/:id', validateCancel, cancelAppointmentHandler);
  router.put('/appointments/:id/reschedule', validateReschedule, rescheduleAppointmentHandler);

  // --- Slots ---
  router.post('/slots/generate', validateGenerateSlots, generateSlotsHandler);
  router.get('/slots', validateListSlots, listSlotsHandler);
  router.patch('/slots/:id/hold', validateHoldSlot, holdSlotHandler);
  router.patch('/slots/:id/release', releaseSlotHandler);

  // --- Doctors ---
  router.get('/doctors/:id', validateDoctorId, getDoctorById);

  return router;
}
