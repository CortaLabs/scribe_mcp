---
id: query_enhancement_suite-query-suite-checklist
title: "Query Enhancement Suite \u2014 Implementation Checklist"
doc_name: QUERY_SUITE_CHECKLIST
category: engineering
status: draft
version: '0.1'
last_updated: '2026-02-02'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Query Enhancement Suite — Implementation Checklist

**Project:** query_enhancement_suite  
**Sub-Plan:** query_suite_v1  
**Architect:** ArchitectAgent-QuerySuite  
**Created:** 2026-02-01

---

## Phase 1: Bug/Security Workflow Overhaul

### Task 1.1: Expand open_bug Parameter Schema
<!-- ID: task_1_1 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `tools/sentinel_tools.py` (lines 278-380)

**Acceptance Criteria:**
- [ ] Function signature includes 8 new optional parameters (expected_behaviour, steps_to_reproduce, root_cause, resolution_notes, severity, component, environment, customer_impact)
- [ ] Metadata dict includes conditional mappings for all new params
- [ ] Unpopulated fields use `[UNFILLED]` marker
- [ ] Docstring documents all new parameters
- [ ] Existing `open_bug` calls work unchanged (backward compatible)

**Verification:**
```bash
# Test minimal params (existing behavior)
pytest tests/test_sentinel_tools.py::test_open_bug_minimal_params -v

# Test new params populate correctly
pytest tests/test_sentinel_tools.py::test_open_bug_full_params -v
```

---

### Task 1.2: Expand open_security Parameter Schema
<!-- ID: task_1_2 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `tools/sentinel_tools.py` (lines 399-500)  
**Dependencies:** Task 1.1

**Acceptance Criteria:**
- [ ] `open_security` signature matches `open_bug` signature (param-for-param)
- [ ] Metadata mappings identical to `open_bug`
- [ ] Docstring matches `open_bug` parameter docs
- [ ] Security reports populate identically to bug reports

**Verification:**
```bash
# Test security report creation
pytest tests/test_sentinel_tools.py::test_open_security_matches_open_bug -v
```

---

### Task 1.3: Add Completeness Scoring to Response
<!-- ID: task_1_3 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `tools/sentinel_tools.py` (return statements)  
**Dependencies:** Tasks 1.1, 1.2

