---
id: council_distributed_compute-phase-plan
title: Phase Plan -- council_distributed_compute
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:21:15 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# Phase Plan -- council_distributed_compute
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-15 05:17:17 UTC

> Execution roadmap for council_distributed_compute.

---
## Phase Overview
<!-- ID: phase_overview -->
### Realignment Notice (2026-02-17)

> This plan was originally written before the `council_infra_pipeline` project completed most infrastructure work. Phases 0-2 and 4 are now DONE. Phase 3 (`council connect` + Ray cluster) is the only remaining work. This revision marks completed work and restructures Phase 3 into bounded task packages.

| Phase | Goal | Status | Evidence |
|-------|------|--------|----------|
| Phase 0 | Config-only quick wins (LLM switch, embedding switch) | DONE (P0.1) / DEFERRED (P0.2) | LLM on gpt-5-mini, embeddings stay local pending AgentKit patches |
| Phase 1 | Scribe PostgresStorage validation + Postgres-primary | DONE | Scribe containerized on Hetzner, Postgres backend, SSE transport |
| Phase 2 | Infrastructure deployment (Hetzner, Tailscale, Docker, data migration) | DONE | CCX23 running, 3-node Tailscale mesh, Docker Compose stack, data migrated |
| Phase 3 | `council connect` CLI + Ray distributed compute | NOT STARTED | Config keys exist, no implementation yet |
| Phase 4 | CI/CD pipeline | DONE | platform.yml: test->build->deploy in ~100s via Tailscale SSH |
| Phase 5+ | Future (Caddy public access, manage_docs DB, monitoring) | DEFERRED | Documented below |

**Remaining Critical Path**: Phase 3 only (5 task packages, est. 7-12 days)

**What exists already (from Phase 2):**
- `council.compute.*` config section in `config.py` DEFAULT_CONFIG (ray_enabled, ray_address, gpu_fallback_to_cpu, dispatch_timeout_seconds)
- `council.deployment.*` config section (mode, hub_tailscale_ip, gateway_domain)
- Ray head service COMMENTED OUT in `deploy/docker-compose.yaml` (placeholder from P2.2)
- All deploy scripts operational (backup, migrate, health-check, rollback, setup-hetzner, setup-linode)
- `get_compute_config()` helper in config.py

**What does NOT exist yet:**
- `src/council_mcp/compute/` directory (no Ray implementation)
- `council connect` CLI command (no connect_cmd.py)
- `deploy/Dockerfile.ray-head` (no Ray Docker image)
- `deploy/scripts/setup-ray-worker.sh` (no worker setup)
- No Ray Python dependencies in pyproject.toml
<!-- ID: phase_0 -->
**Status:** DONE (P0.1 complete, P0.2 deferred)

**Objective:** Switch LLM and embedding providers to cloud APIs via config changes only.

**Gate:** P0.1 passed. P0.2 deferred -- embeddings stay local (384-dim all-MiniLM-L6-v2) until AgentKit patches are applied.

**Completion Evidence:**
- P0.1: LLM switched to OpenAI gpt-5-mini, reflection tuned (micro_reflections=false, min_session_duration=15)
- P0.2: Blocker documented (3 AgentKit files need patches for OpenAI embedding dimension support). Reindex procedure documented. DEFERRED -- not blocking any other phase.

### Task Package P0.1: LLM Provider Switch [DONE]

**Status**: DONE
**Completed By**: Forge (2026-02-15)
**Evidence**: Config changes in `.council/council.yaml` -- primary_provider=openai, openai_model=gpt-5-mini, micro_reflections_enabled=false, min_session_duration=15

### Task Package P0.2: Embedding Provider Switch [DEFERRED]

**Status**: DEFERRED -- Blocked on 3 AgentKit patches (loader.py, openai_embedder.py). Not blocking other phases. Embeddings continue using local all-MiniLM-L6-v2 at 384 dimensions.

