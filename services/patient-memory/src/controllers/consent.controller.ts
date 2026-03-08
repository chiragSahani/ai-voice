/**
 * Consent controller — manages patient consent for voice recording.
 */

import { Request, Response, NextFunction } from 'express';
import { PatientModel } from '../models/domain';
import { validateUpdateConsent } from '../validators/consent.validator';
import { validatePatientId } from '../validators/patient.validator';
import { auditService } from '../services/audit.service';
import { toPatientResponse } from '../models/responses';
import { NotFoundError } from '../../../shared/typescript/src/error-handler';

/**
 * PUT /api/v1/patients/:id/consent
 * Update voice recording consent for a patient.
 */
export async function updateConsent(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const id = validatePatientId(req);
    const { consentVoiceRecording } = validateUpdateConsent(req);
    const userId = req.user!.sub;
    const clinicId = req.user!.clinicId;

    const patient = await PatientModel.findOneAndUpdate(
      { _id: id, isActive: true },
      { $set: { consentVoiceRecording } },
      { new: true },
    );

    if (!patient) {
      throw new NotFoundError('Patient', id);
    }

    await auditService.logAccess({
      userId,
      action: 'UPDATE',
      resourceType: 'patient',
      resourceId: id,
      clinicId,
      details: { field: 'consentVoiceRecording', value: consentVoiceRecording },
      ipAddress: req.ip,
    });

    res.status(200).json({ data: toPatientResponse(patient) });
  } catch (err) {
    next(err);
  }
}
