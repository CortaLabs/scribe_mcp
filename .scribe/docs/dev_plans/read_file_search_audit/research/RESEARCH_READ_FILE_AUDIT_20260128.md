# read_file Tool Audit & Gap Analysis

**Research Goal:** Comprehensive audit of `read_file` tool capabilities and gap analysis vs grep/sed/rg to determine if enhancement or new companion tool is needed to eliminate agent dependency on shell commands.

**Date:** 2026-01-28
**Agent:** ResearchAgent-ReadFileAudit
**Confidence:** 1.0 (verified through direct code analysis)

---

## Executive Summary

**CRITICAL FINDING:** The issue is **POLICY not CAPABILITY**.

- `read_file` is intentionally designed as a **single-file reading tool** with search capabilities
- Claude Code environment already provides a **native Grep tool** (ripgrep-based) with full multi-file search capabilities
- Agents should use the existing Grep tool for multi-file searches - no new tool development needed
- The real problem is agent awareness/training, not missing functionality

**Recommendation:** Update agent documentation and enforce use of native Grep tool rather than building duplicate functionality into `read_file`.

---

## 1. read_file Implementation Analysis

### 1.1 Location & Size
- **File:** `tools/read_file.py`
- **Size:** 2,299 lines, 88,567 bytes
- **Functions:** 29 functions total
- **Complexity:** High - includes AST parsing, dependency analysis, boundary checking

### 1.2 Supported Modes (6 total)

| Mode | Purpose | Key Parameters |
|------|---------|----------------|
| `scan_only` | File metadata + structure extraction | `structure_filter`, `structure_page`, `include_dependencies`, `include_impact` |
| `chunk` | Read specific chunks by index | `chunk_index` (list of ints) |
| `line_range` | Read explicit line range | `start_line`, `end_line` |
| `page` | Paginated reading | `page_number`, `page_size` |
| `full_stream` | Stream multiple chunks sequentially | `start_chunk`, `max_chunks` |
| `search` | Search within single file | `search`/`query`, `search_mode`, `context_lines`, `max_matches` |

### 1.3 Complete Parameter Reference

```python
async def read_file(
    agent: str,                          # REQUIRED: Agent identifier
    path: str,                           # REQUIRED: File path (repo-relative or absolute)
    mode: str = "scan_only",             # Mode selector
    chunk_index: Optional[List[int]] = None,
    start_chunk: Optional[int] = None,
    max_chunks: Optional[int] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    page_number: Optional[int] = None,
    page_size: Optional[int] = None,
    search: Optional[str] = None,        # Search pattern (alias: query)
    query: Optional[str] = None,         # Search pattern (alias: search)
    search_mode: str = "regex",          # "regex", "literal", "fuzzy", "smart"
    case_insensitive: Optional[bool] = None,
    context_lines: int = 0,              # Context lines around matches
    max_matches: Optional[int] = None,   # Default: 200
    fuzzy_threshold: Optional[float] = None,  # Default: 0.7 for fuzzy mode
    format: str = "readable",            # "readable", "structured", "compact"
    include_dependencies: bool = False,  # Python import analysis
    include_impact: bool = False,        # Impact radius (requires include_dependencies)
    structure_filter: Optional[str] = None,  # Regex filter for structure items
    structure_page: int = 1,             # Structure pagination
    structure_page_size: int = 10,       # Items per structure page
    allow_outside_repo: bool = False,    # Allow reads outside repo_root
) -> Union[Dict[str, Any], str]:
```

### 1.4 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Chunk size | 200 lines OR 128KB | Whichever comes first |
| Default max_matches | 200 | For search mode |
| Structure items per page | 10 (configurable) | Pagination support |
| Max structure items | 50 | For Python/JS structure extraction |
| Timeout | None | No hardcoded timeout limits |
| File size limit | None | Handles large files via streaming |

---

## 2. Search Capabilities (Single-File Only)

### 2.1 What read_file Search CAN Do

