# ✅ Dependency Analysis Checklist — read_file_enhancement

**Feature:** Optional dependency analysis for read_file tool
**Sub-Plan:** dependency_analysis
**Version:** 1.0
**Status:** Planning Phase
**Author:** ArchitectAgent
**Last Updated:** 2026-01-07

> This checklist provides verification criteria for each phase of the dependency analysis implementation. All items must be verified before marking phase complete.

---

## Phase 1: Basic Import Extraction
<!-- ID: phase1 -->

### Implementation Tasks

- [ ] **Task 1.1: Add include_dependencies parameter** <!-- ID: phase1_task1 -->
  - **Location:** tools/read_file.py line ~648
  - **Changes:** Add `include_dependencies: bool = False` to read_file() signature
  - **Acceptance:** Parameter accepts bool, default False, docstring updated
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_include_dependencies_default_false`

- [ ] **Task 1.2: Implement _extract_imports() function** <!-- ID: phase1_task2 -->
  - **Location:** tools/read_file.py after _extract_python_structure() (~line 435)
  - **Changes:** Create ~60-80 line function to walk AST and extract Import/ImportFrom nodes
  - **Acceptance:** Function returns list of import dicts with all required fields
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_extract_import_statements -v`

- [ ] **Task 1.3: Handle ast.Import nodes** <!-- ID: phase1_task3 -->
  - **Changes:** Extract module name, line, alias from ast.Import nodes
  - **Acceptance:** Handles `import x` and `import x as y` correctly
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_extract_import_statements`

- [ ] **Task 1.4: Handle ast.ImportFrom nodes** <!-- ID: phase1_task4 -->
  - **Changes:** Extract module, line, names, level from ast.ImportFrom nodes
  - **Acceptance:** Handles `from x import y`, `from . import x`, `from ..x import y`
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_extract_from_imports`

- [ ] **Task 1.5: Detect relative import levels** <!-- ID: phase1_task5 -->
  - **Changes:** Correctly extract level field (0=absolute, 1=., 2=.., etc.)
  - **Acceptance:** Level field matches dot count in import statement
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_relative_import_detection`

- [ ] **Task 1.6: Verify line number accuracy** <!-- ID: phase1_task6 -->
  - **Changes:** Ensure lineno from AST nodes is accurate
  - **Acceptance:** Line numbers match actual import statement lines in source
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_line_number_accuracy`

- [ ] **Task 1.7: Implement import truncation** <!-- ID: phase1_task7 -->
  - **Changes:** Limit extraction to max_imports (default 100)
  - **Acceptance:** Truncation works, truncated flag set correctly
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_import_truncation`

- [ ] **Task 1.8: Integrate with _scan_file()** <!-- ID: phase1_task8 -->
  - **Location:** tools/read_file.py inside _scan_file() (~line 425)
  - **Changes:** Call _extract_imports() when include_dependencies=True
  - **Acceptance:** Dependencies object added to structure when flag is True
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_structured_mode_schema`

- [ ] **Task 1.9: Update response schema** <!-- ID: phase1_task9 -->
  - **Changes:** Return dependencies object with imports, total_imports, unresolved, truncated
  - **Acceptance:** Response structure matches specification
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_structured_mode_schema`

- [ ] **Task 1.10: Create _format_dependencies() function** <!-- ID: phase1_task10 -->
  - **Location:** utils/response.py
  - **Changes:** Create ~80-100 line function to format dependencies for readable mode
  - **Acceptance:** Function returns formatted string with import grouping
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_readable_mode_formatting`

- [ ] **Task 1.11: Integrate formatter with format_readable_file_content()** <!-- ID: phase1_task11 -->
  - **Location:** utils/response.py
  - **Changes:** Call _format_dependencies() when dependencies present in structure
  - **Acceptance:** Dependencies section appears in readable mode output
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_readable_mode_formatting`

### Testing Tasks

- [ ] **Task 1.12: Create test file** <!-- ID: phase1_task12 -->
  - **File:** tests/test_read_file_dependencies.py
  - **Acceptance:** File created with proper imports and setup
  - **Verification:** `pytest tests/test_read_file_dependencies.py --collect-only`

- [ ] **Task 1.13: Write Phase 1 test cases** <!-- ID: phase1_task13 -->
  - **Cases:** Tests 1-9 from Phase Plan
  - **Acceptance:** All 9 test cases implemented and passing
  - **Verification:** `pytest tests/test_read_file_dependencies.py -v --tb=short`

- [ ] **Task 1.14: Test with real scribe_mcp files** <!-- ID: phase1_task14 -->
  - **Files:** tools/append_entry.py, tools/read_file.py, utils/response.py
  - **Acceptance:** Real files extract imports correctly
  - **Verification:** Manual verification of import extraction accuracy

- [ ] **Task 1.15: Test edge case - no imports** <!-- ID: phase1_task15 -->
  - **Case:** File with no import statements
  - **Acceptance:** Empty imports list, no errors
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_python_file_with_no_imports`

