/**
 * Patient request validators.
 * Wraps Zod schemas and adds business-rule validation.
 */

import { Request } from 'express';
import { CreatePatientSchema, UpdatePatientSchema, SearchPatientSchema, PaginationSchema } from '../models/requests';
import type { CreatePatientInput, UpdatePatientInput, SearchPatientCriteria, PaginationInput } from '../models/requests';

/**
 * Validate a create-patient request body.
 * Throws ZodError on invalid input (caught by shared error handler).
 */
export function validateCreatePatient(req: Request): CreatePatientInput {
  return CreatePatientSchema.parse(req.body);
}

/**
 * Validate an update-patient request body.
 * Throws ZodError on invalid input.
 */
export function validateUpdatePatient(req: Request): UpdatePatientInput {
  return UpdatePatientSchema.parse(req.body);
}

/**
 * Validate search query parameters.
 */
export function validateSearchParams(req: Request): {
  criteria: SearchPatientCriteria;
  pagination: PaginationInput;
} {
  const criteria = SearchPatientSchema.parse({
    phone: req.query.phone,
    name: req.query.name,
    mrn: req.query.mrn,
    clinicId: req.query.clinicId,
  });

  const pagination = PaginationSchema.parse({
    page: req.query.page,
    limit: req.query.limit,
    sortBy: req.query.sortBy,
    sortOrder: req.query.sortOrder,
  });

  return { criteria, pagination };
}

/**
 * Validate a patient ID parameter (must be a valid MongoDB ObjectId format).
 */
export function validatePatientId(req: Request): string {
  const id = req.params.id;
  if (!id || !/^[0-9a-fA-F]{24}$/.test(id)) {
    const { ValidationError } = require('../../../shared/typescript/src/error-handler');
    throw new ValidationError('Invalid patient ID format');
  }
  return id;
}

/**
 * Validate a phone number parameter.
 */
export function validatePhoneParam(req: Request): string {
  const phone = req.params.phone;
  if (!phone || phone.length < 7) {
    const { ValidationError } = require('../../../shared/typescript/src/error-handler');
    throw new ValidationError('Invalid phone number');
  }
  return phone;
}
