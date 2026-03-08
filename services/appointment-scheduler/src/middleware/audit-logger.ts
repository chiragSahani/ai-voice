/**
 * Audit logging middleware — logs all mutating requests for compliance.
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger } from '../../../../shared/typescript/src';

const logger = getLogger();

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function auditLoggerMiddleware(req: Request, res: Response, next: NextFunction): void {
  if (!MUTATING_METHODS.has(req.method)) {
    next();
    return;
  }

  const startTime = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - startTime;
    logger.info(
      {
        audit: true,
        method: req.method,
        path: req.originalUrl,
        statusCode: res.statusCode,
        durationMs: duration,
        userId: req.user?.sub || 'anonymous',
        requestId: req.headers['x-request-id'],
        ip: req.ip,
      },
      'Audit log',
    );
  });

  next();
}
