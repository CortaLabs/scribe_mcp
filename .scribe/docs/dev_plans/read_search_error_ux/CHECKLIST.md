---
id: read_search_error_ux-checklist
title: "\u2705 Acceptance Checklist \u2014 read_search_error_ux"
doc_name: checklist
category: checklist|engineering
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

# ✅ Acceptance Checklist — read_search_error_ux
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-02 06:51:10 UTC

> Acceptance checklist for read_search_error_ux.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Phase 1: Helper Module Foundation
<!-- ID: phase1 -->

### Task 1.1: Create utils/path_suggestions.py <!-- ID: phase1_task1_1 -->
- [ ] **Module created with 5 helper functions**
  - **Acceptance:** `utils/path_suggestions.py` exists with all 5 functions implemented
  - **Verification:** `python -c "from utils.path_suggestions import get_fuzzy_file_suggestions, get_directory_listing, classify_path_error, build_search_suggestion, build_read_suggestion"`

- [ ] **All functions have type hints and docstrings**
  - **Acceptance:** Every function has complete type hints (args + return) and docstring with Args/Returns
  - **Verification:** Code review of `utils/path_suggestions.py`

- [ ] **Constants defined correctly**
  - **Acceptance:** MAX_FUZZY_SUGGESTIONS=5, MAX_DIRECTORY_ENTRIES=30, MAX_SCAN_FILES=1000, FUZZY_CUTOFF=0.6
  - **Verification:** `grep "MAX_FUZZY_SUGGESTIONS = 5" utils/path_suggestions.py`

- [ ] **Error handling: all filesystem ops wrapped in try/except**
  - **Acceptance:** No function raises exceptions to caller, graceful degradation on errors
  - **Verification:** Code review + manual test with unreadable directory

### Task 1.2: Unit Tests for path_suggestions <!-- ID: phase1_task1_2 -->
- [ ] **Test file created with ≥20 tests**
  - **Acceptance:** `tests/test_path_suggestions.py` exists with minimum 20 test functions
  - **Verification:** `pytest tests/test_path_suggestions.py -v --collect-only | grep "test_" | wc -l` (should be ≥20)

- [ ] **All tests pass**
  - **Acceptance:** 100% test pass rate, no failures or errors
  - **Verification:** `pytest tests/test_path_suggestions.py -v`

- [ ] **Coverage ≥95% for path_suggestions.py**
  - **Acceptance:** Line coverage ≥95% for utils/path_suggestions.py
  - **Verification:** `pytest tests/test_path_suggestions.py --cov=utils.path_suggestions --cov-report=term`

- [ ] **Edge cases tested (empty dirs, large dirs, permissions, symlinks)**
  - **Acceptance:** Tests cover: empty directory, >1000 files, permission errors, broken symlinks
  - **Verification:** Code review of test file, verify tests exist for each edge case

---

## Phase 2: Tool Integration
<!-- ID: phase2 -->

### Task 2.1: Enhance read_file.py Error Path <!-- ID: phase2_task2_1 -->
- [ ] **Imports added for path_suggestions helpers**
  - **Acceptance:** `from utils.path_suggestions import ...` present in imports section
  - **Verification:** `grep "from utils.path_suggestions import" tools/read_file.py`

- [ ] **Error path at line 1816-1827 enhanced**
  - **Acceptance:** classify_path_error() called, error_type added to response, lazy evaluation for format="readable"
  - **Verification:** Code review of tools/read_file.py lines 1816-1850 region

- [ ] **Fuzzy suggestions appear for format="readable"**
  - **Acceptance:** Non-existent file with format="readable" shows similar_files in response
  - **Verification:** Manual test: `read_file(path="nonexistent_auth_handlers.py", format="readable")` shows suggestions

- [ ] **No suggestions for format="structured" (performance check)**
  - **Acceptance:** format="structured" returns minimal error without computing suggestions
  - **Verification:** Manual test + check response doesn't contain similar_files key

- [ ] **Directory error distinguished from not_found**
  - **Acceptance:** Path to directory returns error="path is a directory", not "file not found"
  - **Verification:** Manual test: `read_file(path="src/", format="readable")` shows "is a directory"

### Task 2.2: Enhance search.py Error Path <!-- ID: phase2_task2_2 -->
- [ ] **Imports added for path_suggestions helpers**
  - **Acceptance:** `from utils.path_suggestions import ...` present in imports section
  - **Verification:** `grep "from utils.path_suggestions import" tools/search.py`

- [ ] **Error path at line 664 enhanced**
  - **Acceptance:** Fuzzy suggestions and directory listing added when format="readable"
  - **Verification:** Code review of tools/search.py line 664 region

- [ ] **Directory suggestions prioritized**
  - **Acceptance:** Filter `[s for s in suggestions if s.get("is_dir")]` applied
  - **Verification:** Code review + manual test confirms directories shown first

- [ ] **No suggestions for format="structured"**
  - **Acceptance:** format="structured" returns minimal error
  - **Verification:** Manual test: `search(path="nonexistent/", format="structured")` minimal response

### Task 2.3: Integration Tests <!-- ID: phase2_task2_3 -->
- [ ] **read_file integration tests created (5 tests minimum)**
  - **Acceptance:** tests/test_read_file_errors.py has ≥5 tests for enhanced error paths
  - **Verification:** `pytest tests/test_read_file_errors.py -v --collect-only | grep "test_read_file" | wc -l`

- [ ] **search integration tests created (3 tests minimum)**
  - **Acceptance:** tests/test_search_errors.py has ≥3 tests for enhanced error paths
  - **Verification:** `pytest tests/test_search_errors.py -v --collect-only | grep "test_search" | wc -l`

- [ ] **All integration tests pass**
  - **Acceptance:** 100% pass rate on both test files
  - **Verification:** `pytest tests/test_read_file_errors.py tests/test_search_errors.py -v`

- [ ] **Backwards compatibility verified**
  - **Acceptance:** Core error fields (ok, error, absolute_path) always present, structured format unchanged
  - **Verification:** Test assertions check for required fields in all formats

---

## Final Verification
<!-- ID: final_verification -->

- [ ] **No crashes on edge cases**
  - **Acceptance:** No exceptions raised for: permission errors, large directories (>1000 files), symlinks, empty dirs
  - **Verification:** Manual testing + integration tests cover all edge cases

- [ ] **Performance regression check**
  - **Acceptance:** Error paths add <5ms latency (measure with time.time() before/after)
  - **Verification:** Optional benchmark test or manual timing check

- [ ] **All tests pass (unit + integration)**
  - **Acceptance:** `pytest tests/test_path_suggestions.py tests/test_read_file_errors.py tests/test_search_errors.py -v` shows 0 failures
  - **Verification:** Full test suite run

- [ ] **Code quality: no new linting errors**
  - **Acceptance:** `pylint utils/path_suggestions.py tools/read_file.py tools/search.py` reports no new errors
  - **Verification:** Linter run (or manual code review if linter not configured)

- [ ] **Documentation complete**
  - **Acceptance:** ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md all updated and accurate
  - **Verification:** Review all three documents match implemented code

- [ ] **Manual testing with real codebase**
  - **Acceptance:** Tested with actual mistyped paths in real projects, suggestions are helpful and accurate
  - **Verification:** Try with scribe_mcp codebase itself (e.g., typo in "tools/append_entry.py")
<!-- ID: phase_0 -->
- [ ] Async write fix merged (proof: commit)
- [ ] Verification enabled (proof: tests)



---
## Final Verification
<!-- ID: final_verification -->
- [ ] All checklist items checked with proofs attached.  
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.


---