### Performance Tasks

- [ ] **Task 1.16: Benchmark default behavior** <!-- ID: phase1_task16 -->
  - **Test:** Run read_file() with include_dependencies=False
  - **Acceptance:** Zero overhead compared to current implementation
  - **Verification:** Performance benchmark shows <1% difference

- [ ] **Task 1.17: Benchmark extraction overhead** <!-- ID: phase1_task17 -->
  - **Test:** Run read_file() with include_dependencies=True (Phase 1 only)
  - **Acceptance:** <10% overhead for extraction alone
  - **Verification:** Performance benchmark on 1000+ line files

### Documentation Tasks

- [ ] **Task 1.18: Update read_file() docstring** <!-- ID: phase1_task18 -->
  - **Location:** tools/read_file.py
  - **Changes:** Document include_dependencies parameter
  - **Acceptance:** Docstring explains parameter, default, behavior
  - **Verification:** Code review

- [ ] **Task 1.19: Update Scribe_Usage.md** <!-- ID: phase1_task19 -->
  - **Location:** docs/Scribe_Usage.md
  - **Changes:** Add include_dependencies parameter documentation
  - **Acceptance:** Examples show usage with readable/structured modes
  - **Verification:** Documentation review

- [ ] **Task 1.20: Update SKILL.md** <!-- ID: phase1_task20 -->
  - **Location:** .codex/skills/scribe-mcp-usage/SKILL.md
  - **Changes:** Update read_file() signature with new parameter
  - **Acceptance:** Signature matches actual implementation
  - **Verification:** Documentation review

### Phase 1 Completion Criteria

- [ ] **All implementation tasks complete (1.1-1.11)** <!-- ID: phase1_completion1 -->
  - **Proof:** All code committed and pushed
  - **Verification:** Git log shows commits

- [ ] **All testing tasks complete (1.12-1.15)** <!-- ID: phase1_completion2 -->
  - **Proof:** All 9 test cases passing
  - **Verification:** `pytest tests/test_read_file_dependencies.py -v`

- [ ] **All performance tasks complete (1.16-1.17)** <!-- ID: phase1_completion3 -->
  - **Proof:** Benchmark results show targets met
  - **Verification:** Performance report document

- [ ] **All documentation tasks complete (1.18-1.20)** <!-- ID: phase1_completion4 -->
  - **Proof:** Documentation updated and reviewed
  - **Verification:** Doc review checklist

---

## Phase 2: Path Resolution
<!-- ID: phase2 -->

### Implementation Tasks

- [ ] **Task 2.1: Implement _resolve_import_path() function** <!-- ID: phase2_task1 -->
  - **Location:** tools/read_file.py after _extract_imports()
  - **Changes:** Create ~80-100 line function for best-effort path resolution
  - **Acceptance:** Function resolves relative and absolute repo-local imports
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_relative_import_resolution`

- [ ] **Task 2.2: Handle relative import resolution** <!-- ID: phase2_task2 -->
  - **Changes:** Navigate up by level, check .py and __init__.py
  - **Acceptance:** Resolves `.`, `..`, `...` imports correctly
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_relative_import_resolution`

- [ ] **Task 2.3: Handle absolute repo-local resolution** <!-- ID: phase2_task3 -->
  - **Changes:** Check if module starts with repo name, resolve from repo root
  - **Acceptance:** Resolves scribe_mcp.tools.x style imports
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_absolute_repo_local_resolution`

- [ ] **Task 2.4: Handle external/stdlib detection** <!-- ID: phase2_task4 -->
  - **Changes:** Return None for non-repo modules
  - **Acceptance:** Returns None for pathlib, json, datetime, etc.
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_external_stdlib_unresolved`

