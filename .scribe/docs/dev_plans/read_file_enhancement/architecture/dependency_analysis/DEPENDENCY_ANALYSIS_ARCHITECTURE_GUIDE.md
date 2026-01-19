# 🏗️ Dependency Analysis Architecture Guide — read_file_enhancement

**Feature:** Optional dependency analysis for read_file tool
**Sub-Plan:** dependency_analysis
**Version:** 1.0
**Status:** Design Phase
**Author:** ArchitectAgent
**Last Updated:** 2026-01-07

> This architecture guide defines the design for adding opt-in dependency analysis capabilities to the read_file tool's scan_only mode. The design prioritizes governance enforcement over visualization, static analysis over runtime inference, and honest incompleteness over false confidence.

---

## 1. Problem Statement
<!-- ID: problem_statement -->

**Context:**
The read_file tool currently provides file structure extraction (functions, classes, headings) but lacks dependency analysis capabilities. Governance agents need to understand import relationships to make informed enforcement decisions about:
- Impact radius of file changes (what depends on this?)
- Boundary violations (sentinel code importing from tools/)
- Dead code detection (files with zero incoming imports)
- Checklist trigger automation (high-impact edits requiring review)

**Current Limitations:**
- No visibility into import statements
- Cannot detect boundary violations programmatically
- Cannot assess change impact radius
- Manual code review required for dependency-related governance

**Goals:**
1. Enable static import extraction from Python files via AST analysis
2. Provide best-effort path resolution for imports (repo-local prioritized)
3. Support governance-first enforcement decisions with dependency data
4. Maintain performance (zero overhead when disabled, <20% when enabled)
5. Admit incompleteness honestly (mark unresolved imports explicitly)

**Non-Goals:**
- Function-level call graphs (dynamic dispatch unprovable statically)
- Runtime behavior analysis (requires execution)
- Complete dependency coverage claims (static analysis has limits)
- Visualization-first design (governance-first, not graphs)

---

## 2. System Overview
<!-- ID: system_overview -->

**High-Level Design:**

The dependency analysis feature extends the existing read_file tool with an opt-in `include_dependencies` parameter. When enabled, the tool performs AST-based import extraction and best-effort path resolution, returning structured dependency data in the response payload.

**Key Components:**

1. **Parameter Extension:** Add `include_dependencies: bool = False` to read_file() function signature
2. **Import Extraction Engine:** `_extract_imports()` function walks AST for Import/ImportFrom nodes
3. **Path Resolution Engine:** `_resolve_import_path()` function resolves imports to file paths when possible
4. **Response Schema Extension:** Add `dependencies` key with imports, resolution status, truncation info
5. **Readable Formatter Enhancement:** Display dependencies in user-friendly format with path resolution status

**Integration with Existing Infrastructure:**

- Leverages existing `_extract_python_structure()` AST parsing infrastructure (tools/read_file.py lines 377-434)
- Reuses parsed AST tree (no double parsing overhead)
- Extends existing response schema pattern (utils/response.py)
- Follows existing truncation pattern for large datasets (functions/classes already paginated)

**Design Principles:**

1. **Opt-in over Always-on:** Default behavior unchanged, power users explicitly enable
2. **Static over Dynamic:** AST-provable only, no runtime inference
3. **Honest over Complete:** Mark unresolved imports, don't guess
4. **Governance over Visualization:** Enable enforcement decisions, not just pretty graphs
5. **Best-effort over Guaranteed:** Resolve what we can prove, admit gaps
6. **Phase-gated over All-at-once:** Stop at Phase 2, evaluate usage, iterate based on reality

---

## 3. Component Design
<!-- ID: component_design -->

### 3.1 Import Extraction Engine (_extract_imports)

**Purpose:** Extract import statements from Python AST tree with line numbers and metadata

**Function Signature:**
```python
def _extract_imports(tree: ast.AST, max_imports: int = 100) -> List[Dict]:
    """Extract import statements from Python AST tree.

    Args:
        tree: Parsed Python AST tree
        max_imports: Maximum imports to extract (truncate if exceeded)

    Returns:
        List of import dicts with module, line, type, level, names, alias
    """
```

**Import Dict Schema:**
```python
{
    "module": str,          # Module name (e.g., "scribe_mcp.tools.append_entry")
    "line": int,            # Line number of import statement
    "type": str,            # "import" or "from_import"
    "names": List[str],     # Imported names (None for ast.Import)
    "alias": Optional[str], # Alias if present (import x as y)
    "level": int,           # Relative import depth (0=absolute, 1=., 2=.., etc.)
    "resolved_path": Optional[str]  # Added in Phase 2
}
```

