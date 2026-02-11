---
id: scribe_pro_cleanup-architecture
title: Architecture Guide -- scribe_pro_cleanup
doc_name: architecture
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

# Architecture Guide -- scribe_pro_cleanup
**Author:** ArchitectAgent-ProCleanup (Opus 4.6)
**Revised by:** ArchitectAgent-FinalPolish (Opus 4.6)
**Version:** v1.1 (post-review revision)
**Status:** Approved (all 5 blocking fixes + 6 recommendations incorporated)
**Last Updated:** 2026-02-06 09:14 UTC

> Comprehensive architecture for the Scribe MCP professional cleanup, packaging, and modernization project. This document is the single source of truth for all implementation work.

---
## 1. Problem Statement
<!-- ID: problem_statement -->

### Context

Scribe MCP v2.2 is a production documentation governance system used by multiple AI agents and human operators. Despite functional maturity, the codebase has accumulated significant technical debt across 10 critical areas that prevent professional distribution, maintainability, and future feature development.

### Measured Problems

| # | Problem | Evidence | Impact |
|---|---------|----------|--------|
| 1 | No packaging configuration | No pyproject.toml or setup.py exists | Cannot pip install; manual sys.path hacks required |
| 2 | God module: storage/sqlite.py | 3,050 lines, 79 methods in one class | Untestable, unnavigable, blocks Postgres parity |
| 3 | God module: tools/manage_docs.py | 3,410 lines, 29 functions in one file | Same maintainability crisis |
| 4 | Path resolution fragility | 50+ instances of `__file__` parent traversal | All break when directory depth changes in src/ layout |
| 5 | Database fragmentation | 4 redundant DB files + state.json (326KB) dual-source-of-truth | Data inconsistency, confusion |
| 6 | Postgres incomplete | 260 lines vs SQLite 3,050 (18 of 31 abstract methods) | Cannot deploy Postgres in production |
| 7 | Reminder system unwired | 2,000+ lines built, only 2 internal call sites, 0 MCP tools | Wasted investment, invisible to users |
| 8 | 200+ junk files | Broken pip artifacts, Zone.Identifier, .bak files, tmp_tests/ | Unprofessional, pollutes git history |
| 9 | No centralized logging | 115+ print/sys.stderr sources with no config | Noisy stderr corrupts MCP JSON-RPC transport |
| 10 | Security vulnerabilities | Symlink path traversal, log injection, unpinned deps | Risk in any non-local deployment |

### Goals

1. **Pip-installable package** -- `pip install -e .` with pyproject.toml, entry points, package data
2. **No god modules** -- Every module under 800 lines; storage/ decomposed into sqlite/ subpackage, tools/manage_docs.py logic pushed into doc_management/ backend engine
3. **Single database** -- One SQLite path, no state.json, clean XDG-compliant defaults
4. **Postgres feature parity** -- Full asyncpg implementation matching all 31 StorageBackend methods
5. **Reminder system live** -- 3 MCP tools exposing the existing reminder engine to users
6. **Centralized logging** -- Python `logging` module with SCRIBE_LOG_LEVEL env var, zero stderr noise
7. **Security hardened** -- Symlink boundary fix, log sanitization, pinned dependencies
8. **Clean repository** -- Zero junk files, effective .gitignore, professional presentation
9. **Auth/transport scaffold** -- Abstract interfaces for API key + JWT auth and HTTP+SSE + WebSocket transport (stubs only)
10. **Optimized startup** -- Lazy tool loading, deferred migrations, background cleanup

### Non-Goals

- Full auth implementation (scaffold interfaces only)
- Multi-tenant isolation (single-tenant for now)
- New features beyond cleanup and restoration of unwired code
- UI/frontend work
- WebSocket or HTTP transport implementation (interfaces only)

### Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| `pip install -e .` succeeds | Exit code 0, `scribe-server --help` works |
| No file > 800 lines in src/scribe_mcp/ (excluding tests) | `wc -l` on all .py files |
| `pytest tests/` passes with >= 90% of existing tests | Test count comparison pre/post |
| Single DB path, state.json deleted | `find . -name state.json` returns nothing |
| Postgres backend passes same test suite as SQLite | Dual-backend pytest parametrize |
| 3 reminder MCP tools operational | `list_tools` includes query_reminders, configure_reminders, reset_reminders |
| Zero print/sys.stderr in production code | `grep -r 'print(' src/` returns 0 (excluding tests) |
| 0 junk files matching cleanup patterns | Glob patterns return empty |
| Startup time < 2s (measured) | Instrumented startup benchmark |

---
## 2. Requirements and Constraints
<!-- ID: requirements_constraints -->

### Functional Requirements

1. All existing MCP tools continue to work identically after migration
2. Existing .scribe/ project data must be preserved during migration
3. Both SQLite and Postgres backends must implement all 31 StorageBackend abstract methods
4. Reminder system exposes query, configure, and reset operations via MCP tools
5. All configuration accessible via environment variables (SCRIBE_LOG_LEVEL, SCRIBE_DB_PATH, etc.)
6. Package installable via `pip install -e .` for development and `pip install scribe-mcp` for production

### Non-Functional Requirements

1. No module exceeds 800 lines (hard limit, enforced in CI)
2. Backward compatibility for .scribe/ directory structure (existing projects must work)
3. All imports use absolute form `from scribe_mcp.X import Y`
4. Python 3.10+ minimum (for modern typing)
5. Dependencies pinned to compatible ranges (`~=` operator) in pyproject.toml
6. Zero print/sys.stderr calls in production code paths

### Constraints

- Package name must remain `scribe_mcp` (internal imports already use this)
- Target layout: `MCP_SPINE/scribe_mcp/src/scribe_mcp/`
- Must support existing `from scribe_mcp.X import Y` import pattern after migration
- Cannot break existing MCP client configurations (Claude Desktop json configs)
- Migration must handle 75MB production SQLite database gracefully

---
## 3. Architecture Overview
<!-- ID: architecture_overview -->

### Target Directory Layout

