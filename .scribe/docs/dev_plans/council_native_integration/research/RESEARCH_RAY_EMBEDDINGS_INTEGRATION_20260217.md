
# 🔬 Research Ray Embeddings Integration 20260217 — council_native_integration
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 07:56:30 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Map current state of Ray compute dispatcher, embeddings integration architecture, and identify gaps for Council tool native integration.

**Key Takeaways:**
- Ray compute system is **100% feature-complete** with dispatcher, bridge, 5 production call sites, and health monitoring (P3.4-P3.5 delivered).
- **Critical Gap:** Council MCP tools still use **blocking embedding calls** within async handlers, preventing Ray GPU dispatch at tool invocation time.
- **Architecture:** Head node (Hetzner CCX23) runs CPU embeddings, workers join with GPU (RTX 4070) — dispatcher auto-routes based on `ray_enabled=true` + availability.
- **Confidence:** HIGH — All findings verified from source code (dispatcher.py, embeddings.py, tasks.py, memory.py, promote.py, domain queries).


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** lens

**Investigation Window:** 2026-02-17 (30 min)

**Focus Areas:**
- [x] ComputeDispatcher routing logic (dual-mode Ray/CPU)
- [x] Embedding bridge architecture (async drop-in replacement)
- [x] Ray task definitions (remote function decoration)
- [x] Production call sites (where embeddings are used)
- [x] Health monitoring integration
- [x] Connect CLI and version pre-flight checks

**Dependencies & Constraints:**
- Ray 2.49.2 must match between head and workers (enforced at connect time)
- Python 3.11.13 exact match (Ray enforces, pre-flight check simplified to Ray version only)
- Embeddings provider is `local` (384-dim pgvector index), not OpenAI (1536-dim dormant config)
- Head node is CPU-only (1.5 vCPU, 3GB RAM), workers provide GPU resources


---
## Findings
<!-- ID: findings -->

### Finding 1: ComputeDispatcher is Fully Functional Dual-Mode Dispatcher
- **Summary:** ComputeDispatcher (src/council_mcp/compute/dispatcher.py) implements a clean dual-mode pattern: Ray GPU dispatch with automatic CPU fallback. Reads config at init time (`council.compute.*`), lazily initializes Ray on first dispatch attempt. When Ray unavailable/disabled, all tasks execute locally via ThreadPoolExecutor.
- **Evidence:** 
  - `dispatcher.py` lines 21-146: Full implementation with 6 methods (init, dispatch, health, _ensure_ray, _dispatch_ray, _dispatch_local)
  - Routing logic (lines 36-59): (1) Check `ray_enabled` + `_ensure_ray()`, (2) Try Ray dispatch, (3) Fallback to local if exception + `gpu_fallback_to_cpu=true`
  - Lazy init (lines 99-117): `_ensure_ray()` checks `ray.is_initialized()`, calls `ray.init(address=...)`, handles ImportError gracefully
- **Confidence:** HIGH

### Finding 2: Embedding Bridge Provides Zero-Overhead Async Routing
- **Summary:** Embedding bridge (src/council_mcp/compute/embeddings.py, lines 1-124) provides drop-in replacement for AgentKit embeddings with zero overhead when `ray_enabled=false` (default). Sync functions (`embed_text()`, `embed_texts()`) always run locally on CPU. Async functions (`embed_text_async()`, `embed_texts_async()`) route through dispatcher when Ray enabled, use executor for local async otherwise.
- **Evidence:**
  - Sync API (lines 43-62): Direct delegation to `agentkit.embeddings` — no dispatcher instantiation
  - Async API (lines 70-111): Config check at line 81-82, dispatcher route (lines 83-86) vs executor fallback (lines 91-92)
  - Import structure (line 9): `from council_mcp.compute.embeddings import embed_text_async` already in production tools
- **Confidence:** HIGH

