---
id: council_native_integration-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_native_integration"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 08:10:28 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_native_integration
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-17 07:53:55 UTC

> Execution roadmap for council_native_integration.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 0 — Diagnose & Fix Hanging Tools | Get Council MCP tools working from dev PC | Diagnostic logs, root cause fix, verified open_session | 0.95 — Task 0.1 complete (diagnostic logs added, tool tests pass; open bug: sentence-transformers missing on daemon) |
| Phase 1 — Operating Mode Detection | Formalize SERVER/CLIENT/STANDALONE modes | OperatingMode module, config keys, init_council integration | 1.0 — Tasks 1.1 + 1.2 ✅ Complete (32/32 tests passing, config package rename done) |
| Phase 2 — Health & Observability | Enhanced health reporting for all subsystems | /api/system/health upgrade, DB/Ray/Scribe status, council status CLI | 0.90 |
| Phase 3 — Downstream Council Support | Enable other repos to connect to central Hetzner | council init --parent config generation, .env.example, validation | 0.80 |

**Ordering rationale**: Phase 0 must come first — everything else depends on working tools. Phase 1 formalizes the operating model. Phase 2 makes the system observable. Phase 3 extends to downstream repos.
<!-- ID: phase_0 -->
**Objective:** Get Council MCP tools working end-to-end from the dev PC. This is the critical blocker — all subsequent phases depend on functional tool execution.

**Key Insight from Research:** The ws_proxy is a pure WebSocket relay. Tool execution happens daemon-side on Hetzner where Docker secrets provide DATABASE_URL. The hang is either: (1) daemon not running or not healthy, (2) ws_proxy connection failing, or (3) AgentKit DB pool blocking during init.

---

### Task Package 0.1: Diagnose the Exact Hang Point

**Scope**: Add diagnostic logging to trace exactly where the tool call hangs in the execution chain.
**Files to Modify**: `src/council_mcp/server.py`, `src/council_mcp/ws_proxy.py`
**Dependencies**: None (first task)

#### Specifications

1. In `server.py` `init_council()` (~line 395), add timing logs:
   ```python
   import time
   t0 = time.monotonic()
   logger.info("[DIAG] init_council starting, DATABASE_URL=%s", "SET" if os.getenv("DATABASE_URL") else "UNSET")
   ```
   Add similar timing log before and after `resolve_project_id_via_adapter()` (line 436) and after AgentKit imports (line 410-419).

2. In `server.py` `main()` (line 1126), add log BEFORE `init_council()`:
   ```python
   logger.info("[DIAG] main() starting, transport=%s", parsed.transport)
   ```

3. In `ws_proxy.py`, add connection lifecycle logs:
   - Log when WebSocket connection to daemon is established
   - Log when WebSocket connection fails with the exact error
   - Log when a tool call message is sent and when the response is received (with elapsed time)

#### Verification
- [ ] Deploy to Hetzner: `ssh council-hub "cd /opt/council_mcp && git pull && docker compose -f deploy/docker-compose.yaml up -d"`
- [ ] Check daemon logs: `ssh council-hub "docker compose -f /opt/council_mcp/deploy/docker-compose.yaml logs --tail 20 council-daemon"` — shows `[DIAG]` timing logs
- [ ] From dev PC, call `open_session` via Claude Code — either succeeds or diagnostic logs reveal the exact hang point

#### Out of Scope (DO NOT TOUCH)
- Do not modify AgentKit internals
- Do not change Docker secrets loading
- Do not modify tool handler logic
- Do not add new config keys yet

---

### Task Package 0.2: Fix the Root Cause

**Scope**: Based on 0.1 diagnostics, apply the targeted fix. The most likely scenarios and their fixes:
**Files to Modify**: Depends on diagnosis — likely `src/council_mcp/server.py` and/or `deploy/docker-compose.yaml`
**Dependencies**: Task 0.1 must be completed and diagnostics reviewed

#### Scenario A: Daemon not starting properly
- Check Docker Compose `council-daemon` service status and logs
- Verify `docker-entrypoint.sh` is loading DATABASE_URL from `/run/secrets/database_url`
- Fix: ensure service dependencies (postgres healthy before daemon starts)

#### Scenario B: AgentKit DB pool blocking during init_council()
- The `resolve_project_id_via_adapter()` call at line 436 queries Postgres
- If this blocks, wrap with `asyncio.wait_for(timeout=5.0)` or use the sync retry logic that already exists (lines 433-451) but add explicit connection timeout
- Fix: Add `statement_timeout` to the DATABASE_URL or wrap the blocking call

