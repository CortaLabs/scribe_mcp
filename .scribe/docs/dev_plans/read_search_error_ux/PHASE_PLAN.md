---
id: read_search_error_ux-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 read_search_error_ux"
doc_name: phase_plan
category: phase_plan|engineering
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

# ⚙️ Phase Plan — read_search_error_ux
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-02 06:51:10 UTC

> Execution roadmap for read_search_error_ux.

---
## Phase Overview
<!-- ID: phase_overview -->
**Total Phases:** 2 (Foundation + Integration)
**Estimated Timeline:** 1-2 coding sessions total
**Priority:** Focused improvement to error UX (no major refactoring)

### Phase Summary

| Phase | Focus | Deliverables | Est. Complexity |
|-------|-------|--------------|-----------------|
| Phase 1 | Helper Module | `utils/path_suggestions.py` + unit tests | Low-Medium |
| Phase 2 | Tool Integration | Enhance `read_file.py` and `search.py` error paths | Low |

**Dependencies:**
- Phase 2 depends on Phase 1 (needs helper module)
- No external dependencies (difflib already in stdlib)
- No breaking changes (additive improvements only)
<!-- ID: phase_0 -->
## Phase 1 — Helper Module Foundation
<!-- ID: phase_1 -->

**Objective:** Create shared path suggestion infrastructure with comprehensive tests

**Duration:** ~1 coding session
**Prerequisites:** None (self-contained)
**Risk Level:** Low (pure utility module, no integration dependencies)

### Task Package 1.1: Create `utils/path_suggestions.py`

**Scope:** Implement 5 helper functions for error enrichment

**Files to Create:**
- `utils/path_suggestions.py` (new file, ~200-300 lines)

**Specifications:**

1. **Module Constants**
   ```python
   MAX_FUZZY_SUGGESTIONS = 5
   MAX_DIRECTORY_ENTRIES = 30
   MAX_SCAN_FILES = 1000
   FUZZY_CUTOFF = 0.6
   ```

2. **`get_fuzzy_file_suggestions(target_name, parent_dir, ...)`**
   - Use `difflib.get_close_matches(target_name, possibilities, n=max_suggestions, cutoff=cutoff)`
   - Get possibilities via `parent_dir.iterdir()`, filter by `include_directories` param
   - Return list of dicts: `[{"name": str, "score": float, "is_dir": bool}, ...]`
   - Wrap in try/except, return `[]` on any filesystem error
   - Cap iteration at MAX_SCAN_FILES for performance protection

3. **`get_directory_listing(directory, ...)`**
   - Use `directory.iterdir()` to scan entries
   - Separate files and directories if `separate_files_dirs=True`
   - Skip hidden files unless `include_hidden=True`
   - Cap at `max_entries` per category
   - Return dict with keys: `files`, `directories`, `truncated`, `total_scanned`, `permission_error`
   - Wrap in try/except, return `{"permission_error": True}` on OSError/PermissionError

4. **`classify_path_error(target)`**
   - Check `target.exists()` → if False, return "not_found"
   - Check `target.is_dir()` → if True, return "is_directory"
   - Check `target.is_symlink() and not target.is_file()` → return "is_symlink"
   - Try `target.stat()`, catch PermissionError → return "permission_denied"
   - Default return "unknown"

5. **`build_search_suggestion(pattern, path, agent)`**
   - Return f-string: `f'search(agent="{agent}", pattern="{pattern}", path="{path}")'`
   - Escape double quotes in inputs if present

6. **`build_read_suggestion(file_path, agent, mode="scan_only")`**
   - Return f-string: `f'read_file(agent="{agent}", path="{file_path}", mode="{mode}")'`
   - Escape double quotes in inputs if present

**Error Handling Requirements:**
- ALL filesystem operations (iterdir, exists, is_dir, etc.) wrapped in try/except
- NEVER raise exceptions to caller
- Gracefully degrade to empty/minimal results on any error
- Log errors to sentinel optional (not required for Phase 1)

**Verification:**
- Run `python -m utils.path_suggestions` (should import without errors)
- No external dependencies beyond stdlib (difflib, pathlib, typing)
- All functions have type hints
- All functions have docstrings with Args/Returns sections

### Task Package 1.2: Unit Tests for `utils/path_suggestions.py`

**Scope:** Comprehensive unit test coverage (≥95%)

**Files to Create:**
- `tests/test_path_suggestions.py` (new file, ~300-400 lines)

**Test Requirements (minimum 20 tests):**

**Fuzzy Matching Tests (6 tests):**
1. `test_fuzzy_match_exact()` - Exact match scores 1.0
2. `test_fuzzy_match_close()` - "auth_handlers.py" → "auth_handler.py" scores >0.9
3. `test_fuzzy_match_no_matches()` - Completely different names return []
4. `test_fuzzy_match_cutoff()` - Matches below 0.6 filtered out
5. `test_fuzzy_match_max_suggestions()` - Respects max_suggestions parameter
6. `test_fuzzy_match_include_directories()` - include_directories flag works

**Directory Listing Tests (6 tests):**
7. `test_directory_listing_normal()` - Standard dir with <30 items
8. `test_directory_listing_large()` - Dir with >30 items truncates correctly
9. `test_directory_listing_empty()` - Empty dir returns empty lists
10. `test_directory_listing_permission_error()` - Unreadable dir returns permission_error=True
11. `test_directory_listing_separate()` - Separates files and dirs correctly
12. `test_directory_listing_hidden()` - Respects include_hidden parameter

**Error Classification Tests (5 tests):**
13. `test_classify_not_found()` - Non-existent path → "not_found"
14. `test_classify_is_directory()` - Existing dir → "is_directory"
15. `test_classify_permission_denied()` - Unreadable path → "permission_denied" (optional, may be hard to set up)
16. `test_classify_symlink()` - Broken symlink → "is_symlink"
17. `test_classify_regular_file()` - Regular accessible file → handled without classification (not an error case)

