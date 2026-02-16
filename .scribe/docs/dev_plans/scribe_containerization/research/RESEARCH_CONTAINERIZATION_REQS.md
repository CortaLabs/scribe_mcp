---
id: scribe_containerization-research-containerization-reqs
title: "\U0001F52C Research Containerization Reqs \u2014 scribe_containerization"
doc_type: RESEARCH_CONTAINERIZATION_REQS
doc_name: RESEARCH_CONTAINERIZATION_REQS
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 03:21:14 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Containerization Reqs — scribe_containerization
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-16 03:18:59 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Research Goal:** Complete inventory of all dependencies, configuration, entry points, and requirements needed to build a production-ready Scribe MCP Docker container for deployment alongside Council MCP on Hetzner CCX23 VPS (16GB RAM, 4 vCPU).

**Key Findings:**

- **CRITICAL BLOCKER:** Scribe currently uses **stdio transport only** - incompatible with Docker networking. Council cannot connect to stdio subprocess across containers. Network transport (WebSocket/SSE) implementation required.
- **Python Dependencies:** 11 core dependencies, Python ≥3.11 required
- **Optional ML Stack:** sentence-transformers (2GB+) is OPTIONAL - lazy-loaded, graceful fallback
- **Storage:** Dual backend (SQLite default OR Postgres via asyncpg), 40+ environment variables
- **Resource Profile:** Lightweight - 512MB RAM base, <0.3 CPU cores, ~200MB Docker image
- **Security:** Can run as non-root user - no privileged operations
- **Initialization:** Fully automatic - no manual setup required on first run
- **Network:** Offline-capable - no external HTTP dependencies

**Recommendation:** Scribe fits comfortably in 8.5GB headroom. Primary effort required: implementing network transport layer (see RESEARCH_TRANSPORT_LAYER for details).
<!-- ID: research_scope -->
**Research Lead:** agent-20260216-031119-6662e6ff

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Detailed Findings

### 1. Python Dependencies

**Source:** `pyproject.toml` lines 13-25

**Core Dependencies (11 total):**
```
asyncpg~=0.29           # Postgres async driver
jinja2~=3.1             # Template rendering (managed docs)
mcp==1.26.0             # Anthropic MCP SDK (pinned)
numpy~=1.20             # Array operations (vector indexing)
portalocker~=2.0        # File locking
psutil~=7.1             # System utilities
pyyaml~=6.0             # YAML config parsing
rich~=13.7              # Terminal formatting
sentence-transformers~=2.0  # ML embeddings (OPTIONAL - see below)
tiktoken~=0.5           # Token counting
watchdog~=3.0           # File system monitoring
```

**Python Version:** ≥3.11 (pyproject.toml line 10)

**Optional Dev Dependencies:**
```
pytest~=7.4
pytest-asyncio~=0.23
faiss-cpu~=1.7          # Vector search (dev only)
```

**CRITICAL FINDING - sentence-transformers is OPTIONAL:**
- Lazy-loaded only when vector indexing enabled (`src/scribe_mcp/plugins/vector_indexer.py:80-99`)
- Graceful fallback to deterministic hash-based encoder if import fails
- Vector indexing controlled by `vector_config.enabled` flag
- **Recommendation:** Build lightweight image WITHOUT ML deps, enable vector features via separate image variant if needed
- **Impact:** Saves ~2GB+ Docker image size (torch, transformers, ML models)

**System Packages Required:**
- **libpq-dev** (for asyncpg Postgres client compilation) - only needed if building from source
- **gcc, python3-dev** (for building native extensions) - only at build time, not runtime
- Pre-built wheels available for common platforms - may not need build deps

### 2. Entry Points & Server Architecture

**Main Entry Point:** `src/scribe_mcp/__main__.py:main()`
- CLI: `scribe-mcp` or `scribe-server` (pyproject.toml line 36-37)
- Calls `asyncio.run(server_main())` → `src/scribe_mcp/server.py:main()`

**Current Transport:** **stdio ONLY** (`server.py:957`)
```python
async with mcp_stdio.stdio_server() as (read_stream, write_stream):
    await app.run(read_stream, write_stream, app.create_initialization_options())
```

