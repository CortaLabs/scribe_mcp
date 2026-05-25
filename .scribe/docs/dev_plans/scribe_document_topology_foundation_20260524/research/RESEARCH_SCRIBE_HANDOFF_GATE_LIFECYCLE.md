---
id: scribe_document_topology_foundation_20260524-research-scribe-handoff-gate-lifecycle
title: "\U0001F52C Research Scribe Handoff Gate Lifecycle \u2014 scribe_document_topology_foundation_20260524"
doc_type: RESEARCH_SCRIBE_HANDOFF_GATE_LIFECYCLE
doc_name: RESEARCH_SCRIBE_HANDOFF_GATE_LIFECYCLE
category: engineering
status: complete
version: '0.1'
last_updated: 2026-05-25 03:45:24 UTC
maintained_by: ArchitectAgent
created_by: agent-20260525-033353-f93a8ca4
owners: []
related_docs: []
tags: []
summary: Research on hard managed-document handoff and clock-out gates grounded in
  current set_project, quality_check, readiness, and agent session behavior.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 03:45:24 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-05-25 03:45:24 UTC
  last_edited_by: agent-20260525-033353-f93a8ca4
  last_action: frontmatter_update
---
# 🔬 Research Scribe Handoff Gate Lifecycle — scribe_document_topology_foundation_20260524
**Author:** ArchitectAgent
**Version:** v0.1
**Status:** Complete
**Last Updated:** 2026-05-25 03:42 UTC

> Research on hard managed-document handoff and clock-out gates grounded in current `set_project`, `quality_check`, readiness, and agent session behavior.

---
## Executive Summary
<!-- ID: executive_summary -->
Scribe already has the core primitives needed for a hard managed-document handoff gate. `set_project` performs the effective clock-in by resolving repo authority, ensuring an agent session, setting the agent's current project, and persisting an authoritative session key into project state (`src/scribe_mcp/tools/set_project.py:559-930`, `src/scribe_mcp/tools/agent_project_utils.py:95-197`). `manage_docs(action='quality_check')` is already the canonical blocker path, and its warning payloads already include the fields needed for enforcement and recovery (`src/scribe_mcp/doc_management/runtime.py:870-1088`, `src/scribe_mcp/doc_management/quality/results.py:10-50`, `src/scribe_mcp/readiness.py:48-150`).

**Primary Objective:** Determine how to block clean handoff, clock-out, or completion claims when an agent's owned managed docs still contain scaffold placeholders, readiness blockers, or failed-write residue.

**Key Takeaways:**
- The best v1 does not need a second session system. It should extend existing `set_project`, `manage_docs`, readiness, and Scribe agent-session teardown seams.
- Scaffold residue is already modeled as blocking `SCF_*` warnings for placeholder brackets, template prose, empty findings, unfilled appendix, TODO-only readiness claims, lifecycle mismatch, and frontmatter mismatch (`src/scribe_mcp/doc_management/scaffold_quality.py:26-50,342-401`).
- The current write pipeline already computes `scaffold_quality_warnings` after every managed-doc mutation, which is the natural continuous-feedback seam (`src/scribe_mcp/doc_management/manager.py:984-1004`).
- Scribe session teardown currently clears bindings without consulting managed-doc quality, so a hard clock-out gate is not implemented yet (`src/scribe_mcp/state/agent_manager.py:233-303`).
- Generic literal failed-write residue is still a real gap. The current code has a changelog-only escaped-newline blocker, but not a document-wide failed-write residue rule (`src/scribe_mcp/doc_management/quality/rules/changelog.py:13-65`).

---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ArchitectAgent

**Investigation Window:** 2026-05-24 — 2026-05-25

**Focus Areas:**
- Current project/session binding and clock-in behavior in `set_project`.
- Agent attribution and ownership metadata in managed-doc frontmatter.
- `quality_check` and readiness blocker semantics.
- Existing session-end or project-detach boundaries inside Scribe and adjacent Council tooling.
- Minimal, backward-compatible enforcement options for hard handoff blocking.

