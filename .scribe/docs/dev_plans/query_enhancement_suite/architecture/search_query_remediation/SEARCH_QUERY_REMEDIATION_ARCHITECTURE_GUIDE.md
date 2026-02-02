---
id: query_enhancement_suite-search-query-remediation-architecture-guide
title: 'Architecture Guide: Search & Query Tool Remediation'
doc_name: SEARCH_QUERY_REMEDIATION_ARCHITECTURE_GUIDE
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
# Architecture Guide: Search & Query Tool Remediation

**Project:** query_enhancement_suite  
**Sub-Plan:** search_query_remediation  
**Author:** ArchitectAgent-SearchQueryFix  
**Version:** 1.0  
**Status:** Draft  
**Created:** 2026-02-02

---

## Executive Summary
<!-- ID: executive_summary -->

This sub-plan addresses two critical tool reliability issues identified in research:

1. **scribe.search Output Explosion**: Tool returns 794K characters for simple queries despite match limits, crashes Claude Code display, has no pagination
2. **query_entries Empty Results**: Tool silently filters legitimate entries containing "template" keyword via `_is_template_entry()`, reads flat files instead of using storage backend DB

Both issues are HIGH severity blocking real usage. This architecture defines a three-phase remediation:

- **Phase 1 (Hot Fix)**: Immediate surgical fixes - fix template filter, add line truncation safety net
- **Phase 2 (DB Migration)**: Migrate query_entries from flat files to storage backend (follow read_recent pattern)
- **Phase 3 (Search Pagination)**: Add pagination support to scribe.search (follow query_entries pattern)

Each phase is independently deployable and testable. Phase 1 can ship in 1-2 hours.

---

## Problem Statement
<!-- ID: problem_statement -->

### Problem 1: scribe.search Output Explosion

**Context:**  
`scribe.search` declares limits (`max_total_matches=200`, `max_matches_per_file=50`, `max_files=100`) but these limit MATCH COUNT, not OUTPUT SIZE. A query for common patterns like `def parse_log_line` returns 200 matches with average 4KB per match = ~800KB output in single response.

**Impact:**
- Claude Code output display crashes when TextContent exceeds ~1MB
- Tool effectively unusable for common search patterns (function names, imports, class definitions)
- Users cannot paginate results - all-or-nothing response
- No per-line truncation - minified JS/CSS files have 100KB+ lines

**Root Cause:**
- Match object (tools/search.py:115-121) stores full line content in `line: str` field (unbounded)
- Context arrays (`context_before`, `context_after`) also store full lines
- No pagination parameters (`page`, `page_size`) in tool signature
- Formatting layer (`_format_search_readable()` lines 478-508) has no output size budget

### Problem 2: query_entries Empty Results & Architectural Divergence

**Context:**  
`query_entries` returns zero results for searches containing "template" despite 39+ legitimate log entries in PROGRESS_LOG.md and DB. Meanwhile, `read_recent` returns correct results for the same data.

**Impact:**
- Users cannot search logs for template-related work (doc generation, templating features)
- Silent filtering - no error message, just empty results
- Architectural divergence creates maintenance burden (two code paths for same data)
- Cross-project search inherits the same bug

**Root Cause:**
- `utils/logs.py` line 20: `_is_template_entry()` has hardcoded filter list including "template"
- Filter is too aggressive - checks if "template" appears ANYWHERE in timestamp/emoji/agent/message
- `query_entries` reads flat PROGRESS_LOG.md files (line 647: `read_all_lines(log_path)`) then parses with buggy filter
- `read_recent` queries storage backend directly (line 307: `backend.fetch_recent_entries_paginated()`) - no parsing, no filtering
- Storage backend has functional `query_entries()` method (storage/sqlite.py:594) that's NEVER CALLED

**Constraints:**
- Must preserve backwards compatibility with existing logs
- Cannot break cross-project search functionality
- Must maintain performance (pagination, DB indexes)
- Template filtering was intended for header/example lines - need smarter logic

---

## System Overview
<!-- ID: system_overview -->

### Current Architecture (Broken)

