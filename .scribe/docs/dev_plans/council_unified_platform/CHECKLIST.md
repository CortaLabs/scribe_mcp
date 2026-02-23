---
id: council_unified_platform-checklist
title: "\u2705 Acceptance Checklist \u2014 council_unified_platform"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 03:24:41 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — council_unified_platform
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-18 01:53:25 UTC

> Acceptance checklist for council_unified_platform.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md — all sections remediated per Arbiter review)
- [x] Phase plan current (proof: PHASE_PLAN.md — 7 phases, 19 task packages, LLM phase removed)
- [x] Checklist items mapped to phases (proof: this document)
- [x] Pre-implementation review remediation applied (proof: 7/7 remediations addressed)
<!-- ID: phase_0 -->
### P0.0 — Connection Supervision (CRITICAL — Must Be First)
- [x] `RayWorkerSupervisor` class implemented — `src/council_mcp/cli/connect_cmd.py` exports class with `run()`, `stop()`, `_check_ray_health()`, `_reconnect()`, `ray_connected` property. Evidence: `pytest tests/test_connect_supervision.py -v` — 19/19 pass.
- [x] Health check uses `ray.is_initialized()` — NOT PID-based detection. Supervisor polls every `supervision_check_interval_seconds` (default 15s). Evidence: TestCheckRayHealth (4 tests) + TestSupervisionLoop::test_loop_detects_disconnection.
- [x] Reconnection with exponential backoff — On failure: `ray stop && ray start` with backoff (1s, 2s, 4s, max configurable). Evidence: TestReconnection (4 tests) — backoff pattern, reset on success, capped at max, stop exits loop.
- [x] Heartbeat includes Ray connectivity — `supervisor.ray_connected` property returns `ray.is_initialized()` status for heartbeat payloads. Evidence: TestRayConnectedProperty (2 tests). Hub heartbeat endpoint is P0.3 scope.
- [x] Foreground mode blocks on supervision — `--foreground` blocks on `supervisor.run()`, not `ray monitor`. Evidence: TestForegroundIntegration::test_foreground_blocks_on_supervisor.
- [x] Graceful shutdown — SIGTERM/SIGINT handler calls `supervisor.stop()` then `ray stop`. Evidence: signal handlers registered in start(), supervisor.stop() tested in TestSupervisionLoop::test_stop_exits_loop.

### P0.1 — Node Schema & Storage Layer
- [x] `council.platform_nodes` table created — SQL file at `db/schema/council/tables/070_platform_nodes.sql` with columns: id, hostname, tailscale_ip, node_type, capabilities, services, repos, councils_served, status, last_heartbeat, resources, metadata, created_at, updated_at. Indexes on status, hostname, councils_served (GIN). Update trigger included. Evidence: SQL file exists, schema matches Architecture Guide spec.
- [x] `platform_nodes` is GLOBAL — Table has NO `council_id` column. One row per physical machine. `councils_served TEXT[]` array links machines to councils. Evidence: SQL file contains no council_id, has `councils_served TEXT[] DEFAULT '{}'`.
- [x] NodeRegistry class implemented — `src/council_mcp/platform/nodes.py` exports `NodeRegistry` with 8 methods: `upsert_node()`, `get_nodes()`, `get_nodes_for_council()`, `get_node()`, `update_heartbeat()`, `mark_stale_nodes()`, `get_service_endpoint()`, `remove_node()`. Evidence: `pytest tests/test_node_registry.py -v` — 22/22 pass.
- [x] Config defaults registered — `council.node` section in both `DEFAULT_CONFIG` (config/__init__.py) and `templates/defaults/council.yaml` with `heartbeat_interval_seconds=30`, `stale_timeout_seconds=90`, `auto_detect_capabilities=True`, `default_role=dev-workstation`. Evidence: TestConfigKeys (3 tests) verify dual registration and value consistency.

### P0.2 — Node Registry API & Web Integration
- [x] REST API endpoints created — `GET /api/platform/nodes`, `POST /api/platform/nodes/register`, `POST /api/platform/nodes/{hostname}/heartbeat`, `DELETE /api/platform/nodes/{hostname}`. All 4 endpoints in `src/council_mcp/web/routes/system.py`. `/api/system/health` enhanced with `nodes` array. Evidence: `pytest tests/test_node_api.py -v` — 17/17 pass.
- [x] Council context filtering (NOT isolation) — GET /api/platform/nodes uses `_get_active_council_id(request)`. When council context exists, calls `NodeRegistry.get_nodes_for_council(council_id)`. When no context, calls `NodeRegistry.get_nodes()`. `platform_nodes` is globally scoped. Evidence: TestListNodes::test_list_nodes_with_council_filters and test_list_all_nodes_no_council pass.
- [x] Auth required — All 4 endpoints use `Depends(get_current_user)`. Evidence: TestAuthRequired (4 tests) confirm 401/403 without token.

