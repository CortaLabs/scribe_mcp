# PIVOT PLAN: manage_docs Production Readiness

**Created:** 2026-01-05
**Project:** scribe_systematic_audit_1 (Phase 5.5 Pivot)
**Priority:** CRITICAL - Blocking wiki maintenance capability
**Estimated Effort:** 6-8 hours (Architect 1hr + Coder 4-5hrs + Testing 2hrs)

---

## Executive Summary

Phase 5.5 manage_docs audit discovered **BUG-MANAGE-DOCS-001**: missing `docs_json` column in database blocks 10+ of 17 editing actions. This pivot fixes the infrastructure bug AND implements auto-registration for edit operations, making manage_docs production-ready for wiki maintenance.

**Critical Context:** The audit wiki copy strategy requires a fully functional manage_docs tool. Future agents will rely on this for maintaining `/docs/wiki/` after the selective copy completes.

---

## Problem Statement

### Current State (BROKEN)

**Infrastructure Bug:**
- `scribe_projects` table missing `docs_json` column (only 16/17 columns present)
- `shared/logging_utils.py:111-119` query returns incomplete project data
- manage_docs validation fails: `project.get("docs")` → `None`
- **Impact:** 10+ actions completely non-functional

**User Experience Gap:**
- Attempting to edit unregistered files fails with "DOC_NOT_FOUND"
- Agents must manually call `generate_doc_templates` before editing
- No automatic registration workflow for edit operations

**Working Actions (3/17):**
- ✅ `create_research_doc` - Document creation (manual registration)
- ✅ `create_bug_report` - Document creation (manual registration)
- ⚠️ All other actions blocked by missing database field

### Desired State (PRODUCTION-READY)

**Infrastructure Fixed:**
- `docs_json` column added to `scribe_projects` table
- Query updated to return complete project data
- All 17 actions functional and tested

**Auto-Registration (SMART):**
- **EDIT operations** auto-register files on first use (list_sections, replace_section, apply_patch, etc.)
- **CREATE operations** remain opt-in (create_research_doc, create_bug_report stay explicit)
- Automatic detection: "Is this file already registered? No → register it, then proceed"

**Developer Experience:**
- Agents can edit ANY file without pre-registration
- Clear error messages with actionable suggestions
- Comprehensive usage documentation

---

## Scope & Requirements

### ✅ IN SCOPE

**1. Fix BUG-MANAGE-DOCS-001 (Infrastructure)**
- Add `docs_json` column to `scribe_projects` table (TEXT, nullable)
- Update `shared/logging_utils.py` query to return docs field
- Backfill existing projects with document metadata
- Verify all 17 actions can access registered documents

**2. Implement Auto-Registration (Edit Operations Only)**
- Detect unregistered files during edit operations
- Auto-register with Scribe project registry
- Update `docs_json` field atomically
- Log registration events to progress log

**EDIT Actions Getting Auto-Registration:**
- `list_sections` - Lists section anchors
- `replace_section` - Anchor-based updates
- `apply_patch` - Structured edits
- `replace_range` - Line-targeted edits
- `append` - Add to end
- `status_update` - Checklist toggles
- `normalize_headers` - ATX canonicalization
- `generate_toc` - Table of contents
- `search` - Semantic search

**CREATE Actions Staying Explicit:**
- `create_research_doc` - Explicit registration (by design)
- `create_bug_report` - Explicit registration (by design)

**3. Comprehensive Testing**
- Test all 17 actions post-fix
- Verify auto-registration triggers correctly
- Edge case testing (malformed files, missing frontmatter, etc.)
- Integration testing (doc_updates log, INDEX updates)

**4. Documentation**
- Update `docs/Scribe_Usage.md` with auto-registration behavior
- Create practical usage guide for agents
- Document action selection flowchart
- Add troubleshooting section

### ❌ OUT OF SCOPE

- PostgreSQL backend changes (SQLite only for now)
- Refactoring manage_docs architecture (working system, just needs fixes)
- Sentinel Mode case tool fixes (separate bug, different scope)
- New manage_docs actions (test existing 17 first)

