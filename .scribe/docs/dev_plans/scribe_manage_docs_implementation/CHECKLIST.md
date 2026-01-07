# ✅ Acceptance Checklist — scribe_manage_docs_implementation
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-06 02:04:45 UTC

> Comprehensive verification ledger for BUG-MANAGE-DOCS-001 fix and auto-registration implementation.

---

## Phase 1: Database Schema Migration
<!-- ID: phase_1_checklist -->

**Database Changes:**
- [ ] `docs_json` column added to scribe_projects table (verify: `PRAGMA table_info`)
- [ ] Column is TEXT type, nullable (verify: schema inspection)
- [ ] CREATE TABLE statement updated in storage/sqlite.py:652-659
- [ ] Database backup created before migration (verify: `.scribe/scribe.db.backup` exists)

**Migration Function:**
- [ ] `migrate_add_docs_json_column()` method implemented (verify: storage/sqlite.py)
- [ ] Migration is idempotent (verify: run twice, no errors)
- [ ] Migration checks if column exists before adding (verify: uses PRAGMA table_info)
- [ ] Migration returns True if added, False if exists (verify: return values)
- [ ] Migration errors logged with clear messages (verify: logs)

**Backfill Function:**
- [ ] `backfill_docs_json_from_state()` method implemented (verify: storage/sqlite.py)
- [ ] Backfill loads state.json correctly (verify: reads .scribe/state.json)
- [ ] Backfill skips projects without docs field (verify: handles gracefully)
- [ ] Backfill uses transaction (verify: atomicity)
- [ ] Backfill returns count of projects updated (verify: return value)
- [ ] Backfill populates docs_json for existing projects (verify: SELECT query)

**upsert_project Update:**
- [ ] `docs_json` parameter added to method signature (verify: storage/sqlite.py:48-80)
- [ ] Parameter is optional (default None) for backward compatibility
- [ ] INSERT SQL includes docs_json column (verify: SQL statement)
- [ ] UPDATE SQL includes docs_json column (verify: ON CONFLICT clause)
- [ ] Method works with and without docs_json parameter (verify: tests)

**Verification:**
- [ ] `verify_migration()` method implemented (verify: storage/sqlite.py)
- [ ] Verification asserts docs_json column exists (verify: assertion logic)
- [ ] Verification runs successfully post-migration (verify: no errors)

**Testing:**
- [ ] Unit test: migration adds column on first run (proof: test_migrate_add_docs_json_column)
- [ ] Unit test: migration is idempotent (proof: run twice test)
- [ ] Unit test: backfill populates docs_json (proof: test_backfill_docs_json_from_state)
- [ ] Unit test: upsert_project writes docs_json (proof: test_upsert_project_with_docs_json)
- [ ] Integration test: migration on real database (proof: test_migration_integration)

**Logging:**
- [ ] Migration logged to progress log (proof: grep "Migration" PROGRESS_LOG.md)
- [ ] Backfill count logged (proof: log entry with count)
- [ ] All errors logged with file:line references

---

## Phase 2: Query Integration
<!-- ID: phase_2_checklist -->

**Query Update:**
- [ ] SELECT statement includes docs_json (verify: shared/logging_utils.py:111-119)
- [ ] Query returns 4 fields (name, root, progress_log, docs_json)
- [ ] Query uses parameterized statement (verify: SQL injection safe)
- [ ] `json` module imported (verify: import statement at top of file)

**JSON Parsing:**
- [ ] docs_json parsed with json.loads() (verify: parsing logic)
- [ ] docs field added to session_project dict (verify: dict structure)
- [ ] NULL docs_json handled gracefully (verify: if row["docs_json"] check)
- [ ] Malformed JSON logged as warning (verify: try/except with logger.warning)
- [ ] Malformed JSON doesn't crash (verify: exception handling)
- [ ] Fallback to state.json still works (verify: existing fallback logic intact)

**Caller Integration:**
- [ ] tools/set_project.py receives docs field (verify: test)
- [ ] tools/get_project.py receives docs field (verify: test)
- [ ] tools/list_projects.py receives docs field (verify: test)
- [ ] tools/manage_docs.py receives docs field (verify: test)

**Testing:**
- [ ] Unit test: query returns docs field (proof: test_query_returns_docs_field)
- [ ] Unit test: NULL docs_json handled (proof: test_null_docs_json)
- [ ] Unit test: malformed JSON handled (proof: test_malformed_docs_json)
- [ ] Integration test: all callers receive docs (proof: test_all_callers)
- [ ] Regression test: existing tests still pass (proof: pytest results)

