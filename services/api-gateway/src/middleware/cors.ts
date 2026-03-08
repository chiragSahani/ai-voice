/**
 * CORS configuration middleware.
 * Wraps the cors package with gateway-specific defaults.
 */

import cors from 'cors';
import { GatewayConfig } from '../config';

export function createCorsMiddleware(config: GatewayConfig) {
  return cors({
    origin: (origin, callback) => {
      // Allow requests with no origin (server-to-server, curl, etc.)
      if (!origin) {
        callback(null, true);
        return;
      }

      if (
        config.cors.origins.includes('*') ||
        config.cors.origins.includes(origin)
      ) {
        callback(null, true);
      } else {
        callback(new Error(`Origin ${origin} not allowed by CORS policy`));
      }
    },
    methods: config.cors.methods,
    allowedHeaders: config.cors.allowedHeaders,
    credentials: config.cors.credentials,
    exposedHeaders: ['X-Request-ID', 'X-Total-Count', 'X-Page', 'X-Per-Page'],
    maxAge: 86400, // Preflight cache: 24 hours
  });
}