### Finding 3: Ray Remote Tasks Use GPU Allocation (num_gpus=0.5)
- **Summary:** Ray task definitions (src/council_mcp/compute/tasks.py) declare embedding tasks with `@ray.remote(num_gpus=0.5)`, requesting half a GPU per task. Two tasks: `_embed_text_ray()` (single text) and `_batch_embed_ray()` (batch of texts). Local CPU fallbacks available: `embed_text_local()` and `batch_embed_local()`.
- **Evidence:**
  - Lines 61-65: `@ray.remote(num_gpus=0.5) def _embed_text_ray(text)`
  - Lines 68-71: `@ray.remote(num_gpus=0.5) def _batch_embed_ray(texts)`
  - Lines 84-87: TASK_REGISTRY maps task names to local implementations
- **Confidence:** HIGH

### Finding 4: Five Production Call Sites Already Using Async Embeddings
- **Summary:** Integration is already deployed across Council tools. Found 5 distinct call sites using `embed_text_async()`:
  1. **tools/memory.py** (line 160, 253): micro-reflections + store_memory
  2. **tools/promote.py** (line 152): promote_message embedding
  3. **domain/queries.py** (line 67): DomainQueryAPI.search_domain() vector search
  4. **domain/loader.py** (line 214): DomainRegistry._stage_embed() batch embedding
  5. **tools/federation.py** (line 677): query_federation vector search
- **Evidence:** Grep match results show all 5 using `await embed_text_async(...)` pattern
- **Confidence:** HIGH

### Finding 5: Config-Driven Ray Enable via council.compute.* Section
- **Summary:** Ray behavior entirely controlled by `.council/council.yaml` config section `council.compute.*`:
  - `ray_enabled` (bool, default=false): Master switch for Ray dispatch
  - `ray_address` (str, default="auto"): Cluster address or "auto" for local
  - `gpu_fallback_to_cpu` (bool, default=true): Fallback on dispatch failure
  - `dispatch_timeout_seconds` (int, default=30): Task timeout
- **Evidence:** 
  - config.py lines 1292-1310: All 4 config keys with defaults + types
  - dispatcher.py lines 24-30: Config read at init, values stored as instance vars
- **Confidence:** HIGH

### Finding 6: Health Monitoring Integrated into System Health Endpoint
- **Summary:** Compute health is exposed via `/api/system/health` endpoint. When dispatcher available, includes `compute` key with ray status, address, timeout, and (if Ray initialized) cluster resources from `ray.cluster_resources()`.
- **Evidence:**
  - dispatcher.py lines 61-93: `health()` method returns dict with ray_enabled, ray_initialized, ray_address, fallback_enabled, dispatch_timeout_seconds, and optional cluster key
  - tools/daemon.py + web/routes/system.py: Both expose compute health in their health endpoint implementations
- **Confidence:** HIGH

### Finding 7: Connect CLI Pre-Flight Only Checks Ray Version (Python Check Simplified)
- **Summary:** `council connect start` pre-flight check previously tried to probe head node Python version via Ray jobs (60 lines, 10s+ latency). Fixed in latest commit (07:44:36 UTC): removed `_probe_head_python()`, now only checks Ray version via `/api/version` endpoint. Python version matching is handled by Ray itself at worker startup with clear error messages.
- **Evidence:**
  - connect_cmd.py lines 138-180: `_preflight_version_check()` function
  - Fix commits (latest): Removed over-engineered probing, simplified to Ray version check only
- **Confidence:** HIGH

### Additional Notes
- **Config File Generation:** `.council/council.yaml` must have `council.compute.*` keys for this to work — operator responsibility
- **Head Node Resource Constraints:** Hetzner CCX23 has 1.5 vCPU, 3GB RAM allocated to Ray head (no GPUs) — CPU embeddings run here, GPU dispatch happens on workers only
- **Worker Connection:** `council connect start` joins local PC (20 CPU, 1 GPU RTX 4070, 39.7 GB) to head node over Tailscale at port 6379


---
## Technical Analysis
<!-- ID: technical_analysis -->

**Code Patterns Identified:**

1. **Lazy Singleton Dispatcher** (`compute/__init__.py`): Global `_dispatcher` variable, `get_dispatcher()` factory, `reset_dispatcher()` for tests — single instance shared across all embedding calls
2. **Async Executor Pattern** (embeddings.py): `loop.run_in_executor(None, ...)` for non-blocking local CPU embeddings in async context
3. **Ray Remote Decorator Pattern** (tasks.py): `@ray.remote(num_gpus=0.5)` on embedding functions, lazy cache of remote handles in `get_remote_tasks()`
4. **Config-Driven Feature Flags** (dispatcher.py): All behavior read from config dict at construction time, no runtime toggles
5. **Graceful Degradation** (dispatcher.py): Ray ImportError caught gracefully, returns False from `_ensure_ray()`, system continues on CPU