### P0.3 — CLI Join & Heartbeat
- [x] `council connect start` enhanced — Existing command enhanced to register local machine as a node, sends capabilities (CPU count, GPU info, memory, repos) and role. POST to `/api/platform/nodes/register` with auto-detected capabilities. Evidence: `pytest tests/test_connect_registration.py -v` — 34/34 pass. TestRegisterWithHub (3 tests) verify payload shape and auth header.
- [x] `--role` flag — `council connect start --role gpu-compute` sets node role for sync policies and dispatch decisions. Default from `council.node.default_role` config. Evidence: TestRoleFlag verifies config default. Role resolved in start() and passed to `_register_with_hub()`.
- [x] Background heartbeat via supervisor — RayWorkerSupervisor handles heartbeat. POSTs to hub every `heartbeat_interval_seconds` with `{ray_connected: bool}`. Independent timer from health check. Evidence: TestSupervisorHeartbeat (3 tests) — heartbeat sent at interval, failure doesn't crash loop, no heartbeat without API key.
- [x] `council connect stop` enhanced — Deregisters node from hub before stopping Ray via DELETE `/api/platform/nodes/{hostname}`. Best-effort: failure is non-fatal. Evidence: TestDeregisterFromHub (3 tests) verify DELETE call, failure handling, 404 handling.
- [x] Auto-capability detection — Detects GPU via `torch.cuda.is_available()`, CPU count via `os.cpu_count()`, memory via `psutil.virtual_memory()`, GPU VRAM via `torch.cuda.get_device_properties()`. Evidence: TestDetectCapabilities (7 tests) verify shape, types, fallbacks without torch/psutil.
<!-- ID: final_verification -->
### Pre-Final Checks
- [ ] All checklist items above checked with proofs attached.
- [ ] Stakeholder sign-off recorded (name + date).
- [ ] Retro completed and lessons learned documented.

---

## Phase 1: GPU Embedding Serving (TEI)

### P1.1 — TEI Client Integration
- [x] TEI embed path in embeddings.py — `embed_text_async()` checks `tei_url` config first, falls back to existing Ray/local paths. `_embed_via_tei()` POSTs to `{url}/embed` with `{"inputs": text}`, returns `list[float]` or `None` on failure. Evidence: `pytest tests/test_compute_tei_integration.py -v` — 24/24 pass (0.39s). TestEmbedTextAsyncRouting (5 tests) verify routing priority (TEI > Ray > local).
- [x] Batch embedding support — `embed_texts_async()` uses `_batch_embed_via_tei()` which sends batch to TEI `/embed` endpoint with `{"inputs": [text1, text2, ...]}`. Validates response count matches input count. Evidence: TestEmbedTextsAsyncRouting::test_batch_ten_texts — 10 texts return 10 embeddings of 384 dimensions. TestBatchEmbedViaTei (4 tests) cover success, timeout, mismatch, HTTP error.
- [x] Config keys registered — `council.compute.tei_url` (default `""`) and `council.compute.tei_timeout_seconds` (default `5`) in both DEFAULT_CONFIG (`config/__init__.py` compute section) and `templates/defaults/council.yaml`. Evidence: TestConfigKeys (4 tests) verify dual registration and value consistency.
- [x] Graceful fallback — When TEI is unreachable (timeout, connection error, 500, unexpected format), `_embed_via_tei()` returns `None` and caller falls back to local embedding without error. Evidence: TestEmbedViaTei (5 tests) — timeout, 500, connection error, unexpected format all return None. TestEmbedTextAsyncRouting::test_tei_failure_falls_through_to_local confirms end-to-end fallback.

### P1.2 — TEI Docker Deployment
- [ ] TEI service in docker-compose.yaml — Service definition with `ghcr.io/huggingface/text-embeddings-inference`, GPU passthrough on worker nodes, CPU mode on hub. Evidence: `docker compose config` validates.
- [ ] Health check endpoint — TEI `/health` monitored by health-check.sh. Evidence: health-check.sh reports TEI status.
- [ ] deploy.sh updated — TEI service included in deploy workflow with optional skip if no GPU. Evidence: deploy on hub skips TEI gracefully.

---

## Phase 2: Compute Dispatch Enhancement

### P2.1 — Dynamic Task Registration
- [x] `register_task()` API — `src/council_mcp/compute/tasks.py` exports `register_task(name, local_fn, *, num_gpus, num_cpus)` that downstream repos can call. Evidence: `pytest tests/test_task_registration.py -v` passes (22/22). register_task() adds to TASK_REGISTRY, stores resource specs in _pending_registrations.
- [x] Task discovery from plugins — Tasks registered via explicit `register_task()` calls are available to ComputeDispatcher via `register()` convenience method. Evidence: test registers a task, dispatches it in both local and Ray modes, gets correct result.
- [x] Resource requirements metadata — Each task declares `num_gpus`, `num_cpus` requirements. get_remote_tasks() wraps pending registrations with ray.remote(num_gpus=..., num_cpus=...). Evidence: test_ray_remote_called_with_resource_args verifies correct resource args passed.