```
MCP_SPINE/scribe_mcp/
|-- pyproject.toml
|-- README.md
|-- LICENSE
|-- pytest.ini
|-- CLAUDE.md
|-- AGENTS.md
|-- src/
|   +-- scribe_mcp/
|       |-- __init__.py
|       |-- server.py            # MCP server entry point
|       |-- py.typed
|       |-- config/
|       |   |-- __init__.py
|       |   |-- settings.py
|       |   |-- display.py
|       |   |-- logging.py       # NEW: Centralized logging
|       |   |-- paths.py         # NEW: All path resolution
|       |   +-- data/            # Package data (JSON, via importlib.resources)
|       |       |-- log_config.json
|       |       |-- mcp_config.json
|       |       |-- reminder_config.json
|       |       +-- boundary_rules_schema.json
|       |-- storage/
|       |   |-- __init__.py      # Factory: create_storage_backend()
|       |   |-- base.py          # StorageBackend ABC (31 methods)
|       |   |-- models.py
|       |   |-- pool.py          # SQLiteConnectionPool
|       |   |-- sqlite/          # DECOMPOSED from 3050-line god module
|       |   |   |-- __init__.py  # SQLiteStorage facade
|       |   |   |-- schema.py    # CREATE TABLE/INDEX statements
|       |   |   |-- migrations.py
|       |   |   |-- projects.py  # Project CRUD
|       |   |   |-- entries.py   # Entry CRUD + queries
|       |   |   |-- sessions.py  # Session management
|       |   |   |-- documents.py # Doc sections, FTS5
|       |   |   |-- planning.py  # Dev plans, phases, milestones
|       |   |   |-- telemetry.py # Tool calls, report cards
|       |   |   +-- internals.py # _execute, _fetchall, connection mgmt
|       |   +-- postgres/        # PARALLEL structure
|       |       |-- __init__.py  # PostgresStorage facade
|       |       |-- schema.py    # Postgres DDL (pg_trgm for FTS)
|       |       |-- migrations.py
|       |       |-- projects.py
|       |       |-- entries.py
|       |       |-- sessions.py
|       |       |-- documents.py
|       |       |-- planning.py
|       |       |-- telemetry.py
|       |       +-- internals.py # asyncpg pool
|       |-- tools/
|       |   |-- __init__.py      # Lazy loader
|       |   |-- base/
|       |   |-- append_entry.py
|       |   |-- set_project.py
|       |   |-- get_project.py
|       |   |-- list_projects.py
|       |   |-- read_recent.py
|       |   |-- query_entries.py
|       |   |-- read_file.py
|       |   |-- edit_file.py
|       |   |-- search.py
|       |   |-- rotate_log.py
|       |   |-- delete_project.py
|       |   |-- health_check.py
|       |   |-- open_bug.py
|       |   |-- open_security.py
|       |   |-- link_fix.py
|       |   |-- generate_docs.py
|       |   |-- reminder_tools.py  # NEW: 3 reminder MCP tools
|       |   |-- append_event.py
|       |   +-- manage_docs.py    # THIN MCP ROUTER (~200 lines, was 3410)
|       |-- state/
|       |   |-- manager.py       # DB-backed (no state.json)
|       |   |-- agent_manager.py
|       |   +-- agent_identity.py
|       |-- shared/
|       |-- utils/
|       |   |-- formatters/      # Already decomposed in v2.2
|       |   |-- reminder_engine.py
|       |   |-- reminder_validator.py
|       |   +-- reminder_monitoring.py
|       |-- reminders.py
|       |-- doc_management/      # BACKEND ENGINE (logic moved FROM tools/manage_docs.py)
|       |   |-- __init__.py
|       |   |-- manager.py       # Existing core manager (105KB, to be decomposed)
|       |   |-- healing.py       # NEW: param normalization from tool
|       |   |-- validation.py    # NEW: path safety, action validation
|       |   |-- preflight.py     # NEW: backup creation + retention
|       |   |-- indexing.py      # NEW: vector chunking, entry IDs
|       |   |-- utils.py         # NEW: hashing, parsing, section splitting
|       |   |-- actions/         # NEW: action handlers from tool
|       |   |   |-- create.py    # create action
|       |   |   |-- edit.py      # replace_section/range/text, apply_patch
|       |   |   |-- append.py
|       |   |   |-- status.py    # status_update
|       |   |   |-- search.py
|       |   |   |-- query.py     # list_sections, toc, validate
|       |   |   +-- batch.py
|       |   |-- change_logger.py     # Existing
|       |   |-- change_rollback.py   # Existing
|       |   |-- conflict_resolver.py # Existing
|       |   |-- diff_visualizer.py   # Existing
|       |   |-- file_watcher.py      # Existing
|       |   |-- integrity_verifier.py # Existing
|       |   |-- performance_monitor.py # Existing
|       |   +-- sync_manager.py      # Existing
|       |-- template_engine/
|       |-- templates/
|       |-- bridges/
|       |-- plugins/
|       |-- security/
|       |-- auth/                # NEW: Scaffold only
|       |   |-- base.py          # AuthProvider ABC
|       |   |-- api_key.py       # Stub
|       |   +-- jwt_auth.py      # Stub
|       |-- transport/           # NEW: Scaffold only
|       |   |-- base.py          # TransportProvider ABC
|       |   |-- http_sse.py      # Stub
|       |   +-- websocket.py     # Stub
|       |-- scripts/
|       |   |-- scribe_cli.py
|       |   |-- scribe_admin.py
|       |   +-- migrate_state.py # NEW: state.json migration
|       +-- db/
|           +-- init.sql
+-- tests/
    |-- conftest.py
    |-- fixtures/
    +-- test_*.py
```

