---
id: read_search_error_ux-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 read_search_error_ux"
doc_name: architecture
category: architecture|engineering
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

# 🏗️ Architecture Guide — read_search_error_ux
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-02 06:51:10 UTC

> Architecture guide for read_search_error_ux.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
**Context:** The `read_file` and `search` MCP tools currently return minimal error messages when paths are not found, providing no suggestions or context to help users recover. Research shows 10 error paths across both tools with varying helpfulness, but the primary targets (read_file.py:1816-1827, search.py:664) return only "file not found" / "path does not exist" with no guidance.

**Pain Points:**
- Users get "file not found" when path is actually a directory (conflated error cases)
- No fuzzy suggestions when filename is mistyped (e.g., "auth_handlers.py" vs "auth_handler.py")
- No directory listing to show what files actually exist in parent directory
- No cross-tool suggestions (read_file could suggest search command, search could suggest similar paths)
- difflib already imported in read_file.py but completely unused

**Goals:**
1. Distinguish between "file doesn't exist" vs "path is a directory" errors
2. Provide fuzzy filename suggestions using difflib.get_close_matches (already imported)
3. Show parent directory listing (first 30 files) when file not found
4. Add cross-tool suggestions (read_file → search, search → read_file)
5. Keep performance overhead under 5ms for error paths
6. Maintain backwards compatibility with existing error response structure

**Success Criteria:**
- Users see fuzzy suggestions when typo detected (≥60% similarity)
- Clear distinction between "not found" vs "is directory" errors
- Directory listings capped at 30 entries to prevent output explosion
- No crashes on permission errors, large directories, or symlinks
- Zero performance regression on happy path (no code in success flow)
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
- Atomic document updates
- Jinja2 templates with inheritance

- **Non-Functional Requirements:**
- Backwards-compatible file layout
- Sandboxed template rendering

- **Assumptions:**
- Filesystem read/write access
- Python runtime available

- **Risks & Mitigations:**
- User edits outside manage_docs
- Template misuse causing errors



---
## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Document manager orchestrates template rendering and writes.
- **Component Breakdown:**
  - **Doc Manager:** Validates sections and applies atomic writes.
      - Interfaces: manage_docs tool
      - Notes: Provides verification and logging.
  - **Template Engine:** Renders templates via Jinja2 with sandboxing.
      - Interfaces: Jinja2 environment
      - Notes: Supports project/local overrides.
- **Data Flow:** User -> manage_docs -> template engine -> filesystem/database.
- **External Integrations:** SQLite mirror, git history.


---
## 4. Detailed Design
<!-- ID: detailed_design -->
### 4.1 Shared Helper Module: `utils/path_suggestions.py`

**Purpose:** Centralized error enrichment logic shared by both `read_file` and `search` tools.

**API Design:**

```python
from pathlib import Path
from typing import List, Dict, Any
import difflib

# Constants (matching existing codebase patterns)
MAX_FUZZY_SUGGESTIONS = 5        # Top matches only
MAX_DIRECTORY_ENTRIES = 30       # Prevent output explosion
MAX_SCAN_FILES = 1000           # Timeout protection for large dirs
FUZZY_CUTOFF = 0.6              # 60% similarity threshold

def get_fuzzy_file_suggestions(
    target_name: str,
    parent_dir: Path,
    max_suggestions: int = MAX_FUZZY_SUGGESTIONS,
    cutoff: float = FUZZY_CUTOFF,
    include_directories: bool = False
) -> List[Dict[str, Any]]:
    """Get fuzzy filename matches from parent directory.
    
    Args:
        target_name: The filename/dirname user tried to access
        parent_dir: Parent directory to search in
        max_suggestions: Maximum number of suggestions to return
        cutoff: Minimum similarity score (0.0-1.0)
        include_directories: Whether to include directories in suggestions
    
    Returns:
        [{"name": "auth.py", "score": 0.88, "is_dir": False}, ...]
        Empty list if parent unreadable or no matches found
    
    Performance: <2ms for typical directories (<500 files)
    """
    ...

def get_directory_listing(
    directory: Path,
    max_entries: int = MAX_DIRECTORY_ENTRIES,
    include_hidden: bool = False,
    separate_files_dirs: bool = True
) -> Dict[str, Any]:
    """Get truncated directory listing with files/dirs separated.
    
    Args:
        directory: Directory to list
        max_entries: Maximum entries to return (per category if separated)
        include_hidden: Include files starting with '.'
        separate_files_dirs: Separate into files and directories
    
    Returns:
        {
            "files": ["auth.py", "config.py"],
            "directories": ["api/", "utils/"],
            "truncated": False,
            "total_scanned": 15,
            "permission_error": False
        }
        Empty dict with permission_error=True if directory unreadable
    
    Performance: <1ms using Path.iterdir(), capped at MAX_SCAN_FILES iterations
    """
    ...

def classify_path_error(target: Path) -> str:
    """Classify path error into specific error type.
    
    Args:
        target: Path that caused error
    
    Returns:
        "not_found" | "is_directory" | "permission_denied" | "is_symlink" | "unknown"
    
    Logic:
        if not target.exists(): return "not_found"
        if target.is_dir(): return "is_directory"
        if target.is_symlink() and not target.is_file(): return "is_symlink"
        # Try to read to detect permission issues
        try: target.stat()
        except PermissionError: return "permission_denied"
        return "unknown"
    """
    ...

def build_search_suggestion(pattern: str, path: str, agent: str) -> str:
    """Build cross-tool search command suggestion.
    
    Returns formatted command string:
        'search(agent="YourAgent", pattern="auth_handler", path="src/")'
    """
    ...

def build_read_suggestion(file_path: str, agent: str, mode: str = "scan_only") -> str:
    """Build cross-tool read_file command suggestion.
    
    Returns formatted command string:
        'read_file(agent="YourAgent", path="src/auth/handler.py", mode="scan_only")'
    """
    ...
```

