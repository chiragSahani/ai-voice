/**
 * Summary service — placeholder for patient interaction summary generation.
 * This service will aggregate interaction history for a patient.
 */

import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

export interface PatientSummary {
  patientId: string;
  totalInteractions: number;
  lastInteraction?: string;
  preferredLanguage: string;
  notes: string[];
}

export class SummaryService {
  /**
   * Generate a summary for a patient. Placeholder for future implementation
   * that will aggregate call transcripts and appointment history.
   */
  async getPatientSummary(patientId: string): Promise<PatientSummary> {
    logger.debug({ patientId }, 'Generating patient summary');

    // Future: aggregate from session logs, appointment history, etc.
    return {
      patientId,
      totalInteractions: 0,
      preferredLanguage: 'en',
      notes: [],
    };
  }
}

export const summaryService = new SummaryService();
