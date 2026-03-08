/**
 * Gateway-specific error handler — wraps the shared errorHandler and adds
 * request-ID propagation to error responses.
 */

import { Request, Response, NextFunction } from 'express';
import { errorHandler } from '@shared/error-handler';
import { getLogger } from '@shared/logger';

const logger = getLogger();

/**
 * Express error-handling middleware.
 * Augments responses with the X-Request-ID header and delegates to the
 * shared error handler for consistent error formatting.
 */
export function gatewayErrorHandler(err: Error, req: Request, res: Response, next: NextFunction): void {
  // Ensure request ID is on the response
  if (req.requestId && !res.headersSent) {
    res.setHeader('X-Request-ID', req.requestId);
  }

  // Handle CORS errors with a friendlier message
  if (err.message && err.message.includes('not allowed by CORS policy')) {
    logger.warn({ origin: req.headers.origin, requestId: req.requestId }, 'CORS rejection');
    if (!res.headersSent) {
      res.status(403).json({
        error: {
          code: 'CORS_REJECTED',
          message: 'Origin not allowed',
          requestId: req.requestId,
        },
      });
    }
    return;
  }

  // Delegate to shared handler
  errorHandler(err, req, res, next);
}