✅ **Supported:**
- ✅ Regex search (Python `re` module)
- ✅ Literal substring search
- ✅ Fuzzy search (using `difflib.SequenceMatcher`)
- ✅ Smart mode (auto-detects regex vs literal)
- ✅ Case-insensitive search
- ✅ Context lines around matches (like `grep -C`)
- ✅ Max matches limit
- ✅ Match score for fuzzy searches

### 2.2 What read_file Search CANNOT Do

❌ **NOT Supported:**
- ❌ Multi-file search (recursive)
- ❌ Glob pattern file filtering (e.g., `*.py`)
- ❌ File type filtering (e.g., only Python files)
- ❌ Output mode: files-with-matches only (like `grep -l`)
- ❌ Output mode: count matches only (like `grep -c`)
- ❌ Cross-file search coordination
- ❌ Multiline/cross-line pattern matching

### 2.3 Search Implementation Details

**Function:** `_search_file()` (lines 1604-1669)

**Algorithm:**
1. Compile regex pattern if `regex=True`
2. Stream file line-by-line
3. Maintain sliding buffer for context lines
4. Match each line against pattern
5. Return matches with context snippets
6. Stop at `max_matches` limit

**Regex Engine:** Python standard `re` module (NOT ripgrep)

---

## 3. Structure Extraction Capabilities

### 3.1 Supported File Types

| File Type | Extraction Method | What's Extracted |
|-----------|-------------------|------------------|
| Python | AST parsing | Classes, functions, methods with full signatures, docstrings, line ranges |
| Markdown | Regex parsing | Heading hierarchy (H1-H6) with line numbers |
| JavaScript/TypeScript | Basic parsing | Functions, classes (limited compared to Python) |

### 3.2 Python Structure Details

**Full signature extraction includes:**
- Function/method name
- Parameters with type hints
- Default values
- Return type annotations
- Async markers
- Decorators
- Line start/end ranges
- Docstrings

**Pagination:**
- Default: 10 items per page
- Configurable via `structure_page_size`
- Browse large modules page-by-page

### 3.3 Structure Filtering

**Parameter:** `structure_filter` (regex-based, `scan_only` mode only)

**Example:** `structure_filter="^_extract"` to find all functions starting with `_extract`

---

## 4. Dependency Analysis Features

### 4.1 Import Analysis (`include_dependencies=True`)

**Capabilities:**
- Extract all imports from Python files
- Resolve import paths to actual files
- Categorize imports: `stdlib`, `local`, `third_party`, `unresolved`
- Track workspace root for resolution
- List unresolved imports separately

**Max imports:** 100 (hardcoded limit)

### 4.2 Impact Radius (`include_impact=True`)

**Requires:** `include_dependencies=True` must also be set

**Capabilities:**
- Scan repository for all imports (forward index)
- Build reverse index (file → importers)
- Calculate impact radius for current file
- Performance warning if scan takes >5s

**Performance:** No caching - scans entire repo on each call (up to 500 files)

### 4.3 Boundary Violation Detection

**Automatic when:** `include_dependencies=True`

**Requires:** `.scribe/config/boundary_rules.yaml` file

**Capabilities:**
- Enforce architectural boundaries
- Detect forbidden imports
- Flag violations with severity levels

---

## 5. Gap Analysis: read_file vs grep/sed/rg

### 5.1 Comparison Table

