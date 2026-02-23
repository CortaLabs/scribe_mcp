---
id: council_unified_platform-review-report-pre-implementation-2026-02-18-0231
title: 'Review Report: Pre Implementation Stage'
doc_type: REVIEW_REPORT_pre_implementation_2026-02-18_0231
doc_name: REVIEW_REPORT_pre_implementation_2026-02-18_0231
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-18 02:35:41 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Review Report: Pre Implementation Stage

**Review Date:** 2026-02-18 02:31:08 UTC
**Reviewer:** agent-20260218-014329-b23e769c
**Project:** council_unified_platform
**Stage:** pre_implementation
**Review Type:** Post-Implementation

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Decision:** REJECTED — REQUIRES REVISION

**Confidence Level:** High (0.95)

**Grade: 68/100 — FAIL** (threshold: 93%)

**Key Findings:**
1. Phase 4 (Local LLM Serving) is entirely out of scope — operator runs own LLM via llamacpp. LLM references contaminate 5+ sections.
2. `council connect start` is fundamentally broken (fire-and-forget, no supervision, no reconnection) — architecture adds features on broken foundations.
3. Syncthing sync model is flat/naive — no per-node policies, no council-aware sync, no automation.
4. `register_council_sync()` and ALL registry SELECT queries omit `api_endpoint` column — federation would silently fail.
5. `memory_federated` receive handler is a no-op — architecture spec doesn't account for existing push implementation.
6. Command naming chaos: `council connect join` vs `council connect start` vs `council join` — three names for one command.

**Remediation required (7 items) before re-review.**
<!-- ID: phase_review_results -->
## Detailed Review Findings

### SECTION 1: CONFIRMED OPERATOR COMPLAINTS

#### COMPLAINT 1: LLM Serving is OUT OF SCOPE — CONFIRMED (Critical)

Phase 4 (Local LLM Serving) occupies 2 task packages (P4.1, P4.2), ~70 lines of Phase Plan, 4 checklist items. LLM contamination found in:
- Architecture Guide section 4.3: Ollama/vLLM with VRAM budget (lines 371-393)
- Architecture Guide section 4.2: `llm_generate: "ollama"` in service_routes config
- Architecture Guide section 4.9: `council connect serve ollama`
- System diagram lines 126-129: "Local LLM (vLLM/Ollama) :11434"
- Open questions table: vLLM vs Ollama entry

**Action:** Strip Phase 4 entirely. Remove all LLM references from other sections.

#### COMPLAINT 2: Architecture Built on Uneven Research — CONFIRMED (Major)

Research quality is actually reasonable (all 0.85-0.96 confidence). The problem is that the architecture IGNORED several research findings:
1. Research correctly identified `register_council_sync()` lacks `api_endpoint` — but architecture missed that SELECT queries also omit it
2. Distributed agents research flagged git worktree as critical gap — architecture ignores it entirely
3. Federation research found `memory_federated` handler is a no-op — architecture spec for the fix doesn't account for existing push implementation in `tools/federation.py`

#### COMPLAINT 3: Syncthing Needs Intelligent Per-Node Sync — CONFIRMED (Major)

