---
id: scribe_pro_cleanup-phase-plan
title: Phase Plan -- scribe_pro_cleanup
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-15 05:34:39 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# Phase Plan -- scribe_pro_cleanup
**Author:** ArchitectAgent-ProCleanup (Opus 4.6)
**Revised by:** ArchitectAgent-FinalPolish (Opus 4.6)
**Version:** v1.1 (post-review revision)
**Status:** Approved (all 5 blocking fixes + 6 recommendations incorporated)
**Last Updated:** 2026-02-11 00:33 UTC

> Ordered execution plan for the Scribe MCP professional cleanup. 10 phases, 6-7 weeks, covering cleanup through packaging. Each phase has scoped task packages executable by Coder agents.

---
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Duration | Risk | Dependencies |
|-------|------|----------|------|-------------|
| P1: Immediate Cleanup | Delete junk, fix .gitignore, remove tmp_tests | 1 day | LOW | None |
| P2: Logging + Security | Centralized logging, symlink fix, log sanitization | 3 days | LOW | None |
| P3: Dead Code Removal | Delete dead code, bare except fixes | 1 day | LOW | None |
| P4: Storage Decomposition | Split sqlite.py (3050 lines) into sqlite/ subpackage | 5 days | HIGH | P2 |
| P5: Doc Management Decomposition | Split manage_docs.py (3410 lines) into subpackage | 4 days | HIGH | P2 |
| P6: src/ Layout + Packaging | Create pyproject.toml, move to src/ layout, path resolution | 4 days | HIGH | P3, P4, P5 |
| P7: DB Consolidation + state.json | Single DB, migrate state.json, fix hardcoded paths | 3 days | MEDIUM | P6 |
| P8: Postgres Full Implementation | Complete all 31 StorageBackend methods for asyncpg | 5 days | MEDIUM | P4, P7 |
| P9: Reminder Wire-Up | 3 MCP tools exposing reminder engine | 2 days | LOW | P7 |
| P10: Startup Optimization + Test Cleanup + Scaffold | Lazy loading, test fixtures, auth/transport interfaces | 3 days | LOW | P6 |

**Total Estimated Duration:** 26-27 days (~5-6 weeks with buffer) -- reduced from 31 days by P4/P5 parallelization

**Ordering Rationale:** Low-risk cleanup first (P1-P3) builds confidence. God module decomposition (P4-P5) must precede src/ migration because moving 3000+ line files creates merge conflicts. Packaging (P6) requires decomposed modules and clean code. DB consolidation (P7) requires new path resolution from P6. Postgres (P8) requires decomposed storage from P4. Reminders (P9) need consolidated DB from P7. Optimization (P10) is final because it depends on stable architecture.

