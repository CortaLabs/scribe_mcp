---
id: scribe_pro_cleanup-research-database-storage-audit-20260206
title: "\U0001F52C Research Database Storage Audit 20260206 \u2014 scribe_pro_cleanup"
doc_name: RESEARCH_DATABASE_STORAGE_AUDIT_20260206
category: engineering
status: draft
version: '0.1'
last_updated: '2026-02-06'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Database Storage Audit 20260206 — scribe_pro_cleanup
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-06 07:54:59 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Complete audit of ALL database and storage systems in Scribe MCP to identify redundancies, document schema, assess Postgres readiness, and plan consolidation strategy.

**Key Takeaways:**
- **CRITICAL**: Multiple redundant database files exist due to historical path migrations (.scribe/scribe.db 436K, .scribe/data/scribe.db 448K, data/scribe_projects.db 75MB PRIMARY)
- **RISK**: state.json (326KB) is deprecated but actively used by StateManager, creating dual-source-of-truth problem with database
- **POSITIVE**: Comprehensive 30+ table schema with FTS5 full-text search, SQLite connection pooling (min=1, max=3), clean StorageBackend abstraction
- **INCOMPLETE**: Postgres implementation exists but only ~40% complete vs SQLite (260 lines vs 3050 lines, missing connection pooling, FTS5, many advanced tables)
- **CLEANUP NEEDED**: 7+ tmp_tests/ directories with orphaned test databases and state.json files
- **PATH INCONSISTENCY**: Some components (reminders.py) hardcode DB paths bypassing central settings configuration
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-DatabaseAudit

**Investigation Window:** 2026-02-06 (single-day comprehensive audit)

**Focus Areas:**
- [x] Database file inventory and size analysis
- [x] Complete schema documentation (all 30+ tables)
- [x] state.json audit and usage patterns
- [x] StorageBackend architecture review
- [x] Postgres implementation completeness assessment
- [x] Database path resolution logic tracing
- [x] Connection pooling implementation analysis
- [x] Migration system capabilities
- [x] Test database cleanup issues
- [x] Consolidation and migration planning

**Dependencies & Constraints:**
- Audit performed on live production system (data/scribe_projects.db is 75MB active database)
- Cannot test Postgres functionality without live Postgres instance
- state.json contains 5554 lines of project state, cannot verify all project references
- Migration recommendations assume backward compatibility requirements
<!-- ID: findings -->
### Finding 1: Multiple Redundant Database Files
- **Summary:** Four production database files exist due to historical path migrations, causing confusion and potential data inconsistency
- **Evidence:**
  - `data/scribe_projects.db` — 75MB PRIMARY (active production database)
  - `.scribe/scribe.db` — 436K (legacy path, likely outdated)
  - `.scribe/data/scribe.db` — 448K (intermediate migration path, still accessed by reminders.py line 31)
  - `.scribe/data/scribe_projects.db` — 0 bytes EMPTY (abandoned file)
  - Path resolution traced through `storage/__init__.py` → `config/settings.py` line 99
- **Root Cause:** Settings default changed from `.scribe/scribe.db` → `.scribe/data/scribe.db` → `data/scribe_projects.db` over time, but hardcoded paths remain in codebase
- **Confidence:** High (0.95) — file sizes and timestamps verified, code paths traced

### Finding 2: state.json Deprecated But Actively Used
- **Summary:** state.json (326KB, 5554 lines) declared deprecated but actively managed by StateManager class, creating dual-source-of-truth with database
- **Evidence:**
  - File: `.scribe/state.json` (326,412 bytes)
  - Code: `state/manager.py` lines 84-260 (StateManager class with load() and save() methods)
  - Contains: current_project, projects dict, session_projects, agent_state, recent_tools
  - Database has overlapping tables: scribe_projects, agent_sessions, session_projects
- **Risk:** State can diverge between state.json and database, causing inconsistent project context
- **Confidence:** High (0.95) — StateManager code actively reads/writes JSON

