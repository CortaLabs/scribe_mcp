---
id: scribe_pro_cleanup-checklist
title: Acceptance Checklist -- scribe_pro_cleanup
doc_name: checklist
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

# Acceptance Checklist -- scribe_pro_cleanup
**Author:** ArchitectAgent-ProCleanup (Opus 4.6)
**Revised by:** ArchitectAgent-FinalPolish (Opus 4.6)
**Version:** v1.1 (post-review revision)
**Status:** Approved (all 5 blocking fixes + 6 recommendations incorporated)
**Last Updated:** 2026-02-06 09:14 UTC

> Granular phase-by-phase verification checklist with pass/fail criteria, verification commands, and proof requirements. Each item maps to a task package in PHASE_PLAN.md.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [ ] Architecture guide finalized (proof: ARCHITECTURE_GUIDE.md >= 20KB with all 10 sections) <!-- ID: doc_arch -->
- [ ] Phase plan finalized (proof: PHASE_PLAN.md >= 30KB with all 10 phases) <!-- ID: doc_phase -->
- [ ] Checklist finalized (proof: CHECKLIST.md with items for all 10 phases) <!-- ID: doc_checklist -->
- [ ] All research documents indexed (proof: research/INDEX.md lists 8 documents) <!-- ID: doc_research -->

---
## Phase 1: Immediate Cleanup
<!-- ID: phase_0 -->

### P1.1 Root Directory Junk Deletion
- [ ] Broken pip artifacts deleted: `ls =0.1.0 =1.7.0 =1.20.0 =2.0.0 2>/dev/null` returns nothing <!-- ID: p1_pip_artifacts -->
- [ ] Broken file artifacts deleted: `ls None None.journal None.lock None.journal.lock 2>/dev/null` returns nothing <!-- ID: p1_none_artifacts -->
- [ ] Temp state files deleted: `ls tmp_state*.json 2>/dev/null` returns nothing <!-- ID: p1_temp_state -->
- [ ] Backup files deleted: `ls *.bak old_agents.md 2>/dev/null` returns nothing <!-- ID: p1_backups -->
- [ ] Debug script deleted: `ls debug_append_entry.py 2>/dev/null` returns nothing <!-- ID: p1_debug -->
- [ ] Code dump deleted: `ls scribe_mcp_fullcode.txt 2>/dev/null` returns nothing <!-- ID: p1_codedump -->
- [ ] Lock artifacts deleted: `ls TOKEN_OPTIMIZATION_LOG.md.journal .lock .journal.lock 2>/dev/null` returns nothing <!-- ID: p1_locks -->
- [ ] Misplaced test files moved to tests/: `ls test_*.py` in root returns nothing <!-- ID: p1_test_files -->
- [ ] Implementation reports moved to docs/: all IMPLEMENTATION_REPORT and BUG_FIX_REPORT files in docs/ <!-- ID: p1_reports -->

### P1.2 Preflight Backup and Test Data Cleanup
- [ ] Preflight backups deleted: `find . -name '*.preflight-*.bak' | wc -l` returns 0 <!-- ID: p1_preflight -->
- [ ] tmp_tests/ deleted: `test -d tmp_tests && echo EXISTS || echo GONE` returns GONE <!-- ID: p1_tmp_tests -->
- [ ] Zone.Identifier files deleted: `find . -name '*Zone.Identifier' | wc -l` returns 0 <!-- ID: p1_zone_id -->
- [ ] Patterns added to .gitignore: `grep 'preflight' .gitignore` returns match <!-- ID: p1_gitignore -->
- [ ] Git tracking cleaned: `git status` shows no untracked files matching cleanup patterns <!-- ID: p1_git_clean -->

### P1.3 Dead Code File Deletion
- [ ] db/ops.py deleted: `test -f db/ops.py && echo EXISTS || echo GONE` returns GONE <!-- ID: p1_dead_ops -->
- [ ] db/pool.py deleted: `test -f db/pool.py && echo EXISTS || echo GONE` returns GONE <!-- ID: p1_dead_pool -->
- [ ] db/init.sql preserved: `test -f db/init.sql && echo EXISTS || echo GONE` returns EXISTS <!-- ID: p1_keep_init -->
- [ ] storage/pool.py preserved (active): `test -f storage/pool.py && echo EXISTS || echo GONE` returns EXISTS <!-- ID: p1_keep_storage_pool -->
- [ ] Baseline test suite passes: `pytest tests/ --tb=short` exit code 0 <!-- ID: p1_tests -->

