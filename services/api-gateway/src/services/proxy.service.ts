/**
 * Proxy service — forwards requests to upstream micro-services with
 * circuit breaker protection, timeout handling, and header propagation.
 */

import http from 'http';
import https from 'https';
import { URL } from 'url';
import { getLogger } from '@shared/logger';
import { createCircuitBreaker } from '@shared/circuit-breaker';
import { UpstreamService } from '../models/domain';
import CircuitBreaker from 'opossum';

const logger = getLogger();

/** Shape returned from an upstream call. */
export interface ProxyResponse {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  body: Buffer;
}

/** Options that travel with every proxied request. */
export interface ProxyRequestOptions {
  method: string;
  path: string;
  body?: Buffer | string;
  headers: Record<string, string | undefined>;
  requestId?: string;
}

export class ProxyService {
  /** One circuit breaker per upstream service name. */
  private readonly breakers = new Map<string, CircuitBreaker<[UpstreamService, ProxyRequestOptions], ProxyResponse>>();

  constructor() {}

  /**
   * Forward an HTTP request to the given upstream service.
   * The call is wrapped in a per-upstream circuit breaker.
   */
  async proxyRequest(
    upstream: UpstreamService,
    options: ProxyRequestOptions,
  ): Promise<ProxyResponse> {
    const breaker = this.getBreaker(upstream);

    try {
      return await breaker.fire(upstream, options);
    } catch (err: any) {
      if (err.code === 'EOPENBREAKER') {
        logger.warn({ upstream: upstream.name }, 'Circuit open — upstream unavailable');
        return {
          status: 503,
          headers: {},
          body: Buffer.from(JSON.stringify({
            error: {
              code: 'SERVICE_UNAVAILABLE',
              message: `Upstream service ${upstream.name} is temporarily unavailable`,
              upstream: upstream.name,
            },
          })),
        };
      }
      throw err;
    }
  }

  // ---- Private helpers ----

  private getBreaker(upstream: UpstreamService) {
    let breaker = this.breakers.get(upstream.name);
    if (breaker) return breaker;

    breaker = createCircuitBreaker<[UpstreamService, ProxyRequestOptions], ProxyResponse>(
      `proxy:${upstream.name}`,
      this.doRequest.bind(this),
      {
        timeout: upstream.timeout,
        errorThresholdPercentage: 50,
        resetTimeout: 30_000,
        volumeThreshold: 5,
      },
    );

    this.breakers.set(upstream.name, breaker);
    return breaker;
  }

  /**
   * Raw HTTP request to the upstream — no circuit breaker.
   */
  private doRequest(
    upstream: UpstreamService,
    options: ProxyRequestOptions,
  ): Promise<ProxyResponse> {
    return new Promise<ProxyResponse>((resolve, reject) => {
      const url = new URL(options.path, upstream.baseUrl);
      const isHttps = url.protocol === 'https:';
      const transport = isHttps ? https : http;

      const outgoingHeaders: Record<string, string> = {
        'content-type': 'application/json',
      };

      // Propagate select headers
      if (options.headers['authorization']) {
        outgoingHeaders['authorization'] = options.headers['authorization'];
      }
      if (options.requestId) {
        outgoingHeaders['x-request-id'] = options.requestId;
      }
      if (options.headers['x-clinic-id']) {
        outgoingHeaders['x-clinic-id'] = options.headers['x-clinic-id'];
      }
      if (options.headers['accept']) {
        outgoingHeaders['accept'] = options.headers['accept'];
      }
      if (options.headers['accept-language']) {
        outgoingHeaders['accept-language'] = options.headers['accept-language'];
      }

      // Set content-length when there is a body
      const bodyBuf = options.body
        ? (typeof options.body === 'string' ? Buffer.from(options.body) : options.body)
        : undefined;
      if (bodyBuf) {
        outgoingHeaders['content-length'] = bodyBuf.length.toString();
      }

      const reqOpts: http.RequestOptions = {
        hostname: url.hostname,
        port: url.port || (isHttps ? 443 : 80),
        path: url.pathname + url.search,
        method: options.method,
        headers: outgoingHeaders,
        timeout: upstream.timeout,
      };

      const req = transport.request(reqOpts, (res) => {
        const chunks: Buffer[] = [];

        res.on('data', (chunk: Buffer) => {
          chunks.push(chunk);
        });

        res.on('end', () => {
          const body = Buffer.concat(chunks);
          const responseHeaders: Record<string, string | string[] | undefined> = {};
          for (const [key, value] of Object.entries(res.headers)) {
            responseHeaders[key] = value;
          }

          resolve({
            status: res.statusCode ?? 502,
            headers: responseHeaders,
            body,
          });
        });
      });

      req.on('error', (err) => {
        logger.error({ upstream: upstream.name, error: err.message }, 'Upstream request error');
        reject(err);
      });

      req.on('timeout', () => {
        req.destroy();
        logger.warn({ upstream: upstream.name, timeout: upstream.timeout }, 'Upstream request timed out');
        reject(new Error(`Upstream ${upstream.name} timed out after ${upstream.timeout}ms`));
      });

      if (bodyBuf) {
        req.write(bodyBuf);
      }

      req.end();
    });
  }
}
