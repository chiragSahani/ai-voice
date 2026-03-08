/**
 * API Gateway — main entry point.
 *
 * Bootstraps Express with all middleware, routes, health checks,
 * and metrics, then starts listening on the configured port.
 */

import express from 'express';
import helmet from 'helmet';
import compression from 'compression';
import { createLogger, getLogger } from '@shared/logger';
import { initMetrics, metricsMiddleware, registry } from '@shared/metrics';
import { loadGatewayConfig } from './config';
import { initRedis, closeRedis } from './clients/redis.client';
import { destroyAgents } from './clients/http.client';
import { requestIdMiddleware } from './middleware/request-id';
import { createCorsMiddleware } from './middleware/cors';
import { auditLoggerMiddleware } from './middleware/audit-logger';
import { gatewayErrorHandler } from './middleware/error-handler';
import { createAuthMiddleware } from './middleware/auth';
import { createGatewayHealthRouter } from './health';
import { createV1Router } from './routes/v1';
import { AuthService } from './services/auth.service';
import { ProxyService } from './services/proxy.service';
import { RateLimiterService } from './services/rate-limiter.service';
import { AuthController } from './controllers/auth.controller';
import { ProxyController } from './controllers/proxy.controller';

async function main(): Promise<void> {
  // ---- Configuration ----
  const config = loadGatewayConfig();

  // ---- Logger ----
  createLogger(config.serviceName, config.logLevel);
  const logger = getLogger();
  logger.info({ port: config.port, env: config.nodeEnv }, 'Starting API Gateway');

  // ---- Metrics ----
  initMetrics(config.serviceName);

  // ---- Redis ----
  const redis = initRedis(config);

  // ---- Services ----
  const authService = new AuthService(config, redis);
  const proxyService = new ProxyService();
  const rateLimiterService = new RateLimiterService(redis);

  // ---- Controllers ----
  const authController = new AuthController(authService);
  const proxyController = new ProxyController(proxyService, config);

  // ---- Express app ----
  const app = express();

  // Trust proxy for X-Forwarded-For headers (load balancer / k8s)
  app.set('trust proxy', 1);

  // ---- Global middleware (order matters) ----
  app.use(requestIdMiddleware);
  app.use(createCorsMiddleware(config));
  app.use(helmet({
    contentSecurityPolicy: false, // Let downstream services set their own CSP
  }));
  app.use(compression());
  app.use(express.json({ limit: '1mb' }));
  app.use(express.urlencoded({ extended: true, limit: '1mb' }));
  app.use(metricsMiddleware());
  app.use(auditLoggerMiddleware);

  // ---- Health & metrics (unauthenticated) ----
  app.use(createGatewayHealthRouter(redis, config));

  app.get('/metrics', async (_req, res) => {
    try {
      res.set('Content-Type', registry.contentType);
      res.end(await registry.metrics());
    } catch (err) {
      res.status(500).end();
    }
  });

  // ---- API v1 routes ----
  const authMiddleware = createAuthMiddleware(config);

  const v1Router = createV1Router({
    authController,
    proxyController,
    rateLimiter: rateLimiterService,
    authMiddleware,
    config,
  });

  app.use('/api/v1', v1Router);

  // ---- 404 catch-all ----
  app.use((_req, res) => {
    res.status(404).json({
      error: {
        code: 'NOT_FOUND',
        message: 'The requested endpoint does not exist',
      },
    });
  });

  // ---- Error handler (must be last) ----
  app.use(gatewayErrorHandler);

  // ---- Start server ----
  const server = app.listen(config.port, () => {
    logger.info({ port: config.port }, 'API Gateway listening');
  });

  // ---- Graceful shutdown ----
  const shutdown = async (signal: string) => {
    logger.info({ signal }, 'Shutdown signal received');

    server.close(async () => {
      logger.info('HTTP server closed');

      try {
        await closeRedis();
        destroyAgents();
        logger.info('All connections closed — exiting');
      } catch (err) {
        logger.error({ error: (err as Error).message }, 'Error during cleanup');
      }

      process.exit(0);
    });

    // Force exit if graceful shutdown takes too long
    setTimeout(() => {
      logger.error('Forced shutdown after timeout');
      process.exit(1);
    }, 15_000).unref();
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  process.on('unhandledRejection', (reason) => {
    logger.error({ reason }, 'Unhandled promise rejection');
  });

  process.on('uncaughtException', (err) => {
    logger.fatal({ error: err.message, stack: err.stack }, 'Uncaught exception — shutting down');
    process.exit(1);
  });
}

main().catch((err) => {
  console.error('Fatal startup error:', err);
  process.exit(1);
});
