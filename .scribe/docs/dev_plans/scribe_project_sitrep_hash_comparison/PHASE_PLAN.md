---
id: scribe_project_sitrep_hash_comparison-phase_plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_project_sitrep_hash_comparison"
doc_type: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-06'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — scribe_project_sitrep_hash_comparison
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-06 10:33:43 UTC

> Execution roadmap for scribe_project_sitrep_hash_comparison.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 0 — Foundation | Stabilize document writes and storage. | Async atomic write, SQLite mirror | 0.90 |
| Phase 1 — Templates | Introduce advanced Jinja2 template system. | Base templates, Custom template discovery | 0.80 |
Update this table as the project evolves. Confidence values should change as knowledge increases.


---
## Phase 0 — Phase 0 — Foundation
<!-- ID: phase_0 -->
**Objective:** Stabilize document writes and storage.

**Key Tasks:**
- Fix async bug- Add verification

**Deliverables:**
- Async atomic write- SQLite mirror

**Acceptance Criteria:**
- [ ] No silent failures (proof: tests)

**Dependencies:** Existing storage layer

**Notes:** Must complete before template overhaul.


---## Phase 1 — Phase 1 — Templates
<!-- ID: phase_1 -->
**Objective:** Introduce advanced Jinja2 template system.

**Key Tasks:**
- Add inheritance- Add sandboxing

**Deliverables:**
- Base templates- Custom template discovery

**Acceptance Criteria:**
- [ ] All built-in templates render (proof: pytest)

**Dependencies:** Phase 0

**Notes:** Focus on template authoring UX.


---
## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Foundation Complete | 2025-10-29 | DevTeam | 🚧 In Progress | PROGRESS_LOG.md |
| Template Engine Ship | 2025-11-02 | DevTeam | ⏳ Planned | Phase 1 tasks |
Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.


---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---
## Implementation Phases

### Phase 4.1: Core Infrastructure & BUG-001 Fix

**Duration:** 4-6 hours  
**Effort:** Medium  
**Priority:** CRITICAL (blocks all other work)

**Objective:** Fix BUG-001 where entry_count==0 after rotation incorrectly marks projects as NEW. Add docs_json to ProjectRecord model to enable custom document tracking.

**Files to Modify:**
1. `storage/models.py` (Lines 9-15)
   - Add `docs_json: Optional[str] = None` field to ProjectRecord
   - Add `docs_dict` property method for JSON parsing
   
2. `storage/sqlite.py` (fetch_project method)
   - Update SELECT query to include docs_json column (already exists at line 659)
   - Update row parsing to construct ProjectRecord with docs_json field

3. `tools/set_project.py` (Lines 459-502)
   - Replace `is_new = entry_count == 0` logic with hash-based detection
   - Add `detect_project_state(registry_info, entry_count)` helper function
   - Add `_build_doc_inventory(docs_dir, flags)` helper function
   - Add `_build_activity_summary(registry_info)` helper function
   - Update conditional branches for four states (NEW/EXISTING_LEGACY/UNCHANGED/MODIFIED)

**Dependencies:**
- None (this is the foundation phase)

**Success Criteria:**
- [ ] ProjectRecord.docs_json field accessible via fetch_project()
- [ ] ProjectRecord.docs_dict property returns parsed dictionary
- [ ] detect_project_state() correctly identifies all four states
- [ ] BUG-001 fixed: After log rotation, set_project shows UNCHANGED not NEW
- [ ] Edge case handled: Legacy projects (no baseline but has entries) marked EXISTING_LEGACY
- [ ] Unit tests pass: 8-10 tests for state detection logic
- [ ] Integration test passes: Create → add entries → rotate → verify state remains correct

**Testing Requirements:**

**Unit Tests (8-10):**
- `test_project_record_docs_json_field()` - Verify field exists and parses correctly
- `test_project_record_docs_dict_with_valid_json()` - Parse valid JSON
- `test_project_record_docs_dict_with_invalid_json()` - Handle malformed JSON gracefully
- `test_detect_state_new_no_registry()` - No database row → NEW
- `test_detect_state_new_no_baseline_no_entries()` - Registry exists but empty → NEW
- `test_detect_state_legacy_no_baseline_has_entries()` - Edge case → EXISTING_LEGACY
- `test_detect_state_unchanged_baseline_matches()` - baseline == current → UNCHANGED
- `test_detect_state_modified_baseline_differs()` - baseline != current → MODIFIED
- `test_set_project_after_rotation_unchanged()` - **BUG-001 PRIMARY FIX**
- `test_set_project_four_states()` - Verify all conditional branches