**Error Handling Strategy:**
- ALL filesystem operations wrapped in try/except
- Graceful degradation: return empty results on any error
- NEVER crash on permission errors, symlink loops, or large directories
- Log errors to sentinel for debugging (optional, low priority)

### 4.2 Integration Points

#### A. read_file.py (Line 1816-1827)

**Current Code:**
```python
if not target.exists() or not target.is_file():
    return await finalize_response({
        "ok": False,
        "error": "file not found",
        "absolute_path": str(target),
        "repo_relative_path": rel_path,
    }, requested_mode)
```

**Enhanced Code:**
```python
if not target.exists() or not target.is_file():
    from utils.path_suggestions import (
        classify_path_error,
        get_fuzzy_file_suggestions,
        get_directory_listing,
        build_search_suggestion
    )
    
    # Classify the specific error
    error_type = classify_path_error(target)
    error_message = {
        "not_found": "file not found",
        "is_directory": "path is a directory",
        "permission_denied": "permission denied",
        "is_symlink": "path is a symbolic link (not a regular file)",
        "unknown": "file not accessible"
    }.get(error_type, "file not found")
    
    error_response = {
        "ok": False,
        "error": error_message,
        "error_type": error_type,
        "absolute_path": str(target),
        "repo_relative_path": rel_path,
    }
    
    # Only enrich errors for readable format (performance optimization)
    if requested_mode == "readable":
        # Fuzzy suggestions
        if target.parent.exists():
            suggestions = get_fuzzy_file_suggestions(
                target.name, target.parent, include_directories=(error_type == "is_directory")
            )
            if suggestions:
                error_response["similar_files"] = suggestions
                best_match = suggestions[0]
                error_response["suggestion"] = (
                    f"Did you mean '{best_match['name']}'? "
                    f"({int(best_match['score'] * 100)}% match)"
                )
            
            # Parent directory listing
            listing = get_directory_listing(target.parent)
            if listing and not listing.get("permission_error"):
                error_response["parent_directory"] = str(target.parent)
                error_response["parent_listing"] = listing
        
        # Cross-tool suggestion
        if error_type in ("not_found", "permission_denied"):
            error_response["search_suggestion"] = build_search_suggestion(
                pattern=target.stem,  # filename without extension
                path=str(target.parent) if target.parent.exists() else str(repo_root),
                agent=agent
            )
    
    await log_read(
        "read_file_error",
        {"reason": error_type, "path": str(target)},
        include_md=True,
    )
    
    return await finalize_response(error_response, requested_mode)
```

**Key Changes:**
- Split "not exists" vs "is directory" into distinct error types
- Add fuzzy file suggestions using difflib (already imported at line 15)
- Add parent directory listing
- Add cross-tool search suggestion
- Lazy evaluation: only compute suggestions for `format="readable"`

#### B. search.py (Line 663-664)

**Current Code:**
```python
if not search_root.exists():
    return {"ok": False, "error": "search path does not exist", "path": str(search_root)}
```

