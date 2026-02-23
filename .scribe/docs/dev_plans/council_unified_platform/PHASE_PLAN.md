---
id: council_unified_platform-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_unified_platform"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 03:12:05 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_unified_platform
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-18 01:53:25 UTC

> Execution roadmap for council_unified_platform.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence | Est. Sessions |
|-------|------|------------------|-----------|--------------|
| Phase 0 -- Connect Supervision + Node Registry | Fix broken connect start, then build node registry | P0.0: Supervision loop. P0.1: platform_nodes table. P0.2: REST API. P0.3: CLI registration + heartbeat | 0.92 | 4 |
| Phase 1 -- GPU Embedding Serving | Highest value: TEI on Nicolas, embedding bridge integration | TEI setup, embeddings.py TEI path, config keys, health integration | 0.95 | 2 |
| Phase 2 -- Compute Dispatch Enhancement | Extend dispatcher with service routing and dynamic task registration | Service dispatch in dispatcher.py, register_task() API, CONFIG_SCHEMA | 0.90 | 2 |
| Phase 3 -- Federation Activation | Fix 6 gaps + SELECT blocker in existing federation system | Fix registry SELECTs, remote registration, api_endpoint API, shared_secret, memory handler | 0.93 | 2 |
| Phase 4 -- Intelligent File Sync (Syncthing) | Role-based repo sync across nodes with automatic Syncthing management | Per-node sync policies, Syncthing API integration, template_loader enhancement | 0.85 | 3 |
| Phase 5 -- Distributed Agent Execution | Most complex: remote agent sessions via Ray Actors | RemoteAgentActor, WorkerPool dual-dispatch, event relay, worktree resolution | 0.78 | 4 |
| Phase 6 -- Platform Dashboard | Unified observability page | platform.html.j2 custom page, platform.js, per-node metrics | 0.90 | 2 |
| Phase 7 -- TEI Container Lifecycle | Auto-start/stop TEI Docker container with council connect | TEIContainerManager, connect_cmd integration, dynamic TEI URL discovery | 0.95 | 3 |
| Phase 8 -- Local Dev Serving | Run local dev stack sharing prod DB over Tailscale | council connect serve command, dev-serve config, hub service registration, test suite | 0.95 | 3 |

**Total estimated Forge sessions:** 25

**Ordering rationale:**
- Phase 0 first: fix the broken `council connect start` before building anything on top of it, then build node registry
- Phase 1 second: highest ROI (GPU embeddings), quickest win, independently valuable
- Phase 2 third: dispatcher enhancements enable clean integration of Phase 1 services
- Phase 3 fourth: federation fixes are well-scoped (6 known gaps + SELECT blocker) and enable multi-council
- Phase 4 fifth: file sync depends on `council connect start` working properly (Phase 0)
- Phase 5 sixth: most complex, depends on Phase 0 + 2 + 4 (sync for CWD resolution)
- Phase 6 last: dashboard visualizes everything built in Phases 0-5
- Phase 8: local dev serving is a developer experience feature built on all prior phases

**NOTE:** Phase 4 (Local LLM Serving) from the original plan has been REMOVED. The operator runs their own llamacpp system independently. All LLM references have been stripped.
<!-- ID: phase_0 -->
**Objective:** Fix the broken `council connect start` command, then build the foundational node registry so the hub knows what machines exist, what they can do, and whether they are online.

**Dependencies:** None (foundational phase)

---

### Task Package P0.0: Connect Start Supervision Fix (CRITICAL)

**Scope:** Fix the fire-and-forget design in `council connect start`. Add supervision loop, automatic reconnection, and heartbeat that verifies actual Ray connectivity.
**Files to Modify:**
- `src/council_mcp/cli/connect_cmd.py` — add `RayWorkerSupervisor` class, modify `start()` to use supervision

**Dependencies:** None (this is the first task)

**Specifications:**
1. Add `RayWorkerSupervisor` class to `connect_cmd.py`:
   - `__init__(self, head_address: str, ray_cmd: list[str], hub_url: str)` — store connection parameters
   - `run(self) -> None` — main supervision loop, checks health every 15s
   - `_check_ray_health(self) -> bool` — calls `ray.is_initialized()` to verify ACTUAL connectivity (not just PID existence)
   - `_reconnect(self) -> None` — `ray stop` + `ray start` with exponential backoff (1s, 2s, 4s, ... max 60s), verifies head reachability first via `_ping_host()`
   - `stop(self) -> None` — signal the loop to exit
2. Modify `start()` function:
   - After successful `ray start`, create `RayWorkerSupervisor` instance
   - Foreground mode: call `supervisor.run()` directly (replaces current `ray monitor` blocking)
   - Background mode: start supervisor as daemon thread `threading.Thread(target=supervisor.run, daemon=True)`
   - Register SIGTERM/SIGINT handler that calls `supervisor.stop()` then `ray stop`
3. Fix PID detection: replace `pgrep -f raylet` with `ray.is_initialized()` check after `ray start`
4. Add config keys to DEFAULT_CONFIG under `council.compute`:
   ```python
   "supervision_check_interval_seconds": 15,
   "supervision_reconnect_max_backoff_seconds": 60,
   ```

**Verification:** (all passing -- 19/19 tests green)
- [x] `council connect start --foreground` blocks on supervision loop (not `ray monitor`) -- start() calls supervisor.run() directly
- [x] Kill raylet process manually -> supervisor detects within 15s and reconnects -- TestSupervisionLoop::test_loop_detects_disconnection
- [x] Head node unreachable -> supervisor waits with exponential backoff, reconnects when head returns -- TestReconnection (4 tests)
- [x] `council connect stop` cleanly shuts down supervisor and ray -- SIGTERM/SIGINT handlers call supervisor.stop() + ray stop
- [x] `pytest tests/test_connect_supervision.py -v` passes (mock ray.is_initialized) -- 19/19 pass

**Out of Scope (DO NOT TOUCH):**
- Node registration API (P0.2)
- NodeRegistry class (P0.1)
- Any web routes

---

### Task Package P0.1: Platform Nodes Schema & Storage

**Scope:** Create the `council.platform_nodes` database table and storage functions.
**Files to Create:**
- `db/schema/council/tables/platform_nodes.sql`
- `src/council_mcp/platform/__init__.py`
- `src/council_mcp/platform/nodes.py`

**Files to Modify:**
- `src/council_mcp/config/__init__.py` — add `council.node.*` config keys to DEFAULT_CONFIG
- `templates/defaults/council.yaml` — mirror config keys

**Dependencies:** None (can run in parallel with P0.0)

**Specifications:**
1. Create SQL file `db/schema/council/tables/platform_nodes.sql` with the schema from Architecture Guide (platform_nodes is GLOBAL, includes `councils_served TEXT[]`, NO `council_id` column)
2. Create `src/council_mcp/platform/nodes.py` with class `NodeRegistry`:
   - `upsert_node(hostname: str, tailscale_ip: str | None, node_type: str, capabilities: dict, services: list[dict], repos: list[str], resources: dict, role: str | None = None, councils_served: list[str] | None = None) -> dict` — Upsert into `council.platform_nodes` using `ON CONFLICT(hostname) DO UPDATE`
   - `get_nodes(status: str | None = None) -> list[dict]` — List nodes, optionally filtered by status
   - `get_nodes_for_council(council_id: str) -> list[dict]` — List nodes where `council_id = ANY(councils_served)`
   - `get_node(hostname: str) -> dict | None` — Get single node by hostname
   - `update_heartbeat(hostname: str, ray_connected: bool = True) -> None` — Update `last_heartbeat` to NOW(), set status based on `ray_connected`
   - `mark_stale_nodes(timeout_seconds: int = 90) -> int` — Set `status='offline'` for nodes with `last_heartbeat < NOW() - interval`
   - `get_service_endpoint(service_name: str) -> dict | None` — Find an online node offering the named service; return `{"hostname": ..., "url": "http://..."}` or None
   - `remove_node(hostname: str) -> bool` — Delete node record
3. Add config keys to DEFAULT_CONFIG:
   ```python
   "node": {
       "heartbeat_interval_seconds": 30,
       "stale_timeout_seconds": 90,
       "auto_detect_capabilities": True,
       "default_role": "dev-workstation",
   }
   ```

**Verification:**
- [x] SQL file created at `db/schema/council/tables/070_platform_nodes.sql` (agentkit-schema plan/apply deferred to operator at deploy)
- [x] `pytest tests/test_node_registry.py -v` passes — 22/22 tests (0.40s)
- [x] `get_nodes_for_council()` tested — uses `ANY(councils_served)` filter, verified in TestGetNodesForCouncil (2 tests)

**Out of Scope (DO NOT TOUCH):**
- Web UI routes (P0.2)
- CLI changes (P0.3)
- ComputeDispatcher (Phase 2)

---

### Task Package P0.2: Node Registration API

**Scope:** Add REST API endpoints for node registration and heartbeat.
**Files to Modify:**
- `src/council_mcp/web/routes/system.py` — add `/api/platform/nodes/*` endpoints

**Files to Create:**
- `tests/test_node_api.py`

**Dependencies:** P0.1 (NodeRegistry class must exist)

**Specifications:**
1. Add endpoints to `system.py`:
   - `POST /api/platform/nodes/register` — accepts `{"hostname", "tailscale_ip", "node_type", "capabilities", "services", "repos", "resources", "role", "councils_served"}`, calls `NodeRegistry.upsert_node()`, returns `{"id", "hostname", "status"}`
   - `POST /api/platform/nodes/{hostname}/heartbeat` — accepts `{"ray_connected": bool}`, calls `NodeRegistry.update_heartbeat()`, returns `{"ok": true}`
   - `GET /api/platform/nodes` — returns list of nodes. If council context available via `_get_active_council_id(request)`, filter using `get_nodes_for_council()`. If no council context, return all nodes.
   - `DELETE /api/platform/nodes/{hostname}` — remove node from registry
2. All endpoints require auth (`Depends(get_current_user)`) or API key
3. Enhance existing `/api/system/health` endpoint to include `"nodes": NodeRegistry.get_nodes()` in the response
4. Node listing respects council context but `platform_nodes` itself is GLOBAL. The GET endpoint uses `councils_served` for filtering when a council is active.

**Verification:**
- [x] `curl -H "Authorization: Bearer ..." POST /api/platform/nodes/register` returns 200 with node data — TestRegisterNode (3 tests)
- [x] `GET /api/system/health` includes `nodes` array — TestHealthIncludesNodes (2 tests)
- [x] `GET /api/platform/nodes` with active council filters by `councils_served` — TestListNodes::test_list_nodes_with_council_filters
- [x] `pytest tests/test_node_api.py -v` passes — 17/17 pass (1.54s)

**Out of Scope (DO NOT TOUCH):**
- CLI connect command (P0.3)
- SessionManager, WorkerPool, StreamBridge

---

### Task Package P0.3: CLI Registration & Heartbeat Integration

**Scope:** Enhance `council connect start` to register with the hub and send heartbeats after joining.
**Files to Modify:**
- `src/council_mcp/cli/connect_cmd.py` — add registration POST, heartbeat in supervision loop, `--role` flag

**Dependencies:** P0.0 (supervision must be working), P0.2 (registration API must exist)

**Specifications:**
1. Add `--role` flag to `council connect start`: `--role gpu-compute|dev-workstation|ci-runner` (default from `council.node.default_role` config)
2. After successful Ray join, POST to hub: `http://{hub_address}:8015/api/platform/nodes/register` with auto-detected capabilities:
   - `hostname`: from `socket.gethostname()` or Tailscale hostname
   - `capabilities`: `os.cpu_count()`, GPU detection via `torch.cuda.is_available()`, RAM via `psutil`
   - `services`: empty list initially (services registered separately via `council connect serve`)
   - `role`: from `--role` flag
   - `councils_served`: detect from `.council/council.yaml` on local machine
3. Integrate heartbeat into `RayWorkerSupervisor.run()`: every 30s, POST to `/api/platform/nodes/{hostname}/heartbeat` with `{"ray_connected": self._check_ray_health()}`
4. On `council connect stop`, send DELETE to `/api/platform/nodes/{hostname}` to deregister
5. Enhance `council connect status` to show "Registered with hub: yes/no" and registration details

**Verification:**
- [x] `council connect start --role gpu-compute` registers with hub (POST /api/platform/nodes/register with auto-detected capabilities)
- [x] Heartbeat sends `ray_connected` status every heartbeat_interval_seconds (TestSupervisorHeartbeat: 3 tests)
- [x] `council connect stop` deregisters from hub (DELETE /api/platform/nodes/{hostname})
- [x] Heartbeat includes actual Ray connectivity status via supervisor._check_ray_health()
- [x] `pytest tests/test_connect_registration.py -v` passes — 34/34 tests

