---
id: council_unified_platform-research-tei-container-lifecycle-20260221
title: "\U0001F52C Research Tei Container Lifecycle 20260221 \u2014 council_unified_platform"
doc_type: RESEARCH_TEI_CONTAINER_LIFECYCLE_20260221
doc_name: RESEARCH_TEI_CONTAINER_LIFECYCLE_20260221
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 02:48:08 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Tei Container Lifecycle 20260221 — council_unified_platform
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-21 02:46:21 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** atlas

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## 1. Current Architecture Summary

### 1.1 connect_cmd.py Flow (Lines 804-980)

**The `council connect start` command**:
1. Check Ray installed (line 813)
2. Check for already-running worker (line 820)
3. Resolve head address (line 829)
4. Ping head node for reachability (line 834)
5. Pre-flight Python version check (line 846)
6. Build `ray start` command with CPU/GPU exposure (lines 849-853)
7. Run Ray worker subprocess (line 857)
8. Verify connectivity via `ray.is_initialized()` (line 867)
9. Detect Ray node ID via `ray.get_runtime_context().get_node_id()` (line 891)
10. Detect available repos via `_detect_repos()` (line 894)
11. Register with hub via `_register_with_hub()` (lines 904-908)
12. Create `RayWorkerSupervisor` (lines 917-923)
13. Register signal handlers (SIGTERM/SIGINT) (lines 926-938)
14. Start supervision loop (blocking, line 969)

**Confidence: HIGH** — verified line by line in connect_cmd.py

### 1.2 RayWorkerSupervisor Class (Lines 585-750)

- Monitors Ray health via `ray.is_initialized()` — NOT PID-based
- On health loss, attempts reconnect with exponential backoff (lines 699-750)
- Sends heartbeat every `_heartbeat_interval` seconds (default 30, from config at line 625)
- Heartbeat refreshes current Ray node ID (line 663)
- All config from `council.compute.*` and `council.node.*` (lines 614-626)

**Confidence: HIGH** — class reviewed in full

### 1.3 council connect stop (Lines 1026-1095)

- Deregister from hub (best-effort, lines 1030-1046)
- Send SIGTERM to Ray worker PID (line 1068)
- Wait `_STOP_GRACE_SECONDS` for graceful shutdown (lines 1075-1079)
- Fall back to SIGKILL if needed (lines 1082-1087)
- Run `ray stop` cleanup (line 1091)
- Remove PID file (line 1094)

**Confidence: HIGH** — function reviewed in full

### 1.4 Service Registration: _register_with_hub() (Lines 410-471)

**Current registration payload** (lines 428-445):
```python
{
    "hostname": str,
    "node_type": "worker",
    "capabilities": {
        "cpu_cores": int,
        "gpu": bool,
        "gpu_type": str | None,
    },
    "services": [],  # ← ALWAYS EMPTY TODAY (line 436)
    "repos": list[str],
    "resources": {
        "cpu_cores": int,
        "ram_gb": float,
        "gpu_vram_gb": float,
    },
    "role": str,  # e.g., "gpu-compute", "dev-workstation"
    "councils_served": list[str],
    "ray_node_id": str | None,
}
```

**Key observation**: The `services` array is pre-allocated but never populated. **This is the integration point for TEI service registration.**

**Confidence: HIGH** — verified in code

---

## 2. Service Registration & Lookup

### 2.1 Hub Service Lookup: nodes.py get_service_endpoint() (Lines 249-289)

The hub finds services via SQL query on `services` JSONB array:
```sql
SELECT hostname, tailscale_ip
FROM council.platform_nodes
WHERE status = 'online'
  AND EXISTS (SELECT 1 FROM jsonb_array_elements(services) AS svc 
             WHERE svc->>'name' = ?)
ORDER BY last_heartbeat DESC
LIMIT 1
```

Returns:
```python
{
    "hostname": "gpu-worker-1",
    "url": "http://<tailscale_ip>:<port>"  # Port extracted from matching service entry
}
```

### 2.2 Expected Service Structure in Registration Payload