**Acceptance Criteria:**
- [ ] `_BUG_TEMPLATE_FIELDS` constant defined with complete field list
- [ ] Completeness calculation counts filled vs unfilled fields
- [ ] Response includes `completeness` dict with score, percentage, filled_sections, unfilled_sections
- [ ] `action_required` provides specific guidance on unfilled sections
- [ ] Response structure backward compatible (adds fields, doesn't remove)

**Verification:**
```bash
# Test completeness scoring
pytest tests/test_sentinel_tools.py::test_open_bug_completeness_scoring -v

# Integration test: create bug with partial params, verify completeness
python -c "from tools.sentinel_tools import open_bug; import asyncio; print(asyncio.run(open_bug(agent='TestAgent', title='Test', symptoms='Test symptoms', category='test', expected_behaviour='Should work')))"
```

---

## Phase 2: Query Tool Enhancements

### Task 2.1: Enhance read_recent Stateless Mode
<!-- ID: task_2_1 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `tools/read_recent.py` (lines 263-276)

**Acceptance Criteria:**
- [ ] ProjectResolutionError handler includes `last_known_project` logic
- [ ] `extra` dict populated with last_known metadata when available
- [ ] `suggestion` field provides actionable next steps
- [ ] Graceful degradation when no last_known (empty extra dict)
- [ ] No exceptions raised during error handling

**Verification:**
```bash
# Test stateless mode enhanced error
pytest tests/test_read_recent.py::test_read_recent_stateless_enhanced_error -v

# Test graceful degradation
pytest tests/test_read_recent.py::test_read_recent_stateless_no_last_known -v

# Integration test: call read_recent with no project
python -c "from tools.read_recent import read_recent; import asyncio; print(asyncio.run(read_recent(agent='TestAgent')))"
```

---

## Phase 3: Session-Aware Filtering

### Task 3.1: Schema Migration
<!-- ID: task_3_1 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `storage/sqlite.py` (lines 1076-1113)

**Acceptance Criteria:**
- [ ] `_ensure_column` call added for `session_id TEXT` column
- [ ] Index creation statement added (`idx_entries_session`)
- [ ] Migration code placed after existing migrations
- [ ] Migration is idempotent (safe to run multiple times)

**Verification:**
```bash
# Restart MCP server (triggers migration)
# Then check schema:
sqlite3 .scribe/db.sqlite3 "PRAGMA table_info(scribe_entries);" | grep session_id
# Should output: session_id|TEXT|0||0

sqlite3 .scribe/db.sqlite3 "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_entries_session';"
# Should output: idx_entries_session

# Test migration on fresh database
pytest tests/test_storage_sqlite.py::test_session_id_column_exists -v
```

---

### Task 3.2: Update insert_entry Signatures
<!-- ID: task_3_2 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `storage/base.py` (lines 76-88), `storage/sqlite.py` (lines 319-370)  
**Dependencies:** Task 3.1

**Acceptance Criteria:**
- [ ] Abstract signature includes `session_id: Optional[str] = None` parameter
- [ ] Concrete signature matches abstract signature
- [ ] INSERT statement includes `session_id` in columns and values
- [ ] Parameter order matches between signature and INSERT tuple
- [ ] Existing tests pass (session_id=None is valid)

**Verification:**
```bash
# Test insert_entry with session_id
pytest tests/test_storage_sqlite.py::test_insert_entry_with_session_id -v

# Test backward compatibility (session_id=None)
pytest tests/test_storage_sqlite.py -k insert_entry -v
```

---

### Task 3.3: Wire session_id Through append_entry
<!-- ID: task_3_3 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `tools/append_entry.py` (around line 633)  
**Dependencies:** Task 3.2

**Acceptance Criteria:**
- [ ] `context.session_id` extracted before insert_entry call
- [ ] `session_id` parameter passed to backend.insert_entry()
- [ ] Graceful handling when context is None (session_id=None)
- [ ] Bulk mode creates entries with consistent session_id

**Verification:**
```bash
# Test append_entry wires session_id
pytest tests/test_append_entry.py::test_append_entry_wires_session_id -v

# Integration test: create entry and check session_id
python -c "from tools.append_entry import append_entry; import asyncio; asyncio.run(append_entry(agent='TestAgent', message='Test', status='info'))"
sqlite3 .scribe/db.sqlite3 "SELECT session_id FROM scribe_entries ORDER BY ts DESC LIMIT 1;"
# Should output: non-NULL session_id hash

# Test bulk mode
pytest tests/test_append_entry.py::test_bulk_append_session_consistency -v
```

---

### Task 3.4: Add session_id Filter to query_entries
<!-- ID: task_3_4 -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]  
**Files:** `tools/query_entries.py`, `storage/sqlite.py` (lines 594-649)  
**Dependencies:** Tasks 3.1, 3.2, 3.3

**Acceptance Criteria:**
- [ ] Tool signature includes `session_id: Optional[str] = None` parameter
- [ ] Docstring documents session_id parameter
- [ ] Tool passes session_id to backend.query_entries()
- [ ] Storage signature includes session_id parameter
- [ ] WHERE clause filter added for session_id
- [ ] Results ordered chronologically within session

**Verification:**
```bash
# Test session filtering
pytest tests/test_query_entries.py::test_query_entries_session_filter -v

# Test NULL session_id excluded
pytest tests/test_query_entries.py::test_query_entries_session_null_excluded -v

# Integration test: create entries with same session_id, query by session
python -c "
import asyncio
from tools.append_entry import append_entry
from tools.query_entries import query_entries
import hashlib

async def test():
    # Get current session_id
    result1 = await append_entry(agent='TestAgent', message='Entry 1', status='info')
    # Query by session_id (extract from context)
    # ... implementation ...

asyncio.run(test())
"

# Test backward compatibility (no session_id filter)
pytest tests/test_query_entries.py -k query_entries -v
```

---

## Regression Testing

### Cross-Phase Verification
<!-- ID: regression_tests -->

**Status:** ☐ Not Started  
**Assigned:** [Coder Agent]

**Acceptance Criteria:**
- [ ] All existing tests pass (no regressions)
- [ ] Integration tests verify end-to-end workflows
- [ ] Performance tests confirm <100ms overhead for session filtering
- [ ] Manual testing: create bug report with new params, verify template population
- [ ] Manual testing: call read_recent with no project, verify helpful error
- [ ] Manual testing: create entries and query by session_id, verify filtering

