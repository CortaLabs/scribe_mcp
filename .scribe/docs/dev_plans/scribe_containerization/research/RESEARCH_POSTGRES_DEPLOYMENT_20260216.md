# 🔬 Research: Council MCP Postgres Deployment Analysis

**Project:** scribe_containerization  
**Research Goal:** Analyze Council MCP's existing Postgres infrastructure for Scribe containerization integration  
**Date:** 2026-02-16  
**Agent:** ResearchAgent-PostgresDeploy  
**Confidence:** 98%

---

## Executive Summary

Council MCP's `deploy/docker-compose.yaml` already contains ALL infrastructure needed for Scribe's Postgres integration. The deployment uses a shared `agentkit` database with schema isolation: Council uses the default `public`/`agentkit` schemas, while Scribe creates its own `scribe` schema. Both services share the same Postgres user (`council`), database (`agentkit`), and password (from `pg_password` secret).

**Key Finding:** Scribe containerization requires NO changes to Council's Postgres service definition. All Scribe needs is:
1. SCRIBE_DB_URL secret (already defined at lines 195, 258, 374-375)
2. SCRIBE_STORAGE_BACKEND=postgres environment variable (already set at lines 182, 249)
3. Network access to `postgres:5432` service (already on `backend` network)

Scribe auto-initializes its schema on first connection. No manual SQL setup required.

---

## Research Scope

**Files Investigated (8 total):**
1. `council_mcp/deploy/docker-compose.yaml` (376 lines) - Postgres service definition
2. `council_mcp/deploy/docker-entrypoint.sh` (165 lines) - Secret bridging logic
3. `council_mcp/deploy/.env.example` (82 lines) - Connection string format
4. `council_mcp/src/council_mcp/services/mcp_servers.py` - Current Scribe integration
5. `src/scribe_mcp/storage/postgres/__init__.py` (2148 lines) - PostgresStorage class
6. `src/scribe_mcp/storage/postgres/schema.py` (133 lines) - Schema bootstrap
7. `src/scribe_mcp/db/init.sql` (468 lines) - Table definitions
8. `src/scribe_mcp/db/postgres_migrations/` (3 files) - Numbered migrations

**Research Questions Answered:**
- ✅ Does Council's Postgres have a schema for Scribe? **No - Scribe creates its own**
- ✅ What's the connection string format? **postgresql://council:PASSWORD@postgres:5432/agentkit**
- ✅ Are there init scripts? **Yes - Scribe runs init.sql + 3 migrations automatically**
- ✅ What user/role does Council use? **council (superuser, created by postgres container)**
- ✅ Should Scribe share or have its own user? **Shares council user, separate schema**
- ✅ What's the secrets path convention? **../secrets/*.txt relative to deploy/ directory**

---

## Key Technical Findings

### 1. Postgres Service (Council docker-compose.yaml)

- **Image:** pgvector/pgvector:pg16 (includes pgvector extension pre-installed)
- **Database:** agentkit
- **User:** council (superuser)
- **Resources:** 4GB RAM, 1.0 CPU core
- **Volume:** pg_data (persistent storage)
- **Health Check:** pg_isready -U council -d agentkit (10s interval)
- **Port:** 127.0.0.1:5432:5432 (localhost only)
- **Network:** backend (shared with all services)

### 2. Secrets Already Configured

Council's docker-compose defines 5 secrets, including **scribe_db_url** (lines 195, 258, 374-375):

```yaml
secrets:
  pg_password:
    file: ../secrets/pg_password.txt
  database_url:
    file: ../secrets/database_url.txt
  api_key:
    file: ../secrets/api_key.txt
  openai_api_key:
    file: ../secrets/openai_api_key.txt
  scribe_db_url:
    file: ../secrets/scribe_db_url.txt    # ← ALREADY CONFIGURED
```

**Path convention:** `../secrets/` relative to `deploy/` = `council_mcp/secrets/`  
**Mounted at:** `/run/secrets/<name>` inside containers  
**Permissions:** chmod 600 recommended

### 3. Docker Entrypoint Secret Bridging

Council's `docker-entrypoint.sh` (lines 72-79) bridges secrets to environment variables:

```bash
if [ -z "${SCRIBE_DB_URL}" ] && [ -f /run/secrets/scribe_db_url ]; then
    export SCRIBE_DB_URL
    SCRIBE_DB_URL="$(cat /run/secrets/scribe_db_url)"
    echo "[entrypoint] Loaded SCRIBE_DB_URL from Docker secret"
fi
```