- [ ] **Task 2.5: Detect __init__.py packages** <!-- ID: phase2_task5 -->
  - **Changes:** Check for __init__.py when resolving directory imports
  - **Acceptance:** Resolves package imports correctly
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_init_py_detection`

- [ ] **Task 2.6: Detect .py file modules** <!-- ID: phase2_task6 -->
  - **Changes:** Check for .py file when resolving module imports
  - **Acceptance:** Resolves file imports correctly
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_py_file_detection`

- [ ] **Task 2.7: Integrate resolution into _scan_file()** <!-- ID: phase2_task7 -->
  - **Location:** tools/read_file.py inside _scan_file()
  - **Changes:** Call _resolve_import_path() for each import, populate resolved_path
  - **Acceptance:** resolved_path field populated in import dicts
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_absolute_repo_local_resolution`

- [ ] **Task 2.8: Build unresolved list** <!-- ID: phase2_task8 -->
  - **Changes:** Track modules with resolved_path=None in unresolved list
  - **Acceptance:** Unresolved list contains external/stdlib module names
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_unresolved_tracking`

- [ ] **Task 2.9: Update _format_dependencies() for resolution** <!-- ID: phase2_task9 -->
  - **Location:** utils/response.py
  - **Changes:** Group by resolution status, show paths for resolved, [external] for unresolved
  - **Acceptance:** Readable mode groups imports by resolution status
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_readable_mode_formatting`

- [ ] **Task 2.10: Show resolved paths with arrow** <!-- ID: phase2_task10 -->
  - **Changes:** Format: `• module (line X) → path/to/file.py`
  - **Acceptance:** Resolved imports display with arrow and path
  - **Verification:** Manual visual verification

- [ ] **Task 2.11: Show unresolved with [external] tag** <!-- ID: phase2_task11 -->
  - **Changes:** Format: `• module (line X) [external]`
  - **Acceptance:** Unresolved imports display with tag
  - **Verification:** Manual visual verification

- [ ] **Task 2.12: Update dependencies section header** <!-- ID: phase2_task12 -->
  - **Changes:** Show unresolved count in header
  - **Acceptance:** Header shows: "📦 Dependencies (X imports, Y unresolved)"
  - **Verification:** Manual visual verification

### Testing Tasks

- [ ] **Task 2.13: Write Phase 2 test cases** <!-- ID: phase2_task13 -->
  - **Cases:** Tests 10-18 from Phase Plan
  - **Acceptance:** All 9 Phase 2 test cases implemented and passing
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_relative_import_resolution -v`

- [ ] **Task 2.14: Test relative import resolution** <!-- ID: phase2_task14 -->
  - **Cases:** `.`, `..`, `...` imports resolve correctly
  - **Acceptance:** Resolved paths match expected locations
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_relative_import_resolution`

- [ ] **Task 2.15: Test absolute repo-local resolution** <!-- ID: phase2_task15 -->
  - **Cases:** scribe_mcp.tools.x style imports resolve
  - **Acceptance:** Resolved paths match actual file locations
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_absolute_repo_local_resolution`

- [ ] **Task 2.16: Test external/stdlib unresolved** <!-- ID: phase2_task16 -->
  - **Cases:** pathlib, json, datetime return None
  - **Acceptance:** resolved_path is None, module in unresolved list
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_external_stdlib_unresolved`

- [ ] **Task 2.17: Test unresolved tracking** <!-- ID: phase2_task17 -->
  - **Cases:** Unresolved list populated correctly
  - **Acceptance:** All external imports tracked in unresolved list
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_unresolved_tracking`

- [ ] **Task 2.18: Test malformed import handling** <!-- ID: phase2_task18 -->
  - **Cases:** Broken import paths don't crash
  - **Acceptance:** Returns None gracefully, no exceptions
  - **Verification:** `pytest tests/test_read_file_dependencies.py::test_malformed_import_handling`

### Performance Tasks

- [ ] **Task 2.19: Benchmark Phase 2 overhead** <!-- ID: phase2_task19 -->
  - **Test:** Run read_file() with include_dependencies=True (extraction + resolution)
  - **Acceptance:** <20% overhead total (Phase 1 + Phase 2)
  - **Verification:** Performance benchmark on 1000+ line files

- [ ] **Task 2.20: Revalidate zero overhead when disabled** <!-- ID: phase2_task20 -->
  - **Test:** Run read_file() with include_dependencies=False
  - **Acceptance:** Still zero overhead after Phase 2 additions
  - **Verification:** Performance benchmark comparison with Phase 1

