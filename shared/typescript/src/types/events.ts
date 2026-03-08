/**
 * Event type definitions for Redis Streams inter-service communication.
 */

// --- Appointment Events ---

export interface AppointmentBookedEvent {
  appointmentId: string;
  patientId: string;
  doctorId: string;
  clinicId: string;
  date: string;
  startTime: string;
  endTime: string;
  bookedVia: 'voice' | 'web' | 'phone' | 'walk_in';
  sessionId?: string;
}

export interface AppointmentCancelledEvent {
  appointmentId: string;
  patientId: string;
  doctorId: string;
  clinicId: string;
  reason?: string;
  cancelledBy: string;
}

export interface AppointmentRescheduledEvent {
  appointmentId: string;
  patientId: string;
  oldDate: string;
  oldStartTime: string;
  newDate: string;
  newStartTime: string;
  newEndTime: string;
  newSlotId: string;
}

// --- Session Events ---

export interface SessionStartedEvent {
  sessionId: string;
  patientId?: string;
  language: string;
  channel: 'voice' | 'text';
}

export interface SessionEndedEvent {
  sessionId: string;
  patientId?: string;
  durationSeconds: number;
  turnCount: number;
  outcome?: string;
}

// --- Campaign Events ---

export interface CampaignStartedEvent {
  campaignId: string;
  clinicId: string;
  type: string;
  totalCalls: number;
}

export interface CampaignCallCompletedEvent {
  campaignId: string;
  callId: string;
  patientId: string;
  outcome: string;
  durationSeconds: number;
}

// --- Audit Events ---

export interface AuditEvent {
  action: string;
  resourceType: string;
  resourceId: string;
  userId: string;
  clinicId: string;
  details?: Record<string, unknown>;
  ipAddress?: string;
}

// --- Alert Events ---

export interface AlertEvent {
  severity: 'info' | 'warning' | 'critical';
  source: string;
  message: string;
  details?: Record<string, unknown>;
}

// --- Event Type Map ---

export type EventTypeMap = {
  'appointment.booked': AppointmentBookedEvent;
  'appointment.cancelled': AppointmentCancelledEvent;
  'appointment.rescheduled': AppointmentRescheduledEvent;
  'session.started': SessionStartedEvent;
  'session.ended': SessionEndedEvent;
  'campaign.started': CampaignStartedEvent;
  'campaign.call.completed': CampaignCallCompletedEvent;
  'audit.action': AuditEvent;
  'alert.triggered': AlertEvent;
};

export type EventType = keyof EventTypeMap;