---

## Technical Design

### 1. Database Schema Fix

**File:** `storage/sqlite.py`

**Change Required:**
```python
# Add to CREATE TABLE scribe_projects:
docs_json TEXT,  -- JSON-encoded document metadata
```

**Migration Strategy:**
- Check if column exists before adding (idempotent)
- Backfill from `state.json` or `generate_doc_templates` results
- Atomic transaction with rollback on failure

### 2. Query Update

**File:** `shared/logging_utils.py:111-119`

**Current (BROKEN):**
```python
cursor.execute("""
    SELECT name, root, progress_log
    FROM scribe_projects
    WHERE name = ?
""", (project_name,))
```

**Fixed:**
```python
cursor.execute("""
    SELECT name, root, progress_log, docs_json
    FROM scribe_projects
    WHERE name = ?
""", (project_name,))
```

**Parser Update:**
```python
project_data = {
    "name": row[0],
    "root": row[1],
    "progress_log": row[2],
    "docs": json.loads(row[3]) if row[3] else {}
}
```

### 3. Auto-Registration Logic

**File:** `tools/manage_docs.py`

**Insertion Point:** Before validation in edit operations

**Pseudocode:**
```python
async def manage_docs(action, doc, ...):
    # For EDIT operations only
    EDIT_ACTIONS = [
        "list_sections", "replace_section", "apply_patch",
        "replace_range", "append", "status_update",
        "normalize_headers", "generate_toc", "search"
    ]

    if action in EDIT_ACTIONS:
        project = await get_active_project()
        docs = project.get("docs", {})

        # Auto-register if not found
        if doc not in docs:
            logger.info(f"Auto-registering unregistered doc: {doc}")
            await _auto_register_document(project, doc)
            # Re-fetch project data with updated docs
            project = await get_active_project()

    # Proceed with normal validation
    ...
```

**Registration Function:**
```python
async def _auto_register_document(project, doc_key):
    """Auto-register document with project registry."""
    # Infer document path from doc_key
    doc_path = _resolve_doc_path(project, doc_key)

    if not os.path.exists(doc_path):
        raise ValueError(f"Cannot auto-register: {doc_path} does not exist")

    # Compute SHA256 hash
    with open(doc_path, 'rb') as f:
        doc_hash = hashlib.sha256(f.read()).hexdigest()

    # Update database
    await storage.execute("""
        UPDATE scribe_projects
        SET docs_json = json_set(
            COALESCE(docs_json, '{}'),
            '$.{doc_key}',
            json_object('path', ?, 'hash', ?)
        )
        WHERE name = ?
    """, (doc_path, doc_hash, project["name"]))

    # Log registration
    await append_entry(
        message=f"Auto-registered document: {doc_key} ({doc_path})",
        status="info",
        agent="manage_docs",
        meta={"action": "auto_register", "doc": doc_key}
    )
```

### 4. Testing Strategy

**Unit Tests:**
- Test database column addition (idempotent migration)
- Test query returns docs_json field
- Test auto-registration triggers on edit operations
- Test create operations DO NOT auto-register

**Integration Tests:**
- Test all 17 actions on registered documents
- Test edit operations on unregistered documents (should auto-register)
- Test create operations require explicit file creation
- Test atomic updates (concurrent edits)

**Edge Cases:**
- Missing files (auto-register should fail gracefully)
- Malformed YAML frontmatter (should handle or error clearly)
- Concurrent edits (locking behavior)
- Unicode filenames and content

---

## Implementation Phases

### Phase 1: Research & Design (Architect Agent - 1 hour)

**Deliverables:**
- Review Research Agent's findings (already complete)
- Design database migration strategy
- Design auto-registration logic
- Create comprehensive test plan
- Update specs: SPEC-MANAGE-DOCS-001, SPEC-MANAGE-DOCS-002

**Agent:** scribe-architect
**Input:** Research Agent's audit deliverables
**Output:** Updated architecture docs with implementation design

### Phase 2: Infrastructure Fix (Coder Agent - 2-3 hours)

