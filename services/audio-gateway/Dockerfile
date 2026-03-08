# Audio Gateway Dockerfile
# Multi-stage build for minimal image size

# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy shared library first (changes less frequently)
COPY shared/python /build/shared/python

# Copy service requirements and install
COPY services/audio-gateway/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /build/requirements.txt && \
    pip install --no-cache-dir --prefix=/install /build/shared/python

# ---- Runtime stage ----
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY services/audio-gateway/app /app/app

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8080/health'); r.raise_for_status()"

# Expose WebSocket + HTTP port
EXPOSE 8080

# Run with uvicorn — uvloop for maximum async performance
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--ws-ping-interval", "20", \
     "--ws-ping-timeout", "10", \
     "--ws-max-size", "65536", \
     "--no-access-log"]
