# read_file.py - Forensic Audit Report

**File**: `tools/read_file.py`
**Size**: 785 LOC | 28,442 bytes
**Complexity**: Medium
**Auditor**: ResearchAgent-F-ReadFile
**Date**: 2026-01-05
**Version**: v2.1.1 (new tool)

---

## 1. Overview

**Purpose**: Repo-scoped file access tool with provenance logging, security policy enforcement, and multiple read modes.

`read_file.py` is Scribe MCP's **secure file reader** - the primary tool for reading arbitrary repository files with audit trails. It provides:
- **6 distinct read modes**: scan_only, chunk, line_range, page, full_stream, search
- **Security boundary enforcement**: denylist/allowlist policy via sentinel config
- **Provenance tracking**: All reads logged to progress log or sentinel log
- **File metadata extraction**: SHA256 hashing, encoding detection, newline analysis
- **Frontmatter awareness**: YAML frontmatter parsing with body-relative line numbers
- **Search capabilities**: literal, regex, fuzzy matching with context windows

**Key Characteristics**:
- **16-parameter signature** (read_file main function, includes `query` alias; query defaults to smart search inference)
- **Security-first design**: All paths validated against denylist before read
- **Mode routing complexity**: 6 completely different execution paths
- **Stateless operation**: Works in both project and sentinel modes
- **Zero modification**: Read-only tool - never writes files

**Critical Design Tensions**:
- **Security vs Flexibility**: Strict repo-scoping can block legitimate reads outside repo
- **Mode Proliferation**: 6 modes create large API surface but enable diverse use cases
- **Frontmatter Handling**: Line number offsetting adds complexity to chunk mode
- **Token Bloat**: All modes include scan metadata + audit metadata + reminders (structural verbosity)

**Relationships**:
- **Uses**: `utils/frontmatter.parse_frontmatter()` (shared)
- **Uses**: `utils/response.default_formatter` (output formatting)
- **Uses**: `shared/execution_context` (agent identity, provenance)
- **Uses**: `shared/logging_utils` (progress log writing)
- **Parallel to**: `manage_docs` (which also reads files but assumes project context)
- **Consumed by**: All agents needing file inspection with audit trail

---

## 2. Sub-System Breakdown

### Sub-System 1: Security Configuration & Path Normalization (Lines 26-117)

**Responsibilities**: Load security policy, normalize paths, enforce repo-scoping via denylist/allowlist.

**Line Ranges**:
- `26-34`: Default denylist constants (`.env`, `.git/`, `.scribe/registry/`, etc.)
- `42-52`: `_load_sentinel_config()` - Load allowlist/denylist from `.scribe/sentinel/sentinel_config.yaml`
- `54-66`: `_normalize_patterns()` - Expand user paths (`~/.ssh` → `/home/user/.ssh`)
- `68-70`: `_normalize_path()` - Convert backslashes to forward slashes (Windows compat)
- `72-74`: `_pattern_is_glob()` - Detect glob characters (`*`, `?`, `[`)
- `76-94`: `_matches_any()` - Pattern matching engine (glob + substring + path-component matching)
- `96-117`: `_enforce_path_policy()` - **CRITICAL SECURITY BOUNDARY**

**Security Contract**:
```python
# Input: path (absolute or relative), repo_root
# Output: None (allowed) | "denylist_match" | "absolute_path_not_allowlisted"
# Policy:
#   1. If path matches denylist → DENY
#   2. If path is relative to repo_root → ALLOW
#   3. If path is absolute AND NOT in allowlist → DENY
#   4. If path is absolute AND in allowlist → ALLOW
```

**Failure Policy**:
- Denylist match → Return error, log `scope_violation`, **NEVER read file**
- Absolute path not allowlisted → Return error, log `scope_violation`, **NEVER read file**
- This is **policy enforcement**, not a bug - intentional security boundary

**State Ownership**: Stateless - policy loaded from YAML on every call (no caching)

**Extractable Module**: [BUCKET:security] - Repo-scoped path policy enforcement
- **Origin**: `read_file.py:26-117`
- **Responsibilities**: Load security config, validate paths against denylist/allowlist
- **Used by**: read_file (currently), potentially other file access tools
- **Why extract**: Generic repo-scoping logic reusable for any file operation
- **Risks**: Tight coupling to `.scribe/sentinel/sentinel_config.yaml` structure
- **Before/After**:
  - Before: Security logic embedded in read_file, no reuse for future file tools
  - After: `RepoSecurityPolicy` class with `validate_path(path, repo_root) → Optional[str]`, used by read_file, potential future write tools, git operations

**Implicit Contracts**:
- Assumes `.scribe/sentinel/sentinel_config.yaml` exists and is valid YAML (silent failure returns empty dict)
- Glob patterns use `fnmatch` semantics (not regex)
- Path matching checks both absolute path and repo-relative path
- Pattern matching is order-independent (first match wins)

---

### Sub-System 2: File Scanning & Verification (Lines 119-178)

**Responsibilities**: Scan file metadata, compute SHA256 hash, detect encoding, analyze newlines, count lines.

**Line Ranges**:
- `119-178`: `_scan_file()` - Complete file metadata extraction

**Algorithm**:
1. Stream file in 65KB chunks
2. Compute SHA256 on raw bytes
3. Collect first 4KB sample for encoding detection
4. Detect newline types (CRLF, LF, mixed)
5. Count lines (handles files without trailing newline)
6. Estimate chunk count based on line count

**Outputs**:
```python
{
    "byte_size": int,
    "line_count": int,
    "sha256": str,  # hex digest
    "newline_type": "unknown" | "mixed" | "CRLF" | "LF",
    "encoding": "utf-8" | "latin-1",
    "estimated_chunk_count": int
}
```

**Failure Policy**:
- If file doesn't decode as UTF-8 → fallback to latin-1 (never fail)
- If file has no newlines but has content → line_count = 1
- If last line missing newline → line_count += 1 (correct count)

**State Ownership**: Stateless - pure function, no side effects

**Extractable Module**: [BUCKET:file_io] - File metadata scanner
- **Origin**: `read_file.py:119-178`
- **Responsibilities**: Extract file metadata (size, hash, encoding, newlines, line count)
- **Used by**: read_file (every mode), potentially manage_docs, log rotation tools
- **Why extract**: Generic file scanning logic needed by any tool that processes files
- **Risks**: None - pure function with no dependencies on read_file semantics
- **Before/After**:
  - Before: File scanning logic embedded in read_file, duplicated in other tools
  - After: `FileScanner.scan(path: Path) → FileScanResult` with typed result, used by read_file and all file processing tools

**Performance Notes**:
- Streams file (65KB chunks) - handles multi-GB files without OOM
- Single-pass algorithm - computes all metadata in one file traversal
- SHA256 computed incrementally (no double-read)

---

### Sub-System 3: Frontmatter Parsing (Lines 180-244)

**Responsibilities**: Detect and parse YAML frontmatter, extract frontmatter metadata, handle parsing errors.

**Line Ranges**:
- `180-244`: `_read_frontmatter_header()` - Frontmatter extraction

**Algorithm**:
1. Read first line - if not `---`, no frontmatter
2. Read until closing `---` or EOF
3. Parse YAML between delimiters
4. Return frontmatter data + metadata (line count, byte count, errors)

