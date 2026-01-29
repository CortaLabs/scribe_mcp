# Search Tool Design Research

**Date:** 2026-01-28
**Agent:** ResearchAgent-ReadFileAudit-R2
**Goal:** Design MCP tool to replace grep/sed/rg shell commands
**Confidence:** 0.87 (High)

---

## Executive Summary

### The Problem

Agents currently use Bash tools (grep/rg/sed) for multi-file search, which requires user approval, breaks autonomy, and creates inconsistent workflows.

### The Solution

Build new `search` MCP tool providing:
- Multi-file recursive search across codebase
- All grep/rg capabilities (glob filters, type filters, output modes)
- No user approval required (native MCP tool)
- Consistent audit trail via Scribe logging

### Recommended Approach

**Option B: New dedicated `search` MCP tool** - Pure Python solution using stdlib, reusing proven read_file patterns, complete feature parity with grep/rg.

---

## 1. Requirements

### Complete Feature Matrix

| Feature | Current Tool | Priority |
|---------|--------------|----------|
| Multi-file search | `grep -r`, `rg` | **CRITICAL** |
| Recursive traversal | `grep -r`, `rg` | **CRITICAL** |
| Glob filtering | `rg --glob` | **HIGH** |
| Type filtering | `rg -t py` | **HIGH** |
| Files-with-matches | `grep -l` | **HIGH** |
| Count mode | `grep -c` | **MEDIUM** |
| Context lines | `grep -C` | **HIGH** |
| Case insensitive | `grep -i` | **HIGH** |
| Regex support | `grep -E`, `rg` | **CRITICAL** |
| Line numbers | `grep -n` | **HIGH** |
| Multiline search | `rg -U` | **LOW** |
| Result limiting | pipe to head | **MEDIUM** |

### Common Use Cases

```python
# UC1: Find all files containing pattern
# Old: grep -r "AuthService" --include="*.py"
search(pattern="AuthService", glob="*.py", output_mode="files_with_matches")

# UC2: Search with context
# Old: rg "class AuthService" -C 5
search(pattern="class AuthService", context_lines=5)

# UC3: Count occurrences
# Old: grep -c "TODO" *.py
search(pattern="TODO", glob="*.py", output_mode="count")

# UC4: Find implementation
# Old: rg "def process_user" -t py
search(pattern="def process_user", type="py")

# UC5: Find imports
# Old: rg "import.*openai" -l
search(pattern="import.*openai", output_mode="files_with_matches")
```

---

## 2. Architecture Options

### Option A: Enhance read_file ❌ NOT RECOMMENDED

**Approach:** Add multi-file search to existing tool

**Cons:**
- Violates single responsibility
- Parameter explosion (30+ params)
- Confusing UX ("read file" vs "search codebase")
- Backward compatibility risk
- Performance concerns (single tool for all cases)

### Option B: New `search` Tool ⭐ RECOMMENDED

**Approach:** Dedicated search tool alongside read_file

**Pros:**
- ✅ Clean separation of concerns
- ✅ Clear intuitive UX
- ✅ Feature parity with grep/rg
- ✅ Reuses proven patterns
- ✅ Flexible output modes
- ✅ No breaking changes
- ✅ Full audit trail

**Cons:**
- New tool registration (minimal effort)
- Agent training (documentation)

### Option C: Two Tools (search + find_files) ❌ NOT RECOMMENDED

**Approach:** Separate content search from file discovery

**Cons:**
- Over-engineering
- Worse UX (agents choose between tools)
- Duplicate logic
- More maintenance

---

## 3. Technical Feasibility

### Existing Infrastructure

**From read_file.py:**
- ✅ `_search_file()` (lines 1604-1669) - Proven search logic
- ✅ Regex via stdlib `re`
- ✅ Fuzzy matching via `difflib`
- ✅ Context line buffering
- ✅ Sandbox enforcement
- ✅ Response formatting

**From server.py:**
- ✅ `@app.tool()` decorator pattern
- ✅ ExecutionContext for security
- ✅ Audit logging patterns

### New Components Needed