### P2.2 — Service Dispatch & CONFIG_SCHEMA
- [x] Service dispatch in ComputeDispatcher — `_resolve_service(task_name)` checks node registry for nodes offering matching service, returns URL. `_dispatch_service()` POSTs to `{url}/dispatch`. `dispatch()` tries service first, falls through to Ray/local on failure. Evidence: `pytest tests/test_dispatcher_service.py -v` passes (24/24). test_returns_url_when_node_found, test_dispatch_routes_to_service_when_configured, test_dispatch_falls_through_on_service_failure all pass.
- [x] CONFIG_SCHEMA entries for all compute keys — 10 entries in CONFIG_SCHEMA covering ray_enabled, ray_address, gpu_fallback_to_cpu, dispatch_timeout_seconds, supervision_check_interval_seconds, supervision_reconnect_max_backoff_seconds, tei_url, tei_timeout_seconds, service_routes, service_timeout_seconds. Web UI config editor at `/api/system/config-schema` already serves these. Evidence: test_all_compute_keys_in_schema, test_schema_defaults_match_default_config pass.
- [x] Config validation on save — `write_council_config()` validates against CONFIG_SCHEMA before writing (existing mechanism). New compute keys now included. Evidence: test_schema_entries_have_required_fields verifies type/section/tier/description/default for all entries.

---

## Phase 3: Federation Activation

### P3.0 — Registry SELECT Fix (BLOCKER)
- [x] `api_endpoint` in all SELECT queries — `list_councils_sync()`, `get_council_by_name_sync()`, `get_council_by_id_sync()` all include `api_endpoint` in their SELECT column lists. Evidence: `pytest tests/test_registry_api_endpoint.py -v` — 12/12 pass (0.36s). SQL verified to contain `api_endpoint` in all 3 queries.
- [x] `register_council_sync()` accepts `api_endpoint` — Function signature updated: `register_council_sync(..., api_endpoint: str | None = None, is_remote: bool = False)`. INSERT includes `api_endpoint` column, ON CONFLICT uses COALESCE to preserve existing value. Async wrapper updated. Evidence: TestRegisterCouncilApiEndpoint (4 tests) — passes endpoint to INSERT, defaults to None, COALESCE in upsert, SQL includes column.
- [x] No regression — Existing federation and registry tests still pass. Evidence: `pytest tests/test_council_registry.py -v` — 19/19 pass. `pytest tests/test_federation.py tests/test_federation_e2e.py -v` — 71/71 pass.

### P3.1 — Remote Registration & API Endpoint
- [x] Remote council registration — `POST /api/councils/register` with `remote=true` skips path validation, passes `api_endpoint` and `is_remote` to `register_council_sync()`. `PATCH /api/councils/{id}` updates `api_endpoint`/`metadata`/`status`. `GET /api/councils/{id}` returns full detail. New `update_council_sync()` in registry.py with field filtering and jsonb metadata merge. Evidence: `pytest tests/test_federation_fixes.py -v` — 27/27 pass (1.43s). 49 existing council tests pass, 71 federation tests pass, zero regressions.
- [x] `council federation setup` CLI — Created `federation_cmd.py` with `council federation setup` command: --shared-secret, --api-endpoint, --non-interactive flags. Reads/writes .council/council.yaml. Registered in main.py. Evidence: `pytest tests/test_federation_memory.py::TestFederationSetupCLI -v` — 4/4 pass, `pytest tests/test_federation_memory.py::TestFederationCLIRegistration -v` — 2/2 pass.

### P3.2 — Shared Secret & Memory Federation
- [x] Shared secret generation — `_build_council_yaml()` in init_cmd.py generates `secrets.token_hex(32)` (64-char hex) for `daemon_federation.shared_secret` during `council init`. Evidence: `pytest tests/test_federation_memory.py::TestInitSharedSecret -v` — 2/2 pass (unique per call, 64 chars).
- [x] HMAC request signing — Already implemented in routes/federation.py `_validate_federation_envelope()` (lines 185-236): validates envelope_id, payload_digest, timestamp_utc, signature via HMAC-SHA256, idempotency key. Evidence: `pytest tests/test_federation_e2e.py::TestFederationReceiveEnvelopeValidation -v` — 13/13 pass.
- [x] Memory federation handler aligned — `_process_memory_federated()` in routes/federation.py: validates text/persona_id, computes text_hash via `_compute_text_hash()`, checks duplicates via `_check_existing_federated_memory()`, stores via `models.insert_persona_memory()` with metadata containing text_hash and federated_from (source_council_id, source_memory_id), updates council_id/source_council_id. Returns stored/duplicate/error. Evidence: `pytest tests/test_federation_memory.py::TestProcessMemoryFederated -v` — 12/12 pass, `pytest tests/test_federation_memory.py::TestFederationReceiveMemory -v` — 4/4 pass.
- [x] Federated memory appears in queries — Stored with `federated` tag (auto-added if not present), `visibility=shared`, `federated_from` metadata with source tracking, `text_hash` for deduplication. Evidence: `pytest tests/test_federation_memory.py::TestProcessMemoryFederated::test_federated_tag_always_present -v` pass, `test_default_values` confirms visibility=shared, `test_text_hash_in_metadata` and `test_federated_from_metadata` confirm metadata.

