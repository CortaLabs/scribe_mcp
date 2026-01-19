
# 🔬 Research: Dependency Analysis for read_file Tool — read_file_enhancement
**Author:** ResearchAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-07 09:47:00 UTC

> This document captures comprehensive research for adding optional dependency analysis to the `read_file` tool's scan_only mode. The design prioritizes governance enforcement over visualization, static analysis over runtime inference, and honest incompleteness over false confidence.

---
## Executive Summary
<!-- ID: executive_summary -->

**Primary Objective:** Design and specify a governance-first dependency analysis system for the `read_file` tool that enables enforcement decisions through static import analysis, while maintaining honest boundaries about what static analysis can and cannot prove.

**Key Takeaways:**
- **Opt-in design**: New `include_dependencies` parameter (default: False) keeps default scan_only mode lightweight while enabling power users to request full dependency analysis
- **Static analysis only**: Extraction limited to AST-provable import statements (ast.Import, ast.ImportFrom nodes) - no runtime inference, no dynamic behavior
- **Best-effort path resolution**: Resolve what we can prove (relative imports, repo-local modules), honestly mark rest as unresolved - no false confidence
- **Governance use cases**: Enable four key enforcement patterns: (1) impact radius warnings, (2) boundary violation detection, (3) dead code identification, (4) checklist trigger automation
- **Implementation phases**: Phases 1-2 for initial deployment (basic extraction + path resolution), Phases 3-5 reserved for future enhancement based on real-world usage
- **Performance constraints**: <20% overhead when flag enabled, zero overhead when disabled (default)
- **Critical boundaries**: No function-level call graphs, no runtime behavior analysis, no "complete" dependency claims - admit incompleteness honestly

**Risk Assessment:**
- **LOW RISK**: Opt-in flag design prevents degradation of existing workflows
- **MEDIUM RISK**: Path resolution accuracy depends on repo structure assumptions
- **MITIGATED**: Honest incompleteness marking prevents downstream agents from making false assumptions


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent

**Investigation Window:** 2026-01-07 (single-day comprehensive research)

**Focus Areas:**
- [x] Python AST import node types and extraction patterns
- [x] Python import resolution algorithm and path resolution strategies
- [x] Response schema design for dependency data
- [x] Governance use cases and enforcement patterns
- [x] Implementation phase breakdown with stopping points
- [x] Boundary enforcement rules (what NOT to do)
- [x] Readable mode output formatting for dependencies
- [x] Performance implications and optimization strategies
- [x] Testing strategy and validation approach

**Dependencies & Constraints:**
- **Existing infrastructure**: Leverage existing `_extract_python_structure()` AST parsing in read_file.py (lines 377-434)
- **Static analysis boundary**: Limited to import statements provable via AST - cannot resolve dynamic imports, conditional imports, or runtime modifications
- **Python version support**: Must work with Python 3.8+ AST node structures
- **Performance requirement**: Must not degrade default (include_dependencies=False) performance
- **User directive**: Stop after Phase 2 implementation, use for one week before considering Phase 3+


---
## Findings
<!-- ID: findings -->

### Finding 1: Python AST Import Nodes (ast.Import and ast.ImportFrom)
- **Summary:** Python's AST module provides two node types for import statements: `ast.Import` for simple imports (`import x, import x as y`) and `ast.ImportFrom` for from-imports (`from x import y, from ..x import y`)
- **Evidence:**
  - Official Python 3.14 documentation: https://docs.python.org/3/library/ast.html
  - `ast.Import` contains `names` list of alias nodes
  - `ast.ImportFrom` contains `module` (string or None), `names` (list of alias nodes), `level` (int for relative import depth)
  - Each alias node has `name` (string) and `asname` (string or None for aliases)
- **Confidence:** HIGH (0.95)
- **Implications:** Can extract all top-level import statements with line numbers, module names, and alias information