#### Scenario C: ws_proxy can't reach daemon
- Verify Tailscale connectivity: `ping council-hub` from dev PC
- Check daemon is listening on port 8016: `ssh council-hub "netstat -tlnp | grep 8016"`
- Fix: network/firewall issue, not code

#### Verification
- [ ] `open_session(persona_id="atlas")` completes in <5 seconds from dev PC
- [ ] `store_memory(persona_id="atlas", text="test")` completes successfully
- [ ] `end_session(session_id="...", persona_id="atlas")` completes successfully
- [ ] Daemon logs show clean startup with no `[DIAG]` warnings about unreachable services

#### Out of Scope (DO NOT TOUCH)
- Do not implement OperatingMode yet (that is Phase 1)
- Do not modify health endpoints
- Do not modify config system
- Do not touch Ray compute layer

---

**Phase 0 Deliverables:**
- Working tool execution from dev PC via ws_proxy
- Diagnostic logging that can be kept as permanent infrastructure
- Clear documentation of what the root cause was

**Acceptance Criteria:**
- [ ] `open_session` + `store_memory` + `end_session` complete successfully from Claude Code
- [ ] Daemon starts cleanly with timing logs in server output
<!-- ID: phase_1 -->
**Objective:** Formalize the SERVER/CLIENT/STANDALONE operating model with automatic detection, config integration, and startup guards.

**Dependencies:** Phase 0 (tools must be working)

---

### Task Package 1.1: Create OperatingMode Module

**Scope**: Create the new `config/operating_mode.py` module with the OperatingMode enum and detection functions.
**Files to Modify**:
- `src/council_mcp/config/__init__.py` (NEW — create package init)
- `src/council_mcp/config/operating_mode.py` (NEW — main module)
**Dependencies**: Phase 0 complete

#### Specifications

1. Create `src/council_mcp/config/` as a package (add `__init__.py`)
2. Create `src/council_mcp/config/operating_mode.py` with:
   - `class OperatingMode(enum.Enum)` — values: `SERVER`, `CLIENT`, `STANDALONE`
   - `async def _probe_postgres(url: str, timeout: float = 5.0) -> bool` — uses `asyncpg.connect()` wrapped in `asyncio.wait_for()`, returns True/False
   - `async def _probe_daemon(url: str, timeout: float = 3.0) -> bool` — uses `httpx.AsyncClient` GET to `{url}/health`, returns True if 200
   - `async def detect_operating_mode() -> OperatingMode` — priority chain: `COUNCIL_MODE` env → `DATABASE_URL` + probe → `COUNCIL_HUB_URL` + probe → `STANDALONE`
   - `def detect_operating_mode_sync() -> OperatingMode` — sync wrapper using `asyncio.run()`
   - Read timeout values from config: `council.connection.db_connect_timeout_seconds` (default 5), `council.connection.daemon_health_timeout_seconds` (default 3)
3. All functions must have type annotations and docstrings per typing-standards rule.
4. Import `get_council_config` from `council_mcp.config` (the existing config.py module — note the package vs module naming; may need to rename config.py to avoid collision; see specification note below).

**IMPORTANT naming note**: Currently `src/council_mcp/config.py` is a module. Creating `src/council_mcp/config/` as a package requires renaming `config.py` to `config/__init__.py` (moving all content). This is a mechanical rename — no logic changes. Verify all imports of `from council_mcp.config import ...` still work after the rename.

#### Verification
- [ ] `python -c "from council_mcp.config.operating_mode import OperatingMode, detect_operating_mode_sync; print(OperatingMode.SERVER)"` succeeds
- [ ] `python -c "from council_mcp.config import get_council_config; print(get_council_config())"` still works after rename
- [ ] Unit test in `tests/test_operating_mode.py`: mock env vars + probes, verify priority chain

#### Out of Scope (DO NOT TOUCH)
- Do not modify server.py integration yet (that is Task 1.3)
- Do not modify health endpoints
- Do not modify Docker configs

---

### Task Package 1.2: Add Connection Config Section

**Scope**: Add `council.connection` config keys to DEFAULT_CONFIG, defaults YAML, and env overrides.
**Files to Modify**:
- `src/council_mcp/config/__init__.py` (was config.py — DEFAULT_CONFIG and _apply_env_overrides)
- `src/council_mcp/templates/defaults/council.yaml`
**Dependencies**: Task 1.1 (config is now a package)

