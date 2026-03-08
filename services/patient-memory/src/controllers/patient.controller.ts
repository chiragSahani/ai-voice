/**
 * Patient controller — HTTP request handlers for patient CRUD operations.
 * Delegates to PatientService, uses validators for input, returns DTOs.
 */

import { Request, Response, NextFunction } from 'express';
import { patientService } from '../services/patient.service';
import {
  validateCreatePatient,
  validateUpdatePatient,
  validateSearchParams,
  validatePatientId,
  validatePhoneParam,
} from '../validators/patient.validator';
import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

/**
 * POST /api/v1/patients
 * Create a new patient record.
 */
export async function createPatient(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const data = validateCreatePatient(req);
    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;
    const ipAddress = req.ip;

    const patient = await patientService.createPatient(data, userId, clinicId, ipAddress);

    res.status(201).json({ data: patient });
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/patients/:id
 * Get a patient by ID. Logs PHI access.
 */
export async function getPatient(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const id = validatePatientId(req);
    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;
    const ipAddress = req.ip;

    const patient = await patientService.getPatient(id, userId, clinicId, ipAddress);

    res.status(200).json({ data: patient });
  } catch (err) {
    next(err);
  }
}

/**
 * PUT /api/v1/patients/:id
 * Update a patient record.
 */
export async function updatePatient(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const id = validatePatientId(req);
    const data = validateUpdatePatient(req);
    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;
    const ipAddress = req.ip;

    const patient = await patientService.updatePatient(id, data, userId, clinicId, ipAddress);

    res.status(200).json({ data: patient });
  } catch (err) {
    next(err);
  }
}

/**
 * DELETE /api/v1/patients/:id
 * Soft-delete (deactivate) a patient.
 */
export async function deactivatePatient(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const id = validatePatientId(req);
    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;
    const ipAddress = req.ip;

    const patient = await patientService.deactivatePatient(id, userId, clinicId, ipAddress);

    res.status(200).json({ data: patient });
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/patients/search
 * Search patients by criteria with pagination.
 */
export async function searchPatients(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { criteria, pagination } = validateSearchParams(req);
    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;
    const ipAddress = req.ip;

    const result = await patientService.searchPatients(criteria, pagination, userId, clinicId, ipAddress);

    res.status(200).json({ data: result.patients, meta: result.pagination });
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/patients/phone/:phone
 * Look up a patient by phone number within the authenticated user's clinic.
 */
export async function getPatientByPhone(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const phone = validatePhoneParam(req);
    const userId = req.user!.sub;
    const clinicId = req.query.clinicId as string || req.user!.clinicId;
    const ipAddress = req.ip;

    const patient = await patientService.getPatientByPhone(phone, clinicId, userId, ipAddress);

    res.status(200).json({ data: patient });
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/patients/mrn/:mrn
 * Look up a patient by medical record number.
 */
export async function getPatientByMRN(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const mrn = req.params.mrn;
    if (!mrn) {
      res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'MRN is required' } });
      return;
    }

    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;
    const ipAddress = req.ip;

    const patient = await patientService.getPatientByMRN(mrn, userId, clinicId, ipAddress);

    res.status(200).json({ data: patient });
  } catch (err) {
    next(err);
  }
}

/**
 * POST /api/v1/patients/:id/interaction
 * Update the lastInteraction timestamp.
 */
export async function updateLastInteraction(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const id = validatePatientId(req);
    await patientService.updateLastInteraction(id);

    res.status(204).send();
  } catch (err) {
    next(err);
  }
}
