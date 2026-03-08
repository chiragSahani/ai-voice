/**
 * Audit logging service for HIPAA-compliant PHI access tracking.
 *
 * Every access to patient PHI is logged to:
 * 1. MongoDB auditLogs collection (durable)
 * 2. Redis Stream STREAM_AUDIT (real-time alerting/analytics)
 */

import { Schema, model, Document } from 'mongoose';
import { getLogger } from '../../../shared/typescript/src/logger';
import { publishEvent, STREAM_AUDIT } from '../../../shared/typescript/src/events';
import { getRedisClient } from '../../../shared/typescript/src/redis-client';
import { getConfig } from '../config';

const logger = getLogger();

// --- Audit Log Schema ---

export type AuditAction =
  | 'CREATE'
  | 'READ'
  | 'UPDATE'
  | 'DELETE'
  | 'SEARCH'
  | 'DEACTIVATE'
  | 'EXPORT'
  | 'DECRYPT';

export interface IAuditLog extends Document {
  userId: string;
  action: AuditAction;
  resourceType: string;
  resourceId: string;
  clinicId: string;
  details: Record<string, unknown>;
  ipAddress?: string;
  userAgent?: string;
  timestamp: Date;
}

const auditLogSchema = new Schema<IAuditLog>(
  {
    userId: { type: String, required: true, index: true },
    action: {
      type: String,
      required: true,
      enum: ['CREATE', 'READ', 'UPDATE', 'DELETE', 'SEARCH', 'DEACTIVATE', 'EXPORT', 'DECRYPT'],
    },
    resourceType: { type: String, required: true },
    resourceId: { type: String, required: true, index: true },
    clinicId: { type: String, required: true, index: true },
    details: { type: Schema.Types.Mixed, default: {} },
    ipAddress: String,
    userAgent: String,
    timestamp: { type: Date, default: Date.now, index: true },
  },
  {
    collection: 'auditLogs',
    timestamps: false, // we manage our own timestamp field
  },
);

// TTL index: retain audit logs for 7 years (HIPAA requirement)
auditLogSchema.index({ timestamp: 1 }, { expireAfterSeconds: 7 * 365 * 24 * 3600 });
auditLogSchema.index({ userId: 1, timestamp: -1 });
auditLogSchema.index({ resourceId: 1, timestamp: -1 });

export const AuditLogModel = model<IAuditLog>('AuditLog', auditLogSchema);

// --- Audit Service ---

export interface AuditLogInput {
  userId: string;
  action: AuditAction;
  resourceType: string;
  resourceId: string;
  clinicId: string;
  details?: Record<string, unknown>;
  ipAddress?: string;
  userAgent?: string;
}

export class AuditService {
  /**
   * Log a PHI access event. Writes to MongoDB and publishes to Redis Stream.
   * Failures are logged but never thrown — audit must not break the request.
   */
  async logAccess(input: AuditLogInput): Promise<void> {
    const {
      userId,
      action,
      resourceType,
      resourceId,
      clinicId,
      details = {},
      ipAddress,
      userAgent,
    } = input;

    const timestamp = new Date();

    // 1. Write to MongoDB
    try {
      await AuditLogModel.create({
        userId,
        action,
        resourceType,
        resourceId,
        clinicId,
        details,
        ipAddress,
        userAgent,
        timestamp,
      });
    } catch (err) {
      logger.error(
        { error: (err as Error).message, userId, action, resourceId },
        'Failed to write audit log to MongoDB',
      );
    }

    // 2. Publish to Redis Stream for real-time processing
    const config = getConfig();
    if (config.auditEventsEnabled) {
      try {
        const redis = getRedisClient();
        await publishEvent(
          redis,
          STREAM_AUDIT,
          `phi.${action.toLowerCase()}`,
          {
            userId,
            action,
            resourceType,
            resourceId,
            clinicId,
            details,
            ipAddress,
            timestamp: timestamp.toISOString(),
          },
          'patient-memory',
        );
      } catch (err) {
        logger.error(
          { error: (err as Error).message, userId, action, resourceId },
          'Failed to publish audit event to Redis Stream',
        );
      }
    }

    logger.info(
      { userId, action, resourceType, resourceId, clinicId },
      'PHI access logged',
    );
  }
}

export const auditService = new AuditService();
