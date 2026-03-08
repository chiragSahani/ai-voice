/**
 * Campaign Engine configuration from environment variables.
 */

import { loadConfig, ServiceConfig } from '../../shared/typescript/src';

export interface CampaignEngineConfig extends ServiceConfig {
  audioGatewayWsUrl: string;
  maxConcurrentCalls: number;
  callWindow: {
    defaultStart: string;
    defaultEnd: string;
    defaultTimezone: string;
  };
  bullmq: {
    defaultJobTimeout: number;
    callRetryDelay: number;
    maxRetriesPerCall: number;
  };
}

function env(key: string, fallback?: string): string {
  const value = process.env[key] ?? fallback;
  if (value === undefined) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

function envInt(key: string, fallback?: number): number {
  const raw = process.env[key];
  if (raw !== undefined) return parseInt(raw, 10);
  if (fallback !== undefined) return fallback;
  throw new Error(`Missing required environment variable: ${key}`);
}

export function getConfig(): CampaignEngineConfig {
  const base = loadConfig('campaign-engine');

  return {
    ...base,
    port: envInt('PORT', 3030),
    audioGatewayWsUrl: env('AUDIO_GATEWAY_WS_URL', 'ws://localhost:8080/ws/outbound'),
    maxConcurrentCalls: envInt('MAX_CONCURRENT_CALLS', 10),
    callWindow: {
      defaultStart: env('CALL_WINDOW_START', '09:00'),
      defaultEnd: env('CALL_WINDOW_END', '18:00'),
      defaultTimezone: env('CALL_WINDOW_TIMEZONE', 'Asia/Kolkata'),
    },
    bullmq: {
      defaultJobTimeout: envInt('BULLMQ_JOB_TIMEOUT_MS', 300000), // 5 minutes
      callRetryDelay: envInt('BULLMQ_CALL_RETRY_DELAY_MS', 60000), // 1 minute
      maxRetriesPerCall: envInt('BULLMQ_MAX_RETRIES', 3),
    },
  };
}

export const config = getConfig();
