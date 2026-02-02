---
id: query_enhancement_suite-research-scribe-search-20260202
title: "\U0001F52C Research Scribe Search 20260202 \u2014 query_enhancement_suite"
doc_name: RESEARCH_SCRIBE_SEARCH_20260202
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

# 🔬 Research Scribe Search 20260202 — query_enhancement_suite
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-02 04:00:43 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Investigate why `scribe.search` returned 794,137 characters for a simple search (`def parse_log_line`) despite declaring limits of `max_total_matches=200`, `max_files=100`, and `max_matches_per_file=50`.

**Key Takeaways:**
- **ROOT CAUSE:** Limits count MATCHES (number of results), not OUTPUT SIZE (bytes generated)
- **Search loop limits ARE enforced correctly** - tool stops at 200 total matches as designed
- **Problem:** Each match can include very long lines (4KB+) plus context_before/context_after
- **Math:** 200 matches × ~4KB average per match = ~800KB output (matches observed 794KB)
- **No pagination support** - all results returned in single response
- **No output size truncation** - formatting layer has zero size-aware limits
- **Severity:** HIGH - tool unusable for common patterns, crashes Claude Code output display
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-ScribeSearch

**Investigation Window:** 2026-02-02 (single session)

**Focus Areas:**
- [x] Locate and analyze `scribe.search` tool implementation (tools/search.py)
- [x] Trace search loop and limit enforcement logic
- [x] Examine per-file match collection (_search_file, _search_file_multiline)
- [x] Analyze result structuring (_build_structured_result)
- [x] Investigate readable formatting pipeline (_format_search_readable)
- [x] Check MCP response wrapping (finalize_tool_response)
- [x] Identify gaps in pagination support
- [x] Assess output size control mechanisms

**Dependencies & Constraints:**
- Tool signature declares limits but doesn't document WHAT is limited (count vs size)
- No existing pagination infrastructure in search tool
- ResponseFormatter pipeline is generic (no tool-specific size limits)
- MCP TextContent wrapping has no size constraints
<!-- ID: findings -->
Detail each major finding with evidence and confidence levels.

### Finding 1: Search Loop Limits Work Correctly (HIGH CONFIDENCE)
- **Summary:** The search loop in `tools/search.py` (lines 665-707) correctly enforces all declared limits
- **Evidence:**
  - Line 680-683: Breaks when `max_total_matches - total_matches <= 0` ✅
  - Line 685: Calculates `per_file_limit = min(max_matches_per_file, remaining)` ✅
  - Line 706-707: Breaks when `len(results) >= max_files` ✅
  - All three limits (`max_total_matches=200`, `max_matches_per_file=50`, `max_files=100`) are enforced
- **Confidence:** 100% (verified by direct code inspection)

### Finding 2: Per-Match Content Size Is Unbounded (HIGH CONFIDENCE)
- **Summary:** Each Match object stores full line content regardless of line length
- **Evidence:**
  - `_search_file()` lines 316-321: Creates `Match(line_number=..., line=all_lines[idx].rstrip(), ...)`
  - No truncation of `line` content - can be megabytes for minified JS, logs, etc.
  - Context arrays (`context_before`, `context_after`) also store full lines
  - Example: Single 100KB minified line × 200 matches = 20MB output despite "200 match limit"
- **Confidence:** 95% (code verified, math extrapolated)

### Finding 3: No Pagination Support (HIGH CONFIDENCE)
- **Summary:** Search tool returns ALL results in single response - no page/offset parameters
- **Evidence:**
  - Tool signature (lines 532-568): No `page`, `page_size`, or `offset` parameters
  - Compare to `query_entries` (tools/query_entries.py): Has `page=1, page_size=10` with PaginationInfo
  - All collected matches passed to `_build_structured_result` without pagination metadata
  - Response structure has no "page X of Y" or "next_page" fields
- **Confidence:** 100% (absence verified)

### Finding 4: Formatting Layer Has No Size Limits (HIGH CONFIDENCE)
- **Summary:** `_format_search_readable()` iterates ALL matches with no output size budget
- **Evidence:**
  - Lines 478-508: `for file_block in data.get("matches", []):` loops every match
  - Each match renders as: `line_number: full_line_content` plus context lines
  - No character count tracking or truncation
  - No "showing X of Y matches, use pagination" message
  - Formatter assumes limits already handled (they are, but count ≠ size)
- **Confidence:** 95% (code verified, could be edge cases)

### Finding 5: MCP Response Wrapping Has No Size Controls (MEDIUM CONFIDENCE)
- **Summary:** `finalize_tool_response()` wraps readable_content in TextContent without size checks
- **Evidence:**
  - `utils/formatters/dispatcher.py` line 278-279: `CallToolResult(content=[TextContent(type="text", text=readable_content)])`
  - No size validation before wrapping
  - MCP protocol may have limits, but not enforced at application layer
  - Claude Code crashes when TextContent exceeds display buffer (~1MB?)
