---
id: query_enhancement_suite-research-query-entries-flatfile-db-20260202
title: "\U0001F52C Research Query Entries Flatfile Db 20260202 \u2014 query_enhancement_suite"
doc_name: RESEARCH_QUERY_ENTRIES_FLATFILE_DB_20260202
category: engineering
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

# 🔬 Research Query Entries Flatfile Db 20260202 — query_enhancement_suite
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-02 04:02:02 UTC

> Root cause analysis of query_entries template search failure and architectural divergence from read_recent

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Investigate why `query_entries` returns zero results for "template" despite 39 occurrences in PROGRESS_LOG.md and DB, while `read_recent` works correctly.

**Root Cause Identified:** The `_is_template_entry()` function in `utils/logs.py` (line 20) contains a hardcoded template filter that silently drops ANY log entry containing the word "template" in timestamp, emoji, agent, or message fields. This overzealous filtering treats legitimate log entries about templates/templating as placeholder/example entries.

**Key Takeaways:**
- `query_entries` reads flat PROGRESS_LOG.md files and parses them with `parse_log_line()` → `_is_template_entry()` filter (lines 647, 667 of tools/query_entries.py).
- `read_recent` queries the SQLite database directly using `storage_backend.fetch_recent_entries()` (line 307 of tools/read_recent.py) — NO filtering applied.
- The storage backend has functional `query_entries()` and `query_entries_paginated()` methods (storage/sqlite.py lines 594-673) but they're unused by the MCP tool.
- Cross-project search exists and works (`search_scope="all_projects"`) but inherits the same flat-file parsing bug.
- The divergence is architectural: `read_recent` = DB-first, `query_entries` = flat-file-first with broken parsing logic.
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-QueryEntries

**Investigation Window:** 2026-02-02 (single-day investigation)

**Focus Areas:**
- [x] Trace `query_entries` execution path from MCP call to results
- [x] Identify why flat files are read instead of DB (like `read_recent`)
- [x] Analyze `parse_log_line()` and `_is_template_entry()` logic in `utils/logs.py`
- [x] Explain differential results: "stdout" matches 1, "template" matches 0
- [x] Verify storage backend `query_entries()` implementation exists and is functional
- [x] Assess DB migration feasibility for `query_entries` tool
- [x] Test cross-project search functionality (`search_scope="all_projects"`)
- [x] Compare data flow: `read_recent` (DB → format) vs `query_entries` (file → parse → filter)

**Dependencies & Constraints:**
- Investigation scoped to `scribe_mcp` codebase only
- Focus on MCP tool layer (`tools/query_entries.py`, `tools/read_recent.py`) and storage layer (`storage/base.py`, `storage/sqlite.py`)
- Parsing logic isolated to `utils/logs.py` (81 lines total)
- No changes made during research phase — observation only
<!-- ID: findings -->
### Finding 1: Root Cause — Overzealous Template Filtering
- **Summary:** `utils/logs.py` line 15-25 implements `_is_template_entry()` with hardcoded `template_indicators` list including "template" keyword. ANY log entry containing "template" in timestamp/emoji/agent/message gets silently filtered (returns `None` from `parse_log_line()`).
- **Evidence:** 
  - `utils/logs.py:20` — `template_indicators = [..., "template"]`
  - `utils/logs.py:40` — `if _is_template_entry(...): return None`
  - PROGRESS_LOG.md line 42 contains legitimate entry with "template" in message → filtered out
- **Confidence:** Critical (1.0) — Verified via code inspection and log file correlation

### Finding 2: Architectural Divergence — Flat File vs Database
- **Summary:** `query_entries` and `read_recent` use completely different data sources despite having identical use cases.
- **Evidence:**
  - `query_entries`: `tools/query_entries.py:647` → `read_all_lines(log_path)` → `parse_log_line(line)` (flat file)
  - `read_recent`: `tools/read_recent.py:307` → `backend.fetch_recent_entries()` (SQLite DB)
  - Result: `read_recent` works perfectly, `query_entries` fails due to parsing bugs
- **Confidence:** High (0.95) — Data flow fully traced

