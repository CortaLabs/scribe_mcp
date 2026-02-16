# Scribe MCP Server - Production Dockerfile
# Multi-stage build: builder (compile deps) -> runtime (minimal image)
# Build context: scribe_mcp root (parent of deploy/)
#
# Usage:
#   CPU (default, for Hetzner/servers without GPU):
#     docker build -f deploy/Dockerfile -t scribe-mcp:latest .
#
#   GPU (CUDA, for machines with NVIDIA GPU):
#     docker build -f deploy/Dockerfile --build-arg DEVICE=gpu -t scribe-mcp:gpu .

# ===== STAGE 1: BUILDER =====
FROM python:3.11-slim AS builder

# DEVICE=cpu (default) pulls torch+cpu (~150MB). DEVICE=gpu pulls full CUDA torch (~900MB).
ARG DEVICE=cpu

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/

# Install scribe-mcp with ALL dependencies including sentence-transformers.
# CPU mode uses PyTorch CPU-only wheels (~150MB vs ~900MB + 3GB CUDA libs).
# GPU mode pulls full CUDA PyTorch for GPU-accelerated embeddings.
# --no-cache-dir keeps the builder layer from doubling in size.
RUN if [ "$DEVICE" = "cpu" ]; then \
      pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu . ; \
    else \
      pip install --no-cache-dir . ; \
    fi

# ===== STAGE 2: RUNTIME =====
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (UID 1001, matching Council convention)
RUN groupadd -r scribe --gid=1001 && \
    useradd -r -g scribe --uid=1001 --create-home --shell=/bin/false scribe

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
     /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
WORKDIR /app
COPY src/ ./src/
COPY pyproject.toml ./

# Copy entrypoint script
COPY deploy/docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

# Create volume mount points
RUN mkdir -p /app/.scribe && chown -R scribe:scribe /app

# Install gosu for privilege drop after reading secrets
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# Environment defaults
ENV PYTHONPATH="/app/src" \
    SCRIBE_ROOT="/app" \
    SCRIBE_TRANSPORT="sse" \
    SCRIBE_TRANSPORT_PORT="8200" \
    SCRIBE_TRANSPORT_HOST="0.0.0.0" \
    PYTHONUNBUFFERED="1" \
    HF_HUB_DISABLE_PROGRESS_BARS="1"

EXPOSE 8200

# Entrypoint runs as root to read secrets, then drops to scribe via gosu
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8200/health || exit 1

ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]
CMD ["python", "-m", "scribe_mcp", "--transport", "sse"]