---

## Phase 4: Intelligent File Sync (Syncthing)

### P4.1 — Syncthing Service & Role-Based Sync Config
- [x] Syncthing service in docker-compose.yaml — Bound to `${TAILSCALE_IP}:8384` (GUI) and `:22000` (sync). Evidence: `docker compose config` validates (exit 0, no errors).
- [x] `SyncPolicyResolver` class — `src/council_mcp/platform/sync_policies.py` resolves sync paths per node role (hub, gpu-compute, dev-workstation, ci-runner). Evidence: `pytest tests/test_sync_policies.py -v` — 24/24 pass (0.40s).
- [x] Role-based config keys — `council.sync.role_policies` with per-role `sync_paths` and `direction` in both DEFAULT_CONFIG and council.yaml. Evidence: TestConfigConsistency.test_council_yaml_matches_default_config passes.
- [x] CONFIG_SCHEMA entries — All sync config keys appear in web UI config editor. Evidence: TestConfigConsistency.test_config_schema_entries_exist passes (5 entries: enabled, syncthing_url, syncthing_api_key, default_sync_paths, role_policies).

### P4.2 — Automatic Syncthing Folder Management
- [x] `SyncthingClient` class — `src/council_mcp/platform/syncthing_client.py` wraps Syncthing REST API (get_config, add_folder, remove_folder, add_device, get_status, get_connections, health). Uses httpx.AsyncClient with X-API-Key header. Reads syncthing_url and syncthing_api_key from council.sync config. Evidence: `pytest tests/test_syncthing_client.py -v` — 33/33 pass (0.45s). TestGetConfig (3 tests), TestAddFolder (3), TestRemoveFolder (2), TestAddDevice (1), TestGetStatus (1), TestGetCon...
- [x] Sync hook on node registration — `NodeRegistry.upsert_node()` calls `_trigger_sync_setup_safe()` after DB commit. When `sync.enabled=True`, resolves policy via SyncPolicyResolver, calls SyncthingClient.add_folder for each path. Best-effort: errors logged as warnings, never crash registration. Evidence: TestTriggerSyncSetup (6 tests) — creates folders per path, uses default role when None, empty paths no-op, per-folder failure non-fatal, direction passed as folder_type. TestUpsertNodeSyn...
- [x] Sync status in node API — `GET /api/platform/nodes` includes per-node `sync_status` field via `_get_syncthing_health()` helper in system.py. Returns "healthy"/"unreachable"/"disabled"/"unknown" based on SyncthingClient.health() probe and sync enabled config. Evidence: 17/17 node API tests pass, inline verification confirms `sync_status` present in response.
- [x] Bidirectional sync — SyncthingClient.add_folder accepts folder_type parameter. _trigger_sync_setup passes direction from SyncPolicyResolver (sendreceive for hub/dev-workstation, receiveonly for gpu-compute, etc.) as folder_type. Evidence: TestTriggerSyncSetup::test_passes_direction_as_folder_type verifies receiveonly passed for gpu-compute role. TestAddFolder::test_posts_correct_payload verifies payload includes type field.

### P4.3 — Sync-Aware Template Loader
- [x] Multi-path discovery — `ProjectTemplateLoader.discover_pages()` checks synced paths in addition to local `.council/web/pages/`. Evidence: `pytest tests/test_template_loader_sync.py -v` — 20/20 pass (0.40s).
- [x] Page limit enforced — 20-page limit applies across ALL paths (local + synced) combined. Evidence: TestPageLimitAcrossPaths (15+15=30 input, 20 returned; 12+12=24 input, 20 returned).
- [x] Existing tests unbroken — Template loader regression tests pass. Evidence: `pytest tests/test_web_templates.py -v` — 40/40 pass (0.47s, zero regressions).

---

## Phase 5: Distributed Agent Execution

### P5.1 — RemoteAgentActor
- [x] RemoteAgentActor class — `src/council_mcp/compute/remote_agent.py` implements Ray Actor wrapping SDKProvider lifecycle. Evidence: `pytest tests/test_remote_agent_actor.py -v` — 31 passed in 0.49s.
- [x] Token streaming via Ray Queue — Actor pushes `{"type": "token", "text": "..."}` dicts to queue, hub reads asynchronously. Evidence: test_send_message_streams_tokens_in_order, test_send_message_done_signal_after_tokens, test_non_text_events_are_skipped all pass.
- [x] Fault tolerance — Actor restarts on crash (max_restarts=3), session marked failed on exhaustion. Evidence: test_simulated_restart_sets_restarted_status, test_restarted_actor_has_no_session, test_failed_status_rejects_messages, test_failed_status_reported_correctly all pass.

