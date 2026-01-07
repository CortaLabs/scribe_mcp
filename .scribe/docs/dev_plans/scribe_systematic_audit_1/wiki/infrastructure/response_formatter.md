# Base Infrastructure: Response Formatter (TOKEN-001 SOURCE)

**File**: `utils/response.py`
**LOC**: 2424
**Complexity**: Very High (13+ specialized formatters + box-drawing infrastructure)
**Relationships**: Used by ALL tools via LoggingToolMixin.success_with_entries()

---

## 1. Overview

Response formatter is the **TOKEN-001 root cause**—a 2424-line monolithic formatter providing box-drawing, ANSI colors, line numbering, and specialized output for every tool type (read_file, list_projects, get_project, read_recent, query_entries, append_entry, errors).

**NOTE FROM DEVELOPER:** I want to have our config easily customize the complexity and token expensive settings.   Specifically for how we format messages.  We need a LOW token mode, and each level of token density is easily changed, without removing important human readable modes.

**Purpose**: Single source of truth for ALL tool output formatting:
- Readable format (boxes, tables, colors) for Claude Code display
- Structured format (JSON) for programmatic parsing
- Compact format (minimal tokens) for token optimization
- Both format (TextContent + structuredContent) for MCP Issue #9962 workaround

**Critical Observation**: Every tool output routes through `default_formatter` singleton (lines 2422-2424). Changes to response.py affect ALL tool token costs.

---

## 2. Sub-System Breakdown

### 2.1 ResponseFormatter Class Definition (Lines 57-104)
**Responsibility**: Class constants, initialization, token estimator
**Key fields**:
- `FORMAT_READABLE`, `FORMAT_STRUCTURED`, `FORMAT_COMPACT`, `FORMAT_BOTH` (Phase 0 constants)
- `ANSI_*` color codes (cyan, green, yellow, blue, magenta, bold, dim, reset)
- `USE_COLORS` property (loads from `.scribe/config/scribe.yaml`)
- `COMPACT_FIELD_MAP` (short field aliases: `id→i`, `message→m`, `timestamp→t`)
- `COMPACT_DEFAULT_FIELDS` (id, message, timestamp, emoji, agent)

**Token estimator** (line 104): Delegates to `TokenEstimator` from utils/estimator.py

### 2.2 Entry Formatting (Lines 106-187)
**Responsibility**: Format individual log entries (compact vs full)
**Methods**:
- `format_entry()` (lines 112-127): Route to compact/full based on flag
- `_format_full_entry()` (lines 129-146): Copy all fields (or selected fields)
- `_format_compact_entry()` (lines 149-187): Map to short names, truncate messages

**Compact transformations**:
- Timestamps: `"2026-01-03T08:15:30Z"` → `"2026-01-03"` (date only)
- Messages: Truncate to 100 chars with `"..."`
- Field names: `timestamp → t`, `message → m`, `emoji → e`, `agent → a`

### 2.3 General Response Formatting (Lines 189-241)
**Responsibility**: Build response with entries + pagination + token warning
**Method**: `format_response(entries, compact, fields, include_metadata, pagination, extra_data)`

**Response structure**:
```python
{
    "ok": True,
    "entries": [formatted_entries],
    "count": len(entries),
    "compact": True,  # If compact mode
    "pagination": {...},  # If provided
    "token_warning": {...}  # If estimated_tokens > threshold
}
```

**Token warning** (lines 233-239): Adds warning if estimated tokens > 4000 (default threshold)

### 2.4 Box-Drawing Infrastructure (Lines 243-438)

#### _add_line_numbers (Lines 245-279)
**Responsibility**: Add green line numbers to content (Claude Read style)
**Format**: `"     1. Line content"` (5-char minimum width, right-aligned)
**ANSI colors**: Green line numbers if `USE_COLORS` enabled

#### _create_header_box (Lines 281-350)
**Responsibility**: ASCII box with title + metadata (80-char width)
**Format**:
```
╔══════════════════════════════════════════════════════════╗
║ TITLE (bold)                                            ║
╟──────────────────────────────────────────────────────────╢
║ key1: value1 (key in green)                            ║
║ key2: value2                                            ║
╚══════════════════════════════════════════════════════════╝
```
**Token cost**: ~20-30 tokens per box (borders + title + metadata)

#### _create_footer_box (Lines 352-438)
**Responsibility**: Metadata + reminders footer box
**Token cost**: ~30-50 tokens (metadata) + ~15 tokens per reminder

#### _format_table (Lines 440-493)
**Responsibility**: ASCII table with borders
**Format**:
```
┌──────────┬──────────┬──────────┐
│ Header1  │ Header2  │ Header3  │
├──────────┼──────────┼──────────┤
│ value1   │ value2   │ value3   │
└──────────┴──────────┴──────────┘
```
**Token cost**: ~10 tokens per row + border overhead

