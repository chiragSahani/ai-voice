/**
 * Structured JSON logging with Pino.
 */

import pino, { Logger } from 'pino';

let logger: Logger | null = null;

export function createLogger(serviceName: string, level: string = 'info'): Logger {
  logger = pino({
    name: serviceName,
    level,
    timestamp: pino.stdTimeFunctions.isoTime,
    formatters: {
      level: (label: string) => ({ level: label }),
      bindings: (bindings) => ({
        service: bindings.name,
        pid: bindings.pid,
        hostname: bindings.hostname,
      }),
    },
    ...(process.env.NODE_ENV === 'development'
      ? {
          transport: {
            target: 'pino-pretty',
            options: { colorize: true, translateTime: 'SYS:HH:MM:ss.l' },
          },
        }
      : {}),
  });

  return logger;
}

export function getLogger(): Logger {
  if (!logger) {
    logger = createLogger('default');
  }
  return logger;
}
