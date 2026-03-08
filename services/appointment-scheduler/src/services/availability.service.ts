/**
 * Availability service — slot queries and temporary holds with optimistic locking.
 */

import { Types } from 'mongoose';
import { getLogger } from '../../../../shared/typescript/src';
import { AppointmentSlot, Doctor } from '../models/domain';
import { toSlotResponse, SlotResponse, AvailabilityResponse } from '../models/responses';
import { getConfig } from '../config';
import { ConflictError, NotFoundError } from '../../../../shared/typescript/src';

const logger = getLogger();

/**
 * Check available slots for a specific doctor on a given date, optionally filtered by time range.
 */
export async function checkAvailability(
  doctorId: string,
  date: string,
  timeRange?: { start: string; end: string },
): Promise<AvailabilityResponse> {
  const doctor = await Doctor.findById(doctorId).lean();
  if (!doctor) {
    throw new NotFoundError('Doctor', doctorId);
  }

  const dateStart = new Date(date);
  dateStart.setUTCHours(0, 0, 0, 0);
  const dateEnd = new Date(date);
  dateEnd.setUTCHours(23, 59, 59, 999);

  const query: Record<string, unknown> = {
    doctorId: new Types.ObjectId(doctorId),
    date: { $gte: dateStart, $lte: dateEnd },
    status: 'available',
  };

  if (timeRange) {
    query.startTime = { $gte: timeRange.start };
    query.endTime = { $lte: timeRange.end };
  }

  // Release expired holds before querying
  await releaseExpiredHolds();

  const slots = await AppointmentSlot.find(query).sort({ startTime: 1 }).lean();

  return {
    slots: slots.map(toSlotResponse),
    doctor: {
      id: doctor._id.toString(),
      name: doctor.name,
      specialization: doctor.specialization,
    },
    date,
    totalAvailable: slots.length,
  };
}

/**
 * Get available slots grouped by doctor for a given specialization and date.
 */
export async function getAvailableSlotsBySpecialization(
  specialization: string,
  date: string,
  clinicId?: string,
): Promise<AvailabilityResponse[]> {
  const doctorQuery: Record<string, unknown> = {
    specialization,
    isActive: true,
  };
  if (clinicId) {
    doctorQuery.clinicId = clinicId;
  }

  const doctors = await Doctor.find(doctorQuery).lean();

  if (doctors.length === 0) {
    return [];
  }

  await releaseExpiredHolds();

  const dateStart = new Date(date);
  dateStart.setUTCHours(0, 0, 0, 0);
  const dateEnd = new Date(date);
  dateEnd.setUTCHours(23, 59, 59, 999);

  const results: AvailabilityResponse[] = [];

  for (const doctor of doctors) {
    const slots = await AppointmentSlot.find({
      doctorId: doctor._id,
      date: { $gte: dateStart, $lte: dateEnd },
      status: 'available',
    })
      .sort({ startTime: 1 })
      .lean();

    if (slots.length > 0) {
      results.push({
        slots: slots.map(toSlotResponse),
        doctor: {
          id: doctor._id.toString(),
          name: doctor.name,
          specialization: doctor.specialization,
        },
        date,
        totalAvailable: slots.length,
      });
    }
  }

  return results;
}

/**
 * Check if a specific slot is available (status = 'available').
 */
export async function isSlotAvailable(slotId: string): Promise<boolean> {
  await releaseExpiredHolds();

  const slot = await AppointmentSlot.findById(slotId).lean();
  if (!slot) return false;

  return slot.status === 'available';
}

/**
 * Temporarily hold a slot with optimistic locking.
 * Sets status='held', heldBy, and heldUntil=now + holdDurationMinutes.
 * Uses Mongoose __v for optimistic concurrency control.
 */
export async function holdSlot(slotId: string, heldBy: string): Promise<SlotResponse> {
  const config = getConfig();

  // Fetch the live document (not lean) so we can use .save() with __v
  const slot = await AppointmentSlot.findById(slotId);
  if (!slot) {
    throw new NotFoundError('Slot', slotId);
  }

  if (slot.status !== 'available') {
    // If it's held and expired, we can take it
    if (slot.status === 'held' && slot.heldUntil && slot.heldUntil < new Date()) {
      // Expired hold, proceed to re-hold
    } else {
      throw new ConflictError(`Slot ${slotId} is not available (current status: ${slot.status})`);
    }
  }

  slot.status = 'held';
  slot.heldBy = heldBy;
  slot.heldUntil = new Date(Date.now() + config.slotHoldDurationMinutes * 60 * 1000);

  try {
    const saved = await slot.save();
    logger.info({ slotId, heldBy, heldUntil: slot.heldUntil }, 'Slot held');
    return toSlotResponse(saved);
  } catch (err: any) {
    if (err.name === 'VersionError') {
      throw new ConflictError('Slot was modified by another request. Please try again.');
    }
    throw err;
  }
}

/**
 * Release a held slot back to available status with optimistic locking.
 */
export async function releaseSlot(slotId: string): Promise<SlotResponse> {
  const slot = await AppointmentSlot.findById(slotId);
  if (!slot) {
    throw new NotFoundError('Slot', slotId);
  }

  if (slot.status !== 'held') {
    throw new ConflictError(`Slot ${slotId} is not held (current status: ${slot.status})`);
  }

  slot.status = 'available';
  slot.heldBy = undefined;
  slot.heldUntil = undefined;

  try {
    const saved = await slot.save();
    logger.info({ slotId }, 'Slot released');
    return toSlotResponse(saved);
  } catch (err: any) {
    if (err.name === 'VersionError') {
      throw new ConflictError('Slot was modified by another request. Please try again.');
    }
    throw err;
  }
}

/**
 * Release all slots whose hold has expired (heldUntil < now).
 */
async function releaseExpiredHolds(): Promise<number> {
  const result = await AppointmentSlot.updateMany(
    {
      status: 'held',
      heldUntil: { $lt: new Date() },
    },
    {
      $set: { status: 'available' },
      $unset: { heldBy: 1, heldUntil: 1 },
    },
  );

  if (result.modifiedCount > 0) {
    logger.info({ count: result.modifiedCount }, 'Expired slot holds released');
  }

  return result.modifiedCount;
}

export { releaseExpiredHolds };