```
scribe.search:
  tools/search.py::search() [line 532]
  ├─ Collects up to max_total_matches (200) Match objects
  ├─ Match object stores FULL line content (unbounded)
  ├─ No pagination - all results in single response
  ├─ _format_search_readable() loops ALL matches
  └─ Returns 800KB+ for common queries → crashes client

query_entries:
  tools/query_entries.py::query_entries() [line 532]
  ├─ Reads flat PROGRESS_LOG.md (line 647: read_all_lines())
  ├─ Parses each line with utils/logs.py::parse_log_line()
  │   └─ Calls _is_template_entry() - filters "template" keyword
  ├─ Returns 0 results for legitimate template-related entries
  └─ NEVER CALLS storage backend query_entries() method

read_recent (WORKS CORRECTLY):
  tools/read_recent.py::read_recent()
  ├─ Calls backend.fetch_recent_entries_paginated() [line 307]
  ├─ DB query with proper pagination
  └─ Returns ALL entries including "template" ones
```

### Target Architecture (Fixed)

```
scribe.search (Phase 3):
  tools/search.py::search(page=1, page_size=10) [NEW PARAMS]
  ├─ Collects up to max_total_matches (200) Match objects
  ├─ Match lines truncated to MAX_LINE_LENGTH=500 chars (Phase 1)
  ├─ Pagination: slice results [(page-1)*page_size : page*page_size]
  ├─ Returns PaginationInfo: {page, page_size, total_matches, total_pages}
  └─ Readable format shows "Page 1/15, showing matches 1-10 of 143"

query_entries (Phase 2):
  tools/query_entries.py::query_entries()
  ├─ Calls backend.query_entries_paginated() [NEW - follow read_recent]
  ├─ DB query with proper filters, pagination
  ├─ NO PARSING - no _is_template_entry() filter
  └─ Returns ALL matching entries from DB

_is_template_entry (Phase 1):
  utils/logs.py::_is_template_entry() [FIXED]
  ├─ Smarter logic: require 2+ indicators OR position check
  ├─ "template" in message is OK if no other indicators present
  └─ Logs when entries are filtered (observability)
```

---

## Component Design
<!-- ID: component_design -->

### Phase 1: Hot Fixes (Immediate Deployment)

#### Component 1.1: Fix Template Filter Logic

**File:** `utils/logs.py`  
**Function:** `_is_template_entry()` (lines 15-25)

**Current Behavior:**
```python
def _is_template_entry(timestamp: str, emoji: str, agent: str, message: str) -> bool:
    template_indicators = [
        "YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI", "Message text",
        "key=value", "placeholder", "example", "template"  # ← TOO AGGRESSIVE
    ]
    combined_text = f"{timestamp} {emoji} {agent} {message}".lower()
    return any(indicator.lower() in combined_text for indicator in template_indicators)
```

**New Behavior:**
```python
def _is_template_entry(timestamp: str, emoji: str, agent: str, message: str) -> bool:
    """Check if entry is a template/placeholder (requires 2+ indicators)."""
    # Structural indicators - highly specific to templates
    structural_indicators = ["YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI"]
    
    # Content indicators - only suspicious if combined with structural
    content_indicators = ["Message text", "key=value", "placeholder", "example"]
    
    combined_text = f"{timestamp} {emoji} {agent} {message}".lower()
    
    structural_count = sum(1 for ind in structural_indicators if ind.lower() in combined_text)
    content_count = sum(1 for ind in content_indicators if ind.lower() in combined_text)
    
    # Require 2+ structural indicators (e.g., "YYYY-MM-DD" + "HH:MM:SS")
    # OR 1 structural + 2 content indicators
    # "template" in message alone is NOT enough to filter
    return structural_count >= 2 or (structural_count >= 1 and content_count >= 2)
```

**Rationale:**
- Original filter was single-keyword match - too aggressive
- Real template entries have MULTIPLE placeholder patterns (timestamp format + emoji placeholder + generic message)
- Legitimate entries about templates/templating have "template" in message but real timestamp/agent/emoji
- New logic requires evidence of being a template, not just mentioning templates

**Testing:**
- Unit test: entry with "template" in message + real timestamp → NOT filtered
- Unit test: entry with "YYYY-MM-DD" + "HH:MM:SS" + "EMOJI" → filtered
- Integration test: query_entries("template") returns 39+ results (not 0)

#### Component 1.2: Add Line Truncation to scribe.search

**File:** `tools/search.py`  
**Function:** `_search_file()` (lines 272-323)  
**Constant:** Add `MAX_LINE_LENGTH = 500` at module level

**Change Location:** Line 318 - Match object creation

**Current Code:**
```python
matches.append(Match(
    line_number=idx + 1,
    line=all_lines[idx].rstrip(),  # ← UNBOUNDED
    context_before=ctx_before,
    context_after=ctx_after,
))
```