From nodes.py lines 276-282, services are expected as:
```python
[
    {
        "name": "tei",              # Service name
        "port": 8080,               # Container port
    }
]
```

Heartbeat does NOT update the services array — only initial registration does (via `_register_with_hub`).

**Confidence: HIGH** — verified in nodes.py implementation

---

## 3. TEI Integration: Current State (embeddings.py)

### 3.1 Routing Priority (Lines 134-169)

1. **TEI HTTP** (lines 149-156): If `tei_url` is set and non-empty, POST to `/embed` endpoint
2. **Ray Cluster** (lines 159-163): If `ray_enabled=True`, dispatch via `ComputeDispatcher`
3. **Local CPU** (lines 166-169): Fallback to AgentKit via executor

### 3.2 TEI HTTP Requests

- Single text: `_embed_via_tei(url, text, timeout=5.0)` — POST `{url}/embed` with `{"inputs": text}`
- Batch: `_batch_embed_via_tei(url, texts, timeout)` — POST `{url}/embed` with `{"inputs": [...text list...]}`
- Both return `list[float]` or `None` on failure (graceful fallback)

### 3.3 Config Keys (DEFAULT_CONFIG lines 797-798, CONFIG_SCHEMA lines 1395-1403)

```python
"tei_url": "",                          # Empty = disabled
"tei_timeout_seconds": 5,               # HTTP timeout for TEI requests
```

**Both keys verified in DEFAULT_CONFIG and CONFIG_SCHEMA with matching defaults and bounds.**

**Confidence: HIGH** — config verified

---

## 4. Docker Usage Patterns in Codebase

### 4.1 Current Docker Usage (61 matches in 4 files)

- `repo_cmd.py` — Git/repo operations (no Docker)
- `connect_cmd.py` — subprocess calls only (Ray operations, no Docker)
- `env_cmd.py` — environment setup
- `config/__init__.py` — config paths

### 4.2 Key Pattern: subprocess.run()

All subprocess operations in connect_cmd.py use:
```python
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    logger.warning("Command failed: %s", result.stderr)
    # Handle error or raise ClickException
```

**No Python Docker SDK** (`docker` package) is used anywhere in the codebase.

### 4.3 Example: Ray Process Management

```python
# Line 857 — start Ray worker
result = subprocess.run(cmd, capture_output=True, text=True)

# Line 1054-1055 — stop Ray worker
result = subprocess.run(["ray", "stop"], capture_output=True, text=True)
```

**Confidence: HIGH** — verified via grep + code review

---

## 5. Role-Based Policies Pattern (sync_policies.py)

The codebase already has a role-based policy resolution pattern:

**SyncPolicyResolver** (lines 21-99):
1. Reads `council.sync.role_policies` — dict mapping role → config
2. Each role has sync paths and direction (sendreceive, receiveonly, etc.)
3. Fallback to `council.sync.default_sync_paths` if role not found
4. Applied at registration time via `_trigger_sync_setup_safe()` in nodes.py (lines 124-153)

**This is the EXACT pattern we should follow for TEI container policies:**
- Map each role to TEI config (enabled/disabled, model, ports, etc.)
- Apply role-based container startup/shutdown rules in connect_cmd

**Confidence: HIGH** — pattern verified

---

## 6. Config Keys: Expansion Plan

### 6.1 Existing council.compute.* keys (lines 794-800)

```python
"ray_enabled": False,
"ray_address": "auto",
"gpu_fallback_to_cpu": True,
"dispatch_timeout_seconds": 30,
"supervision_check_interval_seconds": 15,
"supervision_reconnect_max_backoff_seconds": 60,
"tei_url": "",
"tei_timeout_seconds": 5,
"service_routes": {},
"service_timeout_seconds": 10,
```

### 6.2 New config keys needed for TEI container lifecycle

Under `council.compute.tei_container.*`:
- `enabled` — master toggle (bool, default False)
- `image` — Docker image (str, default `"ghcr.io/huggingface/text-embeddings-inference:cpu-latest"`)
- `port` — container port (int, default 8080)
- `model` — model name (str, default `"BAAI/bge-base-en-v1.5"`)
- `gpu_memory_gb` — GPU memory limit (float, default 8.0)
- `health_check_interval_seconds` — health probe interval (int, default 10)
- `startup_timeout_seconds` — max wait for container startup (int, default 60)

