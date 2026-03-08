# ---- Build Stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy shared dependencies
COPY shared/typescript/ shared/typescript/
RUN cd shared/typescript && npm install --ignore-scripts

# Copy service dependencies
COPY services/api-gateway/package.json services/api-gateway/
RUN cd services/api-gateway && npm install --ignore-scripts

# Copy service source
COPY services/api-gateway/ services/api-gateway/

# Build shared then service.
# --rootDir /app makes tsc preserve the monorepo directory structure in dist/:
#   dist/services/api-gateway/src/...  (compiled service code)
#   dist/shared/typescript/src/...     (compiled shared code)
# Relative require() paths in the compiled JS resolve correctly within this tree.
RUN cd shared/typescript && npx tsc --skipLibCheck || true
RUN cd services/api-gateway && npx tsc --skipLibCheck --rootDir /app || true

# --- Production stage ---
FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# Copy the full compiled dist/ tree (includes both service and shared code)
COPY --from=builder /app/services/api-gateway/dist/ dist/

# The api-gateway source uses @shared/* path aliases (tsconfig paths).
# tsc does NOT rewrite these in the compiled JS output, so we create a
# symlink: node_modules/@shared -> dist/shared/typescript/src
# Node.js resolves require("@shared/logger") by walking up to find
# node_modules/@shared, which points to the compiled shared JS.
RUN mkdir -p dist/node_modules && \
    ln -s ../shared/typescript/src dist/node_modules/@shared

# Install production dependencies for the service.
# These also satisfy require() calls from the compiled shared code
# (e.g. pino, ioredis) since Node.js walks up to /app/node_modules/.
COPY --from=builder /app/services/api-gateway/package.json ./
RUN npm install --omit=dev --ignore-scripts

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1

CMD ["node", "dist/services/api-gateway/src/main.js"]
