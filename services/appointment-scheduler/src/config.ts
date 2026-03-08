/**
 * Appointment Scheduler service configuration.
 */

import { loadConfig, ServiceConfig } from '../../../shared/typescript/src';

export interface AppointmentSchedulerConfig extends ServiceConfig {
  slotHoldDurationMinutes: number;
  maxBookingRetries: number;
  retryBaseDelayMs: number;
  slotGenerationLookaheadDays: number;
  expiredSlotCleanupIntervalMs: number;
}

let config: AppointmentSchedulerConfig | null = null;

function envInt(key: string, fallback: number): number {
  const raw = process.env[key];
  return raw !== undefined ? parseInt(raw, 10) : fallback;
}

export function getConfig(): AppointmentSchedulerConfig {
  if (config) return config;

  const base = loadConfig('appointment-scheduler');

  config = {
    ...base,
    port: envInt('PORT', 3010),
    slotHoldDurationMinutes: envInt('SLOT_HOLD_DURATION_MINUTES', 5),
    maxBookingRetries: envInt('MAX_BOOKING_RETRIES', 3),
    retryBaseDelayMs: envInt('RETRY_BASE_DELAY_MS', 100),
    slotGenerationLookaheadDays: envInt('SLOT_GENERATION_LOOKAHEAD_DAYS', 30),
    expiredSlotCleanupIntervalMs: envInt('EXPIRED_SLOT_CLEANUP_INTERVAL_MS', 60000),
  };

  return config;
}
