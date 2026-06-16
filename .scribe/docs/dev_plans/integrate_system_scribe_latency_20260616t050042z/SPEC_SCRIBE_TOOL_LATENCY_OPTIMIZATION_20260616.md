---
id: integrate_system_scribe_latency_20260616t050042z-spec-scribe-tool-latency-optimization-20260616
title: 'SPEC: Scribe Tool Latency Optimization Audit'
doc_type: spec
doc_name: SPEC_SCRIBE_TOOL_LATENCY_OPTIMIZATION_20260616
category: engineering
status: scaffolded
version: '0.1'
last_updated: 2026-06-16 05:02:03 UTC
maintained_by: agent-20260616-045803-cb0d3c29
created_by: agent-20260616-045803-cb0d3c29
owners:
- seshat
related_docs: []
tags:
- integrate-system
- performance
- telemetry
- postgres
- set_project
- append_entry
summary: Problem-definition SPEC for integrate-system audit of Scribe MCP tool latency,
  set_project/append_entry performance, local Postgres behavior, and telemetry flow.
canonical_doc_type: spec
edit_trace:
  tool: manage_docs
  created_at: 2026-06-16 05:01:29 UTC
  created_via: create_doc
  last_edited_at: 2026-06-16 05:02:03 UTC
  last_edited_by: agent-20260616-045803-cb0d3c29
  last_action: append
  stage: spec
---

# SPEC: Scribe Tool Latency Optimization Audit

## Problem Statement
Scribe MCP tool calls are sometimes taking unacceptably long, especially `set_project` and `append_entry`. The behavior appears inconsistent across repositories: `set_project` can be fast inside `scribe_mcp`, while similar calls feel slow from `council_mcp`. The operator has moved Scribe storage to a fresh local PostgreSQL installation, so old logical database rows may be absent even though physical project data still exists on disk. The system needs a source-backed audit of what is slow, why it is slow, and whether telemetry is actually flowing well enough to diagnose real runtimes.

## Goals
- Measure current `set_project`, `append_entry`, `read_recent`, `manage_docs`, and related Scribe MCP tool runtimes with phase-level evidence where available.
- Identify root causes for slow paths, including storage backend calls, document scaffolding, project registry work, reminders/advisories, file I/O, MCP wrapper overhead, and cross-repo runtime context selection.
- Explain why `set_project` can be fast in `scribe_mcp` but slow in `council_mcp`, using current source, runtime configuration, and direct telemetry/log evidence.
- Verify whether telemetry data is emitted, stored, queryable, and correlated across Scribe MCP, Council MCP, local Postgres, file-backed Scribe docs, and daemon/runtime logs.
- Produce minimum remediation packages that polish and refine the existing system without inventing replacement subsystems.

## Non-Goals
- No feature expansion beyond performance/telemetry integration and hygiene needed to make existing tool calls observable and fast.
- No replacement files, parallel logging stack, or alternate Scribe project registry.
- No destructive migration of existing physical Scribe data.
- No implementation before research artifacts and Blueprint-owned architecture/task packages exist.
- No broad Council MCP redesign unless research proves the latency boundary lives there and the operator approves the package.

## Constraints
- Use direct `mcp__scribe__*` tools for Scribe state and managed docs.
- Preserve the local PostgreSQL installation and treat the fresh DB state as a diagnostic constraint, not an excuse to drop file-backed data.
- Compare `scribe_mcp` and `council_mcp` behavior without conflating repo-local launch context, storage backend, MCP wrapper, and generated config surfaces.
- Treat Scribe tool responses, phase timing, local daemon logs, and reproducible commands as evidence; prose docs are advisory unless corroborated by runtime/source proof.
- Every specialist must bind project `integrate-system-scribe-latency-20260616T050042Z` and log meaningful progress there.

