# ---- Build Stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy shared dependencies
COPY shared/typescript/ shared/typescript/
RUN cd shared/typescript && npm install --ignore-scripts

# Copy service dependencies
COPY services/appointment-scheduler/package.json services/appointment-scheduler/
RUN cd services/appointment-scheduler && npm install --ignore-scripts

# Copy service source
COPY services/appointment-scheduler/ services/appointment-scheduler/

# Build shared then service.
# --rootDir /app makes tsc preserve the monorepo directory structure in dist/:
#   dist/services/appointment-scheduler/src/...  (compiled service code)
#   dist/shared/typescript/src/...               (compiled shared code)
# Relative require() paths in the compiled JS resolve correctly within this tree.
RUN cd shared/typescript && npx tsc --skipLibCheck || true
RUN cd services/appointment-scheduler && npx tsc --skipLibCheck --rootDir /app || true

# --- Production stage ---
FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# Copy the full compiled dist/ tree (includes both service and shared code)
COPY --from=builder /app/services/appointment-scheduler/dist/ dist/

# Install production dependencies for the service.
# These also satisfy require() calls from the compiled shared code
# (e.g. pino, ioredis, mongoose) since Node.js walks up to /app/node_modules/.
COPY --from=builder /app/services/appointment-scheduler/package.json ./
RUN npm install --omit=dev --ignore-scripts

USER appuser

EXPOSE 3010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3010/health || exit 1

CMD ["node", "dist/services/appointment-scheduler/src/main.js"]
