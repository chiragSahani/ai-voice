# ============================================================
# Patient Memory Service -- Multi-stage Docker build
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

# Copy shared dependencies
COPY shared/typescript/ shared/typescript/
RUN cd shared/typescript && npm install --ignore-scripts

# Copy service dependencies
COPY services/patient-memory/package.json services/patient-memory/
RUN cd services/patient-memory && npm install --ignore-scripts

# Copy service source
COPY services/patient-memory/ services/patient-memory/

# Build shared then service.
# --rootDir /app makes tsc preserve the monorepo directory structure in dist/:
#   dist/services/patient-memory/src/...  (compiled service code)
#   dist/shared/typescript/src/...        (compiled shared code)
# Relative require() paths in the compiled JS resolve correctly within this tree.
RUN cd shared/typescript && npx tsc --skipLibCheck || true
RUN cd services/patient-memory && npx tsc --skipLibCheck --rootDir /app || true

# --- Production ---
FROM node:20-alpine

RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

WORKDIR /app

# Copy the full compiled dist/ tree (includes both service and shared code)
COPY --from=builder /app/services/patient-memory/dist/ dist/

# Install production dependencies for the service.
# These also satisfy require() calls from the compiled shared code
# (e.g. pino, ioredis, mongoose) since Node.js walks up to /app/node_modules/.
COPY --from=builder /app/services/patient-memory/package.json ./
RUN npm install --omit=dev --ignore-scripts && \
    npm cache clean --force

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 3020

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3020/health || exit 1

ENV NODE_ENV=production PORT=3020

CMD ["node", "dist/services/patient-memory/src/main.js"]
