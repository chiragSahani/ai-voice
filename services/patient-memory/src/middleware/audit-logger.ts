/**
 * Express middleware for automatic PHI access audit logging.
 *
 * Logs every request that accesses patient data endpoints.
 * This is a defense-in-depth measure — individual service methods
 * also log specific PHI access events.
 */

import { Request, Response, NextFunction } from 'express';
import { auditService, AuditAction } from '../services/audit.service';
import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

/**
 * Map HTTP methods to audit actions.
 */
function methodToAction(method: string): AuditAction {
  switch (method.toUpperCase()) {
    case 'POST':
      return 'CREATE';
    case 'GET':
      return 'READ';
    case 'PUT':
    case 'PATCH':
      return 'UPDATE';
    case 'DELETE':
      return 'DELETE';
    default:
      return 'READ';
  }
}

/**
 * Middleware that logs PHI access at the HTTP layer.
 * Runs after the response is sent (on 'finish') to avoid blocking.
 */
export function auditLoggerMiddleware() {
  return (req: Request, res: Response, next: NextFunction): void => {
    // Only audit patient-related endpoints
    if (!req.path.includes('/patients')) {
      return next();
    }

    // Skip health checks and metrics
    if (req.path.includes('/health') || req.path.includes('/metrics')) {
      return next();
    }

    const startTime = Date.now();

    res.on('finish', () => {
      // Only log successful operations (2xx/3xx)
      if (res.statusCode >= 400) return;

      const userId = req.user?.sub || 'anonymous';
      const clinicId = req.user?.clinicId || 'unknown';
      const action = methodToAction(req.method);
      const resourceId = req.params.id || req.params.phone || req.params.mrn || '*';
      const duration = Date.now() - startTime;

      // Fire-and-forget — never block the response
      auditService.logAccess({
        userId,
        action,
        resourceType: 'patient',
        resourceId,
        clinicId,
        details: {
          method: req.method,
          path: req.path,
          statusCode: res.statusCode,
          durationMs: duration,
          layer: 'middleware',
        },
        ipAddress: req.ip,
        userAgent: req.get('user-agent'),
      }).catch((err) => {
        logger.error({ error: (err as Error).message }, 'Audit middleware logging failed');
      });
    });

    next();
  };
}
