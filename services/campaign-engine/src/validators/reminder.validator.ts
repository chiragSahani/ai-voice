/**
 * Reminder-specific validators.
 */

import { z } from 'zod';
import { Request } from 'express';

export const ReminderFilterSchema = z.object({
  clinicId: z.string().min(1, 'clinicId is required'),
  from: z.string().datetime({ message: 'from must be a valid ISO datetime' }),
  to: z.string().datetime({ message: 'to must be a valid ISO datetime' }),
});

export type ReminderFilterInput = z.infer<typeof ReminderFilterSchema>;

export function validateReminderFilter(req: Request): ReminderFilterInput {
  return ReminderFilterSchema.parse(req.query);
}