- **Confidence:** 75% (MCP protocol limits unclear, Claude Code behavior observed not spec'd)

### Finding 6: Output Mode Doesn't Help (MEDIUM CONFIDENCE)
- **Summary:** `output_mode="files_with_matches"` and `"count"` are more compact but still unbounded
- **Evidence:**
  - `files_with_matches`: Returns file paths only - safe for most queries ✅
  - `count`: Returns `{file: path, count: N}` per file - also safe ✅
  - `content` (default): Full match rendering - unsafe for large result sets ❌
  - Users expect `content` mode for seeing matches, but it's the broken mode
- **Confidence:** 70% (alternative modes work but don't solve UX problem)

### Additional Notes
- **Similar Issue in query_entries:** May have same match-count vs output-size confusion (separate research doc)
- **Workaround Exists:** Users can use `output_mode="files_with_matches"` then read specific files
- **User Expectation:** Declaring `max_total_matches=200` implies "reasonable output size" but delivers 800KB+
- **Documentation Gap:** Tool docstring doesn't explain limits are match COUNT not output SIZE
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

1. **Search Execution Flow:**
   ```
   tools/search.py::search() [line 532]
   ├─ _iterate_files() → yields Path objects [line 656]
   ├─ For each file:
   │  ├─ _search_file() or _search_file_multiline() → List[Match] [lines 272, 326]
   │  └─ Accumulates FileResult objects [line 702]
   ├─ _build_structured_result() → Dict[str, Any] [line 710]
   ├─ _format_search_readable() → str [line 743]
   └─ finalize_tool_response() → CallToolResult [line 745]
   ```

2. **Match Object Structure (lines 115-121):**
   ```python
   @dataclass
   class Match:
       line_number: int
       line: str  # ⚠️ UNBOUNDED - can be megabytes
       context_before: List[str] = field(default_factory=list)  # ⚠️ UNBOUNDED per line
       context_after: List[str] = field(default_factory=list)   # ⚠️ UNBOUNDED per line
   ```

3. **Limit Enforcement (lines 680-707):**
   - ✅ **Match count limit:** `if remaining <= 0: break`
   - ✅ **Per-file limit:** `per_file_limit = min(max_matches_per_file, remaining)`
   - ✅ **File count limit:** `if len(results) >= max_files: break`
   - ❌ **Output size limit:** None - not checked anywhere

**System Interactions:**

- **File I/O:** `Path.read_text()` loads entire file into memory (line 284) - safe because of `max_file_size_mb` limit
- **Pattern Matching:** Python `re` module via `compiled_pattern.search(line)` (line 294)
- **Response Formatting:** Delegates to `ResponseFormatter.finalize_tool_response()` (utils/response.py → utils/formatters/dispatcher.py)
- **MCP Protocol:** Returns `CallToolResult` with `TextContent` - no size validation before serialization

**Risk Assessment:**

- [x] **CRITICAL:** Common search patterns (function names, imports) can produce 50-200 matches with long lines
- [x] **HIGH:** Minified JavaScript/CSS files have 100KB+ lines - single file can produce multi-megabyte output
- [x] **HIGH:** Log files with stack traces can have 1KB+ lines - 200 matches = 200KB+ minimum
- [x] **MEDIUM:** Context lines multiply output size - `context_lines=5` means 11 lines per match (1 + 5 + 5)
- [x] **LOW:** Alternative output modes (`files_with_matches`, `count`) work but don't solve core UX issue

**Performance Characteristics:**

- **Time Complexity:** O(files × lines) - acceptable, uses file traversal + regex
- **Space Complexity:** O(matches × avg_line_length) - **UNBOUNDED** - can OOM or crash client
- **Network:** MCP JSON-RPC response can be multi-megabyte - exceeds typical protocol buffers
<!-- ID: recommendations -->
### Immediate Next Steps

**OPTION A: Add Pagination Support (RECOMMENDED - matches query_entries pattern)**

- [ ] Add pagination parameters to tool signature:
  - `page: int = 1`
  - `page_size: int = 10` (default 10 matches, not 200!)
  - `offset: int = 0` (alternative to page)
- [ ] Modify search loop to paginate match collection, not files:
  - Collect ALL matches (up to max_total_matches=200 hard ceiling)
  - Slice results: `paginated = all_matches[(page-1)*page_size : page*page_size]`
  - Include PaginationInfo in response: `{page: 1, page_size: 10, total_matches: 143, total_pages: 15}`
- [ ] Update `_format_search_readable()` to show pagination metadata:
  - "Showing matches 1-10 of 143 (page 1/15)"
  - "Use page=2 to see next 10 matches"
- [ ] Add pagination to structured response (following query_entries pattern)
- [ ] Update tool docstring to document pagination behavior
- [ ] **Estimated effort:** 4-6 hours (following existing query_entries implementation)

**OPTION B: Add Per-Line Truncation (QUICK FIX - band-aid solution)**

- [ ] Truncate long lines in Match object creation:
  ```python
  MAX_LINE_LENGTH = 500  # characters
  line_truncated = line[:MAX_LINE_LENGTH] + "..." if len(line) > MAX_LINE_LENGTH else line
  ```
- [ ] Apply to match line AND context lines
- [ ] Add truncation indicator in output: `[LINE TRUNCATED - 10523 chars total]`
- [ ] **Pros:** Simple, immediate mitigation
- [ ] **Cons:** Users lose context, doesn't solve UX problem of too many results

**OPTION C: Add Output Size Budget (COMPLEX - MCP-wide solution)**

- [ ] Add `max_output_bytes` parameter (default 100KB)
- [ ] Track cumulative output size during formatting
- [ ] Truncate results when budget exceeded with clear message
- [ ] **Pros:** Solves problem for all tools
- [ ] **Cons:** Requires MCP-wide infrastructure, complex to implement correctly

**RECOMMENDED APPROACH: Option A (Pagination) + Optional B (Truncation)**

1. Implement pagination as primary solution (matches existing query_entries UX)
2. Optionally add per-line truncation as safety net (default OFF, user-configurable)
3. Document the limits clearly: "max_total_matches limits results collected, pagination controls results displayed"

### Long-Term Opportunities

**1. Unified Pagination Framework**
- Extract pagination logic from query_entries into reusable utility
- Apply to all list-returning tools (search, read_file structure mode, list_projects)
- Consistent UX: `page=1, page_size=10, format="readable"` across all tools

**2. Output Size Telemetry**
- Add response size tracking to tool_logger (already logs response_size_bytes)
- Monitor which tools produce large responses
- Alert when responses exceed thresholds (100KB warning, 1MB error)

**3. Smart Defaults Based on Pattern**
- Common patterns (function defs, imports) default to `page_size=5`
- Rare patterns default to `page_size=20`
- Learn from usage data which patterns need pagination

**4. Preview Mode**
- Add `preview=True` parameter: shows first N matches + total count
- "Found 143 matches across 12 files. Showing first 5. Use page=1 to paginate."
- Helps users refine patterns before retrieving full results

**5. Streaming Results (Advanced)**
- For very large result sets, stream matches as they're found
- MCP protocol supports streaming via multiple content blocks
- Requires protocol-level changes but provides best UX for large searches
<!-- ID: appendix -->
**References:**

- **Primary Implementation:** `tools/search.py` (749 lines)
  - Main tool: `search()` lines 532-750
  - Search loop: lines 665-707
  - Match collection: `_search_file()` lines 272-323, `_search_file_multiline()` lines 326-372
  - Result structuring: `_build_structured_result()` lines 379-437
  - Formatting: `_format_search_readable()` lines 440-525

- **Response Pipeline:** `utils/formatters/dispatcher.py`
  - Response wrapping: `finalize_tool_response()` lines 89-300
  - TextContent creation: line 278-279

- **Comparison Tool (has pagination):** `tools/query_entries.py`
  - Pagination parameters: `page=1, page_size=10`
  - PaginationInfo integration: uses `create_pagination_info()` from utils/response.py

- **Related Issue:** query_entries flat-file vs DB inconsistency (parallel research by ResearchAgent-QueryEntries)

**Code Snippets:**

**Current Match Collection (unbounded):**
```python
# tools/search.py line 316-321
matches.append(Match(
    line_number=idx + 1,
    line=all_lines[idx].rstrip(),  # ⚠️ Can be megabytes
    context_before=ctx_before,
    context_after=ctx_after,
))
```

**Proposed Pagination Integration:**
```python
# After line 707, add pagination
all_matches = results  # Full result set (up to max_total_matches)
page_start = (page - 1) * page_size
page_end = page_start + page_size
paginated_results = all_matches[page_start:page_end]

pagination_info = create_pagination_info(
    page=page,
    page_size=page_size,
    total_count=len(all_matches)
)
```

**Test Case for Validation:**

```python
# Search for common pattern that produces many results
result = search(
    agent="test",
    pattern="def ",
    path="tools/",
    page=1,
    page_size=10
)

assert result["pagination"]["total_matches"] > 10  # Found many
assert len(result["matches"]) == 10  # But only returned 10
assert result["pagination"]["total_pages"] >= 2  # Can paginate
```

**Attachments:**

- Original failure: `scribe.search(pattern="def parse_log_line")` → 794,137 characters
- Expected: ~10KB for 10 paginated results
- Current: 800KB for 200 unpaginated results with long lines
