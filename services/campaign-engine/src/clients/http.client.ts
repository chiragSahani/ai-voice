/**
 * HTTP client with circuit breaker for external service calls.
 */

import CircuitBreaker from 'opossum';
import { createCircuitBreaker, getLogger } from '../../../shared/typescript/src';

const logger = getLogger();

export interface HttpClientOptions {
  baseUrl: string;
  timeout?: number;
  headers?: Record<string, string>;
}

export class HttpClient {
  private baseUrl: string;
  private timeout: number;
  private headers: Record<string, string>;
  private breaker: CircuitBreaker<[string, RequestInit], Response>;

  constructor(options: HttpClientOptions) {
    this.baseUrl = options.baseUrl;
    this.timeout = options.timeout || 5000;
    this.headers = options.headers || {};

    const fetchFn = async (url: string, init: RequestInit): Promise<Response> => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeout);

      try {
        const response = await fetch(url, { ...init, signal: controller.signal });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response;
      } finally {
        clearTimeout(timeoutId);
      }
    };

    this.breaker = createCircuitBreaker(
      `http-${options.baseUrl}`,
      fetchFn,
      {
        timeout: this.timeout,
        errorThresholdPercentage: 50,
        resetTimeout: 30000,
        volumeThreshold: 5,
      },
    );
  }

  async get<T>(path: string, headers?: Record<string, string>): Promise<T> {
    const response = await this.breaker.fire(`${this.baseUrl}${path}`, {
      method: 'GET',
      headers: { ...this.headers, ...headers },
    });

    return (await response.json()) as T;
  }

  async post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
    const response = await this.breaker.fire(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this.headers,
        ...headers,
      },
      body: JSON.stringify(body),
    });

    return (await response.json()) as T;
  }
}