**Outputs**:
```python
{
    "has_frontmatter": bool,
    "frontmatter_raw": str,  # raw YAML text including delimiters
    "frontmatter": dict,  # parsed YAML or {} on error
    "frontmatter_line_count": int,
    "frontmatter_byte_count": int,
    "frontmatter_error": Optional[str]  # parse error details
}
```

**Failure Policy**:
- Missing closing `---` → Return error "missing closing delimiter", frontmatter = {}
- Invalid YAML → Return parse error, frontmatter = {}
- File read exception → Return error, has_frontmatter = False
- **NEVER blocks read** - errors returned in metadata, file still readable

**State Ownership**: Stateless - pure function

**Extractable Module**: [BUCKET:utilities] - Frontmatter parser (ALREADY EXTRACTED)
- **Origin**: `read_file.py:180-244` vs `utils/frontmatter.py`
- **Current State**: **DUPLICATION DETECTED** - read_file implements its own frontmatter parsing instead of using `utils/frontmatter.parse_frontmatter()`
- **Why duplication exists**: read_file needs byte/line counts that `utils/frontmatter` doesn't provide
- **Why extract**: N/A - should UNIFY with existing `utils/frontmatter` instead
- **Before/After**:
  - Before: Two frontmatter parsers in codebase - read_file's custom implementation (lines 180-244), utils/frontmatter shared implementation
  - After: Enhance `utils/frontmatter.parse_frontmatter()` to return `FrontmatterResult` with byte_count, line_count, raw_text fields; read_file calls shared implementation

**Implicit Contracts**:
- Frontmatter must start on line 1 (no leading whitespace allowed)
- Delimiters must be exactly `---` on their own line (no trailing content)
- Encoding from file scan used for decode (UTF-8 or latin-1)
- Errors always use `errors="replace"` - never raise decode exceptions

---

### Sub-System 4: Chunk Iteration (Lines 247-318)

**Responsibilities**: Stream file content in chunks (max 200 lines or 128KB per chunk), maintain chunk metadata.

**Line Ranges**:
- `247-318`: `_iter_chunks()` - Generator yielding chunk dictionaries

**Algorithm**:
1. Read file line-by-line (max 128KB per readline call)
2. Accumulate lines until chunk threshold (200 lines OR 128KB)
3. Flush chunk when threshold reached
4. Track byte offsets and line numbers per chunk

**Chunk Format**:
```python
{
    "chunk_index": int,  # 0-based
    "line_start": int,  # 1-based
    "line_end": int,  # 1-based, inclusive
    "byte_start": int,
    "byte_end": int,
    "content": str  # decoded text
}
```

**Failure Policy**:
- Handles files without trailing newline (line counting remains accurate)
- If chunk would exceed 128KB → flush early (prevents OOM)
- Never yields empty chunks

**State Ownership**: Stateless generator - no shared state between calls

**Extractable Module**: [BUCKET:file_io] - Streaming chunk reader
- **Origin**: `read_file.py:247-318`
- **Responsibilities**: Stream file in memory-bounded chunks with byte/line metadata
- **Used by**: read_file (chunk, full_stream modes), potentially log rotation, file processing tools
- **Why extract**: Generic chunking algorithm useful for any large-file processing
- **Risks**: Chunk size thresholds (200 lines, 128KB) are hardcoded constants
- **Before/After**:
  - Before: Chunking logic embedded in read_file, hardcoded thresholds
  - After: `FileChunker` class with configurable thresholds, `iter_chunks(path, max_lines=200, max_bytes=128KB) → Iterator[ChunkResult]`

**Performance Notes**:
- Memory-bounded: Max 128KB per chunk regardless of line count
- Single-pass streaming: Never holds entire file in memory
- Line-aware: Won't split lines across chunks (reads complete lines)

---

### Sub-System 5: Line Range Extraction (Lines 320-349)

**Responsibilities**: Extract specific line range from file with byte offset metadata.

**Line Ranges**:
- `320-349`: `_extract_line_range()` - Extract lines [start, end] inclusive

**Algorithm**:
1. Read file line-by-line
2. Skip lines before start_line
3. Collect lines [start_line, end_line]
4. Track byte offsets for collected region
5. Return content + metadata

**Outputs**:
```python
{
    "line_start": int,
    "line_end": int,
    "byte_start": int,
    "byte_end": int,
    "content": str
}
```

**Failure Policy**:
- If start_line > file line count → returns empty content
- If end_line > file line count → returns partial content up to EOF
- Byte offsets always reflect actual read region (0 if nothing read)

**State Ownership**: Stateless - pure function

**Extractable Module**: [BUCKET:file_io] - Line range extractor (merge with FileChunker)
- **Origin**: `read_file.py:320-349`
- **Responsibilities**: Extract arbitrary line range with byte offsets
- **Used by**: read_file (line_range, page modes)
- **Why extract**: Generic line extraction useful for any file processing tool
- **Risks**: None - pure function
- **Before/After**:
  - Before: Line extraction separate from chunking (code duplication - both read line-by-line)
  - After: `FileChunker.extract_range(start, end)` method - unifies line reading logic

---

### Sub-System 6: Search Engine (Lines 351-427)

**Responsibilities**: Search file content with literal, regex, or fuzzy matching; provide context windows.

**Line Ranges**:
- `351-358`: `_infer_search_mode()` - Auto-detect regex vs literal based on metacharacters
- `360-427`: `_search_file()` - Main search engine

**Search Modes**:
1. **Literal**: Substring match (case-sensitive or insensitive)
2. **Regex**: Compiled regex pattern matching
3. **Fuzzy**: `difflib.SequenceMatcher` with threshold (0.0-1.0)

**Algorithm**:
1. Compile regex matcher if regex mode (fail fast on invalid pattern)
2. Maintain context buffer (N lines before/after)
3. Read file line-by-line
4. Match current line against pattern
5. If match found, capture context window
6. Stop when max_matches reached

**Match Format**:
```python
{
    "line_number": int,
    "line": str,  # matched line
    "context_start": int,
    "context_end": int,
    "context": List[str],  # context window (up to 2*context_lines + 1 lines)
    "match_score": Optional[float]  # only for fuzzy mode
}
```

**Failure Policy**:
- Invalid regex → raise `ValueError` (caught by caller, returned as error response)
- Decode errors → use `errors="replace"` (never crash on binary content)
- Context buffer overflow → maintains sliding window (only last N lines)

**State Ownership**: Stateless - pure function

**Extractable Module**: [BUCKET:search] - File content search engine
- **Origin**: `read_file.py:351-427`
- **Responsibilities**: Multi-mode search with context windows
- **Used by**: read_file (search mode), potentially other tools needing file search
- **Why extract**: Generic search logic reusable for any content search scenario
- **Risks**: Tight coupling to read_file's error handling (ValueError for regex errors)
- **Before/After**:
  - Before: Search engine embedded in read_file, not reusable
  - After: `FileSearcher` class with `search(path, pattern, mode, context_lines, max_matches) → List[SearchMatch]`, used by read_file and potentially grep-like tools

