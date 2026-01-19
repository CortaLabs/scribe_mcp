# Research: read_recent and query_entries Tool Behavior & Readability

**Project**: scribe_tool_output_refinement
**Research Goal**: Investigate log query tools for behavior improvements AND readable output design
**Date**: 2026-01-03
**Agent**: ResearchAgent
**Confidence**: 0.95

---

## Executive Summary

This research investigates `read_recent` and `query_entries` tools with a **dual focus**:
1. **Tool Behavior**: Default parameters, pagination, and usability issues
2. **Readability Design**: Output formatting for dense log files

### Key Findings

1. **Default page_size=50 is too high** - Overwhelming data dump for quick scans
2. **Existing readable format exists** - `ResponseFormatter.format_readable_log_entries` already implemented (ASCII tables)
3. **Log density is extreme** - Auto-generated entries are 500-800 chars each with UUIDs and extensive metadata
4. **Reasoning block parsing works** - Existing `_parse_reasoning_block` method handles structured reasoning
5. **Both tools use same output pipeline** - Both call `LoggingToolMixin.success_with_entries` → `ResponseFormatter.format_response`

---

## Part 1: Current Implementation Analysis

### 1.1 read_recent.py (502 lines)

**File**: `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/read_recent.py`

**Current Defaults:**
```python
async def read_recent(
    project: Optional[str] = None,
    n: Optional[Any] = None,              # Legacy parameter
    limit: Optional[Any] = None,           # Alias for n
    filter: Optional[Dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 50,                   # ⚠️ DEFAULT: 50 entries
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
)
```

**Key Observations:**
- **Default page_size=50**: Returns 50 entries by default - far too many for quick scanning
- **Legacy n parameter**: Overrides page_size when provided (backward compatibility)
- **Parameter healing**: Extensive healing via `ParameterTypeEstimator.heal_comparison_operator_bug`
- **Token budget management**: Uses `TokenBudgetManager.truncate_response_to_budget`
- **Pagination support**: Full pagination with `create_pagination_info(page, page_size, total_count)`
- **Output formatting**: Calls `LoggingToolMixin.success_with_entries()` which routes to `ResponseFormatter.format_response()`

**Execution Flow:**
```
read_recent()
  → heal_parameters_with_exception_handling()
  → backend.fetch_recent_entries_paginated(page, page_size)
  → success_with_entries(entries, context, compact, fields, pagination)
  → ResponseFormatter.format_response()
  → TokenBudgetManager.truncate_response_to_budget()
```

### 1.2 query_entries.py (1961 lines)

**File**: `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/query_entries.py`

**Current Defaults:**
```python
async def query_entries(
    project: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    message: Optional[str] = None,
    message_mode: str = "substring",       # ⚠️ DEFAULT
    case_sensitive: bool = False,
    emoji: Optional[List[str]] = None,
    status: Optional[List[str]] = None,
    agents: Optional[List[str]] = None,
    meta_filters: Optional[Dict[str, Any]] = None,
    limit: int = 50,                       # ⚠️ DEFAULT: 50 entries
    page: int = 1,
    page_size: int = 50,                   # ⚠️ DEFAULT: 50 entries
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
    # Phase 4 Enhanced Search Parameters
    search_scope: str = "project",         # ⚠️ DEFAULT
    document_types: Optional[List[str]] = None,
    include_outdated: bool = True,
    verify_code_references: bool = False,
    time_range: Optional[str] = None,
    relevance_threshold: float = 0.0,
    max_results: Optional[int] = None,
    config: Optional[QueryEntriesConfig] = None,
)
```

**Key Observations:**
- **Default limit=50, page_size=50**: Both default to 50 (same issue as read_recent)
- **Message mode default**: `"substring"` (reasonable)
- **Search scope default**: `"project"` (safe default, not cross-project)
- **Massive complexity**: 1961 lines with extensive parameter healing
  - `BulletproofParameterCorrector`
  - `ExceptionHealer`
  - `BulletproofFallbackManager`