**AST Node Handling:**

- **ast.Import nodes:** `import module_name`, `import module_name as alias`
  - Extract module name from alias.name
  - Set type="import", level=0
  - Store alias if present (alias.asname)

- **ast.ImportFrom nodes:** `from module import name`, `from ..module import name`
  - Extract module from node.module (may be None for `from . import x`)
  - Extract level from node.level (0=absolute, 1+=relative dots)
  - Extract names from node.names list
  - Set type="from_import"

**Truncation Strategy:**
- Truncate at max_imports limit (default 100)
- Set truncated flag in response if limit exceeded
- Follow existing pattern from function/class extraction

**Error Handling:**
- Reuse existing AST parsing error handling from _extract_python_structure()
- Return empty list if AST parsing fails
- Log errors but don't fail the scan

### 3.2 Path Resolution Engine (_resolve_import_path)

**Purpose:** Best-effort resolution of import statements to file paths within the repository

**Function Signature:**
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
```

**Resolution Strategy:**

1. **Relative Imports (level > 0):**
   - Navigate up from current file by `level` directories
   - Append module_name path components if present
   - Check for .py file or __init__.py in directory
   - Return first match found, None if neither exists

2. **Absolute Repo-Local Imports (level == 0):**
   - Check if first module component matches repo name (e.g., "scribe_mcp")
   - Build relative path from remaining components
   - Check for .py file or __init__.py in directory
   - Return first match found, None if neither exists

3. **External/Stdlib Imports:**
   - Return None (mark as unresolved)
   - Add to unresolved list for tracking

**Honest Incompleteness:**
- Resolution is BEST-EFFORT, not guaranteed
- Static analysis cannot predict sys.path modifications
- __package__ attribute unknown at static analysis time
- Mark uncertain resolutions explicitly

**Performance Considerations:**
- Cache resolution results within single scan (dict keyed by module+level)
- Limit filesystem checks to repo-local imports only
- Skip resolution for known stdlib modules (pathlib, json, datetime, etc.)

### 3.3 Response Schema Extension

**Dependencies Object Structure:**
```python
{
    "dependencies": {
        "imports": [
            {
                "module": "scribe_mcp.tools.append_entry",
                "line": 15,
                "type": "from_import",
                "names": ["append_entry"],
                "resolved_path": "tools/append_entry.py",
                "alias": None,
                "level": 0
            },
            {
                "module": "pathlib",
                "line": 10,
                "type": "import",
                "names": None,
                "resolved_path": None,  # External stdlib
                "alias": "Path",
                "level": 0
            }
        ],
        "total_imports": 18,
        "unresolved": ["pathlib", "json", "datetime"],
        "truncated": false
    }
}
```

**Integration with Existing Response:**
- Add `dependencies` key at top level (alongside structure, path, encoding)
- Only present when `include_dependencies=True`
- Empty dict when flag is False (minimal overhead)

### 3.4 Readable Mode Formatter Enhancement

**Display Format:**

```
📦 Dependencies (18 imports, 3 unresolved):

  Repo-Local Imports:
    • scribe_mcp.tools.append_entry (line 15) → tools/append_entry.py
    • ..utils.response (line 23) → utils/response.py
    • .shared.logging_utils (line 31) → shared/logging_utils.py

  External/Stdlib Imports:
    • pathlib (line 10) [stdlib]
    • json (line 11) [stdlib]
    • datetime (line 12) [stdlib]

  ⚠️ Truncated: Showing first 100 of 150 imports
```

**Formatting Rules:**
- Group by resolution status (repo-local vs external)
- Show line numbers for all imports
- Display resolved paths for repo-local imports
- Mark external imports with [stdlib] or [external]
- Show truncation warning if applicable
- Display summary counts at header

---

## 4. Data Flow
<!-- ID: data_flow -->

**Request Flow:**

1. Agent calls `read_file(path="tools/append_entry.py", include_dependencies=True)`
2. read_file() validates path and checks include_dependencies flag
3. _scan_file() performs AST parsing (existing code path)
4. If include_dependencies=True:
   - Call _extract_imports(tree) to get import list
   - For each import, call _resolve_import_path() to resolve
   - Build unresolved list from None resolutions
   - Add dependencies object to response
5. Response formatter checks for dependencies object
6. If present and format="readable":
   - Render dependencies section with grouping and paths
7. Return formatted response to agent

**Data Transformations:**

```
Python source code
    ↓ (ast.parse)