**Integration Test:**
```python
async def test_sitrep_lifecycle_with_rotation():
    # Create project
    result = await set_project("test_project")
    assert "NEW PROJECT CREATED" in result
    
    # Add entries
    await append_entry("First entry")
    await append_entry("Second entry")
    
    # Rotate log (makes entry_count == 0)
    await rotate_log()
    
    # CRITICAL: set_project should NOT show NEW
    result = await set_project("test_project")
    assert "NEW PROJECT CREATED" not in result
    assert "PROJECT ACTIVATED" in result
```

**Proof of Completion:**
- Code reference to ProjectRecord.docs_json field
- Test output showing BUG-001 fix (rotation test passes)
- All 8-10 unit tests passing
- Integration test proves state persists after rotation

---

### Phase 4.2: get_project SITREP Enhancement

**Duration:** 4-5 hours  
**Effort:** Medium  
**Priority:** HIGH

**Objective:** Enhance get_project to display accurate state with recent entries and modification flags. Implement both readable and JSON formats per user requirements.

**Dependencies:**
- Phase 4.1 complete (requires detect_project_state and ProjectRecord.docs_json)

**Files to Modify:**
1. `tools/get_project.py` (Lines 315-400)
   - Add state detection using `detect_project_state()`
   - Add `backend.count_entries()` call for edge case
   - Enhance activity_summary with state, doc_flags, modified_docs
   - Use existing `_read_recent_progress_entries()` for 2-5 recent entries
   - Update readable format to show recent entries inline
   - Update JSON format with state, recent_entries, modified_docs

2. `utils/response.py` (Optional enhancements)
   - Add modification indicators (✏️) to existing formatters (additive only)
   - No breaking changes required

**Success Criteria:**
- [ ] get_project returns state field (NEW/EXISTING_LEGACY/UNCHANGED/MODIFIED)
- [ ] Readable format displays 2-5 recent entries with NO truncation
- [ ] Readable format shows doc modification flags (✏️ for modified, ✓ for unchanged)
- [ ] JSON format includes all required fields (state, recent_entries, modified_docs, timestamps)
- [ ] Token count for readable format ~150-200 tokens
- [ ] Pagination support in JSON format (default page_size: 10)
- [ ] Unit tests pass: 8-10 tests for format output
- [ ] Manual testing confirms no message truncation

**Testing Requirements:**

**Unit Tests (8-10):**
- `test_get_project_state_detection()` - Verify state field present
- `test_get_project_recent_entries_display()` - Show 2-5 entries
- `test_get_project_no_truncation()` - Long messages fully displayed
- `test_get_project_modification_flags()` - Modified docs have ✏️ indicator
- `test_get_project_json_format_complete()` - All required fields present
- `test_get_project_json_pagination()` - Pagination info included
- `test_get_project_readable_format()` - Compact box rendering
- `test_get_project_new_state()` - NEW project display
- `test_get_project_modified_state()` - MODIFIED project with doc list
- `test_get_project_unchanged_state()` - UNCHANGED project

**Integration Test:**
```python
async def test_get_project_shows_modified_docs():
    await set_project("test_project")
    
    # Modify architecture via manage_docs
    await manage_docs(action="replace_section", doc="architecture", ...)
    
    # get_project should show MODIFIED state
    result = await get_project()
    assert result["state"] == "MODIFIED"
    assert "architecture" in result["modified_docs"]
    assert "baseline_hashes" in result["activity"]
    
    # Readable format should show ✏️ indicator
    readable = await get_project(format="readable")
    assert "✏️ ARCHITECTURE_GUIDE.md" in readable
```

**Proof of Completion:**
- Manual test output showing full messages (no truncation)
- Screenshot of readable format with recent entries
- JSON response with all required fields
- All 8-10 unit tests passing

---

### Phase 4.3: list_projects SITREP Enhancement

**Duration:** 4-5 hours  
**Effort:** Medium  
**Priority:** HIGH

**Objective:** Fix list_projects hardcoded `modified: False` bug and add per-project state detection. Implement pagination for JSON format and ensure readable format remains token-efficient.

**Dependencies:**
- Phase 4.1 complete (requires detect_project_state)
- Phase 4.2 complete (optional - format consistency)

