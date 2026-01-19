# 📋 Dependency Analysis Phase Plan — read_file_enhancement

**Feature:** Optional dependency analysis for read_file tool
**Sub-Plan:** dependency_analysis
**Version:** 1.0
**Status:** Planning Phase
**Author:** ArchitectAgent
**Last Updated:** 2026-01-07

> This phase plan breaks down the dependency analysis implementation into concrete, testable phases. User directive: **STOP AFTER PHASE 2** and use for one week before considering Phase 3+.

---

## Phase Overview

| Phase | Description | Lines of Code | Complexity | Dependencies |
|-------|-------------|---------------|------------|--------------|
| **Phase 1** | Basic Import Extraction | ~200 lines | Medium | None |
| **Phase 2** | Path Resolution | ~130 lines | Medium | Phase 1 |
| **STOP HERE** | **Evaluate usage for one week** | **—** | **—** | **—** |
| Phase 3 | Reverse Lookup Index | ~150 lines | High | Phase 2 |
| Phase 4 | Boundary Enforcement | ~200 lines | High | Phase 3 |
| Phase 5 | Dead Code Detection | ~100 lines | Medium | Phase 4 |

**Critical Decision Point:** Phases 3-5 are **RESERVED FOR FUTURE** based on real-world usage evaluation after Phase 2 deployment.

---

## Task Breakdown for Scribe Coder Sessions
<!-- ID: task_breakdown -->

**Purpose:** Break implementation into small-scope, independently testable work units for Scribe Coder agents. Each task is 30-60 minutes of focused work with clear acceptance criteria.

**Execution Strategy:** Tasks must be completed in sequential order within each phase. Some tasks within a phase can be parallelized where noted.

### Phase 1 Tasks (6 tasks, ~4 hours total)

| Task | Description | Duration | Risk | Files | Can Parallelize |
|------|-------------|----------|------|-------|-----------------|
| **1A** | Parameter Plumbing | 30 min | LOW | read_file.py | No (prerequisite) |
| **1B** | AST Import Extractor | 45 min | MEDIUM | read_file.py | Can parallel with 1E |
| **1C** | Response Schema Integration | 30 min | LOW | read_file.py | No (needs 1B) |
| **1D** | Readable Formatter - Dependencies | 60 min | MEDIUM | response.py | Can parallel with 1C |
| **1E** | Test Suite - Import Extraction | 45 min | LOW | test_read_file_dependencies.py | Can parallel with 1B |
| **1F** | Integration Test - End to End | 30 min | LOW | test_read_file_dependencies.py | No (needs all above) |

### Phase 2 Tasks (5 tasks, ~3.5 hours total)

| Task | Description | Duration | Risk | Files | Can Parallelize |
|------|-------------|----------|------|-------|-----------------|
| **2A** | Basic Path Resolver (absolute) | 60 min | MEDIUM | read_file.py | Can parallel with 2B |
| **2B** | Relative Import Resolver | 60 min | HIGH | read_file.py | Can parallel with 2A |
| **2C** | Resolution Integration | 30 min | LOW | read_file.py | No (needs 2A+2B) |
| **2D** | Readable Formatter - Resolution | 45 min | MEDIUM | response.py | Can parallel with 2C |
| **2E** | Test Suite - Path Resolution | 45 min | LOW | test_read_file_dependencies.py | No (needs 2C) |

### Phase 3 Tasks (6 tasks, ~4.5 hours total)

| Task | Description | Duration | Risk | Files | Can Parallelize |
|------|-------------|----------|------|-------|-----------------|
| **3A** | Repository Scanner | 45 min | MEDIUM | read_file.py | Yes (independent) |
| **3B** | Reverse Index Builder | 60 min | HIGH | read_file.py | No (needs 3A) |
| **3C** | Impact Radius Calculator | 30 min | LOW | read_file.py | No (needs 3B) |
| **3D** | Response Schema Integration | 30 min | LOW | read_file.py | Can parallel with 3E |
| **3E** | Readable Formatter - Impact Display | 45 min | MEDIUM | response.py | Can parallel with 3D |
| **3F** | Test Suite - Reverse Index | 45 min | MEDIUM | test_read_file_dependencies.py | No (needs 3D+3E) |

---

### Task 1A: Parameter Plumbing
<!-- ID: task_1a -->

**Scope:** Add `include_dependencies` parameter with no logic changes yet

**Duration:** 30 minutes
**Risk:** LOW
**Files:** `tools/read_file.py`

**Changes:**
1. Add `include_dependencies: bool = False` to function signature (line ~632)
2. Pass parameter through to scan_only handler
3. Add early return if False (ensures zero overhead)

**Acceptance Criteria:**
- [ ] Parameter exists in function signature
- [ ] Defaults to False
- [ ] All existing tests pass (no behavior change)
- [ ] No performance impact when False

**Implementation Notes:**
- This is pure plumbing - no complex logic
- Establishes foundation for subsequent tasks
- Must be completed before any other Phase 1 tasks

---

### Task 1B: AST Import Extractor
<!-- ID: task_1b -->

**Scope:** Implement `_extract_imports()` function - no integration yet

**Duration:** 45 minutes
**Risk:** MEDIUM
**Files:** `tools/read_file.py`

**Changes:**
1. Create `_extract_imports(tree: ast.AST) -> List[Dict]` function
2. Walk AST to find `ast.Import` and `ast.ImportFrom` nodes
3. Extract: module name, line number, import type, names, alias
4. Return list of import dicts (no path resolution yet)

**Acceptance Criteria:**
- [ ] Function exists and returns correct schema
- [ ] Handles `import x` statements
- [ ] Handles `import x as y` statements
- [ ] Handles `from x import y` statements
- [ ] Handles relative imports (`from . import x`)
- [ ] Extracts line numbers correctly
- [ ] Edge cases: empty file, no imports, malformed syntax

**Can Parallelize:** Yes, with Task 1E (testing)

