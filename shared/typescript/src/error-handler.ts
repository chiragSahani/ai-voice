/**
 * Express error handling middleware.
 */

import { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';
import { getLogger } from './logger';
import { errorsTotal } from './metrics';

const logger = getLogger();

export class AppError extends Error {
  public readonly code: string;
  public readonly statusCode: number;
  public readonly details?: Record<string, unknown>;

  constructor(message: string, code: string, statusCode: number, details?: Record<string, unknown>) {
    super(message);
    this.code = code;
    this.statusCode = statusCode;
    this.details = details;
    this.name = 'AppError';
  }
}

export class ValidationError extends AppError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'VALIDATION_ERROR', 400, details);
  }
}

export class NotFoundError extends AppError {
  constructor(resource: string, identifier: string) {
    super(`${resource} not found: ${identifier}`, 'NOT_FOUND', 404);
  }
}

export class ConflictError extends AppError {
  constructor(message: string) {
    super(message, 'CONFLICT', 409);
  }
}

export class ServiceUnavailableError extends AppError {
  constructor(serviceName: string) {
    super(`Service unavailable: ${serviceName}`, 'SERVICE_UNAVAILABLE', 503);
  }
}

export function errorHandler(err: Error, req: Request, res: Response, _next: NextFunction): void {
  // Zod validation errors
  if (err instanceof ZodError) {
    const details = err.errors.map((e) => ({
      path: e.path.join('.'),
      message: e.message,
    }));
    res.status(400).json({
      error: { code: 'VALIDATION_ERROR', message: 'Invalid input', details },
    });
    errorsTotal.inc({ error_type: 'validation' });
    return;
  }

  // Application errors
  if (err instanceof AppError) {
    res.status(err.statusCode).json({
      error: { code: err.code, message: err.message, details: err.details },
    });
    errorsTotal.inc({ error_type: err.code.toLowerCase() });
    return;
  }

  // Unexpected errors
  logger.error({ error: err.message, stack: err.stack }, 'Unhandled error');
  res.status(500).json({
    error: { code: 'INTERNAL_ERROR', message: 'An unexpected error occurred' },
  });
  errorsTotal.inc({ error_type: 'internal' });
}
