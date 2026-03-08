/**
 * Background job to auto-generate slots for active doctors.
 * Runs daily to ensure slots exist for the configured lookahead period.
 */

import { getLogger } from '../../../../shared/typescript/src';
import { Doctor } from '../models/domain';
import { generateSlots } from '../services/slot-generator.service';
import { getConfig } from '../config';

const logger = getLogger();

let intervalHandle: ReturnType<typeof setInterval> | null = null;

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Start the daily slot generation job.
 */
export function startSlotGenerationJob(): void {
  logger.info('Starting daily slot generation job');

  // Run on start
  runGeneration();

  // Then run every 24 hours
  intervalHandle = setInterval(runGeneration, ONE_DAY_MS);
}

/**
 * Stop the daily slot generation job.
 */
export function stopSlotGenerationJob(): void {
  if (intervalHandle) {
    clearInterval(intervalHandle);
    intervalHandle = null;
    logger.info('Stopped daily slot generation job');
  }
}

async function runGeneration(): Promise<void> {
  try {
    const config = getConfig();
    const lookaheadDays = config.slotGenerationLookaheadDays;

    const doctors = await Doctor.find({ isActive: true }).lean();
    logger.info({ doctorCount: doctors.length, lookaheadDays }, 'Running slot generation');

    const today = new Date();
    today.setUTCHours(0, 0, 0, 0);
    const endDate = new Date(today.getTime() + lookaheadDays * ONE_DAY_MS);

    const startDateStr = today.toISOString().split('T')[0];
    const endDateStr = endDate.toISOString().split('T')[0];

    for (const doctor of doctors) {
      try {
        const slots = await generateSlots(doctor._id.toString(), startDateStr, endDateStr);
        if (slots.length > 0) {
          logger.info({ doctorId: doctor._id.toString(), slotsCreated: slots.length }, 'Slots generated for doctor');
        }
      } catch (err) {
        logger.error({ err, doctorId: doctor._id.toString() }, 'Failed to generate slots for doctor');
      }
    }
  } catch (err) {
    logger.error({ err }, 'Error during slot generation job');
  }
}
