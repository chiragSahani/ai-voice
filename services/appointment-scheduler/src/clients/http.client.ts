/**
 * HTTP client for inter-service communication.
 * Uses native fetch (Node 18+) with circuit breaker pattern.
 */

import { createCircuitBreaker, getLogger } from '../../../../shared/typescript/src';

const logger = getLogger();

async function fetchPatient(patientId: string): Promise<boolean> {
  const patientServiceUrl = process.env.PATIENT_MEMORY_URL || 'http://localhost:3020';
  const response = await fetch(`${patientServiceUrl}/api/v1/patients/${patientId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(5000),
  });
  return response.ok;
}

const patientServiceBreaker = createCircuitBreaker(
  'patient-memory',
  fetchPatient,
  {
    timeout: 5000,
    errorThresholdPercentage: 50,
    resetTimeout: 30000,
  },
);

/**
 * Verify a patient exists in the patient-memory service.
 */
export async function verifyPatientExists(patientId: string): Promise<boolean> {
  try {
    return await patientServiceBreaker.fire(patientId);
  } catch (err) {
    logger.warn({ err, patientId }, 'Failed to verify patient existence, allowing booking');
    // Fail open: if patient service is down, allow the booking
    return true;
  }
}
