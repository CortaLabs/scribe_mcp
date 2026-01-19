---
id: scribe_sentinel_concurrency_v1-research_concurrency_session_audit
title: 'Research Report: Concurrency and Session Isolation Audit (scribe_sentinel_concurrency_v1)'
doc_type: research_concurrency_session_audit
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
# Research Report: Concurrency and Session Isolation Audit (scribe_sentinel_concurrency_v1)

## Goal
Audit the current Scribe MCP implementation for multi-instance concurrency across all modes (project + sentinel). Identify global state leak points and any gaps versus the session-scoped design in the architecture guide.

## Sources Reviewed
- server.py:149-217 (tool router context defaults, mode gating)
- shared/execution_context.py:61-141 (session_id derivation, contextvars)
- shared/logging_utils.py:74-140 (logging context resolution order, global fallback)
- tools/set_project.py:250-312 (agent session set + global mirror)
- state/manager.py:19-194 (current_project + session_projects persistence)
- state/agent_manager.py:73-136, 462-499 (DB-backed agent project, legacy migration)
- state/agent_identity.py:135-179 (session resumption)

## Findings
1) ExecutionContext session_id falls back to a process-scoped ID when transport_session_id is absent. This means all requests without a transport session share the same session_id, which is not safe for concurrent clients in a single process. (shared/execution_context.py:61-70, 106-121)
2) Tool router fills missing repo_root by calling load_active_project (global current_project). Requests without context can inherit an unrelated project's root under concurrency. (server.py:165-174)
3) LoggingContext resolves session-scoped projects first, but the final fallback uses load_active_project (global current_project). Tools without session context or agent_id can still resolve to global state. (shared/logging_utils.py:74-134)
4) set_project updates agent-scoped session project, but then always mirrors to global JSON state current_project. This keeps global state changing per session and reintroduces a shared fallback. (tools/set_project.py:250-287)
5) StateManager persists both session_projects and current_project in the state file; current_project is still authoritative in fallback paths. (state/manager.py:139-183)
6) AgentManager uses DB-backed agent projects with session lease validation and migrates legacy current_project to agent "Scribe" then clears the global value. This is a positive step, but later set_project calls still repopulate global current_project. (state/agent_manager.py:73-136, 462-499)

## Risks
- Multiple concurrent clients without transport_session_id collapse onto one session_id, causing cross-project context bleed.
- Tools invoked without explicit context/agent_id can fall back to global current_project and read/write the wrong project's logs.

## Recommendations (Priority Order)
1) Enforce a per-connection transport_session_id from the MCP transport (or require an explicit context.session_id). If absent, fail fast or generate per-request identifiers rather than reusing a process-level session_id.
2) Remove or hard-gate global current_project fallbacks when an ExecutionContext exists but session_project is missing. Require set_project for the session to proceed in project mode.
3) Stop mirroring set_project into global current_project by default (or guard it behind a compatibility flag). Keep session_projects as the authoritative per-session mapping.
4) Avoid load_active_project for repo_root defaults in the router; prefer settings.project_root or explicit context to prevent cross-project leakage.

## Open Questions
- Does the MCP transport provide a stable transport_session_id for each client connection? If not, should we add one at the router boundary or mandate it in client integration?

## Deferred Items (Per User Direction)
- Add descending sort flag to query_entries (do not change current default order).
- Add optional descending flag to read_recent (default remains most-recent-first).
- Add read_file mode=read after sentinel mode and session-scoped concurrency are complete.
