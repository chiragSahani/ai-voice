/**
 * Doctor-related validators — placeholder for future doctor management endpoints.
 */

import { z } from 'zod';
import { Request, Response, NextFunction } from 'express';

const objectIdRegex = /^[0-9a-fA-F]{24}$/;

export const GetDoctorSchema = z.object({
  id: z.string().regex(objectIdRegex, 'Invalid doctor ID'),
});

export function validateDoctorId(req: Request, _res: Response, next: NextFunction): void {
  try {
    GetDoctorSchema.parse({ id: req.params.id });
    next();
  } catch (err) {
    next(err);
  }
}