- **Phase 4 enhanced search**: Cross-project search, document types, relevance scoring
- **Output formatting**: Same `success_with_entries()` → `ResponseFormatter.format_response()` pipeline

**Execution Flow:**
```
query_entries()
  → _validate_search_parameters() [BulletproofParameterCorrector]
  → resolve_logging_context()
  → _build_search_query()
  → _execute_search_with_fallbacks()
    → _search_single_project() / _handle_cross_project_search()
    → parse_log_line() + filter application
    → pagination
  → success_with_entries(entries, context, compact, fields, pagination)
  → ResponseFormatter.format_response()
```

### 1.3 Output Structure (Current)

**Both tools return structured JSON via `ResponseFormatter.format_response()`:**

```python
{
    "ok": True,
    "entries": [
        {
            "id": "...",
            "timestamp": "2026-01-03T03:22:00+00:00",
            "emoji": "ℹ️",
            "agent": "ResearchAgent",
            "message": "Investigation complete",
            "meta": {
                "phase": "research",
                "confidence": 0.95,
                "reasoning": {"why": "...", "what": "...", "how": "..."}
            }
        },
        # ... 49 more entries by default
    ],
    "count": 50,
    "pagination": {
        "page": 1,
        "page_size": 50,
        "total_count": 247,
        "has_next": True,
        "has_prev": False
    },
    "recent_projects": [...],
    "reminders": [...]
}
```

**Issues with current structured format:**
- Deeply nested JSON (ok → entries → [array] → fields)
- Metadata mixed with content
- No visual hierarchy
- Requires mental parsing of JSON structure
- 50 entries = overwhelming JSON blob

---

## Part 2: Log Density Analysis

### 2.1 Real Progress Log Sample

**Source**: `.scribe/docs/dev_plans/scribe_sentinel_concurrency_v1/PROGRESS_LOG.md` (last 10 entries)

**Auto-generated read_file entry (782 chars):**
```
[ℹ️] [2026-01-02T11:47:45.593192+00:00] [Agent: a4b53654-fafd-48d2-8846-abeae72d565c] [Project: scribe_sentinel_concurrency_v1] read_file | execution_id=6aaf34c4-5782-4a15-8572-cf96ad8a4191; session_id=a86ac8e8-9099-437f-82a7-f9b958fd5775; intent=tool:read_file; agent_kind=other; agent_instance_id=a4b53654-fafd-48d2-8846-abeae72d565c; agent_sub_id=None; agent_display_name=None; agent_model=None; read_mode=line_range; line_start=110; line_end=160; absolute_path=/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/vector_indexer.py; repo_relative_path=plugins/vector_indexer.py; byte_size=34987; line_count=852; sha256=0fe34895a5d5199ce97d4c718a066c6b99acf004ce4794f950b05173ccd168eb; newline_type=LF; encoding=utf-8; estimated_chunk_count=5
```

**Agent-written entry with reasoning (694 chars):**
```
[✅] [2026-01-02 11:48:27 UTC] [Agent: Codex] [Project: scribe_sentinel_concurrency_v1] Fixed VectorIndexer._stop_background_processing to cancel/await the queue worker on the dedicated loop, clear queue_worker_task, and avoid stale tasks that block restart after rebuild. reasoning: {"why":"Reindex rebuild left embeddings unprocessed because the queue worker never restarted; stop/start logic kept a non-done task reference.","what":"Constraints: keep dedicated loop support; avoid blocking when loop is closed; ensure safe cancellation without crashing.","how":"Updated _stop_background_processing to handle owned-loop cancellation via run_coroutine_threadsafe, clear queue_worker_task, and fall back to current loop cancellation."} | action=code_change; files_changed=["plugins/vector_indexer.py"]; topic=vector_indexer_worker_restart_fix; log_type=progress; content_type=log
```

**Observations:**
- **Auto-generated entries**: 500-800 chars with UUIDs, execution IDs, sha256 hashes, extensive metadata
- **Agent-written entries**: 400-700 chars with reasoning blocks (JSON-embedded)
- **UUID agent IDs**: `a4b53654-fafd-48d2-8846-abeae72d565c` adds noise
- **ISO timestamps**: Full precision `2026-01-02T11:47:45.593192+00:00` (verbose)
- **Default 50 entries**: 50 × 600 chars = 30,000 chars of dense text