**Tasks:**
1. Add `docs_json` column to scribe_projects table
2. Update `shared/logging_utils.py` query
3. Write migration function to backfill existing projects
4. Test database changes

**Agent:** scribe-coder
**Verification:** All 17 actions can access project.docs field

### Phase 3: Auto-Registration (Coder Agent - 2-3 hours)

**Tasks:**
1. Implement `_auto_register_document()` helper
2. Add auto-registration logic to edit operations
3. Ensure create operations remain explicit
4. Add logging for registration events

**Agent:** scribe-coder
**Verification:** Edit operations auto-register, create operations don't

### Phase 4: Comprehensive Testing (Coder Agent - 1-2 hours)

**Tasks:**
1. Test all 17 actions post-fix
2. Edge case testing
3. Integration testing
4. Performance testing (auto-registration overhead)

**Agent:** scribe-coder
**Verification:** 17/17 actions functional, auto-registration working

### Phase 5: Documentation (Coder Agent - 30 min)

**Tasks:**
1. Update `docs/Scribe_Usage.md`
2. Create usage guide for agents
3. Add troubleshooting section
4. Document auto-registration behavior

**Agent:** scribe-coder
**Verification:** Clear documentation for future agents

---

## Success Criteria

**Functional Requirements:**
- [ ] `docs_json` column exists in scribe_projects table
- [ ] Query returns complete project data (including docs)
- [ ] All 17 manage_docs actions functional
- [ ] Edit operations auto-register unregistered files
- [ ] Create operations remain explicit (no auto-registration)
- [ ] Registration events logged to progress log

**Quality Requirements:**
- [ ] 17/17 actions tested with pass results
- [ ] Edge cases handled gracefully
- [ ] Clear error messages for failures
- [ ] Documentation updated and comprehensive
- [ ] No performance regression (auto-registration <100ms)

**Audit Requirements:**
- [ ] ≥15 Scribe log entries documenting implementation
- [ ] All code changes have file:line references
- [ ] Test results documented with evidence
- [ ] Review Agent approval (≥93%)

---

## Risk Assessment

**High Risk:**
- Database migration fails → **Mitigation:** Idempotent migration, rollback on failure
- Auto-registration breaks existing workflows → **Mitigation:** Only edit ops affected, create ops unchanged

**Medium Risk:**
- Performance overhead from auto-registration → **Mitigation:** Cache registered docs, lazy loading
- Concurrent edit conflicts → **Mitigation:** File locking, atomic updates

**Low Risk:**
- Documentation incomplete → **Mitigation:** Comprehensive guide required in Phase 5
- Edge cases not covered → **Mitigation:** Exhaustive testing in Phase 4

---

## Dependencies

**Blocking:**
- None (all prerequisites met by Research Agent audit)

**Blocks:**
- Phase 5.5 completion (INDEX.md creation, wiki copy)
- Production wiki maintenance capability
- Future agent efficiency (auto-registration reduces friction)

---

## Timeline

**Sequential Execution (Cannot Parallelize):**
- Phase 1 (Architect): 1 hour
- Phase 2 (Coder): 2-3 hours
- Phase 3 (Coder): 2-3 hours (depends on Phase 2)
- Phase 4 (Coder): 1-2 hours (depends on Phase 3)
- Phase 5 (Coder): 30 min (depends on Phase 4)

**Total:** 6.5-9.5 hours (conservative estimate: 8 hours)

---

## Post-Implementation

**After manage_docs is production-ready:**
1. Resume Phase 5.5 tasks:
   - Correct sentinel_mode.md (case tools bug)
   - Create master INDEX.md
   - Execute selective wiki copy to /docs/wiki/
   - Update agent instructions to reference production wiki

2. Proceed to Phase 6: Architecture synthesis

---

## Approval

**Status:** ⏳ AWAITING USER APPROVAL

**Questions for User:**
1. Approve pivot plan scope? (Infrastructure fix + auto-registration)
2. Approve 6-8 hour estimate for full implementation?
3. Ready to deploy Architect Agent for Phase 1?

---

**Last Updated:** 2026-01-05 (Initial creation)
