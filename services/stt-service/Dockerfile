###############################################################################
# STT Service - Multi-stage Dockerfile
###############################################################################

FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/stt-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Generate protobuf stubs
COPY shared/proto /proto
RUN mkdir -p /build/generated && \
    python -m grpc_tools.protoc \
        -I/proto \
        --python_out=/build/generated \
        --grpc_python_out=/build/generated \
        --pyi_out=/build/generated \
        /proto/stt.proto /proto/health.proto && \
    touch /build/generated/__init__.py && \
    sed -i 's/^import \(.*_pb2\)/from . import \1/' /build/generated/*_grpc.py

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/generated /app/generated
COPY shared/python/shared /app/shared
COPY services/stt-service/app/ /app/app/

RUN mkdir -p /models /root/.cache/torch/hub

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    STT_WHISPER_MODEL=large-v3 \
    STT_WHISPER_DEVICE=cpu \
    STT_WHISPER_COMPUTE_TYPE=float32 \
    STT_GRPC_PORT=50051 \
    STT_HTTP_PORT=8051 \
    STT_LOG_LEVEL=info

HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8051/health/live || exit 1

EXPOSE 50051 8051

CMD ["python", "-m", "app.main"]