**Readability Problems:**
1. **Visual scanning impossible** - No line breaks, everything on single lines
2. **Key information buried** - Message hidden after timestamp/agent/project brackets
3. **Metadata pollution** - UUIDs and IDs clutter the view
4. **Reasoning blocks unreadable** - JSON strings not parsed for display

---

## Part 3: Existing Readable Format Infrastructure

### 3.1 ResponseFormatter.format_readable_log_entries

**File**: `/home/austin/projects/MCP_SPINE/scribe_mcp/utils/response.py` (lines 584-635)

**Existing implementation:**
```python
def format_readable_log_entries(self, entries: List[Dict], pagination: Dict) -> str:
    """Format log entries in readable table format."""
    if not entries:
        return "No log entries found."

    # Build header metadata
    header_meta = {
        'total_entries': pagination.get('total_count', len(entries)),
        'page': pagination.get('page', 1),
        'page_size': pagination.get('page_size', len(entries))
    }

    # Build table
    headers = ['Time', 'Agent', 'Status', 'Message']
    rows = []
    for entry in entries:
        timestamp = entry.get('timestamp', '')
        # Shorten timestamp to time only
        if 'T' in timestamp:
            timestamp = timestamp.split('T')[1].split('.')[0]  # HH:MM:SS

        agent = entry.get('agent', '')[:12]  # Truncate long names
        emoji = entry.get('emoji', '')
        status = entry.get('status', 'info')
        message = entry.get('message', '')[:60]  # Truncate long messages

        rows.append([timestamp, agent, f"{emoji} {status}", message])

    # Build readable output
    parts = []
    parts.append(self._create_header_box("LOG ENTRIES", header_meta))
    parts.append("")
    parts.append(self._format_table(headers, rows))
    parts.append("")
    parts.append(self._create_footer_box(footer_meta))

    return '\n'.join(parts)
```

**Format Output:**
```
╔══════════════════════════════════════════════════════════╗
║ LOG ENTRIES                                              ║
╟──────────────────────────────────────────────────────────╢
║ total_entries: 247                                       ║
║ page: 1                                                  ║
║ page_size: 50                                            ║
╚══════════════════════════════════════════════════════════╝

┌────────────┬──────────────┬─────────────┬─────────────────────────────┐
│ Time       │ Agent        │ Status      │ Message                     │
├────────────┼──────────────┼─────────────┼─────────────────────────────┤
│ 03:22:00   │ ResearchAgen │ ℹ️ info     │ Investigation initiated     │
│ 03:22:15   │ ResearchAgen │ ℹ️ info     │ Analyzed read_recent.py ... │
│ 03:22:30   │ ResearchAgen │ ✅ success  │ Analysis complete           │
└────────────┴──────────────┴─────────────┴─────────────────────────────┘

╔══════════════════════════════════════════════════════════╗
║ METADATA                                                 ║
╟──────────────────────────────────────────────────────────╢
║ showing: 50 of 247                                       ║
║ has_more: True                                           ║
╚══════════════════════════════════════════════════════════╝
```

**Existing Helper Methods:**
- `_create_header_box(title, metadata)` - ASCII box with metadata
- `_create_footer_box(audit_data, reminders)` - Bottom metadata box
- `_format_table(headers, rows)` - ASCII table with box drawing
- `_add_line_numbers(content, start)` - Line numbering utility
- `_parse_reasoning_block(meta)` - Parse JSON reasoning into dict

**Limitations of current table format:**
- **Truncates messages at 60 chars** - Loses important detail
- **Truncates agents at 12 chars** - Cuts UUID agents
- **No reasoning block display** - Ignores parsed reasoning
- **Time only** - Loses date context
- **No metadata visibility** - meta field completely hidden
- **Fixed column widths** - Doesn't adapt to terminal size

---

## Part 4: Readability Design Proposals

### 4.1 Proposal: Enhanced Table Format with Expandable Rows

