---
id: council_native_integration-checklist
title: "\u2705 Acceptance Checklist \u2014 council_native_integration"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 08:55:43 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — council_native_integration
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 07:53:55 UTC

> Acceptance checklist for council_native_integration.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md — full rewrite with operating modes, component diagram, detailed design)
- [x] Phase plan current (proof: PHASE_PLAN.md — 4 phases, 9 task packages with bounded scope)
- [x] Research complete (proof: 4 RESEARCH docs in research/ directory)
<!-- ID: phase_0 -->
### Task 0.1: Diagnostic Logging
- [ ] `server.py init_council()` has timing logs for DATABASE_URL check, AgentKit import, resolve_project_id (proof: code diff)
- [ ] `server.py main()` logs transport mode before init_council (proof: code diff)
- [ ] `ws_proxy.py` logs WebSocket connection lifecycle: connect, fail, tool call sent/received with elapsed time (proof: code diff)
- [ ] Deployed to Hetzner and daemon logs show `[DIAG]` entries (proof: `docker compose logs council-daemon`)

### Task 0.2: Root Cause Fix
- [ ] Root cause identified and documented in PROGRESS_LOG (proof: append_entry)
- [ ] Fix applied and deployed (proof: commit SHA)
- [ ] `open_session(persona_id="atlas")` completes in <5 seconds from dev PC (proof: Claude Code test)
- [ ] `store_memory(persona_id="atlas", text="test")` completes successfully (proof: Claude Code test)
- [ ] `end_session` completes successfully (proof: Claude Code test)

---

## Phase 1 — Operating Mode Detection
<!-- ID: phase_1 -->

### Task 1.1: OperatingMode Module
- [x] `src/council_mcp/config/operating_mode.py` exists with OperatingMode enum (proof: file created at src/council_mcp/config/operating_mode.py)
- [x] `detect_operating_mode_sync()` implements priority chain: COUNCIL_MODE env -> DATABASE_URL+probe -> COUNCIL_HUB_URL+probe -> STANDALONE (proof: TestDetectOperatingModeSync 17 tests passing)
- [x] `_probe_postgres_sync()` uses asyncpg.connect() wrapped in asyncio.wait_for() with configurable timeout (proof: TestProbePostgresSync 2 tests passing)
- [x] `_probe_daemon_sync()` uses urllib with configurable timeout (proof: TestProbeDaemonSync 5 tests passing)
- [x] `config.py` -> `config/__init__.py` rename complete, all existing imports work (proof: 72 existing config tests passing)
- [x] Unit tests in `tests/test_operating_mode.py` cover all 4 priority levels (proof: 32/32 tests passing)

### Task 1.2: Connection Config Section
- [x] `DEFAULT_CONFIG["council"]["connection"]` has 3 keys: db_connect_timeout_seconds, daemon_health_timeout_seconds, startup_fail_fast (proof: python -c "from council_mcp.config import get_connection_config; print(get_connection_config())" returns all 3 keys)
- [x] `templates/defaults/council.yaml` has matching `connection:` section (proof: lines 782-786 in council.yaml)
- [x] Env overrides work: `COUNCIL_CONNECTION__DB_CONNECT_TIMEOUT_SECONDS=10` overrides default (proof: TestGetConnectionConfig::test_env_override_db_connect_timeout passing)
- [x] `get_connection_config()` accessor function exists and returns correct dict (proof: TestGetConnectionConfig 8 tests passing)

### Task 1.3: Server Integration
- [x] `init_council()` calls `detect_operating_mode_sync()` before AgentKit init (proof: server.py line 449 — detect_operating_mode_sync() called after agentkit_extensions imports, before register_council_adapter)
- [x] Operating mode stored in `_RUNTIME_CONTEXT` (proof: TestOperatingModeServerIntegration::test_operating_mode_stored_in_runtime_context_server passing)
- [x] DATABASE_URL set but Postgres unreachable logs CRITICAL warning (proof: TestOperatingModeServerIntegration::test_startup_fail_fast_logs_critical_when_db_url_set_standalone passing)
- [x] `get_runtime_health()` includes `operating_mode` field (proof: TestOperatingModeServerIntegration::test_get_runtime_health_includes_operating_mode passing)
- [ ] Deployed to Hetzner: daemon logs show `Operating mode detected: server` (proof: docker compose logs)

---

## Phase 2 — Health & Observability
<!-- ID: phase_2 -->

### Task 2.1: Enhance Health Endpoint
- [x] `/api/system/health` response includes `operating_mode` field (proof: added to web-path and daemon-fallback in system.py)
- [x] `/api/system/health` response includes `database.connected`, `database.url_masked`, `database.latency_ms` (proof: _get_database_health() SELECT 1 probe with 3s timeout)
- [x] `/api/system/health` response includes `scribe.connected` (proof: _get_scribe_health() checks MCP pool)
- [x] DB password masked in URL (shows `***` not actual password) (proof: _mask_db_url() re.sub; 7 tests pass)
- [x] MCP `get_system_health` tool returns same data (proof: daemon.py updated; 15/15 new tests pass)

### Task 2.2: Docker Compose Update
- [ ] `deploy/docker-compose.yaml` has `COUNCIL_MODE: "server"` in council-daemon environment (proof: file diff)
- [ ] Daemon startup skips probe when COUNCIL_MODE is explicit (proof: daemon logs show no probe)

---

## Phase 3 — Downstream Council Support
<!-- ID: phase_3 -->

### Task 3.1: Downstream Config Generation
- [x] `council init --parent` generates `council.yaml` with `deployment.mode: "remote"` (proof: generated file) | proof=24/24 tests pass in tests/test_downstream_support.py. All Task 3.1+3.2 items verified.
- [ ] `council init --parent` generates `deployment.hub_tailscale_ip` from parent's config (proof: generated file)
- [ ] `.env.example` generated with DATABASE_URL template using hub IP (proof: generated file)
- [ ] Setup guide printed to stdout (proof: command output)

### Task 3.2: Connection Validation
- [ ] `council start` in remote mode without DATABASE_URL: clear error, non-zero exit (proof: command output)
- [ ] `council start` in remote mode with DATABASE_URL but hub unreachable: warning + degraded (proof: command output)
- [ ] `council start` with everything configured: clean startup (proof: command output)
<!-- ID: final_verification -->
- [ ] All checklist items checked with proofs attached.  
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.


---