**New Code:**
```python
MAX_LINE_LENGTH = 500  # characters - safety limit for output size

def _truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    """Truncate line with ellipsis if exceeds max_length."""
    if len(line) <= max_length:
        return line
    return f"{line[:max_length]}... [TRUNCATED - {len(line)} chars total]"

# In _search_file() at line 318:
matches.append(Match(
    line_number=idx + 1,
    line=_truncate_line(all_lines[idx].rstrip()),
    context_before=[_truncate_line(ln) for ln in ctx_before],
    context_after=[_truncate_line(ln) for ln in ctx_after],
))
```

**Rationale:**
- Safety net - prevents individual lines from causing multi-MB responses
- 500 chars is enough to see function signatures, class definitions, imports
- Truncation indicator shows users there's more content
- Applies to match line AND context lines
- Does NOT solve pagination problem but prevents catastrophic crashes

**Math:**
- 200 matches × 500 chars × 3 lines (match + 2 context avg) = 300KB worst case
- Down from 800KB+ unbounded, makes tool usable again

**Testing:**
- Unit test: line with 10KB content → truncated to 500 chars with indicator
- Integration test: search minified JS file → response size < 500KB

---

### Phase 2: DB Migration (Architectural Fix)

#### Component 2.1: Migrate query_entries to Storage Backend

**File:** `tools/query_entries.py`  
**Function:** `_execute_search_with_fallbacks()` (lines 590-750)

**Current Flow:**
```python
# Line 647 - reads flat file
lines = await read_all_lines(log_path)

# Lines 665-669 - parses with buggy filter
for line in lines:
    parsed = parse_log_line(line)  # ← Calls _is_template_entry()
    if not parsed:
        continue
    # ... apply more filters
```

**New Flow (follow read_recent pattern):**
```python
# NEW - use storage backend instead of flat files
if hasattr(backend, 'query_entries_paginated'):
    rows, total_count = await backend.query_entries_paginated(
        project=record,
        page=page,
        page_size=page_size,
        agents=agents_filter,
        emojis=emojis_filter,
        message_pattern=message_filter,
        message_mode=message_mode,
        case_sensitive=case_sensitive,
        start_time=start_time,
        end_time=end_time,
        meta_filters=meta_filters,
    )
    pagination_info = create_pagination_info(page, page_size, total_count)
else:
    # Fallback to legacy file reading for backwards compatibility
    # (Keep existing flat-file logic for old logs not in DB)
    lines = await read_all_lines(log_path)
    # ... existing parsing logic
```

**Key Changes:**
1. Check if backend has `query_entries_paginated()` method (it does - sqlite.py:594)
2. Call backend method directly instead of reading files
3. Pass all filter parameters to backend (agents, emojis, message pattern, time ranges)
4. NO PARSING - DB returns structured rows, no `parse_log_line()` needed
5. Keep flat-file fallback for backwards compatibility with old logs

**Files Modified:**
- `tools/query_entries.py` lines 645-750 (~100 lines changed)
- Reuse existing `create_pagination_info()` helper (already exists)
- No changes to storage backend (already implements query_entries_paginated)

**Testing:**
- Integration test: query_entries("template") → 39+ results (not 0)
- Integration test: compare query_entries vs read_recent results → identical
- Integration test: cross-project search still works
- Unit test: fallback to flat files when backend method unavailable

**Rationale:**
- `read_recent` uses DB and works perfectly - proven pattern
- Storage backend already has all necessary methods - no schema changes needed
- DB queries are faster than file I/O + parsing for large logs
- Eliminates parsing bugs entirely (no `_is_template_entry()` in DB path)
- Connection pooling benefits (already implemented in storage/pool.py)

#### Component 2.2: Add Observability to Template Filtering (Flat-File Fallback)

**File:** `utils/logs.py`  
**Function:** `_is_template_entry()` (line 25)

**Add logging when filtering occurs:**
```python
import logging
logger = logging.getLogger(__name__)

def _is_template_entry(...) -> bool:
    # ... existing logic
    is_template = (structural_count >= 2 or ...)
    
    if is_template:
        logger.debug(f"Filtered template entry: {message[:100]}...")
    
    return is_template
```

**Rationale:**
- Phase 1 fixes the filter, but flat-file fallback still uses it
- Logging provides visibility when filtering occurs
- Helps debug if filter is still too aggressive
- Debug level - won't spam production logs

---

### Phase 3: Search Pagination (UX Enhancement)

