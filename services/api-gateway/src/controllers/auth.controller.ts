/**
 * Auth controller — login, refresh, and logout endpoints.
 */

import { Request, Response, NextFunction } from 'express';
import { getLogger } from '@shared/logger';
import { AuthService, LoginError } from '../services/auth.service';

const logger = getLogger();

export class AuthController {
  constructor(private readonly authService: AuthService) {}

  /**
   * POST /auth/login
   * Body has already been validated by validateLogin middleware.
   */
  login = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { email, password } = req.body;
      const result = await this.authService.login(email, password);

      res.status(200).json(result);
    } catch (err) {
      if (err instanceof LoginError) {
        res.status(err.statusCode).json({
          error: { code: err.code, message: err.message },
        });
        return;
      }
      next(err);
    }
  };

  /**
   * POST /auth/refresh
   * Body has already been validated by validateRefresh middleware.
   */
  refresh = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { refreshToken } = req.body;
      const result = await this.authService.refreshToken(refreshToken);

      res.status(200).json(result);
    } catch (err) {
      if (err instanceof LoginError) {
        res.status(err.statusCode).json({
          error: { code: err.code, message: err.message },
        });
        return;
      }
      next(err);
    }
  };

  /**
   * POST /auth/logout
   * Requires a valid access token (via authMiddleware).
   */
  logout = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const authHeader = req.headers.authorization;
      const accessToken = authHeader ? authHeader.substring(7) : '';
      const refreshToken = req.body?.refreshToken;

      await this.authService.logout(accessToken, refreshToken);

      res.status(200).json({ message: 'Logged out successfully' });
    } catch (err) {
      logger.error({ error: (err as Error).message }, 'Logout error');
      next(err);
    }
  };
}
