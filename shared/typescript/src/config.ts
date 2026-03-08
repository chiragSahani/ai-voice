/**
 * Service configuration loader from environment variables.
 */

export interface BaseServiceConfig {
  serviceName: string;
  port: number;
  nodeEnv: string;
  logLevel: string;
}

export interface RedisConfig {
  host: string;
  port: number;
  password: string;
  db: number;
}

export interface MongoConfig {
  uri: string;
  database: string;
}

export interface JwtConfig {
  secret: string;
  issuer: string;
  expiresIn: string;
}

export interface PhiEncryptionConfig {
  key: string;
  algorithm: string;
}

export interface ServiceConfig extends BaseServiceConfig {
  redis: RedisConfig;
  mongo: MongoConfig;
  jwt: JwtConfig;
  phiEncryption: PhiEncryptionConfig;
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

export function loadConfig(serviceName: string): ServiceConfig {
  return {
    serviceName,
    port: envInt('PORT', 3000),
    nodeEnv: env('NODE_ENV', 'development'),
    logLevel: env('LOG_LEVEL', 'info'),
    redis: {
      host: env('REDIS_HOST', 'localhost'),
      port: envInt('REDIS_PORT', 6379),
      password: env('REDIS_PASSWORD', ''),
      db: envInt('REDIS_DB', 0),
    },
    mongo: {
      uri: env('MONGODB_URI', 'mongodb://localhost:27017'),
      database: env('MONGODB_DATABASE', 'voice_agent'),
    },
    jwt: {
      secret: env('JWT_SECRET', 'dev-secret-change-me'),
      issuer: env('JWT_ISSUER', 'voice-agent'),
      expiresIn: env('JWT_EXPIRES_IN', '24h'),
    },
    phiEncryption: {
      key: env('PHI_ENCRYPTION_KEY', '0000000000000000000000000000000000000000000000000000000000000000'),
      algorithm: env('PHI_ENCRYPTION_ALGORITHM', 'aes-256-gcm'),
    },
  };
}