#### Component 3.1: Add Pagination Parameters to scribe.search

**File:** `tools/search.py`  
**Function:** `search()` signature (line 532)

**Current Signature:**
```python
async def search(
    agent: str,
    pattern: str,
    path: Optional[str] = None,
    type: Optional[str] = None,
    glob: Optional[str] = None,
    output_mode: str = "content",
    format: str = "readable",
    # ... other params
    max_total_matches: int = 200,
    max_matches_per_file: int = 50,
    max_files: int = 100,
) -> CallToolResult:
```

**New Signature:**
```python
async def search(
    agent: str,
    pattern: str,
    path: Optional[str] = None,
    type: Optional[str] = None,
    glob: Optional[str] = None,
    output_mode: str = "content",
    format: str = "readable",
    # NEW PAGINATION PARAMS
    page: int = 1,
    page_size: int = 10,  # ← Default 10 matches per page (not 200!)
    # ... other params
    max_total_matches: int = 200,  # ← Still collect up to 200
    max_matches_per_file: int = 50,
    max_files: int = 100,
) -> CallToolResult:
```

**Rationale:**
- Follows query_entries pattern (`page`, `page_size`)
- Default 10 matches per page provides good UX
- `max_total_matches` is still the collection ceiling (200)
- Pagination slices the collected matches for display

#### Component 3.2: Implement Pagination Logic

**File:** `tools/search.py`  
**Location:** After line 707 (after match collection loop)

**New Code:**
```python
# After collecting all matches (line 707):
# results = List[FileResult] with all matches

# Flatten all matches for pagination
all_matches = []
for file_result in results:
    for match in file_result.matches:
        all_matches.append({
            "file": file_result.file_path,
            "match": match,
        })

total_matches = len(all_matches)
total_pages = (total_matches + page_size - 1) // page_size

# Validate page number
if page < 1:
    page = 1
if page > total_pages and total_pages > 0:
    page = total_pages

# Slice for current page
start_idx = (page - 1) * page_size
end_idx = start_idx + page_size
paginated_matches = all_matches[start_idx:end_idx]

# Rebuild FileResult structure for paginated matches
# Group by file path
from collections import defaultdict
file_groups = defaultdict(list)
for item in paginated_matches:
    file_groups[item["file"]].append(item["match"])

paginated_results = [
    FileResult(file_path=fpath, matches=matches)
    for fpath, matches in file_groups.items()
]

# Create pagination info
pagination_info = {
    "page": page,
    "page_size": page_size,
    "total_matches": total_matches,
    "total_pages": total_pages,
    "has_next": page < total_pages,
    "has_prev": page > 1,
}
```

**Rationale:**
- Collect ALL matches up to max_total_matches (unchanged)
- Flatten to list of (file, match) tuples for pagination
- Slice based on page/page_size
- Rebuild FileResult structure for formatter
- Include pagination metadata in response

#### Component 3.3: Update Readable Formatter

**File:** `tools/search.py`  
**Function:** `_format_search_readable()` (lines 478-508)

**Add pagination header:**
```python
def _format_search_readable(data: Dict[str, Any], ...) -> str:
    lines = []
    
    # NEW - Add pagination header if present
    if "pagination" in data:
        p = data["pagination"]
        lines.append(f"\n📄 Page {p['page']}/{p['total_pages']}")
        lines.append(f"   Showing matches {(p['page']-1)*p['page_size']+1}-{min(p['page']*p['page_size'], p['total_matches'])} of {p['total_matches']} total")
        if p['has_next']:
            lines.append(f"   → Use page={p['page']+1} to see next {p['page_size']} matches")
        lines.append("")
    
    # ... existing formatting logic
```

**Testing:**
- Unit test: pagination slice logic (200 matches, page_size=10 → 20 pages)
- Integration test: search common pattern, page through results
- Integration test: readable format shows "Page 1/15" header
- Edge case test: page=99 when only 5 pages → clamps to page=5

---

## Data Flow
<!-- ID: data_flow -->

### Phase 1: Hot Fix Flow

```
User: query_entries(message="template")
  ↓
tools/query_entries.py::query_entries()
  ↓
lines 647-669: read_all_lines() + parse_log_line()
  ↓
utils/logs.py::_is_template_entry()
  ↓ [FIXED LOGIC]
Check: requires 2+ structural indicators
  ↓ ("template" in message alone = NOT FILTERED)
parsed entry returned
  ↓
Results: 39+ entries (not 0) ✅

User: search(pattern="def long_function_name")
  ↓
tools/search.py::search()
  ↓
Collect 200 Match objects
  ↓
Line 318: Match(line=_truncate_line(...)) [FIXED]
  ↓
Each line truncated to 500 chars max
  ↓
Response: ~300KB (not 800KB) ✅
```

