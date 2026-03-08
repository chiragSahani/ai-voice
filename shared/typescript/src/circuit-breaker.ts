/**
 * Circuit breaker wrapper using opossum.
 */

import CircuitBreaker from 'opossum';
import { getLogger } from './logger';

export interface CircuitBreakerOptions {
  timeout?: number;
  errorThresholdPercentage?: number;
  resetTimeout?: number;
  volumeThreshold?: number;
}

const defaults: CircuitBreakerOptions = {
  timeout: 5000,
  errorThresholdPercentage: 50,
  resetTimeout: 30000,
  volumeThreshold: 5,
};

export function createCircuitBreaker<TInput extends unknown[], TOutput>(
  name: string,
  fn: (...args: TInput) => Promise<TOutput>,
  options: CircuitBreakerOptions = {},
): CircuitBreaker<TInput, TOutput> {
  const logger = getLogger();
  const opts = { ...defaults, ...options, name };

  const breaker = new CircuitBreaker(fn, opts);

  breaker.on('open', () => {
    logger.warn({ circuit: name }, 'Circuit breaker OPENED');
  });

  breaker.on('halfOpen', () => {
    logger.info({ circuit: name }, 'Circuit breaker HALF-OPEN');
  });

  breaker.on('close', () => {
    logger.info({ circuit: name }, 'Circuit breaker CLOSED');
  });

  breaker.on('fallback', () => {
    logger.debug({ circuit: name }, 'Circuit breaker fallback triggered');
  });

  breaker.on('timeout', () => {
    logger.warn({ circuit: name }, 'Circuit breaker timeout');
  });

  return breaker;
}