AST tree
    ↓ (ast.walk + filter Import/ImportFrom)
Raw import nodes
    ↓ (_extract_imports)
Import dicts with metadata
    ↓ (_resolve_import_path for each)
Import dicts with resolved_path
    ↓ (group by resolution status)
Dependencies object
    ↓ (format_readable_file_content)
Human-readable dependency section
```

---

## 5. API Design
<!-- ID: api_design -->

### 5.1 Parameter Addition

**read_file() Signature Change:**
```python
def read_file(
    path: str,
    mode: str = "scan_only",
    # ... existing parameters ...
    include_dependencies: bool = False,  # NEW PARAMETER
    format: str = "readable"
) -> Dict:
```

**Parameter Specification:**
- Name: `include_dependencies`
- Type: bool
- Default: False (zero overhead for existing callers)
- When True: Extract imports and resolve paths (adds <20% overhead)
- Applies to: scan_only mode only (other modes ignore this flag)

**Backward Compatibility:**
- Default False ensures existing workflows unchanged
- Optional parameter, no breaking changes
- Can be added without versioning concerns

### 5.2 Response Schema Changes

**When include_dependencies=False (default):**
```python
{
    "path": "tools/append_entry.py",
    "structure": {...},  # Existing structure
    "encoding": "utf-8",
    # No dependencies key
}
```

**When include_dependencies=True:**
```python
{
    "path": "tools/append_entry.py",
    "structure": {...},  # Existing structure
    "encoding": "utf-8",
    "dependencies": {
        "imports": [...],
        "total_imports": 18,
        "unresolved": [...],
        "truncated": false
    }
}
```

---

## 6. Integration Points
<!-- ID: integration_points -->

**File Modifications:**

1. **tools/read_file.py** (Primary Implementation File)
   - Line ~648: Add `include_dependencies` parameter to read_file()
   - New function: `_extract_imports()` (~60-80 lines)
   - New function: `_resolve_import_path()` (~80-100 lines)
   - Line ~425: Integrate extraction in _scan_file() (~20 lines)
   - Total addition: ~200 lines

2. **utils/response.py** (Formatter Enhancement)
   - Modify `format_readable_file_content()` to handle dependencies
   - Add dependency formatting logic (~80-100 lines)
   - Add helper functions for import display (~30 lines)
   - Total addition: ~130 lines

**Total LOC Impact:** ~330 lines added across 2 files

**Testing Integration:**
- New test file: `tests/test_read_file_dependencies.py`
- Test cases: 9 total (extraction, resolution, performance)
- Use existing scribe_mcp files as real-world test subjects

---

## 7. Critical Boundaries
<!-- ID: critical_boundaries -->

**What We DO:**
- ✅ Extract import statements from AST (ast.Import, ast.ImportFrom)
- ✅ Resolve repo-local imports to file paths (best-effort)
- ✅ Mark external/stdlib imports as unresolved
- ✅ Provide line numbers for all imports
- ✅ Support relative import resolution (., .., ...)
- ✅ Admit incompleteness explicitly

**What We DON'T DO:**
- ❌ Function-level call graphs (dynamic dispatch unprovable)
- ❌ Runtime behavior analysis (requires execution)
- ❌ Conditional import detection (if __name__)
- ❌ Dynamic import tracking (importlib)
- ❌ Higher-order function analysis
- ❌ Reflection/monkey patching detection
- ❌ Claims of "complete" dependency coverage

**Why These Boundaries Matter:**
- Static analysis has fundamental limits
- False confidence more harmful than admitted gaps
- Governance decisions need honest data, not lies
- Feature scope creep prevention

---

## 8. Performance Considerations
<!-- ID: performance_considerations -->

**Performance Budget:**
- Default behavior (include_dependencies=False): ZERO overhead
- Enabled behavior (include_dependencies=True): <20% overhead target

**Optimization Strategies:**

1. **Reuse Existing AST Tree:**
   - Don't parse twice (structure extraction already parses)
   - Share AST tree between structure and import extraction

2. **Path Resolution Caching:**
   - Cache resolution results within single scan
   - Key: (module_name, level) tuple
   - Avoid redundant filesystem checks

3. **Import List Truncation:**
   - Cap at 100 imports (configurable via max_imports parameter)
   - Same pattern as function/class truncation
   - Prevents memory bloat on generated files

4. **Stdlib Skip List:**
   - Maintain list of known stdlib modules
   - Skip filesystem checks for these
   - Reduces I/O overhead

5. **Opt-in Design:**
   - Fast path unchanged (include_dependencies=False)
   - Overhead only when explicitly requested
   - Most scans remain fast

**Performance Testing:**
- Benchmark with/without flag on large files (>1000 lines)
- Verify <20% overhead when enabled
- Verify zero overhead when disabled
- Test with files having 100+ imports

---

## 9. Governance Use Cases
<!-- ID: governance_use_cases -->

**Primary Use Cases (Enabled by This Feature):**

1. **Impact Radius Warnings:**
   - Phase 3: Reverse lookup index shows "imported by X files"
   - Trigger governance warnings for high-impact files
   - Example: "CAUTION: This file is imported by 15 other files"

2. **Boundary Violation Detection:**
   - Phase 4: Define forbidden import patterns in config
   - Check imports against rules during scan
   - Example: Flag when sentinel code imports from tools/

3. **Dead Code Identification:**
   - Phase 5: Track files with zero incoming imports
   - Flag deletion candidates
   - Example: "This file has no incoming imports - candidate for removal"

4. **Checklist Trigger Automation:**
   - Agent detects high-impact file edit via dependencies
   - Automatically triggers review checklist items
   - Example: "File has 10+ dependents → require peer review"

**Enforcement Workflow Example:**

```python
# Agent workflow
result = read_file(path="tools/append_entry.py", include_dependencies=True)