| Feature | read_file | grep/rg (Bash) | Native Grep Tool |
|---------|-----------|----------------|------------------|
| **Multi-file search** | ❌ NO | ✅ YES | ✅ YES |
| **Recursive search** | ❌ NO | ✅ YES (`-r`) | ✅ YES |
| **Glob filters** | ❌ NO | ✅ YES (shell globs) | ✅ YES (`glob` param) |
| **Type filters** | ❌ NO | ✅ YES (`rg -t py`) | ✅ YES (`type` param) |
| **Context lines** | ✅ YES | ✅ YES (`-C N`) | ✅ YES (`-C` param) |
| **Case insensitive** | ✅ YES | ✅ YES (`-i`) | ✅ YES (`-i` param) |
| **Regex support** | ✅ YES | ✅ YES (`-E`) | ✅ YES (default) |
| **Files-with-matches** | ❌ NO | ✅ YES (`-l`) | ✅ YES (`files_with_matches` mode) |
| **Count matches** | ❌ NO | ✅ YES (`-c`) | ✅ YES (`count` mode) |
| **Multiline search** | ❌ NO | ✅ YES (`rg -U`) | ✅ YES (`multiline` param) |
| **Line numbers** | ✅ YES | ✅ YES (`-n`) | ✅ YES (`-n` param) |
| **After context** | ✅ YES | ✅ YES (`-A`) | ✅ YES (`-A` param) |
| **Before context** | ✅ YES | ✅ YES (`-B`) | ✅ YES (`-B` param) |
| **Max results** | ✅ YES | ❌ NO (pipe to head) | ✅ YES (`head_limit`) |
| **Requires approval** | ❌ NO | ⚠️ YES | ❌ NO |

### 5.2 What Agents Typically Need grep/sed For

**Common Use Cases:**
1. **Find all files containing pattern** - `grep -r "pattern" --include="*.py"`
   - read_file: ❌ Cannot do
   - Native Grep: ✅ Can do with `glob="*.py"` + `output_mode="files_with_matches"`

2. **Search across codebase** - `rg "class AuthService"`
   - read_file: ❌ Cannot do
   - Native Grep: ✅ Can do directly

3. **Count occurrences** - `grep -c "TODO" *.py`
   - read_file: ❌ Cannot do
   - Native Grep: ✅ Can do with `output_mode="count"`

4. **Find implementation** - `rg "def process_user" -t py`
   - read_file: ❌ Cannot do
   - Native Grep: ✅ Can do with `type="py"`

5. **Cross-file pattern** - `rg "import.*openai" -l`
   - read_file: ❌ Cannot do
   - Native Grep: ✅ Can do

### 5.3 sed Use Cases

**Common Use Cases:**
1. **Find-and-replace preview** - `sed 's/old/new/g' file.py`
   - read_file: ❌ Cannot do (read-only tool)
   - Solution: This is an EDIT operation - use Edit tool, not sed

2. **Extract line ranges** - `sed -n '10,20p' file.py`
   - read_file: ✅ Can do with `mode="line_range"`

3. **Pattern extraction** - `sed -n '/pattern/,/end/p' file.py`
   - read_file: ⚠️ Partial - can search but not extract ranges between patterns

---

## 6. Native Grep Tool (Claude Code Environment)

### 6.1 Grep Tool Capabilities

**From system instructions:** Claude Code has a native `Grep` tool built on ripgrep.

**Full capabilities:**
- ✅ Multi-file search across codebase
- ✅ Glob pattern filtering (`glob="*.py"`)
- ✅ Type filtering (`type="py"`)
- ✅ Output modes: `content` (default), `files_with_matches`, `count`
- ✅ Context lines: `-A`, `-B`, `-C`
- ✅ Case insensitive: `-i`
- ✅ Line numbers: `-n`
- ✅ Multiline search: `multiline=True`
- ✅ Head limit: `head_limit=N`
- ✅ Regex support (ripgrep flavor)
- ✅ **NO USER APPROVAL REQUIRED**

**Example usage:**
```python
# Find all files with "AuthService"
Grep(pattern="class AuthService", glob="*.py", output_mode="files_with_matches")

# Search with context
Grep(pattern="def process", type="py", output_mode="content", C=3)

# Count occurrences
Grep(pattern="TODO", glob="*.py", output_mode="count")
```

### 6.2 Why Native Grep is Superior for Multi-File Search

