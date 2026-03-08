/**
 * Background job to release expired slot holds and mark past slots as unavailable.
 */

import { getLogger } from '../../../../shared/typescript/src';
import { releaseExpiredHolds } from '../services/availability.service';
import { getConfig } from '../config';

const logger = getLogger();

let intervalHandle: ReturnType<typeof setInterval> | null = null;

/**
 * Start the periodic expired slot cleanup job.
 */
export function startExpiredSlotCleanup(): void {
  const config = getConfig();
  const intervalMs = config.expiredSlotCleanupIntervalMs;

  logger.info({ intervalMs }, 'Starting expired slot cleanup job');

  // Run immediately on start
  runCleanup();

  // Then run periodically
  intervalHandle = setInterval(runCleanup, intervalMs);
}

/**
 * Stop the periodic expired slot cleanup job.
 */
export function stopExpiredSlotCleanup(): void {
  if (intervalHandle) {
    clearInterval(intervalHandle);
    intervalHandle = null;
    logger.info('Stopped expired slot cleanup job');
  }
}

async function runCleanup(): Promise<void> {
  try {
    const released = await releaseExpiredHolds();
    if (released > 0) {
      logger.info({ released }, 'Expired slot holds cleaned up');
    }
  } catch (err) {
    logger.error({ err }, 'Error during expired slot cleanup');
  }
}
