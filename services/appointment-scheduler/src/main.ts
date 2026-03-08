/**
 * Appointment Scheduler service entry point.
 * Express server with Mongoose ODM, Redis event bus, and background jobs.
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import compression from 'compression';

import {
  createLogger,
  initMetrics,
  metricsMiddleware,
  registry,
} from '../../../shared/typescript/src';
import { errorHandler } from '../../../shared/typescript/src';

import { getConfig } from './config';
import { initMongo, closeMongo } from './clients/mongo.client';
import { initRedis, closeRedis } from './clients/redis.client';
import { createAppHealthRouter } from './health';
import { createV1Router } from './routes/v1';
import { requestIdMiddleware } from './middleware/request-id';
import { auditLoggerMiddleware } from './middleware/audit-logger';
import { getAuthMiddleware } from './middleware/auth';
import { startExpiredSlotCleanup, stopExpiredSlotCleanup } from './jobs/expire-past-slots';
import { startSlotGenerationJob, stopSlotGenerationJob } from './jobs/generate-slots';

async function main(): Promise<void> {
  const config = getConfig();

  // Initialize logger
  const logger = createLogger(config.serviceName, config.logLevel);

  // Initialize metrics
  initMetrics(config.serviceName);

  // Connect to MongoDB
  await initMongo();
  logger.info('MongoDB connected');

  // Connect to Redis
  initRedis();
  logger.info('Redis connected');

  // Create Express app
  const app = express();

  // Global middleware
  app.use(helmet());
  app.use(cors());
  app.use(compression());
  app.use(express.json({ limit: '1mb' }));
  app.use(requestIdMiddleware);
  app.use(metricsMiddleware());
  app.use(auditLoggerMiddleware);

  // Health check (no auth required)
  app.use(createAppHealthRouter());

  // Metrics endpoint (no auth required)
  app.get('/metrics', async (_req, res) => {
    try {
      res.set('Content-Type', registry.contentType);
      res.end(await registry.metrics());
    } catch (err) {
      res.status(500).end();
    }
  });

  // Auth middleware for API routes
  app.use('/api', getAuthMiddleware());

  // API v1 routes
  app.use('/api/v1', createV1Router());

  // Error handler (must be last)
  app.use(errorHandler);

  // Start background jobs
  startExpiredSlotCleanup();
  startSlotGenerationJob();

  // Start server
  const server = app.listen(config.port, () => {
    logger.info({ port: config.port, env: config.nodeEnv }, 'Appointment Scheduler service started');
  });

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    logger.info({ signal }, 'Shutting down...');

    // Stop background jobs
    stopExpiredSlotCleanup();
    stopSlotGenerationJob();

    // Close server
    server.close(() => {
      logger.info('HTTP server closed');
    });

    // Close database connections
    await closeMongo();
    await closeRedis();

    logger.info('Shutdown complete');
    process.exit(0);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  process.on('unhandledRejection', (reason: unknown) => {
    logger.error({ reason }, 'Unhandled rejection');
  });

  process.on('uncaughtException', (err: Error) => {
    logger.fatal({ err }, 'Uncaught exception');
    process.exit(1);
  });
}

main().catch((err) => {
  console.error('Failed to start Appointment Scheduler service:', err);
  process.exit(1);
});
