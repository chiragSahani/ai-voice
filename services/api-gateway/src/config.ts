/**
 * API Gateway configuration loaded from environment variables.
 */

export interface UpstreamServiceConfig {
  name: string;
  baseUrl: string;
  healthPath: string;
  timeout: number;
}

export interface RateLimitTier {
  windowMs: number;
  maxRequests: number;
}

export interface GatewayConfig {
  serviceName: string;
  port: number;
  nodeEnv: string;
  logLevel: string;

  jwt: {
    secret: string;
    issuer: string;
    accessExpiresIn: string;
    refreshExpiresIn: string;
  };

  redis: {
    host: string;
    port: number;
    password: string;
    db: number;
  };

  cors: {
    origins: string[];
    methods: string[];
    allowedHeaders: string[];
    credentials: boolean;
  };

  rateLimits: {
    auth: RateLimitTier;
    api: RateLimitTier;
    heavy: RateLimitTier;
  };

  upstreams: {
    appointmentScheduler: UpstreamServiceConfig;
    patientMemory: UpstreamServiceConfig;
    campaignEngine: UpstreamServiceConfig;
    sessionManager: UpstreamServiceConfig;
  };
}

function env(key: string, fallback?: string): string {
  const value = process.env[key] ?? fallback;
  if (value === undefined) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

function envInt(key: string, fallback?: number): number {
  const raw = process.env[key];
  if (raw !== undefined) return parseInt(raw, 10);
  if (fallback !== undefined) return fallback;
  throw new Error(`Missing required environment variable: ${key}`);
}

export function loadGatewayConfig(): GatewayConfig {
  return {
    serviceName: 'api-gateway',
    port: envInt('PORT', 3000),
    nodeEnv: env('NODE_ENV', 'development'),
    logLevel: env('LOG_LEVEL', 'info'),

    jwt: {
      secret: env('JWT_SECRET', 'dev-secret-change-me'),
      issuer: env('JWT_ISSUER', 'voice-agent'),
      accessExpiresIn: env('JWT_ACCESS_EXPIRES_IN', '15m'),
      refreshExpiresIn: env('JWT_REFRESH_EXPIRES_IN', '7d'),
    },

    redis: {
      host: env('REDIS_HOST', 'localhost'),
      port: envInt('REDIS_PORT', 6379),
      password: env('REDIS_PASSWORD', ''),
      db: envInt('REDIS_DB', 0),
    },

    cors: {
      origins: env('CORS_ORIGINS', 'http://localhost:3000,http://localhost:5173').split(','),
      methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
      allowedHeaders: [
        'Content-Type',
        'Authorization',
        'X-Request-ID',
        'X-Clinic-ID',
      ],
      credentials: true,
    },

    rateLimits: {
      auth: {
        windowMs: 60_000,       // 1 minute
        maxRequests: 5,
      },
      api: {
        windowMs: 1_000,        // 1 second
        maxRequests: 30,
      },
      heavy: {
        windowMs: 60_000,       // 1 minute
        maxRequests: 10,
      },
    },

    upstreams: {
      appointmentScheduler: {
        name: 'appointment-scheduler',
        baseUrl: env('UPSTREAM_APPOINTMENT_SCHEDULER', 'http://appointment-scheduler:3010'),
        healthPath: '/health',
        timeout: envInt('UPSTREAM_APPOINTMENT_TIMEOUT', 10000),
      },
      patientMemory: {
        name: 'patient-memory',
        baseUrl: env('UPSTREAM_PATIENT_MEMORY', 'http://patient-memory:3020'),
        healthPath: '/health',
        timeout: envInt('UPSTREAM_PATIENT_TIMEOUT', 10000),
      },
      campaignEngine: {
        name: 'campaign-engine',
        baseUrl: env('UPSTREAM_CAMPAIGN_ENGINE', 'http://campaign-engine:3030'),
        healthPath: '/health',
        timeout: envInt('UPSTREAM_CAMPAIGN_TIMEOUT', 10000),
      },
      sessionManager: {
        name: 'session-manager',
        baseUrl: env('UPSTREAM_SESSION_MANAGER', 'http://session-manager:6380'),
        healthPath: '/health',
        timeout: envInt('UPSTREAM_SESSION_TIMEOUT', 5000),
      },
    },
  };
}