### Finding 2: Relative Import Level Encoding
- **Summary:** Relative imports use dot notation (`.`, `..`, `...`) encoded as integer `level` in ImportFrom nodes. Level 0 = absolute import, level 1 = `.`, level 2 = `..`, etc. The `module` attribute can be None for pure relative imports like `from . import foo`.
- **Evidence:**
  - PEP 328 specification: https://peps.python.org/pep-0328/
  - Example: `from ..foo.bar import a` → level=2, module='foo.bar'
  - Example: `from . import x` → level=1, module=None
- **Confidence:** HIGH (0.95)
- **Implications:** Can accurately detect and represent relative import depth, critical for path resolution

### Finding 3: Python Import Resolution is Runtime-Dependent
- **Summary:** Python's actual import resolution depends on runtime state (sys.modules cache, sys.path, __package__ attribute) that static analysis cannot reliably predict. Relative imports resolve via __package__, not filesystem traversal.
- **Evidence:**
  - Python 3.14 import system reference: https://docs.python.org/3/reference/import.html
  - Resolution algorithm: sys.modules cache → built-in modules → sys.path search → __path__ for submodules
  - Static analysis limitations: Cannot predict sys.path modifications, dynamic imports (importlib), conditional imports, __main__ context
- **Confidence:** HIGH (0.95)
- **Implications:** Path resolution must be BEST-EFFORT with honest incompleteness marking. Design principle: "Resolve what we can prove, mark rest as unresolved"

### Finding 4: Existing AST Infrastructure Ready for Extension
- **Summary:** Current read_file.py already implements `_extract_python_structure()` (lines 377-434) using ast.parse() and ast.walk() for function/class extraction. Same pattern applicable to import extraction with minimal overhead.
- **Evidence:**
  - File analysis: tools/read_file.py, 17 functions, 1063 lines
  - Existing structure: Parse source → walk AST tree → filter by node type → collect with line numbers
  - Integration point identified: Can add `_extract_imports()` parallel to `_extract_python_structure()`
- **Confidence:** HIGH (0.95)
- **Implications:** Low integration risk, can reuse existing AST parsing infrastructure, no need for separate parsing pass

### Finding 5: Governance Use Cases Drive Design
- **Summary:** Dependency analysis must enable ENFORCEMENT decisions, not just visualization. Four primary governance patterns identified: (1) Impact radius warnings for high-dependency files, (2) Boundary violation detection (e.g., sentinel code importing from tools/), (3) Dead code detection via zero-import files, (4) Checklist trigger automation for high-impact edits.
- **Evidence:**
  - User requirement: "What decision will dependency graphs allow Scribe to ENFORCE?"
  - Existing Scribe governance patterns: SKILL.md detection, path policy enforcement, sentinel mode boundaries
  - Cross-referenced with Commandment #0.5 (Infrastructure Primacy) enforcement needs
- **Confidence:** HIGH (0.95)
- **Implications:** Feature justification clear, design must support reverse lookup (Phase 3), boundary checking (Phase 4)

### Finding 6: Performance Budget Constraints
- **Summary:** Default behavior (include_dependencies=False) must have ZERO overhead. When enabled, target <20% overhead through: (1) leverage existing parsed AST tree (no double parsing), (2) cache path resolution within single scan, (3) truncate import lists like functions/classes, (4) opt-in design keeps fast path unchanged.
- **Evidence:**
  - Current scan_only mode performance: Fast AST parse + structure extraction
  - Overhead sources identified: AST node iteration (~5-10%), filesystem checks for path resolution (variable, can be expensive)
  - Mitigation strategies designed based on existing pagination/truncation patterns
- **Confidence:** MEDIUM (0.85)
- **Implications:** Opt-in flag critical for performance, caching essential, truncation acceptable

