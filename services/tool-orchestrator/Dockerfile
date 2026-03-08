# ---------- Build stage ----------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/tool-orchestrator/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Runtime stage ----------
FROM python:3.12-slim

LABEL service="tool-orchestrator"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy shared library
COPY shared/python/shared /app/shared

# Copy proto files
COPY shared/proto /app/proto

# Copy application code
COPY services/tool-orchestrator/app /app/app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser
USER appuser

EXPOSE 8091 8092

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8092/healthz')" || exit 1

ENTRYPOINT ["python", "-m", "app.main"]
