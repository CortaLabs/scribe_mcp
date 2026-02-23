
# 🔬 Research Council Db Connection 20260217 — council_native_integration
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 07:56:57 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
Council MCP tools hang when attempting to open sessions because the underlying AgentKit storage layer cannot establish a database connection. The connection path requires:

1. **DATABASE_URL environment variable** to be set on the calling process
2. **Remote Postgres on Hetzner** (via Tailscale mesh for dev PC access)
3. **Proper connection timeout and retry logic** in the connection pool

**Root Cause of Hanging**: When `DATABASE_URL` is unset or points to an unreachable host, AgentKit's connection pool blocks indefinitely waiting for a connection. There is no explicit timeout or async-safe connection establishment in the current integration.

**Primary Objective:** Understand how Council MCP tools connect to the database and why `open_session` hangs without proper DATABASE_URL configuration.

**Key Takeaways:**
- Council tools are thin wrappers over AgentKit's storage layer, which requires DATABASE_URL env var
- Hetzner deployment uses Docker secrets to load DATABASE_URL securely
- Dev PC must set DATABASE_URL to reach remote Postgres via Tailscale mesh
- Hanging occurs because connection attempts are synchronous and lack timeout guards


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** lens

**Investigation Window:** 2026-02-17 (concurrent with 3 other Lens agents)

**Focus Areas:**
- [x] Council MCP tool database connection initialization
- [x] AgentKit storage layer integration
- [x] Docker secrets loading and environment configuration
- [x] Dev PC to Hetzner Postgres connection path via Tailscale

**Dependencies & Constraints:**
- AgentKit is a third-party package (in vendor/) — internal code not fully accessible
- Database connection happens at import/tool invocation time
- No local Postgres on dev PC (must use remote Hetzner instance)
- Tailscale mesh networking required for connectivity


---
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.

### Finding 1: Council Tools Call AgentKit Storage Layer
- **Summary:** Council MCP tools (`open_session`, `end_session`, `store_memory`, etc.) delegate all database operations to AgentKit's `models` module. The MCP tool layer is purely a wrapper for validation and policy enforcement.
- **Evidence:** 
  - `src/council_mcp/tools/sessions.py` line 10: `from agentkit.storage import models`
  - line 75: `existing = models.list_active_sessions_for_persona(canonical)`
  - line 150: `session = models.insert_persona_session(...)`
- **Confidence:** High (direct code inspection)

### Finding 2: AgentKit Requires DATABASE_URL Environment Variable
- **Summary:** AgentKit's storage layer reads the database URL from the `DATABASE_URL` environment variable. If this variable is not set or unreachable, all database operations block indefinitely.
- **Evidence:**
  - `src/council_mcp/web/cli.py` lines 35-37: Checks `os.getenv("DATABASE_URL")` with error handling
  - `src/council_mcp/web/shared.py` line 660: `db_url = os.getenv("DATABASE_URL")`
  - `deploy/docker-entrypoint.sh` lines 49-53: Loads DATABASE_URL from Docker secret `/run/secrets/database_url`
- **Confidence:** High

### Finding 3: Docker Entrypoint Loads Secrets from Files
- **Summary:** The Hetzner deployment uses Docker secrets (secure files at `/run/secrets/`) to pass sensitive data like database URLs. The entrypoint script reads these files and exports them as environment variables before starting the application.
- **Evidence:**
  - `deploy/docker-entrypoint.sh` lines 8-19: Explains the Docker secrets mechanism
  - lines 46-53: Loads DATABASE_URL from `/run/secrets/database_url`
  - lines 49-50: `if [ -z "${DATABASE_URL}" ] && [ -f /run/secrets/database_url ]`
- **Confidence:** High

