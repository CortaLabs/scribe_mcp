---
id: council_native_integration-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_native_integration"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 08:08:17 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — council_native_integration
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 07:53:55 UTC

> Architecture guide for council_native_integration.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
### Context

Council MCP is a multi-agent orchestration system deployed on Hetzner CCX23 (16GB RAM, 4 vCPU) behind Tailscale mesh networking. The operator's primary workflow is through the **production Hetzner web UI** (council-web on port 8015), with the dev PC serving as a **Ray worker** (GPU: RTX 4070) for compute-heavy tasks and as a **Claude Code client** that connects to the daemon via ws_proxy.

Currently, Council tools (open_session, store_memory, etc.) hang when invoked. The system lacks a formal operating mode model, and downstream councils (other repos) have no established pattern for connecting to central Hetzner services.

### Goals

1. **Fix hanging tools** — Diagnose and resolve the root cause of Council MCP tool hangs
2. **Operating Mode System** — Implement SERVER/CLIENT/STANDALONE mode detection (inspired by Scribe's proven pattern)
3. **Connection Reliability** — Add timeout guards and health checks to prevent indefinite hangs
4. **Dev/Prod Config** — Simple mechanism for the operator to toggle between dev and prod environments
5. **Downstream Council Support** — When `council init` runs in another repo, generate correct config to connect to central Hetzner services
6. **Ray Compute Mode Awareness** — Wire operating mode into Ray dispatch: SERVER enables direct Ray, CLIENT delegates compute to server, STANDALONE uses CPU-only

### Non-Goals

- Redesigning the Ray compute layer (it is 100% feature-complete)
- Building a new web UI
- Supporting non-Tailscale networking
- Multi-tenant isolation (each operator runs their own Hetzner instance)
- Config profiles system (environment variables are sufficient for dev/prod switching)

### Success Metrics

- `open_session` completes in <5 seconds from Claude Code on dev PC
- Daemon starts with clear error messages if DATABASE_URL is missing or Postgres unreachable
- Downstream councils can connect to central services with `council init --parent`
- Health endpoint reports operating mode, DB status, and Ray cluster state
<!-- ID: requirements_constraints -->
### Functional Requirements

1. **Operating Mode Detection** — Automatically detect SERVER, CLIENT, or STANDALONE at daemon startup
2. **Database Connection Guards** — Validate DATABASE_URL at startup; fail fast with clear error if Postgres unreachable (5s timeout)
3. **Health Endpoint Enhancement** — `/api/system/health` reports: operating mode, DB connectivity, Ray cluster status, Scribe connectivity
4. **Downstream Config Generation** — `council init --parent` generates correct `council.yaml` with hub connection settings
5. **Dev/Prod Switching** — Environment variable overrides (`COUNCIL_DEPLOYMENT__MODE=remote`) toggle between environments

### Non-Functional Requirements

- All config values through `council.yaml` + env vars (never hardcoded)
- Connection attempts must have explicit timeouts (max 5s for DB, 3s for health probes)
- Backwards compatible — existing deployments must not break
- Template system generates `council.yaml` sections via Jinja2
- Docker secrets loading unchanged (proven pattern)

### Assumptions

- Tailscale mesh provides reliable DNS resolution (`council-hub` hostname)
- Hetzner CCX23 has sufficient resources for all services (current allocation: 7 vCPU on 4 vCPU with overcommit)
- AgentKit reads DATABASE_URL from environment at first query (lazy connection pool init)
- ws_proxy on dev PC relays tool calls to daemon — tools execute daemon-side where secrets are loaded

### Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tailscale mesh disconnected | Medium | Tools hang | Timeout guard + clear error message |
| DATABASE_URL secret not loaded | Low (entrypoint handles) | Daemon can't start | Startup validation with fail-fast |
| AgentKit pool blocks indefinitely | High (current bug) | Tools hang forever | Wrap with 5s timeout at connection level |
| Downstream council misconfigured | Medium | Tools fail | Validation during `council init` |
| Ray head unreachable | Low | Embeddings fall back to CPU | Existing fallback mechanism (working) |
<!-- ID: architecture_overview -->
### Solution Summary

Council MCP adopts a three-mode operating model inspired by Scribe MCP's production-proven pattern. The system automatically detects its operating mode at startup and configures all subsystems (database, compute, health) accordingly. The key insight is that Council already has a working two-mode architecture (daemon on Hetzner with Docker secrets vs. ws_proxy relay from dev PC) -- we formalize this with explicit mode detection, connection guards, and health reporting.

### Operating Modes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Operating Mode Detection                         │
│                                                                         │
│  Priority 1: COUNCIL_MODE env var (explicit override)                   │
│  Priority 2: DATABASE_URL set + Postgres reachable → SERVER             │
│  Priority 3: COUNCIL_HUB_URL set + daemon reachable → CLIENT            │
│  Priority 4: Fallback → STANDALONE                                      │
└─────────────────────────────────────────────────────────────────────────┘

  SERVER Mode (Hetzner daemon)           CLIENT Mode (dev PC ws_proxy)
  ┌─────────────────────────┐            ┌─────────────────────────┐
  │ Direct Postgres access  │            │ ws_proxy → daemon WS    │
  │ Docker secrets loaded   │            │ Tool exec is daemon-side│
  │ Ray head node available │            │ No local DB needed      │
  │ Full tool execution     │            │ Ray worker can join     │
  │ Health endpoint active  │            │ Lightweight process     │
  └─────────────────────────┘            └─────────────────────────┘

  STANDALONE Mode (local dev / CI)
  ┌─────────────────────────┐
  │ No remote services      │
  │ CPU-only embeddings     │
  │ Degraded but functional │
  │ For testing/CI only     │
  └─────────────────────────┘
```

### Critical Architecture Insight: ws_proxy Relay

The dev PC does NOT execute tools locally. The `.mcp.json` configuration points Claude Code to `ws://council-hub:8016/mcp` via the ws_proxy module. All tool calls are relayed to the daemon on Hetzner, where:
- Docker entrypoint has loaded secrets (DATABASE_URL, OPENAI_API_KEY, etc.)
- AgentKit storage layer has access to Postgres
- Ray head node is on the same network

**Therefore**: The "hanging tools" fix is about ensuring the daemon is healthy and the ws_proxy connection succeeds — NOT about setting DATABASE_URL on the dev PC.

### Component Architecture

```
Dev PC (WSL2)                              Hetzner CCX23 (council-hub)
┌──────────────────────┐                   ┌────────────────────────────────┐
│                      │                   │  council-daemon (port 8016)    │
│ Claude Code          │                   │  ┌──────────────────────────┐  │
│   │                  │                   │  │ OperatingMode: SERVER    │  │
│   └→ ws_proxy.py ────┼── Tailscale ────→ │  │ init_council()           │  │
│      (relay only)    │   (WebSocket)     │  │   └→ DB health check     │  │
│                      │                   │  │   └→ AgentKit init       │  │
│ Ray Worker ──────────┼── Tailscale ────→ │  │   └→ Mode detection      │  │
│   (GPU: RTX 4070)    │   (port 6379)    │  │ FastMCP tool handlers    │  │
│                      │                   │  │   └→ models.* (Postgres) │  │
│                      │                   │  └──────────────────────────┘  │
│                      │                   │                                │
│                      │                   │  postgres (port 5432)          │
│                      │                   │  ray-head (port 6379, 8265)    │
│                      │                   │  scribe (port 8200)            │
│                      │                   │  council-web (port 8015)       │
│                      │                   │  corta-store (port 8201)       │
└──────────────────────┘                   └────────────────────────────────┘
```

### Data Flow: Tool Execution Path

```
1. Claude Code calls open_session(persona_id="atlas")
2. ws_proxy.py serializes MCP message, sends to ws://council-hub:8016/mcp
3. Daemon's FastMCP server receives tool call
4. Tool handler imports agentkit.storage.models
5. models.list_active_sessions_for_persona() → Postgres connection pool
6. Postgres responds via Docker network (container-to-container)
7. Result returned via WebSocket → ws_proxy → Claude Code
```

### External Integrations

- **AgentKit** — Storage layer, LLM factory, embeddings (vendored wheel in `vendor/`)
- **Scribe MCP** — Logging and documentation (separate container, daemon proxies)
- **Ray Cluster** — Distributed compute (head on Hetzner, workers via Tailscale)
- **CortaStore** — Object storage for large artifacts
- **Tailscale** — Encrypted mesh networking between all nodes
<!-- ID: detailed_design -->
### 4.1 Operating Mode Detection Module

**New file**: `src/council_mcp/config/operating_mode.py`

```python
import enum
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

class OperatingMode(enum.Enum):
    SERVER = "server"       # Hetzner daemon — direct Postgres, Ray head available
    CLIENT = "client"       # Dev PC — ws_proxy relay, no local DB
    STANDALONE = "standalone"  # Local dev / CI — no remote services

async def _probe_postgres(url: str, timeout: float = 5.0) -> bool:
    """Test Postgres connectivity with explicit timeout."""
    try:
        import asyncpg
        conn = await asyncio.wait_for(
            asyncpg.connect(url),
            timeout=timeout
        )
        await conn.close()
        return True
    except Exception as e:
        logger.warning("Postgres probe failed: %s", e)
        return False

async def _probe_daemon(url: str, timeout: float = 3.0) -> bool:
    """Health-check the remote daemon."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{url}/health")
            return resp.status_code == 200
    except Exception:
        return False

async def detect_operating_mode() -> OperatingMode:
    """Detect operating mode with Scribe-inspired priority chain."""
    # Priority 1: Explicit override
    explicit = os.getenv("COUNCIL_MODE", "").strip().lower()
    if explicit in ("server", "client", "standalone"):
        logger.info("Operating mode from COUNCIL_MODE env: %s", explicit)
        return OperatingMode(explicit)

    # Priority 2: DATABASE_URL present + Postgres reachable → SERVER
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        if await _probe_postgres(db_url):
            logger.info("Operating mode: SERVER (DATABASE_URL set, Postgres reachable)")
            return OperatingMode.SERVER
        else:
            logger.warning("DATABASE_URL set but Postgres unreachable — NOT entering SERVER mode")

    # Priority 3: COUNCIL_HUB_URL set + daemon reachable → CLIENT
    hub_url = os.getenv("COUNCIL_HUB_URL", "")
    if hub_url:
        if await _probe_daemon(hub_url):
            logger.info("Operating mode: CLIENT (hub daemon reachable at %s)", hub_url)
            return OperatingMode.CLIENT
        else:
            logger.warning("COUNCIL_HUB_URL set but daemon unreachable — falling through")

    # Priority 4: Fallback
    logger.info("Operating mode: STANDALONE (no remote services detected)")
    return OperatingMode.STANDALONE

def detect_operating_mode_sync() -> OperatingMode:
    """Synchronous wrapper for mode detection."""
    return asyncio.run(detect_operating_mode())
```

**Design rationale**: Mirrors Scribe's `config/mode_detection.py` (Finding 1) but adapted for Council's architecture. The probe functions have explicit timeouts to prevent the hanging bug. The sync wrapper enables use during `init_council()` which is called from `main()`.

### 4.2 Database Connection Guard

**Modified file**: `src/council_mcp/server.py` (in `init_council()`)

Add a connection health check BEFORE AgentKit initialization:

```python
# In init_council(), before resolve_project_id_via_adapter():
from council_mcp.config.operating_mode import detect_operating_mode_sync, OperatingMode

mode = detect_operating_mode_sync()
_RUNTIME_CONTEXT["operating_mode"] = mode.value

if mode == OperatingMode.SERVER:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        raise SystemExit(
            "SERVER mode requires DATABASE_URL. "
            "Check Docker secrets at /run/secrets/database_url"
        )
    # AgentKit init proceeds normally — DB is reachable (confirmed by probe)

elif mode == OperatingMode.STANDALONE:
    logger.warning(
        "STANDALONE mode — Council tools requiring database will fail. "
        "Set DATABASE_URL or COUNCIL_HUB_URL to connect to Hetzner."
    )
```

### 4.3 Config System Enhancement

**Modified file**: `src/council_mcp/config.py`

Add new config keys to `DEFAULT_CONFIG["council"]`:

```python
# In DEFAULT_CONFIG["council"]:
"connection": {
    "db_connect_timeout_seconds": 5,     # Postgres connection probe timeout
    "daemon_health_timeout_seconds": 3,  # Daemon health check timeout
    "startup_fail_fast": True,           # Fail startup if DB unreachable in SERVER mode
},
```

Add corresponding env override mappings in `_apply_env_overrides()`:

```python
# COUNCIL_CONNECTION__DB_CONNECT_TIMEOUT_SECONDS
# COUNCIL_CONNECTION__DAEMON_HEALTH_TIMEOUT_SECONDS
# COUNCIL_CONNECTION__STARTUP_FAIL_FAST
```

### 4.4 Health Endpoint Enhancement

**Modified file**: `src/council_mcp/web/routes/system.py` (or `tools/daemon.py`)

Extend the `/api/system/health` response:

```python
{
    "status": "healthy",
    "operating_mode": "server",          # NEW
    "database": {                        # NEW
        "connected": true,
        "url_masked": "postgresql://council:***@postgres:5432/agentkit",
        "latency_ms": 12
    },
    "compute": {                         # Existing (from ComputeDispatcher.health())
        "ray_enabled": true,
        "ray_initialized": true,
        "cluster": { "CPU": 21.0, "GPU": 1.0 }
    },
    "scribe": {                          # NEW
        "connected": true,
        "mode": "server"
    }
}
```

### 4.5 Downstream Council Config Generation

**Modified file**: `src/council_mcp/cli/init_cmd.py` (in `_build_council_yaml()`)

When `--parent` is specified, inject hub connection settings:

```python
# In _build_council_yaml(), after loading defaults:
if parent_council_name:
    # Fetch parent's deployment config via API
    parent_config = _fetch_parent_config(parent_council_name, api_key)
    if parent_config:
        config["council"]["deployment"]["mode"] = "remote"
        config["council"]["deployment"]["hub_tailscale_ip"] = parent_config["hub_ip"]
        # Generate env var guidance
        config["_setup_notes"] = {
            "DATABASE_URL": f"postgresql://council:PASSWORD@{parent_config['hub_ip']}:5432/agentkit",
            "COUNCIL_HUB_URL": f"http://{parent_config['hub_ip']}:8016",
        }
```

### 4.6 Ray Compute Mode Integration

**Modified file**: `src/council_mcp/compute/dispatcher.py`

Wire operating mode into compute dispatch logic:

```python
# In ComputeDispatcher.__init__():
from council_mcp.server import get_runtime_context

mode = get_runtime_context().get("operating_mode", "standalone")
if mode == "server":
    # Direct Ray dispatch available (head node on same network)
    self._ray_enabled = cfg.get("ray_enabled", False)
elif mode == "standalone":
    # Force CPU-only regardless of config
    self._ray_enabled = False
# CLIENT mode: tools execute daemon-side, so this code path is never hit
# on dev PC — the daemon is in SERVER mode
```

**Note**: This is a minor enhancement. Since tools execute daemon-side (SERVER mode), the dispatcher already has correct access to Ray. This change only matters if someone runs a daemon locally in STANDALONE mode.
<!-- ID: directory_structure -->
### New Files

```
src/council_mcp/
├── config/
│   ├── __init__.py                    # NEW: Package init
│   └── operating_mode.py              # NEW: OperatingMode enum + detection logic
```

### Modified Files

```
src/council_mcp/
├── config.py                          # MODIFIED: Add connection config section to DEFAULT_CONFIG
│                                      #           Add env overrides for COUNCIL_CONNECTION__*
│                                      #           Add to templates/defaults/council.yaml
├── server.py                          # MODIFIED: Add mode detection in init_council()
│                                      #           Store operating_mode in _RUNTIME_CONTEXT
│                                      #           Add DB health check before AgentKit init
├── compute/
│   └── dispatcher.py                  # MODIFIED: Wire operating_mode into dispatch decisions
├── cli/
│   └── init_cmd.py                    # MODIFIED: Generate hub config for downstream councils
├── web/
│   └── routes/system.py               # MODIFIED: Enhance /api/system/health response
├── tools/
│   └── daemon.py                      # MODIFIED: Expose operating_mode in MCP health tool
│
├── templates/
│   └── defaults/
│       └── council.yaml               # MODIFIED: Add connection section with defaults
│
└── deploy/
    └── docker-compose.yaml            # MODIFIED: Add COUNCIL_MODE=server env var (explicit)
```
<!-- ID: data_storage -->
### Database Architecture (Unchanged)

- **Single shared Postgres** on Hetzner: `agentkit` database
- **Schemas**: `public` (AgentKit), `council` (extensions), `scribe`, `knowledge`
- **Connection**: Docker secrets load `DATABASE_URL` into environment
- **AgentKit pool**: Lazy init on first query, connection pool managed internally

### Operating Mode Impact on Storage

| Mode | Primary Storage | Session Cache | Embeddings |
|------|----------------|---------------|------------|
| SERVER | Direct Postgres (container network) | In-process memory | Ray GPU or CPU fallback |
| CLIENT | Delegated to daemon via ws_proxy | N/A (daemon handles) | N/A (daemon handles) |
| STANDALONE | None (tools fail gracefully) | In-process memory | CPU-only local |

### Connection String Patterns

```
# SERVER (Hetzner, container-to-container)
DATABASE_URL=postgresql://council:<secret>@postgres:5432/agentkit

# Dev PC pointing to Hetzner (for direct DB access if needed, but NOT required for tools)
DATABASE_URL=postgresql://council:<secret>@council-hub:5432/agentkit

# STANDALONE (no database)
# DATABASE_URL is not set — tools that need DB will return clear error
```
<!-- ID: testing_strategy -->
### Unit Tests

- `tests/test_operating_mode.py` — Test mode detection priority chain with mocked env vars and probes
- `tests/test_config_connection.py` — Verify new config keys exist in DEFAULT_CONFIG and defaults YAML

### Integration Tests

- `tests/test_server_init.py` — Test `init_council()` with mocked Postgres probe (SERVER mode passes, STANDALONE warns)
- `tests/test_health_endpoint.py` — Verify `/api/system/health` includes operating_mode, database, and scribe sections

### E2E Validation

- SSH to council-hub: `docker compose logs council-daemon | grep "Operating mode"` — confirms SERVER mode
- Claude Code: call `open_session(persona_id="atlas")` — completes in <5 seconds
- `council connect status` from dev PC — Ray worker sees head node

### Test Persona Policy

All tests use the `test_agent` fixture from `conftest.py`. No unique persona profiles created.
<!-- ID: deployment_operations -->
### Hetzner Deployment (Production)

Docker Compose stack unchanged. Single addition:

```yaml
# In deploy/docker-compose.yaml, council-daemon service:
environment:
  COUNCIL_MODE: "server"  # Explicit — daemon always runs in SERVER mode
```

Docker secrets continue to provide DATABASE_URL, OPENAI_API_KEY, etc. via the entrypoint script. No changes to the secret loading mechanism.

### Dev PC Setup (Client)

The dev PC uses the ws_proxy to relay tool calls. No DATABASE_URL needed on the dev PC for tool execution. However, for running the Ray worker:

```bash
# Required: Tailscale running, council-hub resolvable
# Tool calls: Handled by ws_proxy → daemon (no local DB needed)
# Ray worker: council connect start (joins cluster via Tailscale:6379)
```

### Downstream Council Setup

```bash
# In a new repo:
council init --name my-project --parent council-mcp --auto-register --api-key $KEY
# This generates .council/council.yaml with:
#   deployment.mode: "remote"
#   deployment.hub_tailscale_ip: <auto-detected>
# And a .env.example with:
#   DATABASE_URL=postgresql://council:PASSWORD@<hub_ip>:5432/agentkit
```

### Quick Deploy

```bash
# One-liner deploy after code changes:
git push origin master && ssh council-hub "cd /opt/council_mcp && git pull && docker compose -f deploy/docker-compose.yaml up -d"
```

### Monitoring

- **Health endpoint**: `curl http://council-hub:8016/health` — operating mode, DB status, Ray cluster
- **Daemon logs**: `ssh council-hub "docker compose -f /opt/council_mcp/deploy/docker-compose.yaml logs --tail 50 council-daemon"`
- **Ray dashboard**: `http://council-hub:8265` — cluster resources, active tasks
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Why exactly do tools hang? | Mantis | BLOCKED on Phase 0 | ws_proxy relay works but daemon may not be starting properly. Phase 0 Task 0.1 adds diagnostic logging to determine exact failure point. |
| Should asyncpg be patched with connect_timeout? | Blueprint | DECIDED | Yes — but at the probe level, not globally. We wrap asyncpg.connect() in asyncio.wait_for() in the operating_mode module. AgentKit's internal pool is left alone. |
| Do downstream councils need their own DB? | Blueprint | DECIDED | No. Shared central DB with AgentKit schema isolation per council. Each council gets `council_<slug>` schema for custom tables. |
| Should we adopt Scribe's RemoteStorageBackend pattern? | Blueprint | DEFERRED | Not in this project. Council tools already execute daemon-side via ws_proxy. A full remote backend would be needed only if we wanted offline-capable local tools, which is not a current requirement. |
| Config profiles (dev/prod presets)? | Blueprint | DEFERRED | Environment variable overrides are sufficient. Config profiles add complexity without clear benefit for a single-operator system. |

Close each question once answered and reference the relevant section above.
<!-- ID: references_appendix -->
### Research Documents

1. `RESEARCH_COUNCIL_DB_CONNECTION_20260217.md` — Root cause analysis of hanging tools
2. `RESEARCH_CONFIG_DEVPROD_DOWNSTREAM.md` — Config system and downstream council support
3. `RESEARCH_RAY_EMBEDDINGS_INTEGRATION_20260217.md` — Ray compute layer status
4. `RESEARCH_SCRIBE_REMOTE_DB_PATTERN.md` — Scribe's 3-mode operating pattern

### Key Source Files

| File | Lines | Relevance |
|------|-------|-----------|
| `src/council_mcp/server.py` | 1126-1237 | `main()` and `init_council()` — startup and mode entry point |
| `src/council_mcp/config.py` | 785-820 | `DEFAULT_CONFIG` — deployment and compute sections |
| `src/council_mcp/config.py` | 2432-2476 | `get_deployment_config()`, `get_service_host()`, `get_service_url()` |
| `src/council_mcp/ws_proxy.py` | full | WebSocket relay — pure message forwarding |
| `src/council_mcp/compute/dispatcher.py` | full | ComputeDispatcher dual-mode architecture |
| `src/council_mcp/compute/embeddings.py` | full | Embedding bridge with Ray routing |
| `deploy/docker-entrypoint.sh` | 46-88 | Docker secrets loading |
| `deploy/docker-compose.yaml` | full | Service definitions and resource limits |

### Scribe Patterns Adopted

| Pattern | Scribe Source | Council Adaptation |
|---------|--------------|-------------------|
| OperatingMode enum | `scribe_mcp/config/mode_detection.py` | Same 3-mode enum, different detection logic |
| Health probe during mode detection | `mode_detection.py:64-75` | `_probe_postgres()` and `_probe_daemon()` with timeouts |
| Environment-driven config | `scribe_mcp/config/settings.py` | Extended `_apply_env_overrides()` with new connection keys |

### Patterns NOT Adopted (and why)

| Pattern | Scribe Source | Why Not |
|---------|--------------|---------|
| RemoteStorageBackend | `scribe_mcp/storage/remote.py` | Council tools already execute daemon-side via ws_proxy; no need for HTTP proxy layer |
| AgentIdentity | `scribe_mcp/state/agent_identity.py` | Council tracks identity through persona profiles + sessions in Postgres, not local state |
| In-memory session cache | `remote.py:38-45` | Sessions are already in Postgres with full persistence; local caching adds complexity |

### Architectural Decision Records

| Decision | Options Considered | Chosen | Rationale |
|----------|-------------------|--------|-----------|
| Operating mode detection | (A) Config-only flag, (B) Scribe-style auto-detection, (C) Env var only | B — Auto-detection with env override | Most resilient; adapts to environment without manual config |
| DB timeout approach | (A) Patch AgentKit pool, (B) Wrap probe externally, (C) Both | B — External probe | AgentKit is vendored; external wrap gives control without forking |
| Downstream DB architecture | (A) Separate DB per council, (B) Shared DB with schema isolation | B — Shared DB | Matches AgentKit's existing schema isolation; simpler ops |
| Dev/prod switching | (A) Config profiles, (B) Env var overrides, (C) Separate config files | B — Env var overrides | Simplest; already supported via `_apply_env_overrides()` |
