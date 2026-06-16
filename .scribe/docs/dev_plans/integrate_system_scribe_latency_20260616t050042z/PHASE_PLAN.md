---
id: integrate_system_scribe_latency_20260616t050042z-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 integrate-system-scribe-latency-20260616T050042Z"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: ready
version: '0.1'
last_updated: 2026-06-16 08:25:38 UTC
maintained_by: agent-20260616-081538-6fd3f13d
created_by: agent-20260616-052258-6aee159b
owners:
- ArchitectAgent
related_docs: []
tags:
- phase-plan
- latency
- scribe
- hooks
- planning
summary: Ordered packages P1-P7 for Scribe telemetry, hook attribution, diagnostics,
  and optional optimization.
canonical_doc_type: phase_plan
edit_trace:
  tool: manage_docs
  created_at: 2026-06-16 05:30:15 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-06-16 08:25:38 UTC
  last_edited_by: agent-20260616-081538-6fd3f13d
  last_action: replace_text
  stage: architecture
---

# ⚙️ Phase Plan — integrate-system-scribe-latency-20260616T050042Z
**Author:** ArchitectAgent
**Version:** Draft v0.2
**Status:** Ready
**Last Updated:** 2026-06-16 05:29 UTC

> Ordered implementation roadmap for telemetry truth first, optimization second.

---
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Packages | Repo Owner | Depends On | Exit Gate | Confidence |
|-------|----------|------------|------------|-----------|------------|
| Phase 0 | Architecture complete; Witness + Arbiter review | `scribe_mcp` workstream docs | Verified Wave 1 research | Witness/Arbiter pass or explicit operator waiver | 0.95 |
| Phase 1 | P1 Generic telemetry persistence and P3 hook source-authority gate | `scribe_mcp` + `council_mcp` | Phase 0 | Package-specific Crucible PASS for both packages before any dependents | 0.90 |
| Phase 2 | P2 append_entry sub-phase timing and P4 hook timing/fail-open telemetry | `scribe_mcp` + `council_mcp` | P1 PASS; P3 PASS for P4 | Package-specific Crucible PASS | 0.86 |
| Phase 3 | P5 controlled same-server root comparison and P6 fresh-DB reconciliation diagnostic | `scribe_mcp` | P1 PASS; P4 PASS for P5 labels | Package-specific Crucible PASS | 0.84 |
| Phase 4 | P7 smarter same-binding `set_project` reuse plus Council guidance/hook alignment | `scribe_mcp` primary + `council_mcp` source-authority follow-up | P2, P5, P6 PASS and operator acceptance delta | Crucible PASS for the Scribe package plus verified Council source-template/hook uplift/readback plan | 0.82 |

Parallelism rules:
- P1 and P3 may run in parallel because they touch different repos and different files.
- P2 may run after P1 while P3 is still under review.
- P4 may not start until P3 has its own Crucible PASS.
- P5 may not start until P4 can label hook-included versus hook-excluded measurements.
- P7 is now a bounded follow-up package: the `scribe_mcp` fast path can land first, but operator acceptance is not fully closed until the Council guidance/hook uplift is source-authored and read back from templates.

---
## Phase 0 — Pre-Implementation Review Gate
<!-- ID: phase_0 -->

Recommendation: run both Witness and Arbiter before Forge.

Witness checklist:
- Confirm package ownership boundaries are explicit for `scribe_mcp` versus `council_mcp`.
- Confirm no package depends on editing generated outputs directly.
- Confirm every package has a probe or test command and a readback surface.
- Confirm P6 is diagnostic-only and cannot mutate historical physical data.

Arbiter checklist:
- Confirm P1 and P3 are the first legal implementation packages.
- Confirm P4 is blocked on P3 and P5 is blocked on P4.
- Confirm P7 remains bounded: same-binding fast path only, no new binding subsystem, no public contract break, and Council guidance/hook follow-up stays source-authority-only.
- Confirm no package silently widens into migration, redesign, or cross-repo generated-output churn.

---
## Phase 1 — Ordered Task Packages
<!-- ID: phase_1 -->

### Task Package P1 — Generic durable tool telemetry persistence

**Scope:** Persist real tool-call duration and correlation metadata at the existing generic Scribe tool boundary.

**Repo Owner:** `scribe_mcp`