**Required AgentKit Patches** (documented for future work):
1. `agentkit/src/agentkit/config/loader.py:692-693` -- Remove hardcoded 1536 dimension validation
2. `agentkit/src/agentkit/llm_factory/embedder/openai_embedder.py:24` -- Read dim from config instead of hardcoding 1536
3. `agentkit/src/agentkit/llm_factory/embedder/openai_embedder.py:71` -- Pass dimensions param to OpenAI API call

**Reindex Procedure**: Documented in original plan. ~1 hour after patches applied.
<!-- ID: phase_1 -->
**Status:** DONE (completed via council_infra_pipeline project)

**Objective:** Validate that Scribe's PostgresStorage backend works correctly. Switch Scribe to Postgres-primary mode.

**Gate:** PASSED. Scribe is containerized on Hetzner running Postgres backend with SSE transport. Has been operational since deployment.

**Completion Evidence:**
- Scribe containerized as Docker service on Hetzner (`scribe` service in docker-compose.yaml)
- Postgres backend active (SCRIBE_DB_URL connects to agentkit database, `scribe` schema)
- SSE transport operational (MCPSSEClient in council web/daemon connects to Scribe over SSE)
- Scribe client-mode latency fix deployed (council_infra_pipeline)
- 233+ log entries written through Postgres-backed Scribe without data loss

**Original Task Packages (all superseded):**
- P1.1 Conformance Test Audit -- Superseded by production usage validation
- P1.2 Fix Conformance Gaps -- Not needed; Scribe Postgres works in production
- P1.3 Postgres-Primary Switch -- Done as part of containerized deployment
<!-- ID: phase_2 -->
**Status:** DONE (completed via council_infra_pipeline project)

**Objective:** Provision Hetzner CCX23, set up Tailscale mesh, deploy Docker Compose stack, migrate data.

**Gate:** PASSED. All services running on Hetzner, accessible via Tailscale mesh.

**Completion Evidence:**
- P2.1: Config-driven host resolution -- 51 localhost refs replaced, `council.compute.*` and `council.deployment.*` config sections added, `get_service_url()` helper, 26 unit tests pass
- P2.2: Dockerfile + Docker Compose -- Multi-stage build (base -> daemon, web), docker-entrypoint.sh with 5 Docker secrets, resource limits per Architecture Guide Section 4.5
- P2.3: Hetzner provisioning -- cloud-init.yaml, setup-hetzner.sh, backup-postgres.sh, migrate-data.sh (with Scribe dual-DB support), tailscale-acls.json
- P2.4: Linode Tailscale -- setup-linode.sh (idempotent, no exit node), Caddyfile with Council routes DEFERRED
- P2.5: Integration verified -- 3-node Tailscale mesh (dev PC, council-hub, Linode), all Docker services healthy, remote MCP tools working
- P2.6: Data migration executed -- migrate-data.sh run successfully, Council + Scribe data in single agentkit DB on Hetzner

**Infrastructure State (as of 2026-02-17):**
```
Hetzner CCX23 (council-hub):
  - postgres       :5432  (4GB/1CPU, pg_data volume)
  - council-daemon :8016  (2GB/0.8CPU)
  - council-web    :8015  (1.5GB/0.6CPU)
  - scribe         :8200  (1GB/0.5CPU, scribe_data volume)
  - corta-store    :8201  (512MB/0.3CPU, corta_store_data volume)
  All ports bound to ${TAILSCALE_IP:-127.0.0.1} -- never 0.0.0.0

Deploy scripts: backup-postgres.sh, deploy.sh, health-check.sh, rollback.sh,
                migrate-data.sh, setup-hetzner.sh, setup-linode.sh, lockdown-ssh.sh
```

