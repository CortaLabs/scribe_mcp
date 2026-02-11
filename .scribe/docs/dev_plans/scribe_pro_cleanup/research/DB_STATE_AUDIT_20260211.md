---
id: scribe_pro_cleanup-db-state-audit-20260211
title: DB State Audit - 2026-02-11
doc_type: custom
doc_name: DB_STATE_AUDIT_20260211
category: engineering
status: draft
version: '0.1'
last_updated: '2026-02-11'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# DB State Audit - 2026-02-11

## Scope
- Objective: Produce a full SQLite baseline for Phase 4 migration cleanup and upcoming Postgres parity work.
- Sources: live DB at `.scribe/scribe.db` and a fresh bootstrap DB created from current `SQLiteStorage.setup()`.

## Snapshot Summary
- Live DB path: `/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/scribe.db`
- Fresh bootstrap counts: 32 tables, 68 indexes, 3 triggers
- Live DB counts: 32 tables, 68 indexes, 3 triggers
- Result: live schema object counts match fresh bootstrap counts.

## Tracked Migration Ledger (live DB)
- `agent_report_cards_indexes_v1`
- `document_sections_schema_v1`
- `entries_metadata_columns_v1`
- `entries_metadata_indexes_v1`
- `projects_bridge_columns_v1`
- `projects_extended_columns_v1`
- `agent_sessions_activity_v1`
- `backfill_docs_json_v1`
- `docs_json_column_v1`
- `phase1_optimization_indexes_v1`
- `projects_repo_index_v1`
- `tool_calls_repo_root_v1`

## Table Inventory (fresh bootstrap)
- `agent_project_events`
- `agent_projects`
- `agent_recent_projects`
- `agent_report_cards`
- `agent_sessions`
- `benchmarks`
- `checklists`
- `custom_templates`
- `dev_plans`
- `doc_changes`
- `document_changes`
- `document_sections`
- `document_sections_fts`
- `document_sections_fts_config`
- `document_sections_fts_data`
- `document_sections_fts_docsize`
- `document_sections_fts_idx`
- `milestones`
- `performance_metrics`
- `phases`
- `reminder_history`
- `scribe_bridges`
- `scribe_entries`
- `scribe_entries_archive`
- `scribe_metrics`
- `scribe_migrations`
- `scribe_projects`
- `scribe_sessions`
- `session_projects`
- `sqlite_sequence`
- `sync_status`
- `tool_calls`

## Postgres Readiness Notes
- `storage/sqlite/__init__.py` now delegates schema and tracked migrations to dedicated modules (`schema.py`, `migrations.py`), reducing migration drift risk.
- This document defines the canonical SQLite object inventory and migration names that Postgres must match semantically.
- Next parity gate should verify each StorageBackend method against this inventory and migration intent, not just table existence.

## Evidence
- Full machine-readable audit written during this run: `/tmp/scribe_db_audit_phase4.json`
- Targeted validation suite after extraction: `pytest tests/test_db_routing.py tests/test_agent_manager.py tests/test_audit_trails.py tests/test_migration_priority_columns.py tests/test_query_entries_db.py -q` -> 16 passed, 1 skipped.
