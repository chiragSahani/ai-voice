/**
 * Audit logging middleware — logs every request/response for compliance.
 * Captures method, path, status, duration, user, and request ID.
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger } from '@shared/logger';

const logger = getLogger();

export function auditLoggerMiddleware(req: Request, res: Response, next: NextFunction): void {
  const startTime = process.hrtime.bigint();

  res.on('finish', () => {
    const durationMs = Number(process.hrtime.bigint() - startTime) / 1e6;

    const logData = {
      method: req.method,
      path: req.originalUrl,
      status: res.statusCode,
      durationMs: Math.round(durationMs * 100) / 100,
      requestId: req.requestId,
      userId: req.user?.sub,
      role: req.user?.role,
      ip: req.ip || req.socket.remoteAddress,
      userAgent: req.headers['user-agent'],
    };

    if (res.statusCode >= 500) {
      logger.error(logData, 'Request completed with server error');
    } else if (res.statusCode >= 400) {
      logger.warn(logData, 'Request completed with client error');
    } else {
      logger.info(logData, 'Request completed');
    }
  });

  next();
}