Under `council.node.services_by_role.*`:
- Per-role service policies (tei enabled/disabled, port overrides, etc.)

**Confidence: MEDIUM** — pattern inferred from embeddings.py config usage
<!-- ID: technical_analysis -->
## Integration Design Options

### Option A: Docker CLI Subprocess (Recommended for this codebase)

**Pattern**: Use `subprocess.run(['docker', ...])` like Ray process management

**Advantages**:
- Consistent with existing Ray management pattern (lines 857, 1054)
- Minimal dependencies (no Docker Python SDK)
- Already standard error handling in place
- Easy to test (mock subprocess.run)

**Disadvantages**:
- Docker CLI must be installed on the machine
- Error messages from Docker are less structured
- Health checking requires HTTP probes (not container native)

**Docker commands needed**:
```bash
# Start TEI container
docker run -d \
  --name council-tei \
  --gpus all \
  -p 127.0.0.1:8080:8080 \
  -e MODEL_ID=BAAI/bge-base-en-v1.5 \
  -e DTYPE=float32 \
  ghcr.io/huggingface/text-embeddings-inference:latest

# Health check
docker exec council-tei curl -f http://localhost:8080/health

# Stop container
docker stop council-tei
docker rm council-tei
```

**Implementation location**: New module `src/council_mcp/compute/tei_container.py` with:
- `TEIContainerManager` class
- `start_tei_container(config) -> bool`
- `stop_tei_container() -> bool`
- `health_check_tei_container() -> bool`

**Confidence: HIGH** — follows existing patterns in codebase

---

### Option B: Docker Python SDK

**Pattern**: Use `docker` package (`pip install docker`)

**Advantages**:
- Structured error handling
- Native container health checks
- Can inspect container state directly
- Better streaming/logging

**Disadvantages**:
- Adds dependency to project
- More complex exception handling
- Overkill for simple start/stop/health workflow

**Example code**:
```python
import docker

client = docker.from_env()
container = client.containers.run(
    image="ghcr.io/huggingface/text-embeddings-inference:latest",
    name="council-tei",
    gpus="all",
    ports={"8080/tcp": 8080},
    environment={"MODEL_ID": "BAAI/bge-base-en-v1.5"},
    detach=True
)

# Health check
try:
    response = container.exec_run("curl -f http://localhost:8080/health")
    is_healthy = response.exit_code == 0
except:
    is_healthy = False

container.stop()
container.remove()
```

**Confidence: MEDIUM** — not used in current codebase

---

### Option C: Hybrid (Container management via CLI, health checks via HTTP)

**Pattern**: Use `subprocess` for container lifecycle, HTTP requests for health checks

**Advantages**:
- Minimal dependencies
- Follows existing Ray pattern
- Clean separation (container ops vs health probes)
- Testable at both levels

**Disadvantages**:
- Two different interfaces for the same system

**Recommended approach**: **Option A with HTTP health checks**

- `start_tei_container()` — uses `docker run`
- `stop_tei_container()` — uses `docker stop/rm`
- `health_check_tei_container()` — uses `httpx` to POST `/health` endpoint

This mirrors how embeddings.py already does HTTP health checks for TEI.

**Confidence: HIGH** — consistent with codebase patterns

---

## Proposed TEI Container Lifecycle Flow

### On `council connect start --role gpu-compute`

1. **Check prerequisites**:
   - Docker installed and running (`docker ps`)
   - Role is `gpu-compute` (from `--role` arg or config)
   - Config `council.compute.tei_container.enabled = True`

2. **Stop any existing TEI container** (best-effort cleanup):
   ```bash
   docker stop council-tei 2>/dev/null || true
   docker rm council-tei 2>/dev/null || true
   ```