### P1 Exit Gate
- [ ] Zero junk files in root: `find . -maxdepth 1 -name '*.bak' -o -name 'None*' -o -name 'tmp_state*' -o -name 'debug_*' -o -name 'test_*.py' | wc -l` returns 0 <!-- ID: p1_exit -->

---
## Phase 2: Centralized Logging + Security Fixes
<!-- ID: phase_1 -->

### P2.1 Logging Infrastructure
- [ ] config/logging.py exists with LOGGING_CONFIG: `test -f config/logging.py && echo EXISTS` <!-- ID: p2_logging_file -->
- [ ] configure_logging() callable: `python -c "from scribe_mcp.config.logging import configure_logging; configure_logging()"` succeeds <!-- ID: p2_logging_call -->
- [ ] SCRIBE_LOG_LEVEL respected: setting to ERROR suppresses WARNING messages <!-- ID: p2_log_level -->

### P2.2 Print/Stderr Batch 1 (Critical Path)
- [ ] server.py clean: `grep -c 'print(' server.py` returns 0 <!-- ID: p2_print_server -->
- [ ] storage/sqlite.py clean: `grep -c 'print(' storage/sqlite.py` returns 0 <!-- ID: p2_print_sqlite -->
- [ ] config/settings.py clean: `grep -c 'print(' config/settings.py` returns 0 <!-- ID: p2_print_settings -->
- [ ] Each file has `import logging; logger = logging.getLogger(__name__)` <!-- ID: p2_logger_setup -->

### P2.3 Print/Stderr Batch 2 (Tools and Utils)
- [ ] All production code clean: `grep -rn 'print(' --include='*.py' tools/ utils/ shared/ state/ bridges/ storage/ config/ | grep -v '# noqa' | wc -l` returns 0 <!-- ID: p2_print_all -->
- [ ] scripts/ print() calls preserved (intentional CLI output) <!-- ID: p2_scripts_keep -->
- [ ] Test suite passes after conversion: `pytest tests/ --tb=short` exit code 0 <!-- ID: p2_tests_batch2 -->

### P2.4 Security: Symlink Path Traversal Fix
- [ ] read_file.py: boundary check BEFORE Path.resolve() (code review lines 1754-1760) <!-- ID: p2_symlink_read -->
- [ ] edit_file.py: boundary check BEFORE Path.resolve() (code review lines 215-221) <!-- ID: p2_symlink_edit -->
- [ ] search.py: boundary check BEFORE Path.resolve() (code review lines 651-659) <!-- ID: p2_symlink_search -->
- [ ] Dotdot component check on unresolved path <!-- ID: p2_dotdot_check -->
- [ ] Symlink escape test exists and passes: `pytest tests/test_read_file*.py -k symlink` <!-- ID: p2_symlink_test -->

### P2.5 Security: Log Injection Sanitization
- [ ] _sanitize_log_field() exists in shared/logging_utils.py: strips newline, carriage return, null <!-- ID: p2_sanitize_fn -->
- [ ] compose_log_line() calls _sanitize_log_field on agent, project_name, message <!-- ID: p2_sanitize_call -->
- [ ] Injection test passes: injected newline produces single log line <!-- ID: p2_injection_test -->

### P2 Exit Gate
- [ ] Zero print/stderr in production: `grep -rn 'print(' --include='*.py' tools/ utils/ shared/ state/ bridges/ storage/ config/ server.py | grep -v '# noqa' | wc -l` returns 0 <!-- ID: p2_exit_print -->
- [ ] Symlink escape blocked (tested) <!-- ID: p2_exit_symlink -->
- [ ] Full test suite passes: `pytest tests/ --tb=short` exit code 0 <!-- ID: p2_exit_tests -->

---
## Phase 3: Dead Code Removal + Error Handling
<!-- ID: phase_2 -->

### P3.1 Bare Except Fix
- [x] Zero bare except in production: `grep -rn 'except:$' --include='*.py' tools/ utils/ storage/ shared/ config/ | wc -l` returns 0 <!-- ID: p3_bare_all -->
- [x] All 14 bare except clauses replaced with specific exception types <!-- ID: p3_bare_count -->
- [x] Each replaced clause includes `logger.error("...", exc_info=True)` <!-- ID: p3_bare_logging -->
- [x] Test suite passes: `pytest tests/ --tb=short` exit code 0 <!-- ID: p3_bare_tests -->