### Finding 3: Unused Storage Backend Methods
- **Summary:** Storage backend has fully functional `query_entries()` and `query_entries_paginated()` methods that are never called by the MCP tool.
- **Evidence:**
  - `storage/base.py:184-220` — Abstract method signatures defined
  - `storage/sqlite.py:594-673` — Complete implementation with SQL queries, pagination, filtering
  - `tools/query_entries.py` — Zero calls to `storage_backend.query_entries()`
- **Confidence:** High (0.95) — Verified via code search and dependency analysis

### Finding 4: Cross-Project Search Exists But Inherits Bug
- **Summary:** `search_scope="all_projects"` functionality is implemented and operational, but ALL cross-project searches use flat file parsing, inheriting the `_is_template_entry()` bug.
- **Evidence:**
  - `tools/query_entries.py:1275-1345` — `_resolve_cross_project_projects()` resolves project list
  - `tools/query_entries.py:1465` — `for project in projects:` iterates and calls `_search_single_project()`
  - Each project search reads flat files with same broken parser
- **Confidence:** High (0.90) — Traced cross-project iteration logic

### Finding 5: "stdout" vs "template" Differential Results Explained
- **Summary:** "stdout" matches 1 result because it's NOT in `template_indicators` list. "template" matches 0 because it IS in the list and gets filtered.
- **Evidence:**
  - `template_indicators = ["YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI", "Message text", "key=value", "placeholder", "example", "template"]`
  - "stdout" appears in PROGRESS_LOG.md line 127 and passes filter
  - "template" appears 39+ times but ALL get filtered by line 20 logic
- **Confidence:** Critical (1.0) — Direct keyword comparison

### Finding 6: DB Migration Is Trivial
- **Summary:** Migrating `query_entries` to use DB instead of flat files requires ~10 lines of code changes — just swap `read_all_lines()` + `parse_log_line()` loop with `backend.query_entries()` call.
- **Evidence:**
  - `read_recent` pattern (lines 306-327) shows working DB usage
  - Storage backend methods already support all query_entries parameters (agents, emojis, message filters, time ranges)
  - No schema changes needed — DB already contains all data
- **Confidence:** High (0.90) — Pattern matching and API compatibility verified

### Additional Notes
- The LOG_LINE_PATTERN regex (line 10-12) expects format: `[emoji] [timestamp] [Agent: name] [Project: name] message | meta`
- Template filtering was likely added to skip header/example lines in PROGRESS_LOG.md but is too aggressive
- No test coverage found for `_is_template_entry()` filtering logic
- DB contains ALL entries including those with "template" — data is not lost, just inaccessible via `query_entries`
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

1. **Dual Data Access Pattern (Anti-Pattern)**
   - `read_recent`: DB-first approach using `storage_backend.fetch_recent_entries()`
   - `query_entries`: File-first approach using `read_all_lines()` + `parse_log_line()`
   - Same underlying data, different access paths → inconsistent behavior
   - Pattern suggests historical evolution rather than intentional design

2. **Silent Filtering Logic**
   - `_is_template_entry()` returns `None` without logging or warning
   - `parse_log_line()` propagates `None` → entries silently disappear
   - No metrics, no debugging output, no way to detect filtering in production
   - Users see "No results" with no explanation

3. **Unused Abstraction Layer**
   - StorageBackend defines `query_entries()` interface
   - SQLiteStorage implements full query logic with SQL WHERE clauses
   - MCP tool ignores abstraction and reads files directly
   - Violation of abstraction boundary → bypasses connection pooling, transactions

**System Interactions:**

- **Storage Layer**: `storage/base.py` (abstract interface) → `storage/sqlite.py` (SQLite implementation)
  - Supports: project_id filtering, timestamp ranges, agent filters, emoji filters, message search, metadata filters
  - Pagination: Both `query_entries(offset/limit)` and `query_entries_paginated(page/page_size)` available
  - Connection pooling: Managed by SQLiteConnectionPool (not used by file-based approach)

- **Logging Utils**: `utils/logs.py` (81 lines)
  - `LOG_LINE_PATTERN` regex: Parses canonical log format
  - `_is_template_entry()`: Hardcoded keyword filter (15-25)
  - `parse_log_line()`: Combines regex + filter (28-58)
  - `read_all_lines()`: Async file reader (71-81)