**Keep existing ASCII table but add:**

1. **Smarter truncation with ellipsis indicators**
2. **Reasoning block section** after table
3. **Metadata summary** in footer
4. **Entry detail view option** (show full entry on demand)

**Example Enhanced Format:**
```
╔══════════════════════════════════════════════════════════════════════════╗
║ LOG ENTRIES                                                              ║
╟──────────────────────────────────────────────────────────────────────────╢
║ showing: 10 of 247 entries (page 1/5)                                   ║
║ scope: scribe_tool_output_refinement project                            ║
╚══════════════════════════════════════════════════════════════════════════╝

┌──────────┬──────────────┬─────────┬────────────────────────────────────────┐
│ Time     │ Agent        │ Status  │ Message                                │
├──────────┼──────────────┼─────────┼────────────────────────────────────────┤
│ 03:22:00 │ ResearchAg…  │ ℹ️ info │ Investigation initiated (phase=rese…)  │
│ 03:22:15 │ ResearchAg…  │ ℹ️ info │ Analyzed read_recent.py (502 lines)    │
│ 03:22:30 │ ResearchAg…  │ ✅ ok   │ Analysis complete (confidence=0.95)    │
└──────────┴──────────────┴─────────┴────────────────────────────────────────┘

Reasoning Traces (3 entries with reasoning):
  [03:22:00] Investigation initiated
   ├─ Why: User requested dual focus on behavior and readability
   ├─ What: Investigating read_recent.py and query_entries.py defaults
   └─ How: Systematic file reading, parameter analysis, format mockups

  [03:22:30] Analysis complete
   ├─ Why: Need comprehensive understanding before design proposals
   ├─ What: Documented defaults, output structure, log density issues
   └─ How: Read source code, sampled real logs, traced execution flow

╔══════════════════════════════════════════════════════════════════════════╗
║ PAGINATION                                                               ║
╟──────────────────────────────────────────────────────────────────────────╢
║ page: 1/5 (50 entries per page)                                         ║
║ next: query_entries(page=2) to see more                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### 4.2 Proposal: Condensed List Format (Alternative)

**Optimized for quick scanning:**

```
LOG ENTRIES (10 of 247) | Page 1/5 | Project: scribe_tool_output_refinement
─────────────────────────────────────────────────────────────────────────────

 1. ℹ️  03:22:00  ResearchAgent     Investigation initiated
    → phase=research; scope=log_query_tools

 2. ℹ️  03:22:15  ResearchAgent     Analyzed read_recent.py (502 lines)
    → file=read_recent.py; default_page_size=50; uses_success_with_entries

 3. ✅  03:22:30  ResearchAgent     Analysis complete
    → confidence=0.95; tools_analyzed=2
    └─ Reasoning: Need comprehensive understanding before design proposals

