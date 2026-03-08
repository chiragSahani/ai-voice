/**
 * Patient service — core business logic for patient CRUD operations.
 * All PHI encryption/decryption is handled by Mongoose hooks in domain.ts.
 */

import { FilterQuery } from 'mongoose';
import { PatientModel, IPatientDocument } from '../models/domain';
import { CreatePatientInput, UpdatePatientInput, SearchPatientCriteria, PaginationInput } from '../models/requests';
import { toPatientResponse, toPatientListResponse, PatientResponse, PatientListResponse } from '../models/responses';
import { auditService, AuditAction } from './audit.service';
import { getLogger } from '../../../shared/typescript/src/logger';
import { NotFoundError, ConflictError } from '../../../shared/typescript/src/error-handler';

const logger = getLogger();

export class PatientService {
  /**
   * Create a new patient record.
   * Validates MRN uniqueness within the clinic before creation.
   */
  async createPatient(
    data: CreatePatientInput,
    userId: string,
    clinicId: string,
    ipAddress?: string,
  ): Promise<PatientResponse> {
    // Check MRN uniqueness within clinic
    const existingMrn = await PatientModel.findOne({
      medicalRecordNumber: data.medicalRecordNumber,
      clinicId: data.clinicId,
    });
    if (existingMrn) {
      throw new ConflictError(
        `Patient with MRN ${data.medicalRecordNumber} already exists in clinic ${data.clinicId}`,
      );
    }

    // Check for duplicate phone within clinic
    const existingPhone = await PatientModel.findOne({
      phone: data.phone,
      clinicId: data.clinicId,
    });
    if (existingPhone) {
      throw new ConflictError(
        `Patient with phone ${data.phone} already exists in clinic ${data.clinicId}`,
      );
    }

    const patient = new PatientModel({
      ...data,
      dateOfBirth: new Date(data.dateOfBirth),
      isActive: true,
    });

    const saved = await patient.save();

    logger.info({ patientId: saved._id, clinicId: data.clinicId }, 'Patient created');

    // Audit log — PHI creation
    await auditService.logAccess({
      userId,
      action: 'CREATE',
      resourceType: 'patient',
      resourceId: saved._id.toString(),
      clinicId: data.clinicId,
      details: { medicalRecordNumber: data.medicalRecordNumber },
      ipAddress,
    });

    return toPatientResponse(saved);
  }

  /**
   * Get a patient by ID. Logs PHI access.
   */
  async getPatient(
    id: string,
    userId: string,
    clinicId: string,
    ipAddress?: string,
  ): Promise<PatientResponse> {
    const patient = await PatientModel.findById(id);
    if (!patient || !patient.isActive) {
      throw new NotFoundError('Patient', id);
    }

    // Audit log — PHI read
    await auditService.logAccess({
      userId,
      action: 'READ',
      resourceType: 'patient',
      resourceId: id,
      clinicId,
      ipAddress,
    });

    return toPatientResponse(patient);
  }

  /**
   * Update a patient record. Logs PHI modification.
   */
  async updatePatient(
    id: string,
    data: UpdatePatientInput,
    userId: string,
    clinicId: string,
    ipAddress?: string,
  ): Promise<PatientResponse> {
    const updateData: Record<string, any> = { ...data };

    // Convert dateOfBirth string to Date if present
    if (data.dateOfBirth) {
      updateData.dateOfBirth = new Date(data.dateOfBirth);
    }

    const patient = await PatientModel.findOneAndUpdate(
      { _id: id, isActive: true },
      { $set: updateData },
      { new: true, runValidators: true },
    );

    if (!patient) {
      throw new NotFoundError('Patient', id);
    }

    logger.info({ patientId: id }, 'Patient updated');

    // Determine which fields were changed for audit detail
    const changedFields = Object.keys(data);

    await auditService.logAccess({
      userId,
      action: 'UPDATE',
      resourceType: 'patient',
      resourceId: id,
      clinicId,
      details: { changedFields },
      ipAddress,
    });

    return toPatientResponse(patient);
  }

