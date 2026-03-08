/**
 * Request ID middleware — generates or propagates an X-Request-ID header
 * and attaches it to the request object and logger context.
 */

import { Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { getLogger } from '@shared/logger';

const REQUEST_ID_HEADER = 'x-request-id';

declare global {
  namespace Express {
    interface Request {
      requestId?: string;
    }
  }
}

export function requestIdMiddleware(req: Request, res: Response, next: NextFunction): void {
  const incomingId = req.headers[REQUEST_ID_HEADER] as string | undefined;
  const requestId = incomingId && isValidRequestId(incomingId) ? incomingId : uuidv4();

  req.requestId = requestId;
  res.setHeader(REQUEST_ID_HEADER, requestId);

  // Attach to logger context for correlated log lines
  const logger = getLogger();
  (req as any).log = logger.child({ requestId });

  next();
}

/**
 * Basic validation: request IDs should be reasonable strings (UUID-like).
 */
function isValidRequestId(id: string): boolean {
  return id.length > 0 && id.length <= 128 && /^[\w\-.:]+$/.test(id);
}
