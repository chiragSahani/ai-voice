/**
 * Slot generation service — creates individual slot documents based on doctor schedules.
 */

import { Types } from 'mongoose';
import { getLogger, NotFoundError } from '../../../../shared/typescript/src';
import {
  Doctor,
  AppointmentSlot,
  DoctorOverride,
  DoctorScheduleSlot,
} from '../models/domain';
import { toSlotResponse, SlotResponse } from '../models/responses';

const logger = getLogger();

/**
 * Parse a time string "HH:MM" into total minutes from midnight.
 */
function timeToMinutes(time: string): number {
  const [hours, minutes] = time.split(':').map(Number);
  return hours * 60 + minutes;
}

/**
 * Convert total minutes from midnight back to "HH:MM" format.
 */
function minutesToTime(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

/**
 * Generate appointment slots for a doctor between startDate and endDate.
 *
 * Process:
 *  1. Fetch the doctor and their schedule array.
 *  2. For each date in the range:
 *     a. Check for overrides — skip if override.available === false.
 *     b. Use override times if provided, else use the regular schedule for that day-of-week.
 *     c. Create individual slot documents for each time window (based on slotDurationMinutes).
 *  3. Skip slots that already exist (by doctorId + date + startTime + endTime).
 */
export async function generateSlots(
  doctorId: string,
  startDate: string,
  endDate: string,
): Promise<SlotResponse[]> {
  const doctor = await Doctor.findById(doctorId);
  if (!doctor) {
    throw new NotFoundError('Doctor', doctorId);
  }

  if (!doctor.isActive) {
    throw new Error(`Doctor ${doctorId} is not active`);
  }

  const start = new Date(startDate);
  start.setUTCHours(0, 0, 0, 0);
  const end = new Date(endDate);
  end.setUTCHours(23, 59, 59, 999);

  if (start > end) {
    throw new Error('startDate must be before or equal to endDate');
  }

  const createdSlots: SlotResponse[] = [];
  const current = new Date(start);

  while (current <= end) {
    const dayOfWeek = current.getUTCDay(); // 0=Sun, 6=Sat
    const dateStr = current.toISOString().split('T')[0];

    // Check for overrides on this date
    const override = doctor.overrides?.find((o: DoctorOverride) => {
      const overrideDate = new Date(o.date);
      return overrideDate.toISOString().split('T')[0] === dateStr;
    });

    // If override says unavailable, skip this date
    if (override && !override.available) {
      logger.debug({ doctorId, date: dateStr, reason: override.reason }, 'Skipping date due to override');
      current.setUTCDate(current.getUTCDate() + 1);
      continue;
    }

    // Determine the schedule entries for this day
    let scheduleWindows: Array<{ startTime: string; endTime: string; slotDurationMinutes: number }> = [];

    if (override && override.startTime && override.endTime) {
      // Use override times with default slot duration from first matching schedule entry
      const regularSlot = doctor.schedule.find((s: DoctorScheduleSlot) => s.dayOfWeek === dayOfWeek);
      scheduleWindows.push({
        startTime: override.startTime,
        endTime: override.endTime,
        slotDurationMinutes: regularSlot?.slotDurationMinutes ?? 30,
      });
    } else {
      // Use regular schedule
      const regularSlots = doctor.schedule.filter((s: DoctorScheduleSlot) => s.dayOfWeek === dayOfWeek);
      scheduleWindows = regularSlots.map((s: DoctorScheduleSlot) => ({
        startTime: s.startTime,
        endTime: s.endTime,
        slotDurationMinutes: s.slotDurationMinutes,
      }));
    }

    // Generate individual slots for each schedule window
    for (const window of scheduleWindows) {
      const windowStart = timeToMinutes(window.startTime);
      const windowEnd = timeToMinutes(window.endTime);
      const duration = window.slotDurationMinutes;

      let slotStart = windowStart;
      while (slotStart + duration <= windowEnd) {
        const slotStartTime = minutesToTime(slotStart);
        const slotEndTime = minutesToTime(slotStart + duration);

        // Check if this slot already exists
        const slotDate = new Date(dateStr);
        slotDate.setUTCHours(0, 0, 0, 0);

        const existing = await AppointmentSlot.findOne({
          doctorId: doctor._id,
          date: slotDate,
          startTime: slotStartTime,
          endTime: slotEndTime,
        }).lean();

        if (!existing) {
          const newSlot = await AppointmentSlot.create({
            doctorId: doctor._id,
            clinicId: doctor.clinicId,
            date: slotDate,
            startTime: slotStartTime,
            endTime: slotEndTime,
            status: 'available',
          });

          createdSlots.push(toSlotResponse(newSlot));
        }

        slotStart += duration;
      }
    }

    current.setUTCDate(current.getUTCDate() + 1);
  }

  logger.info(
    { doctorId, startDate, endDate, slotsCreated: createdSlots.length },
    'Slots generated',
  );

  return createdSlots;
}

/**
 * List slots with optional filters and pagination.
 */
export async function listSlots(filters: {
  doctorId?: string;
  date?: string;
  status?: string;
  page: number;
  limit: number;
}): Promise<{ slots: SlotResponse[]; total: number; page: number; limit: number; totalPages: number }> {
  const query: Record<string, unknown> = {};

  if (filters.doctorId) {
    query.doctorId = new Types.ObjectId(filters.doctorId);
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

  const [slots, total] = await Promise.all([
    AppointmentSlot.find(query)
      .sort({ date: 1, startTime: 1 })
      .skip(skip)
      .limit(filters.limit)
      .lean(),
    AppointmentSlot.countDocuments(query),
  ]);

  return {
    slots: slots.map(toSlotResponse),
    total,
    page: filters.page,
    limit: filters.limit,
    totalPages: Math.ceil(total / filters.limit),
  };
}