**Logging:**
- [ ] Query integration logged (proof: append_entry with query update)
- [ ] JSON parse warnings logged (proof: logger.warning calls)

---

## Phase 3: Auto-Registration Implementation
<!-- ID: phase_3_checklist -->

**Action Categorization:**
- [ ] EDIT_ACTIONS set defined (verify: tools/manage_docs.py)
- [ ] 9 EDIT actions listed (verify: set contains list_sections, replace_section, apply_patch, replace_range, append, status_update, normalize_headers, generate_toc, search)
- [ ] 2 CREATE actions identified (verify: create_research_doc, create_bug_report)
- [ ] 6 other actions categorized (verify: read/write/context-dependent)

**_resolve_doc_path() Helper:**
- [ ] Function implemented (verify: tools/manage_docs.py)
- [ ] DOC_FILENAMES whitelist defined (verify: dict with 7 standard keys)
- [ ] doc_key validated against whitelist (verify: ValueError if invalid)
- [ ] Path built from project root (verify: uses project["root"])
- [ ] Path includes .scribe/docs/dev_plans/{name}/ (verify: path construction)
- [ ] Path traversal prevented (verify: checks path starts with docs_dir)
- [ ] Returns absolute path as string (verify: return type)

**_auto_register_document() Helper:**
- [ ] Function implemented (verify: tools/manage_docs.py)
- [ ] Calls _resolve_doc_path() (verify: function call)
- [ ] Verifies file exists (verify: Path.exists() check)
- [ ] Raises ValueError if file missing (verify: exception with actionable message)
- [ ] Computes SHA256 hash (verify: hashlib.sha256)
- [ ] Updates database docs_json (verify: upsert_project call with docs_json)
- [ ] Merges with existing docs (verify: preserves other doc keys)
- [ ] Updates ProjectRegistry (verify: record_doc_update call)
- [ ] Logs registration event (verify: append_entry call)

**Auto-Registration Integration:**
- [ ] Check added before action dispatch (verify: if action in EDIT_ACTIONS)
- [ ] Gets active project (verify: get_active_project() call)
- [ ] Checks if doc registered (verify: if doc not in docs)
- [ ] Calls _auto_register_document() (verify: function call)
- [ ] Re-fetches project after registration (verify: second get_active_project() call)
- [ ] Error handling with clear message (verify: try/except with ValueError)
- [ ] EDIT actions trigger auto-registration (verify: conditional logic)
- [ ] CREATE actions skip auto-registration (verify: not in EDIT_ACTIONS)
- [ ] READ actions skip auto-registration (verify: not in EDIT_ACTIONS)

**Testing:**
- [ ] Unit test: _resolve_doc_path() with valid keys (proof: test_resolve_doc_path)
- [ ] Unit test: _resolve_doc_path() rejects invalid keys (proof: test_resolve_invalid_doc_key)
- [ ] Unit test: path traversal prevented (proof: test_path_traversal_prevention)
- [ ] Unit test: _auto_register_document() with existing file (proof: test_auto_register_success)
- [ ] Unit test: _auto_register_document() with missing file (proof: test_auto_register_missing_file)
- [ ] Unit test: EDIT actions auto-register (proof: test_edit_actions_auto_register)
- [ ] Unit test: CREATE actions don't auto-register (proof: test_create_actions_no_auto_register)
- [ ] Integration test: auto-registration end-to-end (proof: test_auto_registration_integration)

**Logging:**
- [ ] Every auto-registration logged (proof: append_entry in _auto_register_document)
- [ ] Log includes doc_key, path, hash (proof: meta fields)
- [ ] Auto-registration failures logged (proof: logger.error calls)

**Performance:**
- [ ] Auto-registration overhead <100ms (proof: test_auto_registration_performance)
- [ ] No memory leaks (proof: test with 100+ registrations)

---

## Phase 4: Comprehensive Testing
<!-- ID: phase_4_checklist -->