**Dependencies & Constraints:**
- This lane is research/design only; no source code changes were made.
- The proposal must extend the current `quality_check` and readiness lifecycle; no `quality_check_v2` or parallel validator is allowed.
- The proposal must not invent a new session subsystem. Existing Scribe agent sessions and external Council sessions are the only valid lifecycle boundaries.
- Research is grounded in current source reality first, then Wave 1 synthesis and prior research artifacts.

---
## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** `set_project` already acts as the natural clock-in surface. It resolves repo authority, ensures docs/config paths, upserts the project, ensures or resumes an agent session, resolves an authoritative session key, and writes agent-scoped project state.
- **Evidence:** `src/scribe_mcp/tools/set_project.py:559-930`, `src/scribe_mcp/tools/agent_project_utils.py:95-197`, `src/scribe_mcp/state/agent_manager.py:60-186`.
- **Confidence:** High

### Finding 2
- **Summary:** `manage_docs(action='quality_check')` is already the single canonical proof path. It resolves the target doc from registry or canonical research paths, runs `collect_managed_doc_quality_warnings`, normalizes warnings, computes `readiness_blocker_count`, and returns blocking warnings plus suggested repairs.
- **Evidence:** `src/scribe_mcp/doc_management/runtime.py:870-1088`, `src/scribe_mcp/doc_management/quality/results.py:10-50`, `src/scribe_mcp/readiness.py:48-150`, `RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md:39-83`.
- **Confidence:** High

### Finding 3
- **Summary:** The current blocker taxonomy already makes scaffold residue a hard failure for most of the operator's doctrine. Placeholder brackets, template prose, empty findings, unfilled appendix, TODO-only readiness claims, log-template-only readiness claims, frontmatter mismatch, and lifecycle mismatch are all blocking today.
- **Evidence:** `src/scribe_mcp/doc_management/scaffold_quality.py:26-50,330-401`, `src/scribe_mcp/doc_management/quality/rules/scaffold.py:8-85`.
- **Confidence:** High

### Finding 4
- **Summary:** Managed-doc mutation already performs a post-write quality pass. `apply_doc_change` includes `scaffold_quality_warnings` in the write result, and `rehome_doc` already records checkpoint-level readiness and quality summaries. That means Scribe already has post-mutation and post-relocation seams where handoff enforcement can attach without inventing a parallel evaluator.
- **Evidence:** `src/scribe_mcp/doc_management/manager.py:984-1004`, `src/scribe_mcp/doc_management/runtime.py:1288-1439`.
- **Confidence:** High

### Finding 5
- **Summary:** Current session teardown does not enforce document cleanliness. `AgentContextManager.end_session()` expires the session, clears session-project bindings, clears agent-project bindings when owned by that session, logs `session_ended`, and cleans runtime cache, but it does not inspect managed-doc quality or readiness blockers first.
- **Evidence:** `src/scribe_mcp/state/agent_manager.py:233-303`, `src/scribe_mcp/storage/base.py:324-345`.
- **Confidence:** High

### Finding 6
- **Summary:** The existing frontmatter ownership model is last-editor oriented, not shared-ownership oriented. `created_by` is immutable after create, `maintained_by` is runtime-owned and rewritten to the acting agent, and `edit_trace` stores the latest actor/action plus optional `run_id`, `stage`, `session_id`, and `work_item_id`. That is enough for v1 if ownership resolution is explicit, but it is not enough to infer multi-agent ownership by itself.
- **Evidence:** `src/scribe_mcp/doc_management/manager.py:3061-3119,3238-3387`, `src/scribe_mcp/tools/manage_docs_validation.py:187-238`, `RESEARCH_SCRIBE_METADATA_SURFACE.md:76-143`.
- **Confidence:** High

### Finding 7
- **Summary:** Generic literal failed-write residue is not fully covered yet. There is a blocking changelog-specific rule for serialized escaped-newline sludge, but there is no document-wide failed-write residue family for arbitrary managed docs.
- **Evidence:** `src/scribe_mcp/doc_management/quality/rules/changelog.py:13-65`, `src/scribe_mcp/doc_management/scaffold_quality.py:26-50`, repo search for `literal failed-write`/`failed-write residue` returned no broader quality rule.
- **Confidence:** High

