/**
 * Audit logger middleware — logs all mutating requests for compliance.
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger, getRedisClient, publishEvent, STREAM_AUDIT } from '../../../shared/typescript/src';
import { config } from '../config';

const logger = getLogger();

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function auditLoggerMiddleware(req: Request, res: Response, next: NextFunction): void {
  if (!MUTATING_METHODS.has(req.method)) {
    return next();
  }

  // Log after response is sent
  res.on('finish', () => {
    const auditEntry = {
      action: `${req.method} ${req.originalUrl}`,
      resourceType: 'campaign',
      resourceId: req.params.id || '',
      userId: req.user?.sub || 'anonymous',
      clinicId: req.user?.clinicId || '',
      details: {
        statusCode: res.statusCode,
        requestId: req.headers['x-request-id'],
      },
      ipAddress: req.ip || req.socket.remoteAddress,
    };

    logger.info(auditEntry, 'Audit log');

    // Publish audit event asynchronously
    try {
      const redis = getRedisClient({
        host: config.redis.host,
        port: config.redis.port,
        password: config.redis.password || undefined,
      });
      publishEvent(redis, STREAM_AUDIT, 'audit.action', auditEntry, 'campaign-engine').catch(
        (err) => {
          logger.error({ error: err.message }, 'Failed to publish audit event');
        },
      );
    } catch {
      // Redis not available — skip event publish
    }
  });

  next();
}