3. **Start TEI container**:
   ```bash
   docker run -d \
     --name council-tei \
     --gpus all \
     -p 127.0.0.1:{port}:8080 \
     -e MODEL_ID={config.tei_model} \
     -e DTYPE={config.tei_dtype} \
     {config.tei_image}
   ```

4. **Wait for container startup** (with timeout):
   - Poll `/health` endpoint every 2 seconds
   - Max wait: `config.tei_container.startup_timeout_seconds` (default 60)
   - Fail fast with clear error if startup fails

5. **Update `tei_url` config** (in-memory):
   ```python
   tei_url = f"http://localhost:{port}"
   # Store in _RUNTIME_CONTEXT or pass to supervisor
   ```

6. **Register with hub** (existing flow):
   - Populate `services` array with `{"name": "tei", "port": port}`
   - Call `_register_with_hub(..., services=[...], role="gpu-compute")`

7. **Supervision loop enhancement**:
   - Add TEI health check to supervision loop (every N seconds)
   - If TEI unhealthy: log warning, attempt restart
   - Update `tei_url` in registry heartbeat? (or separate call)

### On `council connect stop`

1. **Stop TEI container** (before Ray):
   ```bash
   docker stop council-tei
   docker rm council-tei
   ```

2. **Deregister from hub**:
   - Existing flow already deregisters (line 1043)
   - Hub will mark node offline, services unavailable

3. **Stop Ray** (existing flow)

### During Supervision Loop

- Check Ray health (existing, every 15 seconds)
- **NEW**: Check TEI health (every 10 seconds if TEI enabled)
  - If unhealthy: attempt restart with backoff
  - Log to `logger.warning()`, do NOT crash supervisor

**Confidence: HIGH** — all components verified to exist

---

## Service Registration Enhancement

### Current Flow (lines 904-908)

```python
registered = _register_with_hub(
    hub_url, api_key, resolved_role, capabilities, councils_served,
    repos=detected_repos,
    ray_node_id=ray_node_id,
)
```

### Enhanced Flow

```python
# After TEI container startup
services = []
if tei_enabled and tei_container_running:
    services.append({
        "name": "tei",
        "port": tei_port,
        "health_endpoint": "/health",
        "model": config.tei_model,
    })

registered = _register_with_hub(
    hub_url, api_key, resolved_role, capabilities, councils_served,
    repos=detected_repos,
    ray_node_id=ray_node_id,
    services=services,  # ← NEW
)
```

### How Hub Uses Service Info

Embeddings provider can look up TEI endpoint:
```python
# In embeddings.py or a new dispatcher
registry = NodeRegistry()
tei_service = registry.get_service_endpoint("tei")
if tei_service:
    tei_url = tei_service["url"]  # e.g., "http://gpu-worker-1:8080"
    # Use for routing
```

**Confidence: HIGH** — confirmed get_service_endpoint() exists and works this way

---

## Config Keys to Add

All to be added to DEFAULT_CONFIG and CONFIG_SCHEMA:

### council.compute.tei_container.* (new section)

```python
"tei_container": {
    "enabled": False,                   # Master toggle
    "image": "ghcr.io/huggingface/text-embeddings-inference:cpu-latest",  # Docker image
    "port": 8080,                       # Container port (on 127.0.0.1)
    "model": "BAAI/bge-base-en-v1.5",  # HF model to load
    "dtype": "float32",                 # Model dtype (float32, float16, bfloat16)
    "gpu_memory_gb": 8,                 # GPU memory limit in GB
    "health_check_interval_seconds": 10, # Supervision loop health check interval
    "startup_timeout_seconds": 60,      # Max wait for container startup
}
```

### council.node.services_by_role.* (new section)

```python
"services_by_role": {
    "gpu-compute": {
        "tei_enabled": True,            # Enable TEI for gpu-compute nodes
        "tei_port": 8080,               # Override port if needed
    },
    "dev-workstation": {
        "tei_enabled": False,           # Don't run TEI on dev machines
    },
    "ci-runner": {
        "tei_enabled": False,
    },
}
```

---

## Risk Assessment

### 1. Port Conflicts

**Risk**: TEI container tries to bind to port already in use

