# Scribe MCP Server - Production Dockerfile
# Multi-stage build: builder (compile deps) -> runtime (minimal image)
# Build context: scribe_mcp root (parent of deploy/)
# Usage: docker build -f deploy/Dockerfile -t scribe-mcp:latest .

# ===== STAGE 1: BUILDER =====
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/

# Install scribe-mcp package (no-deps to skip sentence-transformers)
# Then install each dependency individually, EXCLUDING sentence-transformers
# to avoid pulling in PyTorch (~2GB)
RUN pip install --no-cache-dir --no-deps . \
    && pip install --no-cache-dir \
       asyncpg~=0.29 jinja2~=3.1 "mcp==1.26.0" \
       "numpy~=1.20" portalocker~=2.0 psutil~=7.1 \
       pyyaml~=6.0 rich~=13.7 tiktoken~=0.5 watchdog~=3.0

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