- [ ] **Task 2.21: Test with 100+ imports file** <!-- ID: phase2_task21 -->
  - **Test:** Large file with many imports
  - **Acceptance:** Performance within budget, truncation works
  - **Verification:** Performance test with tools/manage_docs.py (large file)

### Documentation Tasks

- [ ] **Task 2.22: Document path resolution strategy** <!-- ID: phase2_task22 -->
  - **Location:** docs/Scribe_Usage.md
  - **Changes:** Explain best-effort resolution, limitations, unresolved tracking
  - **Acceptance:** Documentation explains when resolution works vs doesn't
  - **Verification:** Documentation review

- [ ] **Task 2.23: Add resolution examples** <!-- ID: phase2_task23 -->
  - **Location:** docs/Scribe_Usage.md
  - **Changes:** Show examples of resolved and unresolved imports
  - **Acceptance:** Examples demonstrate grouping and formatting
  - **Verification:** Documentation review

- [ ] **Task 2.24: Create implementation report** <!-- ID: phase2_task24 -->
  - **File:** IMPLEMENTATION_REPORT_PHASE2_<timestamp>.md
  - **Changes:** Document implementation, test results, performance, lessons learned
  - **Acceptance:** Report complete with all metrics and findings
  - **Verification:** Report review

### Phase 2 Completion Criteria

- [ ] **All implementation tasks complete (2.1-2.12)** <!-- ID: phase2_completion1 -->
  - **Proof:** All code committed and pushed
  - **Verification:** Git log shows commits

- [ ] **All testing tasks complete (2.13-2.18)** <!-- ID: phase2_completion2 -->
  - **Proof:** All 18 total test cases passing (9 Phase 1 + 9 Phase 2)
  - **Verification:** `pytest tests/test_read_file_dependencies.py -v`

- [ ] **All performance tasks complete (2.19-2.21)** <!-- ID: phase2_completion3 -->
  - **Proof:** Benchmark results show <20% overhead, zero when disabled
  - **Verification:** Performance report document

- [ ] **All documentation tasks complete (2.22-2.24)** <!-- ID: phase2_completion4 -->
  - **Proof:** Documentation and implementation report complete
  - **Verification:** Doc review checklist

---

## Final Verification
<!-- ID: final_verification -->

### Code Quality

- [ ] **All functions have docstrings** <!-- ID: final_task1 -->
  - **Acceptance:** _extract_imports() and _resolve_import_path() fully documented
  - **Verification:** Code review

- [ ] **All error cases handled** <!-- ID: final_task2 -->
  - **Acceptance:** No unhandled exceptions, graceful degradation
  - **Verification:** Error case testing

- [ ] **Code follows existing patterns** <!-- ID: final_task3 -->
  - **Acceptance:** Matches style of _extract_python_structure() and other read_file code
  - **Verification:** Code review

### Test Coverage

- [ ] **All 18 test cases passing** <!-- ID: final_task4 -->
  - **Acceptance:** 100% test pass rate
  - **Verification:** `pytest tests/test_read_file_dependencies.py -v`

- [ ] **Edge cases covered** <!-- ID: final_task5 -->
  - **Acceptance:** No imports, malformed imports, truncation tested
  - **Verification:** Test coverage report

- [ ] **Real files tested** <!-- ID: final_task6 -->
  - **Acceptance:** Integration tests with actual scribe_mcp files pass
  - **Verification:** Integration test results

### Performance

- [ ] **Zero overhead when disabled** <!-- ID: final_task7 -->
  - **Acceptance:** include_dependencies=False has <1% difference
  - **Verification:** Performance benchmark

- [ ] **<20% overhead when enabled** <!-- ID: final_task8 -->
  - **Acceptance:** include_dependencies=True adds <20% overhead
  - **Verification:** Performance benchmark

- [ ] **Truncation prevents memory bloat** <!-- ID: final_task9 -->
  - **Acceptance:** Large files don't cause memory issues
  - **Verification:** Memory usage testing

### Documentation

- [ ] **Scribe_Usage.md updated** <!-- ID: final_task10 -->
  - **Acceptance:** Complete documentation with examples
  - **Verification:** Documentation review

- [ ] **SKILL.md updated** <!-- ID: final_task11 -->
  - **Acceptance:** Signature matches implementation
  - **Verification:** Documentation review