**Verification:**
```bash
# Run full test suite
pytest tests/ -v --tb=short

# Check test coverage
pytest tests/ --cov=scribe_mcp --cov-report=html
# Verify ≥90% coverage on new code paths

# Performance test
pytest tests/test_query_entries.py::test_session_filter_performance -v
```

---

## Deployment Checklist

### Pre-Deployment
<!-- ID: pre_deployment -->

- [ ] All phase tasks completed
- [ ] All regression tests pass
- [ ] Code review completed
- [ ] Database backup created (for Phase 3)
- [ ] Rollback plan confirmed

### Phase 1 Deployment
<!-- ID: phase_1_deployment -->

- [ ] Deploy `tools/sentinel_tools.py` changes
- [ ] Verify bug report creation with new params
- [ ] Check completeness scoring in response
- [ ] Monitor TOOL_LOG.jsonl for errors

### Phase 2 Deployment
<!-- ID: phase_2_deployment -->

- [ ] Deploy `tools/read_recent.py` changes
- [ ] Test read_recent with no project set
- [ ] Verify enhanced error response structure
- [ ] Monitor TOOL_LOG.jsonl for errors

### Phase 3 Deployment
<!-- ID: phase_3_deployment -->

- [ ] Database backup confirmed
- [ ] Deploy storage layer changes (base.py, sqlite.py)
- [ ] Deploy tool changes (append_entry.py, query_entries.py)
- [ ] Restart MCP server (triggers migration)
- [ ] Verify `session_id` column exists
- [ ] Verify index created
- [ ] Create test entry, verify session_id populated
- [ ] Query by session_id, verify filtering works
- [ ] Monitor query performance
- [ ] Monitor TOOL_LOG.jsonl for errors

### Post-Deployment
<!-- ID: post_deployment -->

- [ ] All phases deployed successfully
- [ ] User acceptance testing completed
- [ ] Documentation updated (Scribe_Usage.md)
- [ ] Release notes prepared
- [ ] Project marked as complete

---

## Rollback Procedures

### Phase 1 Rollback
<!-- ID: phase_1_rollback -->

**Trigger:** Bug reports not populating correctly, completeness scoring broken

**Steps:**
1. Revert `tools/sentinel_tools.py` to commit before Phase 1 changes
2. Restart MCP server
3. Verify existing bug report creation works
4. No database rollback needed (no schema changes)

### Phase 2 Rollback
<!-- ID: phase_2_rollback -->

**Trigger:** read_recent errors, exceptions in error handler

**Steps:**
1. Revert `tools/read_recent.py` to commit before Phase 2 changes
2. Restart MCP server
3. Verify read_recent with no project returns original error
4. No database rollback needed (no schema changes)

### Phase 3 Rollback
<!-- ID: phase_3_rollback -->

**Trigger:** Session filtering broken, insert_entry errors, migration failures

**Steps:**
1. Restore database from pre-Phase 3 backup (if critical)
2. Revert code changes: `storage/base.py`, `storage/sqlite.py`, `tools/append_entry.py`, `tools/query_entries.py`
3. Restart MCP server
4. Verify append_entry and query_entries work without session_id
5. **DO NOT drop session_id column** (NULL values safe, backward compatible)

---

## Success Metrics

### Phase 1 Success
- [ ] Bug reports created with ≥50% template completion on first write (measured via completeness score)
- [ ] ≥80% of bug reports use at least 1 new optional parameter
- [ ] Zero regression bugs filed

### Phase 2 Success
- [ ] `read_recent()` with no project returns helpful error (measured by `extra` dict presence)
- [ ] User satisfaction: fewer "how do I set project?" questions
- [ ] Zero regression bugs filed

### Phase 3 Success
- [ ] `query_entries(session_id=X)` successfully filters entries by session
- [ ] Session filtering used in ≥50% of multi-agent workflows within 1 month
- [ ] Query performance overhead <100ms (measured via performance tests)
- [ ] Zero data loss (all existing entries preserved with NULL session_id)
- [ ] Zero breaking changes to existing tool calls

---

*Checklist v1.0 — Query Enhancement Suite — ArchitectAgent-QuerySuite — 2026-02-01*