### 2.5 read_file Formatting (Lines 497-605)
**Responsibility**: Format read_file output (scan/chunk/page/search modes)
**Method**: `format_readable_file_content(data)`

**Structure**:
```
READ FILE filename.xyz | Lines read: 100-243

[line-numbered content]

───────────────────────────────────────────────────────────────
Path: .../filename.xyz
Size: 12345 bytes | Total lines: 500 | Encoding: utf-8
SHA256: abc123...
```

**Token cost**: ~200-400 tokens (metadata + line numbers + separators)

### 2.6 read_recent/query_entries Formatting (Lines 607-799)
**Responsibility**: Format log entries with reasoning blocks
**Method**: `format_readable_log_entries(entries, pagination, search_context, project_name)`

**Phase 3a enhancements** (documented in docstring):
- Parse `meta.reasoning` blocks as tree structure
- Smarter message truncation at word boundaries
- Compact timestamp format (HH:MM)
- Better pagination display (Page X of Y)

**Structure**:
```
╔═══════════════════════════════════════════════════════════════╗
║ 📋 RECENT LOG ENTRIES (project_name) Page 1 of 3 (50/150)    ║
╚═══════════════════════════════════════════════════════════════╝

[emoji] HH:MM | agent | message
    ├─ Why: reasoning.why (if present)
    ├─ What: reasoning.what
    └─ How: reasoning.how

───────────────────────────────────────────────────────────────
📁 Progress log entries
```

**Token cost**: ~150 tokens (header box) + ~30 tokens per entry + ~40 tokens per reasoning block

### 2.7 list_projects Multi-Format (Lines 821-1489)

#### format_readable_projects (Lines 821-868) - LEGACY
**Responsibility**: Old box + table format (pre-token optimization)
**Token cost**: ~400-600 tokens (header box + table + footer box)

#### format_projects_table (Lines 1123-1233) - NEW
**Responsibility**: Minimal table for 2+ projects (Phase 1/2 optimization)
**Structure**:
```
╔══════════════════════════════════════════════════════════╗
║ 📋 PROJECTS - 5 total (Page 1 of 1, showing 5)          ║
╚══════════════════════════════════════════════════════════╝

NAME                      STATUS        ENTRIES  LAST ACTIVITY
──────────────────────────────────────────────────────────────
⭐ active_project          in_progress       298  2 hours ago
  other_project           planning            5  1 day ago
```
**Token cost**: ~200 tokens (50% reduction from legacy format)

#### format_project_detail (Lines 1235-1426) - NEW
**Responsibility**: Deep dive for single project (Phase 1/2 optimization)
**Token cost**: ~400 tokens (with doc status, activity, tags)

#### format_no_projects_found (Lines 1428-1489) - NEW
**Responsibility**: Empty state with helpful suggestions
**Token cost**: ~100 tokens

### 2.8 get_project Context Formatting (Lines 1491-1700+)
**Responsibility**: Format current project context with recent entries
**Method**: `format_project_context(project, recent_entries, docs_info, activity)`

**Structure**:
```
╔══════════════════════════════════════════════════════════╗
║ 🎯 CURRENT PROJECT: project_name                        ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /path/to/repo
  Dev Plan: .scribe/docs/dev_plans/project_name/

📄 Documents:
  • ARCHITECTURE_GUIDE.md (1274 lines)
  • PHASE_PLAN.md (542 lines)
  • CHECKLIST.md (356 lines)
  • PROGRESS_LOG.md (298 entries)

📊 Recent Activity (last 5 entries):
[HH:MM] agent | message
    ├─ Why: ...
    ├─ What: ...
    └─ How: ...
```

**Token cost**: ~300 tokens (context box) + ~150 tokens (5 recent entries with reasoning)

### 2.9 Helper Methods (Lines 800-1042+)
- `_truncate_message_smart()`: Word boundary truncation
- `_parse_reasoning_block()`: Extract reasoning JSON from meta
- `_format_relative_time()`: "2 hours ago" formatting
- `_get_doc_line_count()`: Efficient line counting
- `_detect_custom_content()`: Scan research/ and bugs/ directories

---

## 3. Modularization Notes

### Extractable Module: BoxDrawing [BUCKET:formatting]
**Origin**: Lines 245-493 (box/table/line-numbering infrastructure)
**Responsibilities**: ASCII boxes, tables, line numbers, ANSI colors
**Used by**: All 13+ format methods
**Why extractable**: Pure presentation logic, no business rules
**Before/After**:
- Before: 250 lines of box-drawing scattered in response.py
- After: `BoxDrawer.create_header_box()`, `BoxDrawer.format_table()`, `BoxDrawer.add_line_numbers()`
- Conceptual win: Formatters focus on WHAT to display, BoxDrawer handles HOW

