---
id: scribe_sentinel_concurrency_v1-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_sentinel_concurrency_v1"
doc_type: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-03'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_sentinel_concurrency_v1
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-02 04:17:01 UTC

> Architecture guide for scribe_sentinel_concurrency_v1.

---
## 1. Problem Statement
- **Context:** Implement repo-bound Sentinel Mode with concurrency-safe session isolation and audited reads in the Scribe MCP server.
- **Goals:**
  - Enforce mode exclusivity (sentinel vs project) with hard-fail gating.
  - Provide daily, repo-bound sentinel logs (MD + append-safe JSONL).
  - Add a `read_file` tool that logs read provenance (path + sha256 + agent identity).
  - Prevent cross-project context leakage under concurrent sessions.
- **Non-Goals:**
  - Sentinel writes into dev_plan project docs (tags only in Phase 1–2).
  - Sentinel writes into dev_plan project docs (tags only in Phase 1–2).
- **Success Metrics:**
  - Required tests pass (mode gating, path enforcement, session isolation, read logging, append safety).
  - Audit report cites current state with file/line evidence before implementation.
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - ExecutionContext required on every tool call at router boundary (repo_root, mode, execution_id, agent_identity, intent, timestamp_utc, affected_dev_projects; sentinel_day derived in sentinel mode). [Audit A,B]
  - Missing/invalid ExecutionContext = hard-fail with explicit error response. [Audit B]
  - Execution/session identity has a single authoritative source at router boundary; no fallback to global state. [Audit B]
  - Sentinel logging writes only under `.scribe/sentinel/YYYY-MM-DD/` (MD + JSONL). [Audit C]
  - `read_file` logs read provenance in sentinel mode (JSONL required; MD optional). [Audit E]
  - Session-scoped context prevents cross-agent leakage; project mode uses ordered resolution. [Audit A]
  - `current_project` remains for project mode fallback only; forbidden in sentinel mode with hard error. [Audit A]
  - Agents can re-connect to old projects via fingerprint (agent_identity + session_id + repo_root), session-scoped lookup preferred. [Audit B]
  - `query_entries` can search sentinel logs by time, execution_id, agent identity, intent, dev_project tags, bug/security IDs, and file paths. [Audit D]
  - Doc registry keys are canonical, case-insensitive, and aliasable; errors list known doc keys. [Audit E]
- **Non-Functional Requirements:**
  - Concurrency-safe append semantics for JSON logs; MD remains single-line under lock.
  - Deterministic path validation (hard-fail on scope mismatch).
  - Backwards-compatible project-mode behavior.
- **Assumptions:**
  - Repo root is set via `set_project` with absolute path.
  - MCP runtime must provide a per-session transport_session_id (or explicit session_id); router hard-fails if missing.
- **Risks & Mitigations:**
  - **Risk:** Missing session id → hard-fail at router; clients must supply transport_session_id or session_id. [Audit B]
  - **Risk:** Concurrent append corruption → append-only JSONL + file locks; bounded retry. [Audit C]
  - **Risk:** Mode confusion → router tool gating with clear hard-fail errors. [Audit A,C]
  - **Risk:** Mode confusion → router tool gating with clear hard-fail errors. [Audit A,C]
<!-- ID: architecture_overview -->
- **Solution Summary:** Introduce ExecutionContext, session-scoped state, and sentinel logging to make multi-agent work safe and auditable.
- **Component Breakdown:**
  - **ExecutionContext Validator:** Validates required fields and enforces mode constraints.
  - **Session Context Store:** Keeps per-session project/sentinel context (no global leakage).
  - **Mode Router:** Exposes only the toolset for the active mode; hard-fails on mismatches.
  - **Sentinel Logger:** Writes daily MD + JSONL logs; supports bug/security schemas.
  - **read_file Tool:** Reads repo files and logs provenance (sha256, agent identity).
  - **query_entries Extension:** Adds sentinel log search by time/filters.
- **Data Flow:** MCP call → context validation → mode router → tool execution → log append.
  - MCP runtime must provide a per-session transport_session_id (or explicit session_id); router hard-fails if missing.
- **Risks & Mitigations:**
  - **Risk:** Missing session id → hard-fail at router; clients must supply transport_session_id or session_id. [Audit B]
  - Router validates required fields and injects derived fields before any tool logic. [Audit B]
  - Hard-fail if missing/invalid; no silent fallback. [Audit B]
- **Session Identity Source (Final)**
  - Router generates UUIDv4 session_id per connection and owns it. [Audit B]
  - MCP transport identity may be recorded as transport_session_id only; never replaces router session_id. [Audit B]
