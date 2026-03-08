/**
 * Campaign and call domain types and Mongoose schemas.
 */

import { Schema, model, Document, Types } from 'mongoose';

// --- Campaign ---

export type CampaignStatus = 'draft' | 'scheduled' | 'running' | 'paused' | 'completed' | 'cancelled';
export type CampaignType = 'reminder' | 'follow_up' | 'recall' | 'survey' | 'custom';

export interface CampaignSchedule {
  startDate: Date;
  endDate?: Date;
  callWindowStart: string; // "09:00"
  callWindowEnd: string;   // "18:00"
  timezone: string;
  maxConcurrentCalls: number;
}

export interface ICampaign extends Document {
  name: string;
  type: CampaignType;
  clinicId: string;
  status: CampaignStatus;
  schedule: CampaignSchedule;
  targetPatientIds: Types.ObjectId[];
  messageTemplate: string;
  language: 'en' | 'hi' | 'ta';
  maxRetries: number;
  retryDelayMinutes: number;
  createdBy: string;
  stats: {
    totalCalls: number;
    completed: number;
    failed: number;
    pending: number;
    answeredRate: number;
  };
  createdAt: Date;
  updatedAt: Date;
}

const campaignSchema = new Schema<ICampaign>(
  {
    name: { type: String, required: true },
    type: { type: String, enum: ['reminder', 'follow_up', 'recall', 'survey', 'custom'], required: true },
    clinicId: { type: String, required: true, index: true },
    status: {
      type: String,
      enum: ['draft', 'scheduled', 'running', 'paused', 'completed', 'cancelled'],
      default: 'draft',
    },
    schedule: {
      startDate: { type: Date, required: true },
      endDate: Date,
      callWindowStart: { type: String, default: '09:00' },
      callWindowEnd: { type: String, default: '18:00' },
      timezone: { type: String, default: 'Asia/Kolkata' },
      maxConcurrentCalls: { type: Number, default: 5 },
    },
    targetPatientIds: [{ type: Schema.Types.ObjectId, ref: 'Patient' }],
    messageTemplate: { type: String, required: true },
    language: { type: String, enum: ['en', 'hi', 'ta'], default: 'en' },
    maxRetries: { type: Number, default: 3 },
    retryDelayMinutes: { type: Number, default: 60 },
    createdBy: { type: String, required: true },
    stats: {
      totalCalls: { type: Number, default: 0 },
      completed: { type: Number, default: 0 },
      failed: { type: Number, default: 0 },
      pending: { type: Number, default: 0 },
      answeredRate: { type: Number, default: 0 },
    },
  },
  { timestamps: true, collection: 'campaigns' },
);

export const Campaign = model<ICampaign>('Campaign', campaignSchema);

// --- Campaign Call ---

export type CallStatus = 'pending' | 'queued' | 'ringing' | 'in_progress' | 'completed' | 'failed' | 'no_answer' | 'busy' | 'cancelled';
export type CallOutcome = 'confirmed' | 'rescheduled' | 'cancelled' | 'no_response' | 'callback_requested' | 'error';

export interface ICampaignCall extends Document {
  campaignId: Types.ObjectId;
  patientId: Types.ObjectId;
  clinicId: string;
  status: CallStatus;
  outcome?: CallOutcome;
  attemptNumber: number;
  scheduledAt: Date;
  startedAt?: Date;
  endedAt?: Date;
  durationSeconds?: number;
  sessionId?: string;
  transcript?: string;
  errorMessage?: string;
  createdAt: Date;
  updatedAt: Date;
}

const campaignCallSchema = new Schema<ICampaignCall>(
  {
    campaignId: { type: Schema.Types.ObjectId, ref: 'Campaign', required: true },
    patientId: { type: Schema.Types.ObjectId, ref: 'Patient', required: true },
    clinicId: { type: String, required: true },
    status: {
      type: String,
      enum: ['pending', 'queued', 'ringing', 'in_progress', 'completed', 'failed', 'no_answer', 'busy', 'cancelled'],
      default: 'pending',
    },
    outcome: {
      type: String,
      enum: ['confirmed', 'rescheduled', 'cancelled', 'no_response', 'callback_requested', 'error'],
    },
    attemptNumber: { type: Number, default: 1 },
    scheduledAt: { type: Date, required: true },
    startedAt: Date,
    endedAt: Date,
    durationSeconds: Number,
    sessionId: String,
    transcript: String,
    errorMessage: String,
  },
  { timestamps: true, collection: 'campaignCalls' },
);

campaignCallSchema.index({ campaignId: 1, status: 1 });
campaignCallSchema.index({ patientId: 1, campaignId: 1 });
campaignCallSchema.index({ scheduledAt: 1, status: 1 });

export const CampaignCall = model<ICampaignCall>('CampaignCall', campaignCallSchema);
