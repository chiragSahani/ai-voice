/**
 * Shared HTTP client configuration.
 * Provides sensible defaults for outbound HTTP connections to upstream services.
 */

import http from 'http';
import https from 'https';

/**
 * Keep-alive agents for connection reuse across upstream requests.
 */
export const httpAgent = new http.Agent({
  keepAlive: true,
  keepAliveMsecs: 30_000,
  maxSockets: 100,
  maxFreeSockets: 20,
});

export const httpsAgent = new https.Agent({
  keepAlive: true,
  keepAliveMsecs: 30_000,
  maxSockets: 100,
  maxFreeSockets: 20,
});

/**
 * Destroy agents on shutdown.
 */
export function destroyAgents(): void {
  httpAgent.destroy();
  httpsAgent.destroy();
}
