/**
 * Reminder Controller — Express request handlers for reminder-specific operations.
 */

import { Request, Response, NextFunction } from 'express';
import { successResponse } from '../../../shared/typescript/src';
import { ReminderGeneratorService } from '../services/reminder-generator.service';

/**
 * POST /api/v1/reminders/preview — Preview a generated reminder message.
 */
export async function previewReminder(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const { template, language, context } = req.body;

    const actualTemplate = template || ReminderGeneratorService.getDefaultTemplate(language || 'en');
    const message = ReminderGeneratorService.generateMessage(actualTemplate, {
      ...context,
      language: language || 'en',
    });

    const validation = ReminderGeneratorService.validateTemplate(actualTemplate);

    res.json(successResponse({
      message,
      template: actualTemplate,
      validation,
    }));
  } catch (err) {
    next(err);
  }
}

/**
 * GET /api/v1/reminders/templates — Get available reminder templates.
 */
export async function getTemplates(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    const templates = {
      en: ReminderGeneratorService.getDefaultTemplate('en'),
      hi: ReminderGeneratorService.getDefaultTemplate('hi'),
      ta: ReminderGeneratorService.getDefaultTemplate('ta'),
    };

    res.json(successResponse(templates));
  } catch (err) {
    next(err);
  }
}