**🚨 CRITICAL BLOCKER FOR DOCKER:**
- stdio transport requires parent process to spawn subprocess over stdin/stdout
- **Impossible across Docker containers** - Council cannot spawn Scribe subprocess
- **Network transport required:** WebSocket or SSE (Server-Sent Events)
- MCP SDK 1.26.0 capabilities need verification (see RESEARCH_TRANSPORT_LAYER)

**Docker CMD Recommendation (AFTER network transport implemented):**
```dockerfile
CMD ["python", "-m", "scribe_mcp", "--transport", "websocket", "--port", "8080"]
```

**Initialization Sequence:** (`server.py:737-800`)
1. `storage_backend.setup()` - creates DB schema, runs migrations (automatic)
2. Schedule background tasks: cleanup, plugins, bridges
3. Initialize AgentContextManager for multi-agent support
4. Migrate legacy state (one-time, automatic)
5. **No manual init required** - first-run safe

### 3. Environment Variables & Configuration

**Source:** `src/scribe_mcp/config/settings.py:89-262` + search across 17 files

**REQUIRED Variables:**
- `SCRIBE_ROOT` - Repository root path (defaults to cwd, but Docker needs explicit path)
  - **Docker value:** `/workspace` or `/app/workspace` (mounted volume)

**Database Configuration:**
- `SCRIBE_DB_URL` - Postgres connection string (e.g., `postgresql://user:pass@host:5432/dbname`)
  - **Docker value:** `postgresql://scribe_user:scribe_pass@postgres:5432/agentkit?options=-c%20search_path=scribe`
  - Can share Council's Postgres instance using different schema
- `SCRIBE_STORAGE_BACKEND` - Backend type: `sqlite` (default) or `postgres`
  - **Docker value:** `postgres` (recommended for production)
