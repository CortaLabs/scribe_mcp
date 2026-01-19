---
id: scribe_project_sitrep_hash_comparison-checklist
title: "\u2705 Acceptance Checklist \u2014 scribe_project_sitrep_hash_comparison"
doc_type: checklist
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

# ✅ Acceptance Checklist — scribe_project_sitrep_hash_comparison
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-06 10:33:43 UTC

> Acceptance checklist for scribe_project_sitrep_hash_comparison.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [ ] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md)- [ ] Phase plan current (proof: PHASE_PLAN.md)


---## Phase 0
<!-- ID: phase_0 -->
- [ ] Async write fix merged (proof: commit)- [ ] Verification enabled (proof: tests)


---
## Final Verification
<!-- ID: final_verification -->
- [ ] All checklist items checked with proofs attached.  
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.


---
## Phase 4.1: Core Infrastructure & BUG-001 Fix

**Component:** ProjectRecord Model Enhancement
- [ ] docs_json field added to ProjectRecord (storage/models.py:15)
  - Proof: Code reference to `docs_json: Optional[str] = None`
- [ ] docs_dict property method implemented
  - Proof: Method returns parsed dict, handles invalid JSON gracefully
- [ ] fetch_project() includes docs_json in SELECT query (storage/sqlite.py)
  - Proof: Query string includes "docs_json" column
- [ ] Row parsing constructs ProjectRecord with docs_json
  - Proof: ProjectRecord constructor receives docs_json parameter

**Component:** State Detection Logic (set_project.py)
- [ ] detect_project_state() function implemented
  - Proof: Function signature matches `(registry_info, entry_count) -> tuple[str, dict]`
- [ ] NEW state detection (no registry or no baseline+no entries)
  - Proof: Test `test_detect_state_new_*` passes
- [ ] EXISTING_LEGACY state detection (no baseline but entry_count > 0)
  - Proof: Test `test_detect_state_legacy_*` passes - **EDGE CASE CRITICAL**
- [ ] UNCHANGED state detection (baseline == current)
  - Proof: Test `test_detect_state_unchanged_*` passes
- [ ] MODIFIED state detection (baseline != current with doc list)
  - Proof: Test `test_detect_state_modified_*` passes

**Component:** BUG-001 Fix
- [ ] Line 459 logic replaced (removed `entry_count == 0`)
  - Proof: Grep shows no `entry_count == 0` in conditional
- [ ] Four-state conditional branches implemented (NEW/LEGACY/UNCHANGED/MODIFIED)
  - Proof: Code shows if/elif/elif/else structure with 4 states
- [ ] After log rotation, set_project shows UNCHANGED not NEW
  - Proof: Integration test `test_sitrep_lifecycle_with_rotation` passes - **PRIMARY BUG FIX**

**Component:** Helper Functions
- [ ] _build_doc_inventory() implemented with modification flags
  - Proof: Function signature includes `flags: Optional[Dict]` parameter
- [ ] _build_activity_summary() extracts registry metrics
  - Proof: Returns dict with total_entries, last_entry_at, last_access_at, status

**Testing:**
- [ ] 8-10 unit tests implemented and passing
  - Proof: pytest output shows all tests green
- [ ] Integration test validates rotation scenario
  - Proof: Test creates project, adds entries, rotates log, verifies state remains correct
- [ ] Edge case test for legacy projects
  - Proof: Test verifies project with no baseline but entries → EXISTING_LEGACY

---

## Phase 4.2: get_project SITREP Enhancement

**Component:** State Detection Integration
- [ ] get_project calls detect_project_state()
  - Proof: Code reference to function call with registry_info and entry_count
- [ ] backend.count_entries() called for edge case detection
  - Proof: Code shows `await backend.count_entries(project, filters=None)`
- [ ] activity_summary enhanced with state field
  - Proof: Dict includes "state" key with value from detect_project_state

**Component:** Recent Entries Display
- [ ] _read_recent_progress_entries() called with limit=5
  - Proof: Code reference showing existing helper function usage
- [ ] Recent entries passed to formatter
  - Proof: Function call includes recent_entries parameter
- [ ] NO truncation of entry messages
  - Proof: Manual test with long message (>200 chars) shows full text - **USER REQUIREMENT**

**Component:** Readable Format
- [ ] State displayed (NEW/EXISTING_LEGACY/UNCHANGED/MODIFIED)
  - Proof: Output shows state indicator
- [ ] 2-5 recent entries shown inline
  - Proof: Readable output contains "Recent Entries:" section with entries
- [ ] Modification flags shown (✏️ for modified, ✓ for unchanged)
  - Proof: Output shows ✏️ next to modified docs
- [ ] Token count ~150-200 tokens
  - Proof: Manual measurement of output string length

**Component:** JSON Format
- [ ] state field included
  - Proof: JSON response contains "state" key
- [ ] recent_entries array (limited to 5)
  - Proof: JSON response contains "recent_entries" array with max 5 items
- [ ] modified_docs list (if MODIFIED state)
  - Proof: JSON response contains "modified_docs" array when state is MODIFIED
- [ ] timestamps object with created_at, last_entry_at, last_access_at
  - Proof: JSON response contains "timestamps" object with all three fields

**Testing:**
- [ ] 8-10 unit tests implemented and passing
  - Proof: pytest output shows all format tests green
- [ ] Integration test validates modified docs shown
  - Proof: Test modifies doc, verifies get_project shows MODIFIED with doc list
- [ ] Manual test confirms no truncation
  - Proof: Screenshot or output showing full long message

---

## Phase 4.3: list_projects SITREP Enhancement

**Component:** Modification Flag Fix
- [ ] Hardcoded `"modified": False` removed at lines 89, 97, 105
  - Proof: Grep shows no `"modified": False` with TODO comment
