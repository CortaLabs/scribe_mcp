# Checklist: Session Isolation & UX Fixes

**Project:** manage_docs_agent_ux
**Sub-Plan:** session_and_ux_fixes
**Created:** 2026-01-20
**Architect:** ArchitectAgent

---

## Phase 1: Session Isolation Unification

### Task 1.1: Create Session Utils Module <!-- ID: phase1_task1 -->
- [ ] File `shared/session_utils.py` created
- [ ] Function `get_canonical_session_key()` implemented with correct signature
- [ ] Type hints present for all parameters and return value
- [ ] Docstring explains stable vs ephemeral session IDs
- [ ] Module compiles: `python -m py_compile shared/session_utils.py`

**Acceptance:** Single-function module that returns `stable_session_id or session_id or None`
**Verification:** `pytest tests/test_session_utils.py::test_stable_session_id_only -v`

---

### Task 1.2: Update set_project.py <!-- ID: phase1_task2 -->
- [ ] Import `get_canonical_session_key` added at top of file
- [ ] Line 513 replaced with function call
- [ ] `exec_context` passed to function
- [ ] No other changes to set_project.py
- [ ] File compiles: `python -m py_compile tools/set_project.py`
- [ ] Manual test: `set_project(name="test")` still works

**Acceptance:** set_project uses canonical session key function
**Verification:** Restart MCP server, call set_project, check session binding in database

---

### Task 1.3: Update logging_utils.py <!-- ID: phase1_task3 -->
- [ ] Import `get_canonical_session_key` added at top of file
- [ ] Lines 91-92 replaced with single function call
- [ ] `exec_context` passed to function
- [ ] No other changes to logging_utils.py
- [ ] File compiles: `python -m py_compile shared/logging_utils.py`
- [ ] Manual test: `append_entry()` resolves correct project

**Acceptance:** logging_utils uses canonical session key function
**Verification:** Call append_entry after set_project, verify same project resolution

---

### Task 1.4: Session Isolation Unit Tests <!-- ID: phase1_task4 -->
- [ ] File `tests/test_session_utils.py` created
- [ ] Test: `test_stable_session_id_only` passes
- [ ] Test: `test_session_id_only` passes
- [ ] Test: `test_both_session_ids_stable_preferred` passes
- [ ] Test: `test_neither_session_id_returns_none` passes
- [ ] Test: `test_none_execution_context_returns_none` passes
- [ ] All 5 tests pass: `pytest tests/test_session_utils.py -v`

**Acceptance:** 100% code coverage of `get_canonical_session_key()`
**Verification:** `pytest tests/test_session_utils.py -v --cov=shared.session_utils`

---

### Task 1.5: Session Isolation Integration Test <!-- ID: phase1_task5 -->
- [ ] File `tests/test_session_isolation_integration.py` created
- [ ] Test creates temp project with stable_session_id
- [ ] Test calls set_project, then append_entry
- [ ] Test verifies same project resolution
- [ ] Test verifies no EmergencyFallback in logs
- [ ] Test passes: `pytest tests/test_session_isolation_integration.py -v`
- [ ] Temp directory cleaned up after test

**Acceptance:** End-to-end verification that session key is consistent
**Verification:** `pytest tests/test_session_isolation_integration.py -v`

---

## Phase 2: Multi-Project Tool Parameters

### Task 2.1: Add Project Parameter to append_entry <!-- ID: phase2_task1 -->
- [ ] `project` parameter added to append_entry signature (after `message`)
- [ ] `explicit_project` parameter added to resolve_logging_context
- [ ] Precedence logic added (explicit project checked first)
- [ ] Manual test: `append_entry(message="test", project="other")` logs to other project
- [ ] Backward compatible: append_entry without project param still works
- [ ] Test passes: `pytest tests/test_tool_project_params.py::test_append_entry_explicit_project -v`

**Acceptance:** append_entry supports explicit project override
**Verification:** Cross-project logging test passes

---

### Task 2.2: Add Project Parameter to read_file <!-- ID: phase2_task2 -->
- [ ] `project` parameter added to read_file signature
- [ ] Path resolution uses project root when param provided
- [ ] Security check prevents path traversal outside project root
- [ ] Manual test: `read_file(path="file.py", project="other")` reads from other project
- [ ] Backward compatible: read_file without project param still works
- [ ] Test passes: `pytest tests/test_tool_project_params.py::test_read_file_explicit_project -v`