**1. File Discovery Engine:**
```python
def discover_files(
    root: Path,
    glob_pattern: Optional[str],
    file_type: Optional[str],
    max_files: int,
) -> List[Path]:
    # Use pathlib.Path.rglob()
    # Filter by glob (fnmatch)
    # Filter by type (extension mapping)
    # Respect skip patterns
    # Enforce max_files limit
```

**2. Type Filter Mapping:**
```python
FILE_TYPE_PATTERNS = {
    "py": ["*.py"],
    "js": ["*.js", "*.jsx"],
    "ts": ["*.ts", "*.tsx"],
    "rust": ["*.rs"],
    "go": ["*.go"],
    # ... more types
}
```

**3. Result Aggregation:**
```python
def aggregate_results(
    matches: List[Dict],
    output_mode: str,
) -> Dict:
    # files_with_matches: unique paths
    # count: matches per file
    # content: full details with context
    # files_only: paths (no search)
```

### Performance Strategy

**Mitigation:**
1. File limits (default max_files=1000)
2. Match limits (default max_matches=200/file)
3. Smart filtering (skip binary, skip large files)
4. Early termination (stop after first match in files_with_matches mode)
5. Async I/O (Phase 3 enhancement)

**Skip Patterns:**
```python
SKIP_PATTERNS = [
    "*.pyc", "__pycache__/*", ".git/*",
    "node_modules/*", "*.so", "*.dylib",
    ".venv/*", "venv/*"
]
```

**Performance Baseline:**
- Small repo (<1000 files): <1 second
- Medium repo (1000-10000 files): 1-5 seconds
- Large repo (>10000 files): Use narrower scope

---

## 4. Proposed Tool Signature

```python
@app.tool()
async def search(
    # Required
    agent: str,
    pattern: str,

    # Scope
    path: Optional[str] = None,  # Default: repo root
    glob: Optional[str] = None,  # "*.py", "**/*.ts"
    type: Optional[str] = None,  # py, js, ts, md, etc.

    # Output
    output_mode: str = "content",  # content|files_with_matches|count|files_only
    format: str = "readable",

    # Context
    context_lines: int = 0,
    before_context: Optional[int] = None,
    after_context: Optional[int] = None,

    # Search Behavior
    case_insensitive: bool = False,
    regex: bool = True,
    multiline: bool = False,
    invert_match: bool = False,

    # Limits
    max_matches: Optional[int] = 200,
    max_total_matches: Optional[int] = 5000,
    max_files: Optional[int] = 1000,

    # Display
    line_numbers: bool = True,
    show_filenames: bool = True,

    # Performance
    skip_binary: bool = True,
    max_file_size: Optional[int] = None,  # 10MB default

) -> Union[Dict[str, Any], str]:
    """Multi-file search with grep/rg feature parity."""
```

### Response Structures

**Content Mode:**
```json
{
  "ok": true,
  "output_mode": "content",
  "files_searched": 142,
  "files_with_matches": 5,
  "total_matches": 23,
  "matches": [
    {
      "file": "src/auth/service.py",
      "matches": [
        {
          "line_number": 45,
          "line": "class AuthService:",
          "context_before": [...],
          "context_after": [...]
        }
      ]
    }
  ]
}
```

**Files-with-matches Mode:**
```json
{
  "ok": true,
  "output_mode": "files_with_matches",
  "files_searched": 142,
  "files_with_matches": 5,
  "files": [
    "src/auth/service.py",
    "src/auth/handlers.py",
    "tests/test_auth.py"
  ]
}
```

**Count Mode:**
```json
{
  "ok": true,
  "output_mode": "count",
  "total_matches": 87,
  "counts": [
    {"file": "src/auth/service.py", "count": 12},
    {"file": "src/db/models.py", "count": 8}
  ]
}
```

---

## 5. Implementation Plan

### Phase 1: Core Search (MVP) - 4-6 hours

**Features:**
- Multi-file recursive search
- Regex and literal patterns
- Glob and type filtering
- Output modes: content, files_with_matches
- Context lines
- Case insensitive
- Result limiting

**Deliverables:**
- `tools/search.py` implementation
- Add to `tools/__init__.py`
- Unit tests in `tests/test_search.py`
- Documentation in `docs/Scribe_Usage.md`