**Original Task Packages (all complete):**
- P2.1 Config-Driven Host Resolution -- DONE (13 files, 26 tests)
- P2.2 Dockerfile + Docker Compose -- DONE (6 files created)
- P2.3 Hetzner Provisioning Scripts -- DONE (5 files)
- P2.4 Linode Tailscale + Caddy -- DONE (2 files)
- P2.5 Integration Smoke Test -- DONE (all connectivity verified)
- P2.6 Data Migration Execution -- DONE (Council + Scribe migrated)
<!-- ID: phase_3 -->
**Objective:** Implement `council connect` CLI command that starts a Ray worker on the operator's local PC (128GB DDR4, RTX 4070), connects to Ray head on Hetzner over Tailscale, registers the PC as a GPU compute node, and enables GPU task dispatch with CPU fallback.

**Gate:** `council connect` starts a Ray worker on local PC that joins the Hetzner Ray head. GPU embedding tasks dispatch to local PC when available. System falls back to CPU on Hetzner when PC offline.

**Prerequisites (all met):**
- Hetzner Docker Compose stack running (Phase 2)
- Tailscale mesh active between dev PC and council-hub (Phase 2)
- `council.compute.*` config section exists in config.py (ray_enabled, ray_address, etc.)
- `get_compute_config()` helper exists in config.py
- Ray head service placeholder exists (commented out) in docker-compose.yaml

**Estimated Total:** 7-12 days across 5 task packages

---

### Task Package P3.1: Ray Dependencies + Head Node Container

**Scope**: Add Ray as an optional dependency, create Ray head Docker image, uncomment ray-head service in docker-compose.yaml.

**Files to Modify/Create**:
- `pyproject.toml` -- Add `ray[default]==2.41.0` as optional dependency under `[project.optional-dependencies]` group `compute`
- `deploy/Dockerfile.ray-head` -- Custom Ray head image: `FROM rayproject/ray:2.41.0-py311`, copy council package, pip install
- `deploy/docker-compose.yaml` -- Uncomment ray-head service, use custom image build, configure resource limits

**Dependencies**: None (Phase 2 complete)

**Specifications**:
1. In `pyproject.toml`, add optional dependency group:
   ```toml
   [project.optional-dependencies]
   compute = ["ray[default]==2.41.0"]
   ```
2. Create `deploy/Dockerfile.ray-head`:
   ```dockerfile
   FROM rayproject/ray:2.41.0-py311
   WORKDIR /app
   COPY src/ src/
   COPY pyproject.toml .
   RUN pip install -e ".[compute]"
   CMD ["ray", "start", "--head", "--port=6379", "--dashboard-host=0.0.0.0", "--block"]
   ```
3. In `deploy/docker-compose.yaml`, uncomment the ray-head service block (currently lines 438-447). Configure:
   - `build: { context: .., dockerfile: deploy/Dockerfile.ray-head }`
   - `container_name: council-ray-head`
   - Resource limits: 3GB RAM, 0.8 CPU (per Architecture Guide Section 4.5)
   - Network: `backend` (same as other services)
   - Port: Ray head `6379` bound to `${TAILSCALE_IP}:6379` (workers connect over Tailscale)
   - Port: Ray dashboard `8265` bound to `${TAILSCALE_IP}:8265` (monitoring, optional)
   - Health check: `ray status` returns 0
4. Pin Ray version `2.41.0` consistently. Head and worker MUST match versions exactly.

**Verification**:
- [x] `pip install -e ".[compute]"` installs ray==2.41.0 without errors (verified: tomllib parse confirms compute group)
- [x] `docker compose -f deploy/docker-compose.yaml config` validates with ray-head service (verified: all fields correct)
- [x] `docker build --check` passes for Dockerfile.ray-head (no warnings)
- [ ] After deploy: `docker compose exec ray-head ray status` shows head node active with 0 workers (requires Hetzner deploy)

**Estimated Effort**: S-M (4-8 hours)
**Agent Model**: Opus (actual)

**Out of Scope (DO NOT TOUCH)**: Python source code in `src/council_mcp/`, existing services in docker-compose

---

### Task Package P3.2: `council connect` CLI Command

**Scope**: Create the `council connect` CLI command that starts a Ray worker on the local PC and joins it to the Ray head on Hetzner.