**Acceptance:** read_file supports explicit project override
**Verification:** Cross-project file reading test passes

---

### Task 2.3: Fix generate_doc_templates Parameter Naming <!-- ID: phase2_task3 -->
- [ ] `project` parameter added to signature (for context)
- [ ] Docstring clarifies `project_name` (content) vs `project` (scope)
- [ ] Path resolution uses `project` when provided
- [ ] Manual test: Can generate templates in different project context
- [ ] Backward compatible: Existing calls still work
- [ ] Test passes: `pytest tests/test_tool_project_params.py::test_generate_templates_explicit_project -v`

**Acceptance:** generate_doc_templates has clear parameter semantics
**Verification:** Cross-project template generation test passes

---

### Task 2.4: Multi-Project Tool Tests <!-- ID: phase2_task4 -->
- [ ] File `tests/test_tool_project_params.py` created
- [ ] Test: `test_append_entry_explicit_project` passes
- [ ] Test: `test_read_file_explicit_project` passes
- [ ] Test: `test_generate_templates_explicit_project` passes
- [ ] Test: `test_precedence_explicit_over_session` passes
- [ ] Test: `test_error_when_require_project_and_none_available` passes
- [ ] Test: `test_backward_compatible_without_project_param` passes
- [ ] All 6 tests pass: `pytest tests/test_tool_project_params.py -v`

**Acceptance:** Comprehensive test coverage for cross-project tool usage
**Verification:** `pytest tests/test_tool_project_params.py -v` (6/6 pass)

---

## Phase 3: Custom Doc Naming Fix

### Task 3.1: Fix Line 828 Parameter Precedence <!-- ID: phase3_task1 -->
- [ ] Line 828 in manager.py modified (precedence order fixed)
- [ ] `doc_name` parameter checked before `metadata` fallbacks
- [ ] No other lines changed in manager.py
- [ ] File compiles: `python -m py_compile doc_management/manager.py`
- [ ] Manual test: `_resolve_create_doc_path(doc_name="TEST", metadata={"doc_type": "custom"})` returns "TEST.md"

**Acceptance:** Function parameter takes precedence over metadata
**Verification:** Manual function call with both params returns param value

---

### Task 3.2: Add Regression Test for Doc Naming <!-- ID: phase3_task2 -->
- [ ] Test `test_doc_name_parameter_takes_precedence_over_metadata` added to existing test file
- [ ] Test case 1: doc_name only → uses doc_name
- [ ] Test case 2: doc_name + metadata.doc_type → uses doc_name (FIX)
- [ ] Test case 3: metadata.doc_name only → uses metadata.doc_name
- [ ] Test case 4: metadata.doc_type only → uses metadata.doc_type
- [ ] Test case 5: All precedence levels → uses highest (param)
- [ ] Test passes: `pytest tests/test_manage_docs_create_doc.py::test_doc_name_parameter_takes_precedence_over_metadata -v`
- [ ] Docstring references research document

**Acceptance:** Test catches bug (would fail with old code)
**Verification:** `pytest tests/test_manage_docs_create_doc.py::test_doc_name_parameter_takes_precedence_over_metadata -v`

---

## Phase 4: Index Update Event Coverage

### Task 4.1: Add Index Update Hook <!-- ID: phase4_task1 -->
- [ ] Function `_determine_doc_category()` added to manage_docs.py
- [ ] Index update block added after `apply_doc_change()`
- [ ] All 4 special doc types handled (research, bugs, review, agent_cards)
- [ ] `doc_dir` determined correctly for each type
- [ ] File compiles: `python -m py_compile tools/manage_docs.py`
- [ ] Manual test: Edit research doc → INDEX.md updates
- [ ] Manual test: Edit bug report → bugs/INDEX.md updates

**Acceptance:** Index updates triggered on ALL document changes
**Verification:** Edit special doc, verify INDEX.md timestamp changes

---

### Task 4.2: Index Update Tests <!-- ID: phase4_task2 -->
- [ ] File `tests/test_index_updates.py` created
- [ ] Test: `test_research_doc_edit_updates_index` passes
- [ ] Test: `test_bug_report_edit_updates_index` passes
- [ ] Test: `test_review_report_edit_updates_index` passes
- [ ] Test: `test_agent_card_edit_updates_index` passes
- [ ] Test: `test_multiple_edits_index_reflects_final_state` passes
- [ ] All 5 tests pass: `pytest tests/test_index_updates.py -v`
- [ ] Tests verify index content changes (not just timestamp)

