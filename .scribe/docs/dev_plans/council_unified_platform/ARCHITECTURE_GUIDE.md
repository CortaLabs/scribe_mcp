---
id: council_unified_platform-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_unified_platform"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-18 02:55:28 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — council_unified_platform
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-18 01:53:25 UTC

> Architecture guide for council_unified_platform.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
**Context:** Council MCP currently operates as a centralized system — all compute, storage, agent execution, and web serving run on a single Hetzner CCX23 VPS (4 vCPU, 16GB RAM). A local PC "Nicolas" (20 CPU, RTX 4070 GPU, 40GB RAM) participates only as a Ray worker for basic embedding tasks. The operator's vision is for Council to become a **truly distributed system** where N nodes contribute specific capabilities (GPU compute, CPU capacity, repos, specialized services) coordinated by a central hub.

**Goals:**
- Enable N nodes to join the platform, each declaring capabilities (GPU, CPU, repos, services)
- Route work to nodes based on capability, not hardcoded topology
- Serve GPU-accelerated embeddings from worker nodes via TEI
- Sync repos across nodes so custom pages, templates, and agent sessions work anywhere
- Activate the existing but dormant federation system for cross-council communication
- Enable agent sessions to execute on remote nodes with transparent streaming
- Provide unified health monitoring across all nodes and services