### P5.2 — WorkerPool Remote Dispatch
- [x] `_resolve_dispatch_target()` — Resolution order: explicit metadata, repo_node_map, capability match, fallback to local. Evidence: `pytest tests/test_worker_pool_dispatch.py -v` — 40 passed. TestResolveDispatchTarget (13 tests) cover all 4 resolution steps plus edge cases.
- [x] Remote worker spawn — `WorkerPool.create_session()` creates RemoteAgentActor on target Ray node via `_spawn_remote_worker()` using `NodeAffinitySchedulingStrategy(ray_node_id, soft=False)` for real node pinning. Evidence: TestSpawnRemoteWorker (5 tests) verify actor creation with NodeAffinitySchedulingStrategy, fallback when no ray_node_id. TestCreateSessionRemoteDispatch (4 tests) verify end-to-end remote session creation.
- [x] Local path unchanged — Existing UDS-based local worker path completely unmodified. Evidence: `pytest tests/test_worker_pool.py -v` — 60/60 pass (5.89s, zero regressions).
- [x] Graceful fallback — Unavailable remote node falls back to local execution with warning log. Evidence: test_remote_failure_falls_back_to_local confirms ProcessManager.spawn called after remote failure, test_remote_failure_cleans_up_partial_state confirms no leaked state.
- [x] NodeAffinitySchedulingStrategy — Replaced fake `resources={"node:<hostname>": 1}` with real Ray `NodeAffinitySchedulingStrategy(ray_node_id, soft=False)`. Uses `ray_node_id` from `platform_nodes` table (set via `ray.get_runtime_context().get_node_id()` at heartbeat). Evidence: test_creates_actor_with_node_affinity_strategy asserts `scheduling_strategy=mock_strategy_instance`, test_returns_none_when_no_ray_node_id verifies graceful fallback when node lacks ray_node_id.
- [x] Repo validation before dispatch — `_validate_repo_on_node()` checks NodeRegistry for target node repos, with fallback to `repo_node_map` config. Prevents dispatching to nodes without the required repo. Evidence: TestValidateRepoOnNode (7 tests) cover repo present, prefix match, repo-node-map secondary match, node not found fallback, registry exceptions. TestResolveDispatchTargetWithRepoValidation (2 tests) verify end-to-end integration.

### P5.3 — Remote Session Lifecycle & Streaming
- [x] SessionManager integration — SessionManager calls WorkerPool (unchanged interface), transparent local/remote handling. Evidence: test_send_message_uses_remote_path_for_remote_worker + test_send_message_uses_local_path_for_local_worker + test_create_session_delegates_to_worker_pool pass. _ensure_active_worker returns worker, reused for remote check without extra get_worker call. 86 existing session_manager tests pass (0 regressions).
- [x] StreamBridge token relay — Tokens from Ray Queue relayed through StreamBridge to WebSocket clients. Evidence: 8 relay tests pass (text tokens, error token, done signal, queue timeout, empty text skip, non-dict skip, sequence numbers, task cleanup). start_relay/cancel_relay/clear_session_cancels_relay all pass. 45 existing stream_bridge tests pass (0 regressions).
- [x] Session cleanup — Remote actor terminated on session end/timeout, resources freed. Evidence: test_end_session_calls_pool_end_session + test_end_session_cleanup_with_remote_worker_entry pass. Pool end_session handles remote cleanup, bridge.clear_session cancels relay tasks.
- [x] Feature flag — `council.compute.agent_dispatch.enabled` defaults to `false`. Evidence: test_dispatch_disabled_by_default + test_dispatch_has_repo_node_map pass.
- [x] Config keys — `agent_dispatch.enabled`, `agent_dispatch.repo_node_map` in both DEFAULT_CONFIG and council.yaml with CONFIG_SCHEMA entries. Evidence: test_schema_has_enabled_key + test_schema_has_repo_node_map_key + test_yaml_has_agent_dispatch_section pass.
- [x] Crash/restart UX contract — StreamBridge detects Ray actor exceptions by `type(exc).__name__` matching: `RayActorError`/`ActorUnavailableError` -> "restarted", `ActorDiedError`/`RayError` -> "failed". Pushes appropriate ErrorEvent to WebSocket clients. Invokes registered failure callbacks. Evidence: TestStreamBridgeFailureCallbacks (6 tests) — register/unregister callbacks, actor restarted/died invokes callback with correct failure_type, no callback is safe.
- [x] SessionManager crash handling — `_stream_remote_message()` catches Ray exceptions during initiation and streaming phases, calls `handle_remote_failure()`. `handle_remote_failure()` marks session degraded (restarted) or ERROR+cleanup (failed). `mark_degraded()` updates session metadata with `remote_state: "degraded"`. Evidence: TestStreamRemoteMessageCrashContract (4 tests), TestHandleRemoteFailure (3 tests), TestMarkDegraded (2 tests).
- [x] Failure callback wiring — StreamBridge `register_failure_callback()` / `unregister_failure_callback()` allow SessionManager to register per-session async callbacks. `clear_session()` removes callback alongside buffer/seq/relay. Evidence: TestStreamBridgeFailureCallbacks::test_clear_session_removes_failure_callback passes.

