/**
 * Encryption service — thin wrapper around the domain encryption helpers.
 * Provides a service-level interface for encrypting/decrypting individual values.
 */

import { encryptField, decryptField } from '../models/domain';
import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

export class EncryptionService {
  /**
   * Encrypt a single plaintext value using AES-256-GCM.
   */
  encrypt(plaintext: string): string {
    return encryptField(plaintext);
  }

  /**
   * Decrypt a single encrypted value.
   * Returns the original plaintext if the value is not encrypted.
   */
  decrypt(ciphertext: string): string {
    return decryptField(ciphertext);
  }

  /**
   * Encrypt multiple fields in an object. Returns a new object with encrypted values.
   */
  encryptFields<T extends Record<string, any>>(data: T, fields: (keyof T)[]): T {
    const result = { ...data };
    for (const field of fields) {
      const value = result[field];
      if (typeof value === 'string' && value.length > 0) {
        (result as any)[field] = this.encrypt(value);
      }
    }
    return result;
  }

  /**
   * Decrypt multiple fields in an object. Returns a new object with decrypted values.
   */
  decryptFields<T extends Record<string, any>>(data: T, fields: (keyof T)[]): T {
    const result = { ...data };
    for (const field of fields) {
      const value = result[field];
      if (typeof value === 'string' && value.length > 0) {
        try {
          (result as any)[field] = this.decrypt(value);
        } catch (err) {
          logger.warn({ field: String(field) }, 'Failed to decrypt field, returning as-is');
        }
      }
    }
    return result;
  }
}

export const encryptionService = new EncryptionService();
