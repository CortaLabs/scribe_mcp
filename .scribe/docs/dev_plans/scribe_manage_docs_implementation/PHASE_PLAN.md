# 📅 Phase Plan — scribe_manage_docs_implementation
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-06 02:03:30 UTC

> Sequential implementation roadmap for fixing BUG-MANAGE-DOCS-001 and implementing auto-registration.

---

## Phase Overview
<!-- ID: phase_overview -->

**Total Estimated Effort:** 6.5-9.5 hours

**Sequential Dependencies:** Phases must be executed in order (1→2→3→4→5). Each phase builds on the previous phase's deliverables.

**Quality Gates:** All phases require testing and validation before proceeding. Review Agent approval (≥93%) required before implementation begins.

**Scope:**
- ✅ **IN SCOPE:** SQLite backend only, 17 manage_docs actions, auto-registration for 9 EDIT actions
- ❌ **OUT OF SCOPE:** PostgreSQL support (future work), new manage_docs actions, sentinel mode fixes

| Phase | Goal | Effort | Key Deliverables |
|-------|------|--------|------------------|
| Phase 1 | Database Schema Migration | 2-3 hours | docs_json column, migration function, backfill |
| Phase 2 | Query Integration | 1-2 hours | Updated query, JSON parsing, docs field |
| Phase 3 | Auto-Registration | 2-3 hours | EDIT action categorization, auto-register helper |
| Phase 4 | Comprehensive Testing | 1-2 hours | All 17 actions tested, edge cases, performance |
| Phase 5 | Documentation | 30 min | Usage guide, troubleshooting, migration docs |

---

## Phase 1: Database Schema Migration
<!-- ID: phase_1 -->

**Estimated Effort:** 2-3 hours

**Owner:** Coder Agent

**Prerequisites:**
- Review Agent approval of architecture (≥93%)
- Database backup created (`.scribe/scribe.db.backup`)
- state.json verified to exist

**Objectives:**
1. Add `docs_json` column to `scribe_projects` table
2. Create idempotent migration function
3. Implement backfill from state.json
4. Verify migration success

### Deliverables

**1.1 Update CREATE TABLE Statement**
- **File:** `storage/sqlite.py:652-659`
- **Change:** Add `docs_json TEXT,` after `updated_at` column
- **Test:** Verify new installations create table with 7 columns

**1.2 Create Migration Function**
- **File:** `storage/sqlite.py` (new method in SQLiteStorage class)
- **Method:** `async def migrate_add_docs_json_column(self)`
- **Logic:**
  - Check if column exists via `PRAGMA table_info(scribe_projects)`
  - If missing, execute `ALTER TABLE scribe_projects ADD COLUMN docs_json TEXT`
  - Return True if added, False if already exists (idempotent)
- **Error Handling:** Log errors, raise exception with clear message
- **Test:** Run twice on same database, verify idempotency

**1.3 Create Backfill Function**
- **File:** `storage/sqlite.py` (new method in SQLiteStorage class)
- **Method:** `async def backfill_docs_json_from_state(self, state_path: Path)`
- **Logic:**
  - Load state.json
  - For each project with docs field:
    - Serialize docs to JSON
    - UPDATE scribe_projects SET docs_json = ? WHERE name = ?
  - Return count of backfilled projects
- **Error Handling:** Skip projects without docs, log failures, use transaction
- **Test:** Verify backfill populates docs_json correctly

**1.4 Update upsert_project Method**
- **File:** `storage/sqlite.py:48-80`
- **Change:** Add `docs_json: Optional[str] = None` parameter
- **Logic:** Update INSERT/UPDATE SQL to include docs_json column
- **Backward Compatibility:** Optional parameter, existing callers unaffected
- **Test:** Verify new projects can write docs_json

**1.5 Create Verification Function**
- **File:** `storage/sqlite.py` (new method in SQLiteStorage class)
- **Method:** `async def verify_migration(self)`
- **Logic:** Assert docs_json column exists in schema
- **Test:** Call after migration, verify no errors

### Success Criteria

- [ ] `docs_json` column exists in scribe_projects table
- [ ] Migration is idempotent (safe to run multiple times)
- [ ] Backfill successfully populates docs_json for existing projects
- [ ] `upsert_project` accepts and writes docs_json parameter
- [ ] All unit tests passing
- [ ] Migration logged to progress log

---

## Phase 2: Query Integration
<!-- ID: phase_2 -->

**Estimated Effort:** 1-2 hours

**Owner:** Coder Agent

**Prerequisites:**
- Phase 1 complete (docs_json column exists)
- Migration verified successful

**Objectives:**
1. Update query to SELECT docs_json field
2. Add JSON parsing logic
3. Handle errors gracefully
4. Test all callers of get_active_project()

### Deliverables

**2.1 Update Query SQL**
- **File:** `shared/logging_utils.py:111-119`
- **Change:** Add `docs_json` to SELECT statement
- **Test:** Verify query returns 4 fields

**2.2 Add JSON Parsing Logic**
- **File:** `shared/logging_utils.py:111-119`
- **Change:** Parse docs_json and add docs field to session_project dict
- **Error Handling:** Log warning but don't crash for malformed JSON
- **Test:** Verify docs field present in returned dict

**2.3 Test All Callers**
- `tools/set_project.py`
- `tools/get_project.py`
- `tools/list_projects.py`
- `tools/manage_docs.py`

### Success Criteria

- [ ] Query returns docs field for projects with docs_json
- [ ] Query handles NULL docs_json without errors
- [ ] Malformed JSON logged as warning, doesn't crash
- [ ] All callers tested and receiving correct data
- [ ] All unit tests passing

