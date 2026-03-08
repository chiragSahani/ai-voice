/**
 * Doctor controller — placeholder for future doctor management endpoints.
 */

import { Request, Response, NextFunction } from 'express';
import { successResponse, NotFoundError } from '../../../../shared/typescript/src';
import { Doctor } from '../models/domain';

/**
 * GET /doctors/:id
 * Get doctor details by ID.
 */
export async function getDoctorById(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const doctor = await Doctor.findById(req.params.id).lean();
    if (!doctor) {
      throw new NotFoundError('Doctor', req.params.id);
    }
    res.json(successResponse({
      id: doctor._id.toString(),
      name: doctor.name,
      specialization: doctor.specialization,
      clinicId: doctor.clinicId,
      isActive: doctor.isActive,
      schedule: doctor.schedule,
    }));
  } catch (err) {
    next(err);
  }
}