- [ ] **Implementation reports created** <!-- ID: final_task12 -->
  - **Acceptance:** Phase 1 and Phase 2 reports complete
  - **Verification:** Report review

### Integration

- [ ] **Read_file tool works with new parameter** <!-- ID: final_task13 -->
  - **Acceptance:** Existing callers unchanged, new callers can use flag
  - **Verification:** Integration testing

- [ ] **Readable mode displays correctly** <!-- ID: final_task14 -->
  - **Acceptance:** Dependencies section formatted properly
  - **Verification:** Manual visual verification

- [ ] **Structured mode schema correct** <!-- ID: final_task15 -->
  - **Acceptance:** Response structure matches specification
  - **Verification:** Schema validation tests

### Final Sign-Off

- [ ] **All Phase 1 tasks complete** <!-- ID: final_task16 -->
  - **Proof:** Phase 1 completion criteria met
  - **Verification:** Checklist review

- [ ] **All Phase 2 tasks complete** <!-- ID: final_task17 -->
  - **Proof:** Phase 2 completion criteria met
  - **Verification:** Checklist review

- [ ] **Ready for one-week evaluation period** <!-- ID: final_task18 -->
  - **Proof:** All tests passing, documentation complete, performance validated
  - **Verification:** Final review meeting

---

## Evaluation Period Checklist (Post-Phase 2)
<!-- ID: evaluation_period -->

**Duration:** One week minimum after Phase 2 deployment

### Usage Monitoring

- [ ] **Track include_dependencies usage frequency** <!-- ID: eval_task1 -->
  - **Target:** >10 uses per week indicates value
  - **Verification:** Log analysis

- [ ] **Track agent types using feature** <!-- ID: eval_task2 -->
  - **Question:** Which agents use it? Research? Architect? Review? Coder?
  - **Verification:** Log analysis

- [ ] **Track readable vs structured mode usage** <!-- ID: eval_task3 -->
  - **Question:** Do agents prefer readable display or structured data?
  - **Verification:** Log analysis

### Accuracy Evaluation

- [ ] **Measure path resolution accuracy** <!-- ID: eval_task4 -->
  - **Target:** >80% accuracy for repo-local imports
  - **Verification:** Manual spot-checking of resolved paths

- [ ] **Identify false positive resolutions** <!-- ID: eval_task5 -->
  - **Question:** Are any resolved paths incorrect?
  - **Verification:** Manual verification + bug reports

- [ ] **Identify false negative resolutions** <!-- ID: eval_task6 -->
  - **Question:** Are any unresolved imports actually resolvable?
  - **Verification:** Manual verification of unresolved list

### Governance Impact

- [ ] **Track boundary violations detected** <!-- ID: eval_task7 -->
  - **Question:** Are agents finding governance issues with dependency data?
  - **Verification:** Agent feedback + manual review

- [ ] **Track impact radius usage** <!-- ID: eval_task8 -->
  - **Question:** Do agents make better refactoring decisions with dependency info?
  - **Verification:** Agent feedback

- [ ] **Track dead code identification** <!-- ID: eval_task9 -->
  - **Question:** Are agents identifying unused files?
  - **Verification:** Agent feedback

### Decision Point

- [ ] **Decide on Phase 3+ implementation** <!-- ID: eval_task10 -->
  - **Criteria:** High usage (>10/week) + governance value demonstrated + accuracy >80%
  - **Options:** Proceed with Phase 3, stop and maintain Phase 2, or deprecate feature
  - **Verification:** Team decision meeting

---

## Summary Statistics

**Total Tasks:**
- Phase 1: 20 tasks
- Phase 2: 24 tasks
- Final Verification: 18 tasks
- Evaluation Period: 10 tasks
- **Grand Total: 72 tasks**

**Estimated Effort:**
- Phase 1: 8-10 hours (implementation + testing + documentation)
- Phase 2: 6-8 hours (implementation + testing + documentation)
- **Total: 14-18 hours**

**Lines of Code:**
- Phase 1: ~350 lines (200 implementation + 150 tests)
- Phase 2: ~280 lines (130 implementation + 150 tests)
- **Total: ~630 lines**

---

**Checklist Status:** COMPLETE - Ready for implementation to begin
**Confidence Level:** HIGH (0.95) - All verification criteria defined and testable