---

## Phase 3: Auto-Registration Implementation
<!-- ID: phase_3 -->

**Estimated Effort:** 2-3 hours

**Owner:** Coder Agent

**Prerequisites:**
- Phase 2 complete (query returns docs field)
- All existing manage_docs actions functional

**Objectives:**
1. Categorize all 17 manage_docs actions
2. Implement _auto_register_document() helper
3. Integrate auto-registration with EDIT actions
4. Add registration event logging

### Deliverables

**3.1 Define Action Categories**
- **File:** `tools/manage_docs.py`
- **EDIT Actions (9):** list_sections, replace_section, apply_patch, replace_range, append, status_update, normalize_headers, generate_toc, search
- **CREATE Actions (2):** create_research_doc, create_bug_report

**3.2 Implement _resolve_doc_path() Helper**
- Validate doc_key against whitelist
- Prevent path traversal attacks
- Return absolute path

**3.3 Implement _auto_register_document() Helper**
- Resolve document path
- Verify file exists
- Compute SHA256 hash
- Update database docs_json field
- Log registration event

**3.4 Integrate Auto-Registration**
- Add check before EDIT action dispatch
- Auto-register if doc not in project["docs"]
- Skip for CREATE and READ actions

### Success Criteria

- [ ] EDIT actions auto-register unregistered docs
- [ ] CREATE actions remain explicit (no auto-registration)
- [ ] Registration events logged to progress log
- [ ] Performance overhead <100ms
- [ ] All unit tests passing

---

## Phase 4: Comprehensive Testing
<!-- ID: phase_4 -->

**Estimated Effort:** 1-2 hours

**Owner:** Coder Agent

**Prerequisites:**
- Phase 3 complete (auto-registration implemented)

**Objectives:**
1. Test all 17 manage_docs actions
2. Execute edge case testing
3. Run integration tests
4. Verify performance requirements

### Test Categories

**Unit Tests:**
- Database migration idempotency
- Backfill from state.json
- Query returns docs field
- Auto-registration triggers
- CREATE actions don't auto-register

**Integration Tests:**
- All 17 actions functional
- set_project → manage_docs workflow
- Migration → backfill → query flow
- Multi-project isolation

**Edge Cases:**
- Missing files
- Malformed JSON
- Unicode content
- NULL docs_json
- Concurrent requests

**Performance Tests:**
- Auto-registration <100ms
- Query <50ms
- Backfill 100 projects <5s

### Success Criteria

- [ ] 17/17 manage_docs actions functional
- [ ] All edge cases handled gracefully
- [ ] Integration tests passing
- [ ] Performance tests passing
- [ ] Test coverage ≥90%

---

## Phase 5: Documentation
<!-- ID: phase_5 -->

**Estimated Effort:** 30 minutes

**Owner:** Coder Agent

**Prerequisites:**
- Phase 4 complete (all tests passing)

**Objectives:**
1. Update docs/Scribe_Usage.md
2. Create agent usage guide
3. Add troubleshooting section
4. Document migration procedure

### Deliverables

**5.1 Update Scribe_Usage.md**
- Add auto-registration section
- Update action reference table
- Add migration instructions

**5.2 Create Agent Usage Guide**
- When to use each action
- Auto-registration explained
- Common workflows
- Error messages and solutions

**5.3 Add Troubleshooting Section**
- "DOC_NOT_FOUND" error
- "Auto-registration failed" error
- Database migration issues

**5.4 Document Migration Procedure**
- Pre-migration checklist
- Step-by-step commands
- Verification procedures
- Rollback instructions

### Success Criteria

- [ ] docs/Scribe_Usage.md updated
- [ ] docs/Agent_Guide_manage_docs.md created
- [ ] Troubleshooting section complete
- [ ] Migration guide complete
- [ ] All code examples tested

---

## Timeline & Dependencies

```
Phase 1: Database Migration (2-3 hours)
    ↓ (docs_json column must exist)
Phase 2: Query Integration (1-2 hours)
    ↓ (query must return docs field)
Phase 3: Auto-Registration (2-3 hours)
    ↓ (auto-registration must work)
Phase 4: Testing (1-2 hours)
    ↓ (all tests must pass)
Phase 5: Documentation (30 min)
    ↓
COMPLETE (6.5-9.5 hours total)
```

**Sequential execution required - phases cannot be parallelized.**

---

## Risk Management

### High-Risk Items
- **Database Migration Fails:** Backup + idempotent migration + rollback procedure
- **Auto-Registration Performance:** Testing + caching strategies
- **Existing Functionality Breaks:** Regression testing + backward compatibility

### Medium-Risk Items
- **Edge Cases Not Covered:** Exhaustive testing in Phase 4
- **Documentation Incomplete:** Review checklist + tested examples

---

## Success Metrics

**Functional:**
- 17/17 manage_docs actions functional (100%)
- 9/9 EDIT actions auto-register (100%)
- 0 breaking changes to existing API

**Performance:**
- Auto-registration <100ms
- Query with docs_json <50ms
- Backfill 100 projects <5s

**Quality:**
- Test coverage ≥90%
- 0 critical bugs
- Clear error messages

**Process:**
- ≥15 Scribe log entries
- Review Agent approval (≥93%)
- Timeline: 6.5-9.5 hours

---

**Phase Plan Status:** COMPLETE
**Ready for Review:** YES
**Next Step:** Review Agent validation (≥93% required to proceed)