- **`current_project` Quarantine (Revision Plan #2)**
  - Project mode resolution order: explicit ExecutionContext project → session-scoped active project → global current_project fallback. [Audit A]
  - Sentinel mode: current_project is ignored; any fallback attempt is a hard error logged as scope_violation. [Audit A]
  - Legacy compatibility preserved by keeping current_project intact for project mode only. [Audit A]
- **Mode Gating (Router Boundary)**
  - Sentinel mode exposes exactly: append_event, open_bug, open_security, link_fix, read_file, query_entries(sentinel). [Audit C,E]
  - Project tools hard-fail when mode=sentinel; sentinel tools hard-fail when mode=project. [Audit A,C]
  - Any new sentinel tool requires a new revision plan. [Audit C]
- **Sentinel Write Scope**
  - Allowed writes only under `.scribe/sentinel/YYYY-MM-DD/`; violations hard-fail and emit scope_violation event. [Audit C]
- **read_file Tool (Spec Addendum, Binding)**
  - Availability: must be available in sentinel and project modes; behavior identical across modes, logging targets differ. [Audit E]
  - No auto-truncation: never implicitly truncates, clips, or token-limits content. [Audit E]
  - Mandatory scan phase (all reads): absolute_path, repo_relative_path, byte_size, line_count, sha256, newline_type, encoding, estimated_chunk_count. [Audit E]
  - Scan must be streaming and memory-bounded; no full-file load into memory or LLM context. [Audit E]
  - Deterministic chunking model with chunk_index, line/byte boundaries; stable across runs. [Audit E]
  - Supported modes: scan_only, chunk, line_range, page, full_stream, search (literal/regex). [Audit E]
  - Large files must be supported via scan + chunk + stream; warnings allowed but behavior must remain correct. [Audit E]
  - Path enforcement: default allow repo_root; absolute paths only if allow-listed; denylist .env, .git/, .scribe/registry/, ~/.ssh, /etc, /proc, /sys. [Audit E]
  - Violations hard-fail and emit scope_violation event. [Audit E]
  - Provenance logging for every read/scan/chunk: absolute_path, repo_relative_path, sha256, byte_size, line_count, read_mode, range refs, execution_id, agent_identity, timestamp_utc. [Audit E]
  - Logging order: JSONL first, then MD line when applicable. [Audit C,E]
- **Concurrency Guarantees**
  - JSONL append is atomic under per-file lock; bounded retry then fail-fast with error event. [Audit C]
  - MD log is single-line, locked, and written after JSONL for the same event. [Audit C]
- **Bug/Security Evidence Rules**
  - Case cannot close without root_cause + fix_link + landing_status >= verified. [Audit C]
- **query_entries Sentinel Extension**
  - Adds search_scope=sentinel and document_types=sentinel_log with filters (day range, timestamp range, execution_id, agent_identity.instance_id, intent, case_id, affected_dev_projects, path, event_type). [Audit D]
  - Output: structured JSON + optional human summary lines. [Audit D]
- **Stop Gates**
  - Phase 2 complete only when ARCHITECTURE_GUIDE has zero OPEN items and PROGRESS_LOG records spec lock. [Audit A–E]
  - No Phase 3 work while any Phase 2 OPEN item exists; checklist must show zero OPEN before approval. [Audit A–E]
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/
  .scribe/
    docs/dev_plans/scribe_sentinel_concurrency_v1/
      ARCHITECTURE_GUIDE.md
      PHASE_PLAN.md
      CHECKLIST.md
      PROGRESS_LOG.md
      AUDIT_REPORT.md
    sentinel/YYYY-MM-DD/
      SENTINEL_LOG.md
      sentinel.jsonl
      bug.jsonl
      security.jsonl
      executions/exec-<execution_id>.json
```
> Update this tree when new sentinel artifacts are added.
<!-- ID: data_storage -->
- **Datastores:** filesystem logs (MD + JSONL), Scribe registry/state (SQLite).
- **Indexes & Performance:** JSONL enables streaming scans; optional in-memory filters for query_entries.
- **Migrations:** Log schema changes via versioned fields; keep backward-compatible readers.
<!-- ID: testing_strategy -->
- **Unit Tests:** ExecutionContext validation, path validation, mode gating.
- **Integration Tests:** Sentinel log append (MD + JSONL), `read_file` provenance logging.
- **Concurrency Tests:** Simulated concurrent appends + session isolation to prevent cross-project writes.
- **Regression Tests:** `query_entries` sentinel search filters.
- **Observability:** Errors and constraints logged via progress/bug/security logs.
<!-- ID: deployment_operations -->
- **Environments:** Local dev + CI.
- **Release Process:** Standard repo commits; no deployment automation changes in this phase.
- **Configuration Management:** ExecutionContext defaults and log paths under repo root.
- **Maintenance & Ownership:** Scribe MCP maintainers; log rotation as needed.
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| None | — | CLOSED | All Phase-2 OPEN items closed by authoritative decisions. |
Close each question once answered and reference the relevant section above.
<!-- ID: references_appendix -->
- PROGRESS_LOG.md
- AUDIT_REPORT.md
- PHASE_PLAN.md
- CHECKLIST.md
Keep references updated as audit/spec work progresses.