#### Specifications

1. Add to `DEFAULT_CONFIG["council"]` (near the `"compute"` and `"deployment"` sections, ~line 790):
   ```python
   "connection": {
       "db_connect_timeout_seconds": 5,
       "daemon_health_timeout_seconds": 3,
       "startup_fail_fast": True,
   },
   ```

2. Add same keys to `src/council_mcp/templates/defaults/council.yaml` under `council:` section:
   ```yaml
   connection:
     db_connect_timeout_seconds: 5
     daemon_health_timeout_seconds: 3
     startup_fail_fast: true
   ```

3. Add env override mappings in `_apply_env_overrides()`:
   - `COUNCIL_CONNECTION__DB_CONNECT_TIMEOUT_SECONDS` → int
   - `COUNCIL_CONNECTION__DAEMON_HEALTH_TIMEOUT_SECONDS` → int
   - `COUNCIL_CONNECTION__STARTUP_FAIL_FAST` → bool

4. Add convenience accessor:
   ```python
   def get_connection_config() -> dict[str, Any]:
       """Get the connection guard configuration section."""
       return get_council_config().get("council", {}).get("connection", {})
   ```

#### Verification
- [ ] `python -c "from council_mcp.config import get_connection_config; print(get_connection_config())"` returns dict with all 3 keys
- [ ] `COUNCIL_CONNECTION__DB_CONNECT_TIMEOUT_SECONDS=10 python -c "from council_mcp.config import get_connection_config; print(get_connection_config()['db_connect_timeout_seconds'])"` returns 10

#### Out of Scope (DO NOT TOUCH)
- Do not modify server.py
- Do not modify existing config keys
- Do not change how other config sections work

---

### Task Package 1.3: Integrate Mode Detection into Server Startup

**Scope**: Wire `detect_operating_mode_sync()` into `init_council()` and store the result in `_RUNTIME_CONTEXT`.
**Files to Modify**: `src/council_mcp/server.py`
**Dependencies**: Tasks 1.1 and 1.2

#### Specifications

1. In `init_council()` (line ~395), BEFORE the AgentKit imports and `resolve_project_id_via_adapter()`:
   ```python
   from council_mcp.config.operating_mode import detect_operating_mode_sync, OperatingMode
   
   mode = detect_operating_mode_sync()
   logger.info("Operating mode detected: %s", mode.value)
   ```

2. Store mode in runtime context via `set_runtime_context()` — add `operating_mode` field:
   ```python
   set_runtime_context(
       operating_mode=mode.value,
       project_id=resolved_project_id,
       project_slug=effective_project_slug,
       workspace=str(repo_root),
   )
   ```
   This requires adding `operating_mode: str | None = None` to `set_runtime_context()` signature and `_RUNTIME_CONTEXT` dict.

3. In SERVER mode, if `startup_fail_fast` is True and DATABASE_URL is set but Postgres probe failed during detection, log a CRITICAL warning:
   ```python
   if mode == OperatingMode.STANDALONE and os.getenv("DATABASE_URL"):
       logger.critical(
           "DATABASE_URL is set but Postgres is unreachable. "
           "Council will start in STANDALONE (degraded) mode. "
           "Check Postgres health: docker compose ps postgres"
       )
   ```

4. In `get_runtime_health()`, include `operating_mode` in the returned dict.

#### Verification
- [ ] Deploy to Hetzner — daemon logs show `Operating mode detected: server`
- [ ] `get_system_health` MCP tool includes `"operating_mode": "server"` in response
- [ ] With `COUNCIL_MODE=standalone`, daemon logs show `Operating mode detected: standalone`

#### Out of Scope (DO NOT TOUCH)
- Do not modify health API endpoints (that is Phase 2)
- Do not modify compute dispatcher
- Do not modify init_cmd.py

---

**Phase 1 Deliverables:**
- `src/council_mcp/config/operating_mode.py` — OperatingMode enum + detection
- `council.connection` config section with 3 keys
- `init_council()` detects and stores operating mode
- Runtime context exposes operating_mode

**Acceptance Criteria:**
- [ ] OperatingMode module exists with full test coverage
- [ ] Config keys registered in DEFAULT_CONFIG and defaults YAML with env overrides
- [ ] Daemon startup logs operating mode
- [ ] `get_runtime_health()` includes operating_mode field
<!-- ID: milestone_tracking -->
## Phase 2 — Health & Observability
<!-- ID: phase_2 -->