**Implementation Notes:**
- Single-purpose function, no side effects
- Focus on correctness over optimization
- NO path resolution in this task (Phase 2)

---

### Task 1C: Response Schema Integration
<!-- ID: task_1c -->

**Scope:** Wire `_extract_imports()` to response payload

**Duration:** 30 minutes
**Risk:** LOW
**Files:** `tools/read_file.py`

**Changes:**
1. Call `_extract_imports()` in scan_only mode when `include_dependencies=True`
2. Add `dependencies` key to response dict
3. Populate with: imports list, total_imports count, truncated flag
4. Ensure not called when `include_dependencies=False`

**Acceptance Criteria:**
- [ ] Response includes `dependencies` when flag is True
- [ ] Response excludes `dependencies` when flag is False
- [ ] Schema matches architecture specification
- [ ] Truncation handled (limit first 50 imports shown)
- [ ] unresolved list initialized (empty for Phase 1)

**Dependencies:** Requires Task 1B complete

**Implementation Notes:**
- Simple function call + dict assignment
- Ensure conditional execution based on flag

---

### Task 1D: Readable Formatter - Dependencies Section
<!-- ID: task_1d -->

**Scope:** Display dependencies in readable output

**Duration:** 60 minutes
**Risk:** MEDIUM
**Files:** `utils/response.py`

**Changes:**
1. Add "📦 Dependencies:" section after structure display
2. Display imports with line numbers and module names
3. Show truncation indicator if >20 imports displayed
4. Keep formatting clean (ONE emoji, no spam)
5. Only display when `include_dependencies=True`

**Acceptance Criteria:**
- [ ] Dependencies section appears after structure
- [ ] Line numbers displayed correctly
- [ ] Module names displayed clearly
- [ ] Truncation message if needed ("... and 30 more imports")
- [ ] No display when `include_dependencies=False`
- [ ] Formatting matches existing style (clean, readable)

**Can Parallelize:** Yes, with Task 1C (different file)

**Implementation Notes:**
- Follow existing formatter patterns
- ONE 📦 emoji for section header
- Keep output scannable, not cluttered

---

### Task 1E: Test Suite - Import Extraction
<!-- ID: task_1e -->

**Scope:** Comprehensive test coverage for `_extract_imports()`

**Duration:** 45 minutes
**Risk:** LOW
**Files:** `tests/test_read_file_dependencies.py` (NEW file)

**Test Cases:**
1. Python file with various import types
2. `import x` statements
3. `import x as y` statements
4. `from x import y` statements
5. `from x import y, z` multiple imports
6. Relative imports (`from . import x`)
7. Empty file (no imports)
8. File with no imports (just code)
9. Malformed imports (syntax errors)
10. Mixed import types
11. Truncation behavior (>50 imports)

**Acceptance Criteria:**
- [ ] 100% code coverage of `_extract_imports()`
- [ ] All import types tested
- [ ] Edge cases handled gracefully
- [ ] Tests pass consistently
- [ ] Test file follows pytest conventions

**Can Parallelize:** Yes, with Task 1B (can write tests while function is being implemented)

---

### Task 1F: Integration Test - End to End
<!-- ID: task_1f -->

**Scope:** Verify full pipeline from read_file() call to output

**Duration:** 30 minutes
**Risk:** LOW
**Files:** `tests/test_read_file_dependencies.py`

**Test Cases:**
1. Full read_file() call with `include_dependencies=True`
2. Response schema validation (structured mode)
3. Readable output validation (readable mode)
4. Test with real scribe_mcp files (tools/read_file.py, tools/append_entry.py)
5. Performance test (<20% overhead vs baseline)

**Acceptance Criteria:**
- [ ] Can scan tools/read_file.py successfully
- [ ] Dependencies appear in structured mode response
- [ ] Dependencies display correctly in readable mode
- [ ] Performance acceptable (measured vs baseline)
- [ ] No crashes or errors

**Dependencies:** Requires ALL Phase 1 tasks (1A-1E) complete

**Implementation Notes:**
- Integration testing only, no new logic
- Use real files from the codebase
- Measure actual performance impact

---

### Task 2A: Basic Path Resolver (Absolute Imports)
<!-- ID: task_2a -->

**Scope:** Implement path resolution for absolute imports only

**Duration:** 60 minutes
**Risk:** MEDIUM
**Files:** `tools/read_file.py`

**Changes:**
1. Create `_resolve_import_path(module: str, source_file: Path, level: int, repo_root: Path) -> Optional[str]`
2. Handle absolute imports: `scribe_mcp.tools.append_entry` → `tools/append_entry.py`
3. Return None for stdlib (pathlib, os, sys, etc.)
4. Return None for external packages
5. NO relative imports yet (level=0 only)

**Acceptance Criteria:**
- [ ] Function exists with correct signature
- [ ] Resolves internal absolute imports correctly
- [ ] Returns None for stdlib imports
- [ ] Returns None for external package imports
- [ ] Unit tested with various module paths
- [ ] Handles edge cases (missing files, invalid paths)

**Can Parallelize:** Yes, with Task 2B (different logic paths)

**Implementation Notes:**
- Handle level=0 (absolute) only in this task
- Use Path operations for cross-platform compatibility
- Be conservative: if uncertain, return None (honest incompleteness)

---

### Task 2B: Relative Import Resolver
<!-- ID: task_2b -->

**Scope:** Add relative import support to `_resolve_import_path()`

**Duration:** 60 minutes
**Risk:** HIGH (relative path logic is tricky)
**Files:** `tools/read_file.py`

**Changes:**
1. Handle level=1 (`.`) imports: same directory
2. Handle level=2 (`..`) imports: parent directory
3. Handle level=3+ (`...`) imports: multiple parents
4. Calculate correct path from source_file location
5. Validate resolved path exists