─────────────────────────────────────────────────────────────────────────────
Showing 10 entries | Use query_entries(page=2) for more
```

**Benefits:**
- **Numbered entries** - Easy reference
- **Hierarchical metadata** - Indented with → and └─
- **Selective reasoning** - Only shown when present
- **Compact timestamps** - Time only, date in header
- **Scannable emoji** - Visual status indicators

### 4.3 Design Decisions Needed

**Questions for Architect/User:**

1. **Table vs List format?**
   - Table: Structured, aligned columns (current approach)
   - List: More compact, hierarchical metadata

2. **Reasoning block display:**
   - Separate section after table (Proposal 4.1)
   - Inline with each entry (Proposal 4.2)
   - Expandable on demand (future enhancement)

3. **Default entry count:**
   - Current: 50 (too high)
   - Proposed: 10-15 for quick scans
   - Full page: 25-30 for detailed review

4. **Metadata visibility:**
   - Show key metadata inline (phase, confidence)
   - Hide verbose metadata (UUIDs, execution_ids)
   - Option to expand full metadata

5. **ANSI colors:**
   - YES for display-heavy tools like query/read
   - NO for confirmations (append_entry pattern)
   - Configurable via repo config (already supported)

---

## Part 5: Tool Behavior Improvement Recommendations

### 5.1 read_recent Behavior Changes

**Current Issues:**
- Default page_size=50 is overwhelming
- No "tail mode" (newest first by default)
- Legacy n parameter confusing

**Recommended Changes:**

| Parameter | Current Default | Proposed Default | Rationale |
|-----------|----------------|------------------|-----------|
| `page_size` | 50 | **10** | Quick scan default |
| `page` | 1 | 1 (no change) | Standard pagination |
| `compact` | False | False (no change) | Readable is default |
| **NEW: `tail`** | N/A | **True** | Newest entries first (most common use case) |

**Proposed Function Signature:**
```python
async def read_recent(
    project: Optional[str] = None,
    n: Optional[Any] = None,              # Legacy (deprecated)
    limit: Optional[Any] = None,          # Alias for n
    filter: Optional[Dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 10,                  # CHANGED: 50 → 10
    tail: bool = True,                     # NEW: newest first
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
    format: str = "readable",              # NEW: default to readable
)
```

**Tail Mode Implementation:**
```python
# When tail=True, reverse pagination
if tail:
    # Get last page first
    total_pages = math.ceil(total_count / page_size)
    effective_page = total_pages - page + 1
    rows = list(reversed(rows))  # Show newest first
```

### 5.2 query_entries Behavior Changes

**Current Issues:**
- Default limit=50 AND page_size=50 (redundant, confusing)
- No smart defaults for common queries
- Relevance_threshold=0.0 (disables scoring by default)

**Recommended Changes:**

| Parameter | Current Default | Proposed Default | Rationale |
|-----------|----------------|------------------|-----------|
| `limit` | 50 | **None** | Use page_size instead |
| `page_size` | 50 | **10** | Quick scan default |
| `relevance_threshold` | 0.0 | **0.0** | (no change - safe default) |
| `search_scope` | "project" | "project" (no change) | Safe default |
| **NEW: `format`** | N/A | **"readable"** | Readable is default |

**Deprecation Note:**
```python
# Deprecate `limit` parameter in favor of `page_size`
if limit is not None and limit != page_size:
    # Log deprecation warning
    logger.warning("Parameter 'limit' is deprecated, use 'page_size' instead")
    page_size = limit  # Backward compatibility
```

### 5.3 Reasoning Trace Extraction Enhancement

**Current:** `_parse_reasoning_block(meta)` exists but not used in log display

**Proposed:** Always parse and display reasoning when present

```python
def _should_show_reasoning(entry: Dict) -> bool:
    """Determine if entry has valuable reasoning to display."""
    meta = entry.get('meta', {})
    reasoning = _parse_reasoning_block(meta)

    if not reasoning:
        return False

    # Show reasoning if any section has meaningful content
    return any(
        reasoning.get(key) and len(reasoning.get(key, '')) > 10
        for key in ['why', 'what', 'how']
    )
```

### 5.4 Dense Log Handling Strategy

**Problem:** Auto-generated entries (read_file, etc.) are 500-800 chars

**Solutions:**

1. **Smart Truncation:**
   ```python
   def _truncate_message(message: str, max_length: int = 80) -> str:
       if len(message) <= max_length:
           return message

       # Try to truncate at word boundary
       truncated = message[:max_length - 3]
       last_space = truncated.rfind(' ')
       if last_space > max_length * 0.7:  # At least 70% of desired length
           truncated = truncated[:last_space]

       return truncated + "..."
   ```

2. **Metadata Folding:**
   ```python
   def _summarize_metadata(meta: Dict) -> str:
       """Create compact metadata summary."""
       summary_keys = ['phase', 'confidence', 'action', 'file']
       parts = []
       for key in summary_keys:
           if key in meta:
               value = meta[key]
               if isinstance(value, float):
                   parts.append(f"{key}={value:.2f}")
               else:
                   parts.append(f"{key}={value}")
       return "; ".join(parts)
   ```

3. **Collapsible Sections (Future):**
   - Show summary line by default
   - Expand full entry on demand
   - Requires interactive mode or follow-up query

---

## Part 6: Implementation Checklist

### 6.1 Behavior Improvements (Priority: HIGH)

- [ ] **Change default page_size from 50 to 10** in both tools
- [ ] **Add `tail=True` parameter to read_recent** (newest first)
- [ ] **Add `format="readable"` parameter** to both tools (default)
- [ ] **Deprecate `limit` parameter** in query_entries (use page_size)
- [ ] **Update parameter healing** to handle new defaults

### 6.2 Readability Enhancements (Priority: MEDIUM)

- [ ] **Enhance format_readable_log_entries**:
  - [ ] Better message truncation (80 chars with word boundary)
  - [ ] Show reasoning blocks when present
  - [ ] Display key metadata inline (phase, confidence)
  - [ ] Improve pagination display (X of Y format)
- [ ] **Add condensed list format** as alternative to table
- [ ] **Implement smart metadata summarization**
- [ ] **Test ANSI colors with repo config integration**

### 6.3 Testing Requirements (Priority: MEDIUM)

- [ ] **Unit tests for new defaults**
- [ ] **Integration tests for tail mode**
- [ ] **Visual validation tests** for readable formats
- [ ] **Backward compatibility tests** for legacy parameters
- [ ] **Performance tests** (ensure ≤5ms overhead for formatting)

### 6.4 Documentation Updates (Priority: LOW)

- [ ] **Update tool docstrings** with new defaults
- [ ] **Add usage examples** for common queries
- [ ] **Document deprecated parameters**
- [ ] **Create visual format samples** in docs

---

## Part 7: Open Questions

1. **Should we add `detail=True` parameter** to show full entry on demand?
2. **How to handle UUID agent IDs** in display? Truncate? Alias?
3. **Should reasoning traces be expandable/collapsible?** (requires interactive mode)
4. **Date context in timestamps**: Show date when crossing day boundaries?
5. **Pagination command hints**: Show exact command to get next page?
6. **Cross-project results**: How to display project boundaries in results?
7. **Search highlighting**: Should matched terms be highlighted (ANSI colors)?
8. **Entry numbering**: Global (1-247) or page-relative (1-10)?

---

## Part 8: References

### Source Files Analyzed

1. **`tools/read_recent.py`** (502 lines) - Default page_size=50, pagination, parameter healing
2. **`tools/query_entries.py`** (1961 lines) - Massive complexity, Phase 4 enhanced search, same defaults
3. **`utils/response.py`** (1216 lines) - ResponseFormatter with existing format_readable_log_entries
4. **`shared/base_logging_tool.py`** (140 lines) - LoggingToolMixin.success_with_entries pipeline
5. **Sample log**: `.scribe/docs/dev_plans/scribe_sentinel_concurrency_v1/PROGRESS_LOG.md`

### Key Line References

- **read_recent defaults**: `tools/read_recent.py:152-162`
- **query_entries defaults**: `tools/query_entries.py:957-985`
- **format_readable_log_entries**: `utils/response.py:584-635`
- **success_with_entries**: `shared/base_logging_tool.py:85-104`
- **_parse_reasoning_block**: `utils/response.py:760-789`
- **_create_header_box**: `utils/response.py:279-348`
- **_format_table**: `utils/response.py:437-490`

### Architecture Context

- **Phase 2 (append_entry)**: Already implemented readable format with reasoning block parsing, NO ANSI colors
- **Phase 3 (current)**: Extending readable format to log query tools with DIFFERENT design (display-heavy = colors OK)
- **ResponseFormatter infrastructure**: Already has all box-drawing and formatting utilities needed

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|-----------|-------|
| Current defaults documentation | 0.95 | Verified from source code |
| Output structure analysis | 0.95 | Traced execution flow |
| Log density findings | 1.0 | Sampled real logs |
| Existing infrastructure | 0.95 | Read ResponseFormatter completely |
| Behavior recommendations | 0.9 | Based on solid analysis but need user validation |
| Readability design | 0.85 | Mockups not user-tested |
| Implementation complexity | 0.8 | Depends on final design choices |

---

**Next Stage**: Hand off to Architect Agent for design decisions and implementation plan.