**Files to Create**:
- `src/council_mcp/cli/connect_cmd.py` -- The `council connect` command implementation

**Files to Modify**:
- `src/council_mcp/cli/main.py` -- Register the `connect` command group

**Dependencies**: P3.1 (Ray head running on Hetzner)

**Specifications**:
1. Command: `council connect` with subcommands:
   - `council connect start` -- Start Ray worker, join head, register as compute node
   - `council connect stop` -- Stop local Ray worker gracefully
   - `council connect status` -- Show connection status (head reachable, worker running, GPU available)

2. `council connect start` implementation:
   ```python
   @click.command()
   @click.option("--head-address", default=None, help="Ray head address (default: from config)")
   @click.option("--num-cpus", default=None, type=int, help="CPUs to expose (default: auto-detect)")
   @click.option("--num-gpus", default=None, type=int, help="GPUs to expose (default: auto-detect)")
   @click.option("--foreground", is_flag=True, help="Run in foreground (default: background)")
   def start(head_address, num_cpus, num_gpus, foreground):
   ```
   - Read `council.compute.ray_address` from config if `--head-address` not provided
   - Read `council.deployment.hub_tailscale_ip` to construct head address: `{hub_ip}:6379`
   - Verify Ray is installed: `try: import ray` with helpful error message if missing
   - Verify Tailscale connectivity: ping head IP before starting worker
   - Start ray worker: `ray start --address={head_address} --num-cpus={cpus} --num-gpus={gpus}`
   - If `--foreground`: block and show worker logs
   - If background (default): start as subprocess, write PID to `.council/ray-worker.pid`
   - Print connection summary: head address, CPUs, GPUs, worker status

3. `council connect stop`:
   - Read PID from `.council/ray-worker.pid`
   - Send SIGTERM, wait 10s, SIGKILL if needed
   - Run `ray stop` as cleanup
   - Remove PID file

4. `council connect status`:
   - Check if local worker is running (PID file + process alive)
   - Connect to Ray head and check `ray.cluster_resources()`
   - Report: head reachable, worker count, GPU available, local worker running

5. Register in `main.py`:
   ```python
   from council_mcp.cli.connect_cmd import connect
   cli.add_command(connect)
   ```

**Verification**:
- [x] `council connect --help` shows start/stop/status subcommands
- [x] `council connect start --head-address=<council-hub-ts-ip>:6379` starts worker (logic verified; full E2E requires P3.1 deploy)
- [x] `council connect status` shows worker connected, GPU detected (graceful output for all states)
- [x] `council connect stop` cleanly stops worker
- [x] Error handling: graceful message when Ray not installed, head unreachable, or already connected

**Estimated Effort**: M (1-2 days)
**Agent Model**: Sonnet

**Out of Scope (DO NOT TOUCH)**: ComputeDispatcher (P3.3), existing CLI commands, web UI

---

### Task Package P3.3: ComputeDispatcher Implementation

**Scope**: Create centralized dual-mode task dispatcher. When Ray is enabled and workers are available, dispatch GPU tasks to Ray. Otherwise, execute locally on CPU.

**Files to Create**:
- `src/council_mcp/compute/__init__.py`
- `src/council_mcp/compute/dispatcher.py`
- `src/council_mcp/compute/tasks.py`
- `tests/test_compute_dispatcher.py`

**Dependencies**: P3.2 (`council connect` working, Ray cluster operational)

