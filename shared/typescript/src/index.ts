/**
 * @voice-agent/shared — barrel export for all shared TypeScript modules.
 */

// Config
export { loadConfig } from './config';
export type { BaseServiceConfig, RedisConfig, MongoConfig, JwtConfig, PhiEncryptionConfig, ServiceConfig } from './config';

// Logger
export { createLogger, getLogger } from './logger';

// Tracing
export { setupTracing, shutdownTracing } from './tracing';

// Metrics
export { registry, httpRequestDuration, httpRequestsTotal, activeConnections, errorsTotal, initMetrics, metricsMiddleware } from './metrics';

// Circuit Breaker
export { createCircuitBreaker } from './circuit-breaker';
export type { CircuitBreakerOptions } from './circuit-breaker';

// Redis
export { getRedisClient, closeRedis, pingRedis } from './redis-client';

// MongoDB
export { connectMongo, closeMongo, pingMongo } from './mongo-client';

// Auth Middleware
export { authMiddleware, requireRole, requirePermission } from './auth-middleware';
export type { JwtPayload } from './auth-middleware';

// Error Handler
export { errorHandler, AppError, ValidationError, NotFoundError, ConflictError, ServiceUnavailableError } from './error-handler';

// Health Check
export { createHealthRouter, mongoHealthCheck, redisHealthCheck } from './health-check';
export type { HealthDependency, HealthStatus } from './health-check';

// Events
export { publishEvent, createConsumerGroup, consumeEvents, ackEvent, STREAM_APPOINTMENTS, STREAM_SESSIONS, STREAM_CAMPAIGNS, STREAM_AUDIT, STREAM_ALERTS, STREAM_ANALYTICS } from './events';
export type { EventEnvelope } from './events';

// Types
export type { IPatient, PatientAddress, EmergencyContact } from './types/patient';
export { Patient } from './types/patient';

export type { IDoctor, DoctorScheduleSlot, DoctorOverride, IAppointmentSlot, SlotStatus, IAppointment, AppointmentStatus } from './types/appointment';
export { Doctor, AppointmentSlot, Appointment } from './types/appointment';

export type { ICampaign, CampaignStatus, CampaignType, CampaignSchedule, ICampaignCall, CallStatus, CallOutcome } from './types/campaign';
export { Campaign, CampaignCall } from './types/campaign';

export type { EventTypeMap, EventType, AppointmentBookedEvent, AppointmentCancelledEvent, AppointmentRescheduledEvent, SessionStartedEvent, SessionEndedEvent, CampaignStartedEvent, CampaignCallCompletedEvent, AuditEvent, AlertEvent } from './types/events';

export type { ApiError, ApiResponse, ApiErrorResponse, PaginationQuery, PaginatedResult } from './types/api-responses';
export { paginate, successResponse, errorResponse } from './types/api-responses';