**Parallelization Note (review recommendation #1):** P4 (storage decomposition) and P5 (doc management decomposition) can run in PARALLEL. P4 touches only `storage/sqlite.py` and `storage/sqlite/` modules. P5 touches only `tools/manage_docs.py` and `doc_management/` modules. Zero file overlap confirmed. Running in parallel saves 4-5 days. Coordination requirement: both phases must complete before P6 begins.

**Execution Timeline:**
- Week 1: P1 + P2 (sequential)
- Week 2: P3 + begin P4/P5 (parallel)
- Week 3: Continue P4/P5 (parallel)
- Week 4: P6 (requires P4 + P5 complete)
- Week 5: P7 + P8 (P8 can begin once P4 complete)
- Week 6: P9 + P10

---
## Phase 1 -- Immediate Cleanup
<!-- ID: phase_0 -->

**Objective:** Remove 200+ junk files, fix .gitignore, delete orphaned test data. Professional first impression.

**Duration:** 1 day | **Risk:** LOW | **Dependencies:** None

### Task Package 1.1: Root Directory Junk Deletion

**Scope:** Delete broken pip artifacts, Windows metadata, temp files, debug scripts from root directory
**Files to Modify:** Root directory (delete files), .gitignore (add rules)
**Dependencies:** None

**Specifications:**
1. Delete broken pip artifacts: `=0.1.0`, `=1.7.0`, `=1.20.0`, `=2.0.0`
2. Delete broken file creation artifacts: `None`, `None.journal`, `None.lock`, `None.journal.lock`
3. Delete temp state files: `tmp_state.json`, `tmp_state_cli.json`, `tmp_state_probe.json`
4. Delete backup files: `CLAUDE.md.bak`, `AGENTS.md.bak`, `old_agents.md`
5. Delete debug script: `debug_append_entry.py`
6. Delete code dump: `scribe_mcp_fullcode.txt`
7. Delete lock file artifacts: `TOKEN_OPTIMIZATION_LOG.md.journal`, `.lock`, `.journal.lock`
8. Move misplaced test files to tests/: `test_db_routing.py`, `test_phase3_state_manager.py`, `test_path_resolution_debug.py`, `test_all_tools_phase5.py`
9. Move implementation reports to docs/: 12 report files (IMPLEMENTATION_REPORT_*.md, BUG_FIX_REPORT_*.md, etc.)

**Verification:**
- [ ] `ls *.bak =*.* None* tmp_state* debug_* scribe_mcp_fullcode.txt` returns "No such file"
- [ ] `ls test_*.py` in root returns nothing
- [ ] `pytest tests/` still passes (baseline)

### Task Package 1.2: Preflight Backup and Test Data Cleanup

**Scope:** Delete 100+ .bak files, 560MB tmp_tests/, Zone.Identifier files
**Files to Modify:** .scribe/ tree, tmp_tests/, .claude/skills/

**Specifications:**
1. Delete all preflight backups: `find .scribe/docs/dev_plans -name '*.preflight-*.bak' -delete`
2. Delete entire tmp_tests/ directory: `rm -rf tmp_tests/`
3. Delete Zone.Identifier files: `find . -name '*:Zone.Identifier' -delete`
4. Run `git rm --cached` on all above patterns to remove from git tracking
5. Update .gitignore with additional rules for these patterns

**Verification:**
- [ ] `find . -name '*.preflight-*.bak' | wc -l` returns 0
- [ ] `du -sh tmp_tests/` returns "No such file"
- [ ] `find . -name '*Zone.Identifier' | wc -l` returns 0
- [ ] `git status` shows only deletions, no untracked files matching patterns

### Task Package 1.3: Dead Code File Deletion

**Scope:** Delete confirmed dead code files (0 imports across codebase)
**Files to Modify:** db/ops.py (DELETE), db/pool.py (DELETE)
**Dependencies:** None

**Specifications:**
1. Delete `db/ops.py` (435 lines, 0 imports found)
2. Delete `db/pool.py` (15 lines, 0 imports found -- NOT storage/pool.py which is active)
3. KEEP `db/init.sql` (used by postgres.py line 19)
4. KEEP `db/__init__.py`

**Verification:**
- [ ] `python -c "from scribe_mcp.storage.sqlite import SQLiteStorage"` succeeds
- [ ] `pytest tests/` passes (no import errors)

**Out of Scope:** Do NOT delete reminders.py (it will be wired up in P9)

**Exit Criteria:** Repository has zero junk files. Test suite baseline established. Git history clean.

**Rollback:** `git stash` before starting; `git stash pop` to restore.

---
## Phase 2 -- Centralized Logging + Security Fixes
<!-- ID: phase_1 -->

**Objective:** Replace 115+ print/stderr calls with Python logging. Fix security vulnerabilities. Foundation for all subsequent phases.

**Duration:** 3 days | **Risk:** LOW | **Dependencies:** None

**Key Reference (review recommendation #3):** Comprehensive stderr audit findings are in `RESEARCH_STDERR_AUDIT_FIXED_20260206.md` (535 lines). This document contains: categorized inventory of 1954 print() calls (120-150 in production code), severity-based prioritization, 4-phase implementation plan with specific code examples, and testing strategy. Coders MUST read this research doc before starting P2.

### Task Package 2.1: Logging Infrastructure

**Scope:** Create config/logging.py with dictConfig, SCRIBE_LOG_LEVEL support
**Files to Modify:** config/logging.py (CREATE), server.py (add configure_logging() call)

**Specifications:**
1. Create `config/logging.py` with LOGGING_CONFIG dict
2. Support SCRIBE_LOG_LEVEL env var (default: WARNING)
3. Add `configure_logging()` function called from server.py _startup()
4. Stderr handler with standard formatter
5. Scribe_mcp logger hierarchy

**Verification:**
- [ ] `SCRIBE_LOG_LEVEL=DEBUG python -c "from scribe_mcp.config.logging import configure_logging; configure_logging()"` succeeds
- [ ] Setting SCRIBE_LOG_LEVEL=ERROR suppresses INFO/WARNING messages

### Task Package 2.2: Print/Stderr Conversion (Batch 1 -- Critical Path)

**Scope:** Convert print/stderr in server.py, storage/sqlite.py, config/settings.py
**Files to Modify:** server.py, storage/sqlite.py, config/settings.py

**Specifications:**
1. Add `import logging; logger = logging.getLogger(__name__)` to each file
2. Replace `print(..., file=sys.stderr)` with `logger.info(...)` or `logger.warning(...)`
3. Replace `sys.stderr.write(...)` with `logger.debug(...)` or `logger.warning(...)`
4. Replace bare `print(...)` used for debug output with `logger.debug(...)`
5. KEEP print() calls that are intentional CLI output (scripts/)

**Verification:**
- [ ] `grep -n 'print(' server.py storage/sqlite.py config/settings.py` returns 0 matches
- [ ] MCP server starts without stderr noise when SCRIBE_LOG_LEVEL=WARNING

### Task Package 2.3: Print/Stderr Conversion (Batch 2 -- Tools and Utils)

**Scope:** Convert remaining 100+ print/stderr calls across tools/ and utils/
**Files to Modify:** All files in tools/, utils/, shared/, state/, bridges/

**Specifications:**
1. Same pattern as 2.2 for all remaining files
2. Particular attention to tools/append_entry.py (50+ import chains may have prints)
3. KEEP print() in scripts/ (CLI output)
4. KEEP print() in tests/ (test output)

**Verification:**
- [ ] `grep -rn 'print(' --include='*.py' tools/ utils/ shared/ state/ bridges/ storage/ config/ | grep -v '# noqa'` returns 0
- [ ] `pytest tests/` passes

### Task Package 2.4: Security -- Symlink Path Traversal Fix

**Scope:** Fix path traversal vulnerability in 3 file operation tools
**Files to Modify:** tools/read_file.py (lines 1754-1760), tools/edit_file.py (lines 215-221), tools/search.py (lines 651-659)

**Specifications:**
1. In each file, change order: check boundary BEFORE resolve
2. Add `..` component check on unresolved path
3. Resolve AFTER boundary validation
4. Add test for symlink escape attempt

**Verification:**
- [ ] Create symlink `ln -s /etc/passwd test_symlink` in repo, verify read_file rejects it
- [ ] `pytest tests/test_read_file*.py` passes
- [ ] `pytest tests/test_edit_file.py` passes
- [ ] `pytest tests/test_search*.py` passes

### Task Package 2.5: Security -- Log Injection Sanitization

**Scope:** Sanitize user input in log line composition
**Files to Modify:** shared/logging_utils.py (lines 581-607)

**Specifications:**
1. Add `_sanitize_log_field(value)` function: strip `\n`, `\r`, `\x00`
2. Apply to agent, project_name, and message fields in `compose_log_line()`
3. Add test for injection attempt

**Verification:**
- [ ] Inject `"test\n[FAKE] injected"` as message, verify single log line output
- [ ] `pytest tests/` passes

**Exit Criteria:** Zero print/stderr in production code. Symlink fix verified. Log sanitization verified.

---
## Phase 3 -- Dead Code Removal + Error Handling
<!-- ID: phase_2 -->

**Objective:** Remove confirmed dead code. Fix bare except clauses. Clean error handling.

**Duration:** 1 day | **Risk:** LOW | **Dependencies:** None

### Task Package 3.1: Bare Except Fix

**Scope:** Replace 14 bare `except:` clauses with specific exception types
**Files to Modify:** utils/formatters/entry.py, tools/list_projects.py, tools/set_project.py, tools/query_entries.py, tools/manage_docs.py, tools/read_file.py, tools/get_project.py, tools/config/append_entry_config.py

**Specifications:**
1. Replace `except:` with `except Exception as e:` (minimum)
2. Add logging: `logger.error("...", exc_info=True)` where appropriate
3. Where possible, narrow to specific exceptions (KeyError, ValueError, etc.)
4. NEVER catch BaseException (preserves SystemExit, KeyboardInterrupt)

**Verification:**
- [x] `grep -rn 'except:$' --include='*.py' tools/ utils/` returns 0
- [x] `pytest tests/` passes

### Task Package 3.2: Preflight Backup Retention Policy

**Scope:** Add 3-backup retention limit to centralized preflight backup system used by doc management.
**Files to Modify:** utils/files.py (preflight_backup retention enforcement), doc_management/manager.py (call-site compatibility if needed)

**Specifications:**
1. After creating a new preflight backup, check count of existing backups for same file
2. If count > 3, delete oldest backups
3. Log cleanup via logger.debug()

**Verification:**
- [x] Create 5 edits to same file, verify only 3 .bak files remain
- [x] `pytest tests/test_manage_docs*.py` passes

### Task Package 3.3: Dead Code File Deletion (Additional)

**Scope:** Delete additional dead code files identified during review
**Files to Delete:** utils/optimization.py
**Dependencies:** None

**Specifications:**
1. Delete `utils/optimization.py` (confirmed 0 usage across codebase except utils/__init__.py re-export)
2. Remove `from .optimization import (...)` line from `utils/__init__.py` (line 8)
3. Verify no runtime imports reference optimization functions directly

**Note:** utils/__init__.py re-exports from optimization.py, but search confirmed 0 external callers import these functions from utils/ or utils.optimization. The re-export exists but is never consumed.

**Verification:**
- [x] `test -f utils/optimization.py && echo EXISTS || echo GONE` returns GONE
- [x] `grep -rn 'optimization' --include='*.py' utils/__init__.py` returns 0 (import removed)
- [x] `pytest tests/` passes

**Exit Criteria:** Zero bare except clauses. Preflight backups bounded. Dead code optimization.py deleted.

**Execution Status (2026-02-11):** Phase 3 completed. Fail-hard and DB-first compatibility work closed the remaining regressions, and full validation now passes: `pytest tests/` => 1804 passed, 22 skipped, 7 deselected.

---
## Phase 4 -- Storage Layer Decomposition
<!-- ID: phase_3 -->

**Objective:** Decompose storage/sqlite.py (3,050 lines, 79 methods) into storage/sqlite/ subpackage (9 modules, each under 800 lines).

**Duration:** 5 days | **Risk:** HIGH | **Dependencies:** P2 (logging)

### Task Package 4.1: Create Subpackage Structure + internals.py

**Scope:** Create storage/sqlite/ directory, move low-level DB operations
**Files to Create:** storage/sqlite/__init__.py, storage/sqlite/internals.py
**Files to Modify:** storage/sqlite.py (extract methods)

**Specifications:**
1. Create storage/sqlite/ directory with __init__.py
2. Extract to internals.py: _execute, _fetchall, _fetchone, _execute_sync, _fetchall_sync, _fetchone_sync, setup, close
3. Create SQLiteInternals class that manages connection pool, write lock, db_path
4. SQLiteStorage in __init__.py delegates to SQLiteInternals

**Verification:**
- [x] `from scribe_mcp.storage.sqlite import SQLiteStorage` works
- [x] `pytest tests/test_db_routing.py tests/test_agent_manager.py tests/test_audit_trails.py tests/test_migration_priority_columns.py tests/test_query_entries_db.py -q` passes (16 passed, 1 skipped)

**Execution Status (2026-02-11):** Task Package 4.1 completed. Monolith module was converted into package layout (`storage/sqlite/__init__.py`) and low-level connection/pool operations were extracted into `storage/sqlite/internals.py` via `SQLiteInternals` delegation.

### Task Package 4.2: Extract schema.py

**Scope:** Move all CREATE TABLE and CREATE INDEX statements
**Files to Create:** storage/sqlite/schema.py
**Files to Modify:** storage/sqlite/__init__.py

**Specifications:**
1. Extract all CREATE TABLE IF NOT EXISTS blocks (lines 870-1340)
2. Extract all CREATE INDEX blocks
3. Organize into functions: create_core_tables, create_session_tables, create_planning_tables, create_document_tables, create_telemetry_tables, create_bridge_tables, create_archive_tables, create_fts_tables, create_all_indexes
4. Each function takes execute_fn as parameter

**Verification:**
- [x] `storage/sqlite/schema.py` under 500 lines (`491` lines)
- [x] Database created from scratch works: fresh DB with all tables

**Execution Status (2026-02-11):** Task Package 4.2 completed. Schema bootstrap was extracted to `storage/sqlite/schema.py`, `_initialise()` now delegates via `create_schema(...)`, and fresh/live schema object counts match (32 tables, 68 indexes, 3 triggers).

### Task Package 4.3: Extract migrations.py

**Scope:** Move migration infrastructure and specific migrations
**Files to Create:** storage/sqlite/migrations.py

**Specifications:**
1. Extract: _ensure_column, _ensure_index, _migration_completed, _mark_migration_complete
2. Extract all specific migration functions (lines 1345-1480)
3. Extract backfill functions
4. Create run_all_migrations(execute_fn, fetchone_fn) orchestrator

**Verification:**
- [x] Fresh DB: migrations run without error
- [x] Existing DB: migrations skip already-completed ones

**Execution Status (2026-02-11):** Task Package 4.3 completed. Tracked migration orchestration was extracted to `storage/sqlite/migrations.py` (`run_all_migrations`, migration state helpers, column/index ensure helpers), and `SQLiteStorage._initialise()` now delegates migration execution through the module while preserving idempotent behavior on existing DBs.

### Task Package 4.4: Extract Domain Modules (projects, entries, sessions)

**Scope:** Move CRUD operations to domain-specific modules
**Files to Create:** storage/sqlite/projects.py, storage/sqlite/entries.py, storage/sqlite/sessions.py

**Specifications:**
1. projects.py: upsert_project, fetch_project, fetch_project_sync, list_projects, list_projects_by_repo, delete_project, update_project_docs, update_project_lifecycle, record_project_access
2. entries.py: insert_entry, fetch_recent_entries, query_entries, count_entries, cleanup_old_entries, archive_entries, fetch_entry_by_id
3. sessions.py: upsert_agent_session, fetch_agent_session, update_session_project, list_agent_sessions, record_agent_project_event, fetch_recent_projects, cleanup_stale_sessions
4. Each function takes execute_fn/fetchall_fn/fetchone_fn as first parameter
5. SQLiteStorage facade delegates to these functions

**Verification:**
- [x] Each module under 500 lines (`projects.py=251`, `entries.py=451`, `sessions.py=449`)
- [x] `pytest tests/test_tools.py` passes (revalidated as part of integration and full-suite runs)

**Execution Status (2026-02-11):** Task Package 4.4 completed. Added `storage/sqlite/projects.py`, `storage/sqlite/entries.py`, and `storage/sqlite/sessions.py`, then converted `SQLiteStorage` project/entry/session methods into thin delegates. Validation gates passed after extraction: focused CRUD/session regressions (`27 passed`), integration bundle (`62 passed`), expanded routing/storage set (`47 passed`), and full suite (`1823 passed, 5 skipped, 7 deselected`).

### Task Package 4.5: Extract Domain Modules (documents, planning, telemetry)

**Scope:** Move remaining domain operations
**Files to Create:** storage/sqlite/documents.py, storage/sqlite/planning.py, storage/sqlite/telemetry.py

**Specifications:**
1. documents.py: Document section CRUD, FTS5 search, document changes, sync status
2. planning.py: Dev plans, phases, milestones, benchmarks, checklists, performance metrics
3. telemetry.py: Tool calls, reminder history, report cards, bridges
4. Same function-level extraction pattern as 4.4

**Verification:**
- [x] Each module under 400 lines (`documents.py=60`, `planning.py=308`, `telemetry.py=398`)
- [x] Old storage/sqlite.py deleted or reduced to import-only facade
- [x] `pytest tests/` passes -- FULL suite (`1823 passed, 5 skipped, 7 deselected`)

**Execution Status (2026-02-11):** Task Package 4.5 completed. Added `storage/sqlite/documents.py`, `storage/sqlite/planning.py`, and `storage/sqlite/telemetry.py`, then extracted remaining heavy facade method groups out of `storage/sqlite/__init__.py` into `storage/sqlite/domain_facade.py` and moved telemetry helper SQL into `storage/sqlite/telemetry_support.py` to satisfy module size gates while preserving behavior.

### Task Package 4.6: Cleanup and Final Verification

**Scope:** Delete old sqlite.py, verify all imports, run full test suite
**Files to Modify:** storage/__init__.py (update factory import), delete storage/sqlite.py

**Specifications:**
1. Verify storage/sqlite/__init__.py is the complete facade
2. Update storage/__init__.py factory to import from storage.sqlite
3. Delete old storage/sqlite.py
4. Verify no file in storage/sqlite/ exceeds 800 lines

**Verification:**
- [x] `wc -l storage/sqlite/*.py` -- all under 800
- [x] `pytest tests/` -- FULL pass (`1823 passed, 5 skipped, 7 deselected in 267.55s`)
- [x] `from scribe_mcp.storage import create_storage_backend` works (`PYTHONPATH=.. python -c "from scribe_mcp.storage import create_storage_backend; print(callable(create_storage_backend))"` => `True`)

**Execution Status (2026-02-11):** Task Package 4.6 completed. `storage/sqlite.py` remains eliminated, `storage/sqlite/__init__.py` is now a 433-line facade/bootstrapping entrypoint, and all package modules are below the 800-line cap.

**Exit Criteria:** storage/sqlite.py eliminated. Modularized storage/sqlite package finalized (13 focused modules), all under 800 lines. All tests pass.

**Rollback:** Git branch per task package. Revert branch if integration tests fail.

---
## Phase 5 -- Doc Management Decomposition
<!-- ID: phase_4 -->

**Objective:** Push logic from tools/manage_docs.py (3,410 lines, 29 functions) into doc_management/ backend engine submodules. Reduce tools/manage_docs.py to a thin MCP routing layer (~200 lines).

**ARCHITECTURE NOTE (review recommendation #6):** `doc_management/` is the existing backend engine. `tools/manage_docs.py` is the MCP tool interface. The decomposition moves action logic FROM the tool file INTO `doc_management/` -- they are ONE system, not two.

**Duration:** 4 days | **Risk:** HIGH | **Dependencies:** P2 (logging)

**Can run in PARALLEL with P4** (review recommendation #1) -- P4 touches storage/sqlite.py, P5 touches tools/manage_docs.py and doc_management/. Zero file overlap.

### Task Package 5.1: Create doc_management/ Shared Modules

**Scope:** Create shared utility modules in doc_management/ for extracted logic
**Files to Create:** doc_management/healing.py, doc_management/validation.py, doc_management/utils.py, doc_management/preflight.py, doc_management/indexing.py

**Specifications:**
1. healing.py: Extract _normalize_metadata_with_healing (line 93), _heal_manage_docs_parameters (line 120), _add_healing_info_to_response (line 317), _coerce_line_number (line 243)
2. utils.py: Extract _hash_text (332), _parse_int (465), _split_into_sections (341), _split_section (356), _build_special_metadata (777), _resolve_custom_doc_path (1023), _parse_numeric_grade (863)
3. preflight.py: Extract backup creation/cleanup with 3-backup retention
4. indexing.py: Extract _chunk_text_for_vector (337), _generate_doc_entry_id (402), _get_index_updater_for_path (2892), _should_skip_doc_index (431), _get_vector_search_defaults (445), _is_rotated_log_filename (423)
5. validation.py: Extract path safety, action validation logic

**Verification:**
- [x] Each module under 300 lines (`healing.py=251`, `validation.py=52`, `utils.py=198`, `preflight.py=86`, `indexing.py=295`)
- [x] `pytest tests/test_manage_docs*.py tests/test_template_engine_manage_docs.py -q` passes (`69 passed in 4.47s`)

**Execution Status (2026-02-11):** Task Package 5.1 completed. Shared modules were created and wired into `tools/manage_docs.py` via delegated helpers for parameter healing, metadata normalization, preflight index/file safeguards, custom doc path resolution, numeric grade parsing, special metadata construction, vector indexing operations, and special index updater selection. Runtime verification of `status_update` behavior remains intentionally deferred until MCP reboot per active operator direction.

### Task Package 5.2: Create doc_management/actions/ Modules

**Scope:** Create actions/ subdirectory in doc_management/ with one module per action group
**Files to Create:** doc_management/actions/__init__.py, actions/create.py, actions/edit.py, actions/append.py, actions/status.py, actions/search.py, actions/query.py, actions/batch.py

**Specifications:**
1. create.py: create action handler (research, bug, custom, agent_card, review docs)
2. edit.py: replace_section, replace_range, replace_text, apply_patch handlers
3. append.py: append action handler
4. status.py: status_update handler, checklist management
5. search.py: search action handler (vector + text)
6. query.py: list_sections, list_checklist_items, normalize_headers, generate_toc, validate_crosslinks
7. batch.py: batch action handler

**Verification:**
- [x] Each action module under 500 lines (`create=80`, `edit=331`, `append=14`, `status=14`, `search=208`, `query=265`, `batch=65`)
- [ ] Every manage_docs action works: create, replace_section, append, status_update, search, list_sections, batch

**Execution Status (2026-02-11, in progress):** `doc_management/actions/` now contains active handlers for create/query/batch/search/edit plus append/status wrappers. Query-transform actions (`normalize_headers`, `generate_toc`, `validate_crosslinks`) are now routed via `query.py` (`handle_query_transform_actions`) into the shared edit pipeline, so query-domain routing is no longer split between modules. `tools/manage_docs.py` dispatch remains module-first and now uses explicit action routing while preserving backward-compat helper wrappers for test-imported internals (`_chunk_text_for_vector`, `_resolve_semantic_limits`, `_should_skip_doc_index`). Current 5.2 remaining gap is explicit end-to-end runtime verification post-reboot.

### Task Package 5.3: Slim Down tools/manage_docs.py to Thin Router

**Scope:** Reduce tools/manage_docs.py to thin MCP routing layer; logic delegates to doc_management/
**Files to Modify:** tools/manage_docs.py (slim from 3410 to ~200 lines)

**Specifications:**
1. tools/manage_docs.py retains ONLY: manage_docs_main() entry point, ACTION_ROUTER dict, MCP parameter extraction
2. ACTION_ROUTER maps action names to doc_management/actions/ handlers
3. Include deprecated action routes (create_research_doc, create_bug_report, create_doc)
4. manage_docs_main() (used by server.py) still accessible at same import path
5. All business logic now lives in doc_management/ submodules

**Verification:**
- [x] `wc -l tools/manage_docs.py` -- under 300 lines (`246`)
- [x] `wc -l` extracted module checks -- all under 800 (`tools/manage_docs.py=246`, `runtime.py=543`, `special_create.py=541`, `special_indexes.py=430`, action max `331`, shared max `295`)
- [x] `pytest tests/test_manage_docs*.py tests/test_template_engine_manage_docs.py -q` -- FULL pass (`71 passed`) + `pytest tests/test_auto_registration*.py -q` (`12 passed`)
- [x] All 7 primary actions + deprecated routes work (verified post-reboot in live MCP runtime incl. wildcard search doc='all'/'*')

**Execution Status (2026-02-11, in progress):** Completed the final routerization pass by extracting manage_docs runtime orchestration into `doc_management/runtime.py` and slimming `tools/manage_docs.py` to `246` lines (`742 -> 246` in this slice; `2348 -> 246` across the larger pass sequence). `tools/manage_docs.py` now serves as a thin MCP router with preserved compatibility wrappers/imports (`manage_docs`, `_auto_register_document`, `_handle_special_document_creation`, `_chunk_text_for_vector`, `_resolve_semantic_limits`, `_should_skip_doc_index`, `manage_docs_main`) while action execution, healing, context handling, custom-doc resolution, and auto-registration flow run through shared runtime modules. Regression validation passed via `pytest tests/test_manage_docs*.py tests/test_template_engine_manage_docs.py -q` (`71 passed`) and `pytest tests/test_auto_registration*.py -q` (`12 passed`). 5.3 live MCP runtime verification is complete for all 7 primary actions plus wildcard search and fail-hard deprecated alias rejection.

**Exit Criteria:** tools/manage_docs.py reduced to ~200 lines (thin router). 17 extracted/shared modules in doc_management/ for this stream, all under 800 lines. All actions verified working.

---
## Phase 6 -- src/ Layout Migration + Packaging
<!-- ID: phase_5 -->

**Objective:** Ship Scribe as an installable `src/` package with a production-ready CLI that can execute every MCP tool while preserving MCP-equivalent execution context semantics (mode/session/tool guards).

**CRITICAL REQUIREMENT (user mandate):** Fix the MCP_SPINE pathing hackiness. The server MUST boot cleanly from `scribe_mcp/` repo root with no `sys.path.insert` hacks. Introduce a clean package entry point while keeping current MCP launch compatibility (`python -m server`) during migration to avoid mandatory config churn.

**Duration:** 5 days | **Risk:** HIGH | **Dependencies:** P3, P4, P5

### Task Package 6.0: Shared Runtime Dispatch + CLI Session Parity

**Scope:** Extract runtime dispatch/context logic from `server.py` into shared module and reuse from both MCP and CLI.
**Files to Create/Modify:** server.py, shared/tool_runtime.py (new), shared/execution_context.py, scripts/scribe_cli.py (or src/scribe_mcp/cli.py)

**Specifications:**
1. Move tool execution pipeline (context resolution, stable session identity, sentinel/project gating, cached project injection) into reusable runtime callable.
2. MCP server and CLI must invoke tools through the same runtime dispatcher.
3. Add CLI session profile persistence under `.scribe/cli/` (transport_session_id, mode, active project, agent, read-before-edit state).
4. CLI must expose `session show|use|reset` plus direct tool invocation (`scribe <tool> --arg ...`) for all registered MCP tools.
5. Preserve current MCP behavior and keep existing `python -m server` launch path working during transition.

**Verification:**
- [ ] `python -c "from scribe_mcp.server import app; print(bool(app))"` works after dispatcher extraction
- [ ] `scribe tools list` shows all MCP tool names
- [ ] `scribe read_file ...` then `scribe edit_file ...` succeeds in same named CLI session (read-before-edit parity)
- [ ] Sentinel-only and project-only tool guards match MCP behavior

### Task Package 6.1: Create config/paths.py + pyproject.toml

**Scope:** Centralized path resolution module and full packaging configuration
**Files to Create:** config/paths.py, pyproject.toml, src/scribe_mcp/py.typed

**Specifications:**
1. config/paths.py: `package_root()`, `config_data_dir()`, `templates_dir()`, `db_init_sql()`, `user_data_dir()`, `default_db_path()`, `scribe_dir()`, `repo_root()` using `importlib.resources` with safe fallback
2. `user_data_dir()` must honor `SCRIBE_DATA_DIR`; `default_db_path()` must honor `SCRIBE_DB_PATH` and compatibility alias `SCRIBE_SQLITE_PATH`
3. pyproject.toml: metadata, dependencies with `~=` pinning, optional dependencies, console scripts, package-data, setuptools find where=["src"]
4. py.typed marker file for PEP 561

**Verification:**
- [ ] `python -c "from scribe_mcp.config.paths import package_root; print(package_root())"` works
- [ ] `pip install -e . --dry-run` succeeds
- [ ] `pip install .` (wheel build/install) succeeds

### Task Package 6.2: Move to src/ Layout

**Scope:** Create `src/scribe_mcp/` and move all runtime packages
**Files to Modify:** all runtime modules/packages moved under `src/scribe_mcp/`

**Specifications:**
1. Create `src/scribe_mcp/` and move packages: config/, storage/, tools/, state/, shared/, utils/, doc_management/, template_engine/, templates/, bridges/, plugins/, security/, scripts/, db/
2. Move root modules: `server.py`, `reminders.py`, `__init__.py`
3. Keep tests/ at repo root; keep CLAUDE.md, AGENTS.md, README.md, pytest.ini at repo root
4. Add compatibility shims so `python -m server` keeps working until MCP configs are migrated
5. Boot console scripts from installed package path (`scribe-server`, `scribe`)

**Verification:**
- [ ] `pip install -e .` succeeds
- [ ] `python -c "from scribe_mcp.server import main"` works
- [ ] `scribe-server --help` works
- [ ] Legacy launch `python -m server` still works during transition

### Task Package 6.3: Kill Path Hacks + Hardcoded DB Paths

**Scope:** Replace `__file__`/`sys.path` patterns with config.paths and remove hardcoded DB paths before/with src migration
**Files to Modify:** server.py, config/settings.py, config/display_config.py, template_engine/engine.py, template_engine/cli.py, storage/postgres.py, reminders.py, utils/reminder_monitoring.py, utils/rotation_state.py, utils/audit.py, utils/tool_logger.py, and remaining production callsites

**Specifications:**
1. Replace `Path(__file__).resolve().parent.parent` patterns with `config.paths.*`
2. Replace template/config/db-init resolution with `templates_dir()`, `config_data_dir()`, `db_init_sql()`
3. Remove production `sys.path` hacks
4. **CRITICAL (review fix #1):** fix `reminders.py` hardcoded `.scribe/data/scribe.db` to `config.paths.default_db_path()`
5. Remove identical hardcoded path usage in `utils/reminder_monitoring.py`

**Verification:**
- [ ] `grep -rn '__file__\|sys.path.insert\|sys.path.append' src/scribe_mcp/ --include='*.py' | grep -v test | grep -v '# noqa'` returns 0
- [ ] `grep -rn '.scribe/data/scribe.db\|.scribe/scribe.db' src/scribe_mcp/ --include='*.py'` returns 0
- [ ] `pytest tests/` passes (FULL suite)

### Task Package 6.4: Test Suite Migration + Installed-Package Flow

**Scope:** Update tests and fixtures for src layout and installed-package execution
**Files to Modify:** tests/conftest.py and path-dependent tests

**Specifications:**
1. Update conftest/import fixtures for src layout and installed package path
2. Replace hardcoded `/home/austin` usage with tmp_path/fixtures
3. Add/normalize test fixtures under `tests/fixtures/` (storage.py, projects.py)
4. Remove `sys.path` manipulation from tests where possible (allow only minimal conftest bootstrap if required)
5. Add CLI parity tests for session context (`read_file` -> `edit_file`), mode gating, and representative tool execution

**Verification:**
- [ ] `pip install -e ".[dev]" && pytest tests/` all pass
- [ ] `grep -rn '/home/austin' tests/` returns 0
- [ ] `grep -rn 'sys.path.insert\|sys.path.append' tests/ --include='*.py'` returns only approved bootstrap locations
- [ ] CLI parity tests pass in CI/local

**Exit Criteria:** Installable package, working console scripts, CLI can call every MCP tool, session context parity between CLI and MCP runtime, zero production `__file__`/`sys.path` path hacks, zero hardcoded DB paths, full tests passing.

**Rollback:** Keep migration in bounded commits by package. Rollback path: `git revert <commit(s)>`; verification: `pip install -e . && pytest`.

---
## Phase 7 -- Database Consolidation + state.json Migration
<!-- ID: phase_6 -->

**Objective:** Single database, eliminate state.json, fix all hardcoded DB paths.

**Duration:** 3 days | **Risk:** MEDIUM | **Dependencies:** P6

### Task Package 7.1: State Migration Script

**Scope:** Create scripts/migrate_state.py to move state.json data to DB
**Files to Create:** scripts/migrate_state.py

**Specifications:**
1. Read .scribe/state.json
2. Extract project records, session data, agent state
3. Insert into DB via StorageBackend methods (upsert_project, upsert_agent_session)
4. Rename state.json to state.json.migrated
5. Print migration summary (records migrated, errors)
6. Idempotent: can run multiple times safely

**Verification:**
- [ ] `scribe-migrate` runs without error on existing state.json
- [ ] All projects from state.json accessible via get_project
- [ ] state.json.migrated exists, state.json does not

### Task Package 7.2: StateManager DB Refactor

**Scope:** Rewrite StateManager to read/write DB only
**Files to Modify:** state/manager.py

**Specifications:**
1. Remove all JSON file read/write code
2. StateManager.__init__ takes StorageBackend
3. get_active_project() reads from agent_sessions table
4. set_active_project() writes to agent_sessions table
5. All state management goes through StorageBackend

**Verification:**
- [ ] `grep -n 'state.json\|json.load\|json.dump' state/manager.py` returns 0
- [ ] `pytest tests/` passes

### Task Package 7.3: Legacy DB Cleanup + Remaining Hardcoded Paths

**Scope:** Remove legacy DB files, fix any remaining hardcoded paths not caught in P6.3
**Files to Modify:** config/settings.py (if not already done in P6)
**Note:** reminders.py hardcoded DB path is already fixed in P6.3 (review fix #1 -- moved here to prevent P6/P7 dependency gap)

**Specifications:**
1. ~~Fix reminders.py line 31~~ (DONE in P6.3 -- do not duplicate)
2. Back up legacy DBs: .scribe/scribe.db, .scribe/data/scribe.db to .scribe/backups/
3. Delete empty .scribe/data/scribe_projects.db
4. Update config/settings.py default_db_path to use config/paths.py (if not already done in P6.1)
5. Verify no remaining hardcoded DB paths in any production code

**Verification:**
- [ ] `grep -rn '.scribe/data/scribe.db\|.scribe/scribe.db' src/ --include='*.py'` returns 0
- [ ] Reminder system works with centralized DB path (already fixed in P6.3)
- [ ] Legacy DB files moved to backups

**Exit Criteria:** Single DB path. state.json eliminated. Zero hardcoded DB paths.

---
## Phase 8 -- Postgres Full Implementation
<!-- ID: phase_7 -->

### Phase 8 Closure (2026-02-15)

**Completed in this pass:**
- Converted Postgres backend to true package layout at `src/scribe_mcp/storage/postgres/` and removed monolith module.
- Added package modules: `internals.py`, `schema.py`, `migrations.py`, `documents.py`, and wired them into `PostgresStorage`.
- Added dual-backend conformance test suite (`tests/test_storage_backend_conformance.py`) with live Postgres validation via `SCRIBE_TEST_POSTGRES_URL`.
- Verified migration helper idempotence (`_run_migration`, `migrate_add_docs_json_column`, `backfill_docs_json_from_state`) and pg_trgm search behavior against live Postgres.

**Validation evidence:**
- `python -m compileall -q src/scribe_mcp/storage/postgres`
- `SCRIBE_TEST_POSTGRES_URL=<postgres_dsn> pytest tests/test_storage_backend_conformance.py -q` -> `8 passed, 3 skipped`
- `SCRIBE_TEST_POSTGRES_URL=<postgres_dsn> pytest tests/test_db_routing.py tests/test_get_project_integration.py tests/test_query_entries_explicit_project_resolution.py tests/test_database_migration.py tests/test_execution_context.py tests/test_storage_backend_conformance.py -q` -> `47 passed, 3 skipped`

**Phase 8 result:** Exit gate achieved and checklist closed.

### Phase 8 Status Update (2026-02-15, pass 2)

**Additional completions in this pass:**
- Added remaining cross-backend compatibility methods in `PostgresStorage`: `fetch_project_sync`, `migrate_add_docs_json_column`, `backfill_docs_json_from_state`.
- Implemented previously open checklist API gaps: `fetch_agent_session`, `archive_entries`, and document-section APIs (`upsert_document_section`, `get_document_section`, `search_document_sections`, `record_document_change`).
- Verified parity at class surface level: SQLite vs Postgres public methods now report `missing_in_postgres=[]`.
- Re-ran targeted regression tests after edits (`test_db_routing`, `test_get_project_integration`, `test_query_entries_explicit_project_resolution`, `test_database_migration`) with all passing.

**Still open before Phase 8 exit:**
- Stand up/run live Postgres dual-backend conformance tests (including FTS equivalence assertions).
- Complete modular split to `storage/postgres/` package (`internals.py`, `schema.py`, `migrations.py`, domain modules) if we are enforcing structural checklist items literally.
- Validate migration behavior on fresh and pre-existing Postgres databases with tracked proofs.

### Phase 8 Status Update (2026-02-15)

**Completed in this sprint:**
- Replaced broken `storage/postgres.py` `db.ops` shell with direct asyncpg queries for core project/entry/session/runtime paths.
- Expanded `db/init.sql` to include missing session/document/telemetry/archive/migration tables and critical indexes.
- Added runtime-required methods used by tool/runtime/state manager (`upsert_session`, `set/get_session_mode`, `set/get_session_project`, reminder/tool-call/bridge hooks).
- Implemented core parity methods (`upsert_project`, `fetch_project`, `list_projects_by_repo`, `update_project_docs`, `insert_entry`, `fetch_recent_entries`, `query_entries`, `count_entries`, `count_query_entries`, benchmark/planning writers).

**Remaining for Phase 8 exit gate:**
- Finish explicit missing API parity items (`archive_entries`, `fetch_agent_session`, document section CRUD/search parity methods, migration helper parity).
- Build/verify dual-backend conformance tests against live Postgres.
- Validate pg_trgm search behavior contract and threshold behavior against SQLite FTS expectations.

**Objective:** Complete asyncpg implementation with all 31 StorageBackend methods.

**Duration:** 5 days | **Risk:** MEDIUM | **Dependencies:** P4, P7

### Task Package 8.1: Postgres Subpackage Structure + Connection Pool

**Scope:** Create storage/postgres/ subpackage mirroring sqlite/, add asyncpg pool
**Files to Create:** storage/postgres/__init__.py, storage/postgres/internals.py, storage/postgres/schema.py

**Specifications:**
1. Create parallel directory structure to storage/sqlite/
2. internals.py: PostgresInternals class with asyncpg.create_pool()
3. schema.py: Postgres-compatible DDL for all 30+ tables (no FTS5; use pg_trgm + GIN)
4. Maintain PostgresStorage facade in __init__.py

**Verification:**
- [ ] PostgresStorage can connect and create all tables (requires test Postgres instance)

### Task Package 8.2: Implement Missing Methods (Batch 1)

**Scope:** Add 7 missing CRUD methods
**Files to Create:** storage/postgres/projects.py, storage/postgres/entries.py, storage/postgres/sessions.py

**Specifications:**
1. list_projects_by_repo, update_project_docs
2. count_entries, cleanup_old_entries, archive_entries
3. upsert_agent_session, fetch_agent_session

**Verification:**
- [ ] Parametrized tests pass for both SQLite and Postgres on all project/entry/session operations

### Task Package 8.3: Implement Missing Methods (Batch 2)

**Scope:** Add 6 remaining methods + pg_trgm search
**Files to Create:** storage/postgres/documents.py, storage/postgres/planning.py, storage/postgres/telemetry.py

**Specifications:**
1. upsert_document_section, search_document_sections (pg_trgm), record_document_change
2. planning table operations
3. record_tool_call, upsert_report_card, upsert_bridge, record_reminder_history

**Verification:**
- [ ] All 31 StorageBackend abstract methods implemented
- [ ] Dual-backend parametrized test suite passes

### Task Package 8.4: Migration System for Postgres

**Scope:** Port migration tracking to Postgres
**Files to Create:** storage/postgres/migrations.py

**Specifications:**
1. scribe_migrations table for Postgres
2. _ensure_column (using information_schema instead of PRAGMA)
3. _migration_completed / _mark_migration_complete
4. Port all SQLite-specific migrations to Postgres equivalents

**Verification:**
- [ ] Fresh Postgres DB: all migrations run
- [ ] Existing Postgres DB: migrations skip completed ones

**Exit Criteria:** Full feature parity. Dual-backend tests pass. All 31 methods implemented.

---
## Phase 9 -- Reminder System Wire-Up
<!-- ID: phase_8 -->

**Objective:** Expose existing reminder engine to users via 3 MCP tools.

**Duration:** 2 days | **Risk:** LOW | **Dependencies:** P7
**Status (2026-02-15):** COMPLETE

### Task Package 9.1: Create Reminder MCP Tools

**Scope:** Create tools/reminder_tools.py with 3 MCP tool functions
**Files to Create:** tools/reminder_tools.py

**Specifications:**
1. query_reminders(agent, project?, category?, limit, format): Query reminder history and active reminders using reminder_engine.get_reminder_history()
2. configure_reminders(agent, project?, enabled?, cooldown_minutes?, categories?, tone?, format): Modify reminder settings per project
3. reset_reminders(agent, project?, reset_cooldowns, reset_history?, format): Reset cooldowns via reminders.reset_reminder_cooldowns()
4. Each tool returns formatted response matching existing tool patterns
5. Register tools in server.py tool registry

**Verification:**
- [x] `list_tools` response includes query_reminders, configure_reminders, reset_reminders
- [x] query_reminders returns reminder data
- [x] reset_reminders resets cooldown counts
- [x] New tests in tests/test_reminder_tools.py

### Task Package 9.2: Documentation Update

**Scope:** Document reminder tools in CLAUDE.md and skill docs
**Files to Modify:** CLAUDE.md, .codex/skills/scribe-mcp-usage/references/Scribe_Usage.md

**Specifications:**
1. Add reminder tools to CLAUDE.md quick reference table
2. Add usage examples to Scribe_Usage.md
3. Update tool count references (18 to 21 tools)

**Verification:**
- [x] CLAUDE.md lists all 3 reminder tools
- [x] Scribe_Usage.md has usage examples

**Exit Criteria:** 3 reminder MCP tools operational and documented.

---
## Phase 10 -- Postgres Migration Hardening + Runtime Readiness
<!-- ID: phase_9 -->

**Objective:** Complete production Postgres migration for distributed deployment and finish runtime hardening.

**Duration:** 5-7 days | **Risk:** MEDIUM | **Dependencies:** P8, P9

### Track A -- Postgres Migration (Critical Path)

### Task Package 10.A1: Real Database Setup (Schema-Isolated)

**Scope:** Finalize production-ready Postgres schema bootstrap for shared-instance operation.
**Files to Modify:** `src/scribe_mcp/storage/postgres/internals.py`, `src/scribe_mcp/storage/postgres/schema.py`, `src/scribe_mcp/db/init.sql`, `src/scribe_mcp/config/settings.py`

**Specifications:**
## Phase 10 -- Postgres Migration Hardening + Runtime Readiness
<!-- ID: phase_10 -->

**Objective:** Complete production Postgres migration for distributed deployment and finish runtime hardening.

**Duration:** 5-7 days | **Risk:** MEDIUM | **Dependencies:** P8, P9

### Track A -- Postgres Migration (Critical Path)

### Task Package 10.A1: Real Database Setup (Schema-Isolated)

**Scope:** Finalize production-ready Postgres schema bootstrap for shared-instance operation.
**Files to Modify:** `src/scribe_mcp/storage/postgres/internals.py`, `src/scribe_mcp/storage/postgres/schema.py`, `src/scribe_mcp/db/init.sql`, `src/scribe_mcp/config/settings.py`

**Specifications:**
1. Use dedicated schema (`scribe`) instead of `public` for all Scribe tables.
2. Ensure `db/init.sql` creates full SQLite parity table set.
3. Ensure indexes cover high-frequency query paths (timestamps/FKs + JSONB GIN).
4. Ensure required extensions are handled (`pg_trgm` required, `pgvector` optional/non-fatal).

**Verification:**
- [ ] Dedicated schema created and selected via connection search_path
- [ ] All expected Scribe tables present in `scribe.*`
- [ ] JSONB GIN indexes visible in `pg_indexes`

### Task Package 10.A2: SQLite -> Postgres Data Migration Tooling

**Scope:** Implement repeatable migration tooling for all Scribe tables.
**Files to Create:** `src/scribe_mcp/scripts/migrate_sqlite_to_postgres.py`
**Files to Modify:** `pyproject.toml`

**Specifications:**
1. Provide CLI for copy/migrate from SQLite to Postgres (`replace` mode supported).
2. Migrate full table set including high-volume `scribe_entries`.
3. Add built-in row-count integrity verification per table.
4. Preserve timestamps and JSON/metadata fidelity.

**Verification:**
- [ ] Migration CLI runs end-to-end on local dataset
- [ ] Source/target row counts match for migrated tables
- [ ] Re-run is safe and deterministic in replace mode

### Task Package 10.A3: High-Volume Readiness

**Scope:** Prepare for million-row `scribe_entries` growth.
**Files to Modify:** `src/scribe_mcp/db/init.sql`, Postgres migration SQL files
**Files to Create:** Postgres numbered migration SQLs under `src/scribe_mcp/db/postgres_migrations/`

**Specifications:**
1. Add/verify indexes for `read_recent`, `query_entries`, and metadata filters.
2. Document partitioning strategy (monthly range partitioning plan for `scribe_entries`).
3. Validate archival/retention flow for Postgres (`cleanup_old_entries`, archive table path).

**Verification:**
- [ ] Query latency remains acceptable on representative migrated dataset
- [ ] Archive path verified with Postgres backend enabled
- [ ] Partitioning plan documented with implementation-ready steps

### Task Package 10.A4: Remote Pool Tuning + Retry Behavior

**Scope:** Tune asyncpg pool defaults for remote latency and transient network faults.
**Files to Modify:** `src/scribe_mcp/storage/postgres/internals.py`, `src/scribe_mcp/config/settings.py`, `.env.example`

**Specifications:**
1. Defaults target remote deployment (`min_size=2`, `max_size=20`).
2. Add configurable connection timeout and retry/backoff.
3. Keep settings env-driven for VPS deployment overrides.

**Verification:**
- [ ] Pool settings configurable via env vars
- [ ] Startup/connect retry behavior validated against transient failure simulation

### Task Package 10.A5: Backup + Restore Procedure

**Scope:** Document schema-scoped backup/restore workflow.
**Files to Create:** `docs/guides/postgres_backup_restore.md`

**Specifications:**
1. `pg_dump` runbook for schema-only backup in shared Postgres instance.
2. Retention policy: 7 daily + 4 weekly.
3. Restore verification checklist and rollback notes.

**Verification:**
- [ ] Backup commands documented and runnable
- [ ] Restore dry run documented with verification steps

### Task Package 10.A6: Conformance + Soak Validation

**Scope:** Validate Postgres-primary mode under representative load.
**Files to Modify:** `tests/test_storage_backend_conformance.py` (as needed), test docs/checklists

**Specifications:**
1. Re-run backend conformance against real Postgres with migrated data.
2. Validate dual-write behavior (file + Postgres) still intact.
3. Record soak-test plan (48h target) and acceptance metrics.

**Verification:**
- [ ] Conformance suite green with `SCRIBE_TEST_POSTGRES_URL`
- [ ] Dual-write spot checks pass
- [ ] Soak plan and monitoring checklist documented

### Track B -- Runtime Hardening (Adjusted Existing Phase 10)

### Task Package 10.B1: Lazy Tool Loading

**Scope:** Convert tool module bootstrapping to deferred import pattern.
**Files to Modify:** `src/scribe_mcp/tools/__init__.py`, `src/scribe_mcp/server.py`

**Specifications:**
1. Introduce `_TOOL_MODULES` registry and `__getattr__`-based deferred import.
2. Ensure unknown tool calls trigger on-demand module load before dispatch.
3. Preserve tool-list and first-call behavior parity.

**Verification:**
- [ ] Startup import path is lighter than eager-import baseline
- [ ] All tools callable on first request

### Task Package 10.B2: Deferred Startup + Timing

**Scope:** Keep startup path minimal and observable.
**Files to Modify:** `src/scribe_mcp/server.py`, storage init paths as needed

**Specifications:**
1. Keep cleanup/migration/bootstrap tasks in delayed background path.
2. Cache migration state where repeated DB checks are unnecessary.
3. Add startup timing instrumentation and expose in logs.

**Verification:**
- [ ] Startup target < 2 seconds in baseline environment
- [ ] Deferred tasks still execute reliably post-start

### Task Package 10.B3: Test Suite Cleanup

**Scope:** Standardize fixtures and DB cleanup behavior.
**Files to Modify/Create:** `tests/fixtures/__init__.py`, `tests/fixtures/storage.py`, `tests/fixtures/projects.py`, related tests

**Specifications:**
1. Shared fixtures for storage/project setup with explicit teardown.
2. Consistent tmp-path usage (no ad-hoc temp dirs).
3. Autouse cleanup for DB artifacts where needed.

**Verification:**
- [ ] No stray `tmp_tests` directories post-run
- [ ] No hardcoded local absolute paths in tests

### Task Package 10.B4: Auth + Transport Contracts (Upgraded)

**Scope:** Define production-ready interface contracts for remote deployment paths.
**Files to Create:** `src/scribe_mcp/auth/__init__.py`, `src/scribe_mcp/auth/base.py`, `src/scribe_mcp/auth/api_key.py`, `src/scribe_mcp/auth/jwt_auth.py`, `src/scribe_mcp/transport/__init__.py`, `src/scribe_mcp/transport/base.py`, `src/scribe_mcp/transport/http_sse.py`, `src/scribe_mcp/transport/websocket.py`

**Specifications:**
1. `AuthProvider` contract must support authenticate/authorize/revoke semantics used by remote callers.
2. `TransportProvider` contract must support start/stop/send and error/lifecycle expectations.
3. Stubs remain `NotImplementedError` where implementation is deferred, but signatures/docs must be deployment-ready.

**Verification:**
- [ ] Auth/transport base contracts import and type-check
- [ ] Stubs raise `NotImplementedError` with clear action messages

**Exit Criteria:**
- Track A migration and production-readiness items completed with evidence.
- Track B runtime hardening complete.
- Postgres-primary mode is operational with documented backup/restore + soak path.

---
## Milestone Tracking
<!-- ID: milestone_tracking -->
## Milestone Tracking
<!-- ID: milestone_tracking -->

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| Repository Clean (P1) | Week 1 | Codex | Complete | Checklist P1 exit gate marked complete |
| Logging + Security (P2) | Week 1-2 | Codex | Complete | Checklist P2 exit gate marked complete |
| Dead Code Clean (P3) | Week 2 | Codex | Complete | Checklist P3 exit gate marked complete |
| Storage Decomposed (P4) | Week 2-3 | Codex | Complete | Checklist P4 exit gate marked complete |
| Docs Decomposed (P5) | Week 2-3 | Codex | Complete | Checklist P5 exit gate marked complete |
| Packaged + src/ (P6) | Week 4 | Codex | Complete | Checklist P6 exit gate marked complete |
| DB Consolidated (P7) | Week 4-5 | Codex | Complete | Checklist P7 exit gate marked complete |
| Postgres Complete (P8) | Week 5 | Codex | Complete | Live Postgres conformance tests passed |
| Reminders Live (P9) | Week 5-6 | Codex | Complete | Reminder tools implemented + tests passing |
| Optimized + Scaffold (P10) | Week 6 | Codex | Planned | Pending Phase 10 execution |

---
## Retro Notes and Adjustments
<!-- ID: retro_notes -->

- Document lessons learned after each phase.
- If a phase takes longer than estimated, adjust subsequent timelines here.
- Record any scope changes or re-planning decisions.

---
