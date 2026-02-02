---
id: query_enhancement_suite-search-query-remediation-phase-plan
title: 'Phase Plan: Search & Query Tool Remediation'
doc_name: SEARCH_QUERY_REMEDIATION_PHASE_PLAN
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
# Phase Plan: Search & Query Tool Remediation

**Project:** query_enhancement_suite  
**Sub-Plan:** search_query_remediation  
**Author:** ArchitectAgent-SearchQueryFix  
**Version:** 1.0  
**Status:** Ready for Implementation  
**Created:** 2026-02-02

---

## Overview

This phase plan breaks down the remediation work into three sequential phases, each with small, bounded task packages suitable for Coder Agent execution. Each phase is independently deployable and testable.

**Total Estimated Effort:** 11-16 hours across 3 phases

**Dependency Chain:**
- Phase 1 → Phase 2 (Phase 1 must be deployed before Phase 2)
- Phase 2 → Phase 3 (Phase 2 should be stable before Phase 3)

---

## Phase 1: Hot Fixes (IMMEDIATE)
<!-- ID: phase_1 -->

**Goal:** Fix critical bugs blocking tool usage  
**Timeline:** 1-2 hours  
**Risk:** LOW  
**Deployment:** Ship immediately after testing

### Task Package 1.1: Fix Template Filter Logic
<!-- ID: task_1_1 -->

**Scope:** Modify `utils/logs.py` to require multiple indicators before filtering entries

**Files to Modify:**
- `utils/logs.py` (lines 15-25 only)

**Dependencies:** None

#### Specifications

1. **Replace `_is_template_entry()` function** (lines 15-25):
   - Remove single-indicator `any()` logic
   - Add two indicator lists: `structural_indicators` and `content_indicators`
   - Structural: `["YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI"]`
   - Content: `["Message text", "key=value", "placeholder", "example"]`
   - Count indicators in each category: `sum(1 for ind in list if ind.lower() in combined_text)`
   - Return `True` only if: `structural_count >= 2 OR (structural_count >= 1 AND content_count >= 2)`
   - Remove "template" from indicator lists entirely

2. **Add debug logging** (optional but recommended):
   - Import: `import logging` at top of file
   - Create logger: `logger = logging.getLogger(__name__)`
   - Log when filtering: `logger.debug(f"Filtered template entry: {message[:100]}...")`

3. **Update docstring**:
   - Change from: `"Check if this appears to be a template/example entry rather than a real one."`
   - Change to: `"Check if entry is a template/placeholder (requires 2+ indicators)."`

#### Verification

- [ ] `pytest tests/test_logs.py::test_template_entry_filter_fixed` passes
- [ ] `pytest tests/test_logs.py::test_template_entry_filter_catches_templates` passes
- [ ] Manual test: `query_entries(message="template")` returns >0 results
- [ ] Manual test: `query_entries(message="YYYY-MM-DD")` returns 0 results (templates filtered)

#### Out of Scope (DO NOT TOUCH)
- Do NOT modify `parse_log_line()` function (lines 28-58)
- Do NOT modify `read_all_lines()` function (lines 71-81)
- Do NOT touch any other files

**Estimated Effort:** 30 minutes

---

### Task Package 1.2: Add Line Truncation to Search
<!-- ID: task_1_2 -->

**Scope:** Add per-line truncation to Match objects in scribe.search

**Files to Modify:**
- `tools/search.py` (lines 270-325 region only)

**Dependencies:** None

#### Specifications

1. **Add module-level constant** (after imports, around line 100):
   ```python
   MAX_LINE_LENGTH = 500  # characters - safety limit for output size
   ```

2. **Add `_truncate_line()` helper function** (around line 270, before `_search_file()`):
   ```python
   def _truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
       """Truncate line with ellipsis if exceeds max_length."""
       if len(line) <= max_length:
           return line
       return f"{line[:max_length]}... [TRUNCATED - {len(line)} chars total]"
   ```