# Check boundary violations (Phase 4 future)
for imp in result["dependencies"]["imports"]:
    if imp["resolved_path"] and imp["resolved_path"].startswith("sentinel/"):
        raise GovernanceViolation("Tools cannot import from sentinel/")

# Check impact radius (Phase 3 future)
if len(result["dependencies"]["reverse_imports"]) > 10:
    log_warning("High-impact file - proceed with caution")
```

---

## 10. Documentation Requirements
<!-- ID: documentation_requirements -->

**Files to Update:**

1. **docs/Scribe_Usage.md:**
   - Add include_dependencies parameter documentation
   - Show example usage with readable/structured modes
   - Document response schema with dependencies object
   - Explain resolution limitations and unresolved tracking

2. **.codex/skills/scribe-mcp-usage/SKILL.md:**
   - Add parameter to read_file() signature
   - Note default False behavior
   - Reference Scribe_Usage.md for detailed examples

3. **CLAUDE.md (Optional):**
   - Update refactoring guidance with dependency awareness
   - Example: "Use read_file(include_dependencies=True) before major refactors"

4. **AGENTS.md (Optional):**
   - Document dependency-aware patterns for Research/Architect/Review agents
   - Example: "Architect Agent should check dependencies before design"

---

## 11. Open Questions & Follow-Ups
<!-- ID: open_questions -->

**Resolved Questions:**
- ✅ Should this be opt-in or always-on? → Opt-in (include_dependencies=False default)
- ✅ How to handle unresolved imports? → Mark explicitly in unresolved list
- ✅ What about call graphs? → Out of scope (critical boundary)
- ✅ When to implement Phases 3-5? → Stop at Phase 2, use for one week first

**Open Questions:**
- [ ] Should we add caching across multiple read_file calls? (Future optimization)
- [ ] Should stdlib skip list be configurable? (Future enhancement)
- [ ] Should max_imports be configurable per-project? (Future configuration)

**Future Considerations:**
- Phase 3 reverse lookup requires in-memory indexing strategy
- Phase 4 boundary rules require YAML schema design
- Phase 5 dead code detection requires repo-wide analysis

---

## 12. References & Appendix
<!-- ID: references -->

**Research Documents:**
- `.scribe/docs/dev_plans/read_file_enhancement/research/RESEARCH_DEPENDENCY_ANALYSIS_20260107_0945.md` (435 lines, complete technical specifications)

**Related Code:**
- `tools/read_file.py`: Current implementation (1063 lines)
- `utils/response.py`: Response formatting infrastructure
- `tools/read_file.py` lines 377-434: Existing _extract_python_structure() for AST patterns

**Python Documentation:**
- https://docs.python.org/3/library/ast.html (AST module reference)
- https://docs.python.org/3/reference/import.html (Import system specification)
- https://peps.python.org/pep-0328/ (Relative imports PEP)

**Design Principles:**
1. Opt-in over always-on
2. Static over dynamic
3. Honest over complete
4. Governance over visualization
5. Best-effort over guaranteed
6. Phase-gated over all-at-once

---

**Architecture Status:** COMPLETE - Ready for Phase Plan and Checklist creation
**Confidence Level:** HIGH (0.95) - All design decisions grounded in research findings