**All 17 Actions Tested:**
- [ ] list_sections functional (proof: test_list_sections_post_fix)
- [ ] replace_section functional (proof: test_replace_section_post_fix)
- [ ] apply_patch functional (proof: test_apply_patch_post_fix)
- [ ] replace_range functional (proof: test_replace_range_post_fix)
- [ ] append functional (proof: test_append_post_fix)
- [ ] status_update functional (proof: test_status_update_post_fix)
- [ ] normalize_headers functional (proof: test_normalize_headers_post_fix)
- [ ] generate_toc functional (proof: test_generate_toc_post_fix)
- [ ] search functional (proof: test_search_post_fix)
- [ ] create_research_doc functional (proof: test_create_research_doc_post_fix)
- [ ] create_bug_report functional (proof: test_create_bug_report_post_fix)
- [ ] read_doc functional (proof: test_read_doc_post_fix)
- [ ] validate_frontmatter functional (proof: test_validate_frontmatter_post_fix)
- [ ] preview_changes functional (proof: test_preview_changes_post_fix)
- [ ] list_documents functional (proof: test_list_documents_post_fix)
- [ ] get_doc_info functional (proof: test_get_doc_info_post_fix)
- [ ] refresh_index functional (proof: test_refresh_index_post_fix)

**Edge Cases:**
- [ ] Missing file handled gracefully (proof: test_edge_case_missing_file)
- [ ] Malformed YAML frontmatter handled (proof: test_edge_case_malformed_yaml)
- [ ] Unicode filenames work (proof: test_edge_case_unicode_filename)
- [ ] Unicode content works (proof: test_edge_case_unicode_content)
- [ ] Very large files handled (proof: test_edge_case_large_file)
- [ ] NULL docs_json handled (proof: test_edge_case_null_docs_json)
- [ ] Invalid JSON handled (proof: test_edge_case_invalid_json)
- [ ] Concurrent edits serialized (proof: test_edge_case_concurrent_edits)
- [ ] Path traversal rejected (proof: test_edge_case_path_traversal)

**Integration Tests:**
- [ ] set_project → manage_docs workflow (proof: test_integration_set_project_manage_docs)
- [ ] Migration → backfill → query → manage_docs (proof: test_integration_full_workflow)
- [ ] Auto-registration → doc_updates log (proof: test_integration_auto_registration_logging)
- [ ] Multi-project isolation (proof: test_integration_multi_project)
- [ ] Database backup → migration → rollback (proof: test_integration_rollback)

**Performance Tests:**
- [ ] Auto-registration <100ms (proof: test_performance_auto_registration)
- [ ] Query with docs_json <50ms (proof: test_performance_query)
- [ ] Backfill 100 projects <5s (proof: test_performance_backfill)
- [ ] Concurrent requests handled (proof: test_performance_concurrent)

**Regression Tests:**
- [ ] All existing tests pass (proof: pytest tests/test_manage_docs.py)
- [ ] No breaking changes to API (proof: backward compatibility tests)
- [ ] Test coverage ≥90% (proof: pytest --cov report)

---

## Phase 5: Documentation
<!-- ID: phase_5_checklist -->

**Scribe_Usage.md Updates:**
- [x] Auto-registration section added (proof: docs/Scribe_Usage.md lines 870-1020)
- [x] Action reference table updated (proof: EDIT vs CREATE marked in lines 885-904)
- [ ] Migration instructions added (proof: migration section) [NOT IN SCOPE]
- [x] All code examples tested (proof: examples run successfully - code blocks validated)
- [x] All links functional (proof: link verification - internal references checked)

**Agent Usage Guide:**
- [x] docs/guides/manage_docs_agent_guide.md created (proof: file exists 350+ lines)
- [x] When to use each action explained (proof: action categories table)
- [x] Auto-registration behavior explained (proof: auto-registration section)
- [x] Common workflows documented (proof: 6 common patterns with examples)
- [x] Error messages and solutions documented (proof: error handling section)
- [x] Best practices included (proof: best practices section with role-specific guidance)
- [x] Examples copy-pasteable (proof: all examples are valid Python code)

**Troubleshooting Section:**
- [x] "DOC_NOT_FOUND" error documented (proof: docs/guides/manage_docs_troubleshooting.md)
- [x] "Auto-registration failed" error documented (proof: auto-registration issues section)
- [x] "Failed to parse docs_json" warning documented (proof: database issues section)
- [x] Database migration issues documented (proof: database issues section)
- [x] Performance troubleshooting documented (proof: performance issues section with solutions)

**Migration Guide:**
- [ ] docs/Migration_Guide_docs_json.md created (proof: file exists)
- [ ] Pre-migration checklist (proof: checklist section)
- [ ] Step-by-step migration commands (proof: command sequence)
- [ ] Verification procedures (proof: verification section)
- [ ] Rollback instructions (proof: rollback section)
- [ ] FAQ section (proof: common questions answered)
- [ ] Dry-run tested on test database (proof: test run completed)

