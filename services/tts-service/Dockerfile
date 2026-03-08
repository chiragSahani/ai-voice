# TTS Service - Coqui XTTS v2 Multilingual Speech Synthesis

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY services/tts-service/requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Generate protobuf stubs
COPY shared/proto /app/proto
RUN mkdir -p /app/generated && \
    python -m grpc_tools.protoc \
    --proto_path=/app/proto \
    --python_out=/app/generated \
    --grpc_python_out=/app/generated \
    /app/proto/tts.proto /app/proto/health.proto && \
    touch /app/generated/__init__.py && \
    sed -i 's/^import \(.*_pb2\)/from . import \1/' /app/generated/*_grpc.py

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TTS_SERVICE_NAME=tts-service \
    TTS_DEVICE=cpu \
    TTS_MODEL_PATH=/models/xtts_v2 \
    TTS_SPEAKER_WAV_DIR=/voices \
    TTS_GRPC_PORT=50052 \
    TTS_HTTP_PORT=8052 \
    TTS_SAMPLE_RATE=24000 \
    TTS_LOG_LEVEL=info

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create directories for models and voice profiles
RUN mkdir -p /models/xtts_v2 /voices/en /voices/hi /voices/ta

WORKDIR /app

# Copy shared library
COPY shared/python/shared /app/shared

# Copy generated proto stubs from builder
COPY --from=builder /app/generated /app/generated

# Copy application code
COPY services/tts-service/app /app/app

ENV PYTHONPATH=/app

HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8052/healthz || exit 1

EXPOSE 50052 8052

CMD ["python", "-m", "app.main"]