**Non-Goals:**
- Public internet exposure (all traffic stays on Tailscale mesh)
- Multi-tenant isolation (all nodes are trusted, same operator)
- Kubernetes or container orchestration beyond Docker Compose
- Replacing existing infrastructure (COMMANDMENT #0.5 — extend, never replace)
- LLM serving (operator runs own llamacpp system independently — NOT part of this project)

**Success Metrics:**
- A new node joins the platform with `council connect start` and is visible in the dashboard within 30 seconds
- GPU embedding latency under 15ms per single text (excluding network)
- Agent sessions can execute on any node with the required provider installed
- Federation works between at least 2 councils on separate machines
- Zero service disruption when a worker node sleeps or disconnects
- `council connect start` survives network blips and node sleep/wake without manual intervention
<!-- ID: requirements_constraints -->
**Functional Requirements:**
- Node Registry: Register/deregister nodes with the hub, declaring capabilities
- Capability Dispatch: Route compute tasks and agent sessions to capable nodes
- GPU Embedding Serving: Persistent model serving on GPU nodes via TEI (HTTP)
- File Sync: Syncthing-based repo synchronization across nodes with role-based per-node sync policies
- Federation: Cross-council memory sharing, work item dispatch, remote registration
- Distributed Agent Execution: Agent sessions running on remote nodes via Ray Actors
- Unified Health Dashboard: Per-node metrics, service status, resource utilization
- Connection Supervision: `council connect start` must supervise the Ray worker with reconnection, heartbeat, and graceful sleep/wake handling

**Non-Functional Requirements:**
- All inter-node communication over Tailscale (WireGuard encrypted)
- Graceful degradation when worker nodes disconnect (sleep, restart, network drop)
- Config-driven behavior — all thresholds and endpoints in `council.yaml`
- Backward compatible — system works identically with `ray_enabled: false`
- Existing infrastructure preserved (ComputeDispatcher, SessionManager, StreamBridge, federation API)

**Assumptions:**
- All nodes run council_mcp (or a subset) with matching Python 3.11.13 and Ray 2.49.2
- Tailscale mesh is pre-configured between all participating nodes
- Hetzner hub is always-on; worker nodes are ephemeral
- Single Postgres instance on Hetzner serves all councils (shared DB pattern)
- Operator manages their own LLM serving independently (not part of this platform)

**Risks & Mitigations:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Worker node sleep causes 45-60s detection delay | High | Medium | Ray GCS timeout is 60s; supervision loop detects via `ray.is_initialized()` within 15s; UI shows "connecting..." status |
| Tailscale DERP relay fallback (30-100ms latency) | Low | Low | Monitor with `tailscale status`; alert if direct connection lost |
| Ray version drift between head and workers | Medium | High | Version pinned in docker-compose; pre-flight check in `council connect start` |
| Federation shared_secret compromise | Low | High | Rotate via `council federation rotate-secret`; HMAC envelope with TTL |
| Syncthing conflict on concurrent edits | Low | Low | Hub repos are read-only mirrors; conflicts auto-resolved by Syncthing |
| Connection supervision fails to reconnect | Medium | Medium | Exponential backoff (1s-60s), heartbeat to hub reports actual Ray connectivity state |
<!-- ID: architecture_overview -->
### System Architecture (ASCII Diagram)

```
                                 TAILSCALE MESH (WireGuard encrypted)
    +------------------------------------------------------------------------------+
    |                                                                              |
    |   +---- HUB (Hetzner CCX23) ----------------------------------------+      |
    |   |                                                                    |      |
    |   |  +--------------+  +--------------+  +--------------+             |      |
    |   |  | council-web  |  | council-     |  |  postgres    |             |      |
    |   |  |   :8015      |  | daemon :8016 |  |   :5432      |             |      |
    |   |  |              |  |              |  |  (all state)  |             |      |
    |   |  | SessionMgr   |  | Node         |  |              |             |      |
    |   |  | WorkerPool   |  | Registry     |  | agent_memories|            |      |
    |   |  | StreamBridge |  | Health Mon   |  | sessions      |            |      |
    |   |  | Dashboard    |  | Federation   |  | platform_nodes|            |      |
    |   |  +--------------+  +--------------+  +--------------+            |      |
    |   |                                                                    |      |
    |   |  +--------------+  +--------------+  +--------------+            |      |
    |   |  | scribe :8200 |  | ray-head     |  | corta-store  |            |      |
    |   |  |              |  | :6379 :8265  |  |   :8201      |            |      |
    |   |  +--------------+  +--------------+  +--------------+            |      |
    |   |                                                                    |      |
    |   |  +--------------+                                                  |      |
    |   |  | Syncthing    | <-- receives per-role repo subsets from workers  |      |
    |   |  | /opt/synced/ |                                                  |      |
    |   |  +--------------+                                                  |      |
    |   +--------------------------------------------------------------------+      |
    |                                                                              |
    |   +---- WORKER NODE (Nicolas / any PC) ---------------------------------+   |
    |   |                                                                      |   |
    |   |  +--------------+  +--------------+  +--------------+               |   |
    |   |  | Ray Worker   |  | TEI          |  | Syncthing    |               |   |
    |   |  | 20 CPU       |  | Embedding    |  | role-based   |               |   |
    |   |  | 1 GPU (4070) |  | Server :8080 |  | sync subsets |               |   |
    |   |  | 40GB RAM     |  | GPU-accel    |  |              |               |   |
    |   |  +--------------+  +--------------+  +--------------+               |   |
    |   |                                                                      |   |
    |   |  +--------------+  +--------------+                                  |   |
    |   |  | Supervision  |  | Claude Code  |                                  |   |
    |   |  | Loop (raylet |  | (IDE)        |                                  |   |
    |   |  | + heartbeat) |  |              |                                  |   |
    |   |  +--------------+  +--------------+                                  |   |
    |   +----------------------------------------------------------------------+   |
    |                                                                              |
    |   +---- WORKER NODE N (future) -----------------------------------------+   |
    |   |  Ray Worker + capabilities declared at `council connect start` time   |   |
    |   +----------------------------------------------------------------------+   |
    +------------------------------------------------------------------------------+
```

### Node Types

| Node Type | Role | Always On? | State | Examples |
|-----------|------|-----------|-------|---------|
| **Hub** | Coordinator, state store, web UI, Ray head | Yes | All persistent state (Postgres) | Hetzner CCX23 |
| **Worker** | Compute contributor (GPU/CPU), repo host | No (ephemeral) | Stateless (caches only) | Nicolas (local PC), future servers |

### Node-Council Data Model

**CRITICAL:** `platform_nodes` represents MACHINES, not councils. A single machine can host multiple councils. Therefore:
- `platform_nodes` is inherently GLOBAL — it has no `council_id` column
- The `council-isolation` rule does NOT apply to the `platform_nodes` table itself
- However, the platform dashboard endpoint respects council context: it shows which nodes are relevant to the active council
- A junction mapping (`platform_node_councils`) or a `councils_served` JSONB array on `platform_nodes` links machines to the councils they serve
- When filtering nodes for a specific council context, JOIN through this mapping

```sql
-- platform_nodes is GLOBAL (no council_id)
CREATE TABLE IF NOT EXISTS council.platform_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname TEXT NOT NULL UNIQUE,
    tailscale_ip TEXT,
    node_type TEXT NOT NULL DEFAULT 'worker',
    capabilities JSONB NOT NULL DEFAULT '{}',
    services JSONB NOT NULL DEFAULT '[]',
    repos TEXT[] DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'unknown',
    last_heartbeat TIMESTAMPTZ,
    resources JSONB DEFAULT '{}',
    councils_served TEXT[] DEFAULT '{}',  -- council IDs this node serves
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Communication Patterns

| Pattern | Transport | Use Case |
|---------|-----------|----------|
| MCP tools | WebSocket (ws://hub:8016) | Agent operations, memory, sessions |
| Compute dispatch | Ray Object Store | GPU tasks, embedding inference |
| Model serving | HTTP (TEI endpoint) | Embedding inference |
| Repo sync | Syncthing P2P | Custom pages, templates, config files (role-based subsets) |
| Federation | HTTP POST with HMAC | Cross-council work items and memories |
| Agent streaming | Ray Queue / Ray Generator | Remote session event relay |
| Health monitoring | HTTP REST (Ray Dashboard API) | Node status, resource utilization |
| Connection supervision | Thread + `ray.is_initialized()` | Worker raylet health monitoring |

### Key Architectural Decisions

| Decision | Choice | Rationale | Research Source |
|----------|--------|-----------|----------------|
| Compute fabric | Ray 2.49.2 | Already deployed, proven for embeddings, supports Actors and Serve | RESEARCH_RAY_ECOSYSTEM |
| Network fabric | Tailscale mesh | Already in place, WireGuard encryption, LAN-like latency | Existing infrastructure |
| State store | Postgres on hub (shared) | All councils share one DB via Tailscale; simplifies cross-council queries | RESEARCH_COUNCIL_FEDERATION |
| Embedding serving | TEI (HTTP) over Ray Serve | TEI is production-grade, handles batching, no Ray dependency for serving | RESEARCH_FILESYSTEM_AND_EMBEDDINGS |
| Repo sync | Syncthing over SSHFS | SSHFS hangs on sleep; Syncthing survives disconnection, P2P | RESEARCH_FILESYSTEM_AND_EMBEDDINGS |
| Remote agents | Ray Actors at WorkerPool layer | SessionManager/StreamBridge unchanged; only WorkerPool gains remote path | RESEARCH_DISTRIBUTED_AGENTS |
| Streaming mechanism | Ray Queue (Phase 1) | Simpler than Generator, proven, 5-15ms overhead acceptable | RESEARCH_DISTRIBUTED_AGENTS |
| Session model | Ephemeral and resumable | Don't fight node disconnections; persist state, resume on reconnect | RESEARCH_DISTRIBUTED_AGENTS |
| Node-machine model | Global (not council-scoped) | A machine is not a council; one machine can host multiple councils | Operator directive |
<!-- ID: detailed_design -->
### 4.1 Node Registry

**Purpose:** Track which machines are participating in the platform, what capabilities they offer, and their current health status.

**Data Model:** New table in `council` schema. `platform_nodes` is GLOBAL — a machine is not a council. One machine can host multiple councils. The `councils_served` array links machines to the councils they participate in. Dashboard endpoints filter nodes by active council context through this column.

```sql
-- See architecture_overview for full schema definition
-- Key: platform_nodes has NO council_id column (it's global)
-- Use councils_served TEXT[] for council-context filtering
```

**Capabilities Declaration:** When a node joins via `council connect start`, it declares its capabilities:

```yaml
# Capabilities detected automatically + user-configurable
council:
  node:
    hostname: "nicolas"              # Auto-detected from Tailscale
    role: "gpu-compute"              # Role determines sync policy (see 4.4)
    capabilities:
      gpu: true
      gpu_type: "rtx4070"
      gpu_vram_gb: 12
      cpu_cores: 20
      ram_gb: 40
    services:                        # Services this node offers
      - name: "tei"
        port: 8080
        type: "embedding"
        model: "all-MiniLM-L6-v2"
    repos:                           # Repos available on this node
      - "/home/austin/projects/MCP_SPINE/council_mcp"
      - "/home/austin/projects/MCP_SPINE/scribe_mcp"
```

**Registration Flow:**
1. Worker runs `council connect start --hub council-hub`
2. Supervision loop starts (see 4.1a below)
3. Joins Ray cluster (existing behavior, now supervised)
4. POSTs capabilities to hub: `POST /api/platform/nodes/register`
5. Hub upserts `platform_nodes` record
6. Heartbeat loop: worker POSTs `/api/platform/nodes/heartbeat` every 30s, includes actual Ray connectivity status
7. Hub marks node `offline` after 3 missed heartbeats (90s)

**Key Files to Modify:**
- `src/council_mcp/cli/connect_cmd.py` — add supervision, registration, heartbeat
- `src/council_mcp/storage/registry.py` — add `upsert_platform_node()`, `get_platform_nodes()`
- `src/council_mcp/web/routes/system.py` — add `/api/platform/nodes/*` endpoints

**Key File to Create:**
- `src/council_mcp/platform/nodes.py` — NodeRegistry class, heartbeat logic

---

### 4.1a Connection Supervision (CRITICAL)

**Problem:** The current `council connect start` implementation (526 lines in `connect_cmd.py`) is fire-and-forget. After running `ray start --address={address}`, it spawns the raylet daemon and exits. There is:
- No supervision loop to monitor the raylet process
- No automatic reconnection when the connection drops (network blip, hub restart, node sleep/wake)
- No heartbeat to report alive/dead status to the hub
- PID detection via `pgrep -f raylet` is fragile (may grab wrong PID with multiple Ray instances)
- Background mode has no daemon supervision at all

**Root Cause of Connection Drops:** When Nicolas sleeps and wakes, the raylet loses its connection to the Ray head. Since there is no supervision, the worker silently becomes a zombie — the PID file still exists, `is_pid_alive()` returns True (the process exists), but Ray is disconnected. The operator must manually run `council connect stop && council connect start`.

**Fix Design — Supervision System:**

```python
# In connect_cmd.py — new supervision thread after ray start

import threading

class RayWorkerSupervisor:
    """Monitors raylet health and reconnects on failure.
    
    Spawned by `council connect start` after initial Ray join.
    Runs as a daemon thread (background) or main thread (foreground).
    """
    
    def __init__(self, head_address: str, ray_cmd: list[str], hub_url: str):
        self._head_address = head_address
        self._ray_cmd = ray_cmd
        self._hub_url = hub_url
        self._running = True
        self._reconnect_backoff = 1.0  # seconds, exponential up to 60s
        self._check_interval = 15  # seconds between health checks
    
    def run(self) -> None:
        """Main supervision loop."""
        while self._running:
            time.sleep(self._check_interval)
            
            if not self._check_ray_health():
                logger.warning("Ray connection lost. Attempting reconnect...")
                self._reconnect()
    
    def _check_ray_health(self) -> bool:
        """Verify Ray is actually connected, not just that the process exists."""
        try:
            import ray
            # ray.is_initialized() checks if the driver is connected
            # This is the REAL test, not just checking PID existence
            return ray.is_initialized()
        except Exception:
            return False
    
    def _reconnect(self) -> None:
        """Stop ray, restart with exponential backoff."""
        backoff = self._reconnect_backoff
        while self._running:
            # Stop any existing ray processes
            subprocess.run(["ray", "stop"], capture_output=True)
            time.sleep(1)
            
            # Verify head is reachable
            head_host = self._head_address.split(":")[0]
            if not _ping_host(head_host, timeout=5):
                logger.info("Head unreachable, waiting %.1fs...", backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            
            # Attempt reconnection
            result = subprocess.run(self._ray_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # Verify connection actually works
                time.sleep(2)
                if self._check_ray_health():
                    logger.info("Reconnected to Ray cluster successfully")
                    self._reconnect_backoff = 1.0  # Reset backoff
                    return
            
            logger.warning("Reconnect failed, waiting %.1fs...", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    
    def stop(self) -> None:
        """Signal the supervisor to stop."""
        self._running = False
```

**Heartbeat Integration:**
The heartbeat POST to the hub includes the ACTUAL Ray connectivity state from `ray.is_initialized()`, not just "I'm alive." The hub uses this to distinguish between:
- Node online + Ray connected = `online`
- Node online + Ray disconnected = `reconnecting`  
- No heartbeat = `offline`

**Foreground Mode Change:**
Currently foreground blocks on `ray monitor` (log tailing). After this fix, foreground blocks on the supervision loop instead, which provides the same functionality (stays alive until Ctrl+C) but also monitors and reconnects.

**Graceful Shutdown:**
SIGTERM/SIGINT handler deregisters from hub (DELETE `/api/platform/nodes/{hostname}`) before running `ray stop`.

---

### 4.2 Capability-Based Dispatch

**Purpose:** Route compute tasks and agent sessions to the right node based on what it offers.

**Dispatch Resolution Chain** (priority order):

```
1. EXPLICIT -- User/config specifies target node
   | (if not specified)
2. SERVICE -- Task requires a specific service (TEI)
   | (if no service match)
3. RESOURCE -- Task requires GPU/CPU resources (Ray scheduling)
   | (if Ray unavailable)
4. LOCAL -- Fall back to hub CPU (existing behavior)
```

**Integration with ComputeDispatcher** (extend, not replace):

```python
# Enhanced dispatcher.py — add service-based dispatch
class ComputeDispatcher:
    async def dispatch(self, task_name: str, *args, **kwargs) -> Any:
        # 1. Check for service-based dispatch (TEI)
        service_url = self._resolve_service(task_name)
        if service_url:
            return await self._dispatch_service(service_url, task_name, *args, **kwargs)

        # 2. Existing Ray dispatch
        if self._ray_enabled and self._ensure_ray():
            try:
                return await self._dispatch_ray(task_name, *args, **kwargs)
            except Exception:
                if self._fallback:
                    return await self._dispatch_local(task_name, *args, **kwargs)
                raise

        # 3. Local fallback
        return await self._dispatch_local(task_name, *args, **kwargs)

    def _resolve_service(self, task_name: str) -> str | None:
        """Look up a service URL from the node registry for this task type."""
        cfg = get_compute_config()
        service_map = cfg.get("service_routes", {})
        # e.g., {"embed_text": "tei", "batch_embed": "tei"}
        service_name = service_map.get(task_name)
        if not service_name:
            return None
        # Query node registry for an online node offering this service
        node = self._node_registry.get_service_endpoint(service_name)
        return node.url if node else None
```

**Config:**
```yaml
council:
  compute:
    service_routes:                    # Map task names to service types
      embed_text: "tei"
      batch_embed: "tei"
    service_timeout_seconds: 10        # HTTP timeout for service calls
```

**Key Files to Modify:**
- `src/council_mcp/compute/dispatcher.py` — add `_resolve_service()`, `_dispatch_service()`
- `src/council_mcp/compute/tasks.py` — add `register_task()` API (GAP 1 from research)
- `src/council_mcp/config/__init__.py` — add `service_routes`, `service_timeout_seconds` to DEFAULT_CONFIG

---

### 4.3 GPU Compute Services

**Architecture Decision: TEI for embeddings.**

TEI chosen over Ray Serve because:
- Production-grade, maintained by HuggingFace
- OpenAI-compatible API (future migration path)
- Dynamic batching built-in
- Runs independently of Ray cluster (separate failure domain)
- No cold-start — model stays loaded in GPU memory

(Source: RESEARCH_FILESYSTEM_AND_EMBEDDINGS, RESEARCH_RAY_ECOSYSTEM)

**Embedding Service (TEI):**

```
Worker Node (Nicolas)
+------------------------------------------+
|  TEI Docker Container                     |
|  Image: ghcr.io/huggingface/tei:turing   |
|  Model: all-MiniLM-L6-v2                 |
|  Port: 8080 (Tailscale-bound)            |
|  GPU: RTX 4070 (num_gpus=0.25)           |
|  Endpoints:                               |
|    POST /embed          -- single/batch   |
|    POST /v1/embeddings  -- OpenAI compat  |
|    GET  /health         -- health check   |
+------------------------------------------+
```

**Integration with existing embed bridge:**

```python
# Modified embeddings.py — add TEI HTTP dispatch
async def embed_text_async(text: str) -> list[float]:
    cfg = get_compute_config()
    tei_url = cfg.get("tei_url", "")

    if tei_url:
        try:
            return await _embed_via_tei(tei_url, text)
        except Exception:
            pass  # Fall through to existing paths

    # Existing Ray/local paths unchanged
    if cfg.get("ray_enabled", False):
        dispatcher = get_dispatcher()
        return await dispatcher.dispatch("embed_text", text)

    return await asyncio.get_event_loop().run_in_executor(
        None, _embed_text_local, text
    )
```

**Note:** LLM serving is explicitly OUT OF SCOPE. The operator runs their own llamacpp system independently. No Ollama, vLLM, or LLM integration is part of this project.

---

### 4.4 File Sync Strategy

**Architecture Decision: Syncthing (not SSHFS) with intelligent per-node sync policies.**

SSHFS causes application hangs when the remote machine sleeps (45-60s freeze). Syncthing operates as a P2P daemon that syncs files asynchronously — disconnections are handled gracefully with no application impact.

(Source: RESEARCH_FILESYSTEM_AND_EMBEDDINGS)

**Per-Node Sync Policies (Role-Based):**

When a node runs `council connect start`, it declares a **role**. The role determines which repos/paths are synced to that node. This prevents GPU compute nodes from receiving web page templates they don't need, and ensures dev workstations get everything.

| Role | Sync Set | Rationale |
|------|----------|-----------|
| `gpu-compute` | Only `.council/council.yaml`, compute config | Compute-only nodes don't need web pages or templates |
| `dev-workstation` | Full `.council/` dirs for all repos | Developers need everything for local testing |
| `ci-runner` | Source code only, no `.council/web/` | CI needs to build and test, not serve pages |
| `hub` | Everything (receives from all workers) | Hub is the aggregator |

**Sync Policy Config:**

```yaml
council:
  sync:
    enabled: false                       # Master toggle
    provider: "syncthing"               # Only supported provider
    hub_sync_root: "/opt/synced"        # Where hub stores synced repos
    conflict_policy: "worker-wins"      # Worker is the source of truth
    roles:
      gpu-compute:
        sync_paths:
          - ".council/council.yaml"
        exclude_paths:
          - ".council/web/"
          - ".council/templates/"
      dev-workstation:
        sync_paths:
          - ".council/"
        exclude_paths: []
      ci-runner:
        sync_paths:
          - "src/"
          - "tests/"
          - "pyproject.toml"
        exclude_paths:
          - ".council/web/"
      hub:
        # Hub receives whatever workers send based on their role
        sync_paths: ["*"]
        exclude_paths: []
    reverse_sync:                       # Hub pushes to workers
      enabled: false
      paths:
        - ".council/council.yaml"       # Config updates
        - ".council/roster.yaml"        # Agent roster updates
```

**Sync Topology (Role-Aware):**

```
Worker Node (gpu-compute role)        Hub (Hetzner)
+----------------------+              +----------------------+
| Syncthing (sending)  |              | Syncthing (receiving)|
|                      |  Tailscale   |                      |
| Watches:             | -----------> | Syncs to:            |
|   .council/          |              |   /opt/synced/nicolas|
|     council.yaml     |              |     council.yaml     |
|                      |              |                      |
| NOT synced (role):   |              | Reverse sync:        |
|   .council/web/      | <----------- |   council.yaml       |
|   .council/templates/|  (optional)  |   roster.yaml        |
+----------------------+              +----------------------+

Worker Node (dev-workstation role)    Hub (Hetzner)
+----------------------+              +----------------------+
| Syncthing (sending)  |              | Syncthing (receiving)|
|                      |  Tailscale   |                      |
| Watches:             | -----------> | Syncs to:            |
|   .council/          |              |   /opt/synced/nicolas|
|     web/pages/       |              |     web/pages/       |
|     web/routes/      |              |     web/routes/      |
|     web/static/      |              |     web/static/      |
|     council.yaml     |              |     council.yaml     |
+----------------------+              +----------------------+
```

**Automatic Syncthing Folder Management:**

When `council connect start` runs, it:
1. Detects the node's declared role (from `council.node.role` config or `--role` flag)
2. Looks up the sync policy for that role in `council.sync.roles.{role}`
3. Calls the Syncthing REST API (`http://localhost:8384/rest/config/folders`) to configure shared folders
4. Configures the hub as the share target for those folders
5. No manual Syncthing configuration required

The hub side also has automation: when a node registers via `/api/platform/nodes/register`, the hub calls its local Syncthing API to accept the incoming share.

**Handling nodes that come and go:**
Syncthing natively handles disconnections — files synced before the node went offline remain available on the hub. When the node comes back, Syncthing resumes incremental sync automatically. No special handling needed.

**Docker Integration:**
```yaml
# deploy/docker-compose.yaml — add bind mount for synced repos
services:
  council-web:
    volumes:
      - /opt/synced:/opt/synced:ro      # Syncthing mirror, read-only
```

**Custom Page Discovery Enhancement:**
The existing `template_loader.py:discover_pages(repo_path)` needs to check both the local repo path AND the synced path:

```python
def discover_pages(repo_path: str) -> list[dict]:
    pages = []
    # Check local repo path (existing)
    local_pages = _scan_pages_dir(Path(repo_path) / ".council/web/pages")
    pages.extend(local_pages)
    # Check synced path (new)
    sync_root = cfg.get("council", {}).get("sync", {}).get("hub_sync_root", "")
    if sync_root:
        synced_path = Path(sync_root) / Path(repo_path).name / ".council/web/pages"
        if synced_path.exists():
            synced_pages = _scan_pages_dir(synced_path)
            pages.extend(synced_pages)
    return pages
```

---

### 4.5 Federation System

**Current State:** Federation API exists but is non-operational due to 6 gaps (RESEARCH_COUNCIL_FEDERATION).

**Fixes Required:**

| Gap | Fix | File |
|-----|-----|------|
| 1. Registration rejects remote paths | Add `remote: bool` to `CouncilRegisterRequest`; skip path check when true | `web/routes/councils.py` |
| 2. No API to set `api_endpoint` | Add `api_endpoint` to register request + `PATCH /api/councils/{id}` | `web/routes/councils.py`, `storage/registry.py` |
| 3. Empty `shared_secret` | Generate during `council init`; add `council federation setup` CLI | `cli/init_cmd.py`, new `cli/federation_cmd.py` |
| 4. Memory federation is intra-DB only | Implement `memory_federated` handler using existing `_copy_memory_to_council()` pattern | `web/routes/federation.py` |
| 5. Remote page discovery | Use Syncthing sync (4.4 above) | `web/template_loader.py` |
| 6. `register_council_sync` omits `api_endpoint` | Add `api_endpoint` parameter to function | `storage/registry.py` |
| **BLOCKER: SELECT queries omit `api_endpoint`** | Add `api_endpoint` to column list in ALL SELECT queries in `registry.py` | `storage/registry.py` |

**CRITICAL FIX — Registry SELECT Queries (Prerequisite for Federation):**

The following functions in `src/council_mcp/storage/registry.py` explicitly SELECT columns and OMIT `api_endpoint`:
- `list_councils_sync()` (line 95): `SELECT id, parent_council_id, name, repo_path, status, metadata, created_at, last_seen`
- `get_council_by_name_sync()` (line 107): same column list
- `get_council_by_id_sync()` (line 118): same column list

Without fixing these, federation silently fails because the web UI and API never see the `api_endpoint` even when it is stored in the database. **This must be the FIRST subtask of Phase 3.**

**Memory Federation Handler — Alignment with Existing Push:**

The existing `tools/federation.py` already has a complete memory federation push implementation:
- `_compute_text_hash(text)` — SHA-256 hash for deduplication (line 37)
- `_check_existing_federated_memory(target_council_id, source_council_id, text_hash)` — deduplication check (line 180)
- `_copy_memory_to_council(source_memory, target_council_id, source_council_id, text_hash)` — full copy with source tracking (line 204)

The receive handler in `web/routes/federation.py` (lines 490-497) is currently a no-op — it returns `{"status": "success", "received": True}` without storing anything.

**The receive handler MUST use the same patterns from `_copy_memory_to_council()`:**
1. Compute `text_hash` from received memory text using `_compute_text_hash()`
2. Check for duplicates using `_check_existing_federated_memory()`
3. If not duplicate, insert using `models.insert_persona_memory()` with:
   - `metadata["text_hash"] = text_hash`
   - `metadata["federated_from"] = {"source_council_id": ..., "source_memory_id": ...}`
4. Update `council_id` and `source_council_id` on the new memory record
5. Generate embedding for the received text

```python
# In web/routes/federation.py — memory_federated handler
if hook_type == "memory_federated":
    from council_mcp.tools.federation import (
        _compute_text_hash,
        _check_existing_federated_memory,
    )
    
    memory_data = payload.get("memory", {})
    text = memory_data.get("text", "")
    text_hash = _compute_text_hash(text)
    
    # Deduplication check
    existing = _check_existing_federated_memory(
        target_council_id=local_council_id,
        source_council_id=source_council_id,
        text_hash=text_hash,
    )
    if existing:
        return JSONResponse(content={
            "status": "duplicate",
            "existing_memory_id": existing,
        })
    
    # Store with source tracking (mirrors _copy_memory_to_council pattern)
    metadata = memory_data.get("metadata", {})
    metadata["text_hash"] = text_hash
    metadata["federated_from"] = {
        "source_council_id": source_council_id,
        "source_memory_id": memory_data.get("id"),
    }
    
    new_id = models.insert_persona_memory(
        project_id=memory_data.get("project_id"),
        persona_id=memory_data.get("persona_id"),
        text=text,
        memory_type=memory_data.get("memory_type", "semantic"),
        strength=memory_data.get("strength", 0.5),
        tags=memory_data.get("tags", []),
        metadata=metadata,
    )
    
    # Update council_id and source_council_id
    with db.connection() as conn:
        conn.execute(
            "UPDATE agent_memories SET council_id = %s, source_council_id = %s WHERE id = %s;",
            (local_council_id, source_council_id, new_id),
        )
    
    return JSONResponse(content={
        "status": "stored",
        "memory_id": str(new_id),
    })
```

**Enhanced Registration Flow:**
```
Worker Node                              Hub
    |                                     |
    | council init --parent council_mcp   |
    |   --auto-register                   |
    |   --api-key ck_...                  |
    |   --remote                          |
    |                                     |
    | POST /api/councils/register         |
    |   { name, remote: true,             |
    |     api_endpoint: "http://nicolas:8016",
    |     tailscale_ip: "100.x.y.z" }     |
    |                                     |
    | <-- 200 { council_id, status }      |
    |                                     |
    | Shared secret exchange              |
    |   (manual or via Tailscale channel) |
    |                                     |
```

---

### 4.6 Distributed Agent Execution

**Architecture Decision: Ray Actors at WorkerPool layer. SessionManager and StreamBridge remain unchanged on the hub.**

(Source: RESEARCH_DISTRIBUTED_AGENTS)

**Known Gap — Git Worktree:**
The distributed agents research (RESEARCH_DISTRIBUTED_AGENTS, confidence 0.88) identified that remote agent sessions need access to the repo's working tree. Currently, the SDK worker CWD is set to the repo path. On a remote node, this path may not exist or may be a different version. Solutions:
- Phase 1: Use Syncthing-synced repos as the CWD (depends on Phase 4 sync)
- Phase 2: Investigate git worktree or volume mounting for more precise control
This is acknowledged as an incomplete area — Phase 5 (Distributed Agents) task packages must include CWD resolution as a specification item.

**Component Architecture:**

```
Hub (Hetzner)                              Worker (Nicolas)
+-------------------------------+       +------------------------------+
| SessionManager (unchanged)    |       |                              |
|   |                           |       |                              |
| WorkerPool (enhanced)         |       |                              |
|   |                           |       |                              |
|   +-- LOCAL PATH (existing)   |       |                              |
|   |   ProcessManager + UDS    |       |                              |
|   |   SDKWorker (child proc)  |       |                              |
|   |                           |       |                              |
|   +-- REMOTE PATH (new)      |       | RemoteAgentActor (Ray Actor) |
|       Ray Actor handle -------|------>|   SDKProvider instance       |
|       Event relay task        |       |   Session state              |
|       StreamBridge.relay() <--|-------|   Event queue -> hub         |
|                               |       |                              |
+-------------------------------+       +------------------------------+
```

**New File: `src/council_mcp/compute/remote_agent.py`**

```python
@ray.remote(num_cpus=1)
class RemoteAgentActor:
    """Encapsulates an SDKWorker on a remote node.
    Communicates back to hub via Ray Queue for event streaming.
    """

    def __init__(self, provider_slug: str, config: dict, event_queue):
        self._provider_slug = provider_slug
        self._config = config
        self._queue = event_queue
        self._provider = None
        self._session = None

    async def create_session(self, config_dict: dict) -> dict:
        """Initialize provider and create session."""
        ...

    async def send_message(self, message: str) -> dict:
        """Send message; stream events via queue."""
        async for event in self._provider.send_message(self._session, message):
            self._queue.put(asdict(event))
        self._queue.put({"type": "stream_complete"})
        return {"ok": True}

    async def handle_tool_decision(self, tool_use_id: str, approved: bool) -> dict:
        """Forward tool approval to provider."""
        ...

    async def end_session(self) -> dict:
        """Cleanup session."""
        ...

    def health(self) -> dict:
        """Return actor health status."""
        ...
```

**WorkerPool Enhancement** (in `src/council_mcp/sdk/worker_pool.py`):

```python
class WorkerPool:
    async def _create_session(self, session_id: str, config: SessionConfig) -> str:
        dispatch_target = self._resolve_dispatch_target(config)

        if dispatch_target == "local":
            return await self._create_local_session(session_id, config)
        else:
            return await self._create_remote_session(session_id, config, dispatch_target)

    def _resolve_dispatch_target(self, config: SessionConfig) -> str:
        """Priority chain: explicit > repo > resource > local."""
        cfg = get_compute_config()
        agent_dispatch = cfg.get("agent_dispatch", {})

        if not agent_dispatch.get("enabled", False):
            return "local"

        # 1. Explicit target in session metadata
        explicit = (config.metadata or {}).get("dispatch_target")
        if explicit:
            return explicit

        # 2. Repo-based: check if cwd maps to a known node
        if config.cwd:
            for path_prefix, node in agent_dispatch.get("repo_node_map", {}).items():
                if config.cwd.startswith(path_prefix):
                    return node

        # 3. Resource-based: Ray schedules based on resource requirements
        return "ray_auto"  # Let Ray pick the node
```

**Event Relay Task** (on hub, in WorkerPool):

```python
async def _remote_event_relay(self, session_id: str, event_queue, bridge: StreamBridge):
    """Background task draining Ray Queue and relaying to StreamBridge."""
    while True:
        try:
            event_dict = await asyncio.to_thread(event_queue.get, timeout=300)
        except Empty:
            break  # Session idle timeout
        if event_dict.get("type") == "stream_complete":
            break
        stream_event = _dict_to_stream_event(event_dict)
        await bridge.relay(session_id, stream_event)
```

**Config:**
```yaml
council:
  compute:
    agent_dispatch:
      enabled: false                    # Feature flag
      default_strategy: "local"         # "local" | "resource" | "repo"
      fallback_to_local: true           # Fall back to local UDS if Ray fails
      repo_node_map:                    # Map repo prefixes to node names
        "/opt/": "hetzner"
        "/home/austin/projects/": "nicolas"
```

---

### 4.7 Health and Observability

**Unified Health Model:**

```python
# Enhanced /api/system/health response
{
    "status": "healthy",
    "hub": { "cpu_percent": 45, "memory_percent": 62, ... },
    "nodes": [
        {
            "hostname": "nicolas",
            "status": "online",
            "last_heartbeat": "2026-02-18T02:00:00Z",
            "capabilities": {"gpu": true, "gpu_type": "rtx4070", ...},
            "resources": {"cpu": 20, "gpu": 1, "ram_gb": 40},
            "utilization": {"cpu_percent": 12, "gpu_percent": 35, "gpu_memory_mb": 4200},
            "services": [
                {"name": "tei", "port": 8080, "status": "healthy", "model": "all-MiniLM-L6-v2"},
                {"name": "ray_worker", "status": "connected"}
            ]
        }
    ],
    "ray": {
        "enabled": true,
        "initialized": true,
        "cluster_resources": {"CPU": 24.0, "GPU": 1.0},
        "nodes_alive": 2
    },
    "federation": {
        "enabled": true,
        "councils_connected": 2,
        "last_federation_at": "2026-02-18T01:55:00Z"
    },
    "compute": { ... }  // Existing compute health
}
```

**Dashboard Page:** New custom page at `.council/web/pages/platform.html.j2` showing:
- Node grid with status indicators (online/offline/draining/reconnecting)
- Per-node resource utilization (CPU, GPU, RAM)
- Service health per node
- Federation status
- Active remote agent sessions
- Connection supervision status per worker

**Key Files to Modify:**
- `src/council_mcp/web/routes/system.py` — enhance `/api/system/health` with node data
- `src/council_mcp/compute/dispatcher.py` — enhance `health()` with per-node breakdown

**Key Files to Create:**
- `.council/web/pages/platform.html.j2` — dashboard page
- `.council/web/static/js/platform.js` — dashboard JS
- `.council/web/static/css/pages/platform.css` — dashboard styles

---

### 4.8 Security Model

**Trust Boundaries:**

```
TRUST ZONE 1: Tailscale Mesh (all nodes)
+-- WireGuard encrypted at network layer
+-- All nodes are operated by the same user
+-- All nodes share the same Postgres credentials
+-- No untrusted nodes in current design

TRUST ZONE 2: Inter-Council (federation)
+-- HMAC-SHA256 signed payloads
+-- Shared secret per council pair
+-- TTL on federation messages (300s default)
+-- Idempotency key replay protection
```

**For N-node expansion (future):**
- Ray cluster auth tokens (not implemented yet, not needed for trusted mesh)
- Per-node capability restrictions (only certain nodes can run certain providers)
- Service mesh policies (rate limiting, ACLs) — deferred

**Current Phase Security Posture:** The 2-node trusted cluster requires no additional security beyond Tailscale. Federation shared_secret is the only new credential needed.

---

### 4.9 Extensibility (Adding a New Node)

**Operator Experience:**

```bash
# 1. Install council_mcp on the new machine
pip install council_mcp[compute]

# 2. Ensure Tailscale is connected to the mesh
tailscale up

# 3. Join the platform (ONE command does everything)
council connect start \
  --hub council-hub \
  --role gpu-compute \
  --capabilities gpu=true,gpu_type=a100,gpu_vram_gb=80

# Under the hood (all automatic):
# - Joins Ray cluster (ray start --address=council-hub:6379)
# - Starts supervision loop (monitors raylet, auto-reconnects)
# - Registers with hub (POST /api/platform/nodes/register)
# - Starts heartbeat loop (reports Ray connectivity every 30s)
# - Configures Syncthing folders based on role
# - Node appears in dashboard within 30s

# 4. Optionally start services on the new node
council connect serve tei --model all-MiniLM-L6-v2 --port 8080
```

**No code changes required to add a new node.** The system discovers capabilities at join time and routes work accordingly.

**Command Reference (canonical — no aliases):**
- `council connect start` — Join the platform. Starts Ray worker, supervision loop, registration, heartbeat, Syncthing config.
- `council connect stop` — Leave the platform. Deregisters from hub, stops Ray, cleans up.
- `council connect status` — Show connection status, registered node info, Ray connectivity.
- `council connect serve <service>` — Start a service (TEI) on the local node.
<!-- ID: directory_structure -->
```
src/council_mcp/
+-- platform/                          # NEW -- Node registry and platform management
|   +-- __init__.py
|   +-- nodes.py                       # NodeRegistry class, heartbeat, capability detection
|
+-- compute/                           # EXISTING -- Extended
|   +-- __init__.py                    # Singleton dispatcher factory (unchanged)
|   +-- dispatcher.py                  # ComputeDispatcher -- add service dispatch path
|   +-- embeddings.py                  # Embedding bridge -- add TEI HTTP path
|   +-- tasks.py                       # Task registry -- add register_task() API
|   +-- remote_agent.py                # NEW -- RemoteAgentActor (Ray Actor)
|   +-- health.py                      # NEW -- Unified health aggregation
|
+-- sdk/
|   +-- worker_pool.py                 # MODIFIED -- Add remote dispatch path
|   +-- session_manager.py             # UNCHANGED -- SessionManager stays hub-local
|   +-- stream_bridge.py               # UNCHANGED -- StreamBridge stays hub-local
|   +-- ...
|
+-- storage/
|   +-- registry.py                    # MODIFIED -- Add upsert_platform_node(), api_endpoint in SELECTs
|   +-- ...
|
+-- web/
|   +-- routes/
|   |   +-- system.py                  # MODIFIED -- Add /api/platform/nodes/* endpoints
|   |   +-- councils.py                # MODIFIED -- Remote registration support
|   |   +-- federation.py              # MODIFIED -- Implement memory_federated handler
|   +-- template_loader.py             # MODIFIED -- Check synced paths for pages
|   +-- ...
|
+-- cli/
|   +-- connect_cmd.py                 # MODIFIED -- Add supervision loop, registration, heartbeat
|   +-- federation_cmd.py              # NEW -- council federation setup/rotate-secret
|
+-- config/
|   +-- __init__.py                    # MODIFIED -- Add new config keys
|
+-- tools/
    +-- federation.py                  # EXISTING -- _copy_memory_to_council() pattern used by receive handler

.council/web/pages/
+-- platform.html.j2                   # NEW -- Platform dashboard page

deploy/
+-- docker-compose.yaml                # MODIFIED -- Add Syncthing volume mount
+-- ...

db/schema/council/tables/
+-- platform_nodes.sql                 # NEW -- Platform nodes table (GLOBAL, no council_id)
```
<!-- ID: data_storage -->
**Primary Datastore:** PostgreSQL on Hetzner hub (shared across all councils/nodes via Tailscale)

| Table | Schema | Purpose | New/Existing |
|-------|--------|---------|-------------|
| `council.platform_nodes` | council | Node registry (hostname, capabilities, services, status) — GLOBAL, no council_id | NEW |
| `council.councils` | council | Council registry (add `api_endpoint` to SELECT queries) | MODIFIED |
| `council.council_bindings` | council | Project-to-council links | EXISTING |
| `public.persona_profiles` | public | Agent profiles (council-scoped) | EXISTING |
| `public.agent_memories` | public | Memories (federation target) | EXISTING |

**Schema Migration:** One new table (`council.platform_nodes`) created via `agentkit-schema plan/apply`. No destructive changes to existing tables. The `api_endpoint` column on `council.councils` already exists (no migration needed) — the fix is adding it to SELECT queries in `registry.py`.

**State Ownership:**
- Hub owns all persistent state (Postgres)
- Worker nodes are stateless — they hold only transient compute state (model weights in GPU memory, Ray Actor state)
- Session state flows to Postgres via existing SDK pathways (no change)
- `platform_nodes` is global (not council-scoped) — machines serve multiple councils. Use `councils_served` column for dashboard context filtering.
<!-- ID: testing_strategy -->
**Unit Tests:**
- `tests/test_node_registry.py` — Node CRUD, capability matching, heartbeat timeout logic
- `tests/test_dispatcher_service.py` — Service-based dispatch routing, TEI integration mock
- `tests/test_federation_fixes.py` — Remote registration, api_endpoint CRUD, memory federation handler
- `tests/test_remote_agent.py` — RemoteAgentActor creation, mock provider, event serialization

**Integration Tests:**
- `tests/test_compute_tei_integration.py` — TEI HTTP client with mock server
- `tests/test_dispatch_chain.py` — Full dispatch chain: service -> Ray -> local fallback
- `tests/test_federation_e2e.py` — End-to-end federation with HMAC envelope

**Manual QA:**
- Deploy TEI on Nicolas, verify embedding latency via `/api/system/health`
- Add Nicolas as platform node, verify dashboard shows capabilities
- Sleep Nicolas, verify hub gracefully marks node offline within 90s
- Resume Nicolas, verify node comes back online automatically

**Observability:**
- All new config keys added to CONFIG_SCHEMA (web UI editable)
- Health endpoint enhanced with per-node metrics
- Scribe logging in all new components
<!-- ID: deployment_operations -->
**Environments:**
- Local development: `ray_enabled: false`, all services local, no TEI
- Distributed: `ray_enabled: true`, TEI on Nicolas, Syncthing active, federation enabled

**Deploy Sequence:**
1. Push code to master
2. SSH to Hetzner: `git pull && docker compose build && docker compose up -d`
3. On Nicolas: `council connect start` (registers node, starts supervision, begins heartbeat)
4. Verify: `ssh council-hub "/opt/council_mcp/deploy/scripts/health-check.sh"`

**Configuration Management:**
- All new config keys in `council.yaml` under `council.compute.*`, `council.platform.sync.*`, `council.platform.*`
- Dual registration: DEFAULT_CONFIG + templates/defaults/council.yaml (per config-standards rule)
- Secrets: federation `shared_secret` in `/opt/council_mcp/secrets/federation_secret.txt`

**Rollback:**
- Feature flags on all new capabilities (`ray_enabled`, `agent_dispatch.enabled`, `sync.enabled`)
- Disable any feature by setting flag to `false` and restarting
- Node registry is additive — removing nodes does not affect existing functionality
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should TEI run as Docker on Nicolas or as a systemd service? | Operator | TODO | Docker preferred for consistency but adds overhead on dev PC |
| Ray Queue vs Ray Generator for streaming? | Blueprint | DECIDED | Queue for Phase 1; evaluate Generator if latency is a problem |
| Should worker nodes run their own council daemon? | Blueprint | DECIDED | No — workers are compute-only. They connect to hub daemon via Ray and Tailscale HTTP |
| Syncthing vs git-webhook-triggered sync? | Operator | TODO | Syncthing for real-time; git webhook for less-frequent updates. Start with Syncthing |
| Should platform_nodes be a new table or metadata on councils? | Blueprint | DECIDED | New table — cleaner schema, nodes are not councils. A node can host multiple councils. Table is GLOBAL (no council_id). |
| How to resolve CWD for remote agent sessions? | Blueprint | OPEN | Research flagged git worktree gap. Phase 1: use Syncthing-synced paths. Phase 2: investigate worktree. |
| Syncthing API key management for automated folder config? | Blueprint | OPEN | `council connect start` needs Syncthing API access to configure folders per role. Need to decide key distribution. |
<!-- ID: references_appendix -->
**Research Documents (all in `.scribe/docs/dev_plans/council_unified_platform/research/`):**
- `RESEARCH_RAY_ECOSYSTEM.md` — Ray Serve, Actors, GPU scheduling, embedding serving
- `RESEARCH_DISTRIBUTED_AGENTS.md` — Agent execution across nodes, WorkerPool integration
- `RESEARCH_CURRENT_RAY_CODEBASE.md` — Current compute layer audit, 10 gaps
- `RESEARCH_COUNCIL_FEDERATION_20260218.md` — Federation API audit, 6 gaps
- `RESEARCH_FILESYSTEM_AND_EMBEDDINGS.md` — SSHFS vs Syncthing, TEI vs Ray Serve

**Key Existing Files:**
- `src/council_mcp/compute/dispatcher.py` — ComputeDispatcher (extend with service dispatch)
- `src/council_mcp/compute/tasks.py` — Task registry (add dynamic registration)
- `src/council_mcp/compute/embeddings.py` — Embedding bridge (add TEI path)
- `src/council_mcp/sdk/worker_pool.py` — WorkerPool (add remote dispatch)
- `src/council_mcp/storage/registry.py` — Council registry (fix SELECT queries, add api_endpoint, add platform node functions)
- `src/council_mcp/web/routes/federation.py` — Federation receive endpoint (implement memory handler)
- `src/council_mcp/tools/federation.py` — Federation push tools (_copy_memory_to_council pattern)
- `src/council_mcp/web/routes/councils.py` — Council registration (add remote flag)
- `src/council_mcp/cli/connect_cmd.py` — Worker lifecycle (add supervision, registration, heartbeat)
- `src/council_mcp/config/__init__.py` — Config defaults (add new keys)

**External References:**
- [HuggingFace TEI](https://github.com/huggingface/text-embeddings-inference)
- [Ray Serve Architecture](https://docs.ray.io/en/latest/serve/architecture.html)
- [Syncthing Getting Started](https://docs.syncthing.net/intro/getting-started.html)
- [Syncthing REST API](https://docs.syncthing.net/dev/rest.html)
- [Ray Actor Fault Tolerance](https://docs.ray.io/en/latest/ray-core/fault_tolerance/actors.html)
