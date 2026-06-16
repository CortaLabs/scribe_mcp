---
id: integrate_system_scribe_latency_20260616t050042z-integration-map-scribe-tool-latency-20260616
title: 'Integration Map: Scribe Tool Latency Optimization'
doc_type: synthesis
doc_name: INTEGRATION_MAP_SCRIBE_TOOL_LATENCY_20260616
category: engineering
status: scaffolded
version: '0.1'
last_updated: 2026-06-16 05:13:07 UTC
maintained_by: agent-20260616-045803-cb0d3c29
created_by: agent-20260616-045803-cb0d3c29
owners:
- seshat
related_docs: []
tags:
- integrate-system
- synthesis
- performance
- telemetry
- postgres
- council-context
summary: Wave 1 synthesis and integration map for Scribe MCP tool latency optimization
  audit.
canonical_doc_type: synthesis
edit_trace:
  tool: manage_docs
  created_at: 2026-06-16 05:12:33 UTC
  created_via: create_doc
  last_edited_at: 2026-06-16 05:13:07 UTC
  last_edited_by: agent-20260616-045803-cb0d3c29
  last_action: append
  stage: research_synthesis
---

# Integration Map: Scribe Tool Latency Optimization

## Synthesis Status
Wave 1 research is verified and ready for Blueprint planning.

Verified artifacts:
- `RESEARCH_TOOL_LATENCY_SURFACE_20260616.md` - quality pass, zero blockers.
- `RESEARCH_STORAGE_POSTGRES_LATENCY_20260616.md` - quality pass, zero blockers.
- `RESEARCH_RUNTIME_TELEMETRY_FLOW_20260616.md` - quality pass, zero blockers.
- `RESEARCH_COUNCIL_CONTEXT_COMPARISON_20260616.md` - quality pass, zero blockers.

Coordinator synthesis result: proceed to Blueprint. The bracket can step down from `STANDARD_BRACKET` to a bounded implementation plan after Blueprint, because Wave 1 found concrete seams and no need for another broad research wave before architecture.

## Integration Map

| Concern | Source Of Truth | Consumers | Broken Or Drifting Seam | Evidence | Minimum Remediation Direction |
|---|---|---|---|---|---|
| `set_project` phase timing | `src/scribe_mcp/tools/set_project.py` timing block and `runtime_timing_envelope.py` budget schema | MCP callers, doctor/log diagnostics, orchestration gates | Timing exists and is rich, but slow perceived cases need controlled root comparison and sub-phase confirmation | Tool research lines 41-69; storage research lines 42-56; council comparison lines 69-89 | Keep existing response timing contract, add or verify finer sub-phase evidence only where needed |
| `append_entry` tool duration | `append_entry.py`, `tool_logger.py`, formatter dispatcher, Postgres `tool_calls` storage | Agents, progress audit trail, telemetry analysis, future performance gates | Append persists log entries, but not durable tool runtime durations; response has `db_mirror` but no shared timing envelope | Tool research lines 41-64 and 82-88; telemetry research lines 48-85 and 88-98 | Add wrapper/tool timing that records real `duration_ms`, plus an append_entry timing envelope or equivalent sub-phase fields |
| File-backed audit durability | `.scribe/docs/dev_plans/*/PROGRESS_LOG.md`, `utils/files.py` WAL/fsync path | Scribe logs, managed docs, recovery workflows | File-first append is intentionally durable, but DB mirror wait is response-blocking and not separately timed | Storage research lines 57-66 and 82-99 | Preserve WAL/fsync; instrument file append versus DB mirror; do not skip durability blindly |
| Postgres logical history after fresh DB | Postgres tables plus physical `.scribe/docs` files | Query entries, project registry, dev-plan registry, telemetry metrics | Physical docs can exist while DB rows are missing, causing cold reconstruction, undercounted history, and first-call write amplification | Storage research lines 68-78 and 108-114 | Add read-only reconciliation diagnostics; avoid implicit historical ingestion inside `set_project` |
| Generic tool telemetry persistence | `.scribe/logs/TOOL_LOG.jsonl`, `scribe.tool_calls`, storage read APIs | `scribe logs analyze`, future MCP/CLI runtime audit, operators | Observed TOOL_LOG entries omit `duration_ms`; Postgres `scribe.tool_calls` had zero recent rows; dispatcher passes `duration_ms=None` | Telemetry research lines 11-29 and 88-98 | Fix generic dispatcher timing and storage persistence before optimizing blind |
| `logs analyze` timing envelope | `log_intelligence.py` plus progress-log-compatible PERF entries | CLI diagnostics, runtime efficiency reports | Analyzer can build an envelope, but active project returned unknown metrics because compatible timing entries were absent | Telemetry research lines 24-27 and 88-98 | Feed analyzer from persisted tool timing or make missing-data status explicit |
| Scribe versus Council perceived latency | Generated MCP configs, Scribe runtime root, `set_project(root=...)`, Codex post-tool hooks | Operators working in `scribe_mcp` and `council_mcp` | Same Scribe server/env is registered, so differences likely come from requested repo root or hook/context overhead, not a different binary | Council comparison lines 11-22 and 40-65 | Run controlled same-server root comparison and hook-overhead measurement before changing Council/Scribe config |
| Codex post-tool hook overhead | `.codex/hooks/post_tool.py` generated hook | Codex sessions and Scribe binding cache | Hook work occurs after `mcp__scribe__set_project`, may add perceived latency outside Scribe tool phase timing | Council comparison lines 91-96 and 107-124 | Instrument hook timing or fail-open/timeout behavior if Blueprint proves it is slow |
| Council topology drift | `.council/council.yaml` and Council MCP defaults | Council MCP runtime/proxy tools | `council_mcp` has local `allow_legacy_transport_fallback: true`; `scribe_mcp` and defaults are false | Council comparison lines 97-103 and 107-124 | Verify intent before config change; never hand-edit generated client configs |