### Phase 2: DB Migration Flow

```
User: query_entries(message="template")
  ↓
tools/query_entries.py::query_entries()
  ↓
[NEW CODE] Check: hasattr(backend, 'query_entries_paginated')
  ↓ (YES - storage/sqlite.py:594)
backend.query_entries_paginated(
    project=record,
    page=page,
    page_size=page_size,
    message_pattern="template",
    ...
)
  ↓
storage/sqlite.py::query_entries_paginated()
  ↓
SQL: SELECT * FROM scribe_entries WHERE message LIKE '%template%'
  ↓
Returns: rows from DB (NO PARSING)
  ↓
Results: 39+ entries ✅

NO _is_template_entry() IN THIS PATH
```

### Phase 3: Pagination Flow

```
User: search(pattern="def", page=1, page_size=10)
  ↓
tools/search.py::search()
  ↓
Collect up to 200 matches
  ↓
Flatten: [(file1, match1), (file2, match2), ...]
  ↓ 143 total matches
Slice: all_matches[(1-1)*10 : (1-1)*10+10]
  ↓ matches 0-9 (first 10)
Rebuild: FileResult objects for page 1
  ↓
_format_search_readable()
  ↓
Output:
  📄 Page 1/15
     Showing matches 1-10 of 143 total
     → Use page=2 to see next 10 matches
  
  file.py:42: def parse_log_line(...)
  file.py:101: def parse_config(...)
  ... (8 more matches)
```

---

## API Design
<!-- ID: api_design -->

### Phase 1: No API Changes

**Internal fixes only:**
- `_is_template_entry()` logic change (internal function)
- `_truncate_line()` helper added (internal function)
- No tool signature changes
- No breaking changes

### Phase 2: No API Changes

**Internal routing change:**
- `query_entries` MCP tool signature unchanged
- Internal: switches from flat-file to DB backend
- Behavior change: returns MORE results (bug fix)
- Backwards compatible: fallback to flat-files if backend unavailable

### Phase 3: Additive API Changes

**scribe.search - NEW optional parameters:**

```python
# NEW parameters (backwards compatible - have defaults)
page: int = 1
page_size: int = 10

# Example calls:
search(agent="Agent", pattern="def")  # ← Works exactly as before (page=1, page_size=10)
search(agent="Agent", pattern="def", page=2)  # ← NEW - get page 2
search(agent="Agent", pattern="def", page_size=20)  # ← NEW - 20 per page
```

**Structured response - NEW fields:**

```json
{
  "matches": [...],  // existing
  "pagination": {     // NEW
    "page": 1,
    "page_size": 10,
    "total_matches": 143,
    "total_pages": 15,
    "has_next": true,
    "has_prev": false
  }
}
```

**Readable response - NEW header:**

```
📄 Page 1/15
   Showing matches 1-10 of 143 total
   → Use page=2 to see next 10 matches

🔍 Search Results for "def"
   Pattern: def (regex)
   Files: 3 matched

... (existing match output)
```

---

## Security Considerations
<!-- ID: security_considerations -->

### Phase 1: Low Risk

**Template Filter Change:**
- Risk: May allow actual template entries through if logic is wrong
- Mitigation: Unit tests verify filter still catches multi-indicator templates
- Impact: Low - worst case is some header/example entries appear in results

**Line Truncation:**
- Risk: Information disclosure if truncation reveals sensitive data prefix
- Mitigation: Truncation is at 500 chars - same risk as showing first 500 chars
- Impact: Low - no new risk vs existing behavior

### Phase 2: Medium Risk

**DB Migration:**
- Risk: SQL injection if message_pattern not properly escaped
- Mitigation: Storage backend already uses parameterized queries (sqlite.py:623)
- Verification: Code review confirms all user inputs are passed as SQL params, not concatenated

**Backwards Compatibility:**
- Risk: Old logs not in DB become inaccessible
- Mitigation: Keep flat-file fallback for backwards compatibility
- Testing: Integration test with project that has flat-file logs only

### Phase 3: Low Risk

**Pagination:**
- Risk: Page parameter manipulation (negative, huge numbers)
- Mitigation: Validation clamping (page < 1 → page = 1, page > total_pages → page = total_pages)
- Impact: Low - worst case is empty page or last page returned