### Finding 7: Critical Boundaries (What NOT to Do)
- **Summary:** Six categories of analysis forbidden due to static analysis limitations: (1) Function-level call graphs (dynamic dispatch lies), (2) Higher-order functions/runtime behavior, (3) Conditional imports (if __name__), (4) Dynamic imports (importlib), (5) Reflection/monkey patching, (6) Claims of "complete" dependency coverage.
- **Evidence:**
  - User constraints: "governance-first, not visualization porn", "static analysis only", "admit incompleteness"
  - Python's dynamic nature makes these unprovable without runtime execution
  - False confidence more harmful than admitted gaps
- **Confidence:** HIGHEST (1.0)
- **Implications:** Feature scope strictly limited, prevents future scope creep, maintains honest API contract

### Additional Notes
- Research completed in single day with high confidence across all areas
- All technical questions answered with sufficient depth for Architect phase
- User directive to stop after Phase 2 provides clear implementation boundary
- Cross-project search capabilities (from Phase 4 read_file enhancements) not yet integrated but compatible


---
## Technical Analysis
<!-- ID: technical_analysis -->

### Code Patterns Identified

**AST Import Extraction Pattern:**
```python
def _extract_imports(tree: ast.AST, max_imports: int = 100) -> List[Dict]:
    """Extract import statements from Python AST tree."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "line": node.lineno,
                    "type": "import",
                    "alias": alias.asname,
                    "names": None,  # Not applicable for ast.Import
                    "level": 0,  # Absolute import
                })
        elif isinstance(node, ast.ImportFrom):
            imports.append({
                "module": node.module or "",  # None for "from . import"
                "line": node.lineno,
                "type": "from_import",
                "level": node.level,  # 0=absolute, 1=., 2=.., etc.
                "names": [alias.name for alias in node.names],
                "alias": None,  # Not applicable for from imports
            })
    return imports[:max_imports]  # Truncate if needed
```

**Path Resolution Strategy:**
```python
def _resolve_import_path(module_name: str, level: int, current_file: Path, repo_root: Path) -> Optional[Path]:
    """Best-effort path resolution for imports."""
    # Relative imports: use current file location + level
    if level > 0:
        parent_dir = current_file.parent
        for _ in range(level):
            parent_dir = parent_dir.parent
        if module_name:
            # from ..foo.bar import x
            module_path = parent_dir / module_name.replace(".", "/")
        else:
            # from . import x
            module_path = parent_dir
        # Check for .py file or package __init__.py
        candidates = [module_path.with_suffix(".py"), module_path / "__init__.py"]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None  # Unresolved

    # Absolute imports: check repo structure
    # Try scribe_mcp.tools.append_entry → tools/append_entry.py
    parts = module_name.split(".")
    if parts[0] == "scribe_mcp":  # Repo-local module
        relative_path = Path("/".join(parts[1:]))
        candidates = [
            repo_root / relative_path.with_suffix(".py"),
            repo_root / relative_path / "__init__.py"
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

    # External/stdlib - mark as unresolved
    return None
```

**Integration Point:**
- Add `include_dependencies: bool = False` parameter to `read_file()` function (line 632)
- Call `_extract_imports()` within `_scan_file()` when flag is True
- Add dependency resolution logic after import extraction
- Include in response payload under `dependencies` key

### System Interactions

**Dependency Flow:**
1. **read_file()** receives `include_dependencies=True` flag
2. **_scan_file()** checks flag and calls structure extraction
3. **AST parsing** happens once (existing tree reused)
4. **_extract_imports()** walks tree for Import/ImportFrom nodes
5. **_resolve_import_path()** attempts resolution for each import
6. **Response formatter** displays dependencies in readable mode
7. **Downstream agents** use dependency data for governance decisions

**No External Dependencies:**
- Uses standard library `ast` module (already imported)
- Path resolution uses `pathlib.Path` (already imported)
- No new dependencies required

### Risk Assessment

**Technical Risks:**
- [ ] **Path resolution accuracy**: Repo structure assumptions may not hold for all projects
  - **Mitigation**: Mark unresolved honestly, don't guess, document assumptions