### Extractable Module: ProjectFormatter [BUCKET:formatting]
**Origin**: Lines 1123-1700+ (list_projects + get_project formats)
**Responsibilities**: Project table, project detail, project context, empty state
**Used by**: list_projects, get_project tools
**Why extractable**: Project-specific formatting logic (50%+ of response.py)
**Estimated LOC**: ~600 lines

### Extractable Module: LogFormatter [BUCKET:formatting]
**Origin**: Lines 607-799 (log entries + reasoning blocks)
**Responsibilities**: Format log entries, parse reasoning, timestamp formatting
**Used by**: read_recent, query_entries tools
**Why extractable**: Log-specific formatting with reasoning tree rendering

### Extractable Module: FileFormatter [BUCKET:formatting]
**Origin**: Lines 497-605 (read_file output)
**Responsibilities**: Format file content with line numbers, metadata footer
**Used by**: read_file tool only
**Why extractable**: Single-purpose formatter

### NOT Extractable: ResponseFormatter Base Class
**Why it should stay**:
- **Singleton pattern**: default_formatter used by ALL tools
- **Common infrastructure**: Token estimation, compact/full routing, ANSI color config
- **Coordination layer**: Routes to specialized formatters

---

## 4. Implicit Contracts

### Contract 1: default_formatter Singleton Stability
**Assumption**: `default_formatter` initialized at module load (line 2422-2424)
**Violation consequence**: All tools import this singleton, module reload breaks state
**Why this is risky**: No lazy initialization, immediate module-level execution

### Contract 2: ANSI Colors Config-Driven
**Assumption**: `USE_COLORS` property loads from `.scribe/config/scribe.yaml`
**Violation consequence**: If config unavailable, falls back to True (colors enabled)
**Why this matters**: Phase 1.5/1.6 made colors configurable (was hardcoded before)

### Contract 3: Reasoning Blocks are Optional
**Assumption**: `meta.reasoning` field may or may not exist
**Violation consequence**: `_parse_reasoning_block()` returns None if missing/invalid
**Why this is policy**: Reasoning traces are encouraged but not required (yet)

### Contract 4: Format Methods Never Fail
**Assumption**: All format methods return strings (never raise exceptions)
**Violation consequence**: Tools expect formatting to always succeed
**Why this is defensive**: Missing fields → empty strings, invalid JSON → raw string

---

## 5. Token Analysis (TOKEN-001 SOURCE)

### Structural Bloat (350-400 tokens per tool call)
**Sources**:
- Header boxes: 20-30 tokens
- Footer boxes: 30-50 tokens
- Table borders: 10 tokens per row
- Separators: 5-10 tokens per separator
- ANSI color codes: +10% token overhead (invisible chars counted)

**Example** (list_projects with 5 projects):
- Header box: ~25 tokens
- Table headers: ~15 tokens
- Table borders: ~50 tokens (10 per row × 5)
- Row data: ~150 tokens (30 per row × 5)
- Footer tips: ~30 tokens
- **Total structural**: ~270 tokens
- **Actual data**: ~150 tokens
- **Efficiency**: 150/270 = 55% data, 45% decoration

### Metadata Bloat (200-250 tokens per call)
**Sources**:
- Pagination info: ~15 tokens
- Filter info: ~20 tokens
- Tips/suggestions: ~30 tokens
- Reminders (automatic): 80-200 tokens
- Recent projects list: 20-50 tokens

### Duplication Bloat (150-200 tokens per call)
**Sources**:
- Repeated header patterns across tools
- Same footer structure (metadata + reminders)
- Duplicate tips/suggestions

### Safety Padding Bloat (150-200 tokens per call)
**Sources**:
- "💡 Tip:" messages after every operation
- Verbose empty states ("No projects found. Try...")
- Defensive explanations ("Page 1 of 1" even when obvious)

### Total TOKEN-001 Cost
**list_projects** (worst case): 1000+ tokens
- Structural: 350 tokens
- Metadata: 250 tokens
- Duplication: 150 tokens
- Safety padding: 200 tokens
- **Actual project data**: ~300 tokens

**Optimization potential**: 60% reduction possible with:
- Compact mode (removes boxes, uses short field names)
- Optional reminders (not automatic)
- Minimal tips (only on errors)
- Result: ~400 tokens (vs 1000+)

---

## 6. Error Handling Architecture

### Policy: Never Fail (Defensive Formatting)
**Pattern**: All format methods wrap in try-except, return fallback strings
**Examples**:
- Missing field → empty string
- Invalid timestamp → original timestamp
- Parse error → raw value