**Files to Modify:**
- `src/scribe_mcp/utils/response.py` — extend the formatter call contract only if needed to carry a measured timing context.
- `src/scribe_mcp/utils/formatters/dispatcher.py` — replace `duration_ms=None` with real measured duration and correlation metadata for JSONL and SQL persistence.
- `src/scribe_mcp/utils/tool_logger.py` — accept additive correlation fields if current JSONL schema needs them.
- `src/scribe_mcp/log_intelligence.py` or existing diagnostics consumer — report persisted timing or explicit missing-data state.
- `tests/test_doctor_telemetry.py`, `tests/test_log_intelligence.py`, `tests/test_tools.py` — verify durable readback and backward compatibility.

**Files to Create:**
- None by default. Reuse existing diagnostics surfaces unless implementation proves a small focused test file is cleaner.

**Dependencies:**
- Requires Phase 0 review gate complete.
- Crucible validation is required before P2, P4, P5, P6, or P7 may route.

**Specifications:**
1. Capture one real monotonic duration per logical tool call at the narrowest existing boundary that already owns tool logging.
2. Persist `duration_ms`, `correlation_id`, and `measurement_scope` to both TOOL_LOG and Postgres `tool_calls`.
3. Preserve existing response formatting behavior; additive metadata is allowed, breaking output shape changes are not.
4. Make `logs analyze` explicitly report `missing_generic_tool_duration` when the project lacks compatible persisted timing.

**Patterns to Follow:**
- `src/scribe_mcp/runtime_timing_envelope.py` for shared timing shape.
- `src/scribe_mcp/utils/formatters/dispatcher.py:207-245` for the current logging hub.

**Verification:**
- `uv run pytest tests/test_doctor_telemetry.py tests/test_log_intelligence.py tests/test_tools.py`
- Probe: run `set_project`, `append_entry`, `read_recent`, and `manage_docs quality_check` through `mcp__scribe__*` and verify durable `duration_ms` readback in TOOL_LOG and `tool_calls`.
- Probe: verify missing-data status is explicit when compatible persisted timing is absent.

**Out of Scope:**
- Tool-specific phase timing beyond additive correlation fields.
- Hook measurement.
- Any optimization of tool behavior.

### Task Package P2 — `append_entry` response and sub-phase timing

**Scope:** Add additive `append_entry` timing that decomposes file, DB, reminder, state, and formatting cost while preserving the `db_mirror` contract.

**Repo Owner:** `scribe_mcp`

**Files to Modify:**
- `src/scribe_mcp/tools/append_entry.py` — instrument single-entry and bulk paths.
- `src/scribe_mcp/runtime_timing_envelope.py` — reuse or lightly extend the generic phase envelope shape.
- `tests/test_tools.py` and a focused append-entry test file if needed — verify additive response fields and failure behavior.

**Files to Create:**
- None required.

**Dependencies:**
- Requires P1 Crucible PASS.
- Crucible validation is required before P7 may route.

**Specifications:**
1. Time file WAL/fsync separately from DB fetch/upsert/insert work.
2. Preserve file-first success semantics when DB mirror fails.
3. Record reminder and response-formatting time explicitly.
4. Persist additive phase metadata where later readback can inspect it.

**Patterns to Follow:**
- `src/scribe_mcp/tools/append_entry.py:639-715` single-entry flow.
- `src/scribe_mcp/tools/append_entry.py:2250-2288` bulk-path result assembly.

**Verification:**
- `uv run pytest tests/test_tools.py`
- Probe: `mcp__scribe__append_entry` success path shows non-empty timing phases and unchanged `db_mirror.status=ok`.
- Probe: simulated mirror failure still returns file success and phase timing with `db_mirror.status=error`.

**Out of Scope:**
- Generic tool persistence plumbing already owned by P1.
- Any change to durability order.

### Task Package P3 — Council hook source-authority and install gate

**Scope:** Define and implement the source-parity/readback gate for hook work so downstream generated hook copies are never treated as authoritative.

**Repo Owner:** `council_mcp`

**Files to Modify:**
- `src/council_mcp/hook_specs.py` — parity/readback helpers if required.
- `src/council_mcp/compiler/phases/hooks.py` — dry-run/readback reporting only if current output is insufficient.
- `src/council_mcp/codex_toml.py` — preserve operator-authored hook entries if the readback report needs stronger guarantees.
- `tests/test_hook_specs.py`, `tests/test_runtime_hook_generation.py` — prove parity and preservation rules.