- [ ] doc_flags read from registry_info.meta.docs.flags
  - Proof: Code shows `doc_flags.get("architecture_modified", False)`
- [ ] Per-document modification status accurate
  - Proof: Test verifies modified doc shows True, unchanged shows False

**Component:** Per-Project State Detection
- [ ] detect_project_state() called for each project
  - Proof: Code shows loop with state detection call per project
- [ ] backend.count_entries() called per project
  - Proof: Code shows entry counting in project loop
- [ ] state field included in project result
  - Proof: Result dict includes "state" key

**Component:** JSON Format with Pagination
- [ ] pagination info included (page, page_size, total, has_next, has_prev)
  - Proof: JSON response contains "pagination" object with all fields
- [ ] projects array paginated correctly
  - Proof: Test with 50 projects, page_size=10 returns 10 items
- [ ] summary with state counts
  - Proof: JSON response contains "summary.states" with counts for each state

**Component:** Readable Format
- [ ] State icons present (🆕 NEW, ✅ UNCHANGED, ✏️ MODIFIED, 📦 LEGACY)
  - Proof: Output shows emoji icons matching project states
- [ ] Modified docs listed for MODIFIED projects
  - Proof: Output shows "(modified: architecture, phase_plan)" for MODIFIED projects
- [ ] Token count <200 per project
  - Proof: Manual measurement of per-project output length - **USER REQUIREMENT**

**Testing:**
- [ ] 8-10 unit tests implemented and passing
  - Proof: pytest output shows all pagination and state tests green
- [ ] Integration test validates accurate states across multiple projects
  - Proof: Test creates NEW/UNCHANGED/MODIFIED projects, verifies list_projects shows correct states
- [ ] Performance test with 100 projects passes (<2s)
  - Proof: Test output shows duration < 2.0 seconds

---

## Final Integration & Verification

**Cross-Phase Integration:**
- [ ] All three tools use consistent detect_project_state() implementation
  - Proof: Code references show same function imported in set_project, get_project, list_projects
- [ ] State transitions work correctly (NEW → LEGACY → UNCHANGED → MODIFIED)
  - Proof: End-to-end test creates project, adds entries, calls manage_docs twice, verifies states
- [ ] Existing infrastructure reused (no duplicate implementations)
  - Proof: Code audit shows backend.count_entries, create_pagination_info, format_readable_log_entries all used

**BUG-001 Validation:**
- [ ] After log rotation, project remains UNCHANGED (not NEW)
  - Proof: Integration test passes - **PRIMARY SUCCESS CRITERION**
- [ ] Empty progress log does not trigger NEW state if baseline exists
  - Proof: Test verifies entry_count == 0 with baseline → UNCHANGED
- [ ] Legacy projects correctly identified (no baseline but has entries)
  - Proof: Test verifies old project without baseline → EXISTING_LEGACY

**Format Requirements Met:**
- [ ] Readable format shows 2-5 recent entries with NO truncation
  - Proof: Manual tests with various entry counts and message lengths
- [ ] JSON format includes all required fields (state, recent_entries, modified_docs, pagination)
  - Proof: JSON schema validation or manual inspection
- [ ] Token efficiency maintained (<200 per project for list_projects)
  - Proof: Token count measurements documented

**Testing Coverage:**
- [ ] 24-30 unit tests total (8-10 per phase)
  - Proof: pytest output shows full test count
- [ ] 4 integration tests pass (lifecycle, modified docs, accurate states, rotation)
  - Proof: pytest output shows integration tests green
- [ ] 1 performance test passes (100 projects < 2s)
  - Proof: Performance test output shows timing

**Documentation:**
- [ ] All code changes logged with append_entry
  - Proof: PROGRESS_LOG.md contains entries for each phase
- [ ] Implementation reports created per phase
  - Proof: Files exist documenting what was implemented
- [ ] Test results documented with proof
  - Proof: Test output files or screenshots included

---

## Architecture Completion Checklist

**Documents Complete:**
- [ ] ARCHITECTURE_GUIDE.md fully populated
  - Proof: All sections (problem_statement, architecture_overview, detailed_design) complete
- [ ] PHASE_PLAN.md with 3 implementation phases
  - Proof: Phases 4.1, 4.2, 4.3 documented with estimates and tests
- [ ] CHECKLIST.md with verification items
  - Proof: This document complete

**Logging Complete:**
- [ ] Minimum 10+ append_entry calls during architecture
  - Proof: PROGRESS_LOG.md contains 10+ entries from ArchitectAgent
- [ ] All architectural decisions logged with reasoning
  - Proof: Entries contain reasoning blocks with why/what/how
- [ ] Confidence scores documented
  - Proof: Meta fields include confidence values (≥0.9 for completion)

**Quality Gates:**
- [ ] All EXISTING components verified with code references
  - Proof: Architecture references specific file:line for existing infrastructure
- [ ] EXISTING vs NEW components clearly marked
  - Proof: Architecture distinguishes what exists vs what's being created
- [ ] No infrastructure replacement (reuse only)
  - Proof: Architecture uses backend.count_entries, create_pagination_info, etc.

**Final Sign-Off:**
- [ ] Architecture confidence ≥ 0.9
  - Proof: Final append_entry shows confidence: 0.9+
- [ ] All mandatory sections complete
  - Proof: ARCHITECTURE_GUIDE.md has problem_statement, architecture_overview, detailed_design
- [ ] Phase plan has 2-3 manageable tasks
  - Proof: PHASE_PLAN.md shows 3 phases (4.1, 4.2, 4.3) with 4-6 hour estimates
- [ ] Checklist traces to architecture and phases
  - Proof: Every checklist item references specific phase or architecture section
