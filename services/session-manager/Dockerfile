###############################################################################
# Session Manager - Multi-stage Dockerfile
###############################################################################

FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/session-manager/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY shared/python/shared /app/shared
COPY services/session-manager/app/ /app/app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    SESSION_PORT=6380 \
    SESSION_HOST=0.0.0.0 \
    SESSION_LOG_LEVEL=info

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:6380/health')" || exit 1

EXPOSE 6380

CMD ["python", "-m", "app.main"]
