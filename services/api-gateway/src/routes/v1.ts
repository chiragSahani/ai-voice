/**
 * V1 route registration — wires controllers, validators, and middleware.
 */

import { Router } from 'express';
import { AuthController } from '../controllers/auth.controller';
import { ProxyController } from '../controllers/proxy.controller';
import { validateLogin, validateRefresh } from '../validators/auth.validator';
import { createRateLimiter, authKeyFn, userKeyFn } from '../middleware/rate-limiter';
import { RateLimiterService } from '../services/rate-limiter.service';
import { GatewayConfig } from '../config';

export interface V1RouterDeps {
  authController: AuthController;
  proxyController: ProxyController;
  rateLimiter: RateLimiterService;
  authMiddleware: ReturnType<typeof import('../middleware/auth').createAuthMiddleware>;
  config: GatewayConfig;
}

export function createV1Router(deps: V1RouterDeps): Router {
  const router = Router();
  const { authController, proxyController, rateLimiter, authMiddleware, config } = deps;

  // ---- Auth routes (public, rate-limited) ----
  const authLimiter = createRateLimiter(rateLimiter, config.rateLimits.auth, authKeyFn);

  router.post('/auth/login', authLimiter, validateLogin, authController.login);
  router.post('/auth/refresh', authLimiter, validateRefresh, authController.refresh);
  router.post('/auth/logout', authMiddleware, authController.logout);

  // ---- Proxy routes (authenticated, rate-limited) ----
  const apiLimiter = createRateLimiter(rateLimiter, config.rateLimits.api, userKeyFn);
  const heavyLimiter = createRateLimiter(rateLimiter, config.rateLimits.heavy, userKeyFn);

  // Patient routes
  router.all('/patients', authMiddleware, apiLimiter, proxyController.handle);
  router.all('/patients/*', authMiddleware, apiLimiter, proxyController.handle);

  // Appointment routes
  router.all('/appointments', authMiddleware, apiLimiter, proxyController.handle);
  router.all('/appointments/*', authMiddleware, apiLimiter, proxyController.handle);

  // Campaign routes (bulk operations use heavy limiter)
  router.all('/campaigns', authMiddleware, apiLimiter, proxyController.handle);
  router.all('/campaigns/*/bulk*', authMiddleware, heavyLimiter, proxyController.handle);
  router.all('/campaigns/*', authMiddleware, apiLimiter, proxyController.handle);

  // Session routes
  router.all('/sessions', authMiddleware, apiLimiter, proxyController.handle);
  router.all('/sessions/*', authMiddleware, apiLimiter, proxyController.handle);

  return router;
}
