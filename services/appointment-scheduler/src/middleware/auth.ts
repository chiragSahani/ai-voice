/**
 * Auth middleware wiring for the Appointment Scheduler service.
 */

import { authMiddleware, requireRole } from '../../../../shared/typescript/src';
import { getConfig } from '../config';

export function getAuthMiddleware() {
  const config = getConfig();
  return authMiddleware(config.jwt.secret);
}

export { requireRole };