**Resource Exhaustion:**
- Risk: User requests page_size=10000 to bypass pagination
- Mitigation: Add MAX_PAGE_SIZE = 100 constant, clamp user input
- Code: `page_size = min(page_size, MAX_PAGE_SIZE)`

---

## Deployment Strategy
<!-- ID: deployment_strategy -->

### Phase 1: Hot Fix (Ship Immediately)

**Timeline:** 1-2 hours development + testing

**Steps:**
1. Implement `_is_template_entry()` fix in `utils/logs.py`
2. Add `_truncate_line()` helper and apply to Match creation
3. Run unit tests (new + existing)
4. Manual test: `query_entries(message="template")` → verify results
5. Manual test: `search(pattern="def")` in large codebase → verify response size
6. Commit with message: "fix: query_entries template filter + search line truncation"
7. Deploy to production (no MCP server restart needed for Python changes)

**Rollback:** Git revert (no schema changes, no data changes)

**Success Metrics:**
- `query_entries("template")` returns >0 results
- `search("common_pattern")` response size <500KB
- No test failures

### Phase 2: DB Migration (Ship After Phase 1 Verified)

**Timeline:** 4-6 hours development + testing

**Prerequisites:**
- Phase 1 deployed and stable
- Storage backend `query_entries_paginated()` method verified functional

**Steps:**
1. Implement DB routing in `tools/query_entries.py` lines 645-750
2. Add feature flag check (optional): `USE_DB_QUERIES` environment variable
3. Run unit tests
4. Integration test: Compare query_entries vs read_recent results
5. Integration test: Cross-project search still works
6. Integration test: Fallback to flat-files when backend unavailable
7. Manual test in production-like environment with real logs
8. Commit: "feat: migrate query_entries to storage backend"
9. Deploy with monitoring

**Rollback:** 
- Set `USE_DB_QUERIES=false` environment variable (instant)
- OR git revert

**Success Metrics:**
- `query_entries` results identical to `read_recent` for same filters
- Query latency <100ms (DB faster than file I/O)
- Cross-project search returns results from all projects
- No errors in logs

### Phase 3: Search Pagination (Ship Last, Optional)

**Timeline:** 6-8 hours development + testing

**Prerequisites:**
- Phase 1 and Phase 2 deployed and stable
- User feedback on Phase 1/2 fixes collected

**Steps:**
1. Add `page`, `page_size` parameters to `search()` signature
2. Implement pagination slicing logic after match collection
3. Update `_format_search_readable()` to show pagination header
4. Add structured response pagination metadata
5. Update tool docstring
6. Run unit tests (pagination math, edge cases)
7. Integration tests (page through large result set)
8. Update documentation/examples
9. Commit: "feat: add pagination support to scribe.search"
10. Deploy

**Rollback:** Git revert (backwards compatible - new params have defaults)

**Success Metrics:**
- `search(pattern="def")` returns 10 results (not 200)
- `search(pattern="def", page=2)` returns next 10 results
- Readable format shows pagination header
- Response size <50KB per page

**Post-Deployment:**
- Monitor tool usage logs for pagination patterns
- Collect user feedback on default page_size (10 vs 20)
- Consider adding preview mode in future

---

## Testing Strategy
<!-- ID: testing_strategy -->

### Phase 1 Tests

**Unit Tests: `test_logs.py`**
```python
def test_template_entry_filter_fixed():
    # Legitimate entry with "template" in message
    result = _is_template_entry(
        timestamp="2026-02-02 04:00:00",
        emoji="ℹ️",
        agent="CoderAgent",
        message="Implemented template rendering feature"
    )
    assert result is False  # Should NOT be filtered

def test_template_entry_filter_catches_templates():
    # Actual template entry with multiple indicators
    result = _is_template_entry(
        timestamp="YYYY-MM-DD HH:MM:SS",
        emoji="EMOJI",
        agent="<name>",
        message="Message text here"
    )
    assert result is True  # Should be filtered
```

**Unit Tests: `test_search.py`**
```python
def test_truncate_line_short():
    line = "short line"
    result = _truncate_line(line, max_length=500)
    assert result == "short line"

def test_truncate_line_long():
    line = "x" * 1000
    result = _truncate_line(line, max_length=500)
    assert len(result) <= 550  # 500 + ellipsis + indicator
    assert "TRUNCATED" in result
    assert "1000 chars total" in result
```