### P3.2 Preflight Backup Retention Policy
- [x] 3-backup retention limit implemented in centralized preflight backup helper <!-- ID: p3_retention_impl -->
- [x] After 5 edits to same file, only 3 .bak files remain <!-- ID: p3_retention_verify -->
- [x] Cleanup logged via logger.debug() <!-- ID: p3_retention_logging -->
- [x] `pytest tests/test_manage_docs*.py` passes <!-- ID: p3_retention_test -->

### P3.3 Dead Code File Deletion (Additional -- review fix #5)
- [x] utils/optimization.py deleted: `test -f utils/optimization.py && echo EXISTS || echo GONE` returns GONE <!-- ID: p3_optimization_deleted -->
- [x] utils/__init__.py import removed: `grep -n 'optimization' utils/__init__.py` returns 0 <!-- ID: p3_optimization_import -->
- [x] No runtime breakage: `pytest tests/` passes <!-- ID: p3_optimization_tests -->

### P3 Exit Gate
- [x] Zero bare except in production code <!-- ID: p3_exit_bare -->
- [x] Preflight backup bounded to 3 per file <!-- ID: p3_exit_retention -->
- [x] utils/optimization.py dead code deleted <!-- ID: p3_exit_optimization -->

---
## Phase 4: Storage Layer Decomposition
<!-- ID: phase_3 -->

### P4.1 Subpackage Structure + internals.py
- [x] storage/sqlite/ directory exists with __init__.py <!-- ID: p4_dir -->
- [x] storage/sqlite/internals.py contains SQLiteInternals class <!-- ID: p4_internals -->
- [x] Methods extracted: _execute, _fetchall, _fetchone, setup, close (and sync variants) <!-- ID: p4_methods -->
- [x] `from scribe_mcp.storage.sqlite import SQLiteStorage` works <!-- ID: p4_import -->

### P4.2 Extract schema.py
- [ ] storage/sqlite/schema.py exists with all CREATE TABLE statements <!-- ID: p4_schema_file -->
- [ ] Schema module under 500 lines: `wc -l storage/sqlite/schema.py` <!-- ID: p4_schema_size -->
- [ ] Fresh DB creation works from schema functions <!-- ID: p4_schema_fresh -->

### P4.3 Extract migrations.py
- [ ] storage/sqlite/migrations.py exists <!-- ID: p4_migrations_file -->
- [ ] run_all_migrations() orchestrator function present <!-- ID: p4_migrations_run -->
- [ ] Fresh DB: migrations run without error <!-- ID: p4_migrations_fresh -->
- [ ] Existing DB: migrations skip completed ones <!-- ID: p4_migrations_skip -->

### P4.4 Domain Modules (projects, entries, sessions)
- [ ] storage/sqlite/projects.py: upsert, fetch, list, delete, update <!-- ID: p4_projects -->
- [ ] storage/sqlite/entries.py: insert, fetch_recent, query, count, cleanup, archive <!-- ID: p4_entries -->
- [ ] storage/sqlite/sessions.py: upsert, fetch, update, list, record, cleanup <!-- ID: p4_sessions -->
- [ ] Each module under 500 lines <!-- ID: p4_domain_size -->

### P4.5 Domain Modules (documents, planning, telemetry)
- [ ] storage/sqlite/documents.py: section CRUD, FTS5 search, sync status <!-- ID: p4_documents -->
- [ ] storage/sqlite/planning.py: dev plans, phases, milestones, benchmarks <!-- ID: p4_planning -->
- [ ] storage/sqlite/telemetry.py: tool calls, reminder history, report cards, bridges <!-- ID: p4_telemetry -->
- [ ] Each module under 400 lines <!-- ID: p4_extended_size -->

### P4.6 Cleanup and Final Verification
- [ ] Old storage/sqlite.py deleted or reduced to import-only facade <!-- ID: p4_old_deleted -->
- [ ] Factory updated: `from scribe_mcp.storage import create_storage_backend` works <!-- ID: p4_factory -->
- [ ] No file in storage/sqlite/ exceeds 800 lines <!-- ID: p4_size_limit -->
- [ ] FULL test suite passes: `pytest tests/ --tb=short` exit code 0 <!-- ID: p4_full_tests -->

### P4 Exit Gate
- [ ] storage/sqlite.py (3050-line monolith) eliminated <!-- ID: p4_exit_monolith -->
- [ ] 9 focused modules in storage/sqlite/ <!-- ID: p4_exit_count -->
- [ ] All modules under 800 lines <!-- ID: p4_exit_size -->
- [ ] Zero import errors in test suite <!-- ID: p4_exit_tests -->

---
## Phase 5: Doc Management Decomposition
<!-- ID: phase_4 -->

