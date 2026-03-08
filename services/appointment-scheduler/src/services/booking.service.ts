/**
 * Booking service — book, cancel, and reschedule appointments.
 * Uses optimistic locking via the conflict resolver for concurrent booking safety.
 */

import mongoose from 'mongoose';
import {
  getLogger,
  getRedisClient,
  publishEvent,
  STREAM_APPOINTMENTS,
  ConflictError,
  NotFoundError,
} from '../../../../shared/typescript/src';
import { Appointment, AppointmentSlot } from '../models/domain';
import { BookAppointmentInput } from '../models/requests';
import { AppointmentResponse, toAppointmentResponse } from '../models/responses';
import { resolveConflict } from './conflict-resolver';

const logger = getLogger();

/**
 * Book an appointment for a patient on a specific slot.
 *
 * Flow:
 *  1. Validate slot exists and is available or held by same user
 *  2. Use conflict resolver (optimistic lock with retries) to atomically book
 *  3. Publish appointment.booked event
 */
export async function bookAppointment(data: BookAppointmentInput): Promise<AppointmentResponse> {
  // Delegate to conflict resolver which handles optimistic locking and retries
  const appointment = await resolveConflict(data.slotId, data);

  // Publish event
  try {
    const redis = getRedisClient();
    await publishEvent(
      redis,
      STREAM_APPOINTMENTS,
      'appointment.booked',
      {
        appointmentId: appointment.id,
        patientId: appointment.patientId,
        doctorId: appointment.doctorId,
        slotId: appointment.slotId,
        date: appointment.date,
        startTime: appointment.startTime,
        endTime: appointment.endTime,
        type: appointment.type,
        bookedBy: appointment.bookedBy,
        bookedVia: appointment.bookedVia,
      },
      'appointment-scheduler',
    );
  } catch (err) {
    // Event publishing failure should not fail the booking
    logger.error({ err, appointmentId: appointment.id }, 'Failed to publish appointment.booked event');
  }

  return appointment;
}

/**
 * Cancel an existing appointment.
 *
 * Flow:
 *  1. Find appointment and verify it can be cancelled
 *  2. Update appointment status to 'cancelled'
 *  3. Release the slot back to 'available'
 *  4. Publish appointment.cancelled event
 */
export async function cancelAppointment(
  appointmentId: string,
  reason: string,
): Promise<AppointmentResponse> {
  const appointment = await Appointment.findById(appointmentId);
  if (!appointment) {
    throw new NotFoundError('Appointment', appointmentId);
  }

  if (appointment.status === 'cancelled') {
    throw new ConflictError('Appointment is already cancelled');
  }

  if (appointment.status === 'completed') {
    throw new ConflictError('Cannot cancel a completed appointment');
  }

  // Update appointment
  appointment.status = 'cancelled';
  appointment.cancelledAt = new Date();
  appointment.cancelReason = reason;
  await appointment.save();

  // Release the slot
  try {
    await AppointmentSlot.findByIdAndUpdate(appointment.slotId, {
      $set: { status: 'available' },
      $unset: { heldBy: 1, heldUntil: 1 },
    });
    logger.info({ slotId: appointment.slotId.toString() }, 'Slot released after cancellation');
  } catch (err) {
    logger.error({ err, slotId: appointment.slotId.toString() }, 'Failed to release slot after cancellation');
  }

  // Publish event
  try {
    const redis = getRedisClient();
    await publishEvent(
      redis,
      STREAM_APPOINTMENTS,
      'appointment.cancelled',
      {
        appointmentId: appointment._id.toString(),
        patientId: appointment.patientId.toString(),
        doctorId: appointment.doctorId.toString(),
        slotId: appointment.slotId.toString(),
        reason,
        cancelledAt: appointment.cancelledAt.toISOString(),
      },
      'appointment-scheduler',
    );
  } catch (err) {
    logger.error({ err, appointmentId }, 'Failed to publish appointment.cancelled event');
  }

  return toAppointmentResponse(appointment);
}

/**
 * Reschedule an appointment to a new slot.
 *
 * Flow:
 *  1. Cancel the old appointment (releases old slot)
 *  2. Book a new appointment on the new slot (with optimistic locking)
 *  3. Link the rescheduled appointment
 *  4. Publish appointment.rescheduled event
 *
 * Uses a Mongoose session for transactional safety.
 */