**Suggestion Builder Tests (3 tests):**
18. `test_build_search_suggestion()` - Formats valid search command
19. `test_build_read_suggestion()` - Formats valid read_file command
20. `test_build_suggestion_escaping()` - Escapes quotes in inputs

**Performance Tests (optional but recommended):**
21. `test_fuzzy_match_performance()` - 1000 files completes in <10ms

**Verification:**
- Run `pytest tests/test_path_suggestions.py -v`
- All tests pass
- Coverage ≥95% for utils/path_suggestions.py
- No test dependencies beyond pytest, tempfile, pathlib

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify any existing tool files (read_file.py, search.py)
- Do NOT integrate with tools yet (that's Phase 2)
- Do NOT add formatter changes

---

## Phase 2 — Tool Integration
<!-- ID: phase_2 -->

**Objective:** Integrate path_suggestions into read_file and search error paths

**Duration:** ~1 coding session
**Prerequisites:** Phase 1 complete (utils/path_suggestions.py exists and tested)
**Risk Level:** Low (small, isolated changes to error paths only)

### Task Package 2.1: Enhance `read_file.py` Error Path

**Scope:** Replace minimal error at line 1816-1827 with enriched error using path_suggestions

**Files to Modify:**
- `tools/read_file.py` (lines 1816-1827 region)

**Specifications:**

1. **Import path_suggestions helpers** (add to imports section):
   ```python
   from utils.path_suggestions import (
       classify_path_error,
       get_fuzzy_file_suggestions,
       get_directory_listing,
       build_search_suggestion
   )
   ```

2. **Replace error block at lines 1816-1827:**
   - Split `not target.exists() or not target.is_file()` check
   - Call `classify_path_error(target)` to get error_type
   - Build error_response dict with error_type field
   - **Only if `requested_mode == "readable"`:**
     - Call `get_fuzzy_file_suggestions(target.name, target.parent, ...)`
     - Call `get_directory_listing(target.parent)`
     - Call `build_search_suggestion(target.stem, str(target.parent), agent)`
     - Add suggestions/listings to error_response
   - Existing `log_read()` and `finalize_response()` calls unchanged

3. **Error message mapping:**
   ```python
   error_messages = {
       "not_found": "file not found",
       "is_directory": "path is a directory",
       "permission_denied": "permission denied",
       "is_symlink": "path is a symbolic link (not a regular file)",
       "unknown": "file not accessible"
   }
   ```

**Verification:**
- Test with non-existent file: should show fuzzy suggestions
- Test with directory path: should show "path is a directory" error
- Test with format="structured": should NOT compute suggestions (performance check)
- Test with format="readable": should show enriched error

**Out of Scope:**
- Do NOT modify any other error paths in read_file.py
- Do NOT change formatter logic
- Do NOT modify search.py (that's Task 2.2)

### Task Package 2.2: Enhance `search.py` Error Path

**Scope:** Replace minimal error at line 664 with enriched error using path_suggestions

**Files to Modify:**
- `tools/search.py` (line 664 region)

**Specifications:**

1. **Import path_suggestions helpers** (add to imports section):
   ```python
   from utils.path_suggestions import (
       get_fuzzy_file_suggestions,
       get_directory_listing,
       build_read_suggestion
   )
   ```

2. **Replace error at line 664:**
   - Build error_response dict with error_type="not_found" field
   - **Only if `format == "readable"`:**
     - Call `get_fuzzy_file_suggestions(search_root.name, search_root.parent, include_directories=True)`
     - Filter suggestions to prioritize directories: `[s for s in suggestions if s.get("is_dir")]`
     - Call `get_directory_listing(search_root.parent)`
     - Add suggestions/listings to error_response
   - Return error_response (no async needed here)

**Verification:**
- Test with non-existent path: should show fuzzy directory suggestions
- Test with format="structured": should NOT compute suggestions
- Test with format="readable": should show enriched error with parent listing

**Out of Scope:**
- Do NOT modify any other error paths in search.py
- Do NOT change formatter logic
- Do NOT modify read_file.py (already done in Task 2.1)

### Task Package 2.3: Integration Tests

**Scope:** End-to-end tests for both enhanced error paths

**Files to Create/Modify:**
- `tests/test_read_file_errors.py` (new or extend existing)
- `tests/test_search_errors.py` (new or extend existing)

**Test Requirements (minimum 8 tests):**

**read_file tests (5 tests):**
1. `test_read_file_not_found_readable()` - format="readable" shows suggestions
2. `test_read_file_not_found_structured()` - format="structured" minimal response
3. `test_read_file_is_directory()` - Directory path shows correct error type
4. `test_read_file_permission_error()` - Graceful degradation on permission issues
5. `test_read_file_large_parent_dir()` - Parent with many files doesn't crash

**search tests (3 tests):**
6. `test_search_path_not_found_readable()` - format="readable" shows suggestions
7. `test_search_path_not_found_structured()` - format="structured" minimal response
8. `test_search_parent_unreadable()` - Graceful degradation

**Verification:**
- Run `pytest tests/test_read_file_errors.py tests/test_search_errors.py -v`
- All tests pass
- No crashes on edge cases
- Backwards compatibility maintained

**Out of Scope:**
- Do NOT add performance benchmarks (nice-to-have, not required)
- Do NOT test formatter rendering (that's FormatterDispatcher's job)
<!-- ID: phase_1 -->
**Objective:** Introduce advanced Jinja2 template system.

**Key Tasks:**
- Add inheritance
- Add sandboxing


**Deliverables:**
- Base templates
- Custom template discovery


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