---

## Phase 6: Platform Dashboard

### P6.1 — Dashboard Page & Real-Time Updates
- [x] Platform page created at `/platform` (core page, not custom) with node grid, service health, metrics sections. Evidence: 21/21 tests pass in test_platform_pages.py — route registration, auth redirect, page rendering (metrics, service health, nodes grid), navigation integration. Files: platform.py, platform.html, nodes.html, platform.js, nodes.js, platform.css, nodes.css.
- [x] Auto-refresh polling — Dashboard refreshes node status without page reload via 10s setInterval polling (per task package spec). Evidence: platform.js loadPlatformData() calls API.get('/api/platform/nodes') + API.get('/api/system/health') in parallel via Promise.allSettled. nodes.js uses 15s polling.
- [x] Council context filtering — Dashboard shows nodes relevant to active council. Evidence: platform.js and nodes.js both listen for `councilSwitched` window event and reload data. API passes X-Council-Id header via API.getAuthHeaders().
- [x] Stale/offline indicators — Nodes with no heartbeat > threshold shown with warning/error indicators. Evidence: getStatusBadgeClass() maps status to badge--success/badge--warning/badge--error CSS classes. 31 regression tests pass (14 page + 17 node API).

### P6.2 — Enhanced Platform Health API
- [x] Unified health endpoint — `GET /api/platform/health` aggregates node health, service health, sync status, compute status. Evidence: 31/31 tests pass in test_platform_health.py (1.42s). Response includes nodes (total/online/stale/offline), services (ray/tei/syncthing with status), resources (cpus/gpus/memory), alerts array, timestamp. Plus GET /api/platform/health/history for time-series.
- [x] Alert thresholds — Config-driven thresholds for node staleness and sync lag. Evidence: TestConfigThresholds verifies custom stale_threshold_seconds=600 prevents stale classification for 200s-old heartbeat. Config keys dual-registered: DEFAULT_CONFIG (120/300), CONFIG_SCHEMA (int, tier 1), council.yaml.
- [x] Auth required — 401 without token. Evidence: TestAuthRequired (2 tests) confirms both /api/platform/health and /api/platform/health/history return 401 without auth.
- [x] Council context applied — Health filtered by active council context. Evidence: TestCouncilIsolation (2 tests) confirms get_nodes_for_council called with council_id when set, get_nodes called when no council. History endpoint also filters by council_id.

---

## Cross-Cutting Verification

- [ ] All new config keys dual-registered — Every key in DEFAULT_CONFIG also in templates/defaults/council.yaml with matching values. Evidence: `grep` comparison shows parity.
- [ ] All new endpoints auth-gated — No new `/api/*` endpoint accessible without Bearer token. Evidence: curl without auth returns 401 on all new endpoints.
- [ ] All new endpoints council-aware — New endpoints use `_get_active_council_id(request)` for council context. Platform node endpoints filter by `councils_served` (GLOBAL table exception). Other endpoints use standard council-isolation. Evidence: code review confirms pattern.
- [ ] Feature flags default OFF — `platform.enabled`, `tei_url=""`, `sync.enabled=false`, `agent_dispatch.enabled=false` all default to disabled. Evidence: fresh config has all features off.
- [ ] No LLM references remain — No Ollama, vLLM, llm_generate, llm_url, ollama_enabled in any architecture, phase plan, or checklist document. Evidence: `grep -r "ollama\|vLLM\|llm_generate\|llm_url\|llm_serving" .scribe/docs/dev_plans/council_unified_platform/` returns zero matches.
- [ ] Command naming consistent — All references use `council connect start` (no `council connect join`, no `council join`). Evidence: `grep -r "council join\|connect join" .scribe/docs/dev_plans/council_unified_platform/` returns zero matches.
- [ ] Existing tests unbroken — `pytest tests/ -x --ignore=tests/test_platform* --ignore=tests/test_tei* --ignore=tests/test_remote*` passes. Evidence: CI green.
- [ ] No hardcoded values — All thresholds, URLs, timeouts, intervals come from config with fallbacks. Evidence: code review confirms no magic numbers.

---

## Final Sign-Off