### Key Architectural Decisions

| # | Decision | Pattern | Rationale |
|---|----------|---------|-----------|
| 1 | Facade pattern for god module decomposition | SQLiteStorage and manage_docs() remain public entry points, delegate internally | Proven by v2.2 ResponseFormatter decomposition (2934 lines to 7 modules). Preserves API surface. |
| 2 | importlib.resources for package data | config/paths.py centralizes all resolution | Standard Python; works for editable, wheel, and zip installs |
| 3 | XDG Base Directory for user data | DB at $XDG_DATA_HOME/scribe_mcp/ | Standard for well-behaved Linux applications |
| 4 | Lazy tool loading via __getattr__ | tools/__init__.py defers imports | 40-50% startup reduction; MCP SDK supports dynamic registration |
| 5 | Python logging module (no print/stderr) | config/logging.py with SCRIBE_LOG_LEVEL | print() to stderr corrupts MCP JSON-RPC transport |
| 6 | Single database with migration script | scripts/migrate_state.py consolidates 4 DBs + state.json | Eliminates data fragmentation |
| 7 | Parallel sqlite/ and postgres/ subpackages | Same module names, same function signatures | Trivial to verify feature parity with parametrized tests |
| 8 | Shared runtime dispatcher for MCP + CLI | server and CLI invoke common `shared/tool_runtime.py` path | Guarantees identical mode/session guards and read-before-edit behavior across interfaces |

---
## 4. Detailed Design
<!-- ID: detailed_design -->

### 4.1 Storage Layer Decomposition (storage/sqlite/)

The SQLiteStorage class (3,050 lines, 79 methods) will be split into 9 modules. The facade class remains the public API and delegates to domain modules.

**Method-to-Module Assignment:**

**internals.py** (~200 lines): `_execute`, `_fetchall`, `_fetchone`, `_execute_sync`, `_fetchall_sync`, `_fetchone_sync`, `_initialise`, `setup`, `close`

**schema.py** (~400 lines): `create_core_tables`, `create_session_tables`, `create_planning_tables`, `create_document_tables`, `create_telemetry_tables`, `create_bridge_tables`, `create_archive_tables`, `create_fts_tables`, `create_all_indexes` (All CREATE TABLE/INDEX from _initialise lines 849-1350)

**migrations.py** (~300 lines): `_ensure_column`, `_ensure_index`, `_migration_completed`, `_mark_migration_complete`, `run_all_migrations`, specific migration functions (lines 1345-1480)

**projects.py** (~300 lines): `upsert_project`, `fetch_project`, `fetch_project_sync`, `list_projects`, `list_projects_by_repo`, `delete_project`, `update_project_docs`, `update_project_lifecycle`, `record_project_access`

**entries.py** (~400 lines): `insert_entry`, `fetch_recent_entries`, `query_entries`, `count_entries`, `cleanup_old_entries`, `archive_entries`, `fetch_entry_by_id`

**sessions.py** (~300 lines): `upsert_agent_session`, `fetch_agent_session`, `update_session_project`, `list_agent_sessions`, `record_agent_project_event`, `fetch_recent_projects`, `cleanup_stale_sessions`

**documents.py** (~300 lines): `upsert_document_section`, `fetch_document_sections`, `search_document_sections` (FTS5), `record_document_change`, `fetch_document_changes`, `upsert_sync_status`, `upsert_custom_template`

**planning.py** (~250 lines): `upsert_dev_plan`, `fetch_dev_plan`, `upsert_phase`, `list_phases`, `upsert_milestone`, `upsert_benchmark`, `upsert_checklist_item`, `record_performance_metric`

**telemetry.py** (~200 lines): `record_tool_call`, `fetch_tool_calls`, `record_reminder_history`, `fetch_reminder_history`, `upsert_report_card`, `fetch_report_cards`, `upsert_bridge`, `fetch_bridges`