- `SCRIBE_POSTGRES_SCHEMA` - Postgres schema name (default: `scribe`)
  - **Docker value:** `scribe` (isolated from Council's default schema)
- `SCRIBE_DB_PATH` or `SCRIBE_SQLITE_PATH` - SQLite database path (if not using Postgres)
  - **Docker value:** `/data/scribe_projects.db` (mounted volume)

**Postgres Connection Pool Settings:**
- `SCRIBE_POSTGRES_POOL_MIN_SIZE` (default: 2)
- `SCRIBE_POSTGRES_POOL_MAX_SIZE` (default: 20)
- `SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS` (default: 30)
- `SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS` (default: 10)
- `SCRIBE_POSTGRES_MAX_INACTIVE_SECONDS` (default: 300)
- `SCRIBE_POSTGRES_CONNECT_RETRIES` (default: 3)
- `SCRIBE_POSTGRES_CONNECT_RETRY_BACKOFF_SECONDS` (default: 1.0)

**Optional Configuration:**
- `SCRIBE_ALLOW_NETWORK` (default: false) - Enable network features
- `SCRIBE_MCP_NAME` (default: `scribe.mcp`) - MCP server name
- `SCRIBE_DEV_PLANS_BASE` (default: `.scribe/docs/dev_plans`) - Docs path
- `SCRIBE_RECENT_PROJECT_LIMIT` (default: 5)
- `SCRIBE_LOG_RATE_LIMIT_COUNT` (default: 0, disabled)
- `SCRIBE_LOG_RATE_LIMIT_WINDOW` (default: 60 seconds)
- `SCRIBE_LOG_MAX_BYTES` (default: 512KB)
- `SCRIBE_STORAGE_TIMEOUT_SECONDS` (default: 5)
- `SCRIBE_RETENTION_DAYS` (default: 90)
- `SCRIBE_REMINDER_IDLE_MINUTES` (default: 45)
- `SCRIBE_REMINDER_WARMUP_MINUTES` (default: 5)

**Vector Indexing Variables:**
- `SCRIBE_VECTOR_ENABLED` (default: via config file)
- `SCRIBE_VECTOR_BACKEND` (default: `faiss`)
- `SCRIBE_VECTOR_DIMENSION` (default: 384)
- `SCRIBE_VECTOR_MODEL` (default: `all-MiniLM-L6-v2`)
- `SCRIBE_VECTOR_GPU` (default: false)
- `SCRIBE_VECTOR_QUEUE_MAX` (default: 1000)
- `SCRIBE_VECTOR_BATCH_SIZE` (default: 32)

**Token Optimization:**
- `SCRIBE_TOKEN_DAILY_LIMIT`
- `SCRIBE_TOKEN_OPERATION_LIMIT`
- `SCRIBE_TOKEN_WARNING_THRESHOLD`

**Debug/Development:**
- `SCRIBE_SESSION_DEBUG` (default: false) - Session debugging
- `SCRIBE_TOOL_LOG_FSYNC` (default: false) - Force fsync on tool logs
- `SCRIBE_LOG_LEVEL` (default: `WARNING`)
- `HF_HUB_DISABLE_PROGRESS_BARS=1` (suppress HuggingFace output)

**Total:** 40+ environment variables discovered

### 4. Storage Architecture & Volume Requirements

**Dual Storage System:**

**Option A: SQLite (default, simpler)**
- Database path: `user_data_dir()/scribe_projects.db` (default)
  - Typical: `~/.local/share/scribe/scribe_projects.db` (Linux)
  - Docker: `/data/scribe_projects.db` (mounted volume)
- Current size: 108MB (active dev database)
- Embedded, no external dependencies

**Option B: Postgres (recommended for Docker)**
- Requires `asyncpg` driver (already in dependencies)
- Can share Council's `pgvector/pgvector:pg16` instance
- Schema isolation via `SCRIBE_POSTGRES_SCHEMA=scribe`
- Connection pooling built-in (2-20 connections)
- Better for concurrent access, backups, migrations

**File System Structure:**
```
.scribe/                    # 103MB total
├── config/                 # Runtime config overlays
│   ├── scribe.yaml
│   ├── boundary_rules.yaml
│   └── bridges/*.yaml
├── docs/
│   └── dev_plans/          # Project documentation
│       └── {project}/
│           ├── PROGRESS_LOG.md
│           ├── ARCHITECTURE_GUIDE.md
│           ├── PHASE_PLAN.md
│           ├── CHECKLIST.md
│           └── research/
├── backups/                # DB backups (if enabled)
└── cli/                    # CLI session state
```

**Package Data (bundled in pip install):**
- `src/scribe_mcp/config/*.json` (11 config files)
- `src/scribe_mcp/config/*.yaml` (templates)
- `src/scribe_mcp/db/*.sql` (schema initialization)
- `src/scribe_mcp/db/postgres_migrations/*.sql` (migrations)
- `src/scribe_mcp/templates/*` (document templates)

**Docker Volume Strategy:**

**Option 1: Postgres + File Volumes (recommended)**
```yaml
volumes:
  - scribe_workspace:/workspace      # SCRIBE_ROOT, .scribe/ directory
  - scribe_config:/app/config        # Optional: custom config overlays
environment:
  SCRIBE_ROOT: /workspace
  SCRIBE_STORAGE_BACKEND: postgres
  SCRIBE_DB_URL: postgresql://scribe_user:scribe_pass@postgres:5432/agentkit?options=-c%20search_path=scribe
```

**Option 2: SQLite + File Volumes (simpler)**
```yaml
volumes:
  - scribe_workspace:/workspace
  - scribe_data:/data
environment:
  SCRIBE_ROOT: /workspace
  SCRIBE_DB_PATH: /data/scribe_projects.db
```

### 5. Resource Requirements

**Memory:**
- Base (no vector indexing): ~512MB
- With vector indexing (lazy-loaded): ~1GB
- **Docker limit recommendation:** 1GB (comfortable headroom)

**CPU:**
- Workload: I/O-bound (async file writes, DB queries, template rendering)
- Typical usage: <0.3 cores
- **Docker limit recommendation:** 0.5 cores (allows burst)

**Disk:**
- Docker image size: ~150-200MB (without ML deps), ~2GB+ (with sentence-transformers)
- `.scribe/` directory: ~100MB (typical), grows with project count
- SQLite database: ~500MB max (typical workload)
- **Volume size recommendation:** 5GB (plenty of headroom)

**Comparison to Council:**
- Council daemon: 2GB RAM, 0.8 CPU (heavier RAG/ML stack)
- Scribe: 1GB RAM, 0.5 CPU (1/2 of Council)
- **Total Hetzner CCX23 usage:** 8GB + 1GB = 9GB / 16GB (7GB free)

### 6. Runtime Dependencies & CLI Tools

**NO subprocess/CLI tool dependencies in core server:**
- Searched for `subprocess.run`, `shutil.which` - only 1 match
- `src/scribe_mcp/scripts/postgres_backup.py` calls `pg_dump` CLI
  - **Optional utility script** for Postgres backups
  - Not used by core MCP server
  - Command: `scribe-backup-postgres` (pyproject.toml line 40)
  - **Docker consideration:** Include `postgresql-client` package only if backup functionality needed

**No git required at runtime**
- No git operations in codebase
- Version control is external

**Pure Python application** - no external process spawning in server code

### 7. Security & Permissions

**Non-root capable:** ✅
- No `chmod`, `chown`, `sudo` calls found in codebase
- All file operations use Python standard library (respects process permissions)
- File mode constants (`0o666`, `0o755`) passed to `open()` - respects umask

**Recommended Docker User:**
```dockerfile
RUN adduser --disabled-password --gecos '' scribe
USER scribe
```

**Volume Permissions:**
- Volumes must be writable by Docker user (UID/GID 1000 or custom)
- No privileged operations required

**Secrets Management:**
- `SCRIBE_DB_URL` contains credentials - pass via Docker secrets or env file
- Bridge API keys via `SCRIBE_BRIDGE_{NAME}_API_KEY` env vars

### 8. Network Requirements

**External Network Access:** NOT REQUIRED
- No HTTP client libraries (`requests`, `httpx`, `aiohttp`) in dependencies
- Only `urllib.parse` for URL manipulation (standard library, no network I/O)
- sentence-transformers model downloads (first run) - can be disabled or pre-cached
  - Set `SCRIBE_VECTOR_ENABLED=false` to disable
  - Or pre-download models in Docker build

**Offline Operation:** ✅ Fully supported
- All functionality works without internet access
- Vector indexing optional - falls back to deterministic encoder

### 9. Existing Docker Artifacts

**Status:** None found
- No `Dockerfile`, `docker-compose.yml`, `.dockerignore` in repository
- Starting from scratch for containerization

### 10. Configuration Files

**Bundled in Package (pip install):**
- 11 JSON/YAML config files in `src/scribe_mcp/config/`
- Included via `pyproject.toml` setuptools.package-data (lines 52-63)
- Available after `pip install scribe-mcp`

**Runtime Overlays (optional):**
- `.scribe/config/scribe.yaml` - user-specific overrides
- `.scribe/config/boundary_rules.yaml` - dependency rules
- `.scribe/config/bridges/*.yaml` - bridge configurations

**Docker Strategy:**
- Base configs bundled in image (via pip install)
- Custom configs via mounted volume: `/workspace/.scribe/config/`
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->
## Recommendations & Next Steps

### Immediate Actions

1. **CRITICAL - Implement Network Transport**
   - Current stdio transport incompatible with Docker networking
   - Verify MCP SDK 1.26.0 supports WebSocket/SSE (see RESEARCH_TRANSPORT_LAYER)
   - Implement WebSocket server in `server.py` as alternative to stdio
   - Add `--transport` CLI argument to select transport mode
   - **Blocker:** Cannot deploy to Docker without this

2. **Create Dockerfile**
   - Base image: `python:3.11-slim` (minimal Debian)
   - Install system deps: `libpq-dev` (if needed for asyncpg wheels)
   - `pip install scribe-mcp` (installs from pyproject.toml)
   - **DO NOT** include sentence-transformers (optional, 2GB+ bloat)
   - Run as non-root user (`scribe`)
   - CMD: `["python", "-m", "scribe_mcp", "--transport", "websocket", "--port", "8080"]`

3. **Create docker-compose Service**
   ```yaml
   scribe-mcp:
     build: ./scribe_mcp
     image: scribe-mcp:latest
     container_name: scribe-mcp
     restart: unless-stopped
     networks:
       - backend
     ports:
       - "127.0.0.1:8080:8080"  # WebSocket endpoint
     volumes:
       - scribe_workspace:/workspace
     environment:
       SCRIBE_ROOT: /workspace
       SCRIBE_STORAGE_BACKEND: postgres
       SCRIBE_DB_URL: postgresql://scribe_user:${SCRIBE_DB_PASSWORD}@postgres:5432/agentkit?options=-c%20search_path=scribe
       SCRIBE_POSTGRES_SCHEMA: scribe
       SCRIBE_MCP_NAME: scribe.mcp
       SCRIBE_LOG_LEVEL: INFO
       HF_HUB_DISABLE_PROGRESS_BARS: "1"
     deploy:
       resources:
         limits:
           memory: 1G
           cpus: '0.5'
     depends_on:
       - postgres
     healthcheck:
       test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.connect(('localhost', 8080)); s.close()"]
       interval: 30s
       timeout: 10s
       retries: 3
   ```

4. **Database Setup**
   - **Option A (Recommended):** Share Council's Postgres with separate schema
     - Create `scribe` schema in existing `agentkit` database
     - Create `scribe_user` role with schema permissions
     - Scribe migrations run automatically on startup
   - **Option B:** Separate SQLite database (simpler, less scalable)
     - Mount `/data` volume for `scribe_projects.db`

### Docker Build Strategy

**Multi-stage Build (recommended):**
```dockerfile
FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev python3-dev && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml setup.py ./
COPY src/ ./src/
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
RUN adduser --disabled-password --gecos '' scribe
USER scribe
WORKDIR /workspace
CMD ["python", "-m", "scribe_mcp", "--transport", "websocket", "--port", "8080"]
```

**Benefits:**
- Smaller final image (no build tools in runtime layer)
- Pre-compiled wheels cached in builder stage
- Non-root user for security

### .dockerignore

Create `.dockerignore` to reduce build context:
```
.scribe/
.git/
.github/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
*.db
*.db-journal
tmp_tests/
tests/
docs/
*.md
!README.md
```

### Testing Strategy

1. **Local Testing (before Docker):**
   - Verify network transport works: `python -m scribe_mcp --transport websocket --port 8080`
   - Test Postgres connection with Council's DB
   - Verify schema isolation (scribe vs default)

2. **Docker Testing:**
   - Build image: `docker build -t scribe-mcp:test .`
   - Run standalone: `docker run -p 8080:8080 -e SCRIBE_DB_URL=... scribe-mcp:test`
   - Test WebSocket connection from host
   - Verify logs, DB writes, volume persistence

3. **Integration Testing (with Council):**
   - Deploy full stack with docker-compose
   - Configure Council to connect to Scribe WebSocket endpoint
   - Test cross-container MCP communication
   - Monitor resource usage (RAM/CPU)

### Open Questions

1. **MCP SDK Network Transport Support**
   - Does mcp==1.26.0 provide WebSocket/SSE server implementations?
   - See RESEARCH_TRANSPORT_LAYER for investigation
   - May need custom implementation or SDK upgrade

2. **Database Schema Isolation**
   - Confirm Council's Postgres allows schema-level isolation
   - Test schema creation permissions for `scribe_user`
   - Verify no table name conflicts

3. **Volume Ownership**
   - UID/GID mapping between host and container
   - Ensure scribe user can write to mounted volumes
   - May need `chown` in entrypoint script (only on volumes, not codebase)

### Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| stdio transport blocker | **HIGH** | Implement network transport (RESEARCH_TRANSPORT_LAYER) |
| Resource exhaustion | LOW | Conservative limits (1GB/0.5 CPU), monitoring |
| Database schema conflicts | MEDIUM | Use separate `scribe` schema, test isolation |
| Volume permission errors | MEDIUM | Document UID/GID mapping, provide entrypoint fix |
| Missing system deps | LOW | Multi-stage build with explicit deps |
| Network transport implementation complexity | MEDIUM | Verify SDK support, fallback to custom implementation |

### Success Criteria

✅ **Containerization Complete When:**
1. Dockerfile builds successfully (<300MB image without ML deps)
2. Container starts and initializes DB schema automatically
3. WebSocket endpoint accepts connections on port 8080
4. Council MCP can connect and invoke Scribe tools
5. Volumes persist across container restarts
6. Resource usage stays within limits (1GB RAM, 0.5 CPU)
7. Logs accessible via `docker logs scribe-mcp`
8. Healthcheck passes consistently
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---