- [ ] All phase checklists complete with evidence.
- [ ] Arbiter post-implementation review >= 93%.
- [ ] Retro completed and lessons learned documented in PHASE_PLAN.md retro_notes section.
---

## Phase 7: TEI Container Lifecycle Management
<!-- ID: phase_7 -->
### P7.1 — TEIContainerManager Class
- [x] `TEIContainerManager` class implemented — `src/council_mcp/compute/tei_container.py` exports class with `start()`, `stop()`, `health_check()`, `is_running()`, `get_url()`, `get_container_logs()`, `check_docker_available()`, `check_gpu_available()`. Evidence: `pytest tests/test_tei_container.py -v` — 40/40 passed (0.40s).
- [x] Docker CLI subprocess pattern — All Docker operations use `subprocess.run()` (no Docker Python SDK). start() builds `docker run -d --name council-tei ...` command, stop() runs `docker stop` + `docker rm`. Evidence: TestStart and TestStop classes verify subprocess.run called with correct args.
- [x] Health check via HTTP — `health_check()` uses httpx to GET `{url}/health`. Returns True on 200, False on any error. Evidence: TestHealthCheck verifies True/False for 200/timeout/connection error (4 tests).
- [x] GPU passthrough — `start(gpu=True)` includes `--gpus all` flag. `start(gpu=False)` omits it. Evidence: test_start_calls_docker_run_with_correct_flags and test_start_without_gpu_omits_gpus_flag verify flag presence/absence.
- [x] Stale container cleanup — `start()` always runs `docker stop` + `docker rm` before `docker run` (errors ignored). Evidence: test_start_runs_cleanup_before_docker_run verifies cleanup subprocess calls precede docker run.
- [x] Startup timeout — `start()` polls health endpoint every 2s, up to `startup_timeout_seconds`. Returns False if timeout exceeded. Evidence: test_start_returns_false_on_timeout with mock time verifies timeout behavior.
- [x] Config keys dual-registered — 8 `tei_container.*` keys + 1 `services_by_role` key in DEFAULT_CONFIG, CONFIG_SCHEMA, and `templates/defaults/council.yaml` with matching values. Evidence: TestConfigKeys class (7 tests) validates all 3 locations.

### P7.2 — Connect Command Integration
- [x] TEI starts on `council connect start --role gpu-compute` — When `tei_container.enabled=True` and role policy has `tei: true`, TEIContainerManager.start() is called after Ray connectivity confirmed. Evidence: `pytest tests/test_connect_tei_integration.py -v` — 28/28 pass (TestShouldStartTei, TestSupervisorTeiInit).
- [x] TEI skipped for non-gpu roles — `--role dev-workstation` or `--role ci-runner` does not attempt TEI start. Evidence: TestShouldStartTei::test_returns_false_for_dev_workstation, test_returns_false_for_ci_runner pass.
- [x] Docker not available degrades gracefully — If `check_docker_available()` returns False, logs warning and continues without TEI. Evidence: TestDockerGpuDegradation::test_docker_not_available_logs_warning_and_continues passes.
- [x] GPU not available falls back — If `check_gpu_available()` returns False, starts TEI without `--gpus all`. Evidence: TestDockerGpuDegradation::test_gpu_not_available_starts_without_gpu_flag passes — verifies start(gpu=False).
- [x] Service registration populated — `_register_with_hub()` includes `services=[{"name": "tei", "port": 8080}]` when TEI running, `services=[]` otherwise. Evidence: TestRegisterWithHubServices — 3 tests verify payload shape.
- [x] Supervisor monitors TEI health — `RayWorkerSupervisor` checks TEI health on heartbeat cycle. Unhealthy TEI triggers stop + restart. Evidence: TestSupervisorTeiHealthCheck — test_tei_health_checked_on_heartbeat, test_tei_restarted_when_unhealthy pass.
- [x] `council connect stop` stops TEI — TEI container stopped before Ray worker. Evidence: TestStopTeiIntegration::test_stop_stops_tei_before_ray — verifies call_order.index("tei_stop") < call_order.index("ray_stop").
- [x] SIGTERM/SIGINT stops TEI — Shutdown handler stops TEI before Ray. Evidence: _shutdown_handler and KeyboardInterrupt blocks both call tei_manager.stop() before ray stop. Code review verified.
- [x] Existing connect tests unbroken — `pytest tests/test_connect_supervision.py tests/test_connect_registration.py -v` — 53/53 pass with zero regressions.

### P7.3 — Service Registration & Dynamic TEI URL
- [ ] Heartbeat includes service health — `_send_heartbeat()` includes `services_healthy: {"tei": true/false}` when TEI managed. Evidence: `pytest tests/test_tei_service_discovery.py -v` passes.
- [ ] Dynamic TEI URL resolution — `_resolve_tei_url()` in embeddings.py checks static config first, then discovers via `NodeRegistry.get_service_endpoint("tei")`. 60-second cache. Evidence: test verifies priority order and caching.
- [ ] `embed_text_async()` uses dynamic resolution — Replaces static `cfg.get("tei_url")` with `_resolve_tei_url()`. Evidence: test verifies function called.
- [ ] Existing TEI integration tests unbroken — `pytest tests/test_compute_tei_integration.py -v` passes with zero regressions.

