/**
 * Authentication service — JWT token management and credential verification.
 */

import jwt from 'jsonwebtoken';
import bcrypt from 'bcrypt';
import { Redis } from 'ioredis';
import { v4 as uuidv4 } from 'uuid';
import { getLogger } from '@shared/logger';
import { GatewayConfig } from '../config';
import { TokenPair, UserRecord } from '../models/domain';
import { AuthResponse } from '../models/responses';

const BCRYPT_ROUNDS = 12;
const REFRESH_TOKEN_PREFIX = 'gateway:refresh:';
const BLACKLIST_PREFIX = 'gateway:blacklist:';

export class AuthService {
  private readonly logger = getLogger();

  constructor(
    private readonly config: GatewayConfig,
    private readonly redis: Redis,
  ) {}

  /**
   * Authenticate a user by email and password.
   * In production this would query a user store; here we demonstrate the
   * full flow with Redis-backed token management.
   */
  async login(email: string, password: string): Promise<AuthResponse> {
    const user = await this.findUserByEmail(email);

    if (!user) {
      this.logger.warn({ email }, 'Login attempt for unknown user');
      throw new LoginError('Invalid email or password');
    }

    if (!user.active) {
      this.logger.warn({ userId: user.id }, 'Login attempt for inactive user');
      throw new LoginError('Account is deactivated');
    }

    const valid = await bcrypt.compare(password, user.passwordHash);
    if (!valid) {
      this.logger.warn({ userId: user.id }, 'Invalid password');
      throw new LoginError('Invalid email or password');
    }

    const tokens = this.generateTokenPair(user);
    await this.storeRefreshToken(tokens.refreshToken, user.id);

    this.logger.info({ userId: user.id }, 'User logged in');

    return {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresIn: tokens.expiresIn,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        clinicId: user.clinicId,
      },
    };
  }

  /**
   * Issue new token pair from a valid refresh token.
   */
  async refreshToken(token: string): Promise<AuthResponse> {
    // Check the token is not blacklisted
    const blacklisted = await this.redis.get(`${BLACKLIST_PREFIX}${token}`);
    if (blacklisted) {
      throw new LoginError('Token has been revoked');
    }

    // Verify the refresh token signature
    let payload: jwt.JwtPayload;
    try {
      payload = jwt.verify(token, this.config.jwt.secret, {
        issuer: this.config.jwt.issuer,
      }) as jwt.JwtPayload;
    } catch {
      throw new LoginError('Invalid or expired refresh token');
    }

    if (payload.type !== 'refresh') {
      throw new LoginError('Invalid token type');
    }

    // Verify that the stored refresh token matches
    const storedUserId = await this.redis.get(`${REFRESH_TOKEN_PREFIX}${token}`);
    if (!storedUserId || storedUserId !== payload.sub) {
      throw new LoginError('Refresh token not recognized');
    }

    // Look up the user to get current permissions
    const user = await this.findUserById(payload.sub!);
    if (!user || !user.active) {
      throw new LoginError('User not found or deactivated');
    }

    // Rotate: invalidate old refresh token and issue a new pair
    await this.redis.del(`${REFRESH_TOKEN_PREFIX}${token}`);
    const newTokens = this.generateTokenPair(user);
    await this.storeRefreshToken(newTokens.refreshToken, user.id);

    this.logger.info({ userId: user.id }, 'Token refreshed');

    return {
      accessToken: newTokens.accessToken,
      refreshToken: newTokens.refreshToken,
      expiresIn: newTokens.expiresIn,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        clinicId: user.clinicId,
      },
    };
  }

  /**
   * Invalidate the current access token and optional refresh token.
   */
  async logout(accessToken: string, refreshToken?: string): Promise<void> {
    // Blacklist the access token until it expires
    try {
      const decoded = jwt.decode(accessToken) as jwt.JwtPayload | null;
      if (decoded?.exp) {
        const ttl = decoded.exp - Math.floor(Date.now() / 1000);
        if (ttl > 0) {
          await this.redis.setex(`${BLACKLIST_PREFIX}${accessToken}`, ttl, '1');
        }
      }
    } catch {
      // If the token is already invalid, just proceed
    }

    // Invalidate the refresh token
    if (refreshToken) {
      await this.redis.del(`${REFRESH_TOKEN_PREFIX}${refreshToken}`);
      await this.redis.setex(`${BLACKLIST_PREFIX}${refreshToken}`, 7 * 24 * 3600, '1');
    }

    this.logger.info('User logged out');
  }

  /**
   * Validate an access token and check it is not blacklisted.
   */
  async validateToken(token: string): Promise<jwt.JwtPayload> {
    const blacklisted = await this.redis.get(`${BLACKLIST_PREFIX}${token}`);
    if (blacklisted) {
      throw new LoginError('Token has been revoked');
    }

    try {
      return jwt.verify(token, this.config.jwt.secret, {
        issuer: this.config.jwt.issuer,
      }) as jwt.JwtPayload;
    } catch {
      throw new LoginError('Invalid or expired token');
    }
  }

  /**
   * Hash a plaintext password (utility for user creation flows).
   */
  async hashPassword(plaintext: string): Promise<string> {
    return bcrypt.hash(plaintext, BCRYPT_ROUNDS);
  }

  // ---- Private helpers ----

  private generateTokenPair(user: UserRecord): TokenPair {
    const commonPayload = {
      sub: user.id,
      role: user.role,
      clinicId: user.clinicId,
      permissions: user.permissions,
      iss: this.config.jwt.issuer,
    };

    const accessToken = jwt.sign(
      { ...commonPayload, type: 'access' },
      this.config.jwt.secret,
      { expiresIn: this.config.jwt.accessExpiresIn },
    );

    const refreshToken = jwt.sign(
      { ...commonPayload, type: 'refresh', jti: uuidv4() },
      this.config.jwt.secret,
      { expiresIn: this.config.jwt.refreshExpiresIn },
    );

    // Parse the access token to get the exact expiry
    const decoded = jwt.decode(accessToken) as jwt.JwtPayload;
    const expiresIn = decoded.exp! - Math.floor(Date.now() / 1000);

    return { accessToken, refreshToken, expiresIn };
  }

  private async storeRefreshToken(token: string, userId: string): Promise<void> {
    // Store for 7 days (matches refresh token expiry)
    await this.redis.setex(`${REFRESH_TOKEN_PREFIX}${token}`, 7 * 24 * 3600, userId);
  }

  /**
   * Look up a user by email.
   * In a real deployment this queries a user database; here we use Redis
   * as a lightweight user store for the gateway.
   */
  private async findUserByEmail(email: string): Promise<UserRecord | null> {
    const raw = await this.redis.get(`gateway:user:email:${email}`);
    if (!raw) return null;
    return JSON.parse(raw) as UserRecord;
  }

  private async findUserById(id: string): Promise<UserRecord | null> {
    const raw = await this.redis.get(`gateway:user:id:${id}`);
    if (!raw) return null;
    return JSON.parse(raw) as UserRecord;
  }
}

/**
 * Custom error for authentication failures.
 */
export class LoginError extends Error {
  public readonly statusCode = 401;
  public readonly code = 'AUTH_FAILED';

  constructor(message: string) {
    super(message);
    this.name = 'LoginError';
  }
}