**Mitigation**:
- Check if port is free before starting: `netstat -tuln | grep :8080`
- Use config override (`--tei-port N`) if needed
- Fail with clear error message

**Confidence: HIGH**

### 2. GPU Not Available

**Risk**: `docker run --gpus all` fails if no GPU or docker GPU plugin not installed

**Mitigation**:
- Run `docker run --gpus all --rm ubuntu nvidia-smi` as pre-flight check
- Fall back to CPU image if GPU not available (operator configurable)
- Log warning but continue (TEI still useful on CPU)

**Confidence: HIGH**

### 3. Container Startup Failure

**Risk**: Image pull timeout, model download timeout, OOM on GPU

**Mitigation**:
- Poll health endpoint with 60-second timeout (configurable)
- Inspect container logs on failure: `docker logs council-tei`
- Print helpful error message (download URL, memory requirements)

**Confidence: HIGH**

### 4. Docker Not Installed

**Risk**: `docker` command not found on worker machine

**Mitigation**:
- Check `docker ps` at startup (same as Ray check at line 813)
- Raise ClickException with install instructions
- Allow `--skip-tei` flag to proceed without TEI

**Confidence: HIGH**

### 5. TEI Container Crashes During Supervision

**Risk**: Container exits due to OOM, SIGKILL, GPU error

**Mitigation**:
- Supervision loop detects unhealthy TEI via HTTP probe
- Attempt restart with exponential backoff (same as Ray reconnect)
- Log to `logger.warning()` but don't crash supervisor
- Update heartbeat to reflect TEI unhealthy state

**Confidence: MEDIUM** — depends on heartbeat payload design

### 6. Stale Docker Container on Restart

**Risk**: `docker run --name council-tei` fails if previous container still exists (not fully cleaned up)

**Mitigation**:
- Always run cleanup before start: `docker stop && docker rm`
- Use `--rm` flag to auto-cleanup on stop (best practice)
- Handle "container not found" error gracefully

**Confidence: HIGH**

---

## Existing Patterns to Follow

1. **Error handling**: Use `logger.warning()` for non-fatal errors, raise `ClickException()` for fatal ones
2. **Subprocess pattern**: `subprocess.run(cmd, capture_output=True, text=True)` with status code checks
3. **Config access**: `cfg.get("council", {}).get("compute", {}).get("key", default)`
4. **Best-effort operations**: Deregister/cleanup use try/except, never crash
5. **Role-based policies**: Read `council.node.services_by_role.*` to determine behavior
6. **Supervision loops**: Use exponential backoff with max backoff cap
7. **Health checks**: HTTP probes with timeout and graceful fallback

**Confidence: HIGH** — all patterns verified in codebase
<!-- ID: recommendations -->
## Recommendations

### 1. Adopt Option A: Docker CLI Subprocess Pattern

**Why**: 
- Minimizes dependencies (no `docker` package)
- Consistent with existing Ray process management
- Proven pattern in codebase (lines 857, 1054)
- Simple to test and debug

**Action**: Create new module `src/council_mcp/compute/tei_container.py` with `TEIContainerManager` class implementing:
```python
class TEIContainerManager:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.container_name = "council-tei"
    
    def start(self) -> bool
    def stop(self) -> bool
    def health_check(self) -> bool
    def get_url(self) -> str | None
```

---

### 2. Enhance connect_cmd.py Integration Points

**Before Ray start**:
- Add role-based check for `council.node.services_by_role`
- Determine if TEI should be started for this role

**After Ray connectivity confirmed**:
- Call `TEIContainerManager.start()` if enabled
- Poll health endpoint with timeout
- Catch startup failures and log clearly

**Before hub registration**:
- Build `services` array with TEI entry (if running)
- Pass to `_register_with_hub(..., services=[...])`

**In supervision loop**:
- Add `TEI_health_check_interval` to supervisor
- Poll `/health` endpoint periodically
- Attempt restart with backoff on failure
- Never crash supervisor

**In stop command**:
- Call `TEIContainerManager.stop()` before Ray
- Best-effort cleanup (try/except)