**Files to Create:**
- None unless a focused hook readback helper is needed inside existing package boundaries.

**Dependencies:**
- Requires Phase 0 review gate complete.
- Crucible validation is required before P4 may route.

**Specifications:**
1. Enumerate authoritative hook sources and generated destinations in machine-readable readback.
2. Classify stale downstream generated hook files as non-authoritative until regenerated.
3. Preserve operator-authored overrides and config entries unless an explicit force/replace path is chosen.
4. Keep `council update --dry-run` as the rollout proof surface; do not hand-edit generated files.

**Patterns to Follow:**
- `src/council_mcp/hook_specs.py:146-195` for canonical source seeding.
- `src/council_mcp/hook_specs.py:345-473` for runtime source resolution and Codex plan building.

**Verification:**
- `uv run pytest tests/test_hook_specs.py tests/test_runtime_hook_generation.py`
- `council update --dry-run`
- Readback: stale generated copies under downstream repos are flagged, not trusted.

**Out of Scope:**
- Measuring hook latency itself.
- Actual generated-output rollout without operator approval.

### Task Package P4 — Hook timing, fail-open telemetry, and timeout hardening

**Scope:** Instrument hook-side timing separately from Scribe MCP timing and harden timeout/fail-open behavior where measured hook waits dominate perceived latency.

**Repo Owner:** `council_mcp`

**Files to Modify:**
- `src/council_mcp/templates/claude/runtime_hooks/post_tool.py` — add phase timing and stop persisting fake durations.
- `src/council_mcp/templates/claude/runtime_hooks/session_start.py` — time startup/session lanes.
- `src/council_mcp/hooks/client.py` — measured logging, timeout control, and no misleading `duration_ms=0.0` behavior.
- `tests/test_runtime_hooks_binding.py`, `tests/test_hooks/test_hook_client.py` — prove fail-open and timeout cases.

**Files to Create:**
- None required.

**Dependencies:**
- Requires P1 PASS and P3 Crucible PASS.
- Crucible validation is required before P5 may route.

**Specifications:**
1. Measure local self-heal writes separately from HTTP bind/get/log calls.
2. Distinguish `hook_only` duration from `tool_only` duration.
3. Preserve local binding truth on daemon failure, 401, timeout, missing `httpx`, or malformed responses.
4. Evaluate short fixed timeouts for hook lanes that currently inherit the default request timeout.

**Patterns to Follow:**
- `src/council_mcp/templates/claude/runtime_hooks/post_tool.py:273-423`
- `src/council_mcp/hooks/client.py:82-221`

**Verification:**
- `uv run pytest tests/test_runtime_hooks_binding.py tests/test_hooks/test_hook_client.py`
- Probe: `mcp__scribe__set_project` followed by hook readback shows separate hook phase timing and no fake `0.0` duration.
- Probe: daemon-down and 401 scenarios remain fail-open with local cache self-heal intact.

**Out of Scope:**
- Council runtime redesign.
- Changes to Scribe MCP semantics.

### Task Package P5 — Controlled same-server root comparison

**Scope:** Produce a sanctioned same-server probe that compares `scribe_mcp` root versus `council_mcp` root and labels whether hooks are included.

**Repo Owner:** `scribe_mcp`

**Files to Modify:**
- Existing diagnostics/probe surface in `src/scribe_mcp/tools` or `src/scribe_mcp/cli` chosen during implementation.
- Tests for the chosen readback/reporting surface.

**Files to Create:**
- At most one focused probe/report helper inside an existing diagnostics module if no current home is suitable.

**Dependencies:**
- Requires P1 PASS.
- Requires P4 Crucible PASS so hook inclusion can be labeled accurately.
- Crucible validation is required before P7 may use P5 results as optimization evidence.

**Specifications:**
1. Hold the same Scribe server constant and vary only the requested root.
2. Capture structured Scribe timing, host wall time, and hook inclusion label for each case.
3. Emit a structured report that identifies whether the latency delta is inside Scribe phases or outside them.

**Patterns to Follow:**
- Existing `set_project` structured response timing surface.
- Existing diagnostics conventions rather than one-off shell notes.