## Cross-Track Conclusions

1. The first local Scribe `set_project` call in this workstream was not the pathological case: observed coordinator baseline was `436.403 ms`, then warm rebind was `172.67 ms`. Wave 1 measured another `set_project` at `0.3400s`. The slow Council-side case still needs a controlled root-specific measurement.
2. `set_project` already has the best timing surface. The likely fix is not to invent a new timing stack, but to preserve and extend the existing `runtime-efficiency-budget.v1` shape where it is missing.
3. `append_entry` is the sharper production bug for auditability. It can be user-visible slow because file WAL/fsync and DB mirror are response-blocking, but the current durable telemetry cannot tell us how much time each part takes.
4. The biggest telemetry flaw is durable queryability. Immediate tool responses and transcript wall time are useful, but after the call completes the system cannot reliably answer: which Scribe tool was slow, how slow, for which project/agent/session, and which phase dominated?
5. The local Postgres switch explains some cold behavior: old physical docs remain, but logical DB history is fresh. This causes missing rows and reconstruction costs without implying the physical Scribe audit trail was lost.
6. `council_mcp` is likely not slow because it points at a different Scribe server. The inspected generated configs point both repos at the same `scribe-server`, `SCRIBE_ROOT`, and Postgres backend. The likely delta is requested project root, repo-local Scribe config, post-tool hook overhead, or Council runtime context interleaving.

## Bug And Risk Register

| ID | Type | Status | Description | Planning Impact |
|---|---|---|---|---|
| `BUG-2026-06-16-0001` | Performance/telemetry | Opened by Track C | Generic Scribe tool runtime telemetry is not durably queryable; `duration_ms` is missing or null in intended sinks | Blueprint should include a first implementation package to persist wrapper timing with correlation keys |
| `LAT-RISK-001` | Measurement gap | Open | No controlled same-server timing comparison for `set_project` rooted at `scribe_mcp` versus `council_mcp` | Blueprint should define a sanctioned probe before config/runtime changes |
| `LAT-RISK-002` | Hook overhead uncertainty | Open | Codex post-tool hook may add perceived latency outside Scribe response timing | Blueprint should include hook timing readback or bounded instrumentation |
| `LAT-RISK-003` | Fresh DB consistency | Open | Physical docs and fresh Postgres logical rows can diverge until explicitly reconciled | Blueprint should include read-only reconciliation diagnostics, not automatic migration |

## Recommended Blueprint Packages

Blueprint should produce task packages in this order:

1. Telemetry persistence package.
   - Add real `duration_ms` and correlation metadata at the generic tool boundary.
   - Persist it to repo/project tool logs and Postgres `tool_calls` consistently.
   - Verify via a readback query after tool completion.

2. Append-entry timing package.
   - Add timing sub-phases for file append/WAL, DB project fetch/upsert, DB entry insert, metrics insert, state/registry updates, reminder lookup, and formatter work.
   - Preserve existing `db_mirror` contract.
   - Verify `append_entry` can still return success when the file append succeeds and DB mirror failure is reported appropriately.

3. Controlled root-comparison package.
   - Measure same Scribe server with `root=/home/austin/projects/MCP_SPINE/scribe_mcp` and `root=/home/austin/projects/MCP_SPINE/council_mcp` using structured output.
   - Capture Scribe phase timing plus host wall time.
   - Determine whether the delta is inside Scribe phases or outside in Codex hooks.

4. Hook-overhead telemetry package.
   - Add or expose timing around generated `post_tool.py` binding/logging steps, especially Scribe `set_project` handling.
   - Keep generated-output source authority intact; source/template path must be identified before edits.

5. Fresh-DB reconciliation diagnostic package.
   - Add a read-only health/report path comparing physical Scribe project docs/configs with Postgres project/dev-plan/entry/tool-call rows.
   - Do not ingest or mutate historical logs by default.

6. Optional set-project write-reduction package.
   - Only after measurement proves it matters, collapse duplicate recent/session writes or batch core dev-plan upserts.
   - Require fake-backend call-count tests and live phase-timing proof.

## Verification Requirements For Blueprint

Blueprint must require these proof surfaces before implementation is declared ready:
- Unit tests for timing payload schema and backwards-compatible response shape.
- Integration or local probe proving `duration_ms` is non-null and queryable after a Scribe MCP tool call completes.
- A before/after measurement table for `set_project`, `append_entry`, `read_recent`, and `manage_docs quality_check` in a controlled local environment.
- A same-server root comparison for `scribe_mcp` and `council_mcp`, with explicit note whether Codex hook time is included.
- Scribe `quality_check` on all managed docs and checklist proof after implementation.

## Gate Decision

Research Wave 1 is complete and verified. The next legal stage is Blueprint architecture/planning. No Forge/Coder implementation should begin until Blueprint writes `ARCHITECTURE_GUIDE`, `PHASE_PLAN`, `CHECKLIST`, and bounded task packages, followed by the appropriate review gate.
