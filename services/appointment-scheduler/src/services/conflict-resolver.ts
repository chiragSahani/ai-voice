/**
 * Optimistic concurrency conflict resolver with exponential backoff retry.
 */

import { getLogger, ConflictError } from '../../../../shared/typescript/src';
import { AppointmentSlot, Appointment } from '../models/domain';
import { BookAppointmentInput } from '../models/requests';
import { AppointmentResponse, toAppointmentResponse } from '../models/responses';
import { getConfig } from '../config';

const logger = getLogger();

/**
 * Delay execution by a given number of milliseconds.
 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Attempt to book a slot with optimistic concurrency control.
 *
 * 1. Fetch the slot document (with __v version key).
 * 2. Verify the slot is 'available' or 'held' by the same user.
 * 3. Set status to 'booked' and save — Mongoose checks __v automatically.
 * 4. If VersionError, retry up to maxRetries with exponential backoff.
 * 5. Create the Appointment record on success.
 */
export async function resolveConflict(
  slotId: string,
  bookingData: BookAppointmentInput,
  retryCount: number = 0,
): Promise<AppointmentResponse> {
  const config = getConfig();
  const maxRetries = config.maxBookingRetries;
  const baseDelay = config.retryBaseDelayMs;

  // Step 1: Fetch the slot (live document, not lean)
  const slot = await AppointmentSlot.findById(slotId);
  if (!slot) {
    throw new ConflictError(`Slot ${slotId} not found`);
  }

  // Step 2: Verify status
  if (slot.status === 'booked') {
    throw new ConflictError(`Slot ${slotId} is already booked`);
  }

  if (slot.status === 'cancelled') {
    throw new ConflictError(`Slot ${slotId} has been cancelled`);
  }

  if (slot.status === 'held' && slot.heldBy !== bookingData.bookedBy) {
    // Check if the hold has expired
    if (slot.heldUntil && slot.heldUntil > new Date()) {
      throw new ConflictError(`Slot ${slotId} is held by another user`);
    }
    // Hold expired, proceed with booking
  }

  // Step 3: Attempt to update the slot to 'booked'
  slot.status = 'booked';
  slot.heldBy = undefined;
  slot.heldUntil = undefined;

  try {
    await slot.save(); // Mongoose checks __v for optimistic concurrency
  } catch (err: any) {
    if (err.name === 'VersionError') {
      // Step 4: Retry with exponential backoff
      if (retryCount < maxRetries) {
        const backoffMs = baseDelay * Math.pow(2, retryCount);
        const jitter = Math.random() * baseDelay;
        const waitMs = backoffMs + jitter;

        logger.warn(
          { slotId, retryCount: retryCount + 1, maxRetries, waitMs: Math.round(waitMs) },
          'VersionError on slot booking, retrying with backoff',
        );

        await delay(waitMs);
        return resolveConflict(slotId, bookingData, retryCount + 1);
      }

      logger.error(
        { slotId, retryCount },
        'Max retries exceeded for slot booking',
      );
      throw new ConflictError(
        `Failed to book slot ${slotId} after ${maxRetries} retries due to concurrent modifications`,
      );
    }
    throw err;
  }

  // Step 5: Create the appointment record
  const appointment = await Appointment.create({
    patientId: bookingData.patientId,
    doctorId: slot.doctorId,
    slotId: slot._id,
    clinicId: slot.clinicId,
    date: slot.date,
    startTime: slot.startTime,
    endTime: slot.endTime,
    status: 'scheduled',
    type: bookingData.type,
    reason: bookingData.reason,
    bookedBy: bookingData.bookedBy,
    bookedVia: bookingData.bookedVia,
    sessionId: bookingData.sessionId,
    reminderSent: false,
  });

  logger.info(
    {
      appointmentId: appointment._id.toString(),
      slotId,
      patientId: bookingData.patientId,
      retries: retryCount,
    },
    'Appointment booked successfully',
  );

  return toAppointmentResponse(appointment);
}
