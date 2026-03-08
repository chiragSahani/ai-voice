/**
 * Campaign Engine — Bootstrap and Express server initialization.
 * Starts HTTP server, BullMQ workers, and connects to databases.
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import compression from 'compression';

import {
  createLogger,
  connectMongo,
  getRedisClient,
  initMetrics,
  metricsMiddleware,
  registry,
  errorHandler,
} from '../../shared/typescript/src';

import { config } from './config';
import { v1Router } from './routes';
import { createCampaignHealthRouter } from './health';
import { requestIdMiddleware } from './middleware/request-id';
import { auditLoggerMiddleware } from './middleware/audit-logger';
import { startCallWorker, stopCallWorker } from './workers/call-worker';
import { startRetryWorker, stopRetryWorker } from './workers/retry-worker';
import { closeCallQueue } from './queues/call-queue';
import { closeRetryQueue } from './queues/retry-queue';

// Initialize logger
const logger = createLogger(config.serviceName, config.logLevel);

async function bootstrap(): Promise<void> {
  logger.info({ port: config.port, env: config.nodeEnv }, 'Starting campaign engine...');

  // Connect to MongoDB
  await connectMongo(config.mongo.uri, config.mongo.database);
  logger.info('MongoDB connected');

  // Connect to Redis
  const redis = getRedisClient({
    host: config.redis.host,
    port: config.redis.port,
    password: config.redis.password || undefined,
    db: config.redis.db,
  });
  logger.info('Redis connected');

  // Initialize metrics
  initMetrics(config.serviceName);

  // Start BullMQ workers
  startCallWorker();
  startRetryWorker();
  logger.info('BullMQ workers started');

  // Create Express app
  const app = express();

  // Global middleware
  app.use(helmet());
  app.use(cors());
  app.use(compression());
  app.use(express.json({ limit: '1mb' }));
  app.use(express.urlencoded({ extended: true }));
  app.use(requestIdMiddleware);
  app.use(metricsMiddleware());
  app.use(auditLoggerMiddleware);

  // Health check (unauthenticated)
  app.use(createCampaignHealthRouter(redis));

  // Metrics endpoint (unauthenticated)
  app.get('/metrics', async (_req, res) => {
    try {
      res.set('Content-Type', registry.contentType);
      res.end(await registry.metrics());
    } catch (err) {
      res.status(500).end();
    }
  });

  // API routes
  app.use('/api/v1', v1Router);

  // Error handler (must be last)
  app.use(errorHandler);

  // Start HTTP server
  const server = app.listen(config.port, () => {
    logger.info({ port: config.port }, 'Campaign engine listening');
  });

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    logger.info({ signal }, 'Shutdown signal received');

    server.close(async () => {
      logger.info('HTTP server closed');

      try {
        // Stop workers first
        await stopCallWorker();
        await stopRetryWorker();

        // Close queues
        await closeCallQueue();
        await closeRetryQueue();

        logger.info('Graceful shutdown complete');
        process.exit(0);
      } catch (err: any) {
        logger.error({ error: err.message }, 'Error during shutdown');
        process.exit(1);
      }
    });

    // Force exit after 30s
    setTimeout(() => {
      logger.error('Forced shutdown after timeout');
      process.exit(1);
    }, 30000);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  process.on('unhandledRejection', (reason: any) => {
    logger.error({ error: reason?.message || reason }, 'Unhandled rejection');
  });

  process.on('uncaughtException', (err) => {
    logger.error({ error: err.message, stack: err.stack }, 'Uncaught exception');
    process.exit(1);
  });
}

bootstrap().catch((err) => {
  logger.error({ error: err.message, stack: err.stack }, 'Failed to start campaign engine');
  process.exit(1);
});
