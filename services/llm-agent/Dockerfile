FROM python:3.12-slim AS base

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install shared Python package
COPY shared/python /shared/python
RUN pip install -e /shared/python

# Install service dependencies
COPY services/llm-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Generate proto stubs
COPY shared/proto /shared/proto
RUN mkdir -p /app/generated && \
    python -m grpc_tools.protoc \
    -I/shared/proto \
    --python_out=/app/generated \
    --grpc_python_out=/app/generated \
    /shared/proto/llm_agent.proto \
    /shared/proto/tool_orchestrator.proto \
    /shared/proto/health.proto && \
    touch /app/generated/__init__.py && \
    sed -i 's/^import \(.*_pb2\)/from . import \1/' /app/generated/*_grpc.py

# Copy application code
COPY services/llm-agent/app /app/app
COPY services/llm-agent/tests /app/tests

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser
USER appuser

# Expose ports: gRPC (8090) + HTTP health (8190)
EXPOSE 8090 8190

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8190/health')" || exit 1

CMD ["python", "-m", "app.main"]