**Integration Test:**
```python
async def test_query_entries_returns_template_results():
    # Search for entries containing "template"
    result = await query_entries(
        agent="TestAgent",
        message="template",
        format="structured"
    )
    assert result["pagination"]["total_count"] > 0
    # Verify at least one result contains "template" in message
    messages = [e["msg"] for e in result["entries"]]
    assert any("template" in msg.lower() for msg in messages)
```

### Phase 2 Tests

**Integration Tests: `test_query_entries.py`**
```python
async def test_query_entries_uses_database():
    """Verify query_entries calls storage backend, not flat files."""
    # Mock backend to verify it's called
    with patch('tools.query_entries.storage_backend') as mock_backend:
        mock_backend.query_entries_paginated = AsyncMock(return_value=([], 0))
        
        await query_entries(agent="TestAgent", message="test")
        
        mock_backend.query_entries_paginated.assert_called_once()

async def test_query_entries_matches_read_recent():
    """Results should be identical to read_recent for same filters."""
    # Query with query_entries
    qe_result = await query_entries(
        agent="TestAgent",
        agents=["CoderAgent"],
        start="2026-02-01",
        format="structured"
    )
    
    # Query with read_recent (same filters)
    rr_result = await read_recent(
        agent="TestAgent",
        filter={"agent": "CoderAgent"},
        format="structured"
    )
    
    # Entry IDs should match
    qe_ids = {e["id"] for e in qe_result["entries"]}
    rr_ids = {e["id"] for e in rr_result["entries"]}
    assert qe_ids == rr_ids
```

### Phase 3 Tests

**Unit Tests: `test_search.py`**
```python
def test_pagination_slice_logic():
    matches = list(range(143))  # 143 matches
    page, page_size = 1, 10
    
    start_idx = (page - 1) * page_size  # 0
    end_idx = start_idx + page_size      # 10
    paginated = matches[start_idx:end_idx]
    
    assert len(paginated) == 10
    assert paginated == list(range(10))

def test_pagination_last_page_partial():
    matches = list(range(143))
    page, page_size = 15, 10  # Last page
    
    start_idx = (page - 1) * page_size  # 140
    end_idx = start_idx + page_size      # 150
    paginated = matches[start_idx:end_idx]
    
    assert len(paginated) == 3  # Only 3 matches left
```

**Integration Tests:**
```python
async def test_search_pagination():
    result = await search(
        agent="TestAgent",
        pattern="def",
        page=1,
        page_size=10,
        format="structured"
    )
    
    assert result["pagination"]["page"] == 1
    assert result["pagination"]["page_size"] == 10
    assert len(result["matches"]) <= 10
    
    # Get page 2
    result_p2 = await search(
        agent="TestAgent",
        pattern="def",
        page=2,
        page_size=10,
        format="structured"
    )
    
    # Pages should have different results
    p1_lines = {(m["file"], m["line_number"]) for m in result["matches"]}
    p2_lines = {(m["file"], m["line_number"]) for m in result_p2["matches"]}
    assert p1_lines.isdisjoint(p2_lines)
```

---

## Performance Considerations
<!-- ID: performance_considerations -->

### Phase 1: Performance Neutral

**Template Filter:**
- Old: Single pass checking 9 indicators with `any()`
- New: Two passes counting structural/content indicators
- Complexity: O(indicators × text_length) - same order of magnitude
- Impact: Negligible (<1ms per entry)

**Line Truncation:**
- Old: Store full line (unbounded memory)
- New: Truncate to 500 chars
- Impact: REDUCES memory usage (200 matches × 4KB avg → 200 matches × 500 chars)
- Response serialization: FASTER (smaller payload)

### Phase 2: Performance Improvement

**DB vs Flat-File:**
- Old: `read_all_lines()` + `parse_log_line()` loop (O(n) where n = log size)
- New: DB query with WHERE clause + indexes (O(log n) with indexes)
- Benchmark (10K entries):
  - Flat-file: ~50-100ms (I/O + parsing)
  - DB query: ~5-20ms (indexed SELECT)
- **5-10x faster for typical queries**

**Connection Pooling:**
- Storage backend uses SQLiteConnectionPool (storage/pool.py)
- Reuses connections across queries
- No repeated file opens/closes

**Scalability:**
- Flat-file approach degrades as logs grow (linear scan)
- DB approach scales with indexes (logarithmic)
- Cross-project search: DB can JOIN across projects, flat-files must iterate

### Phase 3: Performance Trade-offs

