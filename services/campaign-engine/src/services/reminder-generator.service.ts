/**
 * Reminder Generator Service — generates personalized reminder messages
 * using message templates with variable substitution.
 */

import { getLogger } from '../../../shared/typescript/src';

const logger = getLogger();

export interface ReminderContext {
  patientName?: string;
  clinicName?: string;
  appointmentDate?: string;
  appointmentTime?: string;
  doctorName?: string;
  language: string;
}

// Default templates per language
const DEFAULT_TEMPLATES: Record<string, string> = {
  en: 'Hello {{patientName}}, this is a reminder about your appointment at {{clinicName}} on {{appointmentDate}} at {{appointmentTime}} with {{doctorName}}. Please confirm or reschedule.',
  hi: 'नमस्ते {{patientName}}, यह {{clinicName}} में {{appointmentDate}} को {{appointmentTime}} पर {{doctorName}} के साथ आपकी अपॉइंटमेंट की रिमाइंडर है। कृपया पुष्टि करें या रीशेड्यूल करें।',
  ta: 'வணக்கம் {{patientName}}, {{appointmentDate}} அன்று {{appointmentTime}} மணிக்கு {{clinicName}} இல் {{doctorName}} உடன் உங்கள் சந்திப்பு நினைவூட்டல். தயவுசெய்து உறுதிப்படுத்தவும் அல்லது மீண்டும் திட்டமிடவும்.',
};

export class ReminderGeneratorService {
  /**
   * Generate a reminder message by substituting variables into the template.
   */
  static generateMessage(template: string, context: ReminderContext): string {
    let message = template;

    const variables: Record<string, string> = {
      patientName: context.patientName || 'Patient',
      clinicName: context.clinicName || 'our clinic',
      appointmentDate: context.appointmentDate || '',
      appointmentTime: context.appointmentTime || '',
      doctorName: context.doctorName || 'your doctor',
    };

    for (const [key, value] of Object.entries(variables)) {
      message = message.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value);
    }

    return message;
  }

  /**
   * Get the default template for a given language.
   */
  static getDefaultTemplate(language: string): string {
    return DEFAULT_TEMPLATES[language] || DEFAULT_TEMPLATES.en;
  }

  /**
   * Validate that a template contains required variables.
   */
  static validateTemplate(template: string): { valid: boolean; missingVars: string[] } {
    const requiredVars = ['patientName'];
    const missingVars: string[] = [];

    for (const varName of requiredVars) {
      if (!template.includes(`{{${varName}}}`)) {
        missingVars.push(varName);
      }
    }

    return {
      valid: missingVars.length === 0,
      missingVars,
    };
  }
}