- [ ] **Performance regression**: Filesystem checks could be slow in large repos
  - **Mitigation**: Cache resolution results, truncate import lists, opt-in flag
- [ ] **AST parsing edge cases**: Malformed Python files, syntax errors
  - **Mitigation**: Reuse existing error handling from `_extract_python_structure()`
- [ ] **Relative import ambiguity**: __package__ context unknown to static analysis
  - **Mitigation**: Use file location as best guess, mark uncertain cases

**Product Risks:**
- [ ] **Feature creep**: Pressure to add runtime inference, call graphs, etc.
  - **Mitigation**: Document critical boundaries explicitly, user directive to stop at Phase 2
- [ ] **False confidence**: Agents assuming "complete" dependency information
  - **Mitigation**: Explicit `unresolved` list in response, documentation emphasizes limitations


---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps (Architect Agent)

#### Phase 1: Basic Import Extraction
- [ ] Add `include_dependencies: bool = False` parameter to read_file() function
- [ ] Implement `_extract_imports(tree: ast.AST, max_imports: int) -> List[Dict]` function
  - Walk AST tree for ast.Import and ast.ImportFrom nodes
  - Extract module name, line number, type, level, names, aliases
  - Return list of import dicts with truncation
- [ ] Integrate extraction into `_scan_file()` when flag is True
- [ ] Add `dependencies` key to response payload with structure:
  ```python
  {
    "dependencies": {
      "imports": [...],  # List of import dicts
      "total_imports": 18,
      "truncated": false,
      "unresolved": []  # Populated in Phase 2
    }
  }
  ```
- [ ] Update readable mode formatter in utils/response.py to display dependencies
  - Add "📦 Dependencies:" section after file structure
  - Display imports with line numbers and types
  - Show truncation notice if applicable
- [ ] Write tests for basic extraction:
  - Test ast.Import detection
  - Test ast.ImportFrom detection
  - Test line number accuracy
  - Test alias handling (import x as y)
  - Test relative import level detection

#### Phase 2: Path Resolution
- [ ] Implement `_resolve_import_path(module: str, level: int, file: Path, repo: Path) -> Optional[Path]` function
  - Handle relative imports using file location + level
  - Handle absolute imports checking repo structure
  - Return None for external/stdlib/unresolvable
- [ ] Add `resolved_path` field to import dicts (None if unresolved)
- [ ] Populate `unresolved` list with external/stdlib module names
- [ ] Update readable mode formatter to show resolved paths:
  - Format: `• module_name (line 42) → path/to/file.py`
  - Format: `• module_name (line 42) [external stdlib]`
  - Show unresolved count summary
- [ ] Write tests for path resolution:
  - Test relative import resolution (., .., ...)
  - Test absolute repo-local module resolution
  - Test external/stdlib detection
  - Test unresolved import tracking
  - Performance regression test (<20% overhead)
- [ ] **STOP HERE per user directive** - Use for one week before Phase 3

### Long-Term Opportunities (Future Phases 3-5)

#### Phase 3: Reverse Lookup Index (Future)
- Build in-memory import index across repo during scan
- Enable "imported by X files" reverse lookup
- Display impact radius warnings in readable mode:
  - HIGH: Imported by 10+ files
  - MEDIUM: Imported by 3-9 files
  - LOW: Imported by 1-2 files
- Trigger "touch carefully" governance warnings

#### Phase 4: Boundary Enforcement (Future)
- Define forbidden import patterns in `.scribe/config/boundary_rules.yaml`
- Check imports against rules during scan
- Flag violations with severity levels
- Example rules:
  - sentinel code cannot import from tools/
  - tests/ cannot import from production code (except as needed)
  - utils/ cannot have circular dependencies
- Integrate with SKILL.md detection system

#### Phase 5: Dead Code Detection (Future)
- Track files with zero incoming imports across repo
- Flag as deletion candidates
- Generate "never used" reports
- Create audit trail for safe removal