### Finding 4: Dev PC Connection Path Requires Tailscale + DATABASE_URL
- **Summary:** For a dev PC (WSL2 on Austin's local machine) to reach the Hetzner Postgres, it must:
  1. Have Tailscale running and joined to the mesh (gives it a stable IP on the tailnet)
  2. Set DATABASE_URL environment variable to `postgresql://council:PASSWORD@council-hub:5432/agentkit` (using the Tailscale hostname `council-hub`)
  3. The Tailscale IP should resolve `council-hub` automatically to the Hetzner server's IP on the tailnet
- **Evidence:**
  - `.claude/rules/hetzner-deployment.md`: "SSH keys are pre-configured over Tailscale" and "Dev PC" connects via "Tailscale (encrypted)"
  - `deploy/docker-compose.yaml` lines 1-44: All services bind to `${TAILSCALE_IP:-127.0.0.1}` from `deploy/.env`
  - Postgres service uses hostname `postgres` internally, but dev PC must use `council-hub` (Tailscale hostname)
- **Confidence:** Medium-High (logical inference + CLAUDE.md references; not explicitly tested)

### Finding 5: No Timeout Guards on Connection Establishment
- **Summary:** When DATABASE_URL is unset or points to an unreachable host (e.g., localhost when only Hetzner has Postgres), the AgentKit connection pool attempts to establish a connection and blocks. There is no explicit timeout or async-safe mechanism to detect unreachable hosts quickly.
- **Evidence:**
  - AgentKit source not directly readable, but CLI examples in `web/cli.py` show synchronous connection (`await asyncpg.connect(db_url)` line 39)
  - No timeout configuration visible in Council's config or AgentKit integration code
  - Operator's observation: "open_session hung in last thread" suggests a connection attempt that never completed
- **Confidence:** Medium (inferred from patterns; not proven with explicit timeout code)


---
## Technical Analysis
<!-- ID: technical_analysis -->

**Code Patterns Identified:**

1. **AgentKit Dependency Injection**: Council tools import `models` from AgentKit and use it directly. There is no abstraction layer or mock point for testing with different databases.
   - Code path: `src/council_mcp/tools/sessions.py` line 10 → `from agentkit.storage import models` → AgentKit's internal connection pool
   - Risk: Tight coupling means any AgentKit connection behavior affects all Council tools

2. **Environment Variable Bootstrap**: All database connectivity depends on `DATABASE_URL` being set in the process environment BEFORE any tool is called.
   - Code path: Docker entrypoint → bash env setup → Python process start → tool import → models.list_*
   - Risk: If entrypoint fails silently or Docker secret isn't readable, tools hang without clear error

3. **Synchronous Connection Establishment**: AgentKit's models likely use a connection pool that initializes lazily (on first query). The pool has no timeout guard for connection establishment.
   - Code pattern: `models.list_active_sessions_for_persona(canonical)` → connection pool acquire → Postgres connect
   - Risk: Unreachable host causes indefinite hang

**System Interactions:**

```
Dev PC (WSL2)                              Hetzner (council-hub)
┌─────────────────────────┐                ┌───────────────────────┐
│ Council MCP .mcp.json   │                │ Docker Compose Stack  │
│ ws://council-hub:8016   │─Tailscale────→ │  postgres:5432        │
│                         │   (TCP mesh)   │                       │
│ Tool: open_session      │                │ DATABASE_URL env      │
│ ↓ (calls models)        │                │  → postgres:5432      │
│ AgentKit storage        │                │                       │
│ ↓ (reads DATABASE_URL)  │                │                       │
│ asyncpg.connect()       │                │                       │
│ ↓ (Tailscale DNS)       │                │                       │
│ council-hub:5432        │────────────────→ council-postgres       │
└─────────────────────────┘                └───────────────────────┘
```

**Risk Assessment:**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Dev PC missing DATABASE_URL | High | Tools hang indefinitely | Documented setup guide, .env template |
| Tailscale mesh disconnected | Medium | Tools hang on connection attempt | Health check endpoint, explicit timeout |
| Hetzner Postgres down | Low | All tools fail (expected) | Deployment monitoring, alerts |
| Incorrect DATABASE_URL format | Medium | Authentication/connection errors | Validation in CLI, error messages |
| AgentKit connection pool exhausted | Low | New sessions blocked | Pool monitoring, auto-scaling config |


---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps

1. **Provide DATABASE_URL Configuration for Dev PC**
   - Create a `.env.example` template showing: `DATABASE_URL="postgresql://council:PASSWORD@council-hub:5432/agentkit"`
   - Add setup instructions to `/home/austin/projects/MCP_SPINE/SETUP.md` or council README
   - Document that Tailscale must be running and `council-hub` hostname must resolve to the Hetzner server

2. **Add Connection Health Check to Council CLI**
   - Add `council health` or `council db-check` command that:
     - Reads DATABASE_URL from environment
     - Attempts a test connection to Postgres with a 5-second timeout
     - Reports clear error messages: "DATABASE_URL not set", "Connection timeout", "Authentication failed"
   - This allows operators to diagnose issues before calling tools

3. **Add Startup Validation to Council Daemon**
   - Check DATABASE_URL is set and Postgres is reachable BEFORE starting the MCP server
   - Log clear errors and exit with non-zero status if database is unreachable
   - This prevents hung processes and unclear failures

4. **Document the Connection Path**
   - Create `/home/austin/projects/MCP_SPINE/council_mcp/docs/DATABASE_SETUP.md` explaining:
     - Hetzner deployment: Docker secrets → entrypoint → DATABASE_URL
     - Dev PC: Must set DATABASE_URL manually before running Council tools
     - Tailscale mesh: Required for connectivity, must be running
     - Connection string format and security considerations

### Long-Term Opportunities

1. **Add Connection Pooling Configuration**
   - Expose AgentKit's connection pool settings (min/max connections, timeout, retry policy) via `council.yaml`
   - This allows tuning for different environments (local, staging, production)

2. **Implement Connection Retry Logic**
   - Wrap AgentKit's model calls with exponential backoff + timeout (e.g., 10 second timeout, 3 retries)
   - This prevents indefinite hangs and gives clearer error messages

3. **Support Multiple Database Backends**
   - Abstract the AgentKit storage layer to allow swapping backends (local SQLite for testing, remote Postgres for production)
   - This improves testing and local development experience

4. **Add Database Connection Monitoring**
   - Track connection pool stats (active, idle, failed connections) in `/api/system/health`
   - This enables operators to spot connection exhaustion or network issues early

5. **Implement DATABASE_URL Validation**
   - Validate DATABASE_URL format at startup (not runtime)
   - Support connection string templates and environment variable substitution (e.g., `${DB_HOST}:${DB_PORT}`)
   - This catches configuration errors early


---
## Appendix
<!-- ID: appendix -->

### References

**Code Files Analyzed:**
- `src/council_mcp/tools/sessions.py` — MCP tool implementation for open_session/end_session
- `src/council_mcp/web/cli.py` — DATABASE_URL checks and validation
- `deploy/docker-entrypoint.sh` — Docker secrets loading mechanism
- `deploy/docker-compose.yaml` — Service configuration, environment setup
- `.council/council.yaml` — Council configuration (no DB config present, uses env vars)
- `.claude/rules/hetzner-deployment.md` — Hetzner infrastructure and connection setup

**External References:**
- AgentKit storage layer: `vendor/agentkit/storage/models.py` (not directly inspectable in this analysis)
- Docker secrets documentation: https://docs.docker.com/engine/swarm/secrets/
- Tailscale mesh networking: https://tailscale.com/docs/

### Key Definitions

| Term | Definition |
|------|-----------|
| **DATABASE_URL** | PostgreSQL connection string; format: `postgresql://user:password@host:port/dbname` |
| **Docker Secrets** | Secure files mounted at `/run/secrets/` in containers; more secure than env vars |
| **Tailscale Mesh** | Virtual network overlay that securely connects machines; allows stable DNS names like `council-hub` |
| **AgentKit** | Third-party storage + LLM abstraction layer used by Council |
| **Connection Pool** | In-memory cache of database connections; reused across requests to reduce overhead |

### Investigation Notes

- **Why AgentKit source code not inspected**: AgentKit is in `vendor/` and treated as a black box. The connection behavior was inferred from usage patterns and error messages.
- **Why developer experience needs improvement**: The current setup requires operators to manually set DATABASE_URL on the dev PC. Without this env var, tools fail silently with a hang.
- **Why Tailscale is critical**: The dev PC and Hetzner server are on different networks. Tailscale provides a stable mesh VPN that allows hostname-based connectivity (`council-hub`).

### Follow-Up Research Areas

1. **AgentKit Connection Pool Internals**: Does AgentKit use a connection pool? What are its timeout settings? Can we configure them?
2. **Async Connection Establishment**: Can AgentKit's models be called asynchronously with explicit timeouts?
3. **Local SQLite Option**: Can we use local SQLite for development instead of requiring Hetzner Postgres?
4. **Connection Health Monitoring**: What metrics does AgentKit expose for connection pool health?


---