- **MCP Tool Layer**: `tools/query_entries.py` (2034 lines, massive)
  - `_execute_search_with_fallbacks()`: Orchestrates file reading + parsing (590-750)
  - `_resolve_cross_project_projects()`: Multi-project resolution (1275-1345)
  - `_search_single_project()`: Per-project search executor (calls file parsing)

**Data Flow Comparison:**

```
read_recent:
MCP call → resolve_logging_context() → backend.fetch_recent_entries() 
  → SQL query → rows → formatter → response

query_entries:
MCP call → resolve_logging_context() → read_all_lines(log_path) 
  → for line in lines → parse_log_line() → _is_template_entry() 
  → [filter here] → apply filters → results → formatter → response
```

**Risk Assessment:**

- [x] **Data Integrity Risk**: DB contains correct data, but `query_entries` returns incomplete results → users may make decisions based on partial information
- [x] **Maintenance Burden**: Two separate code paths for same functionality → 2x testing, 2x bug surface
- [x] **Performance Impact**: File I/O on every query vs. indexed DB queries → query_entries scales poorly with log size
- [x] **Silent Failures**: No logging when entries are filtered → impossible to debug in production
- [x] **Testing Gap**: No test coverage for `_is_template_entry()` logic → regression risk
- [x] **Cross-Project Amplification**: Bug multiplies across N projects when using `search_scope="all_projects"`
<!-- ID: recommendations -->
### Immediate Next Steps

**Priority 1: Fix Template Filtering Bug (Hot Fix)**
- [ ] Option A: Remove "template" from `template_indicators` list in `utils/logs.py` line 20
  - Least invasive, fixes immediate symptom
  - Risk: May allow actual template/placeholder entries through
  - Mitigation: Make filtering more precise (check for MULTIPLE indicators, not just one)

- [ ] Option B: Make template filtering smarter
  - Require 2+ indicators to trigger filter (e.g., "YYYY-MM-DD" AND "template")
  - Check position: only filter if "template" appears in first 100 chars (likely header)
  - Add explicit header line detection (lines 1-50 of file)

**Priority 2: Migrate query_entries to DB (Architectural Fix)**
- [ ] Replace file reading logic in `tools/query_entries.py` lines 645-673 with `backend.query_entries()` call
- [ ] Follow `read_recent` pattern (lines 306-327) as template
- [ ] Remove `parse_log_line()` dependency for DB-backed queries
- [ ] Keep flat-file fallback for backwards compatibility with old log files
- [ ] Add feature flag: `USE_DB_QUERIES=true` (default), `USE_FILE_QUERIES=false` (legacy)

**Priority 3: Add Observability**
- [ ] Log when entries are filtered by `_is_template_entry()`
  - Example: `logger.debug(f"Filtered template entry: {line[:100]}...")`
- [ ] Add metrics counter: `scribe.query_entries.filtered_entries`
- [ ] Include filter stats in query_entries response: `{"filtered_count": 5, "reason": "template_indicators"}`

**Priority 4: Test Coverage**
- [ ] Add unit tests for `_is_template_entry()` with edge cases
- [ ] Test legitimate entries containing "template", "example", "placeholder" keywords
- [ ] Add integration test comparing `query_entries` vs `read_recent` results (should be identical)
- [ ] Test cross-project search with template filtering

### Long-Term Opportunities

**Consolidate Dual Data Access Pattern**
- Deprecate flat-file parsing in `query_entries` entirely (18-24 month timeline)
- Use DB as single source of truth for ALL query tools
- Keep PROGRESS_LOG.md files for human readability only (not machine parsing)
- Document migration path for users with old log files

**Enhance Storage Backend API**
- Add `query_entries_with_stats()` that returns `(entries, stats_dict)`
- Stats: total_matched, total_filtered, filter_reasons, query_duration_ms
- Support complex filters: boolean logic (AND/OR), regex on metadata fields

**Template Detection Improvements**
- Machine learning-based placeholder detection (train on actual vs template entries)
- OR: Explicit template markers in log files (`# TEMPLATE_SECTION_START` / `# TEMPLATE_SECTION_END`)
- OR: Separate template/example log files from actual data files