---

## Phase 8: Local Dev Serving
<!-- ID: phase_8 -->
### P8.1 — council connect serve Command
- [ ] `council connect serve` starts daemon + web + Ray — Running `council connect serve` in a repo with `DATABASE_URL` in `.council/.env` starts the daemon (port 8016), web UI (port 8015), and joins the Ray cluster. Evidence: `pytest tests/test_connect_serve.py -v` passes.
- [ ] `council connect serve --stop` shuts down cleanly — Reads `serve.pid` JSON, sends SIGTERM to web then daemon, deregisters from hub, disconnects Ray. Evidence: test verifies process termination and PID file removal.
- [ ] `serve.pid` lifecycle — JSON file at `.council/serve.pid` written on start with `daemon_pid`, `web_pid`, `ray_joined` keys. Removed on stop. Evidence: test verifies file creation, content, and cleanup.
- [ ] `--no-ray` flag skips Ray — Running with `--no-ray` starts daemon + web only, no Ray join. `serve.pid` has `ray_joined: false`. Evidence: test verifies no Ray connection attempt.
- [ ] `--reload` enables uvicorn hot-reload — Passed through to web UI spawn. Evidence: test verifies `--reload` flag in subprocess args.
- [ ] `--daemon-port` / `--web-port` override ports — Custom ports passed through to daemon and web processes. Evidence: test verifies correct port in subprocess args and health check URL.
- [ ] Daemon health check before web spawn — serve() polls daemon health endpoint before spawning web UI (same pattern as start_cmd._spawn_web_ui). Evidence: test verifies sequential startup with health gate.
- [ ] Scribe SSE auto-configuration — `SCRIBE_SSE_ENDPOINT` env var set from `deployment.hub_tailscale_ip` config before spawning daemon. Evidence: test verifies env var in subprocess environment.
- [ ] Duplicate instance prevention — If `serve.pid` exists and processes alive, serve() exits with error message. Evidence: test verifies error and non-zero exit.
- [ ] SIGTERM/SIGINT cleanup — Signal handlers stop web, daemon, Ray in order. Evidence: test verifies cleanup on signal.
- [ ] Existing connect tests unbroken — `pytest tests/test_connect_supervision.py tests/test_connect_registration.py -v` pass with zero regressions.

### P8.2 — Dev-Serve Config & Hub Registration
- [ ] `council.dev_serve` config section — 5 keys in DEFAULT_CONFIG, CONFIG_SCHEMA, and `templates/defaults/council.yaml`: `auto_join_ray` (bool, true), `scribe_mode` (str, "hub"), `default_daemon_port` (int, 8016), `default_web_port` (int, 8015), `hub_scribe_sse_endpoint` (str, ""). Evidence: `pytest tests/test_connect_serve_config.py -v` passes.
- [ ] `.env.example.j2` updated — Template includes `DATABASE_URL`, `SCRIBE_SSE_ENDPOINT`, `COUNCIL_API_KEY` with comments. Evidence: `council update` regenerates `.council/.env.example` with new entries.
- [ ] Hub registration includes services — `_register_with_hub()` accepts optional `services` list param, includes in POST payload. Evidence: test verifies payload contains `services` array.
- [ ] Heartbeat includes `services_healthy` — `_send_heartbeat()` accepts optional `services_healthy` dict, includes in heartbeat payload. Evidence: test verifies payload contains `services_healthy`.
- [ ] serve command registers daemon+web services — Registration payload includes `[{"name": "daemon", "port": 8016}, {"name": "web", "port": 8015}]`. Evidence: test verifies service entries.

### P8.3 — Test Suite & Documentation
- [ ] `test_connect_serve.py` comprehensive — Covers: basic start, --stop, --no-ray, --reload, port overrides, duplicate prevention, signal cleanup, Scribe SSE config, health gate, serve.pid lifecycle. Minimum 15 tests. Evidence: `pytest tests/test_connect_serve.py -v` shows 15+ tests passing.
- [ ] `test_connect_serve_config.py` comprehensive — Covers: config defaults, config override, .env.example content, hub registration services, heartbeat services_healthy. Minimum 8 tests. Evidence: `pytest tests/test_connect_serve_config.py -v` shows 8+ tests passing.
- [ ] All mocks, no real processes — Tests mock subprocess.Popen, httpx, Ray init. No real daemon/web/Ray started. Evidence: no test timeout, sub-second execution.
- [ ] Existing test regression check — `pytest tests/test_connect_supervision.py tests/test_connect_registration.py tests/test_compute_tei_integration.py -v` all pass unchanged.
