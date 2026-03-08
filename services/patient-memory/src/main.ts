/**
 * Patient Memory Service — main entry point.
 *
 * Express server with MongoDB + Redis connections, JWT auth,
 * PHI field-level encryption, and HIPAA-compliant audit logging.
 *
 * Port: 3020
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import compression from 'compression';

import { getConfig } from './config';
import { createLogger } from '../../shared/typescript/src/logger';
import { initMetrics, metricsMiddleware, registry } from '../../shared/typescript/src/metrics';
import { errorHandler } from '../../shared/typescript/src/error-handler';
import { initMongo, shutdownMongo } from './clients/mongo.client';
import { initRedis, shutdownRedis } from './clients/redis.client';
import { createPatientMemoryHealthRouter } from './health';
import { createV1Router } from './routes/v1';
import { requestIdMiddleware } from './middleware/request-id';

async function main(): Promise<void> {
  // Load config (validates required env vars)
  const config = getConfig();

  // Initialize structured logger
  const logger = createLogger(config.serviceName, config.logLevel);
  logger.info({ port: config.port, env: config.nodeEnv }, 'Starting Patient Memory Service');

  // Initialize Prometheus metrics
  initMetrics(config.serviceName);

  // Connect to MongoDB
  await initMongo();
  logger.info('MongoDB connected');

  // Initialize Redis client
  initRedis();
  logger.info('Redis client initialized');

  // Create Express app
  const app = express();

  // --- Global middleware ---
  app.use(helmet());
  app.use(cors());
  app.use(compression());
  app.use(express.json({ limit: '1mb' }));
  app.use(express.urlencoded({ extended: true }));
  app.use(requestIdMiddleware());
  app.use(metricsMiddleware());

  // --- Health check (no auth required) ---
  const healthRouter = createPatientMemoryHealthRouter();
  app.use(healthRouter);

  // --- Prometheus metrics endpoint (no auth required) ---
  app.get('/metrics', async (_req, res) => {
    try {
      res.set('Content-Type', registry.contentType);
      res.end(await registry.metrics());
    } catch (err) {
      res.status(500).end();
    }
  });

  // --- API routes ---
  app.use('/api/v1/patients', createV1Router());

  // --- Error handler (must be last) ---
  app.use(errorHandler);

  // --- Start server ---
  const server = app.listen(config.port, () => {
    logger.info({ port: config.port }, 'Patient Memory Service listening');
  });

  // --- Graceful shutdown ---
  const shutdown = async (signal: string) => {
    logger.info({ signal }, 'Shutdown signal received');

    server.close(async () => {
      logger.info('HTTP server closed');

      try {
        await shutdownMongo();
        logger.info('MongoDB disconnected');
      } catch (err) {
        logger.error({ error: (err as Error).message }, 'Error closing MongoDB');
      }

      try {
        await shutdownRedis();
        logger.info('Redis disconnected');
      } catch (err) {
        logger.error({ error: (err as Error).message }, 'Error closing Redis');
      }

      logger.info('Patient Memory Service stopped');
      process.exit(0);
    });

    // Force shutdown after 10s
    setTimeout(() => {
      logger.error('Forced shutdown after timeout');
      process.exit(1);
    }, 10000);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  process.on('unhandledRejection', (reason) => {
    logger.error({ reason }, 'Unhandled rejection');
  });

  process.on('uncaughtException', (err) => {
    logger.fatal({ error: err.message, stack: err.stack }, 'Uncaught exception');
    process.exit(1);
  });
}

main().catch((err) => {
  console.error('Failed to start Patient Memory Service:', err);
  process.exit(1);
});