### P5.1 doc_management/ Shared Modules (review recommendation #6)
- [ ] doc_management/healing.py exists: param normalization, healing info (under 300 lines) <!-- ID: p5_healing -->
- [ ] doc_management/validation.py exists: path safety, action validation (under 300 lines) <!-- ID: p5_validation -->
- [ ] doc_management/utils.py exists: hashing, parsing, section splitting (under 300 lines) <!-- ID: p5_utils -->
- [ ] doc_management/preflight.py exists: backup creation with 3-backup retention (under 300 lines) <!-- ID: p5_preflight -->
- [ ] doc_management/indexing.py exists: vector chunking, entry IDs, index updates (under 300 lines) <!-- ID: p5_indexing -->
- [ ] `pytest tests/test_manage_docs*.py` passes <!-- ID: p5_shared_tests -->

### P5.2 doc_management/actions/ Modules
- [ ] doc_management/actions/ directory exists <!-- ID: p5_actions_dir -->
- [ ] create.py: research, bug, custom, agent_card, review creation <!-- ID: p5_create -->
- [ ] edit.py: replace_section, replace_range, replace_text, apply_patch <!-- ID: p5_edit -->
- [ ] append.py: append action <!-- ID: p5_append -->
- [ ] status.py: status_update, checklist management <!-- ID: p5_status -->
- [ ] search.py: vector + text search <!-- ID: p5_search -->
- [ ] query.py: list_sections, list_checklist_items, normalize_headers, toc, crosslinks <!-- ID: p5_query -->
- [ ] batch.py: batch action <!-- ID: p5_batch -->
- [ ] Each action module under 500 lines <!-- ID: p5_action_size -->

### P5.3 Slim Down tools/manage_docs.py to Thin Router
- [ ] ACTION_ROUTER dict maps action names to doc_management/ handlers <!-- ID: p5_router -->
- [ ] Deprecated routes work: create_research_doc, create_bug_report, create_doc <!-- ID: p5_deprecated -->
- [ ] manage_docs_main() accessible from server.py at same import path <!-- ID: p5_main_fn -->
- [ ] tools/manage_docs.py under 300 lines (thin router only) <!-- ID: p5_thin_router -->
- [ ] All 7 primary actions work end-to-end <!-- ID: p5_all_actions -->
- [ ] FULL test suite: `pytest tests/test_manage_docs*.py` passes <!-- ID: p5_full_tests -->

### P5 Exit Gate
- [ ] tools/manage_docs.py reduced to thin router (~200 lines) <!-- ID: p5_exit_monolith -->
- [ ] 12 new modules in doc_management/ <!-- ID: p5_exit_count -->
- [ ] All modules under 800 lines <!-- ID: p5_exit_size -->
- [ ] All manage_docs actions verified working <!-- ID: p5_exit_actions -->

---
## Phase 6: src/ Layout Migration + Packaging
<!-- ID: phase_5 -->