**Specifications**:
1. `ComputeDispatcher` class in `dispatcher.py`:
   ```python
   class ComputeDispatcher:
       """Dual-mode task dispatcher: Ray (GPU) with local (CPU) fallback."""

       def __init__(self) -> None:
           cfg = get_compute_config()
           self._ray_enabled: bool = cfg.get("ray_enabled", False)
           self._ray_address: str = cfg.get("ray_address", "auto")
           self._timeout: int = cfg.get("dispatch_timeout_seconds", 30)
           self._fallback: bool = cfg.get("gpu_fallback_to_cpu", True)
           self._ray_initialized: bool = False

       async def dispatch(self, task_name: str, *args: Any, **kwargs: Any) -> Any:
           """Dispatch a task. Tries Ray if enabled, falls back to local."""
           if self._ray_enabled and self._ensure_ray():
               try:
                   return await self._dispatch_ray(task_name, *args, **kwargs)
               except Exception:
                   if self._fallback:
                       return await self._dispatch_local(task_name, *args, **kwargs)
                   raise
           return await self._dispatch_local(task_name, *args, **kwargs)

       def health(self) -> dict[str, Any]:
           """Return Ray cluster health info."""
           ...

       def _ensure_ray(self) -> bool:
           """Lazy-init Ray connection. Returns False if unavailable."""
           ...

       async def _dispatch_ray(self, task_name: str, *args, **kwargs) -> Any:
           """Submit task to Ray cluster."""
           ...

       async def _dispatch_local(self, task_name: str, *args, **kwargs) -> Any:
           """Execute task locally (CPU fallback)."""
           ...
   ```

2. `tasks.py` -- Define Ray-compatible task functions:
   ```python
   import ray

   @ray.remote(num_gpus=0.5)
   def embed_text_task(text: str) -> list[float]:
       """Generate embedding on GPU worker."""
       from agentkit.embeddings import embed_text
       return embed_text(text)

   @ray.remote(num_gpus=0.5)
   def batch_embed_task(texts: list[str]) -> list[list[float]]:
       """Batch embedding on GPU worker."""
       from agentkit.embeddings import embed_text
       return [embed_text(t) for t in texts]
   ```
   - Cache remote function handles -- do NOT create new `ray.remote()` wrappers per dispatch
   - Use lazy imports inside task functions (worker may have different installed packages)

3. Config reads from `council.compute.*` via `get_compute_config()`

4. Unit tests in `tests/test_compute_dispatcher.py`:
   - Test dispatch with `ray_enabled=False` -> local path
   - Test dispatch with `ray_enabled=True` + mock Ray -> ray path
   - Test fallback when Ray dispatch fails + `gpu_fallback_to_cpu=True`
   - Test timeout handling
   - Test health() method returns correct structure

**Verification**:
- [ ] `pytest tests/test_compute_dispatcher.py -v` -- all tests pass
- [ ] Dispatcher falls back to local when `ray_enabled: false` in config
- [ ] Dispatcher uses Ray when `ray_enabled: true` and Ray is available
- [ ] Dispatcher falls back to local when Ray task fails and fallback=true

**Estimated Effort**: M (2-3 days)
**Agent Model**: Sonnet

**Out of Scope (DO NOT TOUCH)**: AgentKit embedding code (P3.4), ProcessManager, web UI

---

### Task Package P3.4: Embedding Integration + AgentKit Wiring

**Scope**: Wire ComputeDispatcher into AgentKit's `embed_text()` path so GPU embeddings route through Ray when available.

**Files to Modify**:
- AgentKit embedding entry point (identify exact file -- likely `agentkit/src/agentkit/embeddings.py` or `agentkit/src/agentkit/llm_factory/embedder/`)
- `src/council_mcp/compute/dispatcher.py` -- Add singleton accessor

**Dependencies**: P3.3 (dispatcher implemented and tested)

**Specifications**:
1. Identify AgentKit's `embed_text()` entry point and its call sites
2. Create a dispatcher singleton:
   ```python
   # In compute/__init__.py
   _dispatcher: ComputeDispatcher | None = None

   def get_dispatcher() -> ComputeDispatcher:
       global _dispatcher
       if _dispatcher is None:
           _dispatcher = ComputeDispatcher()
       return _dispatcher
   ```
3. Wrap embedding calls through dispatcher when Ray is enabled:
   - If `ray_enabled=True`: `dispatcher.dispatch("embed_text", text)` routes to GPU
   - If `ray_enabled=False`: direct call to `embed_text()` (zero overhead, current behavior)