**Enhanced Code:**
```python
if not search_root.exists():
    from utils.path_suggestions import (
        get_fuzzy_file_suggestions,
        get_directory_listing,
        build_read_suggestion
    )
    
    error_response = {
        "ok": False,
        "error": "search path does not exist",
        "path": str(search_root),
        "error_type": "not_found"
    }
    
    # Only enrich for readable format
    if format == "readable":
        # Fuzzy directory suggestions from parent
        if search_root.parent.exists():
            suggestions = get_fuzzy_file_suggestions(
                search_root.name,
                search_root.parent,
                include_directories=True  # Prioritize directories for search paths
            )
            if suggestions:
                dir_suggestions = [s for s in suggestions if s.get("is_dir")]
                if dir_suggestions:
                    error_response["similar_paths"] = dir_suggestions
                    best = dir_suggestions[0]
                    error_response["suggestion"] = (
                        f"Did you mean '{best['name']}'? "
                        f"({int(best['score'] * 100)}% match)"
                    )
            
            # Parent directory listing
            listing = get_directory_listing(search_root.parent)
            if listing and not listing.get("permission_error"):
                error_response["parent_directory"] = str(search_root.parent)
                error_response["parent_listing"] = listing
    
    return error_response
```

**Key Changes:**
- Add fuzzy path suggestions (prioritize directories)
- Add parent directory listing
- Lazy evaluation based on `format` parameter

### 4.3 Error Response Schema

**Enhanced Error Response Structure:**

```python
{
    # Core error fields (always present)
    "ok": False,
    "error": "file not found" | "path is a directory" | "search path does not exist",
    "error_type": "not_found" | "is_directory" | "permission_denied" | "is_symlink",
    "absolute_path": str,
    "repo_relative_path": str | None,
    
    # Fuzzy suggestions (present if matches found and format="readable")
    "similar_files": [
        {"name": "auth.py", "score": 0.88, "is_dir": False},
        {"name": "auth_utils.py", "score": 0.72, "is_dir": False}
    ],
    
    # Directory context (present if parent readable and format="readable")
    "parent_directory": "/path/to/parent",
    "parent_listing": {
        "files": ["a.py", "b.py"],
        "directories": ["auth/", "api/"],
        "truncated": False,
        "total_scanned": 15,
        "permission_error": False
    },
    
    # Cross-tool suggestions (present if applicable and format="readable")
    "search_suggestion": 'search(agent="YourAgent", pattern="auth", path="src/")',
    
    # Human-friendly hint (present if suggestions found and format="readable")
    "suggestion": "Did you mean 'auth.py'? (88% match)"
}
```