### Phase 2: Advanced Features - 2-3 hours

- Count mode
- Before/after context (asymmetric)
- Multiline search
- Inverted match
- Files-only mode

### Phase 3: Performance - 3-4 hours

- Async file I/O (aiofiles)
- Concurrent processing
- Smart binary detection
- Result streaming
- Benchmarks

### Phase 4: Agent Integration - 2 hours

- Update AGENTS.md, CLAUDE.md
- Update scribe-mcp-usage skill
- Migration guide
- Examples

---

## 6. Integration Patterns

### Tool Registration

```python
# tools/search.py
from scribe_mcp.server import app

@app.tool()
async def search(agent: str, ...) -> Dict[str, Any]:
    ...

# tools/__init__.py
from . import search  # noqa: F401
```

### Security Enforcement

```python
from scribe_mcp import server as server_module

exec_context = server_module.get_execution_context()
repo_root = Path(exec_context.repo_root)

# Enforce search within repo
search_root = repo_root if path is None else (repo_root / path).resolve()
if not str(search_root).startswith(str(repo_root)):
    return {"ok": False, "error": "Search outside repository"}
```

### Response Formatting

```python
from scribe_mcp.utils.formatters.dispatcher import format_response

response = {"ok": True, "matches": [...]}
if format == "readable":
    return format_response(response, "search", format_type="readable")
return response
```

---

## 7. Reusable Code Patterns

### From read_file.py

**Search Logic (lines 1604-1669):**
- Line-by-line file reading
- Pattern matching (regex/literal/fuzzy)
- Context buffer management
- Match limiting

**Binary Detection:**
```python
def is_binary(path: Path) -> bool:
    with open(path, 'rb') as f:
        chunk = f.read(512)
        return b'\0' in chunk
```

**Encoding Detection:**
```python
import chardet

def detect_encoding(path: Path) -> str:
    with open(path, 'rb') as f:
        raw = f.read(min(10000, path.stat().st_size))
        result = chardet.detect(raw)
        return result['encoding'] or 'utf-8'
```

### File Discovery Pattern

```python
from pathlib import Path
import fnmatch

def discover_files(
    root: Path,
    glob_pattern: Optional[str],
    file_type: Optional[str],
    max_files: int = 1000,
) -> List[Path]:
    files = []

    # Determine patterns
    if file_type and file_type in FILE_TYPE_PATTERNS:
        patterns = FILE_TYPE_PATTERNS[file_type]
    elif glob_pattern:
        patterns = [glob_pattern]
    else:
        patterns = ["*"]

    # Recursive discovery
    for pattern in patterns:
        for file_path in root.rglob(pattern):
            if not file_path.is_file():
                continue

            # Skip ignored patterns
            if any(fnmatch.fnmatch(str(file_path), skip)
                   for skip in SKIP_PATTERNS):
                continue

            files.append(file_path)
            if len(files) >= max_files:
                break

        if len(files) >= max_files:
            break

    return files
```

---

## 8. Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Performance on large repos | Medium | High | File/match limits, async I/O |
| Complex regex patterns | Low | Medium | Proven re module, tests |
| Edge cases in file discovery | Medium | Low | Extensive testing |

### UX Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent adoption | Low | High | Clear docs, examples |
| Parameter confusion | Medium | Low | Sensible defaults, validation |

### Security Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Path traversal | Low | High | Strict validation (reuse read_file) |
| Resource exhaustion | Medium | Medium | Hard limits on files/matches |

---

## 9. Testing Strategy

### Unit Tests

**File:** `tests/test_search.py`

**Coverage:**
- Basic pattern search
- Glob filtering
- Type filtering
- Output modes
- Context lines
- Case insensitive
- Regex vs literal
- Max limits
- Binary skipping
- Security boundaries

### Performance Benchmarks

**Targets:**
- 1000 files, simple pattern: <2 seconds
- 1000 files, complex regex: <5 seconds
- Different output modes comparison

---

## 10. Documentation Updates

### Files to Update

1. **docs/Scribe_Usage.md** - Tool reference with examples
2. **AGENTS.md** - Remove grep/rg, add search tool
3. **CLAUDE.md** - Add to quick reference
4. **scribe-mcp-usage skill** - Add search examples