**Why intentional**: Formatting errors should NEVER block tool execution

---

## 7. Known Issues

### BUG-TOKEN-001: list_projects Produces 1000+ Tokens (P0)
**Location**: Entire response.py (all format methods contribute)
**Evidence**: Wave 2 briefing documents 1000+ token output for list_projects
**Impact**: Token budget exhausted quickly, Claude Code performance degradation
**Root cause**: Structural bloat (boxes, tables, borders) + automatic reminders + safety padding

### BUG-TOKEN-002: Compact Mode Not Implemented for All Tools (P1)
**Location**: Many format methods lack compact code paths
**Evidence**: `format_projects_table()` only has readable format, no compact variant
**Impact**: Users can't opt-in to token savings for all tools
**Recommendation**: Implement compact variants for ALL specialized formatters

---

## 8. Implementation Specs

### SPEC-TOKEN-001: Extract BoxDrawing Infrastructure

**Problem**: 250 lines of box-drawing scattered in response.py
**Location**: `utils/response.py:245-493`

```yaml
spec_id: SPEC-TOKEN-001
title: Extract box-drawing infrastructure
priority: P2 (code quality)
files:
  - utils/response.py:245-493
  - NEW: utils/box_drawer.py
changes:
  - action: create_module
    path: utils/box_drawer.py
    content: |
      class BoxDrawer:
          def __init__(self, use_colors: bool = True):
              self.use_colors = use_colors

          def add_line_numbers(self, content: str, start: int = 1) -> str:
              # Move from response.py:245-279

          def create_header_box(self, title: str, metadata: Dict) -> str:
              # Move from response.py:281-350

          def create_footer_box(self, audit_data: Dict, reminders: Optional[List]) -> str:
              # Move from response.py:352-438

          def format_table(self, headers: List[str], rows: List[List[str]]) -> str:
              # Move from response.py:440-493

  - action: update_response_py
    changes:
      - "from utils.box_drawer import BoxDrawer"
      - "self._box_drawer = BoxDrawer(use_colors=self.USE_COLORS)"
      - "Replace all box-drawing method calls with self._box_drawer.* calls"

benefits:
  - Reduces response.py from 2424 → ~2100 LOC
  - Clear separation: BoxDrawer (presentation) vs ResponseFormatter (business logic)
  - Reusable box-drawing for other tools/reports
  - Easier to test box-drawing in isolation
risks:
  - Circular import if box_drawer imports from response
  - Need to pass use_colors configuration
```

### SPEC-TOKEN-002: Implement Compact Mode for All Tools

**Problem**: Many tools lack compact formatting variants
**Location**: Various format methods in response.py

```yaml
spec_id: SPEC-TOKEN-002
title: Implement compact mode for all specialized formatters
priority: P1 (token optimization)
files:
  - utils/response.py (all format_* methods)
changes:
  - action: add_compact_variants
    methods:
      - format_projects_table → add compact=True path
      - format_project_detail → add compact=True path
      - format_project_context → add compact=True path
      - format_readable_log_entries → already has compact logic
      - format_readable_file_content → add compact=True path

  - action: compact_rules
    guidelines:
      - "No boxes (remove header/footer boxes)"
      - "Minimal separators (single line, not box borders)"
      - "Short field names (use COMPACT_FIELD_MAP)"
      - "No tips/suggestions (unless error state)"
      - "Optional reminders (don't attach automatically)"

  - action: token_targets
    goals:
      - "list_projects: 1000 tokens → 400 tokens (60% reduction)"
      - "get_project: 600 tokens → 300 tokens (50% reduction)"
      - "read_recent: 800 tokens → 350 tokens (56% reduction)"

benefits:
  - 50-60% token reduction across ALL tools
  - Users opt-in via compact=True parameter
  - Maintains readable format as default (backwards compatible)
risks:
  - Compact format may be TOO minimal (user complaints)
  - Need to test compact readability with Claude Code
test_verification:
  - "Token measurements before/after for each tool"
  - "User testing: is compact format still usable?"
```

---

## Cross-Cutting Concerns

- **[BUCKET:formatting]** ALL structural token bloat originates here (TOKEN-001 source)
- **[BUCKET:config]** ANSI color config integration (USE_COLORS property)
- **[BUCKET:reminders]** Automatic reminder attachment (footer boxes)
- **[BUCKET:utilities]** Token estimation, timestamp formatting, relative time

**Impact**: This file is imported by LoggingToolMixin → used by 10+ tools. Changes here affect ALL tool output token costs. **THIS IS THE HIGHEST-IMPACT FILE FOR TOKEN OPTIMIZATION.**
