/**
 * V1 API routes for the Patient Memory service.
 * All routes require JWT authentication.
 * Routes are mounted at /api/v1/patients.
 */

import { Router } from 'express';
import {
  createPatient,
  getPatient,
  updatePatient,
  deactivatePatient,
  searchPatients,
  getPatientByPhone,
  getPatientByMRN,
  updateLastInteraction,
} from '../controllers/patient.controller';
import { updateConsent } from '../controllers/consent.controller';
import { getAuthMiddleware, requireRole } from '../middleware/auth';
import { auditLoggerMiddleware } from '../middleware/audit-logger';

export function createV1Router(): Router {
  const router = Router();
  const auth = getAuthMiddleware();

  // All patient routes require authentication
  router.use(auth);

  // Audit logging for all patient endpoints
  router.use(auditLoggerMiddleware());

  // --- Search must be defined before /:id to avoid conflict ---
  // GET /api/v1/patients/search — search patients
  router.get('/search', searchPatients);

  // GET /api/v1/patients/phone/:phone — look up by phone
  router.get('/phone/:phone', getPatientByPhone);

  // GET /api/v1/patients/mrn/:mrn — look up by MRN
  router.get('/mrn/:mrn', getPatientByMRN);

  // POST /api/v1/patients — create patient (staff, admin, doctor)
  router.post('/', requireRole('admin', 'staff', 'doctor', 'voice_agent'), createPatient);

  // GET /api/v1/patients/:id — get patient by ID
  router.get('/:id', getPatient);

  // PUT /api/v1/patients/:id — update patient
  router.put('/:id', requireRole('admin', 'staff', 'doctor'), updatePatient);

  // DELETE /api/v1/patients/:id — soft delete (admin only)
  router.delete('/:id', requireRole('admin'), deactivatePatient);

  // PUT /api/v1/patients/:id/consent — update consent
  router.put('/:id/consent', requireRole('admin', 'staff', 'doctor'), updateConsent);

  // POST /api/v1/patients/:id/interaction — update last interaction timestamp
  router.post('/:id/interaction', requireRole('admin', 'staff', 'doctor', 'voice_agent'), updateLastInteraction);

  return router;
}