**Objective:** Enhance health reporting to cover all subsystems (DB, Ray, Scribe, operating mode) and make the system easily diagnosable.

**Dependencies:** Phase 1 (operating mode must be detected and stored)

---

### Task Package 2.1: Enhance Health Endpoint

**Scope**: Upgrade `/api/system/health` to report operating mode, DB connectivity, and Scribe status alongside existing compute health.
**Files to Modify**:
- `src/council_mcp/web/routes/system.py` (web health endpoint)
- `src/council_mcp/tools/daemon.py` (MCP health tool)
**Dependencies**: Phase 1 complete

#### Specifications

1. In the health endpoint handler, add operating_mode from runtime context:
   ```python
   from council_mcp.server import get_runtime_context
   ctx = get_runtime_context()
   health["operating_mode"] = ctx.get("operating_mode", "unknown")
   ```

2. Add DB health probe (fast, cached 30s):
   ```python
   health["database"] = {
       "connected": bool,
       "url_masked": mask_db_url(os.getenv("DATABASE_URL", "")),
       "latency_ms": float,  # Time for SELECT 1
   }
   ```
   Implementation: Execute `SELECT 1` through AgentKit's connection, wrap in 3s timeout. Mask password in URL with `***`.

3. Add Scribe connectivity check:
   ```python
   health["scribe"] = {
       "connected": bool,
       "url": scribe_url,
   }
   ```

4. Existing compute section (from `ComputeDispatcher.health()`) remains unchanged.

5. Update the MCP `get_system_health` tool in `tools/daemon.py` to include the same data.

#### Verification
- [ ] `curl http://council-hub:8016/health` returns JSON with `operating_mode`, `database`, `compute`, `scribe` sections
- [ ] `database.connected` is true on Hetzner, `database.url_masked` hides password
- [ ] `database.latency_ms` is present and reasonable (<100ms)

#### Out of Scope (DO NOT TOUCH)
- Do not modify operating mode detection logic
- Do not modify compute dispatcher
- Do not change health check caching strategy

---

### Task Package 2.2: Add COUNCIL_MODE to Docker Compose

**Scope**: Explicitly set `COUNCIL_MODE=server` in docker-compose.yaml for the daemon, ensuring mode detection skips probing and goes straight to SERVER.
**Files to Modify**: `deploy/docker-compose.yaml`
**Dependencies**: Phase 1 complete

#### Specifications

1. In `deploy/docker-compose.yaml`, under the `council-daemon` service `environment` section, add:
   ```yaml
   COUNCIL_MODE: "server"
   ```

2. This is an optimization — the probe would succeed anyway (DATABASE_URL is set + Postgres is reachable), but explicit mode avoids the 5s probe delay at startup.

#### Verification
- [ ] `ssh council-hub "docker compose -f /opt/council_mcp/deploy/docker-compose.yaml exec council-daemon env | grep COUNCIL_MODE"` shows `COUNCIL_MODE=server`
- [ ] Daemon logs show `Operating mode from COUNCIL_MODE env: server` (no probe needed)

#### Out of Scope (DO NOT TOUCH)
- Do not modify other services
- Do not add new Docker secrets
- Do not change port bindings

---

**Phase 2 Deliverables:**
- Enhanced `/api/system/health` with DB, Scribe, and operating mode sections
- Explicit COUNCIL_MODE in docker-compose.yaml
- MCP health tool updated

**Acceptance Criteria:**
- [ ] Health endpoint returns complete subsystem status
- [ ] DB health probe has <100ms latency on Hetzner
- [ ] Daemon startup is faster with explicit COUNCIL_MODE (no probe delay)

---

## Phase 3 — Downstream Council Support
<!-- ID: phase_3 -->

**Objective:** Enable other repos to bootstrap councils that connect to the central Hetzner infrastructure with minimal manual configuration.

**Dependencies:** Phase 2 (health endpoints needed for connection validation)

---

### Task Package 3.1: Enhance council init --parent Config Generation

**Scope**: When `council init --parent` is used, generate a `council.yaml` with hub connection settings and a `.env.example` with the required environment variables.
**Files to Modify**:
- `src/council_mcp/cli/init_cmd.py` (in `_build_council_yaml()` and `scaffold_council()`)
**Dependencies**: Phase 2 complete