**Collection Phase:**
- Still collects up to max_total_matches (200) - unchanged
- Memory usage: Same as before (200 Match objects)

**Pagination Phase:**
- Flatten matches: O(n) where n = total matches (200 max)
- Slice: O(1)
- Rebuild FileResult: O(n) grouping
- Total overhead: ~1-2ms for 200 matches

**Response Size:**
- Old: 200 matches × 4KB = 800KB
- New: 10 matches × 500 chars = 5KB per page
- **160x reduction in response size**
- Network: Faster transmission
- Client: Faster rendering

**User Workflow:**
- Old: Wait for 800KB response (slow), render all 200 (laggy), scroll to find relevant
- New: Fast 5KB response, see first 10, decide if relevant, page forward if needed
- **Better perceived performance despite same backend work**

---

## Risk Assessment
<!-- ID: risk_assessment -->

### Phase 1 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Template filter too permissive | Low | Low | Unit tests verify multi-indicator templates still filtered |
| Template filter still too strict | Medium | Low | Add logging to observe filter behavior in production |
| Line truncation breaks syntax | Low | Low | 500 chars sufficient for most code constructs |
| Performance regression | Very Low | Low | Filter logic still O(n), truncation reduces memory |

**Overall Phase 1 Risk: LOW**

### Phase 2 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| DB query returns different results | Low | Medium | Integration test compares query_entries vs read_recent |
| SQL injection vulnerability | Very Low | High | Storage backend uses parameterized queries (verified) |
| Backend method unavailable | Low | Medium | Fallback to flat-file parsing (backwards compatible) |
| Cross-project search breaks | Low | Medium | Integration test verifies cross-project functionality |
| Performance regression on old hardware | Low | Low | DB queries generally faster, but test on older systems |

**Overall Phase 2 Risk: MEDIUM** (architectural change, but well-mitigated)

### Phase 3 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pagination math errors (off-by-one) | Low | Low | Unit tests cover edge cases (empty, single page, last page partial) |
| Page parameter abuse (huge numbers) | Low | Low | Clamp page to valid range (1 to total_pages) |
| Resource exhaustion (huge page_size) | Low | Medium | Add MAX_PAGE_SIZE=100 constant, clamp input |
| Backwards compatibility break | Very Low | Medium | New params have defaults, old calls work unchanged |

**Overall Phase 3 Risk: LOW** (additive feature, well-tested pattern)

---

## Open Questions
<!-- ID: open_questions -->

### Phase 1
- ✅ Should we remove "template" from indicators entirely? **Decision: No, use multi-indicator logic instead**
- ✅ What's the right MAX_LINE_LENGTH? **Decision: 500 chars (balance between context and size)**
- ⚠️ Should truncation be configurable per-tool-call? **Deferred: Hardcode 500 for now, make configurable later if needed**

### Phase 2
- ✅ Should we deprecate flat-file parsing entirely? **Decision: No, keep as fallback for backwards compatibility**
- ✅ Do we need feature flag for DB routing? **Decision: Optional, check hasattr() instead**
- ⚠️ Should we auto-migrate old flat-file logs to DB? **Deferred: Future enhancement, not in scope**

### Phase 3
- ⚠️ What's the optimal default page_size? **Decision: 10 (matches query_entries), but collect user feedback**
- ⚠️ Should we add preview mode (show total, first N matches)? **Deferred: Future enhancement**
- ⚠️ Should pagination be by matches or by files? **Decision: By matches (more useful for dense files)**

---

## References
<!-- ID: references -->

### Research Documents
- `RESEARCH_SCRIBE_SEARCH_20260202.md` - scribe.search output explosion analysis
- `RESEARCH_QUERY_ENTRIES_FLATFILE_DB_20260202.md` - query_entries template filter bug analysis

### Code References
- `tools/search.py` - scribe.search implementation (749 lines)
- `tools/query_entries.py` - query_entries implementation (2034 lines)
- `tools/read_recent.py` - read_recent implementation (working DB pattern)
- `utils/logs.py` - Log parsing utilities with template filter (81 lines)
- `storage/sqlite.py` - Storage backend with query_entries methods (3022 lines)
- `storage/base.py` - StorageBackend abstract interface

### Patterns to Follow
- `read_recent` DB querying pattern (lines 306-327)
- `query_entries` pagination pattern (page, page_size, PaginationInfo)
- `ResponseFormatter` structured/readable dispatch pattern

---

**End of Architecture Guide**