**Acceptance:** Comprehensive test coverage for index updates
**Verification:** `pytest tests/test_index_updates.py -v` (5/5 pass)

---

## Phase 5: Backup Location Cleanup

### Task 5.1: Create Backup Path Utility <!-- ID: phase5_task1 -->
- [ ] Function `get_backup_path()` added to manager.py
- [ ] Docstring complete with example
- [ ] Function handles edge cases (file not in .scribe, invalid paths)
- [ ] File compiles: `python -m py_compile doc_management/manager.py`
- [ ] Manual test: Function generates correct paths
- [ ] Manual test: Function creates directory structure

**Acceptance:** Utility function generates backup paths in dedicated directory
**Verification:** Call function, verify path structure matches spec

---

### Task 5.2: Update Backup Creation Calls <!-- ID: phase5_task2 -->
- [ ] All backup creation calls in manager.py updated
- [ ] All backup creation calls in manage_docs.py updated
- [ ] Inflight backups use `backup_type="inflight"`
- [ ] Preflight backups use `backup_type="preflight"`
- [ ] Backups appear in `.scribe/backups/` directory
- [ ] Original directories clean (no .bak files)
- [ ] Timestamp in backup filename
- [ ] Date-based directory structure created

**Acceptance:** All backups created in dedicated directory
**Verification:** Create/edit doc, verify backup location and source cleanup

---

### Task 5.3: Backup Location Tests <!-- ID: phase5_task3 -->
- [ ] File `tests/test_backup_paths.py` created
- [ ] Test: `test_get_backup_path_structure` passes
- [ ] Test: `test_backup_created_in_dedicated_directory` passes
- [ ] Test: `test_timestamp_in_filename` passes
- [ ] Test: `test_directory_structure_preserved` passes
- [ ] All 4 tests pass: `pytest tests/test_backup_paths.py -v`
- [ ] Tests verify path structure, cleanup, timestamps

**Acceptance:** Comprehensive test coverage for backup location
**Verification:** `pytest tests/test_backup_paths.py -v` (4/4 pass)

---

## Final Acceptance Criteria

### Session Isolation (Phase 1)
- [ ] set_project() followed by append_entry() → correct project resolution
- [ ] set_project() in session A, set_project() in session B → no cross-contamination
- [ ] Session binding survives MCP server restart
- [ ] No "EmergencyFallback" entries in logs after fix
- [ ] All Phase 1 tests pass (5/5 unit + 1 integration)

**Verification:** `pytest tests/test_session*.py -v`

---

### Multi-Project Parameters (Phase 2)
- [ ] append_entry(project="other") logs to specified project, not active
- [ ] read_file(project="other") reads from specified project context
- [ ] generate_doc_templates(project="other") generates in specified project
- [ ] Error when require_project=True and no project available
- [ ] All Phase 2 tests pass (6/6)

**Verification:** `pytest tests/test_tool_project_params.py -v`

---

### Custom Doc Naming (Phase 3)
- [ ] manage_docs(doc_name="X", metadata={"doc_type": "Y"}) creates X.md, not Y.md
- [ ] All 4 precedence levels tested and work correctly
- [ ] Regression test added to prevent future bugs
- [ ] All Phase 3 tests pass

**Verification:** `pytest tests/test_manage_docs_create_doc.py::test_doc_name_parameter_takes_precedence_over_metadata -v`

---

### Index Updates (Phase 4)
- [ ] Edit research doc → INDEX.md updated
- [ ] Edit bug report → bugs/INDEX.md updated
- [ ] Edit review report → REVIEW_INDEX.md updated
- [ ] Edit agent card → AGENT_CARDS_INDEX.md updated
- [ ] Timestamp in index reflects latest edit
- [ ] All Phase 4 tests pass (5/5)

**Verification:** `pytest tests/test_index_updates.py -v`

---

### Backup Location (Phase 5)
- [ ] Backups created in `.scribe/backups/` directory
- [ ] Original directories clean (no .bak files)
- [ ] Backup filename includes timestamp
- [ ] Multiple backups don't overwrite each other
- [ ] All Phase 5 tests pass (4/4)

**Verification:** `pytest tests/test_backup_paths.py -v`

---

## Pre-Deployment Checklist