**Acceptance Criteria:**
- [ ] Resolves `from . import x` correctly
- [ ] Resolves `from ..utils import y` correctly
- [ ] Resolves deep nesting (`from ....x import y`)
- [ ] Handles edge cases (at repo root, circular references)
- [ ] Unit tested for all levels (1, 2, 3+)
- [ ] Returns None when path doesn't exist

**Can Parallelize:** Yes, with Task 2A (different level values)

**Implementation Notes:**
- Relative path calculation is the tricky part
- Test thoroughly with real scribe_mcp file structure
- Document edge cases in code comments

---

### Task 2C: Resolution Integration
<!-- ID: task_2c -->

**Scope:** Call `_resolve_import_path()` during import extraction

**Duration:** 30 minutes
**Risk:** LOW
**Files:** `tools/read_file.py`

**Changes:**
1. Call `_resolve_import_path()` for each import in `_extract_imports()`
2. Add `resolved_path` key to import dict
3. Mark unresolved imports explicitly (resolved_path=None)
4. Update `unresolved` list in dependencies response

**Acceptance Criteria:**
- [ ] Imports have `resolved_path` when resolvable
- [ ] Unresolved imports have `resolved_path: None`
- [ ] `unresolved` list populated correctly
- [ ] No crashes on resolution failures
- [ ] Integration tested with Phase 1 tests

**Dependencies:** Requires Task 2A AND Task 2B complete

**Implementation Notes:**
- Simple function call during extraction loop
- Handle None returns gracefully
- Update schema to match architecture spec

---

### Task 2D: Readable Formatter - Resolution Display
<!-- ID: task_2d -->

**Scope:** Show resolved paths in readable dependencies output

**Duration:** 45 minutes
**Risk:** MEDIUM
**Files:** `utils/response.py`

**Changes:**
1. Display `→ tools/append_entry.py` for resolved imports
2. Display `[external stdlib]` for stdlib imports (unresolved)
3. Display `[external package]` for external packages
4. Show relative import indicators (`from ..utils`)
5. Keep formatting clean and scannable

**Acceptance Criteria:**
- [ ] Resolved paths display with arrow indicator
- [ ] External/stdlib clearly marked
- [ ] Relative imports show level indicators
- [ ] Formatting matches design spec
- [ ] No display clutter

**Can Parallelize:** Yes, with Task 2C (different file)

**Implementation Notes:**
- Follow existing formatter patterns
- Use visual indicators (→, [external]) consistently
- Test with real scribe_mcp files for readability

---

### Task 2E: Test Suite - Path Resolution
<!-- ID: task_2e -->

**Scope:** Comprehensive resolution testing

**Duration:** 45 minutes
**Risk:** LOW
**Files:** `tests/test_read_file_dependencies.py`

**Test Cases:**
1. Absolute import resolution (internal modules)
2. Relative import resolution - level 1 (.)
3. Relative import resolution - level 2 (..)
4. Relative import resolution - level 3+ (...)
5. Stdlib detection (pathlib, os, sys)
6. External package detection (numpy, pytest)
7. Unresolved import handling
8. Edge cases (missing files, circular refs)
9. Integration test with real scribe_mcp files
10. Performance test (resolution overhead <5%)

**Acceptance Criteria:**
- [ ] 100% coverage of `_resolve_import_path()`
- [ ] All resolution types tested
- [ ] Edge cases handled gracefully
- [ ] Tests pass consistently
- [ ] Performance impact measured

**Dependencies:** Requires Task 2C complete (integration needed)

**Implementation Notes:**
- Test with real scribe_mcp directory structure
- Verify resolution accuracy manually for sample files
- Document any known limitations

---

### Task 3A: Repository Scanner
<!-- ID: task_3a -->

**Scope:** Build function to discover all Python files in repository

**Duration:** 45 minutes
**Risk:** MEDIUM
**Files:** `tools/read_file.py`

**Changes:**
1. Create `_scan_repository_imports(repo_root: Path, max_files: int = 500) -> Dict[str, List[str]]`
2. Find all `.py` files using recursive glob (exclude common dirs: `.git`, `__pycache__`, `.venv`, `node_modules`)
3. For each file: extract imports using existing `_extract_imports()` function
4. Return dict: `{file_path: [list of imported modules]}`
5. Add progress tracking for large repos (log every 50 files)
6. Implement early termination if max_files exceeded

**Acceptance Criteria:**
- [ ] Function exists with correct signature
- [ ] Finds all .py files in scribe_mcp (excluding ignored dirs)
- [ ] Extracts imports from each file successfully
- [ ] Handles files with syntax errors gracefully (skip with warning)
- [ ] Respects max_files limit (prevents runaway scans)
- [ ] Returns clean dict structure
- [ ] Performance: scans scribe_mcp repo in <3 seconds

**Can Parallelize:** Yes (independent of other tasks)

**Implementation Notes:**
- Use `.rglob('*.py')` for recursive file discovery
- Skip files that fail to parse (log warning, continue)
- Cache excluded directory names for performance
- Consider adding `.scribeignore` support in future

---

### Task 3B: Reverse Index Builder
<!-- ID: task_3b -->

**Scope:** Transform forward imports into reverse "imported by" index

**Duration:** 60 minutes
**Risk:** HIGH
**Files:** `tools/read_file.py`

