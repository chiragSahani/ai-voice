/**
 * Health check router for the API Gateway.
 * Reports Redis connectivity and upstream service reachability.
 */

import { Redis } from 'ioredis';
import { createHealthRouter, redisHealthCheck } from '@shared/health-check';
import type { HealthDependency } from '@shared/health-check';
import { GatewayConfig, UpstreamServiceConfig } from './config';
import http from 'http';

const SERVICE_VERSION = process.env.npm_package_version || '1.0.0';

/**
 * Check whether an upstream service responds to its health endpoint.
 */
function upstreamHealthCheck(upstream: UpstreamServiceConfig): HealthDependency {
  return {
    name: upstream.name,
    check: () =>
      new Promise<boolean>((resolve) => {
        const url = new URL(upstream.healthPath, upstream.baseUrl);

        const req = http.get(
          {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            timeout: 3000,
          },
          (res) => {
            resolve(res.statusCode !== undefined && res.statusCode < 500);
            res.resume(); // drain the response
          },
        );

        req.on('error', () => resolve(false));
        req.on('timeout', () => {
          req.destroy();
          resolve(false);
        });
      }),
  };
}

export function createGatewayHealthRouter(redis: Redis, config: GatewayConfig) {
  const dependencies: HealthDependency[] = [
    redisHealthCheck(redis),
    upstreamHealthCheck(config.upstreams.appointmentScheduler),
    upstreamHealthCheck(config.upstreams.patientMemory),
    upstreamHealthCheck(config.upstreams.campaignEngine),
    upstreamHealthCheck(config.upstreams.sessionManager),
  ];

  return createHealthRouter(SERVICE_VERSION, dependencies);
}