Architecture section 4.4 uses flat sync model. Gaps:
1. No per-node sync policy — one `sync_paths` applied globally
2. No role-based filtering (GPU node doesn't need web pages)
3. No reverse sync (hub→worker for config updates)
4. No Syncthing automation in `council connect` flow
5. Phase 5 is "Operational" (manual setup) with no code for automated management

#### COMPLAINT 4: `council connect start` Must Be Canonical AND It's Broken — CONFIRMED (Critical)

Root cause analysis of `connect_cmd.py` (526 lines):
- `ray start` is fire-and-forget — spawns raylet daemon and returns
- No supervision loop, no reconnection, no health checking
- PID detection via `pgrep -f raylet` is fragile
- No heartbeat — silent disconnection goes undetected
- Background mode has no daemon supervision

Architecture proposes `council connect join` but does NOT fix these core bugs. Heartbeat thread would falsely report health if raylet dies. Need: supervision loop checking `ray.is_initialized()`, automatic reconnection, heartbeat that verifies Ray connectivity.

Architecture correctly extends existing command (no COMMANDMENT #0.5 violation) but builds features on broken foundations.

---

### SECTION 2: NEW ISSUES FOUND

#### ISSUE 5: Registry SELECT Queries Omit `api_endpoint` (Blocker)

**File:** `src/council_mcp/storage/registry.py` lines 94-120
All `list_councils_sync()`, `get_council_by_name_sync()`, `get_council_by_id_sync()` SELECT specific columns and OMIT `api_endpoint`. While `tools/federation.py:_load_target_council_transport()` does query it directly, the main registry functions would never return it to the web UI. Phase 3 would produce "api_endpoint always null in UI" bugs.

#### ISSUE 6: `memory_federated` Handler vs Existing Push Implementation (Major)

`web/routes/federation.py` lines 490-497: handler returns success without storing. Architecture P3.2 spec says use bare `insert_persona_memory()`. But `tools/federation.py` already has `_copy_memory_to_council()` with deduplication, text hashing, and source tracking. The receive handler must match or delegate to this existing implementation.

#### ISSUE 7: Command Naming Chaos (Medium)

Three names appear across documents:
- `council connect join` (Architecture Guide, Phase Plan)
- `council connect start` (existing command)
- `council join` (Checklist line 44)

**Action:** Pick ONE canonical name. Recommend keeping `council connect start` and enhancing it.

#### ISSUE 8: Phase 2→Phase 0 Hidden Dependency (Medium)

P2.2 `_resolve_service()` imports `NodeRegistry.get_service_endpoint()` from Phase 0. If P2.2 runs before P0.1 is complete, import fails. Dependency is stated in phase overview but not enforced in task package scope markers.

#### ISSUE 9: CONFIG_SCHEMA Coverage Gap (Medium)

Many new config keys added to DEFAULT_CONFIG but only P2.2 mentions CONFIG_SCHEMA entries. Keys from P0.1 (`node.*`), P1.1 (`tei_*`), P5.2 (`sync.*`), P6.4 (`agent_dispatch.*`) would be invisible in web UI config editor.

#### ISSUE 10: Node-Council Data Model Ambiguity (Major)

`council.platform_nodes` is global — a node is a machine, not a council. One machine can host multiple councils. But `council-isolation` rule requires all endpoints to filter by `council_id`. The checklist says "Council isolation applied" for node endpoints, but there is no `council_id` column on `platform_nodes`. Data model contradiction unresolved.

---

### SECTION 3: ACCURACY AUDIT

| Section | Score | Key Issue |
|---------|-------|-----------|
| 4.1 Node Registry | 85% | Correct code shape, missed `connect start` bugs |
| 4.2 Capability Dispatch | 70% | LLM contamination, Phase 0 dependency |
| 4.3 GPU Compute | 60% | Ollama out of scope, VRAM budget contaminated |
| 4.4 File Sync | 65% | Syncthing choice good, design naive |
| 4.5 Federation | 80% | Gap list accurate, missed SELECT queries |
| 4.6 Distributed Agents | 75% | Ray Actor sound, ignores worktree gap |
| 4.7 Health | 85% | Clean, well-scoped |
| 4.8 Security | 90% | Appropriate for trusted mesh |
| 4.9 Extensibility | 70% | UX appealing, built on broken foundations |

**Overall Architecture Accuracy: 75%**

---

### SECTION 4: SCOPE CORRECTIONS

**Must Remove:** Phase 4 (LLM), all Ollama/vLLM/llm_generate references, LLM VRAM analysis, LLM open questions.

**Must Add:** P0.0 fix `connect start` supervision; `api_endpoint` in registry SELECTs; per-node sync policies; git worktree acknowledgment; node-council data model.

**Must Rewrite:** Phase 5 (sync with policies); P0.3 (fix bugs before features); P3.2 (align with existing federation push); command naming.

---

### SECTION 5: REVISED PHASE RECOMMENDATIONS

| Phase | Goal | Change |
|-------|------|--------|
| Phase 0 | Node Registry | Add P0.0: Fix connect start supervision. Clarify node-council model. |
| Phase 1 | TEI Embeddings | Keep as-is (clean). |
| Phase 2 | Compute Dispatch | Remove LLM refs from service_routes. |
| Phase 3 | Federation | Add api_endpoint to ALL SELECT queries. Align memory handler. |
| ~~Phase 4~~ | ~~LLM Serving~~ | **REMOVE** |
| Phase 4 (was 5) | File Sync | Rewrite with per-node policies. |
| Phase 5 (was 6) | Distributed Agents | Acknowledge worktree gap. |
| Phase 6 (was 7) | Dashboard | Keep, renumber. |

**Total: 7 phases (was 8), ~16 task packages (was 19).**
<!-- ID: detailed_analysis -->
## Detailed Analysis: `connect_cmd.py` Deep Dive

### What `council connect start` Does Today (526 lines)

Three subcommands: `start`, `stop`, `status`.

**`start` flow:**
1. Checks Ray installed (`import ray`)
2. Checks no existing PID via `.council/ray-worker.pid`
3. Resolves head address: CLI override → `council.compute.ray_address` → `council.deployment.hub_tailscale_ip`
4. ICMP ping to head node
5. Pre-flight version check via Ray Dashboard API `/api/version`
6. Runs `ray start --address={address}` as subprocess
7. Background: captures output, finds PID via `pgrep -f raylet`, writes PID file
8. Foreground: runs `ray monitor` (log tailing, blocks on Ctrl+C)

**Root causes of connection dropping:**
1. `ray start` is fire-and-forget — the CLI command finishes after spawning the raylet daemon
2. No supervision — if raylet crashes, PID file may reference dead process, `is_pid_alive()` only checks if PID exists in /proc
3. No reconnection — network blip or head restart kills connection permanently
4. No heartbeat — worker does not report its status to any central system
5. `pgrep -f raylet` returns first match — may grab wrong PID if multiple Ray instances exist
6. Background mode has no daemon loop — it's literally "fire subprocess and exit"

**What the architecture should specify for the fix:**
1. After `ray start`, spawn a persistent supervision thread
2. Thread periodically calls `ray.is_initialized()` (every 10-15s)
3. On failure: `ray stop && ray start` with exponential backoff (1s, 2s, 4s, max 60s)
4. Hub heartbeat should include Ray connectivity status (not just "I'm alive")
5. `--foreground` should block on supervision loop, not `ray monitor`
6. Graceful shutdown handler (SIGTERM/SIGINT) should deregister from hub before stopping

### Source File Cross-Reference Summary

| File | Architecture Claim | Reality | Match? |
|------|-------------------|---------|--------|
| `dispatcher.py` | "add `_resolve_service()`, `_dispatch_service()`" | Class has `dispatch()`, `_dispatch_ray()`, `_dispatch_local()`. No service concept exists. Extension point is clear. | Accurate |
| `tasks.py` | "add `register_task()` API" | Has `TASK_REGISTRY` dict and `get_remote_tasks()`. No dynamic registration. Extension point is clear. | Accurate |
| `embeddings.py` | "add TEI HTTP dispatch" | Has `embed_text_async()` routing ray_enabled → dispatcher or local. TEI path would be a clean addition before the existing dispatch. | Accurate |
| `registry.py` | "add `api_endpoint` param to `register_council_sync()`" | Function does NOT accept or set `api_endpoint`. SELECT queries also omit it. | Partially — missed SELECT gap |
| `federation.py` (routes) | "implement `memory_federated` handler" | Handler exists but returns success without storing. Full HMAC validation infrastructure exists. | Accurate |
| `federation.py` (tools) | Not referenced in architecture | Has `federate_memory()` with deduplication, hashing, source tracking. `_copy_memory_to_council()` is the pattern to follow. | Missed entirely |
| `worker_pool.py` | "Add remote dispatch path" | Complex 800+ line file with `WorkerEntry`, UDS protocol, event construction. Adding remote path is feasible but non-trivial. | Accurate |
| `config/__init__.py` | "Add new config keys" | Has `compute` section with 4 keys. Has CONFIG_SCHEMA for web UI. Dual registration pattern clear. | Accurate |
| `connect_cmd.py` | "enhance `council connect start`" | Fire-and-forget design. No supervision. No heartbeat. Must fix before adding features. | **Critical gap** |
<!-- ID: recommendations -->
## Recommendations — Mandatory Remediation

The following 7 items MUST be addressed before re-review. Architecture must be revised by Blueprint.

### Remediation 1: Strip Phase 4 (LLM Serving) — CRITICAL
Remove Phase 4 entirely. Remove all Ollama/vLLM/llm_generate references from Architecture Guide sections 4.2, 4.3, 4.9, system diagram, open questions, service_routes config defaults.

### Remediation 2: Fix `council connect start` Supervision — CRITICAL
Add task package P0.0 (before P0.1): Fix the fire-and-forget design in `connect_cmd.py`. Add supervision loop, reconnection logic, and heartbeat that verifies Ray connectivity. This is prerequisite to all features that depend on stable node connections.

### Remediation 3: Rewrite Syncthing Section with Per-Node Policies — MAJOR
Architecture section 4.4 and Phase 5 must include:
- Per-node sync policy config (which repos/paths go to which node types)
- Role-based filtering (GPU compute nodes get different sync sets than web-serving nodes)
- `council connect start` integration for automatic Syncthing folder configuration
- Bidirectional sync consideration (hub→worker for config updates)

### Remediation 4: Fix Registry SELECT Queries — BLOCKER
Add `api_endpoint` to the column list in ALL SELECT queries in `registry.py`: `list_councils_sync()`, `get_council_by_name_sync()`, `get_council_by_id_sync()`. Add this to Phase 3 task package P3.1.

### Remediation 5: Align Memory Handler with Existing Push — MAJOR
P3.2 specification must reference `tools/federation.py:_copy_memory_to_council()` pattern. The receive handler should either call this existing function or implement matching logic (deduplication via text hash, source_council_id tracking, proper embedding).

### Remediation 6: Resolve Command Naming — MEDIUM
Pick ONE canonical name for the node join command. Recommendation: keep `council connect start` and add registration/heartbeat capabilities to it. Remove all references to `council connect join` and `council join`.

### Remediation 7: Clarify Node-Council Data Model — MAJOR
Document whether `platform_nodes` is global or council-scoped. If global (recommended — a machine is not a council), add explicit exception to council-isolation rule documentation and remove "Council isolation applied" from P0.2 checklist. If council-scoped, add `council_id` column to `platform_nodes`.

---

## Disposition

**Grade: 68/100 — FAIL**
**Status: Requires Revision**
**Re-review: After all 7 remediation items are addressed**
**Reviewer: Arbiter (session d59294ec-6c45-4d66-9e38-c333dab87f72)**
**Date: 2026-02-18**
<!-- ID: agent_performance_assessment -->
## Agent Performance Assessment

| Agent | Role | Grade | Comments |
|-------|------|-------|----------|
| Research Analyst | Research | [Score]% | [Comments] |
| Architect | Architecture | [Score]% | [Comments] |
| Coder | Implementation | N/A | [Not yet evaluated] |
| Reviewer | Review | [Score]% | [Self-assessment] |

---

<!-- ID: compliance_verification -->
## Compliance Verification

**Scribe Protocol Compliance:** [COMPLIANT/PARTIALLY_COMPLIANT/NON_COMPLIANT]

- [ ] Minimum logging requirements met
- [ ] Documentation standards followed
- [ ] Quality gate procedures completed
- [ ] Cross-project validation performed

---

<!-- ID: final_decision -->
## Final Decision

**[APPROVED/REJECTED/REQUIRES_REVISION]**

**Rationale:** [Detailed justification for decision]

**Conditions for Proceeding:**
- [ ] [Condition 1]
- [ ] [Condition 2]

**Expected Timeline:** [Timeline estimate]

---

*This review report is part of the quality assurance process for council_unified_platform.*
