/**
 * Auth middleware re-export configured with the service's JWT secret.
 */

import { authMiddleware, requireRole, requirePermission } from '../../../shared/typescript/src/auth-middleware';
import { getConfig } from '../config';

export function getAuthMiddleware() {
  const config = getConfig();
  return authMiddleware(config.jwt.secret);
}

export { requireRole, requirePermission };