**Facade Pattern:**
```python
# storage/sqlite/__init__.py
class SQLiteStorage(StorageBackend):
    def __init__(self, db_path):
        self._internals = SQLiteInternals(db_path)
    async def setup(self):
        await self._internals.setup()
        await schema.create_all_tables(self._internals.execute)
        await migrations.run_all_migrations(self._internals.execute, self._internals.fetchone)
    async def upsert_project(self, name, repo_root, ...):
        return await projects.upsert_project(self._internals.execute, ...)
    # ... all 31+ methods delegate to domain modules
```

### 4.2 Doc Management Decomposition (CLARIFIED -- review recommendation #6)

**CRITICAL ARCHITECTURE CLARIFICATION:** The decomposition involves TWO existing components that are part of ONE system:

- **`doc_management/`** -- The BACKEND ENGINE. Contains `manager.py` (105KB), `change_logger.py`, `change_rollback.py`, `conflict_resolver.py`, `diff_visualizer.py`, `file_watcher.py`, `integrity_verifier.py`, `performance_monitor.py`, `sync_manager.py`. This is where document management LOGIC lives.
- **`tools/manage_docs.py`** (3,410 lines) -- The MCP TOOL ROUTER. This is the thin interface layer that receives MCP tool calls and delegates to the backend.

**The decomposition pushes logic FROM the 3410-line tool file INTO `doc_management/` submodules.** `tools/manage_docs.py` becomes a thin routing layer (~200 lines) that:
1. Receives MCP tool parameters
2. Heals/validates parameters
3. Routes to the appropriate `doc_management/` handler
4. Formats the response

**These are NOT two separate systems.** `tools/manage_docs.py` is the entry point; `doc_management/` is the engine.

**Target decomposition of tools/manage_docs.py (3,410 lines):**

Logic moves INTO `doc_management/` submodules:
- **doc_management/healing.py** (~200 lines): `_normalize_metadata_with_healing`, `_heal_manage_docs_parameters`, `_add_healing_info_to_response`, `_coerce_line_number`
- **doc_management/validation.py** (~150 lines): Path safety, action validation, section ID validation
- **doc_management/preflight.py** (~100 lines): Backup creation with 3-backup retention, cleanup
- **doc_management/indexing.py** (~100 lines): `_chunk_text_for_vector`, `_generate_doc_entry_id`, `_get_index_updater_for_path`, `_should_skip_doc_index`
- **doc_management/utils.py** (~100 lines): `_hash_text`, `_parse_int`, `_split_into_sections`, `_split_section`, `_build_special_metadata`, `_resolve_custom_doc_path`
- **doc_management/actions/create.py** (~400 lines): Document creation (research, bug, custom, agent_card, review)
- **doc_management/actions/edit.py** (~400 lines): replace_section, replace_range, replace_text, apply_patch
- **doc_management/actions/append.py** (~100 lines): Append to doc/section
- **doc_management/actions/status.py** (~200 lines): status_update, checklist management
- **doc_management/actions/search.py** (~200 lines): Vector + text search
- **doc_management/actions/query.py** (~200 lines): list_sections, list_checklist_items, normalize_headers, generate_toc, validate_crosslinks
- **doc_management/actions/batch.py** (~100 lines): Multi-operation batch execution

**tools/manage_docs.py** retains ONLY: manage_docs() entry point (~200 lines), ACTION_ROUTER dict, MCP parameter handling

### 4.3 Centralized Logging (config/logging.py)

Replace 115+ print/stderr sources with Python logging:
- Module-level loggers: `logger = logging.getLogger(__name__)`
- SCRIBE_LOG_LEVEL env var (default WARNING)
- dictConfig-based configuration
- Zero stderr noise in production

### 4.4 Path Resolution (config/paths.py)