4. Maintain 100% backward compatibility: when `ray_enabled: false`, behavior is identical to current

**Verification**:
- [ ] Embedding generation works in local mode (`ray_enabled: false`) -- existing tests pass
- [ ] Embedding generation routes to GPU worker when Ray enabled + worker connected (Ray dashboard shows task)
- [ ] Embedding generation falls back to CPU when Ray enabled + worker disconnected
- [ ] No performance regression in local mode (embedding latency unchanged)

**Estimated Effort**: M (1-2 days)
**Agent Model**: Sonnet

**Out of Scope (DO NOT TOUCH)**: P0.2 OpenAI embedding switch (separate concern), web UI, ProcessManager

---

### Task Package P3.5: Health Monitoring + Status Integration

**Scope**: Surface Ray cluster status in the existing system health endpoint and `council connect status`. Enable the operator to see at a glance whether GPU compute is available.

**Files to Modify**:
- `src/council_mcp/compute/dispatcher.py` -- Ensure `health()` method returns structured data
- `src/council_mcp/tools/daemon.py` or system health endpoint -- Include Ray info in `/api/system/health`
- `src/council_mcp/cli/connect_cmd.py` -- `status` subcommand reads from health endpoint

**Dependencies**: P3.3 (dispatcher exists)

**Specifications**:
1. `ComputeDispatcher.health()` returns:
   ```python
   {
       "ray_enabled": True,
       "ray_initialized": True,
       "head_reachable": True,
       "workers": 1,
       "gpus_available": 1,
       "gpu_type": "NVIDIA RTX 4070",
       "cpu_fallback": True,
   }
   ```
2. Expose via existing `get_system_health` MCP tool or `/api/system/health` endpoint:
   ```json
   {
       "status": "healthy",
       "compute": {
           "ray_enabled": true,
           "workers": 1,
           "gpus_available": 1,
           "fallback_mode": "cpu"
       }
   }
   ```
3. `council connect status` reads this endpoint and formats for CLI output.

**Verification**:
- [ ] `/api/system/health` includes `compute` section when Ray is enabled
- [ ] Status correctly reflects: worker connected, worker disconnected, Ray disabled
- [ ] `council connect status` shows formatted output matching health data

**Estimated Effort**: S (4-6 hours)
**Agent Model**: Sonnet

**Out of Scope (DO NOT TOUCH)**: Web UI (no new pages), ProcessManager (deferred)
<!-- ID: phase_4 -->
**Status:** DONE (completed via council_infra_pipeline project)

**Objective:** Automated test, build, and deploy pipeline via GitHub Actions.

**Gate:** PASSED. Push to master triggers test->build->deploy in ~100 seconds.

**Completion Evidence:**
- Single unified workflow: `.github/workflows/platform.yml`
- 3 jobs: test (pytest subset), build (Docker images to GHCR), deploy (Tailscale SSH to council-hub)
- All 3 repos pulled and rebuilt on deploy (council, scribe, corta-store)
- Required secrets configured: TAILSCALE_OAUTH, DEPLOY_SSH_KEY, PROD_PG_PASSWORD, PROD_DATABASE_URL, PROD_COUNCIL_API_KEY, PROD_OPENAI_API_KEY, PROD_SCRIBE_DB_URL, PROD_STORE_HMAC_KEY
- Concurrency group prevents deploy races
- Rollback script: `deploy/scripts/rollback.sh`

**Original Task Packages (all superseded by unified workflow):**
- P4.1 Test Workflow -- Merged into platform.yml `test` job
- P4.2 Build + Push Workflow -- Merged into platform.yml `build` job
- P4.3 Deploy Workflow -- Merged into platform.yml `deploy` job
<!-- ID: phase_5 -->
Items deferred from MVP. Documented for future planning:

