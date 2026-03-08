/**
 * HTTP client for inter-service communication.
 * Placeholder for calling other services (e.g., appointment-scheduler).
 */

import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

export interface HttpClientOptions {
  baseUrl: string;
  timeoutMs?: number;
}

export class HttpClient {
  private baseUrl: string;
  private timeoutMs: number;

  constructor(options: HttpClientOptions) {
    this.baseUrl = options.baseUrl;
    this.timeoutMs = options.timeoutMs || 5000;
  }

  async get<T>(path: string, headers?: Record<string, string>): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    logger.debug({ url }, 'HTTP GET');

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json', ...headers },
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return (await response.json()) as T;
    } finally {
      clearTimeout(timeout);
    }
  }

  async post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    logger.debug({ url }, 'HTTP POST');

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return (await response.json()) as T;
    } finally {
      clearTimeout(timeout);
    }
  }
}
