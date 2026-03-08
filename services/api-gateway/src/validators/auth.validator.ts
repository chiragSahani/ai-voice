/**
 * Request validators for auth endpoints.
 */

import { Request, Response, NextFunction } from 'express';
import { LoginSchema, RefreshTokenSchema } from '../models/requests';

/**
 * Validate login request body against the LoginSchema.
 */
export function validateLogin(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.body = LoginSchema.parse(req.body);
    next();
  } catch (err) {
    next(err); // Caught by the shared errorHandler (ZodError branch)
  }
}

/**
 * Validate refresh-token request body against the RefreshTokenSchema.
 */
export function validateRefresh(req: Request, _res: Response, next: NextFunction): void {
  try {
    req.body = RefreshTokenSchema.parse(req.body);
    next();
  } catch (err) {
    next(err);
  }
}