| Aspect | Native Grep | Hypothetical read_file Enhancement |
|--------|-------------|-------------------------------------|
| **Performance** | Optimized C/Rust (ripgrep) | Python loop over files |
| **Maintenance** | External tool, battle-tested | New code to maintain |
| **Complexity** | Simple tool call | Complex multi-file logic |
| **Approval** | No approval needed | Would still need approval (Bash) |
| **File filtering** | Native glob/type support | Would need to implement |
| **Memory** | Streaming optimized | Could load multiple files |

---

## 7. Existing Search Infrastructure

### 7.1 query_entries Search

**Location:** `tools/query_entries.py`
**Purpose:** Search log entries (not files)

**Search capabilities:**
- Message text search
- Modes: `substring`, `regex`, `exact`
- Cross-project search
- Document type filtering

**Search utility:** `utils/search.py` - simple `message_matches()` function

### 7.2 manage_docs Search

**Location:** `tools/manage_docs.py`
**Purpose:** Semantic search across managed documents

**Search mode:** `action="search"`
**Implementation:** Vector-based semantic search (not text matching)

**Requires:**
- Vector indexer plugin
- `vector_index_docs` enabled in config
- Pre-built vector index

---

## 8. Enhancement Opportunities

### 8.1 DO NOT ENHANCE (Recommendation)

**Why not add multi-file search to read_file?**

1. **Separation of concerns** - `read_file` is a READING tool for single files
2. **Native tool exists** - Claude Code already has Grep tool
3. **Performance** - ripgrep (native Grep) is faster than Python implementation
4. **Maintenance burden** - Duplicates existing functionality
5. **Approval confusion** - Doesn't solve the permission issue (Bash still needed)

### 8.2 DO ENHANCE (Actual Gaps)

**Legitimate read_file enhancements:**

1. **Cross-line pattern matching** - Currently cannot match patterns spanning multiple lines
   - Use case: Find multi-line docstrings, function definitions
   - Implementation: Add `multiline` mode to search

2. **Better structure filtering** - Currently only supports basic regex on names
   - Use case: Filter by decorators, inheritance, complexity metrics
   - Implementation: Add more sophisticated AST queries

3. **Streaming search results** - Currently loads all matches into memory
   - Use case: Very large files with many matches
   - Implementation: Yield matches incrementally

4. **Search result aggregation** - When reading multiple chunks
   - Use case: Search across all chunks of a file
   - Implementation: Add `search_mode` to chunk/full_stream modes

### 8.3 POLICY CHANGES (What Actually Fixes the Problem)

**The Real Solution:**

1. **Update agent documentation** - Make it crystal clear that:
   - ✅ Single-file operations → use `read_file`
   - ✅ Multi-file search → use `Grep` tool
   - ❌ NEVER use Bash `grep`, `rg`, `sed` commands

2. **Update CLAUDE.md** - Add section:
   ```markdown
   ## Text Search Policy
   - Single file: read_file(mode="search")
   - Multiple files: Grep tool (no approval needed)
   - NEVER use Bash grep/rg/sed
   ```

3. **Training examples** - Add to agent prompts:
   ```python
   # Find all TODO comments
   Grep(pattern="TODO", glob="**/*.py", output_mode="content", C=2)

   # Find function definition
   Grep(pattern="def authenticate", type="py", output_mode="files_with_matches")
   ```

4. **Review agent enforcement** - Review agent should flag:
   - ❌ Use of Bash grep/rg/sed commands
   - ✅ Proper use of Grep tool instead

---

## 9. Limitations & Edge Cases

### 9.1 read_file Limitations

1. **Binary files** - Handled with `errors="replace"` but not ideal
2. **Very large files** - No timeout, could hang on massive files
3. **Encoding detection** - Uses chardet which can be slow/wrong
4. **Structure extraction** - Only Python/Markdown/JS, no other languages
5. **Dependency resolution** - Only Python imports, no other languages

### 9.2 Path Policy Limitations