**Out of Scope (DO NOT TOUCH):**
- ComputeDispatcher, embeddings.py
- Federation system
- SessionManager, WorkerPool

---

**Phase 0 Acceptance Criteria:**
- [x] `council connect start` has supervision loop that auto-reconnects on failure (P0.0 — 19/19 tests)
- [x] `council.platform_nodes` table exists in database (GLOBAL, no council_id) (P0.1 — 22/22 tests)
- [x] Hub API can register, list, heartbeat, and deregister nodes (P0.2 — 17/17 tests)
- [x] `/api/system/health` includes node list (P0.2 — TestHealthIncludesNodes: 2 tests)
- [x] `council connect start` registers with hub automatically and reports Ray connectivity (P0.3 — 34/34 tests)
- [x] Stale nodes (90s no heartbeat) marked offline (P0.1 — TestMarkStaleNodes: 2 tests)
<!-- ID: phase_1 -->
**Objective:** Deploy TEI on Nicolas for GPU-accelerated embeddings and integrate with the existing embedding bridge.

**Dependencies:** None (can run in parallel with Phase 0, but Phase 0 enables health reporting)

---

### Task Package P1.1: TEI Integration in Embedding Bridge

**Scope:** Add TEI HTTP dispatch path to `embeddings.py` and config.
**Files to Modify:**
- `src/council_mcp/compute/embeddings.py` — add `_embed_via_tei()` and TEI dispatch path
- `src/council_mcp/config/__init__.py` — add `tei_url`, `tei_timeout_seconds` to DEFAULT_CONFIG `compute` section
- `templates/defaults/council.yaml` — mirror config keys

**Specifications:**
1. Add to DEFAULT_CONFIG `compute` section:
   ```python
   "tei_url": "",                    # Empty = disabled
   "tei_timeout_seconds": 5,
   ```
2. Add `_embed_via_tei(url: str, text: str) -> list[float]` async function using `httpx`:
   - POST to `{url}/embed` with `{"inputs": text}`
   - Parse response as `list[float]`
   - Timeout: `tei_timeout_seconds` from config
3. Add `_batch_embed_via_tei(url: str, texts: list[str]) -> list[list[float]]` for batch path
4. Modify `embed_text_async()`: check `tei_url` first, try TEI, fall through to existing Ray/local on failure
5. Modify `embed_texts_async()`: same pattern, use batch TEI endpoint

**Verification:**
- [x] With `tei_url=""`: behavior unchanged (existing tests pass) -- TestEmbedTextAsyncRouting::test_empty_tei_url_skips_tei passes
- [x] With `tei_url="http://localhost:8080"` and a mock TEI server: embedding returns correct dimensions (384) -- TestEmbedTextAsyncRouting::test_tei_url_set_uses_tei passes
- [x] On TEI failure: falls through to local CPU embedding -- TestEmbedTextAsyncRouting::test_tei_failure_falls_through_to_local passes
- [x] `pytest tests/test_compute_tei_integration.py -v` passes -- 24/24 tests pass (0.39s)

**Out of Scope (DO NOT TOUCH):**
- ComputeDispatcher (Phase 2 will do this)
- tasks.py (no changes needed for TEI)
- SessionManager, WorkerPool

---

### Task Package P1.2: TEI Deployment Setup (Operational)

**Scope:** Deploy TEI Docker container on Nicolas and configure Hetzner to use it.
**Files to Modify:**
- `deploy/docker-compose.yaml` — add TEI_URL environment variable to council-daemon and council-web services

**Specifications:**
1. On Nicolas (manual/scripted setup):
   ```bash
   docker run -d --name tei \
     --gpus all \
     -p 100.x.y.z:8080:80 \
     ghcr.io/huggingface/text-embeddings-inference:turing-1.5 \
     --model-id sentence-transformers/all-MiniLM-L6-v2 \
     --dtype float16
   ```
   (Port bound to Tailscale IP only, NEVER 0.0.0.0)
2. Add to `deploy/docker-compose.yaml` council-daemon and council-web services:
   ```yaml
   environment:
     - TEI_URL=${TEI_URL:-}
   ```
3. Add to `deploy/.env`: `TEI_URL=http://nicolas:8080` (only when Nicolas is available)
4. Update `.council/council.yaml` on Hetzner: `compute.tei_url: "http://nicolas:8080"`
5. Verify: `curl http://nicolas:8080/embed -d '{"inputs": "test"}'` returns 384-dim vector

**Verification:**
- [ ] TEI container runs on Nicolas with GPU
- [ ] `curl http://nicolas:8080/health` returns 200
- [ ] Embedding dimension is 384
- [ ] council-daemon picks up TEI_URL and uses it for embeddings

**Out of Scope (DO NOT TOUCH):**
- Any council_mcp source code (this is operational setup only)

---

**Phase 1 Acceptance Criteria:**
- [ ] TEI running on Nicolas with GPU acceleration
- [ ] `embed_text_async()` routes to TEI when configured
- [ ] Fallback to CPU works when TEI is unavailable
- [ ] Batch embeddings work through TEI


---
## Phase 2 — Compute Dispatch Enhancement
<!-- ID: phase_2 -->

**Objective:** Extend ComputeDispatcher with service-based routing and dynamic task registration. Close GAPs 1, 2, 6 from RESEARCH_CURRENT_RAY_CODEBASE.

**Dependencies:** Phase 0 (node registry for service endpoint lookup)

---

### Task Package P2.1: Dynamic Task Registration API

**Scope:** Add `register_task()` to `tasks.py` so new workloads don't require editing core files.
**Files to Modify:**
- `src/council_mcp/compute/tasks.py` — add `register_task()` function
- `src/council_mcp/compute/dispatcher.py` — add `register()` method

**Specifications:**
1. Add to `tasks.py`:
   ```python
   def register_task(
       name: str,
       local_fn: Callable,
       *,
       num_gpus: float = 0,
       num_cpus: float = 1,
   ) -> None:
       """Register a task in TASK_REGISTRY and mark for lazy ray.remote wrapping."""
       TASK_REGISTRY[name] = local_fn
       _pending_registrations[name] = {"local_fn": local_fn, "num_gpus": num_gpus, "num_cpus": num_cpus}
   ```
2. Modify `get_remote_tasks()` to also wrap any `_pending_registrations` entries
3. Add `ComputeDispatcher.register(name, local_fn, **ray_kwargs)` as a convenience method

**Verification:**
- [x] `register_task("my_task", my_fn, num_gpus=0.5)` adds to TASK_REGISTRY -- TestRegisterTask (5 tests)
- [x] `dispatcher.dispatch("my_task", ...)` works for both Ray and local -- TestDispatchRegisteredTasks (3 tests, local + Ray + fallback)
- [x] Existing `embed_text` and `batch_embed` tasks still work -- TestExistingTasksUnaffected (3 tests) + existing test_compute_dispatcher.py (20/20 pass)
- [x] `pytest tests/test_task_registration.py -v` passes -- 22/22 passed (0.56s)

**Out of Scope (DO NOT TOUCH):**
- embeddings.py (already has TEI path from Phase 1)
- SessionManager, WorkerPool

---

### Task Package P2.2: Service-Based Dispatch & CONFIG_SCHEMA

**Scope:** Add service routing to dispatcher and add compute keys to CONFIG_SCHEMA.
**Files to Modify:**
- `src/council_mcp/compute/dispatcher.py` — add `_resolve_service()`, `_dispatch_service()`
- `src/council_mcp/config/__init__.py` — add `service_routes`, `service_timeout_seconds` to DEFAULT_CONFIG and CONFIG_SCHEMA entries for all compute keys

**Specifications:**
1. Add to DEFAULT_CONFIG `compute` section:
   ```python
   "service_routes": {},               # Map task names to service types
   "service_timeout_seconds": 10,
   ```
2. Add `_resolve_service(task_name)` method to ComputeDispatcher:
   - Looks up task_name in `service_routes` config
   - Queries `NodeRegistry.get_service_endpoint(service_name)` for an online endpoint
   - Returns URL string or None
3. Add `_dispatch_service(url, task_name, *args, **kwargs)` method:
   - HTTP POST to service URL with JSON payload
   - Timeout from `service_timeout_seconds`
   - Returns parsed response
4. Modify `dispatch()` to try service dispatch first (before Ray, before local)
5. Add CONFIG_SCHEMA entries for all `council.compute.*` keys (closes GAP 2 and GAP 10)

**Verification:**
- [x] With `service_routes: {embed_text: "tei"}` and TEI running: dispatch routes to TEI -- Evidence: test_dispatch_routes_to_service_when_configured passes
- [x] Without service_routes: existing Ray/local path works unchanged -- Evidence: test_existing_ray_path_unchanged_without_service, test_existing_local_path_unchanged_without_service, all 20 existing dispatcher tests pass
- [x] CONFIG_SCHEMA entries appear in web UI config editor -- Evidence: 10 entries added, test_all_compute_keys_in_schema passes, /api/system/config-schema serves them
- [x] `pytest tests/test_dispatcher_service.py -v` passes -- 24/24 passed (0.48s)

**Out of Scope (DO NOT TOUCH):**
- WorkerPool (Phase 6)
- Federation system (Phase 3)

---

**Phase 2 Acceptance Criteria:**
- [x] `register_task()` API works for new workloads -- Evidence: P2.1 done, 22 tests pass
- [x] Service-based dispatch routes to TEI when configured -- Evidence: P2.2 done, 24 tests pass
- [x] All `council.compute.*` keys visible in web UI config editor -- Evidence: 10 CONFIG_SCHEMA entries, test_all_compute_keys_in_schema passes
- [x] Existing dispatch paths (Ray, local) unchanged -- Evidence: test_compute_dispatcher.py 20/20 pass (zero regressions)


---
## Phase 3 — Federation Activation
<!-- ID: phase_3 -->
**Objective:** Fix the 6 gaps + SELECT query blocker in the existing federation system so cross-council communication works.

**Dependencies:** None (independent of other phases)

---

### Task Package P3.0: Fix Registry SELECT Queries (BLOCKER)

**Scope:** Add `api_endpoint` to all SELECT column lists in `registry.py`. Without this, federation silently fails.
**Files to Modify:**
- `src/council_mcp/storage/registry.py` — add `api_endpoint` to 3 SELECT queries

**Dependencies:** None (this is the prerequisite for all federation work)

**Specifications:**
1. In `list_councils_sync()` (line 95): change SELECT to include `api_endpoint`:
   ```python
   "SELECT id, parent_council_id, name, repo_path, api_endpoint, status, metadata, created_at, last_seen "
   ```
2. In `get_council_by_name_sync()` (line 107): same change
3. In `get_council_by_id_sync()` (line 118): same change
4. No schema migration needed — `api_endpoint` column already exists on `council.councils`