### P6.1 config/paths.py + pyproject.toml
- [ ] config/paths.py exists with all 8 path functions <!-- ID: p6_paths_file -->
- [ ] All path functions use importlib.resources with __file__ fallback (review fix #2) <!-- ID: p6_importlib -->
- [ ] Editable install tested: `pip install -e .` works on Python 3.10+ <!-- ID: p6_editable_install -->
- [ ] Non-editable install tested: `pip install .` works (wheel) <!-- ID: p6_wheel_install -->
- [ ] Environment variable overrides work (SCRIBE_DATA_DIR, SCRIBE_DB_PATH) <!-- ID: p6_env_vars -->
- [ ] pyproject.toml exists with metadata, deps, console scripts, find where=src <!-- ID: p6_pyproject -->
- [ ] `pip install -e . --dry-run` succeeds <!-- ID: p6_pip_dryrun -->

### P6.2 Move to src/ Layout
- [ ] src/scribe_mcp/ directory exists with all packages <!-- ID: p6_src_dir -->
- [ ] All 14+ packages moved to src/scribe_mcp/ <!-- ID: p6_packages_moved -->
- [ ] tests/ at repo root (not in src/) <!-- ID: p6_tests_root -->
- [ ] `pip install -e .` succeeds <!-- ID: p6_pip_install -->
- [ ] `python -c "from scribe_mcp.server import main"` works <!-- ID: p6_import_test -->
- [ ] `scribe-server --help` works <!-- ID: p6_console_script -->

### P6.3 Fix __file__ Path Resolutions + Hardcoded DB Paths
- [ ] Zero __file__ in production: `grep -rn '__file__' src/scribe_mcp/ --include='*.py' | grep -v test | grep -v '# noqa' | wc -l` returns 0 <!-- ID: p6_no_file_refs -->
- [ ] All 50+ locations use config.paths.* calls <!-- ID: p6_paths_replaced -->
- [ ] sys.path hacks removed from server.py <!-- ID: p6_no_syspath -->
- [ ] reminders.py hardcoded DB path fixed (review fix #1): `grep -n '.scribe/data/scribe.db' src/scribe_mcp/reminders.py` returns 0 <!-- ID: p6_reminders_path -->
- [ ] Zero hardcoded DB paths in production code: `grep -rn '.scribe/data/scribe.db' src/ --include='*.py'` returns 0 <!-- ID: p6_no_hardcoded_db -->

### P6.4 Test Suite Migration
- [ ] conftest.py updated for src/ layout <!-- ID: p6_conftest -->
- [ ] Zero hardcoded paths: `grep -rn '/home/austin' tests/ | wc -l` returns 0 <!-- ID: p6_no_hardcoded -->
- [ ] tests/fixtures/ directory with storage.py and projects.py <!-- ID: p6_fixtures -->
- [ ] `pip install -e ".[dev]" && pytest tests/` all pass <!-- ID: p6_full_tests -->

### P6 Exit Gate
- [ ] Package installable and console scripts work <!-- ID: p6_exit_pip -->
- [ ] Zero __file__ in production code <!-- ID: p6_exit_file -->
- [ ] All tests pass from installed package <!-- ID: p6_exit_tests -->

---
## Phase 7: Database Consolidation + state.json Migration
<!-- ID: phase_6 -->

### P7.1 State Migration Script
- [ ] scripts/migrate_state.py exists and runs: `scribe-migrate` <!-- ID: p7_script -->
- [ ] Reads state.json, inserts via StorageBackend methods <!-- ID: p7_insert_db -->
- [ ] Renames state.json to state.json.migrated <!-- ID: p7_rename -->
- [ ] Idempotent: running twice is safe <!-- ID: p7_idempotent -->

### P7.2 StateManager DB Refactor
- [ ] StateManager.__init__ takes StorageBackend <!-- ID: p7_backend_init -->
- [ ] Zero JSON file ops: `grep -n 'state.json\|json.load\|json.dump' state/manager.py | wc -l` returns 0 <!-- ID: p7_no_json -->
- [ ] get/set_active_project read/write agent_sessions table <!-- ID: p7_state_methods -->
- [ ] Test suite passes <!-- ID: p7_state_tests -->

### P7.3 Fix Hardcoded DB Paths
- [ ] reminders.py uses config.paths.default_db_path() (ALREADY FIXED in P6.3 -- verify it persists) <!-- ID: p7_reminder_path -->
- [ ] Zero hardcoded DB paths: `grep -rn '.scribe/data/scribe.db\|.scribe/scribe.db' src/ --include='*.py' | wc -l` returns 0 <!-- ID: p7_no_hardcoded -->
- [ ] Legacy DBs backed up; empty DB deleted <!-- ID: p7_legacy_cleanup -->

### P7 Exit Gate
- [ ] Single DB path across codebase <!-- ID: p7_exit_single -->
- [ ] state.json eliminated <!-- ID: p7_exit_state -->
- [ ] All tests pass <!-- ID: p7_exit_tests -->

---
## Phase 8: Postgres Full Implementation
<!-- ID: phase_7 -->

### P8.1 Postgres Subpackage + Connection Pool
- [ ] storage/postgres/ mirrors sqlite/ structure <!-- ID: p8_dir -->
- [ ] internals.py with asyncpg.create_pool() <!-- ID: p8_internals -->
- [ ] schema.py with pg_trgm + GIN (not FTS5) <!-- ID: p8_schema -->
- [ ] `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in schema.py (review fix #3) <!-- ID: p8_pg_trgm_ext -->
- [ ] Connection to test Postgres works <!-- ID: p8_connection -->

### P8.2 Missing Methods Batch 1 (7 methods)
- [ ] projects.py: list_projects_by_repo, update_project_docs <!-- ID: p8_projects -->
- [ ] entries.py: count_entries, cleanup_old_entries, archive_entries <!-- ID: p8_entries -->
- [ ] sessions.py: upsert_agent_session, fetch_agent_session <!-- ID: p8_sessions -->
- [ ] Parametrized dual-backend tests pass <!-- ID: p8_batch1_tests -->

### P8.3 Missing Methods Batch 2 (6 methods) + FTS Behavior Contract
- [ ] documents.py: section CRUD + pg_trgm search <!-- ID: p8_documents -->
- [ ] pg_trgm search returns results with normalized score (0-1 float) matching FTS5 contract (review fix #3) <!-- ID: p8_fts_contract -->
- [ ] search_document_sections() threshold parameter works (default 0.3) <!-- ID: p8_fts_threshold -->
- [ ] planning.py: planning operations <!-- ID: p8_planning -->
- [ ] telemetry.py: tool calls, report cards, bridges, reminders <!-- ID: p8_telemetry -->
- [ ] All 31 StorageBackend abstract methods implemented <!-- ID: p8_31_methods -->
- [ ] Parametrized dual-backend FTS tests verify identical result sets for common queries <!-- ID: p8_fts_dual_test -->

### P8.4 Migration System
- [ ] migrations.py with information_schema (not PRAGMA) <!-- ID: p8_migrations -->
- [ ] Fresh and existing Postgres DB migrations work <!-- ID: p8_migrate_test -->

### P8 Exit Gate
- [ ] 31/31 methods implemented <!-- ID: p8_exit_parity -->
- [ ] Dual-backend tests pass <!-- ID: p8_exit_tests -->
- [ ] pg_trgm search works <!-- ID: p8_exit_search -->

---
## Phase 9: Reminder System Wire-Up
<!-- ID: phase_8 -->

### P9.1 Reminder MCP Tools
- [ ] tools/reminder_tools.py with 3 tool functions <!-- ID: p9_file -->
- [ ] query_reminders implemented and tested <!-- ID: p9_query -->
- [ ] configure_reminders implemented and tested <!-- ID: p9_configure -->
- [ ] reset_reminders implemented and tested <!-- ID: p9_reset -->
- [ ] All 3 registered in server.py tool registry <!-- ID: p9_registered -->
- [ ] `list_tools` includes all 3 <!-- ID: p9_list_tools -->
- [ ] tests/test_reminder_tools.py passes <!-- ID: p9_unit_tests -->

### P9.2 Documentation
- [ ] CLAUDE.md lists all 3 reminder tools <!-- ID: p9_claude_md -->
- [ ] Scribe_Usage.md has examples <!-- ID: p9_usage_md -->
- [ ] Tool count updated 18 to 21 <!-- ID: p9_tool_count -->

### P9 Exit Gate
- [ ] 3 reminder MCP tools operational <!-- ID: p9_exit_tools -->
- [ ] Documentation complete <!-- ID: p9_exit_docs -->

---
## Phase 10: Startup Optimization + Test Cleanup + Scaffold
<!-- ID: phase_9 -->

### P10.1 Lazy Tool Loading
- [ ] _TOOL_MODULES dict maps tool names to module paths <!-- ID: p10_tool_map -->
- [ ] __getattr__ deferred import implemented <!-- ID: p10_getattr -->
- [ ] All tools work on first call <!-- ID: p10_tools_work -->

### P10.2 Deferred Startup
- [ ] cleanup_old_entries() moved to background task <!-- ID: p10_deferred_cleanup -->
- [ ] Migration completion cached in memory <!-- ID: p10_migration_cache -->
- [ ] Startup under 2 seconds: `time python -c "from scribe_mcp.server import main"` <!-- ID: p10_startup_time -->

### P10.3 Test Suite Cleanup
- [ ] tests/fixtures/ with storage.py, projects.py <!-- ID: p10_fixtures -->
- [ ] All fixtures use tmp_path <!-- ID: p10_tmp_path -->
- [ ] Autouse DB cleanup fixture <!-- ID: p10_autouse -->

### P10.4 Auth + Transport Scaffold
- [ ] auth/base.py: AuthProvider ABC <!-- ID: p10_auth_base -->
- [ ] auth/api_key.py + auth/jwt_auth.py stubs (NotImplementedError) <!-- ID: p10_auth_stubs -->
- [ ] transport/base.py: TransportProvider ABC <!-- ID: p10_transport_base -->
- [ ] transport/http_sse.py + transport/websocket.py stubs (NotImplementedError) <!-- ID: p10_transport_stubs -->
- [ ] All stubs importable and have docstrings <!-- ID: p10_stub_docs -->
- [ ] `from scribe_mcp.auth.base import AuthProvider` works <!-- ID: p10_auth_import -->
- [ ] `from scribe_mcp.transport.base import TransportProvider` works <!-- ID: p10_transport_import -->

### P10 Exit Gate
- [ ] Startup under 2 seconds <!-- ID: p10_exit_startup -->
- [ ] Test fixtures shared and clean <!-- ID: p10_exit_fixtures -->
- [ ] Auth/transport interfaces defined and importable <!-- ID: p10_exit_scaffold -->

---
## Final Verification
<!-- ID: final_verification -->

Maps to 9 success criteria from ARCHITECTURE_GUIDE.md Section 1.

| # | Criterion | Verification | Status |
|---|-----------|-------------|--------|
| 1 | pip install -e . succeeds | `pip install -e . && scribe-server --help` | [ ] |
| 2 | No file > 800 lines in src/ | `find src/ -name '*.py' -exec wc -l {} + \| awk '$1>800'` empty | [ ] |
| 3 | pytest >= 90% tests pass | Compare pre/post test counts | [ ] |
| 4 | Single DB, state.json gone | `find . -name state.json -not -name '*.migrated'` empty | [ ] |
| 5 | Postgres passes same tests | `pytest tests/ -k postgres` pass | [ ] |
| 6 | 3 reminder tools operational | `list_tools` includes all 3 | [ ] |
| 7 | Zero print/stderr | `grep -r 'print(' src/ --include='*.py' \| grep -v test` returns 0 | [ ] |
| 8 | Zero junk files | Root clean of artifacts | [ ] |
| 9 | Startup < 2 seconds | Instrumented benchmark | [ ] |

### Final Sign-Off
- [ ] All 10 phase exit gates passed <!-- ID: final_all_phases -->
- [ ] All 9 success criteria verified <!-- ID: final_criteria -->
- [ ] No regressions from P1 baseline <!-- ID: final_no_regression -->
- [ ] Milestone tracking table updated with evidence <!-- ID: final_milestones -->
- [ ] Stakeholder sign-off (name + date) <!-- ID: final_signoff -->
- [ ] Retro documented in PHASE_PLAN.md retro_notes <!-- ID: final_retro -->

---

<!-- ID: p1_pip_artifacts -->
- [x] P1 Pip Artifacts | proof=CoderAgent-Phase1 deleted =0.1.0, =1.7.0, =1.20.0, =2.0.0

<!-- ID: p1_none_artifacts -->
- [x] P1 None Artifacts | proof=CoderAgent-Phase1 deleted None, None.journal, None.lock, None.journal.lock

<!-- ID: p1_temp_state -->
- [x] P1 Temp State | proof=CoderAgent-Phase1 deleted tmp_state.json, tmp_state_cli.json, tmp_state_probe.json

<!-- ID: p1_backups -->
- [x] P1 Backups | proof=CoderAgent-Phase1 deleted CLAUDE.md.bak, AGENTS.md.bak, old_agents.md

<!-- ID: p1_debug -->
- [x] P1 Debug | proof=debug_append_entry.py deleted

<!-- ID: p1_codedump -->
- [x] P1 Codedump | proof=scribe_mcp_fullcode.txt deleted

<!-- ID: p1_locks -->
- [x] P1 Locks | proof=TOKEN_OPTIMIZATION_LOG.md.journal and lock files deleted

<!-- ID: p1_test_files -->
- [x] P1 Test Files | proof=4 test files moved to tests/

<!-- ID: p1_reports -->
- [x] P1 Reports | proof=12 reports moved to docs/historical/

<!-- ID: p1_preflight -->
- [x] P1 Preflight | proof=401 preflight backups deleted

<!-- ID: p1_tmp_tests -->
- [x] P1 Tmp Tests | proof=tmp_tests/ directory deleted (~560MB)

<!-- ID: p1_zone_id -->
- [x] P1 Zone Id | proof=67 Zone.Identifier files deleted

<!-- ID: p1_gitignore -->
- [x] P1 Gitignore | proof=11 pattern categories added to .gitignore

<!-- ID: p1_git_clean -->
- [x] P1 Git Clean | proof=~130 files untracked via git rm --cached

<!-- ID: p1_dead_ops -->
- [x] P1 Dead Ops | proof=db/ops.py deleted (435 lines, 0 imports)

<!-- ID: p1_dead_pool -->
- [x] P1 Dead Pool | proof=db/pool.py deleted (15 lines, 0 imports)

<!-- ID: p1_exit -->
- [x] P1 Exit | proof=All P1 tasks complete - 506+ files removed, 4 tests relocated, 12 reports relocated

<!-- ID: p2_logging_file -->
- [x] P2 Logging File | proof=TASK 2.1 created config/logging.py with LOGGING_CONFIG and SCRIBE_LOG_LEVEL support

<!-- ID: p2_logging_call -->
- [x] P2 Logging Call | proof=TASK 2.1 wired configure_logging() into server startup path before logger usage

<!-- ID: p2_log_level -->
- [x] P2 Log Level | proof=TASK 2.1 explicitly implemented SCRIBE_LOG_LEVEL env var (default WARNING)

<!-- ID: p2_print_server -->
- [x] P2 Print Server | proof=TASK 2.2 converted 35 server.py stderr/print calls to logger levels

<!-- ID: p2_print_sqlite -->
- [x] P2 Print SQLite | proof=TASK 2.2 converted storage/sqlite.py print path to logger.warning

<!-- ID: p2_print_settings -->
- [x] P2 Print Settings | proof=TASK 2.2 verified config/settings.py had 0 print calls

<!-- ID: p2_logger_setup -->
- [x] P2 Logger Setup | proof=TASK 2.2/2.3 added module logger setup where missing across converted files

<!-- ID: p2_print_all -->
- [x] P2 Print All | proof=verification log reports 0 production print() calls across tools/utils/shared/state/bridges/storage/config

<!-- ID: p2_scripts_keep -->
- [x] P2 Scripts Keep | proof=verification log preserved intentional CLI prints (manage_docs/tool_logger/reminder_monitoring/template_engine)

<!-- ID: p2_tests_batch2 -->
- [x] P2 Tests Batch2 | proof=post-conversion test run reported 1562 passing and 0 regressions from logging changes

<!-- ID: p2_symlink_read -->
- [x] P2 Symlink Read | proof=TASK 2.4 applied boundary-before-resolve and symlink target checks in tools/read_file.py

<!-- ID: p2_symlink_edit -->
- [x] P2 Symlink Edit | proof=TASK 2.4 applied boundary-before-resolve and symlink target checks in tools/edit_file.py

<!-- ID: p2_symlink_search -->
- [x] P2 Symlink Search | proof=TASK 2.4 applied boundary-before-resolve and symlink target checks in tools/search.py

<!-- ID: p2_dotdot_check -->
- [x] P2 Dotdot Check | proof=TASK 2.4 added unresolved-path dotdot component escape blocking in all 3 file tools

<!-- ID: p2_symlink_test -->
- [x] P2 Symlink Test | proof=security tests added and passing for symlink escape blocking in read_file tool tests

<!-- ID: p2_sanitize_fn -->
- [x] P2 Sanitize Fn | proof=TASK 2.5 added _sanitize_log_field() stripping newline/carriage/null in shared/logging_utils.py

<!-- ID: p2_sanitize_call -->
- [x] P2 Sanitize Call | proof=TASK 2.5 applied sanitization to compose_log_line fields: agent, project_name, message

<!-- ID: p2_injection_test -->
- [x] P2 Injection Test | proof=security tests added/passing for newline log injection prevention in compose_log_line

<!-- ID: p2_exit_print -->
- [x] P2 Exit Print | proof=PHASE 2 verification recorded zero print/stderr in production code paths

<!-- ID: p2_exit_symlink -->
- [x] P2 Exit Symlink | proof=PHASE 2 security completion logged symlink escape protections as complete and tested

<!-- ID: p2_exit_tests -->
- [x] P2 Exit Tests | proof=PHASE 2 complete log recorded 0 regressions with full-suite run (1562 passing)

<!-- ID: p3_bare_all -->
- [x] P3 Bare All | proof=2026-02-11 scan: 0 bare `except:` across tools/utils/storage/shared/config

<!-- ID: p3_bare_count -->
- [x] P3 Bare Count | proof=targeted P3 files remediated with explicit exception handling and logger instrumentation

<!-- ID: p3_retention_impl -->
- [x] P3 Retention Impl | proof=utils/files.py preflight_backup enforces newest-3 retention policy

<!-- ID: p3_retention_verify -->
- [x] P3 Retention Verify | proof=tests/test_preflight_backup.py includes retention window test (3 backups retained)

<!-- ID: p3_optimization_deleted -->
- [x] P3 Optimization Deleted | proof=utils/optimization.py removed and utils/__init__.py exports cleaned

<!-- ID: p3_retention_test -->
- [x] P3 Retention Test | proof=manage_docs patch/create/structured suites green in Phase 3 verification batch

<!-- ID: p3_bare_tests -->
- [x] P3 Bare Tests | proof=2026-02-11 full `pytest tests/` run green (1804 passed, 22 skipped, 7 deselected)

<!-- ID: p3_optimization_tests -->
- [x] P3 Optimization Tests | proof=post-optimization full-suite verification passed with no runtime regressions