  /**
   * Search patients by criteria with pagination.
   */
  async searchPatients(
    criteria: SearchPatientCriteria,
    pagination: PaginationInput,
    userId: string,
    clinicId: string,
    ipAddress?: string,
  ): Promise<PatientListResponse> {
    const filter: FilterQuery<IPatientDocument> = { isActive: true };

    if (criteria.clinicId) {
      filter.clinicId = criteria.clinicId;
    }

    if (criteria.phone) {
      filter.phone = criteria.phone;
    }

    if (criteria.mrn) {
      filter.medicalRecordNumber = criteria.mrn;
    }

    // Name search: since names are encrypted at rest, we cannot do a
    // server-side regex match on encrypted fields. For name searches,
    // we retrieve all matching patients from the clinic and filter in memory
    // after decryption (Mongoose post-find hook decrypts automatically).
    // This is acceptable for clinic-scoped queries with reasonable data sizes.

    const { page, limit, sortBy, sortOrder } = pagination;
    const skip = (page - 1) * limit;
    const sort: Record<string, 1 | -1> = { [sortBy]: sortOrder === 'asc' ? 1 : -1 };

    let patients: IPatientDocument[];
    let total: number;

    if (criteria.name) {
      // For name search: fetch all from clinic, decrypt, then filter
      const nameFilter = { ...filter };
      if (!nameFilter.clinicId && clinicId) {
        nameFilter.clinicId = clinicId;
      }

      const allPatients = await PatientModel.find(nameFilter).sort(sort);
      const nameLower = criteria.name.toLowerCase();

      const filtered = allPatients.filter((p) => {
        const fullName = `${p.firstName} ${p.lastName}`.toLowerCase();
        return fullName.includes(nameLower);
      });

      total = filtered.length;
      patients = filtered.slice(skip, skip + limit);
    } else {
      [patients, total] = await Promise.all([
        PatientModel.find(filter).sort(sort).skip(skip).limit(limit),
        PatientModel.countDocuments(filter),
      ]);
    }

    // Audit log — PHI search
    await auditService.logAccess({
      userId,
      action: 'SEARCH',
      resourceType: 'patient',
      resourceId: '*',
      clinicId,
      details: { criteria, resultCount: total },
      ipAddress,
    });

    return toPatientListResponse(patients, total, page, limit);
  }

  /**
   * Soft-delete a patient by setting isActive = false.
   */
  async deactivatePatient(
    id: string,
    userId: string,
    clinicId: string,
    ipAddress?: string,
  ): Promise<PatientResponse> {
    const patient = await PatientModel.findOneAndUpdate(
      { _id: id, isActive: true },
      { $set: { isActive: false } },
      { new: true },
    );

    if (!patient) {
      throw new NotFoundError('Patient', id);
    }

    logger.info({ patientId: id }, 'Patient deactivated (soft delete)');

    await auditService.logAccess({
      userId,
      action: 'DEACTIVATE',
      resourceType: 'patient',
      resourceId: id,
      clinicId,
      ipAddress,
    });

    return toPatientResponse(patient);
  }

  /**
   * Look up a patient by phone number within a clinic.
   */
  async getPatientByPhone(
    phone: string,
    clinicId: string,
    userId: string,
    ipAddress?: string,
  ): Promise<PatientResponse> {
    const patient = await PatientModel.findOne({
      phone,
      clinicId,
      isActive: true,
    });

    if (!patient) {
      throw new NotFoundError('Patient', `phone:${phone}`);
    }

    await auditService.logAccess({
      userId,
      action: 'READ',
      resourceType: 'patient',
      resourceId: patient._id.toString(),
      clinicId,
      details: { lookupMethod: 'phone' },
      ipAddress,
    });

    return toPatientResponse(patient);
  }

  /**
   * Look up a patient by medical record number.
   */
  async getPatientByMRN(
    mrn: string,
    userId: string,
    clinicId: string,
    ipAddress?: string,
  ): Promise<PatientResponse> {
    const patient = await PatientModel.findOne({
      medicalRecordNumber: mrn,
      isActive: true,
    });

    if (!patient) {
      throw new NotFoundError('Patient', `mrn:${mrn}`);
    }

    await auditService.logAccess({
      userId,
      action: 'READ',
      resourceType: 'patient',
      resourceId: patient._id.toString(),
      clinicId,
      details: { lookupMethod: 'mrn' },
      ipAddress,
    });

    return toPatientResponse(patient);
  }

  /**
   * Update the lastInteraction timestamp for a patient.
   * Used by voice agent after each interaction.
   */
  async updateLastInteraction(id: string): Promise<void> {
    const result = await PatientModel.findByIdAndUpdate(id, {
      $set: { lastInteraction: new Date() },
    });

    if (!result) {
      throw new NotFoundError('Patient', id);
    }

    logger.debug({ patientId: id }, 'Patient last interaction updated');
  }
}

export const patientService = new PatientService();