### Additional Notes
- `SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md:77-116` already pointed to `set_project` as the natural clock-in surface and explicitly asked Wave 2 to decide whether handoff blocking belongs in `manage_docs`, session-close hooks, or both.
- The repo source does not expose Council `open_session`/`end_session` implementations; those live outside `scribe_mcp` in the broader tool surface. Blueprint should therefore treat Council session close as an integration boundary, not a local source-owned seam.

---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- `set_project` already materializes the project/session binding contract: root authorization, docs_dir resolution, project upsert, `ensure_agent_session`, `set_current_project`, and authoritative session resolution.
- `quality_check` already returns the exact ingredients a handoff gate needs: `quality_status`, `warnings`, `readiness_blockers`, `readiness_blocker_count`, and `next_actions`.
- `apply_doc_change` already computes post-write `scaffold_quality_warnings`, which supports continuous feedback during authoring rather than only at the end.
- `AgentContextManager.end_session()` is a clean teardown seam, but it currently has no document-readiness branch.

**System Interactions:**
- `set_project` is the right clock-in surface for both standalone MCP callers and orchestrated agents because it already normalizes project identity and session scope.
- `manage_docs` is the right enforcement surface for status transitions and explicit handoff/completion claims because it already owns document mutation, frontmatter attribution, and `quality_check`.
- Scribe internal agent sessions and external Council sessions are adjacent but not identical. Scribe can enforce local agent-session teardown in-repo; Council close behavior should call into a Scribe preflight rather than fork a second lifecycle contract.

**Proposed Gate Surfaces:**
- `set_project` clock-in:
  - Do not block on initial bind.
  - Record/return a richer `clock_in` summary derived from existing project/session data: `agent`, `project`, `authoritative_session_id`, `docs_dir`, and any currently owned managed docs with active blocking warnings.
  - If blockers already exist, return them as recovery signals, not as a bind failure.
- `manage_docs` status/handoff gate:
  - Add a shared pre-handoff helper that uses the same warning collector and summary path as `quality_check`.
  - Run it when a mutation attempts a readiness claim such as `status_update`/`frontmatter_update` to `ready`, `done`, `complete`, or equivalent.
  - Also expose it for an explicit handoff/claim-complete action or finalization helper if Blueprint wants one, but it must still use the existing quality contract.
- Final append_entry / handoff protocol:
  - Require a final structured append entry when an agent claims handoff or completion.
  - On success, log `agent`, `project`, `owned_docs_checked`, `quality_status`, `readiness_blocker_count=0`, and the exact proof surface used.
  - On failure, log a blocked handoff event with the failure contract below before returning the blocker response.
- `end_session` / clock-out integration boundary:
  - For Scribe-owned agent-session teardown, add the same preflight before `AgentContextManager.end_session()` clears bindings.
  - For external Council `end_session`, do not duplicate session state in `scribe_mcp`; instead require the caller/wrapper to invoke the same Scribe preflight first and refuse clean clock-out when Scribe reports blockers.

**Failure Logging Contract:**
- Required fields:
  - `agent`
  - `project`
  - `session_id` or `authoritative_session_id` when available
  - `operation` (`status_update`, `frontmatter_update`, `handoff_claim`, `scribe_end_session`, `council_end_session_preflight`)
  - `docs` as a list of objects with `doc_name`, `path`, `created_by`, `maintained_by`, `owners`, `warning_codes`, `blocker_codes`, `blocker_count`, `quality_status`, `suggested_repairs`
  - `total_blocker_count`
  - `warning_counts_by_code`
  - `repair_summary`
- Behavior:
  - Write a Scribe append entry before returning the blocked response.
  - Keep the payload additive and reuse existing warning structures wherever possible so downstream review tools do not need a second parser.

**Ownership Model For Multi-Agent Docs:**
- Keep current runtime-owned fields exactly as they are:
  - `created_by` = creator, immutable after create.
  - `maintained_by` = last mutating agent.
  - `edit_trace` = last actor/action/session/run/work item provenance.
- Use an ownership precedence model for handoff gating:
  1. If `owners` explicitly contains the active agent or active agent role, the doc is in scope for that agent's handoff gate.
  2. Else if `maintained_by` equals the active agent, the doc is in scope.
  3. Else if the doc was created in the current session/work item and has not been reassigned, `created_by` is a fallback scope hint.