**Strategic Value:**
- Enables automatic enforcement of Commandment #0.5 (Infrastructure Primacy)
- Supports governance-first development workflow
- Provides objective data for refactoring decisions
- Reduces technical debt through dead code identification


---
## Appendix
<!-- ID: appendix -->

### References
1. **Python AST Documentation**: https://docs.python.org/3/library/ast.html
   - Complete reference for ast.Import and ast.ImportFrom node structures
2. **Python Import System**: https://docs.python.org/3/reference/import.html
   - Official documentation of Python's import resolution algorithm
3. **PEP 328 - Relative Imports**: https://peps.python.org/pep-0328/
   - Specification for relative import syntax and semantics
4. **Existing Implementation**:
   - tools/read_file.py: Current read_file tool implementation (1063 lines)
   - utils/response.py: Response formatting infrastructure (format_readable_file_content)
5. **Related Documentation**:
   - docs/Scribe_Usage.md: Complete tool reference with examples
   - CLAUDE.md: Project-level operational guidance
   - AGENTS.md: Cross-agent governance and commandments

### Response Schema Specification

**Complete dependency response structure:**
```python
{
  "dependencies": {
    "imports": [
      {
        "module": "scribe_mcp.tools.append_entry",
        "line": 15,
        "type": "from_import",  # or "import"
        "names": ["append_entry"],
        "resolved_path": "tools/append_entry.py",  # if resolvable
        "alias": None,
        "level": 0  # for relative imports
      },
      {
        "module": "..utils.response",
        "line": 23,
        "type": "from_import",
        "names": ["format_readable_file_content"],
        "resolved_path": "utils/response.py",
        "alias": None,
        "level": 2  # two dots = level 2
      },
      {
        "module": "pathlib",
        "line": 10,
        "type": "import",
        "names": None,
        "resolved_path": None,  # external stdlib
        "alias": "Path",
        "level": 0
      }
    ],
    "total_imports": 18,
    "unresolved": ["pathlib", "json", "datetime"],  # external/stdlib
    "truncated": false
  }
}
```

### Implementation Notes

**File Modifications Required:**
- `tools/read_file.py`:
  - Add `include_dependencies` parameter to `read_file()` function (~line 648)
  - Add `_extract_imports()` function (~60-80 lines)
  - Add `_resolve_import_path()` function (~80-100 lines)
  - Integrate extraction in `_scan_file()` (~20 lines)
  - Total addition: ~200 lines

- `utils/response.py`:
  - Add dependency formatting to `format_readable_file_content()` (~80-100 lines)
  - Add helper functions for import display (~30 lines)
  - Total addition: ~130 lines

**Testing Requirements:**
- Create `tests/test_read_file_dependencies.py` with 9 test cases
- Use existing scribe_mcp Python files as real-world test subjects
- Validate extraction accuracy, resolution correctness, performance

**Documentation Updates:**
- Update `docs/Scribe_Usage.md` with `include_dependencies` parameter documentation
- Update `.codex/skills/scribe-mcp-usage/SKILL.md` with parameter reference
- Optionally update `CLAUDE.md` with dependency-aware refactoring guidance
- Optionally update `AGENTS.md` with Research/Architect/Review agent usage patterns

### Design Principles Summary

1. **Opt-in over always-on**: Default fast, enable for power users
2. **Static over dynamic**: AST-provable only, no runtime inference
3. **Honest over complete**: Mark unresolved, don't guess
4. **Governance over visualization**: Enable enforcement decisions
5. **Best-effort over guaranteed**: Resolve what we can prove
6. **Phase-gated over all-at-once**: Stop at Phase 2, evaluate, iterate

---

**Research Status:** COMPLETE - Ready for Architect Agent to create ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, and CHECKLIST.md

**Confidence Level:** HIGH (0.95) - All technical questions answered with supporting evidence