### Finding 3: Comprehensive SQLite Schema (30+ Tables)
- **Summary:** Production schema is well-designed with 30+ tables covering all aspects of project management, telemetry, and document tracking
- **Evidence:** `storage/sqlite.py` lines 849-1350 (_initialise method)
- **Schema Categories:**
  1. **Core**: scribe_projects, scribe_entries, scribe_metrics, scribe_migrations
  2. **Sessions**: agent_sessions, scribe_sessions, session_projects, agent_projects, agent_project_events, agent_recent_projects
  3. **Planning**: dev_plans, phases, milestones, benchmarks, checklists, performance_metrics
  4. **Documents**: document_sections (with FTS5 full-text search + triggers), document_changes, sync_status, custom_templates
  5. **Telemetry**: doc_changes, tool_calls, reminder_history
  6. **Bridges**: scribe_bridges (external MCP integration)
  7. **Archives**: scribe_entries_archive (data retention)
  8. **Report Cards**: agent_report_cards (agent performance tracking)
- **Confidence:** High (1.0) — schema directly from production code

### Finding 4: Postgres Implementation Incomplete
- **Summary:** Postgres storage backend exists but only implements ~40% of SQLite functionality
- **Evidence:**
  - `storage/postgres.py` — 260 lines, 18 methods
  - `storage/sqlite.py` — 3050 lines, 50+ methods
  - Missing in Postgres: connection pooling (no asyncpg pool), FTS5 search, migration tracking, many advanced tables, session management complexity
  - Factory: `storage/__init__.py` lines 13-23 can instantiate either backend
- **Gap Analysis:**
  - Has: Basic CRUD (upsert_project, fetch_project, list_projects, delete_project, insert_entry, fetch_recent_entries)
  - Missing: Agent sessions, document management, FTS5 search, migrations, connection pooling, benchmarks, phases, milestones
- **Confidence:** High (0.9) — code line counts and method inventory verified

### Finding 5: SQLite Connection Pooling Present
- **Summary:** SQLite has production-ready connection pooling with min/max limits and timeout handling
- **Evidence:** `storage/pool.py` lines 54-409 (SQLiteConnectionPool class)
- **Implementation:**
  - Thread-safe connection management
  - Default: min=1, max=3 connections
  - Timeout handling and connection validation
  - Context manager support (`with pool.connection()`)
  - Documented latency improvements: 50-80% reduction
- **Confidence:** High (1.0) — implementation code verified

### Finding 6: Path Resolution Inconsistencies
- **Summary:** Database path resolution mixes centralized configuration with hardcoded paths in individual components
- **Evidence:**
  - **Centralized**: `config/settings.py` lines 94-99 (sqlite_path with SCRIBE_SQLITE_PATH override)
  - **Hardcoded**: `reminders.py` line 31 hardcodes `.scribe/data/scribe.db` instead of using settings
  - **Factory**: `storage/__init__.py` line 19 correctly uses settings.sqlite_path
- **Risk:** Components can write to different databases, causing data fragmentation
- **Confidence:** High (0.95) — hardcoded path found in active code

### Finding 7: Test Database Pollution
- **Summary:** Test suite creates temporary databases but cleanup is incomplete, leaving 7+ tmp_tests/ directories
- **Evidence:** `find` command discovered 7+ tmp_tests/debug_* directories, each containing scribe.db + state.json
- **Impact:** Disk space waste, potential confusion during debugging (which DB is which?)
- **Root Cause:** Test teardown likely incomplete or skipped on errors
- **Confidence:** High (1.0) — files verified to exist

### Finding 8: Migration System Exists
- **Summary:** SQLite has migration tracking infrastructure with scribe_migrations table and helper methods
- **Evidence:**
  - `scribe_migrations` table (lines 857-862) tracks completed migrations
  - `_ensure_column()` and `_ensure_index()` helper methods for safe schema updates
  - Migration functions checked via `_migration_completed()` to prevent re-runs
  - Example: `projects_extended_columns_v1` migration (lines 1345-1350)
- **Quality:** Idempotent, safe, version-tracked
- **Confidence:** High (1.0) — migration infrastructure code verified