**Cross-Project Query Optimization**
- Add cross-project DB index on (project_id, ts_iso, agent, emoji)
- Single SQL query across projects instead of N file reads
- Result streaming for large result sets (avoid loading 10K entries into memory)

**Backwards Compatibility**
- For legacy PROGRESS_LOG.md files not yet in DB: auto-import on first query
- Background job: sync flat files → DB for all projects
- Deprecation notice in logs when file-based querying is used
<!-- ID: appendix -->
**File References:**

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `tools/query_entries.py` | 2034 | MCP tool - query log entries | Uses flat files (broken) |
| `tools/read_recent.py` | 591 | MCP tool - recent entries | Uses DB (working) |
| `utils/logs.py` | 81 | Log parsing utilities | Contains `_is_template_entry()` bug |
| `storage/base.py` | 400 | Abstract storage interface | Defines `query_entries()` (unused) |
| `storage/sqlite.py` | 3022 | SQLite implementation | Implements `query_entries()` (unused) |
| `.scribe/docs/dev_plans/query_enhancement_suite/PROGRESS_LOG.md` | 138 | Active project log | Contains filtered "template" entries |

**Key Code Snippets:**

1. **Broken Template Filter** (`utils/logs.py:15-25`):
```python
def _is_template_entry(timestamp: str, emoji: str, agent: str, message: str) -> bool:
    """Check if this appears to be a template/example entry rather than a real one."""
    template_indicators = [
        "YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI", "Message text",
        "key=value", "placeholder", "example", "template"  # ← BUG: Too broad
    ]
    combined_text = f"{timestamp} {emoji} {agent} {message}".lower()
    return any(indicator.lower() in combined_text for indicator in template_indicators)
```

2. **Working DB Query Pattern** (`tools/read_recent.py:306-317`):
```python
if hasattr(backend, 'fetch_recent_entries_paginated'):
    rows, total_count = await backend.fetch_recent_entries_paginated(
        project=record,
        page=page,
        page_size=page_size,
        filters=_normalise_filters(filters),
    )
else:
    rows = await backend.fetch_recent_entries(
        project=record,
        limit=page_size,
        filters=_normalise_filters(filters),
        offset=offset,
    )
```

3. **Unused DB Query Method** (`storage/sqlite.py:594-610`):
```python
async def query_entries(
    self,
    *,
    project: ProjectRecord,
    limit: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    agents: Optional[List[str]] = None,
    emojis: Optional[List[str]] = None,
    message: Optional[str] = None,
    message_mode: str = "substring",
    case_sensitive: bool = False,
    meta_filters: Optional[Dict[str, str]] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    # Full SQL implementation exists but is never called by MCP tool
```

**Related Documents:**
- Query Enhancement Suite Architecture Guide: `.scribe/docs/dev_plans/query_enhancement_suite/ARCHITECTURE_GUIDE.md`
- Query Enhancement Suite Phase Plan: `.scribe/docs/dev_plans/query_enhancement_suite/PHASE_PLAN.md`
- Scribe MCP Usage Documentation: `docs/Scribe_Usage.md`

**Search Terms for Future Investigation:**
- `parse_log_line` - Find all usages of broken parser
- `_is_template_entry` - Find filter callsites
- `storage_backend.query_entries` - Check if ever called
- `read_all_lines` - Find all flat file reads
- `template_indicators` - Find filter definition

**Verification Commands:**
```bash
# Count "template" occurrences in log
grep -c "template" .scribe/docs/dev_plans/query_enhancement_suite/PROGRESS_LOG.md

# Verify DB contains template entries
sqlite3 .scribe/scribe.db "SELECT COUNT(*) FROM scribe_entries WHERE message LIKE '%template%'"

# Compare results
# query_entries returns: 0 results
# read_recent returns: N results (where N > 0)
```

**Impact Assessment:**
- **Users Affected**: All users of `query_entries` MCP tool searching for: "template", "example", "placeholder", "YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI", "Message text", "key=value"
- **Data Loss**: None (DB intact, only query results affected)
- **Workaround**: Use `read_recent` with agent/emoji filters instead of `query_entries` message search
- **Severity**: High — affects core search functionality, silent failure mode