**Performance Notes**:
- Stops early when max_matches reached (doesn't scan entire file unnecessarily)
- Context buffer size bounded (2*context_lines + 1 lines max in memory)
- Regex compiled once, reused for all lines

---

### Sub-System 7: Provenance Logging (Lines 429-456)

**Responsibilities**: Log file access events to project progress log or sentinel log (audit trail).

**Line Ranges**:
- `429-456`: `_log_project_read()` - Write read event to progress log

**Logged Metadata**:
```python
{
    "execution_id": str,
    "session_id": str,
    "intent": str,
    "agent_kind": str,
    "agent_instance_id": str,
    "agent_sub_id": Optional[str],
    "agent_display_name": str,
    "agent_model": str,
    # Plus mode-specific metadata (read_mode, path, chunk_index, search params, etc.)
}
```

**Logging Paths**:
1. **Project mode**: Writes to project's PROGRESS_LOG.md via `append_line()`
2. **Sentinel mode**: Writes to `.scribe/sentinel/<date>/sentinel.jsonl` via `append_sentinel_event()`

**Failure Policy**:
- If project has no progress_log configured → **silent skip** (no error)
- If log write fails → **silent skip** (never blocks read operation)
- Provenance is **best-effort** - read succeeds even if logging fails

**State Ownership**: Async side effect - doesn't modify read_file state

**Extractable Module**: NO - This is integration seam, not extractable
- **Why not**: Provenance logging is the bridge between read_file and the logging system - extracting it just moves the integration complexity elsewhere
- **Correct boundary**: read_file calls `_log_project_read()`, which calls shared logging utilities - the seam is already in the right place

**Implicit Contracts**:
- Assumes `resolve_logging_context()` never raises (handles all errors internally)
- Assumes `append_line()` is async and best-effort (won't block)
- Audit metadata structure matches sentinel schema expectations
- Tool name hardcoded as "read_file" (no parameterization)

---

### Sub-System 8: Main Mode Router & Response Assembly (Lines 459-788)

**Responsibilities**: Route to appropriate read mode handler, assemble responses, finalize formatting.

**Line Ranges**:
- `459-476`: Function signature (15 parameters)
- `477-503`: Execution context setup, audit metadata assembly
- `504-526`: Helper functions: `get_reminders()`, `finalize_response()`, `log_read()`
- `528-558`: Path policy enforcement (calls `_enforce_path_policy()`)
- `560-572`: File existence check
- `573-594`: File scan + frontmatter parsing (common to all modes)
- `600-602`: **Mode: scan_only**
- `605-658`: **Mode: chunk** (with frontmatter line offset handling)
- `660-672`: **Mode: line_range**
- `674-689`: **Mode: page** (pagination via line_range)
- `691-717`: **Mode: full_stream** (multi-chunk streaming)
- `719-786`: **Mode: search** (pattern matching)
- `788`: Invalid mode fallback

**Mode Routing Table**:
| Mode | Handler Lines | Key Operations |
|------|---------------|----------------|
| scan_only | 600-602 | Return scan metadata only, no content |
| chunk | 605-658 | Iterate chunks, filter by chunk_index, strip frontmatter from chunk 0 |
| line_range | 660-672 | Extract [start_line, end_line] |
| page | 674-689 | Extract page via line_range (page_number * page_size) |
| full_stream | 691-717 | Stream multiple chunks from start_chunk |
| search | 719-786 | Pattern search with mode inference, fuzzy threshold |

**Response Structure** (all modes):
```python
{
    "ok": bool,
    "scan": {
        "absolute_path": str,
        "repo_relative_path": Optional[str],
        "byte_size": int,
        "line_count": int,
        "sha256": str,
        "newline_type": str,
        "encoding": str,
        "estimated_chunk_count": int
    },
    "mode": str,
    "frontmatter": dict,
    "frontmatter_raw": str,
    "frontmatter_line_count": int,
    "frontmatter_byte_count": int,
    "has_frontmatter": bool,
    # Mode-specific fields:
    "chunks": List[dict],  # chunk, full_stream
    "chunk": dict,  # line_range, page
    "matches": List[dict],  # search
    "reminders": List[dict],  # all modes
    # Format-dependent rendering (readable vs structured)
}
```

**Frontmatter Line Offset Handling** (chunk mode only, lines 633-652):
- If first chunk contains frontmatter → strip frontmatter from content
- Adjust line_start/line_end to be body-relative (subtract frontmatter_line_count)
- Adjust byte_start/byte_end to be body-relative (subtract frontmatter_byte_count)
- Mark chunk with `frontmatter_stripped: true` flag
- Preserve original offsets in `original_line_start`, etc. fields

**Failure Policy**:
- Path policy violation → Return error + log `scope_violation` (line 545-558)
- File not found → Return error + log `read_file_error` (line 560-572)
- Invalid mode → Return error with unsupported mode message (line 788)
- Invalid parameters (e.g., missing start_line) → Return error describing requirement
- Regex compilation error (search mode) → Return error with regex details (line 749-768)

**State Ownership**:
- Execution context provided by server (read from global `server_module.get_execution_context()`)
- No mutable state - all responses freshly constructed

**Extractable Module**: NO - This IS the tool
- **Why not**: This is the core orchestration logic - extracting it would just create `read_file_v2`
- **Correct architecture**: Mode handlers call sub-system modules, main function routes requests - already clean separation

**Implicit Contracts**:
- Assumes `server_module.get_execution_context()` returns valid context (returns error if None)
- Assumes `default_formatter.finalize_tool_response()` handles format routing (readable/structured/compact)
- All modes include scan metadata even if unnecessary (token bloat but consistent structure)
- Reminders fetched asynchronously for every request (no caching)

---

### Sub-System 9: Path Normalization Utilities (Lines 54-94)

**Responsibilities**: Normalize patterns and paths for cross-platform compatibility.

**Line Ranges**:
- `54-66`: `_normalize_patterns()` - Expand `~` and convert patterns to list
- `68-70`: `_normalize_path()` - Replace backslashes with forward slashes
- `72-74`: `_pattern_is_glob()` - Detect glob metacharacters
- `76-94`: `_matches_any()` - Pattern matching with glob support

**Extractable Module**: [BUCKET:utilities] - Path normalization
- **Origin**: `read_file.py:54-94`
- **Responsibilities**: Cross-platform path handling, glob pattern matching
- **Used by**: read_file (security policy), potentially other tools with path handling
- **Why extract**: Generic utilities not specific to read_file
- **Risks**: None - pure functions
- **Before/After**:
  - Before: Path utilities embedded in read_file
  - After: `PathUtils` module with `normalize_patterns()`, `matches_any()` - used by read_file and other path-handling tools

---

### Sub-System 10: Sentinel Config Loading (Lines 42-52)

**Responsibilities**: Load security configuration from `.scribe/sentinel/sentinel_config.yaml`.

**Line Ranges**:
- `42-52`: `_load_sentinel_config()` - YAML config loader with error suppression

**Config Structure**:
```yaml
allowlist:
  - /home/user/allowed_path
  - /usr/local/bin
denylist:
  - ~/.ssh
  - .env
  - /etc
```

**Failure Policy**:
- Config file doesn't exist → Return `{}`
- Config file invalid YAML → Return `{}`
- Config file non-dict (e.g., list) → Return `{}`
- All errors suppressed via `try/except Exception` (silent failure)

**Extractable Module**: [BUCKET:config] - Config file loader
- **Origin**: `read_file.py:42-52`
- **Responsibilities**: Load YAML config with error tolerance
- **Used by**: read_file (security policy), potentially other tools
- **Why extract**: Generic YAML loading pattern
- **Risks**: Silent failure hides configuration errors from users
- **Before/After**:
  - Before: Config loading embedded in read_file
  - After: `ConfigLoader.load_yaml(path, default={}) → dict` - used by read_file and other config consumers

---

### Sub-System 11: Audit Metadata Assembly (Lines 493-503)

**Responsibilities**: Construct audit metadata from execution context for provenance logging.

**Line Ranges**:
- `493-503`: Inline audit_meta dict construction

**Metadata Fields**:
```python
{
    "execution_id": exec_context.execution_id,
    "session_id": exec_context.session_id,
    "intent": exec_context.intent,
    "agent_kind": exec_context.agent_identity.agent_kind,
    "agent_instance_id": exec_context.agent_identity.instance_id,
    "agent_sub_id": exec_context.agent_identity.sub_id,
    "agent_display_name": exec_context.agent_identity.display_name,
    "agent_model": exec_context.agent_identity.model,
}
```

**Extractable Module**: NO - Too simple to extract
- **Why not**: 10-line dict construction is not worth extracting - would just add indirection
- **Pattern note**: This metadata structure is likely duplicated in other tools - but extraction threshold not met

---

## 3. Modularization Notes

### Extractable Modules (Contract-First Analysis)

#### Module 1: RepoSecurityPolicy [BUCKET:security]
**Contract**:
- **Inputs**: `path: Path`, `repo_root: Path`, `config: Optional[Dict[str, Any]]`
- **Outputs**: `None` (allowed) | `"denylist_match"` | `"absolute_path_not_allowlisted"`
- **Failure Policy**: Never raises - returns error strings for policy violations
- **State Ownership**: Stateless - loads config on every call (no caching)

**Before/After**:
- **Before**: Security logic embedded in read_file lines 26-117, not reusable for future file tools (write operations, git commands, etc.)
- **After**: Standalone `RepoSecurityPolicy` class providing `validate_path(path, repo_root)`, `load_policy(repo_root)`, `matches_denylist(path)` methods. Used by read_file, future write_file tool, git integration tools.

---

#### Module 2: FileScanner [BUCKET:file_io]
**Contract**:
- **Inputs**: `path: Path`
- **Outputs**: `FileScanResult(byte_size, line_count, sha256, newline_type, encoding, estimated_chunk_count)`
- **Failure Policy**: Never raises for decode errors - fallback to latin-1
- **State Ownership**: Stateless - pure function

**Before/After**:
- **Before**: File scanning logic (lines 119-178) embedded in read_file, likely duplicated in manage_docs and other file processors
- **After**: Reusable `FileScanner.scan(path)` returning typed `FileScanResult`. Used by read_file, manage_docs, log rotation tools, any file processing infrastructure.

---

#### Module 3: Unified Frontmatter Parser [BUCKET:utilities]
**Contract**:
- **Inputs**: `path: Path`, `encoding: str`
- **Outputs**: `FrontmatterResult(has_frontmatter, frontmatter_data, raw_text, line_count, byte_count, error)`
- **Failure Policy**: Returns empty dict + error string on parse failures, never raises
- **State Ownership**: Stateless

**Before/After**:
- **Before**: TWO frontmatter parsers exist - `read_file.py:180-244` (custom) and `utils/frontmatter.py` (shared). Duplication because read_file needs byte/line counts that shared version doesn't provide.
- **After**: Enhance `utils/frontmatter.parse_frontmatter()` to return extended `FrontmatterResult` with byte_count and line_count. Delete read_file's custom parser (lines 180-244). Single source of truth for frontmatter parsing.

**CRITICAL**: This is UNIFICATION, not extraction - module already exists but incomplete.

---

#### Module 4: FileChunker [BUCKET:file_io]
**Contract**:
- **Inputs**: `path: Path`, `encoding: str`, `max_lines: int = 200`, `max_bytes: int = 128KB`
- **Outputs**: `Iterator[ChunkResult(chunk_index, line_start, line_end, byte_start, byte_end, content)]`
- **Failure Policy**: Never yields empty chunks, handles files without trailing newlines
- **State Ownership**: Generator state (internal) - no shared state between calls

**Before/After**:
- **Before**: Chunking logic (lines 247-318) and line extraction logic (lines 320-349) are separate implementations that both read files line-by-line. Code duplication.
- **After**: Unified `FileChunker` class with `iter_chunks()` generator and `extract_range(start, end)` method. Line extraction becomes special case of chunking. Single file-reading implementation.

---

#### Module 5: FileSearcher [BUCKET:search]
**Contract**:
- **Inputs**: `path: Path`, `encoding: str`, `pattern: str`, `mode: SearchMode`, `context_lines: int`, `max_matches: int`, `case_insensitive: bool`, `fuzzy_threshold: float`
- **Outputs**: `List[SearchMatch(line_number, line, context_start, context_end, context, match_score)]` OR raises `ValueError` for invalid regex
- **Failure Policy**: Raises ValueError for regex compilation errors, otherwise returns matches (empty list if no matches)
- **State Ownership**: Stateless

**Before/After**:
- **Before**: Search engine (lines 351-427) embedded in read_file, not available to other tools needing file search capabilities
- **After**: Standalone `FileSearcher` class providing `search(path, pattern, mode, ...)` method. Used by read_file (search mode), potentially by grep-like tools, log analysis tools, any content search scenario.

---

### Intentionally Coupled (Should NOT Extract)

#### 1. Main Mode Router (Lines 459-788)
**Why not extractable**: This IS the tool - extracting orchestration logic would just create `read_file_v2`. The router delegates to sub-systems (scan, chunk, search, etc.) which are extractable. The routing itself is read_file's core responsibility.

#### 2. Provenance Logging (Lines 429-456)
**Why not extractable**: This is the integration seam between read_file and the logging system. Extracting it just moves the integration complexity to a different file without improving clarity. The seam is already at the correct boundary.

#### 3. Audit Metadata Assembly (Lines 493-503)
**Why not extractable**: 10-line dict construction - extraction threshold not met. This pattern may exist in other tools but isn't complex enough to warrant shared infrastructure.

---

## 4. Implicit Contracts

### Contract 1: Repo-Scoping Invariant
**Assumption**: All file paths must be validated against denylist/allowlist before read.
**Not Enforced By**: Type system (paths are strings, not validated types)
**What Breaks**: If caller bypasses `_enforce_path_policy()` → security boundary violated, sensitive files readable
**Evidence**: Lines 545-558 - policy check happens BEFORE file operations
**Why It Matters**: Security boundary depends on runtime check, not compile-time guarantee

---

### Contract 2: Frontmatter Line Offset Correctness
**Assumption**: When frontmatter is stripped from chunk 0, line numbers MUST be adjusted by frontmatter_line_count to maintain body-relative addressing.
**Not Enforced By**: Type system or validation - adjustment logic inline (lines 633-652)
**What Breaks**: If offset calculation wrong → line numbers reference wrong content, editing tools break
**Evidence**: Complex arithmetic: `line_start = max(1, line_start - line_offset)` without verification
**Why It Matters**: Line numbers returned to callers used for editing - off-by-one errors corrupt edits

---

### Contract 3: Encoding Fallback Hierarchy
**Assumption**: All text decoding uses UTF-8 first, falls back to latin-1 on failure.
**Not Enforced By**: Centralized encoding logic - scattered across functions
**What Breaks**: If different functions use different fallback → inconsistent decoding across modes
**Evidence**: Lines 162-166 (scan), line 261 (chunks), line 347 (line range), line 386 (search) - all implement same fallback independently
**Why It Matters**: Consistent encoding critical for content integrity - duplication risks divergence

---

### Contract 4: Error Responses Must Include Scan Metadata
**Assumption**: Even error responses should include absolute_path and repo_relative_path for debugging.
**Not Enforced By**: Validation or type system - each error handler manually constructs response
**What Breaks**: If error handler forgets path fields → debugging difficulty
**Evidence**: Lines 552-558 (policy error), lines 566-571 (not found error), lines 616-621 (chunk error) - all manually construct similar error dicts
**Why It Matters**: Consistent error structure enables automated error handling

---

### Contract 5: Silent Sentinel Config Failures
**Assumption**: If `.scribe/sentinel/sentinel_config.yaml` is missing or invalid, default to empty config (no allowlist/denylist).
**Not Enforced By**: Any warning or error - completely silent (line 50 catches `Exception`)
**What Breaks**: User expects security policy to be enforced but typo in YAML → policy silently disabled
**Evidence**: `_load_sentinel_config()` returns `{}` on any error, no logging
**Why It Matters**: Silent security failures are dangerous - users don't know policy isn't active

---

### Contract 6: Mode Name Case-Insensitivity
**Assumption**: Mode parameter is case-insensitive (`mode.lower()` at lines 482, 594).
**Not Enforced By**: Documentation or type hints (mode parameter is `str`, not enum)
**What Breaks**: If caller passes `"SCAN_ONLY"` expecting it to work, it does - but this isn't documented
**Evidence**: Lines 482, 594 - lowercase normalization happens before routing
**Why It Matters**: API contract unclear - users don't know if case matters

---

### Contract 7: Reminders Are Best-Effort
**Assumption**: Reminder fetching can fail without blocking read operation.
**Not Enforced By**: Code structure - reminders fetched in `finalize_response()` which is awaited (looks blocking)
**What Breaks**: If reminder fetch hangs or errors → entire read_file call delayed/failed
**Evidence**: Line 519 - `await get_reminders()` wrapped in try/except (line 514) that returns `[]` on failure
**Why It Matters**: Async error handling not obvious from API surface

---

## 5. Token Analysis

### Token Bloat Categories

#### Category 1: Structural Metadata (UNAVOIDABLE)
**Component**: Scan metadata block
**Location**: Lines 574-591 (response assembly)
**Size**: ~150-200 tokens per read
**Content**:
```python
{
    "scan": {
        "absolute_path": "...",
        "repo_relative_path": "...",
        "byte_size": 28442,
        "line_count": 785,
        "sha256": "8b3c44b530bf71fa...",
        "newline_type": "LF",
        "encoding": "utf-8",
        "estimated_chunk_count": 4
    }
}
```
**Justification**: File identity metadata required for provenance and cache invalidation
**Extractable**: NO - required for file verification and security audit

---

#### Category 2: Metadata Overhead (AUDIT TRAIL)
**Component**: Audit metadata (execution context)
**Location**: Lines 493-503
**Size**: ~100-150 tokens per read
**Content**:
```python
{
    "execution_id": "uuid",
    "session_id": "uuid",
    "intent": "...",
    "agent_kind": "research",
    "agent_instance_id": "...",
    "agent_sub_id": null,
    "agent_display_name": "...",
    "agent_model": "claude-sonnet-4-5"
}
```
**Justification**: Provenance tracking - who read what, when, why
**Extractable**: NO - required for security audit trail
**Optimization**: Could be moved to separate audit log instead of tool response

---

#### Category 3: Frontmatter Duplication (QUESTIONABLE)
**Component**: Frontmatter fields in response
**Location**: Lines 586-593
**Size**: ~50-200 tokens depending on frontmatter size
**Content**:
```python
{
    "frontmatter": {...},  # Parsed YAML
    "frontmatter_raw": "---\n...\n---",  # Raw text
    "frontmatter_line_count": 10,
    "frontmatter_byte_count": 456,
    "has_frontmatter": true
}
```
**Justification**: Frontmatter needed for line offset calculations, raw text for debugging
**Extractable**: Partially - `frontmatter_raw` could be omitted from default response (only include on request)
**Before/After**:
- Before: All frontmatter fields always included (even when not needed)
- After: `frontmatter` and `has_frontmatter` always included (needed), `frontmatter_raw` only if `include_raw_frontmatter=true` parameter

---

#### Category 4: Reminder Overhead (CONTEXTUAL)
**Component**: Reminders list
**Location**: Line 519 (added to every response)
**Size**: 0-500+ tokens depending on project state
**Content**:
```python
{
    "reminders": [
        {"type": "...", "message": "...", "priority": "..."},
        ...
    ]
}
```
**Justification**: Contextual guidance for agents
**Extractable**: YES - reminders could be opt-in via `include_reminders=true` parameter
**Before/After**:
- Before: Reminders fetched and included for every read (even scan_only)
- After: Reminders only fetched if `include_reminders=true` (default false for high-frequency tools)

---

#### Category 5: Mode-Specific Verbosity (VARIES BY MODE)

**scan_only mode**: ~300-400 tokens (scan + frontmatter + reminders)
**chunk mode**: ~500-2000+ tokens per chunk depending on content size
**line_range mode**: ~400-1500 tokens depending on range size
**page mode**: ~400-1500 tokens (same as line_range)
**full_stream mode**: ~1000-10000+ tokens for multi-chunk reads
**search mode**: ~500-5000+ tokens depending on matches + context windows

**Bloat Analysis**:
- **scan_only**: Appropriate - metadata-only response
- **chunk/line_range/page**: Content-driven - token count matches requested content
- **full_stream**: Potentially bloated - no max chunk limit (could return entire file)
- **search**: Context windows inflate results - each match includes 2*context_lines + 1 lines

---

### Token Profile Estimates

Based on code analysis (actual execution blocked by import issues):

| Mode | Min Tokens | Avg Tokens | P95 Tokens | Max Tokens | Primary Bloat Source |
|------|-----------|-----------|-----------|-----------|---------------------|
| scan_only | 300 | 350 | 450 | 500 | Scan metadata + reminders |
| chunk (single) | 500 | 1200 | 2500 | 3000 | Content + scan + frontmatter |
| chunk (multi) | 1000 | 3000 | 8000 | 15000 | Multiple chunks + scan |
| line_range | 400 | 1000 | 2000 | 5000 | Content + scan + frontmatter |
| page | 400 | 1000 | 2000 | 5000 | Same as line_range |
| full_stream | 1000 | 5000 | 15000 | 50000+ | **NO MAX LIMIT** - could return entire file |
| search (literal) | 500 | 1500 | 4000 | 10000 | Context windows per match |
| search (fuzzy) | 500 | 2000 | 5000 | 15000 | Match scores + context |
| search (regex) | 500 | 1500 | 4000 | 10000 | Context windows per match |

**Critical Finding**: `full_stream` mode has NO upper bound - passing `max_chunks=1000` could return 50MB+ file (200K+ tokens).

---

### Optimization Opportunities

1. **Make reminders opt-in**: Save 0-500 tokens per call for high-frequency reads
2. **Omit frontmatter_raw by default**: Save 50-200 tokens, include only on request
3. **Add max_chunks hard limit**: Prevent full_stream mode from returning unbounded content
4. **Compress scan metadata**: SHA256 could be truncated to 16 chars (still unique), save ~48 chars
5. **Audit metadata to separate channel**: Move execution context to audit log, remove from tool response

---

## 6. Error Handling Architecture

### Policy Failures (Intentional, User-Facing)

#### Policy 1: Denylist Match
**Lines**: 545-558
**Trigger**: Path matches sentinel config denylist (e.g., `.env`, `/etc/passwd`)
**Response**: `{"ok": false, "error": "read_file denied", "reason": "denylist_match", ...}`
**Logged**: `scope_violation` event
**Justification**: Security boundary - prevents reading sensitive files

---

#### Policy 2: Absolute Path Not Allowlisted
**Lines**: 545-558
**Trigger**: Path is absolute and not in sentinel config allowlist
**Response**: `{"ok": false, "error": "read_file denied", "reason": "absolute_path_not_allowlisted", ...}`
**Logged**: `scope_violation` event
**Justification**: Repo-scoping enforcement - only repo-relative or explicitly allowed paths

---

#### Policy 3: File Not Found
**Lines**: 560-572
**Trigger**: Path doesn't exist or isn't a file
**Response**: `{"ok": false, "error": "file not found", ...}`
**Logged**: `read_file_error` event (reason: file_not_found)
**Justification**: User error - requested path doesn't exist

---

#### Policy 4: Invalid Parameters
**Lines**: Multiple (607-612, 661-664, 675-676, 692-695, 720-725)
**Trigger**: Missing required parameters for mode (e.g., chunk_index for chunk mode)
**Response**: `{"ok": false, "error": "descriptive message"}`
**Logged**: No logging for parameter errors (silent)
**Justification**: API contract violation - caller passed invalid params

---

### Bugs (Unintentional Failures)

#### BUG-READ-001: Silent Sentinel Config Failures
**Lines**: 42-52 (`_load_sentinel_config`)
**Symptom**: If `.scribe/sentinel/sentinel_config.yaml` has YAML syntax error → returns `{}` (no allowlist/denylist)
**Root Cause**: `except Exception` catches YAML parse errors silently
**Impact**: Security policy silently disabled - users don't know denylist isn't enforced
**Evidence**: Line 50 - broad exception handler with no logging
**Severity**: HIGH - security boundary failure
**Failure Type**: BUG - users expect parse errors to be reported, not silently ignored

**Spec**:
```yaml
spec_id: SPEC-READ-001
title: Report sentinel config parse errors
file: tools/read_file.py
lines: [42-52]
problem: Silent YAML parse errors disable security policy
solution: >
  1. Change _load_sentinel_config to return tuple: (config: dict, error: Optional[str])
  2. If YAML parse fails, return ({}, "YAML parse error: ...")
  3. Caller logs warning if error is present (don't fail read, but warn user)
  4. Add test: invalid YAML → warning logged, empty config returned
before: |
  Security policy silently disabled on config errors
after: |
  Users warned about config issues, can fix YAML syntax
```

---

#### BUG-READ-002: Frontmatter Line Offset Off-by-One Risk
**Lines**: 633-652
**Symptom**: Frontmatter line offset calculation uses `max(1, line_start - line_offset)` without verification
**Root Cause**: Arithmetic assumes frontmatter_line_count is accurate, but no test verifies edge cases
**Impact**: If frontmatter has unusual structure (missing closing `---`, empty lines) → line numbers wrong → editing breaks
**Evidence**: No bounds checking on offset calculation, no test for edge cases
**Severity**: MEDIUM - affects chunk mode only, editing tools impacted
**Failure Type**: BUG - edge case handling incomplete

**Spec**:
```yaml
spec_id: SPEC-READ-002
title: Verify frontmatter offset correctness
file: tools/read_file.py
lines: [633-652]
problem: Line offset calculation unverified for edge cases
solution: >
  1. Add assertion: adjusted line numbers must be >= 1 and <= original line numbers
  2. If assertion fails, log error and return chunk without offset adjustment (safer fallback)
  3. Add tests: frontmatter with no closing delimiter, frontmatter larger than chunk, empty frontmatter
before: |
  Frontmatter offset bugs silent, corrupt line numbers
after: |
  Offset errors detected, fallback to safe behavior
```

---

#### BUG-READ-003: Full_Stream Mode Unbounded
**Lines**: 691-717
**Symptom**: `full_stream` mode has no hard limit on max_chunks → caller can request entire file
**Root Cause**: No upper bound enforced on `max_chunks` parameter
**Impact**: Passing `max_chunks=10000` on 50MB file → 200K+ token response → OOM or timeout
**Evidence**: Line 697 - `max_chunk_count = int(max_chunks if max_chunks is not None else (page_size or 1))` - no clamping
**Severity**: MEDIUM - DoS vector, resource exhaustion
**Failure Type**: BUG - missing resource limit

**Spec**:
```yaml
spec_id: SPEC-READ-003
title: Add hard limit to full_stream max_chunks
file: tools/read_file.py
lines: [691-717]
problem: No upper bound on chunks returned - DoS risk
solution: >
  1. Define MAX_CHUNKS constant = 50 (10K lines max)
  2. Clamp max_chunks: min(max_chunks, MAX_CHUNKS)
  3. If caller requests > MAX_CHUNKS, log warning and return clamped result
  4. Add test: max_chunks=1000 → returns only 50 chunks
before: |
  full_stream can return unbounded content (50MB+ files)
after: |
  full_stream limited to reasonable max (50 chunks = 10K lines)
```

---

#### BUG-READ-004: Encoding Fallback Duplication
**Lines**: 162-166, 261, 347, 386
**Symptom**: UTF-8 → latin-1 fallback logic duplicated in 4 functions
**Root Cause**: No centralized encoding detection - each function implements independently
**Impact**: If fallback logic needs update (e.g., add UTF-16 support) → must change 4 places → divergence risk
**Evidence**: Identical `try: decode('utf-8') except: decode('latin-1')` in scan, chunks, line_range, search
**Severity**: LOW - maintenance burden, not immediate bug
**Failure Type**: BUG - code duplication creating technical debt

**Spec**:
```yaml
spec_id: SPEC-READ-004
title: Centralize encoding fallback logic
file: tools/read_file.py
lines: [162-166, 261, 347, 386]
problem: Encoding fallback duplicated 4 times - divergence risk
solution: >
  1. Create _decode_with_fallback(bytes, primary='utf-8', fallback='latin-1') -> str
  2. Replace all 4 implementations with calls to shared function
  3. Add test: binary content → latin-1 decode consistent across all functions
before: |
  4 copies of encoding logic - update requires 4 edits
after: |
  Single encoding fallback function - update once, applies everywhere
```

---

### Error Handling Policy Classification

**Policy Failures** (intentional, expected):
- Denylist/allowlist violations (security boundary)
- File not found (user error)
- Invalid parameters (API contract)
- Invalid regex patterns (user input error)

**Bugs** (unintentional, should be fixed):
- Silent sentinel config parse errors (BUG-READ-001)
- Frontmatter offset edge cases (BUG-READ-002)
- Unbounded full_stream (BUG-READ-003)
- Encoding fallback duplication (BUG-READ-004)

---

## 7. Known Issues

### Issue 1: Frontmatter Parser Duplication
**Severity**: MEDIUM
**Type**: Architecture Debt
**Evidence**: Lines 180-244 implement custom frontmatter parsing; `utils/frontmatter.py` has shared implementation
**Root Cause**: Shared frontmatter parser doesn't return byte/line counts needed by read_file
**Impact**: Two parsers to maintain, divergence risk
**Spec**: See Module 3 in Modularization Notes - enhance `utils/frontmatter` to return extended result

---

### Issue 2: Silent Security Config Failures
**Severity**: HIGH
**Type**: Security Bug (BUG-READ-001)
**Evidence**: Line 50 - `except Exception` returns `{}` silently
**Root Cause**: Error suppression without logging
**Impact**: Security policy silently disabled on config errors
**Spec**: See SPEC-READ-001 above

---

### Issue 3: Mode Proliferation
**Severity**: LOW
**Type**: API Complexity
**Evidence**: 6 read modes (scan_only, chunk, line_range, page, full_stream, search)
**Root Cause**: Each use case gets dedicated mode instead of composing primitives
**Impact**: Large API surface, documentation burden, testing complexity
**Observation**: `page` mode is just `line_range` with arithmetic; `full_stream` is just `chunk` with iteration. Could these be composable?

**Spec**:
```yaml
spec_id: SPEC-READ-005
title: Evaluate mode composition vs proliferation
file: tools/read_file.py
lines: [459-788]
problem: 6 modes create large API surface - some are composite
solution: >
  RESEARCH QUESTION (not implementation):
  Could page/full_stream be eliminated in favor of:
  - page_number param on line_range mode?
  - start_chunk + chunk_count params on chunk mode?

  Benefits: Smaller API, clearer composition
  Risks: Breaking change, existing callers would need updates

  Decision: Phase 6 architectural decision - not a bug fix
before: |
  6 modes, some composite (page = line_range + arithmetic)
after: |
  Potentially 4 core modes, composable parameters
```

---

### Issue 4: Token Bloat from Reminders
**Severity**: LOW
**Type**: Performance/UX
**Evidence**: Line 519 - reminders fetched for every read, even scan_only
**Root Cause**: Reminders always included, no opt-out
**Impact**: 0-500 tokens overhead per read, especially problematic for high-frequency reads
**Spec**: See Category 4 in Token Analysis - make reminders opt-in

---

### Issue 5: Full_Stream Unbounded (BUG-READ-003)
**Severity**: MEDIUM
**Type**: Resource Limit Bug
**Evidence**: Lines 691-717 - no max_chunks upper bound
**Impact**: DoS vector, 200K+ token responses possible
**Spec**: See SPEC-READ-003 above

---

## 8. Implementation Specs

### SPEC-READ-001: Report Sentinel Config Parse Errors
```yaml
spec_id: SPEC-READ-001
title: Report sentinel config parse errors
priority: HIGH
type: security_enhancement
file: tools/read_file.py
lines: [42-52]

problem: |
  _load_sentinel_config() silently returns {} on YAML parse errors.
  Users don't know security policy is disabled due to config typos.

solution:
  step_1:
    description: Change return type to tuple
    changes:
      - file: tools/read_file.py
        line: 42
        old: "def _load_sentinel_config(repo_root: Path) -> Dict[str, Any]:"
        new: "def _load_sentinel_config(repo_root: Path) -> Tuple[Dict[str, Any], Optional[str]]:"

  step_2:
    description: Capture parse errors
    changes:
      - file: tools/read_file.py
        lines: [46-51]
        old: |
          try:
              data = yaml.safe_load(handle) or {}
              return data if isinstance(data, dict) else {}
          except Exception:
              return {}
        new: |
          try:
              data = yaml.safe_load(handle) or {}
              if not isinstance(data, dict):
                  return {}, "config root must be dict, got {type(data).__name__}"
              return data, None
          except yaml.YAMLError as exc:
              return {}, f"YAML parse error: {exc}"
          except Exception as exc:
              return {}, f"config load error: {exc}"

  step_3:
    description: Update caller to log warnings
    changes:
      - file: tools/read_file.py
        lines: [97-99]
        old: "config = _load_sentinel_config(repo_root)"
        new: |
          config, config_error = _load_sentinel_config(repo_root)
          if config_error:
              # TODO: Log warning via provenance system
              pass  # Non-blocking - continue with empty config

tests:
  - test_invalid_yaml_reports_error:
      setup: Create sentinel_config.yaml with syntax error
      call: read_file(path="test.txt")
      expect: Warning logged, empty config used, read succeeds

  - test_non_dict_config_reports_error:
      setup: sentinel_config.yaml contains list instead of dict
      call: read_file(path="test.txt")
      expect: Error reported, empty config used

migration: |
  Non-breaking - return type changes but error handling is backward compatible
```

---

### SPEC-READ-002: Verify Frontmatter Offset Correctness
```yaml
spec_id: SPEC-READ-002
title: Verify frontmatter offset correctness
priority: MEDIUM
type: robustness_enhancement
file: tools/read_file.py
lines: [633-652]

problem: |
  Frontmatter line offset adjustment assumes frontmatter_line_count is accurate.
  Edge cases (missing closing delimiter, empty frontmatter) not tested.
  Off-by-one errors corrupt line numbers for editing tools.

solution:
  step_1:
    description: Add offset validation
    changes:
      - file: tools/read_file.py
        lines: [645-652]
        add_after_line: 644
        new: |
          # Validate offset calculation
          original_start = first_chunk.get("line_start", 1)
          original_end = first_chunk.get("line_end", 1)
          adjusted_start = max(1, original_start - line_offset)
          adjusted_end = max(0, original_end - line_offset)

          if adjusted_start > original_start or adjusted_start < 1:
              # Offset calculation failed - skip adjustment
              await log_read("frontmatter_offset_error", {
                  "reason": "invalid_offset",
                  "original_start": original_start,
                  "line_offset": line_offset,
                  "adjusted_start": adjusted_start
              })
              # Return chunk without offset adjustment (safer)
              continue

  step_2:
    description: Add assertion for debugging
    changes:
      - file: tools/read_file.py
        lines: [645-652]
        add_assertion: |
          assert 1 <= adjusted_start <= original_start, \
              f"Invalid offset: {adjusted_start} not in [1, {original_start}]"

tests:
  - test_frontmatter_no_closing_delimiter:
      setup: File with "---\nkey: value\n" (no closing ---)
      call: read_file(mode="chunk", chunk_index=[0])
      expect: Frontmatter error reported, chunk returned without offset

  - test_frontmatter_larger_than_chunk:
      setup: File with 250-line frontmatter, chunk size 200
      call: read_file(mode="chunk", chunk_index=[0])
      expect: Offset validation detects issue, chunk returned safely

  - test_empty_frontmatter:
      setup: File with "---\n---\n" (empty frontmatter)
      call: read_file(mode="chunk", chunk_index=[0])
      expect: line_offset=2, content starts at line 3

migration: |
  Non-breaking - adds validation, degrades gracefully on edge cases
```

---

### SPEC-READ-003: Add Hard Limit to Full_Stream Max_Chunks
```yaml
spec_id: SPEC-READ-003
title: Add hard limit to full_stream max_chunks
priority: MEDIUM
type: resource_limit
file: tools/read_file.py
lines: [691-717]

problem: |
  full_stream mode has no upper bound on max_chunks.
  Caller passing max_chunks=10000 on 50MB file → 200K+ tokens → OOM.

solution:
  step_1:
    description: Add constant
    changes:
      - file: tools/read_file.py
        lines: [36-40]
        add_constant: |
          _MAX_CHUNKS_PER_REQUEST = 50  # Max 10K lines (200 lines/chunk * 50)

  step_2:
    description: Clamp max_chunks
    changes:
      - file: tools/read_file.py
        lines: [696-697]
        old: |
          start_index = int(start_chunk if start_chunk is not None else (chunk_index[0] if chunk_index else 0))
          max_chunk_count = int(max_chunks if max_chunks is not None else (page_size or 1))
        new: |
          start_index = int(start_chunk if start_chunk is not None else (chunk_index[0] if chunk_index else 0))
          requested_chunks = int(max_chunks if max_chunks is not None else (page_size or 1))
          max_chunk_count = min(requested_chunks, _MAX_CHUNKS_PER_REQUEST)

          if requested_chunks > _MAX_CHUNKS_PER_REQUEST:
              await log_read("full_stream_clamped", {
                  "requested_chunks": requested_chunks,
                  "clamped_to": _MAX_CHUNKS_PER_REQUEST,
                  "reason": "resource_limit"
              })

tests:
  - test_full_stream_respects_limit:
      setup: File with 20K lines (100 chunks)
      call: read_file(mode="full_stream", max_chunks=1000)
      expect: Returns 50 chunks, logs clamp warning

  - test_full_stream_under_limit:
      setup: File with 1K lines (5 chunks)
      call: read_file(mode="full_stream", max_chunks=10)
      expect: Returns 5 chunks, no warning

migration: |
  Breaking for callers requesting >50 chunks, but those are DoS vectors.
  Log warning so callers know request was clamped.
```

---

### SPEC-READ-004: Centralize Encoding Fallback Logic
```yaml
spec_id: SPEC-READ-004
title: Centralize encoding fallback logic
priority: LOW
type: refactoring
file: tools/read_file.py
lines: [162-166, 261, 347, 386]

problem: |
  UTF-8 → latin-1 fallback duplicated in 4 functions.
  Adding UTF-16 support requires changing 4 locations.

solution:
  step_1:
    description: Create shared decode function
    changes:
      - file: tools/read_file.py
        lines: [70-80]
        add_function: |
          def _decode_with_fallback(
              data: bytes,
              primary: str = "utf-8",
              fallback: str = "latin-1"
          ) -> str:
              """Decode bytes with fallback on UnicodeDecodeError."""
              try:
                  return data.decode(primary)
              except UnicodeDecodeError:
                  return data.decode(fallback, errors="replace")

  step_2:
    description: Replace _scan_file encoding detection
    changes:
      - file: tools/read_file.py
        lines: [161-166]
        old: |
          encoding = "utf-8"
          try:
              sample.decode("utf-8")
              encoding = "utf-8"
          except UnicodeDecodeError:
              encoding = "latin-1"
        new: |
          # Detect encoding from sample
          try:
              sample.decode("utf-8")
              encoding = "utf-8"
          except UnicodeDecodeError:
              encoding = "latin-1"
          # Note: Keep detection separate - this determines encoding for file

  step_3:
    description: Replace chunk decode
    changes:
      - file: tools/read_file.py
        line: 261
        old: 'text = b"".join(segments).decode(encoding, errors="replace")'
        new: 'text = _decode_with_fallback(b"".join(segments), encoding, "latin-1")'

  step_4:
    description: Replace line_range decode
    changes:
      - file: tools/read_file.py
        line: 347
        old: '"content": b"".join(matched).decode(encoding, errors="replace")'
        new: '"content": _decode_with_fallback(b"".join(matched), encoding, "latin-1")'

  step_5:
    description: Replace search decode
    changes:
      - file: tools/read_file.py
        line: 386
        old: 'line = raw_line.decode(encoding, errors="replace")'
        new: 'line = _decode_with_fallback(raw_line, encoding, "latin-1")'

tests:
  - test_decode_fallback_consistency:
      setup: File with mixed UTF-8 and binary content
      call: |
        scan = _scan_file(path)
        chunks = list(_iter_chunks(path, scan["encoding"]))
        range_result = _extract_line_range(path, scan["encoding"], 1, 10)
      expect: All decoding uses same fallback logic

migration: |
  Internal refactoring - no API changes
```

---

### SPEC-READ-005: Evaluate Mode Composition (Research Question)
```yaml
spec_id: SPEC-READ-005
title: Evaluate mode composition vs proliferation
priority: LOW
type: architectural_research
file: tools/read_file.py
lines: [459-788]

problem: |
  6 read modes create large API surface.
  Some modes are composites: page = line_range + arithmetic, full_stream = chunk + iteration.

research_questions:
  - Can page mode be eliminated in favor of page_number param on line_range?
  - Can full_stream be eliminated in favor of chunk mode with start/count params?
  - Would this reduce API complexity without losing functionality?
  - What are migration costs for existing callers?

proposed_api:
  # Current: 6 modes
  read_file(mode="scan_only")
  read_file(mode="chunk", chunk_index=[0, 1, 2])
  read_file(mode="line_range", start_line=1, end_line=100)
  read_file(mode="page", page_number=1, page_size=50)
  read_file(mode="full_stream", start_chunk=0, max_chunks=5)
  read_file(mode="search", search="pattern")
  read_file(mode="search", query="Phase 2.*Storage.*State")  # query alias (smart inference)

  # Proposed: 4 modes with composable params
  read_file(mode="scan")  # Renamed for clarity
  read_file(mode="chunk", chunks=[0, 1, 2])  # OR start=0, count=3
  read_file(mode="lines", start=1, end=100)  # OR page=1, page_size=50
  read_file(mode="search", pattern="...", ...)

trade_offs:
  benefits:
    - Smaller API surface (4 modes vs 6)
    - Clearer composition (pagination as param, not mode)
    - Fewer code paths to maintain

  costs:
    - Breaking change for existing callers
    - Migration burden (search/replace all call sites)
    - Risk of regression bugs

decision: |
  Phase 6 architectural decision - NOT a Phase 5 implementation task.
  This spec documents the research question for future consideration.

next_steps: |
  1. Survey all read_file callers across codebase
  2. Measure usage distribution (which modes are most used?)
  3. Design migration path if composition is chosen
  4. Decide in Phase 6 after full audit complete
```

---

## 9. Cross-Cutting Concerns Update

Now updating `wiki/analysis/cross_cutting_concerns.md`:
