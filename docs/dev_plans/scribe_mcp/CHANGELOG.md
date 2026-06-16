# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>

## Runtime latency, telemetry, and binding reuse
- `entry_id`: 20260616:runtime-latency-telemetry-binding-reuse-2-7-0
- `entry_status`: accepted
- `title`: Runtime latency, telemetry, and binding reuse
- `summary`: Bumped the public release line to `2.7.0`. Scribe now records queryable tool runtimes with durations, correlation IDs, measurement scope, and repo root; `append_entry` returns phase timing; `set_project` has a strict same-agent/session/project/root no-write reuse path that skips redundant writes and mutation-time reminder refresh; successful timing logs stay out of warning output; local probes support JSON output, same-server root comparison, and background telemetry draining; diagnostics expose physical/logical reconciliation for fresh Postgres installs with existing file-backed Scribe artifacts.
- `evidence_refs`:
  - pyproject.toml
  - src/scribe_mcp/__main__.py
  - src/scribe_mcp/tools/set_project.py
  - src/scribe_mcp/tools/append_entry.py
  - src/scribe_mcp/state/agent_manager.py
  - src/scribe_mcp/scripts/scribe_probe.py
  - src/scribe_mcp/utils/formatters/dispatcher.py
  - src/scribe_mcp/physical_logical_reconciliation.py
  - tests/test_set_project.py
  - tests/test_scribe_probe.py
  - tests/test_execution_context.py
  - tests/test_physical_logical_reconciliation.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.7.0

## Quality-check agent actions, bulk validation, and write-barrier safety
- `entry_id`: 20260616:quality-check-agent-actions-bulk-write-barrier-2-6-0
- `entry_status`: accepted
- `title`: Quality-check agent actions, bulk validation, and write-barrier safety
- `summary`: Bumped the public release line to `2.6.0`. `manage_docs quality_check` now returns agent-actionable summaries with grouped warning families, ranked `agent_actions`, file/section context, repair hints, and provenance; Atlas can run bulk quality checks across a project or bounded doc list; `quality_handoff_check` returns concrete follow-up actions; write barriers protect mutation surfaces and Postgres backup/restore custody; exported remote transport blocks local operator-only tools; sparse Postgres `read_recent` responses can be supplemented from canonical progress logs.
- `evidence_refs`:
  - pyproject.toml
  - src/scribe_mcp/doc_management/quality/results.py
  - src/scribe_mcp/doc_management/runtime.py
  - src/scribe_mcp/shared/write_barrier.py
  - src/scribe_mcp/tools/append_entry.py
  - src/scribe_mcp/tools/manage_docs.py
  - src/scribe_mcp/tools/read_recent.py
  - src/scribe_mcp/tools/set_project.py
  - src/scribe_mcp/server_sse.py
  - src/scribe_mcp/scripts/postgres_backup.py
  - src/scribe_mcp/scripts/postgres_restore.py
  - tests/test_manage_docs_quality_check.py
  - tests/test_write_barrier_contract.py
  - tests/security/test_transport_authorization.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.6.0

## Unified create contract + error remediation envelopes (P2-P3)
- `entry_id`: 20260611:create-contract-error-envelopes-2-5-0
- `entry_status`: accepted
- `title`: Unified create contract + error remediation envelopes
- `summary`: Bumped the unpublished release line to `2.5.0` (backward-compatible public capability). Create contract unified and pinned: empty create legal for generic doc types, and a metadata.sections payload now emits stable section anchors so created sections are durable replace_section targets. New structured error remediation envelopes {code, remediation, alternatives[]} on DOC_NOT_FOUND (did-you-mean + registered docs), SECTION_ANCHOR_MISSING (inline available anchors + closest match), SECTION_ANCHOR_AMBIGUOUS, REPLACE_TEXT_NO_MATCH (nearest-line), and PATCH_CONTEXT_NOT_FOUND (structured-mode fallback).
- `evidence_refs`:
  - pyproject.toml
  - docs/COMPATIBILITY_MATRIX.md
  - src/scribe_mcp/doc_management/errors.py
  - src/scribe_mcp/doc_management/manager.py
  - src/scribe_mcp/doc_management/actions/edit.py
  - tests/test_create_contract_unified.py
  - tests/test_error_remediation.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.5.0

## Session authority contract + logging-never-blocked repairs (P1.6-P1.7, BUG-2026-06-11-0004)
- `entry_id`: 20260611:session-authority-and-case-guidance-2-4-2
- `entry_status`: accepted
- `title`: Session authority contract + logging-never-blocked repairs
- `summary`: Restored the pinned write-authority contract (request session_id outranks a bare carried-over stable_session_id in degraded contexts; verified resolved_scope keys keep absolute priority) regressed by e320b3d, re-adding the deleted contract test. append_entry now heals pipe characters to the broken bar instead of rejecting entries. open_bug/open_security guidance now maps completeness fields to their real template section anchors, validated against the live templates.
- `evidence_refs`:
  - src/scribe_mcp/tools/agent_project_utils.py
  - src/scribe_mcp/tools/append_entry.py
  - src/scribe_mcp/tools/sentinel_tools.py
  - tests/test_manage_docs_session_binding.py
  - tests/test_message_pipe_healing.py
  - tests/test_case_field_section_anchors.py
  - docs/bugs/logic/2026-06-11_BUG-2026-06-11-0004/report.md
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.2

## manage_docs defect-repair wave (P1.1-P1.5)
- `entry_id`: 20260611:manage-docs-defect-wave-2-4-2
- `entry_status`: accepted
- `title`: manage_docs defect-repair wave (P1.1-P1.5)
- `summary`: Five live-reproduced manage_docs defects repaired on the unpublished `2.4.2` line: batch operations inherit top-level doc_name; exact-match edit payloads (metadata.find/.replace) preserved verbatim through parameter healing with a near-miss hint on no-match; section inspection reports inline anchors (editable_sections now complete); replace_section preserves inter-section separators and strips duplicate headings with a response hint; create-guidance reconciled to one story across reminder, create_intent, and rule template.
- `evidence_refs`:
  - src/scribe_mcp/doc_management/actions/batch.py
  - src/scribe_mcp/doc_management/actions/query.py
  - src/scribe_mcp/doc_management/manager.py
  - src/scribe_mcp/doc_management/runtime.py
  - src/scribe_mcp/utils/parameter_validator.py
  - src/scribe_mcp/config/reminders/en-US.json
  - .council/templates/claude/rules/_rule_manage_docs_create.j2
  - tests/test_batch_doc_name_inheritance.py
  - tests/test_replace_text_multiline.py
  - tests/test_create_editable_sections_complete.py
  - tests/test_replace_section_separator.py
  - tests/test_create_guidance_consistent.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.2

## doc_updates auto-log contract repair
- `entry_id`: 20260611:doc-updates-autolog-contract-2-4-2
- `entry_status`: accepted
- `title`: doc_updates auto-log contract repair
- `summary`: Bumped the public release line to `2.4.2` and repaired the manage_docs edit auto-logger so internal doc_updates entries satisfy their own metadata_requirements (`doc`, `section`, `action`) and use a valid `warn` status, eliminating the ~37k "Log requirements not met: Missing metadata for log entry: doc" silent error stream (BUG-2026-06-11-0003).
- `evidence_refs`:
  - pyproject.toml
  - docs/COMPATIBILITY_MATRIX.md
  - src/scribe_mcp/doc_management/actions/edit.py
  - tests/test_doc_updates_autolog_contract.py
  - docs/bugs/logic/2026-06-11_BUG-2026-06-11-0003/report.md
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.2

## Bug and security report follow-up editing
- `entry_id`: 20260604:case-report-manage-docs-followup-2-4-1
- `entry_status`: accepted
- `title`: Bug and security report follow-up editing
- `summary`: Bumped the public release line to `2.4.1`, added obvious `open_bug` and `open_security` follow-up handles, and taught `manage_docs` to resolve governed bug/security reports by case id, governed path, or canonical category metadata before applying edits.
- `evidence_refs`:
  - pyproject.toml
  - README.md
  - docs/COMPATIBILITY_MATRIX.md
  - docs/RELEASE_SURFACE.md
  - src/scribe_mcp/doc_management/runtime.py
  - src/scribe_mcp/doc_management/utils.py
  - src/scribe_mcp/tools/sentinel_tools.py
  - tests/test_manage_docs_target_resolution.py
  - tests/test_sentinel_tools.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.1

## No-dotenv-safe settings import
- `entry_id`: 20260518:no-dotenv-settings-import
- `entry_status`: accepted
- `title`: No-dotenv-safe settings import
- `summary`: Added the generic `SCRIBE_DISABLE_DOTENV` settings-load guard so import/readiness proof can avoid repo and global dotenv reads, preserved storage backend fail-closed behavior, and bumped the public release line to `2.2.24`.
- `evidence_refs`:
  - src/scribe_mcp/config/settings.py
  - tests/test_settings_schema_alias.py
  - tests/test_storage_factory_backends.py
  - tests/test_runtime_backend_repo_overrides.py
  - pyproject.toml
  - README.md
  - docs/COMPATIBILITY_MATRIX.md
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.2.24