**Changes:**
1. Create `_build_reverse_index(forward_index: Dict[str, List[str]], repo_root: Path) -> Dict[str, List[str]]`
2. Invert the forward index: for each file's imports, record the importing file
3. Normalize paths (absolute → repo-relative for consistency)
4. Handle import resolution: `scribe_mcp.tools.append_entry` → `tools/append_entry.py`
5. Return dict: `{imported_file_path: [list of files that import it]}`
6. Add deduplication (same file shouldn't appear twice as importer)

**Acceptance Criteria:**
- [ ] Function exists with correct signature
- [ ] Correctly inverts forward index
- [ ] Handles both absolute and relative imports
- [ ] Normalizes paths to repo-relative format
- [ ] Deduplicates importer lists
- [ ] Returns clean reverse index structure
- [ ] Handles missing files (imports that can't be resolved)

**Dependencies:** Requires Task 3A complete (needs forward index)

**Implementation Notes:**
- This is the core complexity of Phase 3
- Use Phase 2's resolution logic to map imports → file paths
- Be defensive: if import can't be resolved, skip it (don't crash)
- Consider memory usage for large repos (dict size)

---

### Task 3C: Impact Radius Calculator
<!-- ID: task_3c -->

**Scope:** Calculate impact metrics from reverse index

**Duration:** 30 minutes
**Risk:** LOW
**Files:** `tools/read_file.py`

**Changes:**
1. Create `_calculate_impact_radius(file_path: str, reverse_index: Dict[str, List[str]]) -> Dict[str, Any]`
2. Count number of files that import the target file
3. Categorize impact level:
   - `low`: 0-4 importers
   - `medium`: 5-15 importers
   - `high`: 16+ importers
4. Return dict with: `count`, `level`, `importers` (list of file paths)
5. Add truncation: if >20 importers, only return first 20 (indicate truncation)

**Acceptance Criteria:**
- [ ] Function exists with correct signature
- [ ] Correctly counts importers from reverse index
- [ ] Categorizes impact level accurately
- [ ] Returns importer list (truncated if needed)
- [ ] Handles files not in index (0 importers)
- [ ] Performance: O(1) lookup in reverse index

**Dependencies:** Requires Task 3B complete (needs reverse index)

**Implementation Notes:**
- Simple counting and categorization logic
- Thresholds (5, 15) are configurable in future
- Truncation prevents output explosion for highly-used files

---

### Task 3D: Response Schema Integration
<!-- ID: task_3d -->

**Scope:** Add impact radius to read_file response when include_dependencies=True

**Duration:** 30 minutes
**Risk:** LOW
**Files:** `tools/read_file.py`

**Changes:**
1. Update `read_file()` scan_only mode to optionally build reverse index
2. Add new parameter: `include_impact: bool = False` (requires `include_dependencies=True`)
3. When both flags True: call `_scan_repository_imports()`, `_build_reverse_index()`, `_calculate_impact_radius()`
4. Add `impact_radius` key to response dict with: `{"count": int, "level": str, "importers": List[str], "truncated": bool}`
5. Add performance warning if repo scan takes >5 seconds

**Acceptance Criteria:**
- [ ] `include_impact` parameter added to function signature
- [ ] Defaults to False (opt-in only)
- [ ] Requires `include_dependencies=True` (validate and error if not)
- [ ] Builds reverse index on-demand (not cached between calls - future optimization)
- [ ] Adds impact_radius to response schema
- [ ] Handles errors gracefully (return None if scan fails)

**Can Parallelize:** Yes, can work on response.py (3E) in parallel

**Implementation Notes:**
- Phase 3 does NOT cache reverse index (future optimization)
- Each call with `include_impact=True` rescans repo (expensive but simple)
- User should use sparingly (governance checks only)

---

### Task 3E: Readable Formatter - Impact Display
<!-- ID: task_3e -->

**Scope:** Display impact radius in readable mode output

**Duration:** 45 minutes
**Risk:** MEDIUM
**Files:** `utils/response.py`

**Changes:**
1. Update `_format_read_file_readable()` to handle `impact_radius` in response
2. Add new section after dependencies:
   ```
   ⚠️  Impact Radius:
      This file is imported by 23 files [HIGH IMPACT]

      Recent importers:
        • tools/append_entry.py
        • tools/set_project.py
        ... and 21 more files
   ```
3. Color-code impact level (future: use terminal colors if available):
   - LOW: No warning
   - MEDIUM: `⚠️` warning
   - HIGH: `🚨 HIGH IMPACT` banner
4. Group importers by directory for readability (if >10 importers)
5. Add truncation message

**Acceptance Criteria:**
- [ ] Impact radius section appears when data present
- [ ] Impact level displayed clearly (low/medium/high)
- [ ] Importer list formatted cleanly
- [ ] Truncation indicated when >20 importers
- [ ] Output remains scannable (not overwhelming)
- [ ] No impact section if `include_impact=False`

**Can Parallelize:** Yes, can work on read_file.py (3D) in parallel

**Implementation Notes:**
- Keep formatting clean - one emoji for warning, not spam
- Importer paths should be repo-relative (easier to read)
- Consider grouping by top-level directory: `tools/ (5), storage/ (3), shared/ (2)`

---

### Task 3F: Test Suite - Reverse Index
<!-- ID: task_3f -->

**Scope:** Comprehensive reverse index and impact testing

**Duration:** 45 minutes
**Risk:** MEDIUM
**Files:** `tests/test_read_file_dependencies.py`

**Test Cases:**
1. Repository scanning (file discovery, import extraction)
2. Reverse index building (forward → reverse transformation)
3. Impact radius calculation (count, categorization)
4. Integration test: read_file with `include_impact=True`
5. Edge cases:
   - File with 0 importers
   - File with 100+ importers (truncation)
   - File not in repository
   - Circular imports (A imports B imports A)
6. Performance test: repo scan completes in <5 seconds for scribe_mcp

**Acceptance Criteria:**
- [ ] 100% coverage of new Phase 3 functions
- [ ] Repository scanner finds all .py files correctly
- [ ] Reverse index accurately inverts forward index
- [ ] Impact levels categorized correctly
- [ ] Integration test validates full pipeline
- [ ] Edge cases handled gracefully
- [ ] Performance test passes

**Dependencies:** Requires Tasks 3D and 3E complete (full integration needed)

**Implementation Notes:**
- Create test fixture: small fake repo with known import structure
- Test with real scribe_mcp repo for integration validation
- Verify impact counts manually for 2-3 files
- Document performance baseline for future regression testing

---

### Execution Order Summary

**Sequential Execution (Safest):**
```
Phase 1: 1A → 1B → 1C → 1D → 1E → 1F
Phase 2: 2A → 2B → 2C → 2D → 2E
Phase 3: 3A → 3B → 3C → 3D → 3E → 3F
```

**Parallel Execution (Faster):**
```
Phase 1:
  - 1A (prerequisite, must be first)
  - 1B + 1E (parallel: implementation + tests)
  - 1C + 1D (parallel: backend + frontend)
  - 1F (integration, must be last)

Phase 2:
  - 2A + 2B (parallel: absolute + relative resolvers)
  - 2C + 2D (parallel: backend + frontend)
  - 2E (testing, must be last)

Phase 3:
  - 3A (repo scanner, can be independent)
  - 3B (reverse index, needs 3A)
  - 3C (impact calculator, needs 3B)
  - 3D + 3E (parallel: backend + frontend)
  - 3F (testing, must be last)
```

**Total Duration:**
- **Phases 1+2:** ~7.5 hours (COMPLETED)
- **Phase 3:** ~4.5 hours
- **Total Phases 1+2+3:** ~12 hours
- **Parallel (optimal):** ~8.5 hours
- **Per task:** 30-60 minutes (manageable Coder sessions)

---

## Phase 1: Basic Import Extraction
<!-- ID: phase1 -->

**Objective:** Extract import statements from Python AST and return them in response payload with line numbers and metadata. Zero overhead when disabled (include_dependencies=False).

**Duration Estimate:** 3-4 hours of focused implementation

### 1.1 Parameter Addition (tools/read_file.py)

**Location:** Line ~648 (read_file function signature)

**Changes:**
```python
def read_file(
    path: str,
    mode: str = "scan_only",
    chunk_index: Optional[int] = None,
    # ... existing parameters ...
    include_dependencies: bool = False,  # ADD THIS PARAMETER
    format: str = "readable"
) -> Dict:
    """Read files with optional dependency analysis.

    Args:
        include_dependencies: If True, extract import statements and resolve paths (default: False)
    """
```

**Testing:**
- Verify parameter accepts bool values
- Verify default False behavior unchanged
- Verify True enables extraction

### 1.2 Import Extraction Function (tools/read_file.py)

**New Function:** `_extract_imports(tree: ast.AST, max_imports: int = 100) -> List[Dict]`

**Location:** After `_extract_python_structure()` function (~line 435)

**Implementation:**
```python
def _extract_imports(tree: ast.AST, max_imports: int = 100) -> List[Dict]:
    """Extract import statements from Python AST tree.

    Args:
        tree: Parsed Python AST tree
        max_imports: Maximum imports to extract (truncate if exceeded)

    Returns:
        List of import dicts with module, line, type, level, names, alias
    """
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # Handle: import module_name
            # Handle: import module_name as alias
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "line": node.lineno,
                    "type": "import",
                    "names": None,  # Not applicable for ast.Import
                    "alias": alias.asname,  # May be None
                    "level": 0,  # Always absolute
                    "resolved_path": None  # Phase 2
                })
        elif isinstance(node, ast.ImportFrom):
            # Handle: from module import name1, name2
            # Handle: from ..module import name
            # Handle: from . import name
            imports.append({
                "module": node.module or "",  # None for "from . import"
                "line": node.lineno,
                "type": "from_import",
                "names": [alias.name for alias in node.names],
                "alias": None,  # Not applicable for from imports
                "level": node.level,  # 0=absolute, 1=., 2=.., etc.
                "resolved_path": None  # Phase 2
            })

        if len(imports) >= max_imports:
            break

    return imports
```

**Lines of Code:** ~60-80 lines

**Testing:**
- Test ast.Import detection (`import json`)
- Test ast.Import with alias (`import json as j`)
- Test ast.ImportFrom detection (`from pathlib import Path`)
- Test relative imports (`from . import x`, `from ..foo import bar`)
- Test line number accuracy
- Test truncation at max_imports limit

### 1.3 Integration with _scan_file() (tools/read_file.py)

**Location:** Line ~425 (inside _scan_file function)

**Changes:**
```python
def _scan_file(...) -> Dict:
    # ... existing code ...

    # Extract Python structure if applicable
    if file_path.suffix == ".py":
        try:
            tree = ast.parse(content, filename=str(file_path))
            structure["functions"] = _extract_python_structure(tree, max_items=100)
            structure["classes"] = _extract_python_classes(tree, max_items=50)

            # NEW: Extract imports if requested
            if include_dependencies:  # Pass this parameter down from read_file()
                structure["dependencies"] = {
                    "imports": _extract_imports(tree, max_imports=100),
                    "total_imports": len(structure["dependencies"]["imports"]),
                    "unresolved": [],  # Phase 2
                    "truncated": len(structure["dependencies"]["imports"]) >= 100
                }
        except SyntaxError:
            # Existing error handling
            pass
```

**Lines of Code:** ~20 lines

**Testing:**
- Verify dependencies key only present when include_dependencies=True
- Verify default (False) has no dependencies key
- Verify dependencies object structure matches spec

### 1.4 Response Schema Extension (tools/read_file.py)

**Changes:** Return dependencies object in response when include_dependencies=True

**Response Structure:**
```python
{
    "path": "tools/append_entry.py",
    "structure": {
        "functions": [...],
        "classes": [...],
        "dependencies": {  # NEW - only when include_dependencies=True
            "imports": [
                {
                    "module": "scribe_mcp.tools.shared",
                    "line": 15,
                    "type": "from_import",
                    "names": ["get_storage"],
                    "alias": None,
                    "level": 0,
                    "resolved_path": None  # Phase 2
                }
            ],
            "total_imports": 18,
            "unresolved": [],  # Phase 2
            "truncated": false
        }
    },
    "encoding": "utf-8"
}
```

**Testing:**
- Verify response structure matches spec
- Verify backward compatibility (no dependencies when False)

### 1.5 Readable Mode Formatter Enhancement (utils/response.py)

**Location:** `format_readable_file_content()` function

**New Function:** `_format_dependencies(deps: Dict) -> str`

**Implementation:**
```python
def _format_dependencies(deps: Dict) -> str:
    """Format dependencies for readable mode display."""
    if not deps or not deps.get("imports"):
        return ""

    imports = deps["imports"]
    total = deps.get("total_imports", len(imports))
    truncated = deps.get("truncated", False)

    lines = [f"\n📦 Dependencies ({total} imports):"]

    # Group by type
    import_nodes = [imp for imp in imports if imp["type"] == "import"]
    from_imports = [imp for imp in imports if imp["type"] == "from_import"]

    if import_nodes:
        lines.append("\n  Import Statements:")
        for imp in import_nodes[:20]:  # Show first 20
            alias_text = f" as {imp['alias']}" if imp['alias'] else ""
            lines.append(f"    • {imp['module']}{alias_text} (line {imp['line']})")

    if from_imports:
        lines.append("\n  From Imports:")
        for imp in from_imports[:20]:  # Show first 20
            level_text = "." * imp['level'] if imp['level'] > 0 else ""
            module_text = imp['module'] or ""
            names_text = ", ".join(imp['names'][:5])  # First 5 names
            if len(imp['names']) > 5:
                names_text += f" ... +{len(imp['names']) - 5} more"
            lines.append(f"    • from {level_text}{module_text} import {names_text} (line {imp['line']})")

    if truncated:
        lines.append(f"\n  ⚠️ Truncated: Showing first 100 of {total} imports")

    return "\n".join(lines)
```

**Integration:**
```python
def format_readable_file_content(result: Dict, ...) -> str:
    # ... existing code ...

    # Add dependencies section if present
    if "structure" in result and "dependencies" in result["structure"]:
        output.append(_format_dependencies(result["structure"]["dependencies"]))

    return "\n".join(output)
```

**Lines of Code:** ~80-100 lines

**Testing:**
- Test display with import statements
- Test display with from imports
- Test relative import display (dots shown)
- Test truncation warning display
- Test empty imports list handling

### 1.6 Phase 1 Testing

**Test File:** `tests/test_read_file_dependencies.py` (create new file)

**Test Cases:**
1. `test_include_dependencies_default_false()` - Verify default behavior unchanged
2. `test_extract_import_statements()` - Test `import x` and `import x as y`
3. `test_extract_from_imports()` - Test `from x import y`
4. `test_relative_import_detection()` - Test `.`, `..`, `...` level detection
5. `test_line_number_accuracy()` - Verify line numbers match actual imports
6. `test_import_truncation()` - Verify max_imports limit works
7. `test_readable_mode_formatting()` - Verify dependencies section displays correctly
8. `test_structured_mode_schema()` - Verify response schema matches spec
9. `test_python_file_with_no_imports()` - Edge case: file with no imports

**Test Data:**
- Use existing scribe_mcp files: `tools/append_entry.py`, `tools/read_file.py`, `utils/response.py`
- Create test fixture file with known imports for controlled testing

**Lines of Code:** ~150 lines of test code

### Phase 1 Verification Criteria

**Completion Checklist:**
- [  ] `include_dependencies` parameter added to read_file()
- [ ] `_extract_imports()` function implemented and tested
- [ ] Integration with _scan_file() complete
- [ ] Response schema includes dependencies object
- [ ] Readable formatter displays dependencies section
- [ ] All 9 test cases passing
- [ ] Zero overhead when include_dependencies=False (benchmark)
- [ ] Documentation updated (docstrings in code)

**Performance Target:**
- Default (False): Zero overhead (same as current)
- Enabled (True): <10% overhead (Phase 1 only extracts, no resolution yet)

---

## Phase 2: Path Resolution
<!-- ID: phase2 -->

**Objective:** Resolve import statements to file paths within repository. Mark external/stdlib imports as unresolved. Honest incompleteness over false confidence.

**Duration Estimate:** 3-4 hours of focused implementation

**Dependencies:** Phase 1 must be complete

### 2.1 Path Resolution Function (tools/read_file.py)

**New Function:** `_resolve_import_path(module_name: str, level: int, current_file: Path, repo_root: Path) -> Optional[Path]`

**Location:** After `_extract_imports()` function

**Implementation:**
```python
def _resolve_import_path(
    module_name: str,
    level: int,
    current_file: Path,
    repo_root: Path
) -> Optional[Path]:
    """Best-effort path resolution for imports.

    Args:
        module_name: Module name from import statement
        level: Relative import level (0=absolute, 1+=relative)
        current_file: Path to file being scanned
        repo_root: Repository root directory

    Returns:
        Resolved file path if found, None if unresolved
    """
    # Relative imports (level > 0)
    if level > 0:
        parent_dir = current_file.parent
        for _ in range(level):
            parent_dir = parent_dir.parent
            if parent_dir == parent_dir.parent:  # Reached filesystem root
                return None

        # Handle "from . import x" (no module name)
        if not module_name:
            module_path = parent_dir
        else:
            # Handle "from ..foo.bar import x"
            module_path = parent_dir / module_name.replace(".", "/")

        # Check candidates: module.py or module/__init__.py
        candidates = [
            module_path.with_suffix(".py"),
            module_path / "__init__.py"
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_relative_to(repo_root):
                return candidate.relative_to(repo_root)
        return None

    # Absolute imports (level == 0)
    # Check if repo-local module (e.g., scribe_mcp.tools.append_entry)
    parts = module_name.split(".")
    if parts[0] == repo_root.name or parts[0] == "scribe_mcp":  # Repo name check
        # Build path from module components
        relative_path = Path("/".join(parts[1:] if parts[0] == repo_root.name else parts[1:]))
        candidates = [
            repo_root / relative_path.with_suffix(".py"),
            repo_root / relative_path / "__init__.py"
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.relative_to(repo_root)
        return None

    # External/stdlib - return None (unresolved)
    return None
```

**Lines of Code:** ~80-100 lines

**Testing:**
- Test relative import resolution (., .., ...)
- Test absolute repo-local resolution
- Test external/stdlib returns None
- Test malformed paths return None
- Test __init__.py detection
- Test .py file detection

### 2.2 Resolution Integration (tools/read_file.py)

**Location:** Inside `_scan_file()` where _extract_imports() is called

**Changes:**
```python
if include_dependencies:
    imports = _extract_imports(tree, max_imports=100)

    # NEW: Resolve paths for each import
    unresolved = []
    for imp in imports:
        resolved = _resolve_import_path(
            module_name=imp["module"],
            level=imp["level"],
            current_file=file_path,
            repo_root=repo_root  # Pass from read_file()
        )
        if resolved:
            imp["resolved_path"] = str(resolved)
        else:
            imp["resolved_path"] = None
            # Track unresolved modules
            module_name = imp["module"] if imp["module"] else f".<level {imp['level']}>"
            if module_name not in unresolved:
                unresolved.append(module_name)

    structure["dependencies"] = {
        "imports": imports,
        "total_imports": len(imports),
        "unresolved": unresolved,
        "truncated": len(imports) >= 100
    }
```

**Lines of Code:** ~30 lines

**Testing:**
- Verify resolved_path populated for repo-local imports
- Verify resolved_path is None for external imports
- Verify unresolved list contains external module names

### 2.3 Readable Formatter Enhancement (utils/response.py)

**Location:** Update `_format_dependencies()` function

**Changes:**
```python
def _format_dependencies(deps: Dict) -> str:
    """Format dependencies for readable mode display."""
    if not deps or not deps.get("imports"):
        return ""

    imports = deps["imports"]
    total = deps.get("total_imports", len(imports))
    unresolved = deps.get("unresolved", [])
    truncated = deps.get("truncated", False)

    lines = [f"\n📦 Dependencies ({total} imports, {len(unresolved)} unresolved):"]

    # Group by resolution status
    resolved_imports = [imp for imp in imports if imp.get("resolved_path")]
    unresolved_imports = [imp for imp in imports if not imp.get("resolved_path")]

    if resolved_imports:
        lines.append("\n  Repo-Local Imports:")
        for imp in resolved_imports[:20]:  # Show first 20
            level_text = "." * imp['level'] if imp['level'] > 0 else ""
            module_text = imp['module'] or ""
            path_text = imp['resolved_path']
            lines.append(f"    • {level_text}{module_text} (line {imp['line']}) → {path_text}")

    if unresolved_imports:
        lines.append("\n  External/Stdlib Imports:")
        for imp in unresolved_imports[:20]:  # Show first 20
            module_text = imp['module'] or f".<level {imp['level']}>"
            lines.append(f"    • {module_text} (line {imp['line']}) [external]")

    if truncated:
        lines.append(f"\n  ⚠️ Truncated: Showing first 100 of {total} imports")

    return "\n".join(lines)
```

**Lines of Code:** ~50 lines modification

**Testing:**
- Test resolved imports show path with arrow (→)
- Test unresolved imports show [external] tag
- Test grouping by resolution status
- Test unresolved count in header

### 2.4 Phase 2 Testing

**Additional Test Cases (add to `tests/test_read_file_dependencies.py`):**

10. `test_relative_import_resolution()` - Verify `.`, `..`, `...` resolve correctly
11. `test_absolute_repo_local_resolution()` - Verify `scribe_mcp.tools.x` resolves
12. `test_external_stdlib_unresolved()` - Verify stdlib imports return None
13. `test_unresolved_tracking()` - Verify unresolved list populated correctly
14. `test_init_py_detection()` - Verify package __init__.py resolution
15. `test_py_file_detection()` - Verify .py file resolution
16. `test_resolution_caching()` - Verify performance optimization (future)
17. `test_malformed_import_handling()` - Edge case: broken import paths
18. `test_performance_regression()` - Verify <20% overhead when enabled

**Test Data:**
- Create test fixtures with known import patterns
- Use real scribe_mcp files for integration testing
- Benchmark performance with/without include_dependencies flag

**Lines of Code:** ~150 lines additional test code

### Phase 2 Verification Criteria

**Completion Checklist:**
- [ ] `_resolve_import_path()` function implemented and tested
- [ ] Path resolution integrated into _scan_file()
- [ ] resolved_path field populated in import dicts
- [ ] unresolved list tracks external/stdlib imports
- [ ] Readable formatter shows resolution status with grouping
- [ ] All 18 test cases passing (9 from Phase 1 + 9 new)
- [ ] Performance target met (<20% overhead when enabled)
- [ ] Zero overhead verified when disabled (False)

**Performance Target:**
- Default (False): Zero overhead (unchanged from Phase 1)
- Enabled (True): <20% overhead (extraction + resolution)

---

## STOPPING POINT
<!-- ID: stopping_point -->

**USER DIRECTIVE:** **STOP IMPLEMENTATION AFTER PHASE 2**

**Rationale:**
- Phase 2 provides complete basic dependency analysis
- Real-world usage will reveal if Phases 3-5 are actually needed
- Governance use cases can be partially achieved with Phase 2 alone
- Avoid over-engineering before understanding actual usage patterns

**Evaluation Period:** Use Phase 2 implementation for **one week minimum** before considering Phase 3+

**Questions to Answer During Evaluation:**
1. Do agents actually use include_dependencies in practice?
2. Is path resolution accuracy sufficient for governance decisions?
3. Are there false positives in resolution (incorrect paths)?
4. What governance patterns emerge from actual usage?
5. Is reverse lookup (Phase 3) actually needed, or can agents query as needed?
6. Do boundary violations justify Phase 4 complexity?

**Decision Criteria for Phase 3+:**
- ✅ Proceed if agents use include_dependencies regularly (>10 times/week)
- ✅ Proceed if governance violations are manually caught that Phase 4 would automate
- ✅ Proceed if dead code candidates are identified that Phase 5 would systematize
- ❌ Stop if feature is rarely used or resolution accuracy is too low

---

## Future Phases (RESERVED - NOT IMPLEMENTED YET)
<!-- ID: future_phases -->

### Phase 3: Reverse Lookup Index (Future)

**Objective:** Build in-memory index of "imported by" relationships across repository

**Key Features:**
- Scan all Python files in repo to build import graph
- Store reverse lookup: file → list of files that import it
- Display impact radius in readable mode
- Trigger governance warnings for high-impact files

**Estimated Effort:** ~150 lines, 4-5 hours

**Not Implemented:** Waiting for Phase 2 evaluation results

### Phase 4: Boundary Enforcement (Future)

**Objective:** Define and enforce forbidden import patterns via configuration

**Key Features:**
- YAML configuration file: `.scribe/config/boundary_rules.yaml`
- Define rules: "sentinel code cannot import from tools/"
- Check imports against rules during scan
- Flag violations with severity levels
- Integration with SKILL.md detection system

**Estimated Effort:** ~200 lines, 5-6 hours

**Not Implemented:** Waiting for Phase 2 evaluation results

### Phase 5: Dead Code Detection (Future)

**Objective:** Identify files with zero incoming imports as deletion candidates

**Key Features:**
- Track files with no reverse imports
- Generate "never used" reports
- Create audit trail for safe removal
- Integration with project cleanup workflows

**Estimated Effort:** ~100 lines, 3-4 hours

**Not Implemented:** Waiting for Phase 2 evaluation results

---

## Risk Mitigation
<!-- ID: risk_mitigation -->

**Technical Risks:**

1. **Path Resolution Accuracy**
   - Risk: Repo structure assumptions may not hold
   - Mitigation: Mark unresolved honestly, document assumptions
   - Fallback: Agents can manually verify paths if uncertain

2. **Performance Regression**
   - Risk: Filesystem checks could be slow
   - Mitigation: Cache results, truncate lists, opt-in flag
   - Fallback: Reduce max_imports if performance issues occur

3. **AST Parsing Edge Cases**
   - Risk: Malformed files, syntax errors
   - Mitigation: Reuse existing error handling, return empty list
   - Fallback: Graceful degradation to structure-only scan

**Product Risks:**

1. **Feature Creep**
   - Risk: Pressure to add runtime inference, call graphs
   - Mitigation: Document critical boundaries explicitly, stop at Phase 2
   - Fallback: Reject scope expansion requests until Phase 2 evaluation complete

2. **False Confidence**
   - Risk: Agents assuming "complete" dependency info
   - Mitigation: Explicit unresolved list, documentation emphasizes limitations
   - Fallback: Add warnings in readable mode about static analysis limits

---

## Success Metrics
<!-- ID: success_metrics -->

**Phase 1 Success Criteria:**
- ✅ All 9 test cases passing
- ✅ Zero overhead when disabled (benchmark proof)
- ✅ <10% overhead when enabled (extraction only)
- ✅ Readable mode displays imports correctly
- ✅ Response schema matches specification

**Phase 2 Success Criteria:**
- ✅ All 18 test cases passing (Phase 1 + Phase 2)
- ✅ Zero overhead when disabled (revalidate)
- ✅ <20% overhead when enabled (extraction + resolution)
- ✅ Path resolution >80% accurate for repo-local imports
- ✅ Unresolved tracking complete for external/stdlib
- ✅ Readable mode groups by resolution status

**Long-Term Success Metrics (Post-Phase 2):**
- Usage frequency: include_dependencies used >10 times/week by agents
- Governance impact: >3 boundary violations prevented per month
- Code quality: >5 dead code files identified per quarter
- Developer satisfaction: Positive feedback from agent developers

---

## Documentation Requirements
<!-- ID: documentation_requirements -->

**Phase 1 Documentation:**
- [ ] Update `docs/Scribe_Usage.md` with include_dependencies parameter
- [ ] Add examples of usage with readable/structured modes
- [ ] Document response schema with dependencies object
- [ ] Update `.codex/skills/scribe-mcp-usage/SKILL.md` signature

**Phase 2 Documentation:**
- [ ] Document path resolution strategy and limitations
- [ ] Explain unresolved tracking and marking
- [ ] Add examples of resolution output
- [ ] Update CLAUDE.md with refactoring guidance (optional)
- [ ] Update AGENTS.md with dependency-aware patterns (optional)

**Implementation Reports:**
- [ ] Create `IMPLEMENTATION_REPORT_PHASE1_<timestamp>.md` after Phase 1
- [ ] Create `IMPLEMENTATION_REPORT_PHASE2_<timestamp>.md` after Phase 2
- [ ] Document test results, performance benchmarks, lessons learned

---

## Appendix
<!-- ID: appendix -->

**Total Lines of Code by Phase:**
- Phase 1: ~200 lines (implementation) + ~150 lines (tests) = ~350 lines
- Phase 2: ~130 lines (implementation) + ~150 lines (tests) = ~280 lines
- **Total for Phases 1-2:** ~630 lines

**Files Modified:**
1. `tools/read_file.py` - Primary implementation (+330 lines total)
2. `utils/response.py` - Formatter enhancement (+130 lines total)
3. `tests/test_read_file_dependencies.py` - New test file (+300 lines)
4. `docs/Scribe_Usage.md` - Documentation updates
5. `.codex/skills/scribe-mcp-usage/SKILL.md` - Signature updates

**Implementation Timeline:**
- Phase 1: 3-4 hours focused work
- Phase 2: 3-4 hours focused work
- Testing: 2-3 hours per phase
- Documentation: 1-2 hours total
- **Total Effort:** 12-18 hours for Phases 1-2

---

**Phase Plan Status:** COMPLETE - Ready for Checklist creation and implementation
**Confidence Level:** HIGH (0.95) - Phases 1-2 scope well-defined, stopping point clear