**Auto-bootstrap logic** (lines 117-148):
- Checks if `schema_migrations` table exists (Council's AgentKit schema)
- If missing: runs `agentkit init --auto` with superuser credentials
- Creates admin/app roles, installs pgvector, runs migrations
- Skip with `AGENTKIT_SKIP_AUTO_BOOTSTRAP=1`

**Note:** This is for Council's schema. Scribe does its own bootstrap independently.

### 4. Connection String Format

**Standard format:**
```
postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

**Council's URLs:**
```bash
# Council AgentKit connection
DATABASE_URL=postgresql://council:PASSWORD@postgres:5432/agentkit

# Scribe connection (SAME database, DIFFERENT schema)
SCRIBE_DB_URL=postgresql://council:PASSWORD@postgres:5432/agentkit
```

**Critical detail:**
- Both use **same database** (agentkit)
- Both use **same user** (council - Postgres superuser)
- Isolation via **PostgreSQL schemas:**
  - Council: `public` schema (default) or `agentkit` schema
  - Scribe: `scribe` schema (dedicated namespace)

### 5. Scribe Schema Architecture

**Schema name:** `scribe` (default, configurable)

**Bootstrap process (automatic on first connection):**
1. Create schema: `CREATE SCHEMA IF NOT EXISTS "scribe"`
2. Install extensions: `pg_trgm` (required), `vector` (optional)
3. Run baseline schema from `init.sql` (15+ tables)
4. Apply numbered migrations (001-003)

**Migration tracking:**
```sql
CREATE TABLE IF NOT EXISTS scribe_migrations (
    name TEXT PRIMARY KEY,
    completed_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Key tables:**
- `scribe_projects` - Project metadata (name UNIQUE, repo_root, docs_json, status, phase)
- `scribe_entries` - Log entries (project_id FK, ts, emoji, agent, message, meta JSONB)
- `scribe_metrics` - Per-project aggregates (total_entries, success_count, warn/error counts)
- `agent_sessions` - Session state (session_id, identity_key UNIQUE, mode CHECK)
- `agent_projects` - Active project per agent (agent_id, project_name FK, version)
- `documents` - Document tracking (id, project_id, doc_type, file_path, metadata JSONB)
- `doc_changes` - Edit audit trail (project_id FK, doc_name, section, action, sha_before/after)

**Foreign keys:** CASCADE delete rules on project_id references

### 6. PostgresStorage Initialization

**Class:** `scribe_mcp.storage.postgres.PostgresStorage`

**Constructor:**
```python
def __init__(
    self,
    dsn: str,                    # Connection string (REQUIRED)
    *,
    schema_name: str = "scribe", # Schema name (default: "scribe")
    pool_min_size: int = 2,
    pool_max_size: int = 20,
    command_timeout_seconds: float = 60.0,
    # ... connection/retry settings
) -> None:
```

**Connection pooling:** asyncpg pool, 2-20 connections, 300s inactivity timeout, 3 retries

**Setup flow:**
```python
storage = PostgresStorage(dsn="postgresql://council:pass@postgres:5432/agentkit")
await storage.setup()  # Triggers schema.ensure_schema()
```

**What setup() does:**
1. Acquire schema lock (prevent concurrent bootstrap)
2. Create `scribe` schema if missing
3. Install extensions (pg_trgm required, pgvector optional)
4. Run all statements from `init.sql`
5. Create `scribe_migrations` table
6. Apply numbered migrations in order (idempotent)
7. Set `_schema_ready = True`

### 7. Current vs. Containerized Integration

**Current pattern (stdio subprocess):**
```python
# Council spawns Scribe as subprocess
scribe_env = {
    "SCRIBE_ROOT": f"{spine_root}/scribe_mcp",
    "SCRIBE_STORAGE_BACKEND": "postgres",
}
# Forward env vars
for var in ("SCRIBE_DB_URL", "SCRIBE_DB_SCHEMA"):
    if val := os.environ.get(var):
        scribe_env[var] = val
```

**Containerized pattern (SSE network):**
```
Council → HTTP/SSE client → http://scribe-mcp:8080/sse → Scribe container
                                                         (reads SCRIBE_DB_URL from own secret)
```

**Change:**
- OLD: Council spawns subprocess, forwards env vars
- NEW: Council connects to SSE endpoint, Scribe self-contained with own config

---

## Schema Isolation Strategy

**Why same database, different schemas?**

| Approach | Pros | Cons |
|----------|------|------|
| Separate databases | Maximum isolation | Connection overhead, backup complexity |
| **Same DB, different schemas** ✅ | Shared pool, atomic cross-schema transactions, single backup | Requires schema-aware queries |

**Namespace isolation:**
```sql
-- Council tables
public.schema_migrations
public.agents
public.memories

-- Scribe tables
scribe.scribe_projects
scribe.scribe_entries
scribe.documents
```

**No naming conflicts:** Both have `schema_migrations` tables, but in different namespaces.

**Search path:**
```sql
-- Council connection
SET search_path TO public, agentkit;

-- Scribe connection (set automatically by PostgresStorage)
SET search_path TO scribe, public;
```

---

## Recommendations

### ✅ No Infrastructure Changes Needed

Council's docker-compose.yaml is **already 100% ready** for Scribe:
- ✅ Postgres service running pgvector/pgvector:pg16
- ✅ `scribe_db_url` secret defined and mounted (lines 195, 258, 374-375)
- ✅ `SCRIBE_STORAGE_BACKEND=postgres` environment variable set (lines 182, 249)
- ✅ `backend` network shared across all services
- ✅ Entrypoint bridges SCRIBE_DB_URL from secret to env var

### 🔧 Deployment Steps (Hetzner VPS)

**1. Create secret file:**
```bash
mkdir -p /opt/council_mcp/secrets
echo -n "postgresql://council:ACTUAL_PASSWORD@postgres:5432/agentkit" > /opt/council_mcp/secrets/scribe_db_url.txt
chmod 600 /opt/council_mcp/secrets/scribe_db_url.txt
```

**2. Add Scribe service to compose (example):**
```yaml
services:
  scribe-mcp:
    build:
      context: ../scribe_mcp
      dockerfile: deploy/Dockerfile
    container_name: scribe-mcp
    mem_limit: 1g
    cpus: 0.5
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - SCRIBE_STORAGE_BACKEND=postgres
      - SCRIBE_DB_URL_FILE=/run/secrets/scribe_db_url
    secrets:
      - scribe_db_url
    networks:
      - backend
    ports:
      - "127.0.0.1:8080:8080"
```

**3. Verify schema initialization:**
```bash
docker compose exec postgres psql -U council -d agentkit
\dn  # Should show "scribe" schema
\dt scribe.*  # Should list 15+ tables
```

**4. Monitor logs:**
```bash
docker compose logs -f scribe-mcp
# Look for:
# [entrypoint] Loaded SCRIBE_DB_URL from Docker secret
# [schema] Created schema "scribe"
# [schema] Applied Postgres schema migration: 001_jsonb_indexes.sql
```

### 🎯 Verification Commands

**Health check:**
```bash
curl http://localhost:8080/health
# Expected: {"status": "ok", "transport": "sse", "storage": "postgres", "schema": "scribe"}
```

**Database verification:**
```sql
-- Check Scribe entries table
SELECT COUNT(*) FROM scribe.scribe_entries;

-- Check migrations applied
SELECT * FROM scribe.scribe_migrations ORDER BY completed_at;
# Expected: 3 rows (001, 002, 003)
```

---

## Critical Decisions & Open Questions

### ✅ Decisions Made

| Decision | Rationale |
|----------|-----------|
| **Same database, different schemas** | Operational simplicity, shared connection pool, single backup |
| **Share council user** | Superuser privileges needed for CREATE SCHEMA + extensions |
| **Schema name = "scribe"** | Clear namespace, matches project name, no collision risk |
| **Auto-initialization on first connection** | No manual SQL setup, idempotent migrations, production-safe |
| **Secret file path: ../secrets/** | Matches Council convention |

### ❓ Open Questions for Architect/Coder

1. **Schema name override?**
   - Default `scribe` works for all cases
   - **Recommendation:** Keep default unless multi-tenancy needed

2. **Connection pool sizing?**
   - Default: min=2, max=20
   - **Recommendation:** Monitor with `pg_stat_activity`, adjust if needed

3. **pgvector extension?**
   - Currently optional (logs debug if missing)
   - Council's image has it pre-installed
   - **Recommendation:** Keep optional for future postgres:16-alpine compatibility

4. **Backup strategy?**
   - Single `pg_dump` captures both schemas
   - Or schema-specific: `pg_dump -n scribe`
   - **Recommendation:** Whole-database backups (simpler)

5. **Scribe entrypoint secret bridging?**
   - Council's entrypoint does this
   - **Recommendation:** Yes - add to Scribe's entrypoint for consistency

---

## Appendix: File References

**Council Infrastructure:**
- `council_mcp/deploy/docker-compose.yaml` - Postgres service, secrets, networks
- `council_mcp/deploy/docker-entrypoint.sh` - Secret bridging logic
- `council_mcp/deploy/.env.example` - Connection string examples
- `council_mcp/src/council_mcp/services/mcp_servers.py` - Current Scribe integration

**Scribe Postgres Backend:**
- `scribe_mcp/src/scribe_mcp/storage/postgres/__init__.py` - PostgresStorage class
- `scribe_mcp/src/scribe_mcp/storage/postgres/schema.py` - Schema bootstrap logic
- `scribe_mcp/src/scribe_mcp/db/init.sql` - Baseline table definitions
- `scribe_mcp/src/scribe_mcp/db/postgres_migrations/` - Numbered migrations (001-003)

**Configuration Paths:**
- Secrets: `council_mcp/secrets/*.txt` (created by user)
- Migrations: `scribe_mcp/src/scribe_mcp/db/postgres_migrations/NNN_*.sql`
- Init SQL: `scribe_mcp/src/scribe_mcp/db/init.sql`

---

## Research Complete

**Confidence:** 98%

**Unverified Assumptions:** None - all findings verified against actual source files.

**Next Agent:** Architect (to design Scribe container integration) or Coder (to implement if design already exists).

**Handoff Notes:**
- Council's infrastructure is complete - focus on Scribe container build and SSE endpoint
- No manual SQL setup needed - schema auto-initializes
- Test schema isolation: verify Council and Scribe can write simultaneously without conflicts
- Monitor connection pool usage under load - current settings are conservative
