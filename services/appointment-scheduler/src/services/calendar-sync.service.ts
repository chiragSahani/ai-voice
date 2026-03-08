/**
 * Calendar sync service — placeholder for external calendar integration.
 * Future: sync with Google Calendar, Outlook, etc.
 */

import { getLogger } from '../../../../shared/typescript/src';

const logger = getLogger();

/**
 * Sync appointment to external calendar system.
 * Currently a no-op placeholder for future implementation.
 */
export async function syncToExternalCalendar(
  appointmentId: string,
  action: 'create' | 'update' | 'cancel',
): Promise<void> {
  logger.debug({ appointmentId, action }, 'Calendar sync placeholder (not implemented)');
}