### Additional Notes
- Postgres schema creation likely needs separate migration scripts (can't reuse SQLite's CREATE TABLE directly due to syntax differences)
- FTS5 in SQLite would need pg_trgm or similar in Postgres for equivalent full-text search
- Connection pooling for Postgres would require asyncpg pool setup (not just wrapper like SQLite)
- state.json removal requires careful migration to ensure no data loss and backward compatibility for existing tools
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- **Good**: Clean abstraction via StorageBackend base class (`storage/base.py`) with 30+ abstract methods
- **Good**: Factory pattern for backend instantiation (`storage/__init__.py`) with env var override support
- **Good**: Migration tracking with idempotent helpers (`_ensure_column`, `_ensure_index`, `_migration_completed`)
- **Anti-pattern**: Hardcoded database paths bypass centralized configuration (e.g., `reminders.py` line 31)
- **Anti-pattern**: Dual state management (state.json + database tables) without clear ownership boundaries
- **Pattern**: FTS5 full-text search with automatic triggers for document_sections table (lines 1262-1288)
- **Pattern**: Connection pooling via context manager pattern in `storage/pool.py`

**System Interactions:**
- **Primary Flow**: MCP Server → create_storage_backend() → SQLiteStorage(settings.sqlite_path) → data/scribe_projects.db
- **Legacy Flow**: Reminder system → hardcoded .scribe/data/scribe.db (bypasses factory)
- **State Management**: Tools → StateManager → .scribe/state.json (parallel to database)
- **Bridge System**: scribe_bridges table for external MCP server integration
- **Session Flow**: AgentContextManager → agent_sessions/scribe_sessions tables → session isolation
- **Document Management**: document_sections table + FTS5 → full-text semantic search capability

**Risk Assessment:**
- **HIGH RISK**: Multiple DB files + hardcoded paths = data fragmentation potential. Components may write/read from different databases creating inconsistent state.
- **MEDIUM RISK**: state.json deprecation incomplete. StateManager actively used means removal requires full audit of all StateManager.load() callers.
- **HIGH RISK**: Postgres implementation gap means production Postgres deployment would lose 60% of features (sessions, FTS5, advanced planning, telemetry).
- **LOW RISK**: Test database pollution is cleanup issue, not correctness issue. Can be addressed with fixture teardown improvements.
- **MEDIUM RISK**: Schema divergence between SQLite and Postgres. No automated schema sync mechanism means implementations can drift.
<!-- ID: recommendations -->
### Immediate Next Steps (Phase 1: Consolidation)
1. **[ ] Database Consolidation** (Priority: CRITICAL)
   - Audit all code for hardcoded DB paths (search for `.scribe/data/scribe.db`, `.scribe/scribe.db`)
   - Replace hardcoded paths with `settings.sqlite_path` (e.g., fix `reminders.py` line 31)
   - Verify all components point to `data/scribe_projects.db`
   - Back up and archive legacy DBs (.scribe/scribe.db, .scribe/data/scribe.db) after confirming no unique data
   - Delete empty .scribe/data/scribe_projects.db file

2. **[ ] Test Cleanup** (Priority: HIGH)
   - Add pytest fixture teardown to remove tmp_tests/ directories
   - Implement `@pytest.fixture(autouse=True)` with tmpdir cleanup
   - Document test database isolation patterns

3. **[ ] state.json Deprecation Audit** (Priority: HIGH)
   - Search for all `StateManager.load()` call sites
   - Identify what data each caller needs from state.json
   - Map state.json fields to database tables (current_project → agent_projects, session_projects → session_projects table)
   - Create migration plan: state.json → database with backward compat layer

### Phase 2: state.json Removal Strategy
1. **Create StateManager database adapter** — StateManager reads from DB instead of JSON, falls back to JSON if DB empty (migration transition period)
2. **One-time migration script** — Load state.json, populate database tables, rename state.json to state.json.deprecated
3. **Deprecation period** — StateManager reads DB-first, JSON-second for 1-2 releases
4. **Removal** — Delete StateManager JSON code, state.json file, update docs