### Testing
- [ ] All unit tests pass: `pytest tests/test_session_utils.py tests/test_tool_project_params.py tests/test_manage_docs_create_doc.py tests/test_index_updates.py tests/test_backup_paths.py -v`
- [ ] All integration tests pass: `pytest tests/test_session_isolation_integration.py -v`
- [ ] Manual smoke tests complete (see below)
- [ ] No regressions in existing functionality
- [ ] Test coverage ≥90% for new code

### Documentation
- [ ] Scribe_Usage.md updated with new `project` parameter
- [ ] CHANGELOG.md entry added for v2.1.2
- [ ] Architecture guide reviewed by second architect
- [ ] Handoff notes written for Coder agent

### Code Quality
- [ ] All files compile without errors
- [ ] No linting errors: `ruff check .`
- [ ] Type hints present for all new functions
- [ ] Docstrings complete for all new functions
- [ ] No hardcoded paths or magic strings

---

## Manual Smoke Tests

### Smoke Test 1: Session Isolation
```bash
# 1. Start MCP server
# 2. Open Claude Code
# 3. Call: set_project(name="test_session_a")
# 4. Call: append_entry(message="Test A", agent="TestAgent")
# 5. Verify log written to test_session_a
# 6. Call: set_project(name="test_session_b")
# 7. Call: append_entry(message="Test B", agent="TestAgent")
# 8. Verify log written to test_session_b (not test_session_a)
```

**Expected:** Each project gets its own logs, no cross-contamination
**Status:** [ ] PASS / [ ] FAIL

---

### Smoke Test 2: Cross-Project Logging
```bash
# 1. Active project: test_project_a
# 2. Call: append_entry(message="Cross-project test", project="test_project_b")
# 3. Verify log written to test_project_b (not test_project_a)
```

**Expected:** Explicit project parameter overrides active project
**Status:** [ ] PASS / [ ] FAIL

---

### Smoke Test 3: Custom Doc Naming
```bash
# 1. Call: manage_docs(
#       action="create",
#       doc_name="MY_CUSTOM_DOC",
#       metadata={"doc_type": "custom"}
#    )
# 2. Verify file created: MY_CUSTOM_DOC.md (NOT custom.md)
```

**Expected:** doc_name parameter takes precedence over metadata
**Status:** [ ] PASS / [ ] FAIL

---

### Smoke Test 4: Index Updates on Edit
```bash
# 1. Create research doc
# 2. Note INDEX.md timestamp
# 3. Edit research doc (replace_section)
# 4. Verify INDEX.md timestamp changed
# 5. Verify INDEX.md contains updated content
```

**Expected:** Index updates immediately after edit
**Status:** [ ] PASS / [ ] FAIL

---

### Smoke Test 5: Backup Location
```bash
# 1. Create and edit a doc
# 2. Verify backup exists in .scribe/backups/{date}/{project}/
# 3. Verify source directory has NO .bak files
# 4. Verify backup filename includes timestamp
```

**Expected:** Backups in dedicated directory, source clean
**Status:** [ ] PASS / [ ] FAIL

---

## Deployment Sign-Off

**Phase 1 - Session Isolation:**
- [ ] All tests pass
- [ ] Manual smoke test pass
- [ ] Code review complete
- [ ] Approved by: _____________ Date: _______

**Phase 2 - Multi-Project Parameters:**
- [ ] All tests pass
- [ ] Manual smoke test pass
- [ ] Code review complete
- [ ] Approved by: _____________ Date: _______

**Phase 3 - Custom Doc Naming:**
- [ ] All tests pass
- [ ] Manual smoke test pass
- [ ] Code review complete
- [ ] Approved by: _____________ Date: _______

**Phase 4 - Index Updates:**
- [ ] All tests pass
- [ ] Manual smoke test pass
- [ ] Performance acceptable (<200ms latency)
- [ ] Code review complete
- [ ] Approved by: _____________ Date: _______

**Phase 5 - Backup Location:**
- [ ] All tests pass
- [ ] Manual smoke test pass
- [ ] Code review complete
- [ ] Approved by: _____________ Date: _______

---

**Final Deployment Approval:**
- [ ] All 5 phases complete
- [ ] All tests passing
- [ ] All smoke tests passing
- [ ] Documentation updated
- [ ] CHANGELOG.md complete
- [ ] Rollback plan documented
- [ ] Monitoring alerts configured

**Approved for Production:**
Name: _____________
Date: _______
Signature: _____________

---

**End of Checklist**