**Files to Modify:**
1. `tools/list_projects.py` (Lines 84-250)
   - Replace hardcoded `"modified": False` at lines 89, 97, 105
   - Add per-project `detect_project_state()` calls
   - Add `backend.count_entries()` for each project
   - Read `registry_info.meta.docs.flags` for modification status
   - Enhance JSON format with pagination (use `create_pagination_info`)
   - Enhance readable format with state icons (🆕 NEW, ✅ UNCHANGED, ✏️ MODIFIED, 📦 LEGACY)

**Success Criteria:**
- [ ] Modification flags no longer hardcoded False
- [ ] Per-project state detection (NEW/EXISTING_LEGACY/UNCHANGED/MODIFIED)
- [ ] JSON format includes pagination (page, page_size, total, has_next, has_prev)
- [ ] JSON format includes summary with state counts
- [ ] Readable format uses state icons for visual identification
- [ ] Readable format token count <200 per project
- [ ] Pagination works for large project lists (50+ projects)
- [ ] Unit tests pass: 8-10 tests for pagination and state display

**Testing Requirements:**

**Unit Tests (8-10):**
- `test_list_projects_modification_flags_not_hardcoded()` - Flags read from registry
- `test_list_projects_state_detection()` - All four states represented
- `test_list_projects_json_pagination()` - Pagination info correct
- `test_list_projects_json_summary()` - State counts accurate
- `test_list_projects_readable_format_icons()` - State icons present
- `test_list_projects_readable_token_count()` - <200 tokens per project
- `test_list_projects_large_dataset()` - 50 projects paginated correctly
- `test_list_projects_modified_docs_list()` - Modified docs shown for MODIFIED state
- `test_list_projects_page_boundaries()` - First/last page edge cases
- `test_list_projects_empty_result()` - No projects graceful handling

**Integration Test:**
```python
async def test_list_projects_shows_accurate_states():
    # Create multiple projects in different states
    await set_project("new_project")  # NEW state
    
    await set_project("unchanged_project")
    await manage_docs(action="replace_section", ...)  # Set baseline
    # Remains UNCHANGED
    
    await set_project("modified_project")
    await manage_docs(action="replace_section", ...)  # Set baseline
    await manage_docs(action="replace_section", ...)  # Modify again
    # Now MODIFIED
    
    # list_projects should show correct states
    result = await list_projects(format="json")
    assert result["summary"]["states"]["new"] == 1
    assert result["summary"]["states"]["unchanged"] == 1
    assert result["summary"]["states"]["modified"] == 1
    
    # Verify modification flags not hardcoded
    modified_proj = [p for p in result["projects"] if p["name"] == "modified_project"][0]
    assert modified_proj["documents"]["architecture"]["modified"] == True
```

**Performance Test:**
```python
async def test_list_projects_performance_100_projects():
    # Create 100 test projects
    for i in range(100):
        await set_project(f"perf_test_{i}")
    
    # Measure response time
    start = time.time()
    result = await list_projects(format="json", page=1, page_size=20)
    duration = time.time() - start
    
    assert duration < 2.0  # Must complete in under 2 seconds
    assert len(result["projects"]) == 20
    assert result["pagination"]["total_count"] == 100
```

**Proof of Completion:**
- Test output showing actual modification flags (not hardcoded False)
- JSON response with pagination and state summary
- Readable format under 200 tokens per project (measurement)
- All 8-10 unit tests passing
- Performance test passes (<2s for 100 projects)

---

## Phase Summary

**Total Implementation Time:** 12-16 hours  
**Total Tests:** 24-30 unit tests + 4 integration tests + 1 performance test

**Phase Dependencies:**
```
Phase 4.1 (Foundation)
    ↓
Phase 4.2 (get_project) ← Independent
    ↓ (format consistency)
Phase 4.3 (list_projects)
```

**Rollout Strategy:**
1. Phase 4.1 must complete and pass all tests before proceeding
2. Phases 4.2 and 4.3 can be developed in parallel after 4.1 (optional)
3. Each phase must have all tests passing before Review Agent validation
4. Integration tests run after all phases complete to validate end-to-end workflow

**Risk Mitigation:**
- Phase 4.1 is CRITICAL - if it fails, all other phases blocked
- Each phase has independent test suite for early failure detection
- Integration tests catch cross-phase issues
- Performance test ensures scalability with large project counts

**Coder Agent Guidance:**
- Implement phases sequentially (4.1 → 4.2 → 4.3)
- Run unit tests after each component change
- Log every meaningful change with `append_entry`
- Do NOT skip edge case tests (legacy project detection critical)
- Verify token counts manually for readable formats
- Use existing infrastructure (NO new pagination/counting implementations)