### Phase 3: Postgres Completion (Long-Term)
1. **Connection Pooling** — Implement asyncpg pool in PostgresStorage (similar to SQLiteConnectionPool pattern)
2. **Schema Parity** — Port all 30+ tables to Postgres-compatible SQL:
   - Core tables (projects, entries, metrics, migrations) — DONE
   - Session management (agent_sessions, scribe_sessions, etc.) — TODO
   - Planning tables (dev_plans, phases, milestones, benchmarks, checklists) — TODO
   - Document tables (document_sections, document_changes, sync_status) — TODO
   - Full-text search (FTS5 → pg_trgm or ts_vector) — TODO
   - Telemetry (tool_calls, reminder_history) — TODO
   - Bridges (scribe_bridges) — TODO
3. **Migration System** — Implement Postgres migration tracking (scribe_migrations table + migration helpers)
4. **Testing** — Dual-backend test suite ensuring SQLite and Postgres have feature parity
5. **Schema Sync** — Consider schema migration tool (Alembic?) to prevent SQLite/Postgres drift

### Long-Term Opportunities
- **Single source of truth** — Eliminate state.json entirely, use database as canonical state
- **Postgres production readiness** — Full feature parity enables horizontal scaling for multi-user deployments
- **Schema versioning** — Automated migration generation from StorageBackend interface changes
- **Performance optimization** — With single consolidated DB, can optimize indexes and query patterns
- **Backup strategy** — Unified backup/restore for single database vs scattered JSON + multiple DBs
- **Multi-backend support** — With clean abstraction, could support additional backends (Redis for caching layer, cloud databases)
<!-- ID: appendix -->
**File References:**
- `storage/base.py` — StorageBackend abstract interface (400 lines, 30+ methods)
- `storage/sqlite.py` — SQLite implementation (3050 lines, schema lines 849-1350)
- `storage/postgres.py` — Postgres implementation (260 lines, ~40% complete)
- `storage/pool.py` — SQLite connection pooling (409 lines)
- `storage/__init__.py` — Backend factory (lines 13-23)
- `config/settings.py` — Configuration and path resolution (lines 85-105)
- `state/manager.py` — StateManager class (lines 84-260)
- `reminders.py` — Hardcoded DB path example (line 31)

**Database Files:**
- `data/scribe_projects.db` — 75MB PRIMARY (production)
- `.scribe/scribe.db` — 436K (legacy, potentially outdated)
- `.scribe/data/scribe.db` — 448K (intermediate path, still accessed)
- `.scribe/data/scribe_projects.db` — 0 bytes EMPTY
- `data/backups/scribe_backup_*.db` — 688K each (backups)
- `.scribe/state.json` — 326KB (5554 lines, deprecated but active)

**Schema Documentation:**
- 30+ tables total across 8 categories
- Core: scribe_projects, scribe_entries, scribe_metrics, scribe_migrations (lines 870-906)
- Sessions: agent_sessions, scribe_sessions, session_projects, agent_projects, agent_project_events, agent_recent_projects (lines 908-999)
- Planning: dev_plans, phases, milestones, benchmarks, checklists, performance_metrics (lines 1019-1119)
- Documents: document_sections, document_changes, sync_status, custom_templates (lines 1122-1182)
- FTS5: document_sections_fts with insert/delete/update triggers (lines 1262-1288)
- Telemetry: doc_changes, tool_calls, reminder_history (lines 1001-1253)
- Bridges: scribe_bridges (lines 1290-1308)
- Archives: scribe_entries_archive (lines 1310-1334)
- Agent Performance: agent_report_cards (lines 1184-1197)

**Migration Infrastructure:**
- scribe_migrations tracking table (lines 857-862)
- _ensure_column() helper for safe column additions
- _ensure_index() helper for safe index additions
- _migration_completed() check to prevent re-runs
- Example migration: projects_extended_columns_v1 (lines 1345-1350)

**Connection Pooling:**
- SQLiteConnectionPool class (storage/pool.py lines 54-409)
- Default: min=1, max=3 connections
- Thread-safe with validation and timeout handling
- 50-80% latency reduction documented

**Tool Call Log Entries:**
- 10+ append_entry calls documenting investigation progress
- Progress log contains full audit trail with reasoning blocks
- All findings cross-referenced with code line numbers
