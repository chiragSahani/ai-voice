/**
 * Proxy controller — routes API requests to the appropriate upstream service.
 *
 * Route mapping:
 *   /api/v1/patients/*      -> patient-memory:3020
 *   /api/v1/appointments/*   -> appointment-scheduler:3010
 *   /api/v1/campaigns/*      -> campaign-engine:3030
 *   /api/v1/sessions/*       -> session-manager:6380
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger } from '@shared/logger';
import { ProxyService } from '../services/proxy.service';
import { UpstreamService } from '../models/domain';
import { GatewayConfig } from '../config';

const logger = getLogger();

export class ProxyController {
  private readonly routeMap: Map<string, UpstreamService>;

  constructor(
    private readonly proxyService: ProxyService,
    config: GatewayConfig,
  ) {
    this.routeMap = new Map<string, UpstreamService>([
      ['patients', config.upstreams.patientMemory],
      ['appointments', config.upstreams.appointmentScheduler],
      ['campaigns', config.upstreams.campaignEngine],
      ['sessions', config.upstreams.sessionManager],
    ]);
  }

  /**
   * Generic proxy handler — resolves the upstream from the URL segment
   * and forwards the full request.
   */
  handle = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      // Extract the resource segment: /api/v1/{resource}/...
      const segments = req.path.split('/').filter(Boolean);
      // segments: ['api', 'v1', 'patients', ...]
      const resourceSegment = segments[2];

      const upstream = this.routeMap.get(resourceSegment);
      if (!upstream) {
        res.status(404).json({
          error: {
            code: 'NOT_FOUND',
            message: `No upstream service registered for /${resourceSegment}`,
            requestId: (req as any).requestId,
          },
        });
        return;
      }

      // Build the upstream path: strip /api/v1 prefix, forward everything after
      const upstreamPath = '/' + segments.slice(2).join('/');
      const queryString = req.url.includes('?') ? req.url.substring(req.url.indexOf('?')) : '';
      const fullPath = upstreamPath + queryString;

      logger.debug(
        { upstream: upstream.name, method: req.method, path: fullPath, requestId: (req as any).requestId },
        'Proxying request',
      );

      // Collect the raw body
      let body: Buffer | undefined;
      if (req.body && Object.keys(req.body).length > 0) {
        body = Buffer.from(JSON.stringify(req.body));
      }

      const proxyRes = await this.proxyService.proxyRequest(upstream, {
        method: req.method,
        path: fullPath,
        body,
        headers: {
          authorization: req.headers.authorization,
          'x-request-id': (req as any).requestId,
          'x-clinic-id': req.headers['x-clinic-id'] as string | undefined,
          accept: req.headers.accept,
          'accept-language': req.headers['accept-language'],
          'content-type': req.headers['content-type'],
        },
        requestId: (req as any).requestId,
      });

      // Forward response headers selectively
      const forwardHeaders = [
        'content-type',
        'x-request-id',
        'x-total-count',
        'x-page',
        'x-per-page',
        'cache-control',
        'etag',
        'last-modified',
      ];
      for (const header of forwardHeaders) {
        const value = proxyRes.headers[header];
        if (value) {
          res.setHeader(header, value);
        }
      }

      res.status(proxyRes.status).send(proxyRes.body);
    } catch (err) {
      logger.error(
        { error: (err as Error).message, requestId: (req as any).requestId },
        'Proxy error',
      );
      next(err);
    }
  };
}