export async function rescheduleAppointment(
  appointmentId: string,
  newSlotId: string,
): Promise<AppointmentResponse> {
  const session = await mongoose.startSession();

  try {
    session.startTransaction();

    // Find the original appointment
    const original = await Appointment.findById(appointmentId).session(session);
    if (!original) {
      throw new NotFoundError('Appointment', appointmentId);
    }

    if (original.status === 'cancelled') {
      throw new ConflictError('Cannot reschedule a cancelled appointment');
    }

    if (original.status === 'completed') {
      throw new ConflictError('Cannot reschedule a completed appointment');
    }

    // Cancel the old appointment
    original.status = 'cancelled';
    original.cancelledAt = new Date();
    original.cancelReason = 'Rescheduled';
    await original.save({ session });

    // Release the old slot
    await AppointmentSlot.findByIdAndUpdate(
      original.slotId,
      {
        $set: { status: 'available' },
        $unset: { heldBy: 1, heldUntil: 1 },
      },
      { session },
    );

    await session.commitTransaction();

    // Book the new slot (outside transaction since it uses optimistic locking with retries)
    const newAppointment = await resolveConflict(newSlotId, {
      patientId: original.patientId.toString(),
      slotId: newSlotId,
      type: original.type,
      reason: original.reason,
      bookedBy: original.bookedBy,
      bookedVia: original.bookedVia as 'voice' | 'web' | 'phone' | 'walk_in',
      sessionId: original.sessionId,
    });

    // Publish rescheduled event
    try {
      const redis = getRedisClient();
      await publishEvent(
        redis,
        STREAM_APPOINTMENTS,
        'appointment.rescheduled',
        {
          oldAppointmentId: appointmentId,
          newAppointmentId: newAppointment.id,
          patientId: newAppointment.patientId,
          oldSlotId: original.slotId.toString(),
          newSlotId: newAppointment.slotId,
          date: newAppointment.date,
          startTime: newAppointment.startTime,
          endTime: newAppointment.endTime,
        },
        'appointment-scheduler',
      );
    } catch (err) {
      logger.error({ err, appointmentId, newAppointmentId: newAppointment.id }, 'Failed to publish appointment.rescheduled event');
    }

    return newAppointment;
  } catch (err) {
    if (session.inTransaction()) {
      await session.abortTransaction();
    }
    throw err;
  } finally {
    session.endSession();
  }
}

/**
 * Get a single appointment by ID.
 */
export async function getAppointment(appointmentId: string): Promise<AppointmentResponse> {
  const appointment = await Appointment.findById(appointmentId).lean();
  if (!appointment) {
    throw new NotFoundError('Appointment', appointmentId);
  }
  return toAppointmentResponse(appointment);
}

/**
 * List appointments with optional filters and pagination.
 */
export async function listAppointments(filters: {
  patientId?: string;
  doctorId?: string;
  date?: string;
  status?: string;
  page: number;
  limit: number;
}): Promise<{ appointments: AppointmentResponse[]; total: number; page: number; limit: number; totalPages: number }> {
  const query: Record<string, unknown> = {};

  if (filters.patientId) {
    query.patientId = new mongoose.Types.ObjectId(filters.patientId);
  }
  if (filters.doctorId) {
    query.doctorId = new mongoose.Types.ObjectId(filters.doctorId);
  }
  if (filters.date) {
    const dateStart = new Date(filters.date);
    dateStart.setUTCHours(0, 0, 0, 0);
    const dateEnd = new Date(filters.date);
    dateEnd.setUTCHours(23, 59, 59, 999);
    query.date = { $gte: dateStart, $lte: dateEnd };
  }
  if (filters.status) {
    query.status = filters.status;
  }

  const skip = (filters.page - 1) * filters.limit;

  const [appointments, total] = await Promise.all([
    Appointment.find(query)
      .sort({ date: -1, startTime: 1 })
      .skip(skip)
      .limit(filters.limit)
      .lean(),
    Appointment.countDocuments(query),
  ]);

  return {
    appointments: appointments.map(toAppointmentResponse),
    total,
    page: filters.page,
    limit: filters.limit,
    totalPages: Math.ceil(total / filters.limit),
  };
}