---

## Overall Success Criteria
<!-- ID: overall_success -->

**Functional Requirements:**
- [ ] 17/17 manage_docs actions functional (100%)
- [ ] 9/9 EDIT actions auto-register unregistered docs (100%)
- [ ] 2/2 CREATE actions remain explicit (100%)
- [ ] 0 breaking changes to existing API
- [ ] All 17 actions return consistent error formats
- [ ] Registration events logged to progress log

**Quality Requirements:**
- [ ] Test coverage ≥90% for new code
- [ ] 0 critical bugs in production
- [ ] All edge cases handled gracefully
- [ ] Clear, actionable error messages for all failures
- [ ] Documentation comprehensive and accurate
- [ ] No performance regression from baseline

**Performance Requirements:**
- [ ] Auto-registration overhead <100ms
- [ ] Query with docs_json <50ms
- [ ] Backfill 100 projects <5 seconds
- [ ] Concurrent request handling (≥10 simultaneous)
- [ ] No memory leaks with 1000+ projects

**Process Requirements:**
- [ ] ≥15 Scribe log entries documenting implementation
- [ ] All code changes have file:line references in architecture
- [ ] Test results documented with evidence
- [ ] Review Agent approval (≥93%)
- [ ] Timeline on target (6.5-9.5 hours)

**Audit Requirements:**
- [ ] All architectural decisions logged with reasoning
- [ ] All code changes traceable to architecture specs
- [ ] All test results documented with evidence
- [ ] Migration procedure tested and verified
- [ ] Rollback procedure tested and verified

---

## Deployment Readiness
<!-- ID: deployment_readiness -->

**Pre-Deployment:**
- [ ] Database backup created (proof: .scribe/scribe.db.backup)
- [ ] state.json verified to exist (proof: ls .scribe/state.json)
- [ ] Migration script tested on development (proof: migration test results)
- [ ] All tests passing (proof: pytest -v results)
- [ ] Documentation complete (proof: all docs updated)

**Deployment:**
- [ ] Migration script executed (proof: migration log)
- [ ] Backfill completed (proof: backfill count logged)
- [ ] Verification passed (proof: verify_migration() success)
- [ ] Code deployed (proof: git commit SHA)
- [ ] Server restarted (proof: restart log)

**Post-Deployment:**
- [ ] All existing projects functional (proof: smoke test results)
- [ ] New project creation works (proof: test new project)
- [ ] Auto-registration works (proof: test edit unregistered doc)
- [ ] No errors in logs (proof: grep ERROR logs)
- [ ] Performance metrics within targets (proof: monitoring data)

---

## Review Agent Validation
<!-- ID: review_validation -->

**Architecture Review:**
- [ ] ARCHITECTURE_GUIDE.md reviewed (grade: ___/100)
- [ ] All sections complete and detailed
- [ ] All file:line references accurate
- [ ] All SQL statements verified
- [ ] Security considerations addressed

**Phase Plan Review:**
- [ ] PHASE_PLAN.md reviewed (grade: ___/100)
- [ ] All phases have clear deliverables
- [ ] All success criteria measurable
- [ ] Timeline realistic
- [ ] Risk management comprehensive

**Checklist Review:**
- [ ] CHECKLIST.md reviewed (grade: ___/100)
- [ ] All checklist items verifiable
- [ ] All proofs concrete and achievable
- [ ] Comprehensive coverage of requirements

**Overall Grade:**
- [ ] Average grade ≥93% required to proceed
- [ ] Architecture Agent grade: ___/100
- [ ] Ready for implementation: YES / NO

---

## Final Verification
<!-- ID: final_verification -->

**Completion Criteria:**
- [ ] All checklist items completed with proofs
- [ ] All tests passing (100%)
- [ ] All documentation updated
- [ ] Review Agent approval (≥93%)
- [ ] Deployment successful
- [ ] No critical issues outstanding

**Sign-Off:**
- [ ] Architect Agent: ArchitectAgent (Date: 2026-01-06)
- [ ] Review Agent: _______________ (Date: _______)
- [ ] Coder Agent: _______________ (Date: _______)
- [ ] Orchestrator: _______________ (Date: _______)

---

**Checklist Status:** COMPLETE
**Total Items:** 150+
**Ready for Review:** YES
**Next Step:** Review Agent validation (≥93% required to proceed to implementation)