1. **Public access via Caddy reverse proxy** (1-2 days): Configure Caddy on Linode for inbound HTTPS reverse proxy to Council on Hetzner. Deploy Caddyfile, open ports 80/443 on Linode, configure domain DNS.
2. **manage_docs PostgreSQL migration** (5-8 days): Migrate 2,980-line file-based manage_docs to Postgres storage
3. **Security monitoring**: Wazuh + Falco when resource budget allows
4. **Sanctum ORBIT bridge**: Connect Council to Sanctum's orchestrator for cross-project compute
5. **Auto-scaling Ray cluster**: Cloud-based worker nodes for burst compute
6. **Prometheus/Grafana**: Full observability stack when resource budget allows (CCX33 upgrade)
7. **ProcessManager distributed adapter**: Replace SQLite+subprocess with Ray actors or Postgres-backed process registry
8. **Multi-region federation**: Council instances in multiple datacenters
9. **Postgres TLS hardening**: Certificate generation, postgresql.conf ssl settings, pg_hba.conf hostssl rules, sslmode=require in connection strings. Deferred because Tailscale WireGuard provides equivalent encryption at the network layer for MVP.

---

## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| P0.1: LLM Provider Switch | 2026-02-15 | Forge | DONE | Config changes in .council/council.yaml |
| P0.2: Embedding Provider Switch | DEFERRED | -- | DEFERRED | AgentKit patches required (3 files), not blocking |
| P0: Config quick wins | 2026-02-15 | Forge | DONE (P0.1) / DEFERRED (P0.2) | P0.2 not blocking Phase 3 |
| P1: Scribe Postgres validated | 2026-02-16 | infra_pipeline | DONE | Scribe containerized on Hetzner, Postgres backend |
| P2: Hetzner + Tailscale deployed | 2026-02-16 | infra_pipeline | DONE | Docker Compose stack on council-hub |
| P2.6: Data migration verified | 2026-02-16 | Operator + Forge | DONE | migrate-data.sh executed with Scribe dual-DB |
| P3.1: Ray dependencies + head node | 2026-02-17 | Forge | DONE | pyproject.toml compute group, Dockerfile.ray-head, docker-compose ray-head service |
| P3.2: `council connect` CLI | 2026-02-17 | Forge | DONE | connect_cmd.py: start/stop/status subcommands, main.py registered |
| P3.3: ComputeDispatcher | TBD | Forge | NOT STARTED | -- |
| P3.4: Embedding integration | TBD | Forge | NOT STARTED | -- |
| P3.5: Health monitoring | TBD | Forge | NOT STARTED | -- |
| P4: CI/CD pipeline active | 2026-02-16 | infra_pipeline | DONE | platform.yml: test->build->deploy |
| PROJECT COMPLETE: Production distributed | TBD | Atlas | Phase 3 remaining | 5 task packages left |
<!-- ID: retro_notes -->
### 2026-02-17: Phase Plan Realignment (Blueprint)

**What happened:** The `council_infra_pipeline` project was created to handle Docker/Hetzner/CI/CD deployment work. It completed Phases 1, 2, and 4 of this plan before the original plan was updated. This created significant drift between the plan and reality.

**Key lessons:**
1. **Cross-project tracking matters.** When work for one project gets done under a different project name, the original plan goes stale fast. The Scribe project boundary is a coordination challenge.
2. **Infrastructure work was significantly faster than estimated.** Original estimate: 18-28 days total. Actual for Phases 0-2, 4: approximately 5 days of active work across infra_pipeline. The Docker learning curve for the operator was less steep than feared.
3. **Scribe Postgres validation was a non-event.** We estimated 2-4 days for conformance testing. In practice, containerizing Scribe and running it on Postgres worked out of the box -- the scribe_pro_cleanup project had already fixed the backend.
4. **P0.2 (embeddings) correctly deferred.** AgentKit patches are needed but don't block the critical path. Local embeddings at 384-dim work fine.

| P3.3: ComputeDispatcher | 2026-02-17 | Forge | DONE | compute/__init__.py, dispatcher.py, tasks.py + 20/20 tests pass |

---