3. **Apply truncation to Match creation** (line 316-321 in `_search_file()`):
   - Replace: `line=all_lines[idx].rstrip()`
   - With: `line=_truncate_line(all_lines[idx].rstrip())`
   - Replace: `context_before=ctx_before`
   - With: `context_before=[_truncate_line(ln) for ln in ctx_before]`
   - Replace: `context_after=ctx_after`
   - With: `context_after=[_truncate_line(ln) for ln in ctx_after]`

4. **Apply same truncation to multiline search** (line 360-366 in `_search_file_multiline()`):
   - Same transformation as above for Match object creation

#### Verification

- [ ] `pytest tests/test_search.py::test_truncate_line_short` passes
- [ ] `pytest tests/test_search.py::test_truncate_line_long` passes
- [ ] Manual test: `search(pattern="def", path=".")` response size <500KB
- [ ] Manual test: Search in minified JS file shows "[TRUNCATED - N chars total]" indicator

#### Out of Scope (DO NOT TOUCH)
- Do NOT modify `_build_structured_result()` function
- Do NOT modify `_format_search_readable()` function
- Do NOT change tool signature (no new parameters)
- Do NOT touch pagination logic (Phase 3)

**Estimated Effort:** 30 minutes

---

### Task Package 1.3: Add Unit Tests for Phase 1
<!-- ID: task_1_3 -->

**Scope:** Create unit tests for template filter and line truncation

