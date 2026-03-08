/**
 * Patient Memory Service configuration.
 * Loads all config from environment variables via shared loadConfig.
 */

import { loadConfig, ServiceConfig } from '../../shared/typescript/src/config';

export interface PatientMemoryConfig extends ServiceConfig {
  /** Maximum number of patients returned in a search */
  maxSearchResults: number;
  /** Whether to publish audit events to Redis Streams */
  auditEventsEnabled: boolean;
}

let config: PatientMemoryConfig | null = null;

export function getConfig(): PatientMemoryConfig {
  if (config) return config;

  const base = loadConfig('patient-memory');

  config = {
    ...base,
    port: base.port || 3020,
    maxSearchResults: parseInt(process.env.MAX_SEARCH_RESULTS || '100', 10),
    auditEventsEnabled: process.env.AUDIT_EVENTS_ENABLED !== 'false',
  };

  return config;
}