---

### 3. Add Config Keys (6 new keys)

To `DEFAULT_CONFIG` (config/__init__.py):
```python
"council": {
    "compute": {
        # ... existing keys ...
        "tei_container": {
            "enabled": False,
            "image": "ghcr.io/huggingface/text-embeddings-inference:cpu-latest",
            "port": 8080,
            "model": "BAAI/bge-base-en-v1.5",
            "dtype": "float32",
            "gpu_memory_gb": 8,
            "health_check_interval_seconds": 10,
            "startup_timeout_seconds": 60,
        }
    },
    "node": {
        # ... existing keys ...
        "services_by_role": {
            "gpu-compute": {"tei_enabled": True},
            "dev-workstation": {"tei_enabled": False},
            "ci-runner": {"tei_enabled": False},
        }
    }
}
```

To `CONFIG_SCHEMA` (same file):
- 8 new entries for validation/tier/bounds

**Then run**: `council update` to regenerate config defaults in `.council/council.yaml`

---

### 4. Enhance Hub Service Discovery

**embeddings.py** can now dynamically look up TEI:
```python
# In embed_text_async (or new dispatcher)
# Instead of hard-coded tei_url:
tei_service = registry.get_service_endpoint("tei")
if tei_service:
    tei_url = tei_service["url"]
    # Use dynamically discovered endpoint
```

This enables:
- Multiple TEI instances across cluster
- Automatic load balancing
- Graceful fallback if TEI unavailable

---

### 5. Document Docker Requirements

Add to project README:
- Docker installed and running
- Docker GPU plugin (nvidia-docker) for GPU support
- Required Linux kernel modules (nvidia-uvm, etc.)

Pre-flight check in code (same as Ray):
```python
if not _check_docker_installed():
    raise ClickException("Docker is not installed...")
```

---

### 6. Testing Strategy

**Unit tests** (test_tei_container.py):
- Mock `subprocess.run()` to simulate docker commands
- Test startup/stop/health check logic
- Test timeout and error handling

**Integration tests**:
- Spin up real Docker container (if Docker available in test env)
- Test actual startup, health checks, cleanup

**E2E tests** (test_connect_cmd.py):
- Test `council connect start --role gpu-compute` with TEI enabled
- Verify service registration includes TEI entry
- Verify `council connect stop` cleanups TEI

---

### 7. Phased Rollout

**Phase 1** (MVP):
- Implement `TEIContainerManager` class
- Basic start/stop/health check
- Add to connect_cmd start path
- No supervision yet (kill TEI on any Ray reconnect)

**Phase 2**:
- Supervision loop integration
- Exponential backoff restart
- Health checks every N seconds

**Phase 3** (Future):
- Dynamic TEI endpoint discovery in embeddings.py
- Multiple TEI instances across cluster
- Load balancing

---

## Conclusions

### Key Findings

1. **Infrastructure exists**: Service registration, lookup, and role-based policies are already in place. TEI container lifecycle is a **natural extension**, not a new subsystem.

2. **Minimal code changes**: Three main touchpoints:
   - New module: `tei_container.py` (100-150 lines)
   - Enhance: `connect_cmd.py` (30-50 lines)
   - Enhance: `RayWorkerSupervisor` (20-30 lines for health check)

3. **Recommended approach**: Docker CLI subprocess (Option A) — consistent with existing patterns, zero new dependencies.

4. **No breaking changes**: TEI is optional (disabled by default). Existing workflows unaffected.

5. **Clear migration path**: Current users with manual `tei_url` config continue to work. New users get auto-management with `--role gpu-compute`.

### Implementation Effort

- **MEDium complexity** (not simple, not complex)
- Config keys: 1 hour
- `TEIContainerManager`: 2-3 hours
- `connect_cmd` integration: 2-3 hours
- Tests: 3-4 hours
- **Total**: ~12 hours (1.5 days)

### Confidence in Recommendation

**HIGH** — all components verified, no architectural blockers, follows established patterns.

**Recommendation**: Proceed with Option A (Docker CLI) as designed above.
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---