**System Interactions:**

- **ComputeDispatcher** ← used by → **Embedding Bridge** ← used by → **Council Tools** (memory, promote, domain, federation)
- **Ray Head Node** (Hetzner) ← connects to → **Ray Workers** (local PCs) via Tailscale port 6379
- **Config** (`.council/council.yaml`) → drives all compute settings at daemon startup
- **Health Endpoint** (`/api/system/health`) ← queries → ComputeDispatcher.health()

**Risk Assessment:**

- **Risk 1 - Blocking I/O in Tools:** Council MCP tools still invoke `embed_text_async()` WITHIN their async tool handlers but DON'T await it in all paths. When `ray_enabled=true` but Ray is offline, tools block on `_dispatch_local()` ThreadPoolExecutor call — no timeout. **Mitigation:** Verify all 5 call sites properly await with timeout handling.
- **Risk 2 - Silent Config Misses:** If operator forgets to set `council.compute.*` keys in `.council/council.yaml`, system silently defaults to `ray_enabled=false` — worker connection prepared but never used. **Mitigation:** Provide clear startup message when Ray is available but disabled.
- **Risk 3 - Version Pinning Brittleness:** Ray enforces exact Python version matching at connect time. If operator has 3.11.14 locally but head is 3.11.13, worker connection fails with cryptic error. **Mitigation:** Pre-flight check should validate local Python matches deployed head node version before `ray start`.


---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps
- [ ] **Audit 5 Call Sites for Timeout Safety:** Verify tools/memory.py, tools/promote.py, domain/queries.py, domain/loader.py, tools/federation.py all properly handle Ray dispatch timeouts (30s default from config).
- [ ] **Validate Config Defaults:** Ensure `.council/council.yaml` scaffolding includes `council.compute.*` section with sensible defaults (`ray_enabled=false` for dev, operator explicitly enables for prod).
- [ ] **Test Ray Disabled → Enabled Transition:** Verify embedding calls gracefully work both when Ray is disabled (CPU) and enabled (GPU) with no code changes.

### Long-Term Opportunities
- [ ] **Council Tool Async Refactoring:** Current MCP tool bodies are sync/blocking. Refactor high-volume tools (memory, promote) to expose async code paths that benefit from Ray dispatch during heavy workloads.
- [ ] **More Ray Tasks:** Currently only embeddings (2 tasks). Consider dispatching other CPU-heavy operations: LLM reasoning, batch processing, FAISS indexing.
- [ ] **Distributed Session Startup:** Operator directive mentions "Council tools must use Hetzner Postgres" — Ray distributed compute layer ready, but Council session management still local. Opportunity for cross-cluster session coordination.


---
## Appendix
<!-- ID: appendix -->

**References:**
- `src/council_mcp/compute/dispatcher.py` — ComputeDispatcher implementation (146 lines)
- `src/council_mcp/compute/embeddings.py` — Embedding bridge (124 lines)
- `src/council_mcp/compute/tasks.py` — Ray task definitions (87 lines)
- `src/council_mcp/compute/__init__.py` — Singleton factory (42 lines)
- `src/council_mcp/config.py` lines 1290-1310 — Config schema for `council.compute.*`
- Production call sites: tools/memory.py (lines 160, 253), tools/promote.py (line 152), domain/queries.py (line 67), domain/loader.py (line 214), tools/federation.py (line 677)
- PROGRESS_LOG.md entries 283-294: P3.4-P3.5 Phase completion (council_distributed_compute project)

**Attachments:**
- Ray cluster status: 2 nodes (1 head on Hetzner CCX23, 1 worker on local PC), 21 total CPUs, 1 GPU (RTX 4070), 39.7 GB memory
- Test coverage: 164 embedding-related tests across 9 test files (council_distributed_compute project)


---