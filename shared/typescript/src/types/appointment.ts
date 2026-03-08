/**
 * Appointment and slot domain types and Mongoose schemas.
 */

import { Schema, model, Document, Types } from 'mongoose';

// --- Doctor ---

export interface DoctorScheduleSlot {
  dayOfWeek: number; // 0=Sun, 6=Sat
  startTime: string; // "09:00"
  endTime: string;   // "17:00"
  slotDurationMinutes: number;
}

export interface DoctorOverride {
  date: Date;
  available: boolean;
  reason?: string;
  startTime?: string;
  endTime?: string;
}

export interface IDoctor extends Document {
  name: string;
  specialization: string;
  clinicId: string;
  schedule: DoctorScheduleSlot[];
  overrides: DoctorOverride[];
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const doctorSchema = new Schema<IDoctor>(
  {
    name: { type: String, required: true },
    specialization: { type: String, required: true, index: true },
    clinicId: { type: String, required: true, index: true },
    schedule: [
      {
        dayOfWeek: { type: Number, required: true },
        startTime: { type: String, required: true },
        endTime: { type: String, required: true },
        slotDurationMinutes: { type: Number, default: 30 },
      },
    ],
    overrides: [
      {
        date: { type: Date, required: true },
        available: { type: Boolean, required: true },
        reason: String,
        startTime: String,
        endTime: String,
      },
    ],
    isActive: { type: Boolean, default: true },
  },
  { timestamps: true, collection: 'doctors' },
);

export const Doctor = model<IDoctor>('Doctor', doctorSchema);

// --- Appointment Slot ---

export type SlotStatus = 'available' | 'held' | 'booked' | 'cancelled';

export interface IAppointmentSlot extends Document {
  doctorId: Types.ObjectId;
  clinicId: string;
  date: Date;
  startTime: string;
  endTime: string;
  status: SlotStatus;
  heldBy?: string;
  heldUntil?: Date;
  createdAt: Date;
  updatedAt: Date;
}

const appointmentSlotSchema = new Schema<IAppointmentSlot>(
  {
    doctorId: { type: Schema.Types.ObjectId, ref: 'Doctor', required: true },
    clinicId: { type: String, required: true },
    date: { type: Date, required: true },
    startTime: { type: String, required: true },
    endTime: { type: String, required: true },
    status: { type: String, enum: ['available', 'held', 'booked', 'cancelled'], default: 'available' },
    heldBy: String,
    heldUntil: Date,
  },
  {
    timestamps: true,
    collection: 'appointmentSlots',
    optimisticConcurrency: true, // Uses __v for optimistic locking
  },
);

appointmentSlotSchema.index({ doctorId: 1, date: 1, status: 1 });
appointmentSlotSchema.index({ clinicId: 1, date: 1, status: 1 });
appointmentSlotSchema.index({ heldUntil: 1 }, { expireAfterSeconds: 0 });

export const AppointmentSlot = model<IAppointmentSlot>('AppointmentSlot', appointmentSlotSchema);

// --- Appointment ---

export type AppointmentStatus = 'scheduled' | 'confirmed' | 'checked_in' | 'completed' | 'cancelled' | 'no_show';

export interface IAppointment extends Document {
  patientId: Types.ObjectId;
  doctorId: Types.ObjectId;
  slotId: Types.ObjectId;
  clinicId: string;
  date: Date;
  startTime: string;
  endTime: string;
  status: AppointmentStatus;
  type: 'new_visit' | 'follow_up' | 'consultation' | 'procedure';
  reason?: string;
  notes?: string;
  bookedBy: string; // userId or 'voice_agent'
  bookedVia: 'voice' | 'web' | 'phone' | 'walk_in';
  cancelledAt?: Date;
  cancelReason?: string;
  reminderSent: boolean;
  sessionId?: string;
  createdAt: Date;
  updatedAt: Date;
}

const appointmentSchema = new Schema<IAppointment>(
  {
    patientId: { type: Schema.Types.ObjectId, ref: 'Patient', required: true },
    doctorId: { type: Schema.Types.ObjectId, ref: 'Doctor', required: true },
    slotId: { type: Schema.Types.ObjectId, ref: 'AppointmentSlot', required: true, unique: true },
    clinicId: { type: String, required: true },
    date: { type: Date, required: true },
    startTime: { type: String, required: true },
    endTime: { type: String, required: true },
    status: {
      type: String,
      enum: ['scheduled', 'confirmed', 'checked_in', 'completed', 'cancelled', 'no_show'],
      default: 'scheduled',
    },
    type: {
      type: String,
      enum: ['new_visit', 'follow_up', 'consultation', 'procedure'],
      required: true,
    },
    reason: String,
    notes: String,
    bookedBy: { type: String, required: true },
    bookedVia: { type: String, enum: ['voice', 'web', 'phone', 'walk_in'], required: true },
    cancelledAt: Date,
    cancelReason: String,
    reminderSent: { type: Boolean, default: false },
    sessionId: String,
  },
  { timestamps: true, collection: 'appointments' },
);

appointmentSchema.index({ patientId: 1, date: -1 });
appointmentSchema.index({ doctorId: 1, date: 1 });
appointmentSchema.index({ clinicId: 1, date: 1, status: 1 });

export const Appointment = model<IAppointment>('Appointment', appointmentSchema);