**Verification:**
- Probe: structured `set_project` against `scribe_mcp` root and `council_mcp` root from the same server instance.
- Readback: report rows include `hook_excluded`, `hook_included`, or `hook_state_unknown`.
- Crucible review: confirm the report is attribution-only and does not smuggle in config changes.

**Out of Scope:**
- Any direct hook implementation.
- Any generated config change.

### Task Package P6 — Fresh Postgres / physical docs reconciliation diagnostic

**Scope:** Add a read-only report that compares physical Scribe artifacts to logical Postgres rows without auto-ingesting history.

**Repo Owner:** `scribe_mcp`

**Files to Modify:**
- Existing diagnostics/readback surface in `src/scribe_mcp/tools` or another existing diagnostics module.
- Tests covering read-only classification behavior.

**Files to Create:**
- None unless one focused diagnostics helper is required.

**Dependencies:**
- Requires P1 PASS.
- Crucible validation is required before P7 may claim fresh-DB drift explains optimization candidates.

**Specifications:**
1. Compare project configs to `scribe_projects`.
2. Compare core plan docs to `dev_plans` rows.
3. Compare physical progress logs to `scribe_entries` counts.
4. Compare tool-log artifacts to `tool_calls` counts.
5. Classify mismatches without mutating anything.

**Patterns to Follow:**
- Existing Scribe diagnostics style and read-only probe behavior.
- Storage read APIs rather than raw destructive repair logic.

**Verification:**
- `uv run pytest` for the targeted diagnostics test file(s).
- Probe: report surfaces `consistent`, `physical_only`, `logical_only`, or `missing_logical_rows`.
- Probe: repeated runs show no side effects on files or DB counts.

**Out of Scope:**
- Recovery or ingestion.
- Automatic repair during `set_project`.

### Task Package P7 — Smarter same-binding `set_project` reuse

**Scope:** Add a cheap, behavior-preserving fast path when the same live agent/session is already bound to the same canonical project and canonical repo root, and expose the reuse outcome clearly enough for Council guidance/hooks to stop periodic rebinding.

**Repo Owner:** `scribe_mcp` primary implementation; `council_mcp` source-authority follow-up for generated guidance/hooks.

**Files to Modify:**
- `src/scribe_mcp/tools/set_project.py` — add the same-binding confirmation and no-write reuse path.
- `src/scribe_mcp/state/agent_manager.py` only if a small public helper is needed to validate or describe live-session binding state without rewriting it.
- `src/scribe_mcp/state/manager.py` only if a small no-write helper is needed to reuse cached session/project payloads.
- `tests/test_set_project.py` — add same-binding call-count, fallback, and response-shape coverage.

**Files to Create:**
- None required.

**Dependencies:**
- Requires P2, P5, and P6 Crucible PASS.
- Uses existing execution-context, router-cache, state-manager, and storage authorities; no new binding subsystem is allowed.
- Council follow-up after the Scribe patch: `/home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/templates/claude/CLAUDE.md.j2`, `/home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/templates/claude/runtime_hooks/session_start.py`, and `/home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/templates/claude/runtime_hooks/post_tool.py` must be updated in their own repo before the operator acceptance is fully closed.

**Specifications:**
1. Keep required-input validation, write-barrier/root authorization, and canonical name/root resolution intact.
2. Confirm same-binding using existing authorities only: verified execution context plus router cached project first, then persisted agent/session binding plus `fetch_project(..., repo_root=resolved_root)` or cached state payload if the local cache is empty.
3. If same-binding cannot be proven because the session is missing, expired, mismatched, aliased differently, rooted differently, or in sentinel/base-project/fallback recovery, fall back to the existing full bind path unchanged.
4. On confirmed same-binding, skip persistent and filesystem side effects: project upsert, dev-plan upserts, doc bootstrap checks, ProjectRegistry touch/update, agent-project/session-project/global-mirror writes, recent-project writes, and any version bump caused only by rewriting the same binding.
5. It is acceptable to refresh in-memory cache or response metadata when that avoids persistent writes; it is not acceptable to create a parallel binding registry.
6. Preserve normal success responses while adding explicit reuse metadata for structured/compact consumers, for example `side_effects.binding_reused` and a reuse reason/phase label that downstream hooks can inspect.
7. Council uplift follow-up must mirror the bind-once rule in startup guidance and make hook `handle_set_project` treat a server-reported reuse result as a no-op instead of another fresh bind write.

