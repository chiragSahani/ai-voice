# ---- Build Stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy shared typescript modules
COPY shared/typescript/package*.json ./shared/typescript/
RUN cd shared/typescript && npm install --ignore-scripts

COPY shared/typescript/ ./shared/typescript/

# Copy campaign engine
COPY services/campaign-engine/package*.json ./services/campaign-engine/
RUN cd services/campaign-engine && npm install --ignore-scripts

COPY services/campaign-engine/ ./services/campaign-engine/

# Build shared then service.
# --rootDir /app makes tsc preserve the monorepo directory structure in dist/:
#   dist/services/campaign-engine/src/...  (compiled service code)
#   dist/shared/typescript/src/...         (compiled shared code)
# Relative require() paths in the compiled JS resolve correctly within this tree.
RUN cd shared/typescript && npx tsc --skipLibCheck || true
RUN cd services/campaign-engine && npx tsc --skipLibCheck --rootDir /app || true

# ---- Runtime Stage ----
FROM node:20-alpine AS runtime

RUN apk add --no-cache tini dumb-init

WORKDIR /app

# Copy the full compiled dist/ tree (includes both service and shared code)
COPY --from=builder /app/services/campaign-engine/dist/ dist/

# Install production dependencies for the service.
# These also satisfy require() calls from the compiled shared code
# (e.g. pino, ioredis, mongoose, bullmq) since Node.js walks up to /app/node_modules/.
COPY --from=builder /app/services/campaign-engine/package*.json ./
RUN npm install --omit=dev --ignore-scripts

# Non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

ENV NODE_ENV=production
ENV PORT=3030

EXPOSE 3030

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3030/health || exit 1

ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "dist/services/campaign-engine/src/main.js"]
