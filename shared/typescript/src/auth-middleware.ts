/**
 * JWT authentication middleware for Express.
 */

import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { getLogger } from './logger';

const logger = getLogger();

export interface JwtPayload {
  sub: string;        // User ID
  role: string;       // admin | staff | doctor | voice_agent
  clinicId: string;
  permissions: string[];
  exp: number;
  iss: string;
}

declare global {
  namespace Express {
    interface Request {
      user?: JwtPayload;
    }
  }
}

export function authMiddleware(jwtSecret: string) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const authHeader = req.headers.authorization;

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      res.status(401).json({ error: { code: 'UNAUTHORIZED', message: 'Missing authorization token' } });
      return;
    }

    const token = authHeader.substring(7);

    try {
      const decoded = jwt.verify(token, jwtSecret) as JwtPayload;
      req.user = decoded;
      next();
    } catch (err: any) {
      if (err.name === 'TokenExpiredError') {
        res.status(401).json({ error: { code: 'TOKEN_EXPIRED', message: 'Token has expired' } });
      } else {
        res.status(401).json({ error: { code: 'TOKEN_INVALID', message: 'Invalid token' } });
      }
    }
  };
}

export function requireRole(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: { code: 'UNAUTHORIZED', message: 'Authentication required' } });
      return;
    }

    if (!roles.includes(req.user.role)) {
      logger.warn({ userId: req.user.sub, role: req.user.role, required: roles }, 'Insufficient permissions');
      res.status(403).json({ error: { code: 'FORBIDDEN', message: 'Insufficient permissions' } });
      return;
    }

    next();
  };
}

export function requirePermission(...permissions: string[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: { code: 'UNAUTHORIZED', message: 'Authentication required' } });
      return;
    }

    const hasPermission = permissions.every((p) => req.user!.permissions.includes(p));
    if (!hasPermission) {
      res.status(403).json({ error: { code: 'FORBIDDEN', message: 'Missing required permissions' } });
      return;
    }

    next();
  };
}
