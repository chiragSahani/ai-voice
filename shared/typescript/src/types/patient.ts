/**
 * Patient domain types and Mongoose schema.
 */

import { Schema, model, Document } from 'mongoose';

export interface PatientAddress {
  street: string;
  city: string;
  state: string;
  zipCode: string;
  country: string;
}

export interface EmergencyContact {
  name: string;
  relationship: string;
  phone: string;
}

export interface IPatient extends Document {
  firstName: string;          // PHI - encrypted
  lastName: string;           // PHI - encrypted
  dateOfBirth: Date;
  gender: 'male' | 'female' | 'other' | 'prefer_not_to_say';
  phone: string;
  email: string;              // PHI - encrypted
  address: PatientAddress;    // PHI - encrypted
  preferredLanguage: 'en' | 'hi' | 'ta';
  insuranceProvider?: string;
  insuranceId?: string;
  emergencyContact?: EmergencyContact;
  medicalRecordNumber: string;
  clinicId: string;
  tags: string[];
  isActive: boolean;
  lastInteraction?: Date;
  consentVoiceRecording: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const patientSchema = new Schema<IPatient>(
  {
    firstName: { type: String, required: true },
    lastName: { type: String, required: true },
    dateOfBirth: { type: Date, required: true },
    gender: { type: String, enum: ['male', 'female', 'other', 'prefer_not_to_say'], required: true },
    phone: { type: String, required: true, index: true },
    email: { type: String, required: true },
    address: {
      street: String,
      city: String,
      state: String,
      zipCode: String,
      country: { type: String, default: 'IN' },
    },
    preferredLanguage: { type: String, enum: ['en', 'hi', 'ta'], default: 'en' },
    insuranceProvider: String,
    insuranceId: String,
    emergencyContact: {
      name: String,
      relationship: String,
      phone: String,
    },
    medicalRecordNumber: { type: String, required: true, unique: true },
    clinicId: { type: String, required: true, index: true },
    tags: [{ type: String }],
    isActive: { type: Boolean, default: true },
    lastInteraction: Date,
    consentVoiceRecording: { type: Boolean, default: false },
  },
  {
    timestamps: true,
    collection: 'patients',
  },
);

patientSchema.index({ clinicId: 1, phone: 1 });
patientSchema.index({ clinicId: 1, lastName: 1, firstName: 1 });

export const Patient = model<IPatient>('Patient', patientSchema);