**Files to Modify:**
- `tests/test_logs.py` (create if doesn't exist)
- `tests/test_search.py` (add to existing)

**Dependencies:** Task 1.1 and 1.2 must be complete

#### Specifications

1. **Create `tests/test_logs.py`** if it doesn't exist:
   ```python
   from utils.logs import _is_template_entry
   
   def test_template_entry_filter_fixed():
       """Legitimate entry with 'template' in message should NOT be filtered."""
       result = _is_template_entry(
           timestamp="2026-02-02 04:00:00",
           emoji="ℹ️",
           agent="CoderAgent",
           message="Implemented template rendering feature"
       )
       assert result is False, "Entry with 'template' in message should not be filtered"
   
   def test_template_entry_filter_catches_templates():
       """Actual template entry with multiple indicators SHOULD be filtered."""
       result = _is_template_entry(
           timestamp="YYYY-MM-DD HH:MM:SS",
           emoji="EMOJI",
           agent="<name>",
           message="Message text here"
       )
       assert result is True, "Entry with 2+ structural indicators should be filtered"
   
   def test_template_entry_single_structural_not_filtered():
       """Single structural indicator alone should NOT filter."""
       result = _is_template_entry(
           timestamp="YYYY-MM-DD",  # Only 1 structural
           emoji="✅",
           agent="RealAgent",
           message="Real work done"
       )
       assert result is False, "Single structural indicator insufficient"
   ```

2. **Add to `tests/test_search.py`**:
   ```python
   from tools.search import _truncate_line, MAX_LINE_LENGTH
   
   def test_truncate_line_short():
       """Short lines should pass through unchanged."""
       line = "short line"
       result = _truncate_line(line, max_length=500)
       assert result == "short line"
   
   def test_truncate_line_long():
       """Long lines should be truncated with indicator."""
       line = "x" * 1000
       result = _truncate_line(line, max_length=500)
       assert len(result) <= 550  # 500 + ellipsis + indicator text
       assert "TRUNCATED" in result
       assert "1000 chars total" in result
       assert result.startswith("x" * 500)
   
   def test_truncate_line_exact_boundary():
       """Line exactly at MAX_LINE_LENGTH should not be truncated."""
       line = "x" * MAX_LINE_LENGTH
       result = _truncate_line(line)
       assert result == line
       assert "TRUNCATED" not in result
   ```

#### Verification

- [ ] `pytest tests/test_logs.py -v` - all tests pass
- [ ] `pytest tests/test_search.py -v` - all tests pass
- [ ] Test coverage for `_is_template_entry()` ≥90%
- [ ] Test coverage for `_truncate_line()` = 100%

#### Out of Scope
- Do NOT write integration tests (those come later)
- Do NOT test Phase 2 or Phase 3 functionality

**Estimated Effort:** 20 minutes

---

## Phase 2: DB Migration (ARCHITECTURAL FIX)
<!-- ID: phase_2 -->

**Goal:** Migrate query_entries from flat-file parsing to storage backend  
**Timeline:** 4-6 hours  
**Risk:** MEDIUM  
**Deployment:** Ship after Phase 1 is stable

### Task Package 2.1: Wire query_entries to Storage Backend
<!-- ID: task_2_1 -->

**Scope:** Replace flat-file reading logic with storage backend DB queries

**Files to Modify:**
- `tools/query_entries.py` (lines 645-750 region only)

**Dependencies:** Phase 1 must be deployed and stable

#### Specifications

1. **Locate `_execute_search_with_fallbacks()` function** (line 590):
   - Find the section that reads flat files (lines 645-750)
   - This is where `lines = await read_all_lines(log_path)` occurs

2. **Add DB routing logic BEFORE flat-file reading** (insert at line 645):
   ```python
   # NEW: Try storage backend first (follows read_recent pattern)
   if hasattr(backend, 'query_entries_paginated'):
       try:
           rows, total_count = await backend.query_entries_paginated(
               project=record,
               page=page,
               page_size=page_size,
               agents=agents_filter if agents_filter else None,
               emojis=emojis_filter if emojis_filter else None,
               message_pattern=message_filter,
               message_mode=message_mode,
               case_sensitive=case_sensitive,
               start_time=start_time,
               end_time=end_time,
               meta_filters=meta_filters if meta_filters else None,
           )
           
           # Convert DB rows to entry format (match existing structure)
           filtered_entries = [
               {
                   "ts": row.get("ts_iso") or row.get("timestamp"),
                   "emoji": row.get("emoji", ""),
                   "agent": row.get("agent", ""),
                   "project": row.get("project_name") or project,
                   "message": row.get("message", ""),
                   "meta": row.get("meta", {}),
               }
               for row in rows
           ]
           
           pagination_info = create_pagination_info(page, page_size, total_count)
           
           # Skip flat-file logic - DB query succeeded
           return filtered_entries, pagination_info, validation_warnings
           
       except Exception as db_error:
           # Log error and fall through to flat-file fallback
           logger.warning(f"Storage backend query failed: {db_error}, falling back to file")
   
   # EXISTING: Flat-file fallback (keep for backwards compatibility)
   # ... existing lines 647-750 logic stays here ...
   ```

3. **Key integration points**:
   - `backend` is already available in scope (passed to function)
   - `record` is the project record (already available)
   - `page`, `page_size`, filter variables already exist in function
   - `create_pagination_info()` helper already exists (reuse it)
   - Return same format as existing code (tuple of entries, pagination, warnings)

4. **DO NOT delete flat-file logic** - keep lines 647-750 as fallback:
   - It will only execute if backend unavailable or DB query fails
   - Backwards compatibility for old logs not in DB

#### Verification

- [ ] `pytest tests/test_query_entries.py::test_query_entries_uses_database` passes
- [ ] Manual test: `query_entries(message="template")` returns >0 results
- [ ] Manual test: `query_entries(message="test", agents=["CoderAgent"])` filters correctly
- [ ] Manual test: Cross-project search still works (`search_scope="all_projects"`)
- [ ] Check logs: "Storage backend query failed" should NOT appear under normal conditions

#### Out of Scope (DO NOT TOUCH)
- Do NOT modify `parse_log_line()` or `_is_template_entry()` (already fixed in Phase 1)
- Do NOT change tool signature
- Do NOT modify storage backend code (`storage/sqlite.py`)
- Do NOT remove flat-file fallback logic

**Estimated Effort:** 2-3 hours

---

### Task Package 2.2: Add Integration Tests for DB Migration
<!-- ID: task_2_2 -->

**Scope:** Verify query_entries uses DB and returns correct results

**Files to Modify:**
- `tests/test_query_entries.py` (add to existing or create)

**Dependencies:** Task 2.1 must be complete

#### Specifications

1. **Add DB routing test**:
   ```python
   from unittest.mock import patch, AsyncMock
   import pytest
   
   @pytest.mark.asyncio
   async def test_query_entries_uses_database():
       """Verify query_entries calls storage backend, not flat files."""
       # Mock backend to verify it's called
       with patch('tools.query_entries.storage_backend') as mock_backend:
           mock_backend.query_entries_paginated = AsyncMock(return_value=([], 0))
           
           from tools.query_entries import query_entries
           await query_entries(agent="TestAgent", message="test")
           
           # Verify backend method was called
           assert mock_backend.query_entries_paginated.called, "Backend not called"
           call_args = mock_backend.query_entries_paginated.call_args
           assert call_args.kwargs.get("message_pattern") == "test"
   ```

2. **Add result parity test** (query_entries vs read_recent):
   ```python
   @pytest.mark.asyncio
   async def test_query_entries_matches_read_recent():
       """Results should be identical to read_recent for same filters."""
       from tools.query_entries import query_entries
       from tools.read_recent import read_recent
       
       # Query with query_entries
       qe_result = await query_entries(
           agent="TestAgent",
           agents=["Orchestrator"],
           start="2026-02-01",
           format="structured"
       )
       
       # Query with read_recent (same filters)
       rr_result = await read_recent(
           agent="TestAgent",
           filter={"agent": "Orchestrator"},
           format="structured"
       )
       
       # Entry counts should match (or be very close)
       qe_count = qe_result["pagination"]["total_count"]
       rr_count = rr_result["pagination"]["total_count"]
       assert abs(qe_count - rr_count) <= 1, f"Counts differ: {qe_count} vs {rr_count}"
   ```

3. **Add fallback test**:
   ```python
   @pytest.mark.asyncio
   async def test_query_entries_fallback_to_files():
       """Should fall back to flat files when backend unavailable."""
       # Mock backend without query_entries_paginated method
       with patch('tools.query_entries.storage_backend') as mock_backend:
           delattr(mock_backend, 'query_entries_paginated')  # Remove method
           
           from tools.query_entries import query_entries
           # Should not crash - should use flat-file fallback
           result = await query_entries(agent="TestAgent", message="test")
           assert result is not None
   ```

#### Verification

- [ ] `pytest tests/test_query_entries.py::test_query_entries_uses_database -v` passes
- [ ] `pytest tests/test_query_entries.py::test_query_entries_matches_read_recent -v` passes
- [ ] `pytest tests/test_query_entries.py::test_query_entries_fallback_to_files -v` passes
- [ ] All existing query_entries tests still pass (no regressions)

**Estimated Effort:** 1-2 hours

---

### Task Package 2.3: Performance Validation
<!-- ID: task_2_3 -->

**Scope:** Verify DB queries are faster than flat-file parsing

**Files to Modify:**
- `tests/test_performance.py` (create if doesn't exist)

**Dependencies:** Task 2.1 and 2.2 must be complete

#### Specifications

1. **Create benchmark test** in `tests/test_performance.py`:
   ```python
   import pytest
   import time
   from tools.query_entries import query_entries
   
   @pytest.mark.asyncio
   async def test_query_entries_performance():
       """DB queries should be faster than 100ms for typical queries."""
       start = time.time()
       
       result = await query_entries(
           agent="PerfTestAgent",
           message="test",
           page_size=50,
           format="structured"
       )
       
       elapsed_ms = (time.time() - start) * 1000
       
       # DB query should be fast (allow 100ms, typical is 5-20ms)
       assert elapsed_ms < 100, f"Query too slow: {elapsed_ms:.1f}ms"
       
       # Log performance for monitoring
       print(f"Query completed in {elapsed_ms:.1f}ms")
   ```

2. **Add cross-project performance test**:
   ```python
   @pytest.mark.asyncio
   async def test_cross_project_query_performance():
       """Cross-project queries should scale reasonably."""
       start = time.time()
       
       result = await query_entries(
           agent="PerfTestAgent",
           search_scope="all_projects",
           message="test",
           format="structured"
       )
       
       elapsed_ms = (time.time() - start) * 1000
       
       # Allow more time for cross-project (scale with num projects)
       # If 5 projects, allow 500ms max
       assert elapsed_ms < 500, f"Cross-project query too slow: {elapsed_ms:.1f}ms"
   ```

#### Verification

- [ ] `pytest tests/test_performance.py -v` passes
- [ ] Single-project queries complete in <100ms
- [ ] Cross-project queries scale linearly with project count
- [ ] No performance regressions vs Phase 1

**Estimated Effort:** 1 hour

---

## Phase 3: Search Pagination (UX ENHANCEMENT)
<!-- ID: phase_3 -->

**Goal:** Add pagination support to scribe.search  
**Timeline:** 6-8 hours  
**Risk:** LOW  
**Deployment:** Ship after Phase 2 is stable

### Task Package 3.1: Add Pagination Parameters to Search
<!-- ID: task_3_1 -->

**Scope:** Add `page` and `page_size` parameters to search tool signature

**Files to Modify:**
- `tools/search.py` (signature only, line 532)

**Dependencies:** Phase 2 must be deployed and stable

#### Specifications

1. **Modify `search()` function signature** (line 532):
   - Add after `format` parameter:
     ```python
     page: int = 1,
     page_size: int = 10,
     ```
   - Keep all existing parameters unchanged
   - `max_total_matches`, `max_matches_per_file`, `max_files` remain as-is

2. **Add parameter validation** at start of function (around line 570):
   ```python
   # Validate pagination params
   MAX_PAGE_SIZE = 100
   if page < 1:
       page = 1
   if page_size < 1:
       page_size = 1
   if page_size > MAX_PAGE_SIZE:
       page_size = MAX_PAGE_SIZE
   ```

3. **Update docstring** (add to parameters section):
   ```
   page: Page number (1-based). Default: 1.
   page_size: Matches per page. Default: 10, max: 100.
   ```

#### Verification

- [ ] Tool can be called with `page` and `page_size` parameters
- [ ] Default behavior unchanged: `search(pattern="def")` still works
- [ ] Parameter validation works: `page=-1` → `page=1`, `page_size=1000` → `page_size=100`

#### Out of Scope
- Do NOT implement pagination logic yet (Task 3.2)
- Do NOT modify formatter yet (Task 3.3)

**Estimated Effort:** 30 minutes

---

### Task Package 3.2: Implement Pagination Logic
<!-- ID: task_3_2 -->

**Scope:** Add pagination slicing after match collection

**Files to Modify:**
- `tools/search.py` (lines 707-715 region, after match collection loop)

**Dependencies:** Task 3.1 must be complete

#### Specifications

1. **After line 707** (after match collection loop, before `_build_structured_result()`):
   - Find: `results: List[FileResult]` (collected matches)
   - Insert pagination logic before calling `_build_structured_result()`

2. **Add pagination slicing code**:
   ```python
   # Flatten all matches for pagination
   all_matches = []
   for file_result in results:
       for match in file_result.matches:
           all_matches.append({
               "file": file_result.file_path,
               "match": match,
           })
   
   total_matches = len(all_matches)
   total_pages = (total_matches + page_size - 1) // page_size if total_matches > 0 else 1
   
   # Clamp page to valid range
   if page > total_pages:
       page = total_pages
   
   # Slice for current page
   start_idx = (page - 1) * page_size
   end_idx = start_idx + page_size
   paginated_matches = all_matches[start_idx:end_idx]
   
   # Rebuild FileResult structure for paginated matches
   from collections import defaultdict
   file_groups = defaultdict(list)
   for item in paginated_matches:
       file_groups[item["file"]].append(item["match"])
   
   paginated_results = [
       FileResult(file_path=str(fpath), matches=matches)
       for fpath, matches in file_groups.items()
   ]
   
   # Create pagination metadata
   pagination_info = {
       "page": page,
       "page_size": page_size,
       "total_matches": total_matches,
       "total_pages": total_pages,
       "has_next": page < total_pages,
       "has_prev": page > 1,
   }
   
   # Use paginated_results instead of results for formatting
   results = paginated_results
   ```

3. **Pass pagination_info to `_build_structured_result()`** (line 710):
   - Find: `data = _build_structured_result(...)`
   - Modify to include pagination: `data = _build_structured_result(results, ...)`
   - Add pagination to data dict: `data["pagination"] = pagination_info`

#### Verification

- [ ] `pytest tests/test_search.py::test_pagination_slice_logic` passes
- [ ] `pytest tests/test_search.py::test_pagination_last_page_partial` passes
- [ ] Manual test: `search(pattern="def", page=1, page_size=10)` returns max 10 matches
- [ ] Manual test: `search(pattern="def", page=2, page_size=10)` returns different matches
- [ ] Manual test: `search(pattern="def", page=999)` clamps to last page (no crash)

#### Out of Scope
- Do NOT modify readable formatter yet (Task 3.3)
- Do NOT change match collection logic (still collects up to max_total_matches)

**Estimated Effort:** 2-3 hours

---

### Task Package 3.3: Update Readable Formatter
<!-- ID: task_3_3 -->

**Scope:** Add pagination header to readable output

**Files to Modify:**
- `tools/search.py` (function `_format_search_readable()`, lines 478-508)

**Dependencies:** Task 3.2 must be complete

#### Specifications

1. **Locate `_format_search_readable()` function** (line 478):
   - Find where it builds the output lines: `lines = []`

2. **Add pagination header** (insert after line 480, before match output):
   ```python
   # Add pagination header if present
   if "pagination" in data:
       p = data["pagination"]
       lines.append("")
       lines.append(f"📄 Page {p['page']}/{p['total_pages']}")
       
       # Calculate match range for this page
       start_match = (p['page'] - 1) * p['page_size'] + 1
       end_match = min(p['page'] * p['page_size'], p['total_matches'])
       
       lines.append(f"   Showing matches {start_match}-{end_match} of {p['total_matches']} total")
       
       # Navigation hints
       if p['has_next']:
           lines.append(f"   → Use page={p['page'] + 1} to see next {p['page_size']} matches")
       if p['has_prev']:
           lines.append(f"   ← Use page={p['page'] - 1} to see previous matches")
       
       lines.append("")
   ```

3. **No other changes to formatter** - existing match rendering stays the same

#### Verification

- [ ] Manual test: `search(pattern="def", page=1, format="readable")` shows pagination header
- [ ] Header shows: "📄 Page 1/15" and "Showing matches 1-10 of 143 total"
- [ ] Navigation hints appear when applicable ("→ Use page=2 to see next...")
- [ ] Page 1 shows "→" hint but no "←" hint
- [ ] Last page shows "←" hint but no "→" hint
- [ ] Middle pages show both hints

#### Out of Scope
- Do NOT modify structured formatter
- Do NOT change match rendering logic

**Estimated Effort:** 1 hour

---

### Task Package 3.4: Add Unit Tests for Pagination
<!-- ID: task_3_4 -->

**Scope:** Test pagination math, edge cases, formatter

**Files to Modify:**
- `tests/test_search.py` (add to existing)

**Dependencies:** Tasks 3.1, 3.2, 3.3 must be complete

#### Specifications

1. **Add pagination math tests**:
   ```python
   def test_pagination_slice_logic():
       """Test basic pagination slicing."""
       matches = list(range(143))  # 143 matches
       page, page_size = 1, 10
       
       start_idx = (page - 1) * page_size  # 0
       end_idx = start_idx + page_size      # 10
       paginated = matches[start_idx:end_idx]
       
       assert len(paginated) == 10
       assert paginated == list(range(10))
   
   def test_pagination_last_page_partial():
       """Last page may have fewer than page_size matches."""
       matches = list(range(143))
       page, page_size = 15, 10  # Last page (143 / 10 = 14.3 → 15 pages)
       
       start_idx = (page - 1) * page_size  # 140
       end_idx = start_idx + page_size      # 150
       paginated = matches[start_idx:end_idx]
       
       assert len(paginated) == 3  # Only 3 matches left (143 - 140)
   
   def test_pagination_total_pages_calculation():
       """Total pages calculation."""
       # 143 matches, 10 per page → 15 pages
       total_pages = (143 + 10 - 1) // 10
       assert total_pages == 15
       
       # 100 matches, 10 per page → 10 pages
       total_pages = (100 + 10 - 1) // 10
       assert total_pages == 10
       
       # 1 match, 10 per page → 1 page
       total_pages = (1 + 10 - 1) // 10
       assert total_pages == 1
   ```

2. **Add edge case tests**:
   ```python
   def test_pagination_empty_results():
       """Pagination with zero matches."""
       matches = []
       total_matches = len(matches)
       total_pages = (total_matches + 10 - 1) // 10 if total_matches > 0 else 1
       
       assert total_pages == 1  # At least 1 page even if empty
   
   def test_pagination_page_clamping():
       """Page number should clamp to valid range."""
       total_pages = 5
       
       # Page too high → clamp to last page
       page = 99
       if page > total_pages:
           page = total_pages
       assert page == 5
       
       # Page too low → clamp to 1 (done in param validation)
       page = -1
       if page < 1:
           page = 1
       assert page == 1
   ```

3. **Add integration test**:
   ```python
   @pytest.mark.asyncio
   async def test_search_pagination_integration():
       """Full pagination integration test."""
       from tools.search import search
       
       # Page 1
       result = await search(
           agent="TestAgent",
           pattern="def",
           page=1,
           page_size=10,
           format="structured"
       )
       
       assert "pagination" in result
       assert result["pagination"]["page"] == 1
       assert result["pagination"]["page_size"] == 10
       assert len(result["matches"]) <= 10
       
       # If there are more results, test page 2
       if result["pagination"]["has_next"]:
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
           assert p1_lines.isdisjoint(p2_lines), "Pages should not overlap"
   ```

#### Verification

- [ ] `pytest tests/test_search.py -v` - all pagination tests pass
- [ ] Edge cases covered (empty results, page clamping, last page partial)
- [ ] Integration test verifies pages don't overlap

**Estimated Effort:** 1-2 hours

---

### Task Package 3.5: Update Documentation
<!-- ID: task_3_5 -->

**Scope:** Update tool docstring and examples

**Files to Modify:**
- `tools/search.py` (docstring only, around line 535-565)
- `docs/Scribe_Usage.md` (add pagination examples)

**Dependencies:** All Phase 3 tasks complete

#### Specifications

1. **Update `search()` docstring** (around line 535):
   - Add to parameters section:
     ```
     page (int): Page number for pagination (1-based). Default: 1.
     page_size (int): Number of matches per page. Default: 10, max: 100.
         Note: max_total_matches limits collection (up to 200),
         pagination controls display (10 per page).
     ```

2. **Add pagination examples to docstring**:
   ```python
   Examples:
       # Default: page 1, 10 matches
       search(agent="Agent", pattern="def")
       
       # Get page 2
       search(agent="Agent", pattern="def", page=2)
       
       # Show 20 matches per page
       search(agent="Agent", pattern="def", page_size=20)
       
       # Navigate: Page 3 of large result set
       search(agent="Agent", pattern="import", page=3, page_size=15)
   ```

3. **Update `docs/Scribe_Usage.md`** - add search pagination section:
   ```markdown
   ### search() Pagination
   
   The `search()` tool supports pagination for large result sets:
   
   - `page` (int): Page number (1-based), default: 1
   - `page_size` (int): Matches per page, default: 10, max: 100
   - Response includes `pagination` metadata with navigation hints
   
   **Example:**
   ```python
   # Page through results
   result = search(agent="Agent", pattern="def", page=1, page_size=10)
   # Readable format shows: "📄 Page 1/15, showing matches 1-10 of 143 total"
   ```
   ```

#### Verification

- [ ] Docstring updated with pagination parameters
- [ ] Examples added to docstring
- [ ] `docs/Scribe_Usage.md` updated with pagination section
- [ ] Documentation review - clear and accurate

**Estimated Effort:** 30 minutes

---

## Phase Completion Criteria
<!-- ID: completion_criteria -->

### Phase 1 Complete When:
- [ ] All Phase 1 task packages verified
- [ ] Unit tests passing (test_logs.py, test_search.py)
- [ ] Manual verification: `query_entries("template")` returns results
- [ ] Manual verification: `search("def")` response size <500KB
- [ ] Code review complete
- [ ] Committed with message: `fix: query_entries template filter + search line truncation`
- [ ] Deployed to production
- [ ] No errors in production logs for 24 hours

### Phase 2 Complete When:
- [ ] All Phase 2 task packages verified
- [ ] Integration tests passing (test_query_entries.py, test_performance.py)
- [ ] Manual verification: `query_entries` returns same results as `read_recent`
- [ ] Manual verification: Cross-project search still works
- [ ] Performance benchmark: queries <100ms
- [ ] Code review complete
- [ ] Committed with message: `feat: migrate query_entries to storage backend`
- [ ] Deployed to production
- [ ] Monitored for 48 hours - no errors, no performance degradation

### Phase 3 Complete When:
- [ ] All Phase 3 task packages verified
- [ ] Unit and integration tests passing (pagination tests)
- [ ] Manual verification: Pagination works in readable format
- [ ] Manual verification: Structured response includes pagination metadata
- [ ] Documentation updated (docstring, Scribe_Usage.md)
- [ ] Code review complete
- [ ] Committed with message: `feat: add pagination support to scribe.search`
- [ ] Deployed to production
- [ ] User feedback collected - pagination UX acceptable

---

## Rollback Plan
<!-- ID: rollback_plan -->

### Phase 1 Rollback
**If issues detected:** `git revert <commit_hash>`  
**Impact:** None (no schema changes, no data changes)  
**Time:** <5 minutes

### Phase 2 Rollback
**Option 1:** Add environment variable `USE_DB_QUERIES=false` (instant)  
**Option 2:** `git revert <commit_hash>`  
**Impact:** Falls back to flat-file parsing (Phase 1 fixes still active)  
**Time:** <5 minutes

### Phase 3 Rollback
**If issues detected:** `git revert <commit_hash>`  
**Impact:** None (backwards compatible - new params have defaults)  
**Time:** <5 minutes  
**Note:** Phase 1 and Phase 2 fixes remain active

---

## Risk Mitigation
<!-- ID: risk_mitigation -->

| Risk | Phase | Mitigation | Monitoring |
|------|-------|------------|------------|
| Template filter too permissive | 1 | Unit tests verify multi-indicator filtering | Log filtered entries in debug mode |
| Template filter still too strict | 1 | Phase 2 bypasses filter entirely with DB | User reports, empty result analysis |
| DB query fails | 2 | Automatic fallback to flat-file parsing | Error logs, fallback counter metric |
| Performance regression | 2 | Benchmark tests, performance monitoring | Query latency metrics (<100ms target) |
| Pagination math errors | 3 | Comprehensive unit tests for edge cases | Integration tests, manual QA |
| Page parameter abuse | 3 | Validation clamping (page_size max=100) | Parameter validation logs |

---

**End of Phase Plan**