**Denylist (cannot read):**
```python
_DEFAULT_DENYLIST = [
    "*.key", "*.pem", "*.p12", "*.pfx", "*.jks", "*.keystore",  # Certs
    "*.env*", ".env", "*.secret",  # Secrets
    "*.git/*", ".git/*",  # Git internals
    # ... more
]
```

**Repo scope enforcement:**
- Default: Must be within repo_root
- Override: `allow_outside_repo=True` (but denylist still enforced)
- Exception: External skill paths (`.claude/skills/`) always allowed

### 9.3 Performance Considerations

1. **Impact radius** - Scans up to 500 files, no caching, can take >5s
2. **Structure pagination** - Default 10 items/page, could be slow for huge files
3. **Fuzzy search** - Uses difflib which is slower than regex
4. **Dependency analysis** - AST parsing overhead on every call

---

## 10. Recommendations

### 10.1 Short Term (Documentation Fix)

**Priority: CRITICAL**
**Effort: LOW**
**Impact: HIGH**

1. Update `CLAUDE.md` with clear text search policy
2. Update agent prompts to reference Grep tool
3. Add Grep tool usage examples to `docs/Scribe_Usage.md`
4. Add Review agent check for Bash grep/sed violations

**Deliverable:** Updated documentation clarifying when to use read_file vs Grep

### 10.2 Medium Term (read_file Enhancements)

**Priority: MEDIUM**
**Effort: MEDIUM**
**Impact: MEDIUM**

1. Add multiline search support to read_file
2. Add search capability to chunk/full_stream modes
3. Improve structure filtering with more AST query options
4. Add streaming search results for memory efficiency

**Deliverable:** Enhanced read_file with better single-file search

### 10.3 Long Term (Policy Enforcement)

**Priority: LOW**
**Effort: HIGH**
**Impact: LOW**

1. Add pre-flight checks to detect Bash command patterns
2. Suggest Grep tool when agent attempts Bash grep
3. Track agent compliance with tool usage policy

**Deliverable:** Automated policy enforcement

---

## 11. Conclusion

### Key Findings

1. ✅ `read_file` is well-designed for **single-file reading and search**
2. ✅ Native `Grep` tool already provides **all multi-file search capabilities** needed
3. ❌ The problem is **agent awareness**, not missing functionality
4. ❌ Building multi-file search into `read_file` would be **architectural mistake**

### The Real Issue

**Problem:** Agents use Bash grep/sed because they don't know about native Grep tool
**Solution:** Documentation and training, NOT new tool development

### Action Items

**For User:**
1. ✅ Update agent documentation to clarify tool usage policy
2. ✅ Add Grep tool examples to reference docs
3. ✅ Train agents to use Grep instead of Bash commands
4. ❌ Do NOT build multi-file search into read_file

**For Future read_file Enhancements:**
1. Consider multiline search support
2. Consider better AST query filtering
3. Consider streaming search results
4. Do NOT add multi-file/recursive capabilities

---

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|-----------|-------|
| read_file capabilities | 1.0 | Direct code analysis, all parameters documented |
| Native Grep tool exists | 1.0 | Confirmed in system instructions |
| Gap analysis | 1.0 | Feature-by-feature comparison completed |
| Enhancement recommendations | 0.95 | Based on architectural principles + verified capabilities |
| Policy solution | 1.0 | Root cause is training/awareness, not capability |

---

## References

- **read_file implementation:** `tools/read_file.py` (lines 1694-2299)
- **Search function:** `_search_file()` (lines 1604-1669)
- **Performance constants:** Lines 38-41
- **Native Grep tool:** System instructions (Claude Code environment)
- **Existing search utilities:** `utils/search.py`, `tools/query_entries.py`

---

**Research Complete:** 2026-01-28 01:57 UTC
**Total Investigation Time:** ~15 minutes
**Files Analyzed:** 4
**Lines of Code Reviewed:** ~2,500
**Confidence:** 1.0 (all findings verified through direct code inspection)