**Patterns to Follow:**
- Existing `set_project` timing envelope and `side_effects` response contract.
- Existing storage `fetch_project(...)` identity path instead of new lookup tables.
- Fake-backend call-count testing for state/storage write reductions.

**Verification:**
- `uv run pytest tests/test_set_project.py`
- Unit test: second same-session/same-agent/same-name/same-root `set_project(format="structured")` does not bump agent-project version or invoke project/session/recent/dev-plan writes on the fake backend.
- Unit test: different root, alias mismatch, missing/expired session proof, or execution-context failure falls back to the existing full bind path.
- Before/after probe: back-to-back live `set_project(format="structured")` on the same session reports explicit reuse metadata on the second call and materially lower warm-path phase time.
- Council readback gate: verify source-authority updates in `AGENTS.md.j2`/`CLAUDE.md.j2`/`runtime_hooks/session_start.py`/`runtime_hooks/post_tool.py` before declaring the acceptance requirement complete.

**Out of Scope:**
- Cold-start schema/bootstrap work.
- Readiness-cache or unrelated latency work.
- Historical data ingestion or repair.
- Generated-output hand edits in `council_mcp`.

---
## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Status | Evidence / Gate |
|-----------|--------|-----------------|
| Architecture contract written | Complete | `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md` updated in this project |
| Research-to-Blueprint gate | Complete | Verified Wave 1 research plus hook addendum and direct source spot checks |
| Pre-implementation review | Complete | `REVIEW_REPORT_phase_0_review_2026-06-16_0545.md` passed Witness + Arbiter at 96/100; P1 and P3 legal first-wave packages |
| P1 telemetry foundation | Complete | P1 package-specific Crucible revalidation PASS 97/100; required telemetry tests passed and readback proved non-null `duration_ms`, matching `correlation_id`, and `measurement_scope=tool_only`. |
| P2 append_entry timing | Complete | P2 revalidation PASS 96/100; append_entry phase timing persisted after final `total_ms` calculation; focused, P2, and `tests/test_tools.py` lanes passed. |
| P3 hook authority gate | Complete | Council hook source-authority package implemented and validated before dependent hook/root attribution work. |
| P4 hook timing and fail-open telemetry | Complete | P4 package-specific Crucible PASS 95/100; hook-only timing labels, fail-open behavior, and timeout lane validated. |
| P5 root attribution diagnostics | Complete | P5 post-identity-fix Crucible PASS 100/100; same-server probe emitted structured root rows, hook labels, and inside-Scribe attribution. |
| P6 reconciliation diagnostic | Complete | P6 revalidation PASS 96/100; physical/logical reconciliation remains read-only and classifies non-zero drift honestly. |
| Probe measurement surface repair | Complete | `src/scribe_mcp/scripts/scribe_probe.py` now serializes MCP/Pydantic/non-dict result objects recursively, binds a local request execution context for direct probe runs, and supports `--json-output`; `uv run pytest tests/test_scribe_probe.py` passed 14/14; four-tool probe for `set_project`, `append_entry`, `read_recent`, and `manage_docs quality_check` completed with aggregate JSON `ok: true`. |
| P7 same-binding reuse acceptance delta | Server-side Complete / Council Follow-up Open | `scribe_mcp` now has a no-write same-binding reuse path with explicit `binding_reused` metadata. Proof: `uv run pytest tests/test_set_project.py -q` passed 26/26; direct edited-runtime double-call probe measured first_total_ms=302.311, second_total_ms=42.168, second_binding_reused=true, and only one project/agent binding write. Council source-authority guidance/hook uplift remains a separate repo follow-up because this package did not edit `council_mcp`. |

---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->

Rollback / defer contract:
- If P1 fails to make generic tool duration durable and queryable, stop the rest of the performance lane and fix measurement first.
- If P3 exposes generated-output drift that cannot be resolved without wider rollout work, freeze hook packages and keep the Scribe-only packages separate.
- If the `scribe_mcp` fast path lands before the Council uplift, treat the work as partial completion only: server-side reuse is allowed to ship first, but operator acceptance stays open until source-authority guidance/hook surfaces stop reinforcing redundant rebinding.
- If P6 shows large fresh-DB drift, treat that as a separate operator decision; do not auto-repair as part of the latency lane.
- Any package that needs a broader redesign than described here must route back through Blueprint instead of quietly expanding scope.