**Verification:**
- [ ] `list_councils_sync()` returns dicts that include `api_endpoint` key
- [ ] `get_council_by_id_sync()` returns dict with `api_endpoint`
- [ ] Existing tests still pass (new column is additive, won't break anything)
- [ ] `pytest tests/ -k "registry" -v` passes

**Out of Scope (DO NOT TOUCH):**
- Federation receive handler (P3.2)
- CLI federation command (P3.2)
- Any endpoint changes

---

### Task Package P3.1: Remote Registration & api_endpoint

**Scope:** Fix Gaps 1, 2, 6 — allow remote council registration and api_endpoint management.
**Files to Modify:**
- `src/council_mcp/web/routes/councils.py` — add `remote` flag, `api_endpoint` to register; add PATCH endpoint
- `src/council_mcp/storage/registry.py` — add `api_endpoint` param to `register_council_sync()`

**Dependencies:** P3.0 (SELECT queries must include api_endpoint first)

**Specifications:**
1. Modify `CouncilRegisterRequest` pydantic model: add `remote: bool = False`, `api_endpoint: str | None = None`
2. In `register_council` endpoint: when `remote=True`, skip `path.exists()` check
3. Modify `register_council_sync()` to accept and store `api_endpoint` parameter:
   ```python
   def register_council_sync(
       name: str,
       repo_path: str | None = None,
       parent: str | None = None,
       api_endpoint: str | None = None,
   ) -> str:
   ```
   Update INSERT/ON CONFLICT to include `api_endpoint`
4. Add `PATCH /api/councils/{council_id}` endpoint to update `api_endpoint` and metadata
5. Add `GET /api/councils/{council_id}` endpoint to get single council detail (if missing)

**Verification:**
- [x] `POST /api/councils/register` with `remote=true` succeeds without local path
- [x] `PATCH /api/councils/{id}` updates `api_endpoint`
- [ ] `dispatch_work_item_federation` succeeds when api_endpoint is set (P3.2 scope)
- [x] Existing local registration still works
- [x] `pytest tests/test_federation_fixes.py -v` passes (27/27)

**Out of Scope (DO NOT TOUCH):**
- Federation receive handler (P3.2)
- CLI federation command (P3.2)

---

### Task Package P3.2: Shared Secret & Memory Federation Handler

**Scope:** Fix Gaps 3, 4 — configure shared_secret and implement memory_federated handler using existing push patterns.
**Files to Modify:**
- `src/council_mcp/web/routes/federation.py` — implement `memory_federated` hook handler
- `src/council_mcp/cli/init_cmd.py` — generate shared_secret during `council init`

**Files to Create:**
- `src/council_mcp/cli/federation_cmd.py` — `council federation setup` CLI command

**Dependencies:** P3.0 and P3.1 (api_endpoint must be queryable)

**Specifications:**
1. In `federation_receive` handler, for `hook_type == "memory_federated"`:
   - Import `_compute_text_hash` and `_check_existing_federated_memory` from `tools/federation.py`
   - Extract memory fields from payload: `text`, `persona_id`, `memory_type`, `tags`, `strength`
   - Compute `text_hash = _compute_text_hash(text)` (matches push-side pattern)
   - Check duplicates via `_check_existing_federated_memory(target_council_id, source_council_id, text_hash)`
   - If duplicate, return `{"status": "duplicate", "existing_memory_id": ...}`
   - If new, call `models.insert_persona_memory()` with metadata containing:
     - `metadata["text_hash"] = text_hash`
     - `metadata["federated_from"] = {"source_council_id": ..., "source_memory_id": ...}`
   - Update `council_id` and `source_council_id` on the new memory record (mirrors `_copy_memory_to_council()`)
   - Return `{"status": "stored", "memory_id": ...}`
2. In `init_cmd.py`: generate `shared_secret` during `council init` if not provided:
   ```python
   import secrets
   shared_secret = secrets.token_hex(32)
   ```
   Write to `council.yaml` under `daemon_federation.shared_secret`
3. Create `federation_cmd.py` with `council federation setup` wizard:
   - Prompt for shared_secret (or generate)
   - Prompt for api_endpoint
   - Write to council.yaml
   - Print summary

**Verification:**
- [ ] `council init` generates a non-empty `shared_secret`
- [ ] Sending `memory_federated` hook to `/api/v1/federation/receive` stores the memory with correct metadata
- [ ] Duplicate memory is detected and returns `{"status": "duplicate"}`
- [ ] `council federation setup` configures shared_secret and api_endpoint
- [ ] `pytest tests/test_federation_memory.py -v` passes

**Out of Scope (DO NOT TOUCH):**
- Node registry (Phase 0)
- ComputeDispatcher (Phase 2)
- Template loader (Phase 4)

---

**Phase 3 Acceptance Criteria:**
- [ ] All 3 registry SELECT queries include `api_endpoint`
- [ ] Remote councils can register without local filesystem path
- [ ] api_endpoint can be set via API
- [ ] shared_secret is auto-generated and configurable
- [ ] Memory federation between councils works end-to-end with deduplication
- [ ] All 6 federation gaps from research are resolved
<!-- ID: phase_4 -->
## Phase 4 — Intelligent File Sync (Syncthing)

**Goal:** Role-based file synchronization across platform nodes using Syncthing, with automatic folder configuration via REST API.

**Prerequisites:** Phase 0 complete (node registry with role + capabilities). Syncthing installed on nodes.

**Why:** Flat sync (same paths to all nodes) wastes bandwidth and disk. GPU compute nodes don't need web pages. Dev workstations don't need CI artifacts. Role-based policies sync only what each node type needs.

---

### Task Package P4.1 — Syncthing Service & Role-Based Sync Config

**Scope**: Add Syncthing Docker service, sync policy config, and role-based folder resolution.

**Files to Create**: `src/council_mcp/platform/sync_policies.py`
**Files to Modify**: `deploy/docker-compose.yaml`, `src/council_mcp/config/__init__.py`, `templates/defaults/council.yaml`

**Dependencies**: Phase 0 complete (NodeRegistry with `role` field).

#### Specifications

1. Add `syncthing` service to `deploy/docker-compose.yaml`:
   - Image: `syncthing/syncthing:latest`
   - Bind to `${TAILSCALE_IP:-127.0.0.1}:8384` (GUI) and `:22000` (sync protocol)
   - Volume: `syncthing_data:/var/syncthing`
   - Network: `backend`
   - Resource limits: 0.5 CPU, 512MB memory

2. Add config keys to `DEFAULT_CONFIG` and `council.yaml`:
   ```yaml
   council:
     platform:
       sync:
         enabled: false
         syncthing_url: "http://localhost:8384"
         syncthing_api_key: ""
         default_sync_paths:
           - ".council/web/pages"
           - ".council/web/static"
         role_policies:
           hub:
             sync_paths: [".council/web/pages", ".council/web/static", ".council/web/routes"]
             direction: "sendreceive"
           gpu-compute:
             sync_paths: [".council/web/pages"]
             direction: "receiveonly"
           dev-workstation:
             sync_paths: [".council/web/pages", ".council/web/static", ".council/web/routes"]
             direction: "sendreceive"
           ci-runner:
             sync_paths: []
             direction: "receiveonly"
   ```

3. Create `sync_policies.py` with:
   ```python
   class SyncPolicyResolver:
       def resolve_sync_paths(self, node_role: str) -> list[dict]:
           """Return sync folder configs for a given node role."""
       def get_policy_for_node(self, hostname: str) -> dict:
           """Look up node role from registry, return policy."""
   ```

4. Add `CONFIG_SCHEMA` entries for all new sync keys so they appear in web UI config editor.

#### Verification
- [x] `docker compose config` validates with syncthing service
- [x] `pytest tests/test_sync_policies.py -v` passes — 24/24 tests, resolver returns correct paths per role
- [x] Config keys exist in both `DEFAULT_CONFIG` and `council.yaml` with matching values
- [x] CONFIG_SCHEMA entries exist for all sync keys (5 entries)

#### Out of Scope (DO NOT TOUCH)
- Syncthing device pairing (manual for now — see Open Questions)
- Template loader changes (Phase 4.3)
- connect_cmd.py modifications

---

### Task Package P4.2 — Automatic Syncthing Folder Management

**Scope**: Use Syncthing REST API to automatically configure folders when a node joins the platform.

**Files to Create**: `src/council_mcp/platform/syncthing_client.py`
**Files to Modify**: `src/council_mcp/platform/nodes.py` (NodeRegistry — add sync hook)

**Dependencies**: P4.1 complete.

#### Specifications

1. Create `syncthing_client.py` with:
   ```python
   class SyncthingClient:
       def __init__(self, base_url: str, api_key: str) -> None: ...

       async def get_config(self) -> dict:
           """GET /rest/config — current Syncthing config."""

       async def add_folder(self, folder_id: str, path: str, 
                            devices: list[str], folder_type: str = "sendreceive") -> None:
           """POST /rest/config/folders — add a sync folder."""

       async def add_device(self, device_id: str, name: str) -> None:
           """POST /rest/config/devices — register a remote device."""

       async def get_status(self, folder_id: str) -> dict:
           """GET /rest/db/status — folder sync completion."""

       async def get_connections(self) -> dict:
           """GET /rest/system/connections — connected devices."""
   ```

2. Add sync hook to `NodeRegistry.register_node()`:
   - After successful registration, if `sync.enabled` is true:
   - Resolve sync policy for the node's role via `SyncPolicyResolver`
   - Call `SyncthingClient.add_device()` to register the node
   - Call `SyncthingClient.add_folder()` for each path in the policy
   - Log sync configuration via `append_entry`

3. Add sync status to `GET /api/platform/nodes` response:
   - For each node, include `sync_status: {folders: [{id, completion_pct}]}`
   - Source: `SyncthingClient.get_status()` per folder

4. Add reverse sync consideration:
   - Hub folders that push config to workers use `sendonly` type
   - Worker folders use `receiveonly` for config paths
   - Shared content (web pages) uses `sendreceive` bidirectional

#### Verification
- [x] `pytest tests/test_syncthing_client.py -v` passes with mocked Syncthing API -- 33/33 pass (0.45s)
- [x] Node registration with sync enabled triggers folder creation -- TestTriggerSyncSetup (6 tests), TestUpsertNodeSyncHook (2 tests)
- [x] Sync status appears in `/api/platform/nodes` response — `_get_syncthing_health()` helper added to system.py, each node serialized with `sync_status` field ("healthy"/"unreachable"/"disabled"/"unknown"). 17/17 node API tests pass, inline verification confirms field present.
- [x] Reverse sync: hub sends config, workers receive -- folder_type from role policies passed to add_folder

#### Out of Scope (DO NOT TOUCH)
- Syncthing device ID exchange (manual — Syncthing generates device IDs)
- connect_cmd.py changes
- Template loader changes

---

### Task Package P4.3 — Sync-Aware Template Loader

**Scope**: Enhance `ProjectTemplateLoader` to discover pages from synced directories in addition to local `.council/web/pages/`.

**Files to Modify**: `src/council_mcp/web/template_loader.py`

**Dependencies**: P4.1 complete (sync config paths available).

#### Specifications

1. Modify `ProjectTemplateLoader.discover_pages()`:
   - Read `council.sync.default_sync_paths` from config
   - For each sync path containing `web/pages`, add to discovery search paths
   - Maintain existing 20-page limit across ALL paths (not per-path)
   - Maintain existing 30-second TTL cache

2. Add `_get_synced_page_paths(repo_path: str) -> list[Path]`:
   - Resolve sync paths relative to repo_path
   - Filter to only paths that exist on disk
   - Return as additional search directories

3. Cache invalidation awareness:
   - When Syncthing syncs new files, the 30-second TTL handles discovery
   - No Syncthing event webhook needed (TTL is sufficient for page discovery)

#### Verification
- [x] `pytest tests/test_template_loader_sync.py -v` passes — 20/20 tests pass (0.40s), synced pages discovered
- [x] Existing template loader tests still pass — 40/40 pass (0.47s, zero regressions)
- [x] Page limit enforced across local + synced paths combined — TestPageLimitAcrossPaths verifies
- [x] Non-existent sync paths handled gracefully — TestGetSyncedPagePaths::test_skips_nonexistent_paths + TestDiscoverPagesSynced::test_nonexistent_sync_path_no_crash

#### Out of Scope (DO NOT TOUCH)
- FrontmatterStrippingLoader (unchanged)
- base.html or base_sidebar.html templates
- Syncthing client or policy code
<!-- ID: phase_5 -->
## Phase 5 — Distributed Agent Execution

**Goal:** Run SDK agent sessions on remote Ray worker nodes, with token streaming back to the hub for WebSocket delivery.

**Prerequisites:** Phase 0 complete (node registry), Phase 2 complete (compute dispatch). Ray cluster operational (`council connect start` with supervision from P0.0).

**Why:** Heavy agent workloads (Claude sessions, code generation) should run on GPU-equipped worker nodes while the hub handles coordination and UI. This keeps the hub responsive.

**Known Gap — Git Worktree**: Remote agent execution requires the agent's working directory to exist on the worker node. Current system assumes local filesystem. For repos not synced to workers, the agent must either: (a) operate without local repo access (chat-only), or (b) use `git worktree` to create a lightweight checkout on the worker. **This phase does NOT implement worktree automation** — it routes agents to nodes that already have the repo (via `NodeRegistry.repos` field). Worktree automation is deferred to a future phase.

---

### Task Package P5.1 — RemoteAgentActor

**Scope**: Create a Ray Actor that wraps the SDKWorker lifecycle for remote execution.

**Files to Create**: `src/council_mcp/compute/remote_agent.py`
**Files to Modify**: None (new file only).

**Dependencies**: Phase 0 complete, Ray cluster operational.

#### Specifications

1. Create `RemoteAgentActor` as a Ray Actor:
   ```python
   @ray.remote(max_restarts=3)
   class RemoteAgentActor:
       def __init__(self, session_id: str, provider: str, model: str,
                    system_prompt: str, repo_path: str | None = None) -> None:
           """Initialize SDKWorker on the remote node."""

       async def send_message(self, message: str) -> None:
           """Send user message to the agent session."""

       async def get_response_stream(self) -> ray.util.queue.Queue:
           """Return a Ray Queue that receives token chunks."""

       async def terminate(self) -> None:
           """Clean shutdown of the agent session."""

       def get_status(self) -> dict:
           """Return session status (active, tokens_generated, etc.)."""
   ```

2. Token streaming via `ray.util.queue.Queue`:
   - Actor pushes `{"type": "token", "text": "..."}` dicts to queue
   - Actor pushes `{"type": "done"}` on completion
   - Actor pushes `{"type": "error", "message": "..."}` on failure
   - Hub reads queue asynchronously (non-blocking)

3. Fault tolerance:
   - `max_restarts=3` — Ray restarts actor on crash
   - On restart, actor sets status to `"restarted"` (session state is lost)
   - After 3 restarts exhausted, session marked as `"failed"`

#### Verification
- [x] `pytest tests/test_remote_agent_actor.py -v` passes with mock SDKProvider — 31 passed in 0.49s
- [x] Token streaming test: test_send_message_streams_tokens_in_order verifies 3 tokens + done in order
- [x] Fault tolerance test: test_simulated_restart_sets_restarted_status verifies restart detection
- [x] Max restarts exhausted test: test_failed_status_rejects_messages + test_failed_status_reported_correctly verify "failed" status

#### Out of Scope (DO NOT TOUCH)
- WorkerPool modifications (P5.2)
- SessionManager modifications (P5.3)
- StreamBridge modifications (P5.3)

---

### Task Package P5.2 — WorkerPool Remote Dispatch

**Scope**: Add remote dispatch path to WorkerPool so it can spawn RemoteAgentActors on target Ray nodes.

**Files to Modify**: `src/council_mcp/sdk/worker_pool.py`

**Dependencies**: P5.1 complete.

#### Specifications

1. Add `_resolve_dispatch_target(session_config: dict) -> str`:
   ```python
   def _resolve_dispatch_target(self, session_config: dict) -> str:
       """Determine where to run this agent session.
       
       Resolution order:
       1. Explicit metadata: session_config.get("dispatch_target")
       2. Repo-node map: config agent_dispatch.repo_node_map[repo_path]
       3. Capability match: NodeRegistry.get_nodes_with_capability("gpu")
       4. Fallback: "local"
       """
   ```

2. Modify `spawn_worker()`:
   - Call `_resolve_dispatch_target()` first
   - If target is `"local"`: use existing UDS-based local worker path (UNCHANGED)
   - If target is a hostname: create `RemoteAgentActor` on that Ray node
   - Store actor handle in `self._remote_actors[session_id]`

3. Add `_spawn_remote_worker(session_id, target_node, config) -> RemoteAgentActor`:
   - Create actor with `ray.remote(...).options(resources={"node:<hostname>": 1})`
   - Register in `_remote_actors` dict
   - Return actor handle

4. **Critical**: Existing UDS-based local worker path MUST remain unchanged. All existing WorkerPool tests must still pass.

#### Verification
- [x] `pytest tests/test_worker_pool_dispatch.py -v` passes — 40/40 pass, dispatch resolution correct
- [x] Remote worker spawn test: creates actor on target node with NodeAffinitySchedulingStrategy — TestSpawnRemoteWorker (5 tests) verify actor creation with scheduling_strategy, fallback when no ray_node_id
- [x] Local path unchanged: `pytest tests/test_worker_pool.py -v` — 60/60 pass (5.89s, zero regressions)
- [x] Fallback test: unavailable remote node falls back to local with warning log — test_remote_failure_falls_back_to_local passes
- [x] Repo validation: `_validate_repo_on_node()` prevents dispatch to nodes without required repo — TestValidateRepoOnNode (7 tests), TestResolveDispatchTargetWithRepoValidation (2 tests)
- [x] NodeAffinitySchedulingStrategy replaces fake resource pinning — test_creates_actor_with_node_affinity_strategy, test_returns_none_when_no_ray_node_id

#### Out of Scope (DO NOT TOUCH)
- UDS protocol code in worker_pool.py
- WorkerEntry dataclass (add new fields only, don't modify existing)
- SessionManager (P5.3)

---

### Task Package P5.3 — Remote Session Lifecycle & Streaming

**Scope**: Integrate remote actors into SessionManager and relay tokens through StreamBridge to WebSocket clients.

**Files to Modify**: `src/council_mcp/sdk/session_manager.py`, `src/council_mcp/sdk/stream_bridge.py`

**Dependencies**: P5.2 complete.

#### Specifications

1. SessionManager integration:
   - `create_session()` calls `WorkerPool.spawn_worker()` (unchanged interface)
   - WorkerPool handles local vs remote transparently
   - `end_session()` calls `actor.terminate()` for remote sessions

2. StreamBridge token relay:
   - Add `_relay_remote_tokens(session_id, queue: ray.util.queue.Queue)`:
   - Async task reads from Ray Queue, pushes to WebSocket via StreamBridge
   - Handles `{"type": "done"}` to close stream
   - Handles `{"type": "error"}` to send error to client

3. Session cleanup:
   - On session end or timeout: `ray.kill(actor)` to free resources
   - Remove from `_remote_actors` dict
   - Log cleanup via `append_entry`

4. Config & feature flags:
   - `council.compute.agent_dispatch.enabled` defaults to `false`
   - `council.compute.agent_dispatch.repo_node_map` — dict mapping repo paths to preferred nodes
   - Add to both `DEFAULT_CONFIG` and `council.yaml`
   - Add `CONFIG_SCHEMA` entries

#### Verification
- [x] `pytest tests/test_session_manager_remote.py -v` passes — 42/42 tests pass. Session creates with remote actor via test_create_session_delegates_to_worker_pool.
- [x] End-to-end streaming test: remote actor tokens arrive at WebSocket client — test_send_message_uses_remote_path_for_remote_worker validates TextDelta("Remote output") relayed through bridge.
- [x] Session cleanup test: actor terminated, resources freed — test_end_session_calls_pool_end_session + test_end_session_cleanup_with_remote_worker_entry pass.
- [x] Feature flag test: disabled by default, local execution only — test_dispatch_disabled_by_default + test_dispatch_has_repo_node_map pass.
- [x] Config keys in both `DEFAULT_CONFIG` and `council.yaml` — test_yaml_has_agent_dispatch_section + test_schema_has_enabled_key + test_schema_has_repo_node_map_key pass.
- [x] Crash/restart UX contract: StreamBridge failure callbacks + SessionManager crash handling — TestStreamBridgeFailureCallbacks (6 tests), TestStreamRemoteMessageCrashContract (4 tests), TestHandleRemoteFailure (3 tests), TestMarkDegraded (2 tests).
- [x] Zero regressions: 86 session_manager + 45 stream_bridge + 40 worker_pool_dispatch + 31 remote_agent_actor tests pass (202 total).

#### Out of Scope (DO NOT TOUCH)
- WebSocket transport code
- Authentication/authorization
- RemoteAgentActor internals (P5.1)
<!-- ID: phase_6 -->
## Phase 6 — Platform Dashboard

**Goal:** Web UI dashboard showing node status, resource utilization, service health, and sync status across the platform.

**Prerequisites:** Phase 0 complete (node registry API), Phase 4 partial (sync status API helpful but not required).

**Why:** Operators need visibility into the distributed platform without SSH-ing into each node. One page shows everything.

---

### Task Package P6.1 — Dashboard Page & Real-Time Updates

**Scope**: Create the platform dashboard page with node status cards and auto-refresh.

**Files to Create**: `.council/web/pages/platform.html.j2`, `.council/web/static/css/pages/platform.css`, `.council/web/static/js/platform.js`
**Files to Modify**: None (all new files, uses existing custom pages infrastructure).

**Dependencies**: Phase 0 complete (node API endpoints exist).

#### Specifications

1. Create `platform.html.j2` with frontmatter:
   ```yaml
   ---
   nav_label: Platform
   nav_order: 5
   nav_group: System
   nav_group_order: 1
   nav_group_icon: server
   ---
   ```

2. Dashboard layout:
   - **Node cards**: One card per registered node showing hostname, role, status (online/stale/offline), last heartbeat, capabilities (CPU/GPU/memory)
   - **Service health**: TEI status, Ray cluster status, Syncthing sync status (if enabled)
   - **Resource summary**: Total CPU, GPU, memory across all online nodes

3. Auto-refresh:
   - `platform.js` polls `GET /api/platform/nodes` every 10 seconds
   - Updates node cards in-place (no full page reload)
   - Stale nodes (no heartbeat > threshold) shown with warning indicator
   - Offline nodes shown with error indicator

4. Council isolation:
   - Dashboard shows nodes filtered by active council context
   - Uses `councils_served` field from `platform_nodes` for context filtering
   - Listens for `councilSwitched` event to reload

#### Verification
- [x] Page loads at `/platform` with correct layout — 21/21 tests pass (test_platform_pages.py). Routes at /platform and /nodes return 200. Platform page renders metrics section, service health, nodes grid.
- [x] Node status cards display correct data from API — TestPlatformPageRenders verifies metrics section, service health cards, node grid present in HTML.
- [x] Auto-refresh updates cards within 15 seconds of status change — platform.js uses 10s setInterval polling via API.get('/api/platform/nodes') + API.get('/api/system/health'). nodes.js uses 15s polling.
- [x] Council switch shows different node sets — platform.js and nodes.js both listen for `councilSwitched` window event and reload data. API passes X-Council-Id header.
- [x] Stale/offline nodes display appropriate warning/error indicators — getStatusBadgeClass() maps status to badge--success/warning/error CSS classes. 31 regression tests pass.

#### Out of Scope (DO NOT TOUCH)
- Node registration logic (Phase 0)
- Health check internals
- base.html template

---

### Task Package P6.2 — Enhanced Platform Health API

**Scope**: Create a unified health endpoint aggregating node, service, and sync health.

**Files to Create**: `src/council_mcp/web/routes/platform_health.py`
**Files to Modify**: `src/council_mcp/web/app.py` (register route)

**Dependencies**: Phase 0 complete, Phase 4 helpful (sync status).

#### Specifications

1. Create `GET /api/platform/health` endpoint:
   ```python
   async def platform_health(request: Request) -> JSONResponse:
       """Aggregate platform health from all subsystems."""
       return {
           "nodes": {
               "total": int,
               "online": int,
               "stale": int,
               "offline": int,
           },
           "services": {
               "ray": {"status": "connected|disconnected", "nodes": int, "gpus": int},
               "tei": {"status": "healthy|unreachable|disabled", "url": str},
               "syncthing": {"status": "healthy|unreachable|disabled", "folders": int},
           },
           "resources": {
               "total_cpus": int,
               "total_gpus": int,
               "total_memory_gb": float,
           },
           "alerts": [
               {"level": "warning|critical", "message": str, "node": str | None}
           ],
       }
   ```

2. Alert thresholds (from config):
   - `council.platform.health.stale_threshold_seconds`: Node stale alert (default: 120)
   - `council.platform.health.sync_lag_threshold_seconds`: Sync lag alert (default: 300)
   - Add to both `DEFAULT_CONFIG` and `council.yaml`

3. Health history (optional enhancement):
   - Store last 24h of health snapshots in memory (list of timestamped dicts)
   - `GET /api/platform/health/history` returns time series
   - No database persistence needed (in-memory ring buffer, lost on restart)

4. Auth required on all endpoints. Council isolation via `_get_active_council_id(request)`.

#### Verification
- [x] `curl` with auth returns comprehensive health JSON — 31/31 tests pass (test_platform_health.py). TestHealthEndpoint verifies nodes/services/resources/alerts/timestamp in response.
- [x] Alerts array populated when nodes are stale — TestAlertGeneration verifies stale node triggers warning alert with node hostname.
- [x] Config-driven thresholds honored — TestConfigThresholds verifies custom stale_threshold_seconds=600 prevents stale classification for 200s-old heartbeat. Config keys dual-registered.
- [x] Auth required (401 without token) — TestAuthRequired (2 tests) confirms both /api/platform/health and /api/platform/health/history return 401 without auth.
- [x] Council isolation applied — TestCouncilIsolation (2 tests) confirms get_nodes_for_council called with council_id when set, get_nodes called when no council.

#### Out of Scope (DO NOT TOUCH)
- Existing `/api/system/health` endpoint (keep as-is, this is a new platform-specific endpoint)
- Node registration logic
- Syncthing client internals
<!-- ID: phase_7 -->
**Objective:** Automate TEI (Text Embeddings Inference) Docker container lifecycle as part of `council connect start/stop`. When a gpu-compute node joins the cluster, TEI starts automatically. When it disconnects, TEI shuts down. Supervision loop monitors TEI health alongside Ray.

**Dependencies:** Phase 0 (node registry, connect supervision), Phase 1 (TEI client integration in embeddings.py)

**Replaces:** P1.2 (TEI Deployment Setup) which was deferred as operational/manual. Phase 7 automates what P1.2 described as a manual process.

**Design Decisions:**
1. **Docker CLI via subprocess** — matches existing Ray process management pattern (line 857, 1054 in connect_cmd.py). No Docker Python SDK dependency.
2. **Role-based activation** — only `gpu-compute` nodes start TEI (configurable via `council.node.services_by_role`). Other roles skip TEI entirely.
3. **Tailscale IP binding** — TEI port binds to Tailscale IP (NEVER 0.0.0.0). Uses `deployment.hub_tailscale_ip` config or auto-detects local Tailscale IP.
4. **Graceful degradation** — if Docker not installed, GPU unavailable, or container fails to start, log warning and continue without TEI. Ray worker still functions.
5. **Supervision integration** — TEI health check runs in existing RayWorkerSupervisor heartbeat loop. TEI crash triggers restart with exponential backoff.
6. **Service registration** — populates the existing `services` array (currently hardcoded `[]` at connect_cmd.py line 436) with TEI endpoint info, enabling hub-side service discovery via `NodeRegistry.get_service_endpoint("tei")`.
7. **Config-driven** — all values from `council.compute.tei_container.*` and `council.node.services_by_role.*`, dual-registered in DEFAULT_CONFIG and council.yaml.

---

### Task Package P7.1: TEIContainerManager Class

**Scope:** Create a new `TEIContainerManager` class that manages the Docker container lifecycle for TEI via subprocess calls. Self-contained module with no dependencies on connect_cmd.py internals.
**Files to Create:**
- `src/council_mcp/compute/tei_container.py` — TEIContainerManager class
**Files to Modify:**
- `src/council_mcp/config/__init__.py` — add `tei_container.*` config keys to DEFAULT_CONFIG and CONFIG_SCHEMA
- `src/council_mcp/templates/defaults/council.yaml` — add `tei_container.*` defaults under `compute` section
**Files to Create (tests):**
- `tests/test_tei_container.py` — unit tests for TEIContainerManager

**Dependencies:** None (self-contained module)

#### Specifications

1. **New file `src/council_mcp/compute/tei_container.py`:**

   ```python
   class TEIContainerManager:
       """Manages TEI Docker container lifecycle via subprocess."""

       CONTAINER_NAME: str = "council-tei"

       def __init__(self, config: dict[str, Any] | None = None) -> None:
           """Load config from council.compute.tei_container.* with fallbacks."""

       def start(self, bind_ip: str = "127.0.0.1", gpu: bool = True) -> bool:
           """Start TEI container. Returns True on success.

           Steps:
           1. Check Docker installed: subprocess.run(["docker", "info"], ...)
           2. Cleanup stale container: docker stop + docker rm (best-effort, ignore errors)
           3. Build docker run command:
              - --name council-tei
              - -d (detached)
              - --gpus all (only if gpu=True)
              - -p {bind_ip}:{port}:80
              - -e MODEL_ID={model}
              - -e DTYPE={dtype}
              - {image}
           4. Run subprocess.run(cmd, capture_output=True, text=True)
           5. Wait for health: poll get_url()/health every 2s, up to startup_timeout_seconds
           6. Return True if healthy, False otherwise
           """

       def stop(self) -> bool:
           """Stop and remove TEI container. Returns True on success.

           Steps:
           1. docker stop council-tei (10s timeout)
           2. docker rm council-tei
           Both best-effort — log warnings on failure, never raise.
           """

       def health_check(self) -> bool:
           """Check TEI health via HTTP GET to {url}/health.

           Uses httpx with tei_timeout_seconds. Returns True if 200 OK.
           Returns False on any error (connection, timeout, non-200).
           """

       def is_running(self) -> bool:
           """Check if council-tei container exists and is running.

           Uses: docker inspect --format '{{.State.Running}}' council-tei
           Returns True only if output is 'true'.
           """

       def get_url(self, bind_ip: str = "127.0.0.1") -> str:
           """Return the TEI endpoint URL: http://{bind_ip}:{port}"""

       def get_container_logs(self, tail: int = 50) -> str:
           """Return last N lines of container logs for debugging.

           Uses: docker logs --tail {tail} council-tei
           """

       @staticmethod
       def check_docker_available() -> bool:
           """Check if Docker is installed and the daemon is running.

           Uses: docker info (returns True if exit code 0)
           """

       @staticmethod
       def check_gpu_available() -> bool:
           """Check if Docker GPU support is available.

           Uses: docker run --rm --gpus all ubuntu nvidia-smi
           Returns True if exit code 0. Caches result for session lifetime.
           """
   ```

2. **Config keys — add to DEFAULT_CONFIG** (inside `"compute"` dict, after `agent_dispatch` block, around line 805):
   ```python
   # TEI container lifecycle (P7.1)
   "tei_container": {
       "enabled": False,                          # Master toggle
       "image": "ghcr.io/huggingface/text-embeddings-inference:turing-1.5",
       "model": "sentence-transformers/all-MiniLM-L6-v2",  # 384-dim, matches existing
       "dtype": "float16",                        # float16 for GPU, float32 for CPU
       "port": 8080,                              # Host port (binds to Tailscale IP)
       "startup_timeout_seconds": 120,            # Max wait for model load + health
       "health_check_interval_seconds": 30,       # Supervision health check interval
       "health_check_timeout_seconds": 5,         # HTTP timeout for /health probe
   },
   ```

3. **Config keys — add to DEFAULT_CONFIG** (inside `"node"` dict, after `default_role`, around line 813):
   ```python
   "services_by_role": {                          # Per-role service policies (P7.1)
       "gpu-compute": {"tei": True},
       "dev-workstation": {"tei": False},
       "ci-runner": {"tei": False},
       "hub": {"tei": False},
   },
   ```

4. **CONFIG_SCHEMA entries** — add after existing `agent_dispatch.repo_node_map` entry (around line 1424):
   ```python
   "council.compute.tei_container.enabled": {
       "type": "bool", "section": "Compute", "tier": 2,
       "description": "Auto-start TEI Docker container on council connect start",
       "default": False, "restart_required": False,
   },
   "council.compute.tei_container.image": {
       "type": "str", "section": "Compute", "tier": 2,
       "description": "Docker image for TEI embedding server",
       "default": "ghcr.io/huggingface/text-embeddings-inference:turing-1.5",
   },
   "council.compute.tei_container.model": {
       "type": "str", "section": "Compute", "tier": 2,
       "description": "HuggingFace model ID for TEI to load",
       "default": "sentence-transformers/all-MiniLM-L6-v2",
   },
   "council.compute.tei_container.dtype": {
       "type": "str", "section": "Compute", "tier": 2,
       "description": "Model data type (float16 for GPU, float32 for CPU)",
       "default": "float16", "enum": ["float16", "float32", "bfloat16"],
   },
   "council.compute.tei_container.port": {
       "type": "int", "section": "Compute", "tier": 2,
       "description": "Host port for TEI container (binds to Tailscale IP)",
       "default": 8080, "min": 1024, "max": 65535,
   },
   "council.compute.tei_container.startup_timeout_seconds": {
       "type": "int", "section": "Compute", "tier": 2,
       "description": "Max seconds to wait for TEI container startup and model load",
       "default": 120, "min": 10, "max": 600,
   },
   "council.compute.tei_container.health_check_interval_seconds": {
       "type": "int", "section": "Compute", "tier": 2,
       "description": "Seconds between TEI health checks in supervision loop",
       "default": 30, "min": 5, "max": 300,
   },
   "council.compute.tei_container.health_check_timeout_seconds": {
       "type": "int", "section": "Compute", "tier": 2,
       "description": "HTTP timeout for TEI health check requests",
       "default": 5, "min": 1, "max": 30,
   },
   "council.node.services_by_role": {
       "type": "dict", "section": "Node", "tier": 2,
       "description": "Per-role service activation policies (e.g., tei: true/false)",
       "default": {"gpu-compute": {"tei": True}, "dev-workstation": {"tei": False}},
   },
   ```

5. **council.yaml template defaults** — add after `agent_dispatch` block (around line 784):
   ```yaml
   # TEI container lifecycle (P7.1)
   tei_container:
     enabled: false                               # Auto-start TEI on council connect start
     image: "ghcr.io/huggingface/text-embeddings-inference:turing-1.5"
     model: "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim, matches existing embeddings
     dtype: "float16"                             # float16 for GPU, float32 for CPU
     port: 8080                                   # Host port (binds to Tailscale IP)
     startup_timeout_seconds: 120                 # Max wait for model load
     health_check_interval_seconds: 30            # Supervision health check interval
     health_check_timeout_seconds: 5              # HTTP timeout for /health probe
   ```

   And under `node` section (after `default_role`, around line 791):
   ```yaml
   services_by_role:                              # Per-role service policies (P7.1)
     gpu-compute:
       tei: true
     dev-workstation:
       tei: false
     ci-runner:
       tei: false
     hub:
       tei: false
   ```

#### Verification
- [x] `TEIContainerManager.start()` calls `docker run` with correct flags (mock subprocess)
- [x] `TEIContainerManager.stop()` calls `docker stop` + `docker rm` (mock subprocess)
- [x] `TEIContainerManager.health_check()` returns True on 200, False on error (mock httpx)
- [x] `TEIContainerManager.is_running()` parses docker inspect output correctly
- [x] `check_docker_available()` returns False when docker not installed
- [x] `check_gpu_available()` returns False when nvidia-smi fails
- [x] GPU flag omitted when `gpu=False` in start()
- [x] Stale container cleanup runs before start (docker stop + rm, errors ignored)
- [x] Startup timeout honored — returns False if health check never passes
- [x] All 8 `tei_container.*` config keys in DEFAULT_CONFIG
- [x] All 8 `tei_container.*` config keys in CONFIG_SCHEMA with correct types/bounds
- [x] `services_by_role` in DEFAULT_CONFIG and CONFIG_SCHEMA
- [x] All config keys mirrored in `templates/defaults/council.yaml`
- [x] `pytest tests/test_tei_container.py -v` passes — 40/40 (0.40s)

#### Out of Scope (DO NOT TOUCH)
- `connect_cmd.py` — P7.2 handles integration
- `embeddings.py` — existing tei_url routing unchanged
- `nodes.py` — service discovery already works via get_service_endpoint()
- Any web routes or dashboard code

---

### Task Package P7.2: Connect Command Integration

**Scope:** Wire TEIContainerManager into `council connect start` and `council connect stop`. Add TEI health monitoring to RayWorkerSupervisor. Populate `services` array in hub registration.
**Files to Modify:**
- `src/council_mcp/cli/connect_cmd.py` — integrate TEI into start(), stop(), RayWorkerSupervisor, _register_with_hub()
**Files to Create (tests):**
- `tests/test_connect_tei_integration.py` — integration tests for TEI lifecycle in connect command

**Dependencies:** P7.1 (TEIContainerManager class must exist)

#### Specifications

1. **Modify `_register_with_hub()` signature** (line 405) — add `services` parameter:
   ```python
   def _register_with_hub(
       hub_url: str,
       api_key: str,
       role: str,
       capabilities: dict[str, Any],
       councils_served: list[str],
       repos: list[str] | None = None,
       ray_node_id: str | None = None,
       services: list[dict[str, Any]] | None = None,  # NEW
   ) -> bool:
   ```
   Replace hardcoded `"services": []` (line 436) with `"services": services or []`.

2. **Add helper function `_should_start_tei(role: str) -> bool`:**
   ```python
   def _should_start_tei(role: str) -> bool:
       """Check if TEI should be started for this node role."""
       cfg = get_council_config()
       tei_cfg = cfg.get("council", {}).get("compute", {}).get("tei_container", {})
       if not tei_cfg.get("enabled", False):
           return False
       node_cfg = cfg.get("council", {}).get("node", {})
       role_policies = node_cfg.get("services_by_role", {})
       role_policy = role_policies.get(role, {})
       return bool(role_policy.get("tei", False))
   ```

3. **Add helper function `_get_tailscale_ip() -> str | None`:**
   ```python
   def _get_tailscale_ip() -> str | None:
       """Auto-detect local Tailscale IP address.

       Tries: tailscale ip -4
       Falls back to: config deployment.hub_tailscale_ip
       Falls back to: None
       """
   ```

4. **Modify `start()` function** — add TEI lifecycle between step 8 (Ray connectivity verified) and step 10 (hub registration):

   After line 877 (PID write), insert:
   ```python
   # 9a. TEI container lifecycle (if enabled for this role)
   tei_manager = None
   tei_services: list[dict[str, Any]] = []
   if _should_start_tei(resolved_role):
       from council_mcp.compute.tei_container import TEIContainerManager
       tei_manager = TEIContainerManager()

       if not TEIContainerManager.check_docker_available():
           click.echo("  TEI:           skipped (Docker not available)")
           logger.warning("TEI skipped: Docker not available")
       else:
           # Determine bind IP (Tailscale IP or 127.0.0.1)
           bind_ip = _get_tailscale_ip() or "127.0.0.1"
           has_gpu = TEIContainerManager.check_gpu_available()

           click.echo(f"Starting TEI container (bind={bind_ip}, gpu={has_gpu})...")
           if tei_manager.start(bind_ip=bind_ip, gpu=has_gpu):
               tei_url = tei_manager.get_url(bind_ip=bind_ip)
               click.echo(f"  TEI:           running at {tei_url}")
               tei_services.append({
                   "name": "tei",
                   "port": tei_manager._port,
               })
           else:
               logs = tei_manager.get_container_logs(tail=20)
               click.echo(f"  TEI:           failed to start (non-fatal)")
               if logs:
                   click.echo(f"  TEI logs:\n{logs}")
               logger.warning("TEI container failed to start — continuing without TEI")
               tei_manager = None
   ```

   Modify hub registration call (line 904) to pass services:
   ```python
   registered = _register_with_hub(
       hub_url, api_key, resolved_role, capabilities, councils_served,
       repos=detected_repos,
       ray_node_id=ray_node_id,
       services=tei_services,  # NEW
   )
   ```

5. **Modify `RayWorkerSupervisor.__init__()` — accept TEI manager:**
   ```python
   def __init__(
       self,
       head_address: str,
       ray_cmd: list[str],
       hub_url: str,
       api_key: str | None = None,
       hostname: str | None = None,
       tei_manager: TEIContainerManager | None = None,  # NEW
   ) -> None:
       # ... existing code ...
       self._tei_manager = tei_manager
       tei_cfg = compute_cfg.get("tei_container", {})
       self._tei_health_interval: float = float(
           tei_cfg.get("health_check_interval_seconds", 30)
       )
   ```

6. **Modify `RayWorkerSupervisor.run()` — add TEI health check to heartbeat cycle:**

   Inside the `while self._running` loop, after the heartbeat block (around line 671), add:
   ```python
   # TEI health check (piggyback on heartbeat timer)
   if (
       self._tei_manager is not None
       and time_since_heartbeat == 0.0  # just sent heartbeat
   ):
       if not self._tei_manager.health_check():
           logger.warning("TEI health check failed — attempting restart")
           click.echo("Supervisor: TEI unhealthy, restarting...")
           bind_ip = _get_tailscale_ip() or "127.0.0.1"
           has_gpu = TEIContainerManager.check_gpu_available()
           self._tei_manager.stop()
           if not self._tei_manager.start(bind_ip=bind_ip, gpu=has_gpu):
               logger.warning("TEI restart failed — will retry next cycle")
   ```

7. **Modify supervisor creation** (line 917) to pass tei_manager:
   ```python
   supervisor = RayWorkerSupervisor(
       head_address=address,
       ray_cmd=cmd,
       hub_url=hub_url,
       api_key=api_key,
       hostname=local_hostname,
       tei_manager=tei_manager,  # NEW (may be None)
   )
   ```

8. **Modify `_shutdown_handler()`** (line 926) — stop TEI before Ray:
   ```python
   def _shutdown_handler(signum: int, frame: object) -> None:
       click.echo("\nShutting down...")
       supervisor.stop()
       # Stop TEI container first (if managed)
       if tei_manager is not None:
           click.echo("Stopping TEI container...")
           tei_manager.stop()
       # Deregister from hub before stopping Ray
       if api_key:
           _deregister_from_hub(hub_url, api_key, local_hostname)
       subprocess.run(["ray", "stop"], capture_output=True)
       _remove_ray_pid()
       click.echo("Worker stopped.")
       sys.exit(0)
   ```

9. **Modify `stop()` command** (line 1026) — stop TEI container:

   After hub deregistration block (around line 1046), before PID check (line 1048), add:
   ```python
   # Stop TEI container (best-effort)
   cfg_for_stop = get_council_config()
   tei_cfg = cfg_for_stop.get("council", {}).get("compute", {}).get("tei_container", {})
   if tei_cfg.get("enabled", False):
       from council_mcp.compute.tei_container import TEIContainerManager
       mgr = TEIContainerManager()
       if mgr.is_running():
           click.echo("Stopping TEI container...")
           if mgr.stop():
               click.echo("  TEI:           stopped")
           else:
               click.echo("  TEI:           stop failed (non-fatal)")
   ```

10. **Update connection summary** (line 940) — add TEI status line:
    ```python
    if tei_manager and tei_services:
        click.echo(f"  TEI:           running (port {tei_services[0]['port']})")
    elif _should_start_tei(resolved_role):
        click.echo(f"  TEI:           failed/skipped")
    else:
        click.echo(f"  TEI:           not enabled for role '{resolved_role}'")
    ```

#### Verification
- [ ] `council connect start --role gpu-compute` with TEI enabled starts TEI container (mock subprocess + httpx)
- [ ] `council connect start --role dev-workstation` skips TEI entirely
- [ ] TEI disabled in config skips TEI even for gpu-compute role
- [ ] `_register_with_hub()` includes `services=[{"name": "tei", "port": 8080}]` when TEI running
- [ ] `_register_with_hub()` includes `services=[]` when TEI not running
- [ ] Docker not available logs warning and continues without TEI
- [ ] GPU not available starts TEI without --gpus flag
- [ ] TEI startup failure logs container logs and continues
- [ ] RayWorkerSupervisor checks TEI health on heartbeat cycle
- [ ] TEI unhealthy triggers stop + restart attempt
- [ ] `council connect stop` stops TEI container before Ray
- [ ] `_shutdown_handler` stops TEI before Ray on SIGTERM/SIGINT
- [ ] `_should_start_tei()` reads config correctly for each role
- [ ] `_get_tailscale_ip()` returns IP from `tailscale ip -4` subprocess
- [ ] Connection summary shows TEI status
- [ ] Existing connect tests pass (zero regressions): `pytest tests/test_connect_supervision.py tests/test_connect_registration.py -v`
- [ ] `pytest tests/test_connect_tei_integration.py -v` passes

#### Out of Scope (DO NOT TOUCH)
- `tei_container.py` internals (P7.1 scope)
- `embeddings.py` — existing TEI HTTP routing unchanged
- `nodes.py` — service discovery unchanged
- Web routes, dashboard, platform health API
- Existing supervision tests (test_connect_supervision.py)
- Existing registration tests (test_connect_registration.py)

---

### Task Package P7.3: Service Registration & Dynamic TEI URL

**Scope:** Update `_send_heartbeat()` to include TEI service health status. Add `_resolve_tei_url()` helper to embeddings.py that discovers TEI via NodeRegistry when no static `tei_url` is configured.
**Files to Modify:**
- `src/council_mcp/cli/connect_cmd.py` — enhance `_send_heartbeat()` with service health
- `src/council_mcp/compute/embeddings.py` — add dynamic TEI discovery via NodeRegistry
**Files to Create (tests):**
- `tests/test_tei_service_discovery.py` — tests for heartbeat service status and dynamic TEI URL resolution

**Dependencies:** P7.2 (connect_cmd integration must be complete)

#### Specifications

1. **Modify `_send_heartbeat()` signature** (line 474) — add `services_healthy` parameter:
   ```python
   def _send_heartbeat(
       hub_url: str,
       api_key: str,
       hostname: str,
       ray_connected: bool,
       ray_node_id: str | None = None,
       services_healthy: dict[str, bool] | None = None,  # NEW: {"tei": True/False}
   ) -> bool:
   ```
   Include `services_healthy` in heartbeat payload so hub knows service state.

2. **Modify `RayWorkerSupervisor.run()` heartbeat call** — pass TEI health:
   ```python
   services_healthy = None
   if self._tei_manager is not None:
       services_healthy = {"tei": self._tei_manager.health_check()}
   _send_heartbeat(
       self._hub_url,
       self._api_key,
       self._hostname,
       connected,
       ray_node_id=current_ray_node_id,
       services_healthy=services_healthy,
   )
   ```

3. **Add `_resolve_tei_url()` to embeddings.py:**
   ```python
   def _resolve_tei_url() -> str:
       """Resolve TEI endpoint URL.

       Priority:
       1. Static config: council.compute.tei_url (if non-empty)
       2. Dynamic discovery: NodeRegistry.get_service_endpoint("tei")
       3. Empty string (disabled)

       Caches result for 60 seconds to avoid DB queries on every embed call.
       """
       cfg = get_compute_config()
       static_url = cfg.get("tei_url", "")
       if static_url:
           return static_url

       # Dynamic discovery via NodeRegistry
       try:
           from council_mcp.platform.nodes import NodeRegistry
           registry = NodeRegistry()
           endpoint = registry.get_service_endpoint("tei")
           if endpoint:
               return endpoint["url"]
       except Exception:
           pass
       return ""
   ```

4. **Modify `embed_text_async()` in embeddings.py** — replace static `tei_url` read with `_resolve_tei_url()`:
   ```python
   # Replace: tei_url = cfg.get("tei_url", "")
   # With:    tei_url = _resolve_tei_url()
   ```
   Same change in `embed_texts_async()`.

5. **Caching for `_resolve_tei_url()`** — use a simple module-level cache:
   ```python
   _tei_url_cache: dict[str, Any] = {"url": "", "expires": 0.0}
   _TEI_URL_CACHE_TTL = 60.0  # seconds

   def _resolve_tei_url() -> str:
       now = time.monotonic()
       if _tei_url_cache["expires"] > now:
           return _tei_url_cache["url"]
       # ... resolution logic ...
       _tei_url_cache["url"] = result
       _tei_url_cache["expires"] = now + _TEI_URL_CACHE_TTL
       return result
   ```

#### Verification
- [ ] `_send_heartbeat()` includes `services_healthy` in payload when provided
- [ ] `_send_heartbeat()` omits `services_healthy` when None (backward compat)
- [ ] Supervisor heartbeat includes TEI health status when tei_manager present
- [ ] `_resolve_tei_url()` returns static URL when `tei_url` configured
- [ ] `_resolve_tei_url()` discovers TEI via NodeRegistry when no static URL
- [ ] `_resolve_tei_url()` returns empty string when no TEI available
- [ ] Cache honors 60-second TTL (mock time.monotonic)
- [ ] `embed_text_async()` uses `_resolve_tei_url()` instead of static config read
- [ ] Existing TEI integration tests pass (zero regressions): `pytest tests/test_compute_tei_integration.py -v`
- [ ] `pytest tests/test_tei_service_discovery.py -v` passes

#### Out of Scope (DO NOT TOUCH)
- `tei_container.py` (P7.1)
- `connect_cmd.py` start/stop flow (P7.2)
- NodeRegistry internals (get_service_endpoint already works)
- Dashboard or platform health API
- Heartbeat endpoint on hub side (already accepts arbitrary payload fields)

---

**Phase 7 Acceptance Criteria:**
- [ ] `council connect start --role gpu-compute` auto-starts TEI when enabled
- [ ] `council connect stop` auto-stops TEI container
- [ ] TEI health monitored in supervision loop with auto-restart
- [ ] Hub registration includes TEI in `services` array
- [ ] Heartbeat reports TEI health status
- [ ] `embed_text_async()` auto-discovers TEI via NodeRegistry when no static URL
- [ ] All config keys dual-registered (DEFAULT_CONFIG + council.yaml + CONFIG_SCHEMA)
- [ ] No regressions in existing connect, TEI integration, or supervision tests
<!-- ID: phase_8 -->
## Phase 8 — Local Dev Serving via `council connect serve`

**Objective:** Enable developers to run a full local copy of the Council stack (daemon + web UI) that shares the production Postgres database on Hetzner over Tailscale, auto-joins the Ray compute cluster, and proxies Scribe through the hub — all via a single `council connect serve` command.

**Dependencies:** Phase 0 (connect supervision + node registry), Phase 7 (TEI container lifecycle — soft dependency, TEI integration is additive)

**Operator Decisions (Resolved):**
- Scribe: Hub proxy via SSE endpoint (`http://council-hub:8200/sse`)
- Ray: Auto-join (serve does everything `connect start` does PLUS launches local daemon + web)
- Ports: Same as prod (8015/8016) — dev and prod are different Tailscale IPs, no conflict
- DB: Shared production Postgres over Tailscale (`postgresql://council:<pw>@council-hub:5432/agentkit`)

**Key Architectural Insight:** The web UI (`app.py`) does NOT connect to Postgres directly — everything goes through the local MCP daemon. So `council connect serve` starts a local daemon that:
1. Connects to Hetzner Postgres via `DATABASE_URL` over Tailscale
2. Starts its own MCP WebSocket server on local port 8016
3. Routes Scribe calls through hub's SSE endpoint (MCPClientPool priority 1)
4. Web UI connects to this local daemon (same as prod architecture)

This is essentially `council start` with remote DB + Scribe SSE + auto Ray join.

---

### Task Package P8.1: `council connect serve` Command

**Scope:** Add the `serve` subcommand to the `council connect` click group. This command orchestrates: (1) environment setup from `.council/.env`, (2) Ray cluster join with supervision, (3) local daemon spawn, (4) local web UI spawn with optional hot-reload. Also add `council connect serve --stop` for clean shutdown of all components.

**Files to Modify:**
- `src/council_mcp/cli/connect_cmd.py` — add `serve()` and `_serve_stop()` functions

**Dependencies:** None (P8.2 config keys are read with safe fallbacks)

**Specifications:**

1. Add `serve()` function as `@connect.command()` with these Click options:
   ```python
   @connect.command()
   @click.option("--head-address", default=None, type=str,
       help="Ray head address (host:port). Default: from config.")
   @click.option("--role", default=None, type=str,
       help="Node role (gpu-compute, dev-workstation). Default: from config.")
   @click.option("--daemon-port", default=None, type=int,
       help="Local daemon port. Default: 8016 from config.")
   @click.option("--web-port", default=None, type=int,
       help="Local web UI port. Default: 8015 from config.")
   @click.option("--reload", is_flag=True, default=False,
       help="Enable hot-reload for web UI (uvicorn --reload).")
   @click.option("--no-ray", is_flag=True, default=False,
       help="Skip Ray cluster join (daemon + web only).")
   @click.option("--stop", "do_stop", is_flag=True, default=False,
       help="Stop a running serve instance.")
   def serve(head_address, role, daemon_port, web_port, reload, no_ray, do_stop) -> None:
   ```

2. When `do_stop=True`, call `_serve_stop()` and return. `_serve_stop()` does:
   - Read `.council/serve.pid` JSON file (`{"daemon_pid": int, "web_pid": int, "ray_joined": bool}`)
   - If `ray_joined`: call existing `stop()` logic (deregister from hub, ray stop, remove ray PID)
   - Stop web UI process (SIGTERM, wait 5s, SIGKILL if needed)
   - Stop daemon process (SIGTERM, wait 5s, SIGKILL if needed)
   - Remove `.council/serve.pid`
   - Print summary of what was stopped

3. Main `serve()` flow (when `do_stop=False`):

   **Step A — Environment Setup:**
   - Call `_load_dotenv_from_council()` (already exists in config/__init__.py, ensures `.council/.env` and repo `.env` are loaded)
   - Validate `DATABASE_URL` is set: `os.environ.get("DATABASE_URL")`. If not set, print clear error message with instructions to create `.council/.env` with `DATABASE_URL=postgresql://council:<password>@council-hub:5432/agentkit` and exit with code 1
   - Set `SCRIBE_SSE_ENDPOINT` env var if not already set: read from `council.scribe.sse_endpoint` config, or derive from `council.deployment.hub_tailscale_ip` as `http://{hub_ip}:8200/sse`
   - Set `COUNCIL_API_KEY` from config if not already set: try reading from `secrets/api_key.txt` in repo root (same as docker-entrypoint.sh pattern), or from env
   - Skip `validate_env_or_exit()` validation for Docker-specific vars by setting `COUNCIL_SKIP_ENV_CHECK=1` temporarily if needed (dev mode won't have all Docker vars)

   **Step B — Ray Cluster Join (unless `--no-ray`):**
   - Reuse the existing `start()` function's logic, extracted into a helper `_join_ray_cluster(head_address, role) -> tuple[bool, RayWorkerSupervisor | None]`:
     - Check Ray installed
     - Check for already-running worker
     - Resolve head address, ping host, preflight version check
     - Build and run `ray start` command
     - Verify connectivity, write PID
     - Resolve role, detect capabilities
     - Register with hub (with `services` array including `dev-web` entry)
     - Create `RayWorkerSupervisor` instance
   - If Ray join fails, print warning and continue (dev mode should work without Ray)

   **Step C — Daemon Spawn:**
   - Resolve daemon port: `daemon_port or get_daemon_port()` (from config, default 8016)
   - Resolve web port: `web_port or get_web_port()` (from config, default 8015)
   - Build daemon command: `[sys.executable, "-m", "council_mcp.server", "--transport", "ws", "--ws-port", str(daemon_port)]`
   - Spawn daemon as background process using the same pattern as `_start_background()` in start_cmd.py
   - Write daemon PID to `write_pid_file_atomic()` (uses existing `.council/daemon.pid`)
   - Wait for daemon to be accepting connections (same health-check loop as `_spawn_web_ui`)

   **Step D — Web UI Spawn:**
   - Build web command: `[sys.executable, "-m", "council_mcp.web.app"]`
   - If `--reload` flag: set `COUNCIL_WEB_RELOAD=1` env var (web app.py checks this for uvicorn reload mode)
   - Set `COUNCIL_WORKSPACE` and `COUNCIL_PROJECT` env vars (same as `_spawn_web_ui`)
   - Spawn as background process, capture PID

   **Step E — Write serve.pid and Print Summary:**
   - Write `.council/serve.pid` as JSON: `{"daemon_pid": int, "web_pid": int, "ray_joined": bool, "started_at": ISO timestamp}`
   - Print connection summary:
     ```
     --- Dev Serve Summary ---
       Database:    postgresql://...@council-hub:5432/agentkit (Tailscale)
       Daemon:      ws://localhost:{daemon_port}/mcp
       Web UI:      http://localhost:{web_port}
       Scribe:      hub proxy via SSE (http://council-hub:8200/sse)
       Ray:         connected to {head_address} / skipped
       Hot reload:  enabled / disabled
       Mode:        dev-serve
     ```

   **Step F — Foreground Supervision:**
   - If Ray was joined: start supervisor in daemon thread (same as `start()` background mode)
   - Register SIGTERM/SIGINT handler that calls `_serve_stop()` for clean shutdown
   - Block on `threading.Event().wait()` (keeps main thread alive for signal handling)

4. Add helper `_get_serve_pid_path() -> Path`:
   - Returns `get_repo_root() / ".council" / "serve.pid"`

5. Add helper `_read_serve_pid() -> dict[str, Any] | None`:
   - Read and parse `.council/serve.pid` JSON, return None if doesn't exist or parse fails

6. Add helper `_write_serve_pid(data: dict[str, Any]) -> None`:
   - Write JSON to `.council/serve.pid`

**Verification:**
- [ ] `council connect serve --help` shows all options (head-address, role, daemon-port, web-port, reload, no-ray, stop)
- [ ] `council connect serve` without DATABASE_URL prints clear error and exits 1
- [ ] `council connect serve` with valid DATABASE_URL starts daemon + web + Ray join
- [ ] `council connect serve --no-ray` starts daemon + web without Ray
- [ ] `council connect serve --reload` sets COUNCIL_WEB_RELOAD=1 in web process env
- [ ] `council connect serve --stop` cleanly stops all components and removes serve.pid
- [ ] SIGINT (Ctrl+C) during serve triggers clean shutdown of all components
- [ ] `.council/serve.pid` contains valid JSON with daemon_pid, web_pid, ray_joined
- [ ] `pytest tests/test_connect_serve.py -v` passes

**Out of Scope (DO NOT TOUCH):**
- Config DEFAULT_CONFIG changes (P8.2)
- Hub registration `services` array changes (P8.2)
- .env.example template changes (P8.3)
- Existing `council connect start` behavior
- Existing `council start` behavior
- Any web UI code (app.py, templates, static files)

---

### Task Package P8.2: Dev-Serve Configuration & Hub Registration

**Scope:** Add config keys for dev-serve mode, update hub registration to advertise dev-web services, and ensure the `.council/.env.example` template includes DATABASE_URL for Tailscale.

**Files to Modify:**
- `src/council_mcp/config/__init__.py` — add `dev_serve` config keys to `DEFAULT_CONFIG` and `CONFIG_SCHEMA`
- `src/council_mcp/templates/defaults/council.yaml` — add `dev_serve` config defaults
- `src/council_mcp/cli/connect_cmd.py` — modify `_register_with_hub()` to include dev-web service, modify `_send_heartbeat()` to include service health
- `src/council_mcp/templates/scaffold/.env.example.j2` — add DATABASE_URL and SCRIBE_SSE_ENDPOINT

**Dependencies:** P8.1 (serve command exists)

**Specifications:**

1. Add `dev_serve` section to `DEFAULT_CONFIG` under `council`:
   ```python
   "dev_serve": {
       "enabled": False,                              # True when running via `council connect serve`
       "scribe_sse_endpoint": "",                     # Hub Scribe SSE URL (e.g. http://council-hub:8200/sse)
       "auto_set_scribe_sse": True,                   # Auto-derive from hub_tailscale_ip if not set
       "register_dev_web_service": True,               # Register dev-web in hub node services
       "web_reload": False,                            # Enable uvicorn --reload
   }
   ```

2. Add matching entries to `templates/defaults/council.yaml`:
   ```yaml
   dev_serve:
     enabled: false
     scribe_sse_endpoint: ""
     auto_set_scribe_sse: true
     register_dev_web_service: true
     web_reload: false
   ```

3. Add 5 CONFIG_SCHEMA entries for the dev_serve keys:
   ```python
   "council.dev_serve.enabled": {
       "type": "bool", "section": "dev_serve", "tier": 2,
       "description": "Whether this instance is running via council connect serve",
       "default": False,
   },
   "council.dev_serve.scribe_sse_endpoint": {
       "type": "str", "section": "dev_serve", "tier": 2,
       "description": "Hub Scribe SSE endpoint URL for dev-serve proxy",
       "default": "",
   },
   "council.dev_serve.auto_set_scribe_sse": {
       "type": "bool", "section": "dev_serve", "tier": 2,
       "description": "Auto-derive Scribe SSE URL from hub_tailscale_ip",
       "default": True,
   },
   "council.dev_serve.register_dev_web_service": {
       "type": "bool", "section": "dev_serve", "tier": 2,
       "description": "Register dev-web as a service in hub node registry",
       "default": True,
   },
   "council.dev_serve.web_reload": {
       "type": "bool", "section": "dev_serve", "tier": 2,
       "description": "Enable uvicorn hot-reload for web UI in dev-serve mode",
       "default": False,
   },
   ```

4. Modify `_register_with_hub()` in connect_cmd.py:
   - Add optional parameter `services: list[dict[str, Any]] | None = None`
   - If `services` is provided, use it instead of empty `[]` in the payload
   - In `serve()` (P8.1), pass `services=[{"name": "dev-web", "url": f"http://{local_tailscale_ip}:{web_port}"}]` where `local_tailscale_ip` is detected via `socket.getaddrinfo(socket.gethostname(), None)` or config

5. Modify `_send_heartbeat()` in connect_cmd.py:
   - Add optional parameter `services_healthy: dict[str, bool] | None = None`
   - If provided, include in heartbeat payload: `payload["services_healthy"] = services_healthy`
   - In `serve()` supervisor, heartbeat includes `services_healthy={"dev-web": True}` (always True since we're running)

6. Update `.env.example.j2` scaffold template to include:
   ```
   # Database (required for council connect serve)
   # DATABASE_URL=postgresql://council:<password>@council-hub:5432/agentkit

   # Scribe SSE endpoint (auto-derived from hub_tailscale_ip if not set)
   # SCRIBE_SSE_ENDPOINT=http://council-hub:8200/sse

   # Council API key (required for hub registration)
   # COUNCIL_API_KEY=ck_...
   ```

**Verification:**
- [ ] `dev_serve` section present in `DEFAULT_CONFIG` with all 5 keys
- [ ] `dev_serve` section present in `templates/defaults/council.yaml` with matching values
- [ ] 5 `CONFIG_SCHEMA` entries exist for `council.dev_serve.*`
- [ ] `_register_with_hub()` accepts and uses `services` parameter
- [ ] `_send_heartbeat()` accepts and uses `services_healthy` parameter
- [ ] `.env.example.j2` includes DATABASE_URL, SCRIBE_SSE_ENDPOINT, COUNCIL_API_KEY
- [ ] Hub platform dashboard shows dev instance with `dev-web` service after `council connect serve`
- [ ] Existing `council connect start` tests pass (zero regressions): `pytest tests/test_connect_supervision.py tests/test_connect_registration.py -v`
- [ ] `pytest tests/test_connect_serve_config.py -v` passes

**Out of Scope (DO NOT TOUCH):**
- The `serve()` command itself (P8.1)
- Web UI code
- Existing connect start/stop behavior (only additive optional params)
- Operating mode detection logic (dev-serve uses existing SERVER mode)
- ScribeProxyClient or MCPClientPool logic (already handles SSE as priority 1)

---

### Task Package P8.3: Test Suite & Documentation

**Scope:** Comprehensive test suite for `council connect serve` command, config validation, hub registration with services, and heartbeat with service health. Plus a `.council/DEVELOPMENT.md` scaffold.

**Files to Create:**
- `tests/test_connect_serve.py` — main test suite for serve command
- `tests/test_connect_serve_config.py` — config key validation tests

**Files to Modify:**
- (none — pure additive test + doc creation)

**Dependencies:** P8.1 and P8.2 (tests exercise both command and config)

**Specifications:**

1. `tests/test_connect_serve.py` test classes:

   ```python
   class TestServeCommand:
       """Test the serve CLI command structure."""
       def test_serve_help_shows_all_options(self)
       def test_serve_without_database_url_exits_1(self)
       def test_serve_stop_without_serve_pid_exits_gracefully(self)

   class TestServePidFile:
       """Test serve.pid read/write/cleanup."""
       def test_write_serve_pid_creates_json(self)
       def test_read_serve_pid_returns_dict(self)
       def test_read_serve_pid_returns_none_on_missing(self)
       def test_read_serve_pid_returns_none_on_corrupt(self)

   class TestServeEnvironmentSetup:
       """Test environment variable resolution for dev-serve."""
       def test_scribe_sse_endpoint_auto_derived_from_hub_ip(self)
       def test_scribe_sse_endpoint_uses_config_when_set(self)
       def test_scribe_sse_endpoint_uses_env_override(self)
       def test_api_key_loaded_from_secrets_file(self)
       def test_api_key_uses_env_when_set(self)

   class TestServeRayIntegration:
       """Test Ray cluster join within serve."""
       def test_serve_joins_ray_cluster(self)
       def test_serve_no_ray_skips_cluster_join(self)
       def test_serve_ray_failure_continues_with_warning(self)

   class TestServeDaemonSpawn:
       """Test daemon and web UI process spawn."""
       def test_daemon_spawned_with_correct_command(self)
       def test_web_spawned_with_correct_env(self)
       def test_reload_flag_sets_env_var(self)
       def test_custom_ports_passed_through(self)

   class TestServeStop:
       """Test serve --stop cleanup."""
       def test_stop_kills_daemon_and_web(self)
       def test_stop_deregisters_from_hub_when_ray_joined(self)
       def test_stop_removes_serve_pid(self)
       def test_stop_handles_already_dead_processes(self)
       def test_sigint_triggers_clean_shutdown(self)
   ```

2. `tests/test_connect_serve_config.py` test classes:

   ```python
   class TestDevServeConfigKeys:
       """Verify dev_serve config keys are dual-registered."""
       def test_dev_serve_in_default_config(self)
       def test_dev_serve_in_council_yaml(self)
       def test_default_config_matches_yaml(self)
       def test_all_schema_entries_exist(self)
       def test_schema_defaults_match_default_config(self)

   class TestRegisterWithHubServices:
       """Test _register_with_hub with services parameter."""
       def test_empty_services_by_default(self)
       def test_custom_services_in_payload(self)
       def test_dev_web_service_in_payload(self)

   class TestHeartbeatServiceHealth:
       """Test _send_heartbeat with services_healthy parameter."""
       def test_no_services_healthy_by_default(self)
       def test_services_healthy_in_payload(self)
   ```

3. All tests use `test_agent` fixture from conftest.py where persona is needed.
4. All tests mock subprocess.Popen, urllib.request.urlopen, and ray module as needed.
5. No real network calls, no real process spawns, no real database connections.

**Verification:**
- [ ] `pytest tests/test_connect_serve.py -v` passes (all ~20 tests)
- [ ] `pytest tests/test_connect_serve_config.py -v` passes (all ~10 tests)
- [ ] Existing tests unbroken: `pytest tests/test_connect_supervision.py tests/test_connect_registration.py tests/test_node_registry.py -v` passes
- [ ] No test creates unique persona profiles (uses test_agent fixture)

**Out of Scope (DO NOT TOUCH):**
- Production code (all production changes are in P8.1 and P8.2)
- Existing test files
- Web UI tests

<!-- ID: milestone_tracking -->
| Milestone | Target | Owner | Status | Evidence/Link |
|-----------|--------|-------|--------|---------------|
| P0.0 — Connection Supervision | Phase 0 | Forge | Complete | 19/19 tests pass. RayWorkerSupervisor in connect_cmd.py |
| P0.1 — Node Schema & Storage | Phase 0 | Forge | Complete | 22/22 tests pass. SQL at 070_platform_nodes.sql, NodeRegistry in platform/nodes.py, config dual-registered |
| P0.2 — Node Registry API | Phase 0 | Forge | Complete | 17/17 tests pass (test_node_api.py). REST endpoints: GET /api/platform/nodes, POST register, POST heartbeat, DELETE. Council context filtering, auth required. |
| P0.3 — CLI Join & Heartbeat | Phase 0 | Forge | Complete | 34/34 tests pass (test_connect_registration.py). Enhanced council connect start/stop with node registration, --role flag, background heartbeat via supervisor, auto-capability detection. |
| P1.1 — TEI Client Integration | Phase 1 | Forge | Complete | 24/24 tests pass (test_compute_tei_integration.py, 0.39s). TEI embed path in embeddings.py, batch support, config keys dual-registered, graceful fallback. |
| P1.2 — TEI Docker Deployment | Phase 1 | Forge | Deferred | Operational/manual task, not a code package. TEI container deployment is an ops concern. |
| P2.1 — Dynamic Task Registration | Phase 2 | Forge | Complete | 22/22 tests pass (test_task_registration.py). register_task() API, task discovery from plugins, resource requirements metadata. |
| P2.2 — Service Dispatch & CONFIG_SCHEMA | Phase 2 | Forge | Complete | 24/24 tests pass (test_dispatcher_service.py). Service dispatch in ComputeDispatcher, 10 CONFIG_SCHEMA entries for all compute keys. |
| P3.0 — Registry SELECT Fix (BLOCKER) | Phase 3 | Forge | Complete | 12/12 new tests + 19/19 existing + 71/71 federation tests pass |
| P3.1 — Remote Registration & API Endpoint | Phase 3 | Forge | Complete | 27/27 new tests + 49 existing + 71 federation tests pass |
| P3.2 — Shared Secret & Memory Federation | Phase 3 | Forge | Complete | 24/24 new tests + 98 existing federation + 30 registry tests pass |
| P4.1 — Syncthing Service & Role-Based Config | Phase 4 | Forge | Complete | 24/24 tests pass (0.40s), docker compose validates, config dual-registered |
| P4.2 — Automatic Syncthing Folder Management | Phase 4 | Forge | Complete | 33/33 new tests + 24 sync policy + 22 node registry tests pass |
| P4.3 — Sync-Aware Template Loader | Phase 4 | Forge | Complete | 20/20 new tests + 40 existing template loader tests pass |
| P5.1 — RemoteAgentActor | Phase 5 | Forge | Complete | 31/31 tests pass (0.49s). RemoteAgentActor Ray Actor with Queue streaming, fault tolerance. |
| P5.2 — WorkerPool Remote Dispatch | Phase 5 | Forge | Complete | 40/40 tests pass (test_worker_pool_dispatch.py). Hardened: NodeAffinitySchedulingStrategy replaces fake resource pinning, _validate_repo_on_node() prevents dispatch to nodes without repo. 60/60 existing tests pass (0 regressions). |
| P5.3 — Remote Session Lifecycle & Streaming | Phase 5 | Forge | Complete | 42/42 tests pass (test_session_manager_remote.py). Hardened: crash/restart UX contract with StreamBridge failure callbacks, SessionManager mark_degraded/handle_remote_failure. Config: agent_dispatch.enabled + repo_node_map. 202 total tests across 4 files, 0 regressions. |
| P6.1 — Dashboard Page & Real-Time Updates | Phase 6 | Forge | Complete | 21/21 tests pass (test_platform_pages.py, 2.05s). 8 files created: platform.py route module, platform.html + nodes.html templates, platform.js + nodes.js, platform.css + nodes.css, test_platform_pages.py. 3 files modified: routes/__init__.py, _nav_desktop.html, _nav_mobile.html. 31 regression tests pass (14 page + 17 node API). |
| P6.2 — Enhanced Platform Health API | Phase 6 | Forge | Complete | 31/31 tests pass (test_platform_health.py, 0.30s). 1 file created: platform_health.py route module with GET /api/platform/health + /history. 3 files modified: routes/__init__.py (router registration), config/__init__.py (DEFAULT_CONFIG + CONFIG_SCHEMA for stale_threshold_seconds/sync_lag_threshold_seconds), council.yaml (template defaults). Config-driven thresholds, auth required, council isolation, in-memory ring buffer history. 38 regression tests pass (17 node API + 21 platform pages). |
| P7.1 — TEIContainerManager Class | Phase 7 | Forge | Complete | 40/40 tests pass (0.40s). tei_container.py created, 9 config keys added. |
| P7.2 — Connect Command Integration | Phase 7 | Forge | Complete | 28/28 tests pass, 53 existing tests zero regressions. connect_cmd.py: +_should_start_tei, +_get_tailscale_ip, services param, tei_manager in supervisor, TEI health in loop, TEI in start/stop/signal. |
| P7.3 — Service Registration & Dynamic TEI URL | Phase 7 | Forge | Not Started | |
| P8.1 — council connect serve Command | Phase 8 | Forge | Not Started | |
| P8.2 — Dev-Serve Config & Hub Registration | Phase 8 | Forge | Not Started | |
| P8.3 — Test Suite & Documentation | Phase 8 | Forge | Not Started | |

**Total: 9 phases, 25 task packages** (reduced from original 8 after LLM removal, Phase 7 re-added for TEI container lifecycle, Phase 8 added for local dev serving)

**NOTE:** Phase 4 (Local LLM Serving) was removed during pre-implementation review remediation. LLM serving is out of scope — the operator runs their own LLM infrastructure via llamacpp or similar. All subsequent phases were renumbered.
<!-- ID: retro_notes -->
### Architecture Phase (2026-02-18)
- **Research quality**: 5 Lens research docs provided excellent coverage. Key gap: federation research was thinner than others (331 lines vs 700+ for Ray/agents). Compensated by cross-referencing existing codebase knowledge.
- **Research-to-architecture gap**: Research correctly identified several issues (registry SELECT gaps, federation no-op handler, connect_cmd fire-and-forget) but architecture v1 missed some of them. Lesson: systematically cross-reference every research finding against architecture sections.
- **Phasing strategy**: Starting with node registry (Phase 0) before features was the right call — nearly every subsequent phase depends on knowing what nodes exist and what they can do.
- **Task package sizing**: ~22 packages across 8 phases. Average 2-3 packages per phase. Largest phase (Phase 5: Distributed Agents) has 3 packages, all well-bounded.

### Pre-Implementation Review Remediation (2026-02-18)
- **Arbiter score**: 68/100 (FAIL, threshold 93%). 7 mandatory remediations identified.
- **Root causes of failure**:
  1. LLM Serving (Phase 4) was out of scope — should never have been included. Operator runs own LLM.
  2. Architecture built features on broken foundations (`council connect start` fire-and-forget).
  3. Several research findings were acknowledged but not reflected in architecture (SELECT gaps, federation handler alignment).
  4. Syncthing design was flat/naive — no role awareness, no per-node policies.
  5. Command naming inconsistency across documents.
- **All 7 remediations applied**:
  - R1: Stripped Phase 4 (LLM) entirely, purged all Ollama/vLLM/llm_generate references from all sections.
  - R2: Added P0.0 — RayWorkerSupervisor with `ray.is_initialized()` health check, exponential backoff reconnection, heartbeat integration.
  - R3: Rewrote Syncthing section with role-based per-node sync policies, automatic Syncthing folder management via REST API, reverse sync.
  - R4: Added P3.0 BLOCKER — fix `api_endpoint` in all SELECT queries in registry.py.
  - R5: Aligned memory handler spec with existing `_copy_memory_to_council()` pattern (dedup via text hash, source tracking metadata).
  - R6: Canonical name is `council connect start` everywhere. Removed all `council connect join` and `council join` references.
  - R7: Clarified `platform_nodes` is GLOBAL (not council-scoped). Added `councils_served TEXT[]` for dashboard context filtering. Explicit exception to council-isolation rule.
- **Lesson learned**: Always verify architecture claims against actual source code. The Arbiter caught gaps that could have been found by reading 4 files (connect_cmd.py, registry.py, tools/federation.py, routes/federation.py).