Replace 50+ `__file__` patterns with centralized module:
- `package_root()` via importlib.resources.files("scribe_mcp")
- `config_data_dir()`, `templates_dir()`, `db_init_sql()`
- `user_data_dir()` via XDG Base Directory or `SCRIBE_DATA_DIR`
- `default_db_path()` with `SCRIBE_DB_PATH` override and compatibility alias `SCRIBE_SQLITE_PATH`
- `repo_root()` with `SCRIBE_ROOT` override + auto-detect
- `cli_session_dir()` and `cli_session_state_path()` for persistent CLI session context

**importlib.resources Compatibility Strategy (review fix #2):**

The `importlib.resources.files()` API has known quirks with editable installs (`pip install -e .`) on Python 3.10/3.11. The codebase currently has **zero** importlib.resources usage, so this is entirely new infrastructure.

**Required pattern -- try importlib.resources first, fall back to __file__ for editable installs:**
```python
def package_root() -> Path:
    """Resolve package root, with fallback for editable installs."""
    try:
        # Standard: works for wheel installs and Python 3.12+ editable
        import importlib.resources
        return Path(str(importlib.resources.files("scribe_mcp")))
    except (TypeError, FileNotFoundError, ModuleNotFoundError):
        # Fallback: editable installs on Python 3.10/3.11
        return Path(__file__).resolve().parent.parent
```

**Verification requirements:**
- Test with `pip install -e .` on Python 3.10 and 3.12+
- Test with `pip install .` (non-editable wheel)
- Each path function must have the try/except fallback
- Document minimum Python version implications in pyproject.toml

**OUT OF SCOPE:** Type hints improvement. Research found 60-70% type hint coverage. This is explicitly deferred to a future project to prevent scope creep.

### 4.5 Database Consolidation

Current: 4 DBs + state.json. Target: 1 DB + no state.json.

Migration script (scripts/migrate_state.py):
1. Read state.json, extract projects/sessions/agent state
2. Insert missing records into DB via StorageBackend methods
3. Rename state.json to state.json.migrated
4. Back up and remove legacy DB files

Note: reminders.py hardcoded DB path is fixed in P6.3 (path resolution phase), not here. This prevents a hidden dependency where P6 breaks reminders before P7 fixes it.

**scripts/migrate_database.py awareness (review recommendation #4):** An existing `scripts/migrate_database.py` (313 lines, 6 functions) already handles schema migrations and database upgrades. The new `scripts/migrate_state.py` focuses specifically on state.json-to-DB data migration, which is a different concern. However, Coders should verify these do not overlap in practice. If both scripts touch the same tables, consolidate into a single `scripts/migrate.py` with subcommands.

StateManager refactor: Read/write DB only via StorageBackend. No JSON file access.

### 4.6 Postgres Implementation

Current: 260 lines, 18/31 methods. Target: Full parity.

Missing 13 methods: list_projects_by_repo, update_project_docs, count_entries, cleanup_old_entries, archive_entries, upsert_agent_session, fetch_agent_session, upsert_document_section, search_document_sections (pg_trgm), record_tool_call, upsert_report_card, upsert_bridge, record_reminder_history.

Schema: Port all 30+ tables to Postgres DDL. FTS5 replaced by pg_trgm + GIN index. Connection pooling via asyncpg.create_pool().

**pg_trgm FTS Behavior Contract (review fix #3):**

SQLite FTS5 and PostgreSQL pg_trgm have fundamentally different search semantics. The StorageBackend `search_document_sections()` method must define a consistent behavior contract:

| Aspect | SQLite FTS5 | PostgreSQL pg_trgm | Behavior Contract |
|--------|------------|-------------------|-------------------|
| Query syntax | `MATCH 'term1 term2'` | `similarity(col, 'term') > threshold` | StorageBackend accepts plain text query string |
| Tokenization | ICU or unicode61 | Trigram decomposition (3-char windows) | Minimum 3-char query enforced at API level |
| Ranking | BM25 via `rank` | `similarity()` score (0.0-1.0) | Results ordered by relevance score (normalized 0-1) |
| Partial match | Prefix: `term*` | Automatic (trigram overlap) | Prefix matching supported on both backends |
| Boolean ops | `AND`, `OR`, `NOT` | Combined with `%` operator | Simple AND semantics only (multiple terms = all must match) |

**Implementation approach:**
1. `search_document_sections(query: str, threshold: float = 0.3)` -- shared API
2. SQLite: Use FTS5 `MATCH` with BM25 ranking, normalize scores to 0-1
3. Postgres: Use `pg_trgm similarity()` with GIN index, filter by threshold
4. Both: Return `list[dict]` with `score` field (float 0-1)
5. Parametrized dual-backend tests verify identical result sets for common queries

**Setup requirement:** `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in schema.py for Postgres.

### 4.7 Reminder Wire-Up

3 new MCP tools in tools/reminder_tools.py:
- `query_reminders(agent, project?, category?, limit, format)` -- Query history and active reminders
- `configure_reminders(agent, project?, enabled?, cooldown_minutes?, categories?, tone?, format)` -- Per-project settings
- `reset_reminders(agent, project?, reset_cooldowns, reset_history?, format)` -- Reset cooldowns/history

### 4.8 Security Fixes

1. **Symlink traversal**: Check boundary BEFORE resolve in read_file.py, edit_file.py, search.py
2. **Log injection**: Sanitize newlines/control chars in shared/logging_utils.py compose_log_line()
3. **Dependency pinning**: Use `~=` operator in pyproject.toml

### 4.9 Auth and Transport Scaffold

Abstract base classes only:
- auth/base.py: AuthProvider ABC (authenticate, authorize, revoke)
- auth/api_key.py, auth/jwt_auth.py: NotImplementedError stubs
- transport/base.py: TransportProvider ABC (start, stop, send_message)
- transport/http_sse.py, transport/websocket.py: NotImplementedError stubs

### 4.10 pyproject.toml

Full packaging config with: build-system (setuptools), project metadata, dependencies with `~=` pinning, optional-dependencies (postgres, vector, mcp, dev), console scripts (scribe-server, scribe, scribe-admin, scribe-migrate), package-data (config/data/*.json, templates/**/*.md, db/*.sql), setuptools packages.find where=["src"].

### 4.11 Startup Optimization

- Lazy tool loading: tools/__init__.py uses __getattr__ + importlib.import_module
- Deferred cleanup: cleanup_old_entries() moved to background task
- Migration caching: In-memory set tracks completed migrations
- Deferred plugins: Bridge/plugin discovery on first relevant tool call
- Schema verification: PRAGMA table_list check before CREATE

### 4.12 Unified CLI Execution Path

- `scribe` CLI invokes the same runtime dispatcher used by MCP tool calls (no duplicate execution logic).
- CLI sessions persist under `.scribe/cli/` and include mode, project binding, agent identity, and read-before-edit state.
- CLI supports direct tool execution for the full MCP surface (`scribe <tool> --arg ...`).
- Compatibility is preserved during migration: legacy MCP launch (`python -m server`) remains valid until clients are cut over.

---
## 5. Directory Structure
<!-- ID: directory_structure -->

See Section 3 for complete target tree. Key changes:

| Current | Target | Reason |
|---------|--------|--------|
| `scribe_mcp/*.py` (flat) | `src/scribe_mcp/*.py` | Standard src/ layout |
| `storage/sqlite.py` (3050 lines) | `storage/sqlite/` (9 modules) | God module decomposition |
| `tools/manage_docs.py` (3410 lines) | `tools/manage_docs.py` (~200 lines) + `doc_management/` (12 new modules) | Logic pushed into backend engine; tool stays as thin router |
| `db/ops.py`, `db/pool.py` | DELETED | Dead code (0 imports) |
| `.scribe/state.json` | DELETED | Migrated to DB |
| No config/paths.py | `config/paths.py` | Centralized path resolution |
| No config/logging.py | `config/logging.py` | Centralized logging |

---
## 6. Data and Storage
<!-- ID: data_storage -->

| Store | Technology | Location | Purpose |
|-------|-----------|----------|---------|
| Primary DB | SQLite 3 | $XDG_DATA_HOME/scribe_mcp/scribe.db | All data |
| Postgres | PostgreSQL 14+ | SCRIBE_DB_URL env var | Production alternative |
| Project State | .scribe/ dirs | Per-project | Logs, dev plans, docs |
| Package Config | JSON | importlib.resources | Shipped with package |
| User Config | YAML | $XDG_CONFIG_HOME/scribe_mcp/ | User settings |

---
## 7. Testing and Validation
<!-- ID: testing_strategy -->

- Add dedicated storage unit tests (test_storage/)
- Dual-backend parametrized fixtures (SQLite + Postgres)
- Existing manage_docs tests validate decomposed code
- Each phase verifies full test suite passes
- Startup benchmark tests for optimization phase
- Hardcoded path cleanup (121 /home/austin instances)

---
## 8. Deployment and Operations
<!-- ID: deployment_operations -->

Install: `pip install -e ".[dev]"` (dev), `pip install scribe-mcp` (prod)
Optional: `pip install "scribe-mcp[postgres]"`, `"scribe-mcp[vector]"`

Environment variables: SCRIBE_LOG_LEVEL (WARNING), SCRIBE_DB_PATH (XDG), SCRIBE_DB_URL (Postgres), SCRIBE_ROOT (auto-detect)

Claude Desktop config updated to use `scribe-server` entry point.

---
## 9. Open Questions
<!-- ID: open_questions -->

| Item | Status | Notes |
|------|--------|-------|
| Formal schema versioning (Alembic)? | DEFERRED | Current migration system works |
| Keep examples/council_bridge.py? | DECIDED: KEEP | Product owner decision: keep for now, do NOT delete in P1 (review fix #4) |
| Python minimum: 3.10 | DECIDED | Modern typing, broad adoption |
| Keep deprecated manage_docs actions? | DECIDED: YES | Backward compat; deprecation warnings after 6 months |

---
## 10. References
<!-- ID: references_appendix -->

### Research Documents
- RESEARCH_STRUCTURE_MAP_20260206_0755.md (265 files, 50+ __file__ risks)
- RESEARCH_STDERR_AUDIT_FIXED_20260206.md (535 lines; 1954 print() calls catalogued, 120-150 production actionable) -- replaces original empty template
- RESEARCH_STARTUP_PERF_20260206_0755.md (DB init bottleneck, eager loading)
- RESEARCH_DATABASE_STORAGE_AUDIT_20260206.md (4 DBs, state.json, Postgres 40%)
- RESEARCH_DEAD_CODE_AUDIT_20260206.md (483 dead, 2000+ unwired)
- RESEARCH_SECURITY_AUDIT_20260206_0758.md (symlink, log injection, deps)
- RESEARCH_TEST_AUDIT_20260206.md (560MB orphaned, fixture gaps)
- RESEARCH_CODE_QUALITY_REPO_HYGIENE_20260206.md (200+ junk, god modules)

### Verified File Metrics
| File | Lines | Methods | Action |
|------|-------|---------|--------|
| storage/sqlite.py | 3,050 | 79 | DECOMPOSE to 9 modules |
| tools/manage_docs.py | 3,410 | 29 | DECOMPOSE to 12 modules |
| storage/postgres.py | 260 | 18 | COMPLETE to 31 methods |
| storage/base.py | 400 | 31 | REFERENCE (ABC) |
| server.py | 957 | 13+4 | SLIM DOWN |
| reminders.py | 418 | 7+3 | WIRE UP |
| utils/reminder_engine.py | 563 | 19+4 | KEEP |

---
Batch
Batch