### Migration Guide

| Old (Bash) | New (MCP) |
|------------|------------|
| `rg "pattern"` | `search(pattern="pattern")` |
| `grep -r "pattern" --include="*.py"` | `search(pattern="pattern", glob="*.py")` |
| `rg "pattern" -t py` | `search(pattern="pattern", type="py")` |
| `rg "pattern" -l` | `search(pattern="pattern", output_mode="files_with_matches")` |
| `grep -c "pattern" *.py` | `search(pattern="pattern", glob="*.py", output_mode="count")` |
| `rg "pattern" -C 5` | `search(pattern="pattern", context_lines=5)` |

---

## 11. Success Metrics

### Implementation
- ✅ All unit tests pass
- ✅ Performance meets benchmarks
- ✅ Documentation complete
- ✅ No security vulnerabilities

### Adoption
- ✅ Agents use search >90% of time (vs grep/rg)
- ✅ No feature complaints
- ✅ No performance complaints

### Quality
- ✅ Zero security incidents
- ✅ <5 bug reports in first month
- ✅ High agent satisfaction

---

## 12. Handoff Notes for Architect

### Critical Decisions

1. **Architecture:** New dedicated `search` tool (Option B)
2. **Implementation:** Pure Python, stdlib only
3. **Scope:** Multi-file search (sed out of scope)
4. **Security:** Reuse read_file sandbox patterns
5. **Performance:** File/match limits, async in Phase 3

### What Needs Architecture Work

1. Detailed file discovery algorithm
2. Result streaming for large result sets
3. Async file processing model
4. Complete type filter mappings
5. Integration touchpoints

### What's Ready to Implement

1. Tool signature defined
2. Response structures specified
3. Core search logic reusable
4. Registration pattern clear
5. Testing strategy scoped

### Blockers

**NONE** - All technical questions answered.

---

## 13. Confidence Assessment

| Aspect | Confidence | Reasoning |
|--------|-----------|------------|
| Requirements | 0.95 | All grep/rg use cases captured |
| Architecture | 0.90 | Proven pattern, clean separation |
| Feasibility | 0.90 | Reusing proven code, stdlib |
| Performance | 0.75 | Unknowns on large repos, mitigations ready |
| Security | 0.95 | Reusing read_file patterns |
| Implementation | 0.85 | 4-6 hours realistic for MVP |
| Adoption | 0.80 | Depends on documentation |
| **Overall** | **0.87** | **High confidence** |

### Confidence Reasoning

**High (0.9+):**
- Straightforward proven architecture
- Reusing existing search logic
- Well-established tool patterns
- Proven security patterns

**Medium (0.75-0.85):**
- Performance untested on huge repos (mitigations designed)
- Implementation time estimate
- Agent adoption needs good docs

**Increases Confidence:**
- Prototype with benchmarks
- User testing with agents
- Code review

---

## 14. Open Questions

1. **Support .gitignore patterns?**
   - **Recommendation:** Add as optional param (default: False)

2. **Support tool piping?**
   - **Recommendation:** Not needed, agents can chain

3. **Saved search patterns?**
   - **Recommendation:** Out of scope for MVP, v2 feature

4. **Paginate large results?**
   - **Recommendation:** Yes, use query_entries pagination pattern

5. **Exclude patterns?**
   - **Recommendation:** Add in Phase 2

---

## Conclusion

This research provides a complete blueprint for building a Scribe MCP search tool that eliminates grep/sed/rg shell commands.

**Key Takeaways:**
1. ✅ Technically feasible - Pure Python, stdlib, proven patterns
2. ✅ Clear architecture - Dedicated tool, clean separation
3. ✅ Feature complete - All grep/rg capabilities
4. ✅ Performance viable - Mitigation strategies ready
5. ✅ Security sound - Reuses proven patterns
6. ✅ Ready to implement - 4-6 hours for MVP

**Recommendation:** Proceed to Architecture phase with Option B.

**Confidence:** 0.87 (High) - No blockers identified.

---

**Research Complete** | ResearchAgent-ReadFileAudit-R2 | 2026-01-28
