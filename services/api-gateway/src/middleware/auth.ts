/**
 * Auth middleware — re-exports the shared authMiddleware bound to the
 * gateway's JWT secret, plus role/permission guards.
 */

import { authMiddleware, requireRole, requirePermission } from '@shared/auth-middleware';
import { GatewayConfig } from '../config';

/**
 * Create the JWT auth middleware pre-configured with the gateway secret.
 */
export function createAuthMiddleware(config: GatewayConfig) {
  return authMiddleware(config.jwt.secret);
}

export { requireRole, requirePermission };