#### Specifications

1. In `_build_council_yaml()`, when `parent_council_name` is set:
   - Set `council.deployment.mode` to `"remote"`
   - Fetch parent council's `hub_tailscale_ip` from the registration API response (the API already returns council info)
   - If hub IP is available, populate `council.deployment.hub_tailscale_ip`
   - Add `council.compute.ray_address` pointing to `<hub_ip>:6379`
   - Add `council.compute.ray_enabled` set to `false` (operator explicitly enables)

2. In `scaffold_council()`, after writing `council.yaml`, generate `.env.example`:
   ```
   # Council Native Integration — Environment Variables
   # Copy this file to .env and fill in values
   
   # Required: Database connection (get from council admin)
   DATABASE_URL=postgresql://council:PASSWORD@<hub_ip>:5432/agentkit
   
   # Optional: Direct hub connection for health checks
   COUNCIL_HUB_URL=http://<hub_ip>:8016
   
   # Optional: Override operating mode (auto-detected if not set)
   # COUNCIL_MODE=client
   
   # Optional: OpenAI API key for LLM calls
   # OPENAI_API_KEY=sk-...
   ```

3. Print a setup guide to stdout after scaffold:
   ```
   Next steps:
   1. Copy .env.example to .env and fill in your DATABASE_URL
   2. Run: council start
   3. Verify: council status
   ```

#### Verification
- [ ] `council init --name test-downstream --parent council-mcp --preset minimal` in a temp dir generates:
  - `.council/council.yaml` with `deployment.mode: "remote"` and `deployment.hub_tailscale_ip` populated
  - `.env.example` with DATABASE_URL template using the hub IP
- [ ] Setup guide printed to stdout

#### Out of Scope (DO NOT TOUCH)
- Do not modify the registration API
- Do not change how non-parent init works
- Do not modify database schema
- Do not implement automatic secret distribution

---

### Task Package 3.2: Add Connection Validation to council start

**Scope**: When starting a downstream council in remote mode, validate hub connectivity before proceeding.
**Files to Modify**: `src/council_mcp/cli/start_cmd.py`
**Dependencies**: Task 3.1

#### Specifications

1. In `_start_background()` or before daemon spawn, if `deployment.mode == "remote"`:
   - Check that DATABASE_URL is set (from `.env` or environment)
   - Probe the hub daemon health endpoint with 5s timeout
   - If DATABASE_URL is missing, print clear error and exit
   - If hub is unreachable, print warning but allow startup in degraded mode

2. Use `_probe_postgres()` and `_probe_daemon()` from `config/operating_mode.py`.

#### Verification
- [ ] `council start` without DATABASE_URL in remote mode: clear error message, non-zero exit
- [ ] `council start` with DATABASE_URL but hub unreachable: warning + degraded startup
- [ ] `council start` with everything configured: clean startup

#### Out of Scope (DO NOT TOUCH)
- Do not modify the daemon itself
- Do not change how local mode starts
- Do not modify init_cmd.py

---

**Phase 3 Deliverables:**
- `council init --parent` generates hub-aware config + .env.example
- `council start` validates connectivity in remote mode
- Setup guide printed after scaffold

**Acceptance Criteria:**
- [ ] Downstream council can be initialized and started with clear guidance
- [ ] Missing DATABASE_URL caught early with actionable error message
- [ ] Hub unreachability degrades gracefully with warning

---

## Milestone Tracking
<!-- ID: milestone_tracking -->

| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Phase 0.1: Diagnostic Logging | 2026-02-17 | Mantis/Forge | Planned | — |
| Phase 0.2: Root Cause Fix | 2026-02-17 | Mantis/Forge | Planned | — |
| Phase 1.1: OperatingMode Module | 2026-02-18 | Forge | Planned | — |
| Phase 1.2: Connection Config | 2026-02-18 | Forge | Planned | — |
| Phase 1.3: Server Integration | 2026-02-18 | Forge | Planned | — |
| Phase 2.1: Health Endpoint | 2026-02-19 | Forge | Planned | — |
| Phase 2.2: Docker Compose Update | 2026-02-19 | Forge | Planned | — |
| Phase 3.1: Downstream Config Gen | 2026-02-20 | Forge | Planned | — |
| Phase 3.2: Connection Validation | 2026-02-20 | Forge | Planned | — |
Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---