- This stays within the current metadata system and avoids inventing a separate ownership registry.
- Shared docs should be blocked for any agent explicitly listed in `owners` until the blocker is repaired or the owner set changes.

**Backward Compatibility Risks:**
- Some callers may currently rely on `status_update` or session end succeeding even when docs are still scaffolded. Enforcing a hard blocker changes behavior and must be deliberate.
- Initial `create` for research/special docs produces scaffold content by design. Gating creation itself would be wrong; the gate must attach only to readiness claims or handoff/clock-out attempts.
- Some execution paths still fall back to compatibility/global mirrors when there is no runtime context (`src/scribe_mcp/tools/set_project.py:900-921`). Hard teardown enforcement must tolerate missing authoritative session IDs.
- `maintained_by` alone is not enough for shared ownership, so a naive "last editor owns everything" rule would misclassify docs in multi-agent waves.
- External Council session tooling is outside this repo, so a fully automatic operator-visible clock-out block requires integration work across the boundary.

**Minimal Enforceable V1:**
- Add one shared preflight function that evaluates owned managed docs through the existing `collect_managed_doc_quality_warnings` plus `summarize_quality_warnings` path.
- Treat existing blocking `SCF_*` warnings as hard blockers for readiness claims and handoff/clock-out attempts.
- Add one additive generic failed-write residue code to the scaffold family so the operator's doctrine is fully covered beyond changelog-only sludge.
- Enforce the preflight in two places only:
  - `manage_docs` readiness-claim mutations.
  - Scribe `AgentContextManager.end_session()` or a thin Scribe-owned teardown wrapper.
- Expose the same preflight result to any external Council clock-out wrapper rather than building a separate session validator.

---
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Define a shared handoff-preflight helper in Scribe that returns the same warning payload shape as `quality_check`, plus ownership-scoped doc lists.
- Gate `status_update` and `frontmatter_update` when they attempt readiness/completion states and the preflight returns blocking warnings.
- Add one generic blocking code for literal failed-write residue in the scaffold-quality family.
- Add a Scribe append-entry contract for blocked handoff attempts using the failure fields listed above.
- Add a narrow Scribe session-close preflight before binding teardown, and document the external Council wrapper requirement instead of creating duplicate session state.

### Blueprint-Ready Tests
- Unit test: `set_project` still succeeds while returning clock-in context even if existing owned docs have blockers.
- Unit test: `manage_docs` readiness claim on a doc with placeholder brackets returns a blocked response and logs the blocker payload.
- Unit test: repairing the same doc and retrying the readiness claim succeeds with zero blockers.
- Unit test: multi-agent ownership precedence uses `owners` first, `maintained_by` second, and `created_by` only as fallback.
- Unit test: generic failed-write residue is detected for a non-changelog managed doc.
- Integration test: Scribe session teardown refuses clean clock-out when the active agent still owns a managed doc with blocking warnings.
- Integration test: explicit external-style clock-out preflight returns the same blocker payload as the local Scribe session gate.

### Long-Term Opportunities
- Surface a small `handoff_readiness` block in `set_project` and `project_health` so agents see ownership-scoped blockers earlier in the workstream.
- Add richer repair batching for "fix all owned docs with SCF blockers, then retry handoff" while still using the same warning contract.
- If operator ergonomics require it later, add a dedicated managed-doc completion helper, but keep it as a thin wrapper around the same shared preflight and append-entry logic.

---
## Appendix
<!-- ID: appendix -->
- **Primary References:**
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/SPEC.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_METADATA_SURFACE.md`
- **Source Evidence:**
  - `src/scribe_mcp/tools/set_project.py`
  - `src/scribe_mcp/tools/agent_project_utils.py`
  - `src/scribe_mcp/doc_management/runtime.py`
  - `src/scribe_mcp/doc_management/manager.py`
  - `src/scribe_mcp/doc_management/scaffold_quality.py`
  - `src/scribe_mcp/doc_management/quality/rules/scaffold.py`
  - `src/scribe_mcp/doc_management/quality/rules/changelog.py`
  - `src/scribe_mcp/readiness.py`
  - `src/scribe_mcp/state/agent_manager.py`
- **Attachments:** None