## Participating Systems
- Scribe MCP tool layer: `set_project`, `append_entry`, `read_recent`, `manage_docs`, diagnostics, and telemetry response payloads.
- Scribe storage layer: local PostgreSQL backend, file-backed docs/progress logs, registry/session state, and any compatibility/fallback cache.
- Scribe runtime/daemon: MCP server startup, runtime context selection, logs, timing emission, and diagnostics.
- Council MCP comparison surface: generated MCP/client configuration, repo context selection, proxy/bridge behavior, and any wrapper latency around Scribe calls.
- Operator-facing telemetry surfaces: tool response `timing`, Council log manager events, Scribe progress logs, doctor/readback tools, and database/queryable telemetry if present.

## Research Questions
1. What exact phases dominate `set_project` in fast and slow cases, and which phases vary by repo/context?
2. What exact phases dominate `append_entry`, including Postgres mirror writes, file writes, reminder handling, metadata normalization, and downstream logging hooks?
3. Does telemetry exist only in tool responses, or is it persisted/queryable after the call completes?
4. Are slow calls caused by fresh Postgres state, missing historical rows, file-system discovery, generated config mismatch, daemon/runtime context, reminder/advisory calculation, or MCP/Council bridge overhead?
5. What minimum code/config/doc remediation packages would reduce wait times and improve auditability while preserving existing contracts?

## Bracket Classification
`STANDARD_BRACKET`.

Rationale: this is a multi-domain optimization/integration audit spanning Scribe MCP runtime, storage, telemetry, and cross-repo Council MCP behavior. It has downstream runtime implications and needs named specialists, but the first wave is diagnostic and can stay below grand-bracket scope unless research reveals launch/release-critical or security-sensitive migration risk.

## Bracket Outline
Wave 1 has four parallel research tracks, capped below the five-agent limit and with disjoint artifact ownership:

1. `scribe-research-analyst` owns `RESEARCH_TOOL_LATENCY_SURFACE_20260616.md`: inventory Scribe MCP tool timing instrumentation, `set_project`/`append_entry` call paths, response timing fields, and current tests/docs around performance.
2. `sia` owns `RESEARCH_STORAGE_POSTGRES_LATENCY_20260616.md`: analyze local PostgreSQL backend, project/session/log writes, fresh-DB behavior, file-backed doc interactions, and likely slow storage operations.
3. `scribe-bug-hunter` owns `RESEARCH_RUNTIME_TELEMETRY_FLOW_20260616.md`: gather runtime/daemon evidence for telemetry emission, persistence, logs, and reproducible latency measurement methods; identify observed failures as bug candidates but do not fix yet.
4. `maat` owns `RESEARCH_COUNCIL_CONTEXT_COMPARISON_20260616.md`: compare Scribe behavior when invoked from `scribe_mcp` versus `council_mcp`, focusing on generated config, MCP registration, runtime context selection, and wrapper/proxy paths.

Synthesis checkpoint: Seshat verifies the four artifacts, checks Scribe logs for completion, and writes an integration map before routing Blueprint. If the evidence lowers risk, the workflow may step down to a narrower direct implementation package. If it exposes release-critical generated-surface or cross-repo migration risk, the bracket may step up with operator approval.

## Initial Observations
- Local `set_project` in this workstream completed in `436.403 ms`, with phase timing included in the tool response.
- Largest observed phases in that call were `prepare_context=131.633 ms` and `ensure_documents=120.831 ms`; this is useful baseline evidence, not a root-cause conclusion.
- `append_entry` for the startup log returned `db_mirror.status=ok`, so Postgres mirroring is active for at least this write path.

## Acceptance Criteria
- Research artifacts cite exact source/runtime evidence and distinguish current measured behavior from hypotheses.
- The integration map identifies source-of-truth ownership for timing emission, persistence, storage writes, runtime context, and cross-repo invocation.
- Blueprint produces bounded task packages with verification commands and telemetry proof requirements before any code changes.
- Implementation, if approved by gates, improves or guards measured wait time and leaves telemetry queryable enough to audit real runtimes later.