**Backwards Compatibility:**
- Core fields (`ok`, `error`, `absolute_path`, etc.) unchanged
- New fields are additive (won't break existing consumers)
- `format="structured"` and `format="compact"` get minimal response (no suggestions overhead)
- Existing FormatterDispatcher handles new fields via key-value display

### 4.4 Data Flow

```
User calls read_file(path="src/auth_handlers.py", format="readable")
    ↓
read_file.py line 1816: target.exists() == False
    ↓
classify_path_error(target) → "not_found"
    ↓
[if format == "readable":]
    ↓
get_fuzzy_file_suggestions("auth_handlers.py", Path("src/"))
    ↓
    → difflib.get_close_matches("auth_handlers.py", ["auth_handler.py", "auth.py", ...])
    → Returns [{"name": "auth_handler.py", "score": 0.93}]
    ↓
get_directory_listing(Path("src/"))
    ↓
    → parent.iterdir() (up to 1000 files, return first 30)
    → Returns {"files": ["auth.py", "handler.py", ...], "directories": ["api/"], ...}
    ↓
build_search_suggestion("auth_handlers", "src/", agent)
    ↓
Construct enriched error_response dict
    ↓
await finalize_response(error_response, "readable")
    ↓
FormatterDispatcher._format_readable_error() displays all fields
    ↓
User sees:
    "File not found: src/auth_handlers.py
     
     Did you mean 'auth_handler.py'? (93% match)
     
     Parent directory contains:
       Files: auth.py, handler.py, ...
       Directories: api/
     
     To search for files: search(agent='YourAgent', pattern='auth_handlers', path='src/')"
```

### 4.5 Performance Analysis

**Overhead Budget:** <5ms total added latency on error paths

| Operation | Typical Time | Worst Case | Mitigation |
|-----------|-------------|------------|------------|
| classify_path_error() | <0.1ms | 0.5ms (symlink resolution) | Simple if-else logic |
| get_fuzzy_file_suggestions() | 0.5-2ms | 5ms (1000 files) | Cap scan at 1000, early termination |
| get_directory_listing() | 0.1-0.5ms | 2ms (large dir) | Cap at 30 entries, bail at 1000 scanned |
| **Total** | **~1-3ms** | **~7ms** | Lazy evaluation skips for format!="readable" |

**Performance Guards:**
- Lazy evaluation: skip entirely when `format != "readable"`
- Early termination: stop scanning after 1000 files
- Capped results: max 5 suggestions, max 30 directory entries
- No caching: error paths are cold, simplicity > optimization
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/read_search_error_ux
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.


---
## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown', 'SQLite mirror']
- **Indexes & Performance:** FTS for sections
- **Migrations:** Sequential migrations tracked in storage layer


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
### 7.1 Unit Tests (utils/path_suggestions.py)

**Test File:** `tests/test_path_suggestions.py`

**Coverage Requirements:**
```python
# Fuzzy matching tests
def test_fuzzy_match_exact_match():
    # Exact filename should score 1.0
def test_fuzzy_match_close_match():
    # "auth_handlers.py" → "auth_handler.py" should score >0.9
def test_fuzzy_match_no_matches():
    # Completely different names should return empty list
def test_fuzzy_match_cutoff_threshold():
    # Low similarity matches (<0.6) should be filtered
def test_fuzzy_match_max_suggestions():
    # Should respect max_suggestions parameter
def test_fuzzy_match_include_directories():
    # Should include/exclude dirs based on parameter

# Directory listing tests  
def test_directory_listing_normal():
    # Standard directory with <30 items
def test_directory_listing_large():
    # Directory with >1000 items (should truncate and set flag)
def test_directory_listing_empty():
    # Empty directory should return empty lists
def test_directory_listing_permission_error():
    # Should gracefully return permission_error=True
def test_directory_listing_separate_files_dirs():
    # Should separate files and directories correctly
def test_directory_listing_hidden_files():
    # Should respect include_hidden parameter

# Error classification tests
def test_classify_not_found():
    # Non-existent path → "not_found"
def test_classify_is_directory():
    # Existing directory → "is_directory"
def test_classify_permission_denied():
    # Unreadable path → "permission_denied"
def test_classify_symlink():
    # Broken symlink → "is_symlink"

# Suggestion builder tests
def test_build_search_suggestion():
    # Should format valid search command
def test_build_read_suggestion():
    # Should format valid read_file command
```

### 7.2 Integration Tests (tools)

**Test File:** `tests/test_read_file_errors.py`, `tests/test_search_errors.py`

**Coverage Requirements:**
```python
# read_file integration tests
async def test_read_file_not_found_with_suggestions():
    # File doesn't exist, format="readable" → fuzzy suggestions returned
async def test_read_file_not_found_structured_format():
    # File doesn't exist, format="structured" → no suggestions (performance)
async def test_read_file_is_directory_error():
    # Path is directory → distinct error message, directory listing
async def test_read_file_permission_error():
    # Unreadable file → permission_denied error, graceful degradation
async def test_read_file_large_directory_parent():
    # Parent has >1000 files → suggestions truncated, no crash

# search integration tests
async def test_search_path_not_found_with_suggestions():
    # Path doesn't exist, format="readable" → fuzzy directory suggestions
async def test_search_path_not_found_structured_format():
    # Path doesn't exist, format="structured" → minimal response
async def test_search_permission_error_parent():
    # Parent unreadable → graceful degradation
```

### 7.3 Edge Case Tests

```python
# Symlinks
async def test_read_file_symlink_to_directory():
    # Symlink pointing to directory → "is_directory" error
async def test_read_file_broken_symlink():
    # Broken symlink → "is_symlink" error

# Special characters
async def test_fuzzy_match_special_chars():
    # Filenames with spaces, unicode, etc.

# Performance
async def test_fuzzy_match_performance():
    # 1000 files directory should complete in <10ms

# Backwards compatibility
async def test_error_response_backwards_compatible():
    # Core fields (ok, error, absolute_path) always present
    # New fields don't break existing consumers
```

### 7.4 Acceptance Criteria

**Must Pass Before Merge:**
- ✅ All unit tests pass (≥95% coverage for path_suggestions.py)
- ✅ All integration tests pass
- ✅ No crashes on permission errors, large directories, symlinks
- ✅ Performance regression tests pass (<5ms added latency on error paths)
- ✅ Backwards compatibility verified (existing consumers unaffected)
- ✅ Manual testing with real codebases (node_modules, .git, etc.)

**Quality Gates:**
- Test coverage ≥90% for new code
- No new linting errors
- All error paths have explicit tests
- Performance benchmarks documented
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md
- ARCHITECTURE_GUIDE.md

Generated via generate_doc_templates.


---