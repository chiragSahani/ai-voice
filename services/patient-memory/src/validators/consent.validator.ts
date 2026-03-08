/**
 * Consent-related validators.
 */

import { z } from 'zod';
import { Request } from 'express';

export const UpdateConsentSchema = z.object({
  consentVoiceRecording: z.boolean(),
});

export type UpdateConsentInput = z.infer<typeof UpdateConsentSchema>;

export function validateUpdateConsent(req: Request): UpdateConsentInput {
  return UpdateConsentSchema.parse(req.body);
}
