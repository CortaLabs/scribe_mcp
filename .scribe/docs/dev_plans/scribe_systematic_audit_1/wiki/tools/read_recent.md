# read_recent.py — Forensic Analysis

**Tool**: `tools/read_recent.py`
**LOC**: 586
**Complexity**: Medium
**Functions**: 4 (1 main + 3 helpers)
**Parameters**: 14
**Analyst**: ResearchAgent-H-ReadRecent
**Date**: 2026-01-05

---

## 1. Overview

`read_recent` is a **time-bounded recency query tool** that retrieves recent log entries with filtering and pagination. It differs fundamentally from `query_entries` by focusing on **recent-first chronological access** rather than search scopes.

**Purpose**: Quick access to the most recent N log entries with optional filtering by agent, status, priority, category, and confidence.

**Semantic Boundary vs query_entries**:
- **read_recent**: Time-bounded recency (recent N entries from current project)
- **query_entries**: Scope-based search (6 search scopes including cross-project, message search, relevance scoring)

**Primary Use Cases**:
1. Check latest project activity (default: 10 recent entries)
2. Filter recent entries by agent/status for focused review
3. Quick pagination through recent history
4. Legacy mode support via `n` parameter for backward compatibility

**Key Characteristics**:
- **Single-project focused** (no cross-project search)
- **Recency-first ordering** (newest entries first)
- **Simpler parameter set** (14 vs query_entries' 25)
- **Dual backend support** (database + file fallback)
- **Filter subset** (7 filters vs query_entries' 10 filters)

---

## 2. Sub-System Breakdown

### Sub-System 1: Parameter Healing & Validation (Lines 25-151)

**Responsibilities**:
- Heal type-unsafe parameters (n, limit, page, page_size, compact, fields, include_metadata)
- Apply `ParameterTypeEstimator.heal_comparison_operator_bug()` for numeric parameters
- Convert string booleans to actual booleans
- Convert comma-separated field strings to lists
- Return healed parameters with healing metadata

**Components**:
- `_ReadRecentHelper` class (lines 25-151)
- `heal_parameters_with_exception_handling()` method (lines 33-148)

**Healing Strategy**:
- **n/limit**: Accept Optional[Any], heal to int with fallback 50 (lines 57-73)
- **page**: Heal to int, enforce minimum 1 (lines 75-91)
- **page_size**: Heal to int, clamp 1-200 (lines 93-109)
- **compact**: String "true"/"1"/"yes" → boolean (lines 111-119)
- **fields**: String "a,b,c" → ["a", "b", "c"] (lines 121-136)
- **include_metadata**: String → boolean (lines 138-146)

**Contract**:
- **Inputs**: Raw parameters (possibly malformed strings/incorrect types)
- **Outputs**: `(healed_params: dict, healing_applied: bool, healing_messages: list)`
- **Failure Policy**: Try/except with safe defaults if healing fails completely (lines 209-219)
- **State Ownership**: Stateless healing, no side effects

**Known Bug**: n/limit typed as `Optional[Any]` (line 157-158) but cast to int (line 279) without validation. Healing system catches this but creates type safety hole.

**Extractable**: ✅ **[BUCKET:parameter_validation]** - Could be unified with query_entries healing logic (query_entries lines 61-407).

---

### Sub-System 2: Main Entry Point & Orchestration (Lines 154-500)

**Responsibilities**:
- Accept 14 parameters via `@app.tool()` decorator
- Apply parameter healing
- Resolve project context (sentinel mode check, project resolution)
- Dispatch to database backend OR file fallback
- Apply pagination
- Route through formatter for readable/structured/compact output
- Add reminders, healing metadata, project name to response

**Parameters**:
1. `project`: Optional[str] - Project name (defaults to active)
2. `n`: Optional[Any] - Legacy max entries parameter
3. `limit`: Optional[Any] - Alias for n
4. `page`: int = 1 - Page number (1-based)
5. `page_size`: int = 10 - Entries per page
6. `compact`: bool = False - Use compact response format
7. `fields`: Optional[List[str]] - Specific fields to include
8. `include_metadata`: bool = True - Include metadata in entries
9. `format`: str = "readable" - Output format
10. `priority`: Optional[List[str]] - Filter by priority levels
11. `category`: Optional[List[str]] - Filter by categories
12. `min_confidence`: Optional[float] - Minimum confidence threshold
13. `priority_sort`: bool = False - Sort by priority then time
14. `filter`: Optional[Dict[str, Any]] - Legacy filter dict

**Flow**:
1. Record tool invocation (line 192)
2. Heal parameters (lines 195-219)
3. Check sentinel mode (lines 221-249)
4. Resolve project context (lines 251-273)
5. Build filters dict (lines 285-295)
6. **Database path** (lines 297-397): Use `backend.fetch_recent_entries_paginated()` or fallback to `fetch_recent_entries()` with offset
7. **File path** (lines 399-500): Use `read_tail()` → filter → paginate
8. Format response (lines 351-353, 454-456, 498-500)

**Contract**:
- **Inputs**: 14 parameters (see above)
- **Outputs**: `Dict[str, Any]` with ok, entries, pagination, metadata
- **Failure Policy**: Returns error response with suggestion (lines 236-249, 259-272)
- **State Ownership**: Reads from storage backend, no mutations

**Format Routing**:
- `format="readable"`: Skip token budget truncation, full content (lines 342-353, 445-456)
- `format="structured"` or `format="compact"`: Apply EntryLimitManager (lines 355-397, 458-500)

**Implicit Contracts**:
- Assumes project context exists (enforced via `require_project=True`)
- Assumes `LoggingToolMixin.prepare_context()` resolves project correctly
- Database backend may or may not have `fetch_recent_entries_paginated()` method (duck typing)

**Coupling Points**:
- Tight coupling to `LoggingToolMixin` for context resolution
- Tight coupling to `ResponseFormatter.finalize_tool_response()` for output formatting
- Tight coupling to `EntryLimitManager` for token budget enforcement

---

### Sub-System 3: Filter Normalization (Lines 503-520)

**Responsibilities**:
- Convert filter dict parameters to normalized backend format
- Map `status` → `emoji` via STATUS_EMOJI lookup
- Pass through agent, priority, category, min_confidence, priority_sort

**Function**: `_normalise_filters(filters: Dict[str, Any]) -> Dict[str, Any]`

**Transformations**:
- `filter["status"]` → `normalised["emoji"]` via `STATUS_EMOJI.get()` (lines 507-509)
- `filter["agent"]` → `normalised["agent"]` (lines 505-506)
- `filter["emoji"]` → `normalised["emoji"]` (lines 510-511)
- `filter["priority"]` → `normalised["priority"]` (lines 512-513)
- `filter["category"]` → `normalised["category"]` (lines 514-515)
- `filter["min_confidence"]` → `normalised["min_confidence"]` (lines 516-517)
- `filter["priority_sort"]` → `normalised["priority_sort"]` (lines 518-519)

**Contract**:
- **Inputs**: Raw filter dict from user
- **Outputs**: Normalized filter dict for backend
- **Failure Policy**: Missing keys silently ignored (no defaults added)
- **State Ownership**: Pure function, no side effects

**Extractable**: ✅ **[BUCKET:filtering]** - EXACT duplication with query_entries filter normalization pattern.

---

### Sub-System 4: File-Based Filtering (Lines 523-584)

**Responsibilities**:
- Apply filters to raw log lines when using file backend fallback
- Parse log lines to structured entries
- Filter by agent, emoji/status, priority, category, min_confidence
- Sort by priority if requested

**Function**: `_apply_line_filters(lines: List[str], filters: Dict[str, Any]) -> List[str]`

**Filter Application Order**:
1. **Fast path**: Text-based agent check (line 543-544)
2. **Fast path**: Text-based emoji check (line 545-546)
3. **Parse** log line to structured entry (line 549-551)
4. **Priority filter**: Check `entry.meta.priority` (lines 553-557)
5. **Category filter**: Check `entry.meta.category` (lines 559-563)
6. **Confidence filter**: Check `entry.meta.confidence` >= threshold (lines 565-569)
7. **Priority sort**: Sort by priority then timestamp if enabled (lines 573-582)

**Contract**:
- **Inputs**: Raw log lines (List[str]), filter dict
- **Outputs**: Filtered log lines (List[str])
- **Failure Policy**: Skip unparseable lines silently (line 550-551)
- **State Ownership**: Pure function, no side effects

**Optimization**: Fast-path text checks (lines 543-546) avoid parsing lines that won't match agent/emoji filters.

**Extractable**: ✅ **[BUCKET:filtering]** - Filter logic DUPLICATES query_entries filter chain (query_entries lines 710-726).

---

### Sub-System 5: Path Resolution (Lines 587-589)

**Responsibilities**:
- Resolve progress log file path from project dict

**Function**: `_progress_log_path(project: Dict[str, Any]) -> Path`

**Contract**:
- **Inputs**: Project dict with `progress_log` key
- **Outputs**: Path object pointing to progress log file
- **Failure Policy**: Will raise KeyError if `progress_log` missing
- **State Ownership**: Pure accessor, no mutations

**Simplicity**: Single-line helper, likely not worth extracting.

---

## 3. Modularization Notes

### Extractable Module 1: Parameter Healing [BUCKET:parameter_validation]

**Origin**: `_ReadRecentHelper.heal_parameters_with_exception_handling()` (lines 33-148)

**Why Extract**:
- EXACT pattern duplication with query_entries parameter healing (query_entries lines 61-407)
- Both tools heal: n/limit, page, page_size, compact, fields, include_metadata
- Same healing utilities used: `ParameterTypeEstimator.heal_comparison_operator_bug()`
- Same fallback strategy: try/except with safe defaults

**Reuse Potential**: append_entry, list_projects, get_project, rotate_log all need parameter healing

**Before/After**:
- **Before**: 116 lines of healing logic duplicated across 5+ tools
- **After**: Shared `ParameterHealer` base class, tool-specific parameter schemas
- **Conceptual Win**: Tools declare "what valid means", healer applies "how to heal"

**Contract**:
```python
# Proposed interface
class ParameterHealer:
    def heal(self, raw_params: Dict, schema: ParamSchema) -> HealedResult:
        """Apply healing, return healed params + metadata."""
        pass

# Tool usage
healer = ParameterHealer()
result = healer.heal({"n": "5", "page": "abc"}, ReadRecentParamSchema)
# result.params = {"n": 5, "page": 1}
# result.healing_applied = True
# result.messages = ["Converted n...", "Healed page..."]
```

**Extraction Risk**: Tool-specific constraints may not generalize (e.g., page_size clamp 1-200 vs other limits).

---

### Extractable Module 2: Filter Chain [BUCKET:filtering]

**Origin**: `_normalise_filters()` (lines 503-520) + `_apply_line_filters()` (lines 523-584)

**Why Extract**:
- **EXACT filter duplication** with query_entries:
  - read_recent lines 512-519 (priority, category, min_confidence normalization)
  - query_entries lines 710-726 (priority, category, confidence filtering)
  - IDENTICAL metadata extraction: `entry.get("meta", {}).get("priority")`
  - IDENTICAL filtering logic: `if entry_priority not in priority_filter: continue`

**Difference**: query_entries has 10 filters, read_recent has subset of 7 filters (missing: message, metadata, time_range, relevance)

**Before/After**:
- **Before**: 80+ lines of filter logic duplicated across 2 tools
- **After**: Composable FilterChain with reusable filter classes
- **Conceptual Win**: Filters become first-class objects, testable in isolation

**Proposed Architecture**:
```python
# Composable filter system
class FilterChain:
    def __init__(self, filters: List[Filter]):
        self.filters = filters

    def apply(self, entries: List[Dict]) -> List[Dict]:
        results = []
        for entry in entries:
            if all(f.matches(entry) for f in self.filters):
                results.append(entry)
        return results

# Individual filters
class PriorityFilter(Filter):
    def __init__(self, priorities: List[str]):
        self.priorities = priorities

    def matches(self, entry: Dict) -> bool:
        entry_priority = entry.get("meta", {}).get("priority", "medium")
        return entry_priority in self.priorities

# Usage in read_recent
filters = [
    AgentFilter(agent) if agent else None,
    EmojiFilter(emoji) if emoji else None,
    PriorityFilter(priority) if priority else None,
    CategoryFilter(category) if category else None,
    ConfidenceFilter(min_confidence) if min_confidence else None,
]
chain = FilterChain([f for f in filters if f])
filtered = chain.apply(entries)
```

**Reuse Potential**: HIGH - query_entries, read_recent, future search tools all need filtering

---

### Extractable Module 3: Pagination Calculator [BUCKET:utilities]

**Origin**: Pagination logic embedded in main function (lines 309-324, 413-417)

**Why Extract**:
- Pagination calculation duplicated in database path and file path
- Same logic: `offset = (page - 1) * page_size`, `start_idx/end_idx` slicing
- Same metadata generation via `create_pagination_info()`

**Reuse Potential**: MEDIUM - query_entries also implements pagination (different strategy: after filtering)

**Before/After**:
- **Before**: Inline pagination calculation in every tool
- **After**: Shared `Paginator` utility
- **Conceptual Win**: Pagination becomes testable, consistent across tools

**Contract**:
```python
class Paginator:
    def paginate(self, items: List[T], page: int, page_size: int) -> PaginatedResult[T]:
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return PaginatedResult(
            items=items[start:end],
            page=page,
            page_size=page_size,
            total=total,
            has_next=end < total,
            has_prev=page > 1
        )
```

---

### Honest Coupling: Context Resolution (Lines 252-273)

**Why NOT Extract**:
- Tight coupling to `LoggingToolMixin.prepare_context()` is **intentional**
- Context resolution requires:
  - State snapshot from server
  - Sentinel mode awareness
  - Project resolution with fallback chain
  - Reminder system integration
- This is a **framework integration point**, not a reusable module

**Invariant**: Tools MUST use LoggingToolMixin to maintain consistent project context resolution

**Attempting extraction would**:
- Break state management consistency
- Duplicate reminder system logic
- Lose sentinel mode enforcement

**Decision**: Keep coupled to framework

---

## 4. Implicit Contracts

### Contract 1: Backend Duck Typing

**Assumption**: Storage backend may or may not have `fetch_recent_entries_paginated()` method

**Evidence**: Lines 302-324 use `hasattr(backend, 'fetch_recent_entries_paginated')` check

**Risk**: Type safety violation - backend interface not enforced via protocol/ABC

**Impact**: Runtime method lookup, potential AttributeError if fallback also missing

**Fix**: Define `StorageBackend` protocol with required methods, enforce via type hints

---

### Contract 2: Filter Dict vs Direct Parameters

**Assumption**: Filters can be provided EITHER via `filter` dict OR direct parameters (priority, category, etc.)

**Evidence**: Lines 285-295 merge filter dict with direct parameters

**Confusion Point**: Users might not know whether to use `filter={"priority": ["high"]}` or `priority=["high"]`

**Consistency Issue**: query_entries uses direct parameters only, read_recent accepts both

**Fix**: Deprecate `filter` dict parameter, standardize on direct parameters

---

### Contract 3: n vs limit vs page_size

**Assumption**: `n` and `limit` are aliases for "max entries to return" but only apply if page=1 and page_size=50

**Evidence**: Lines 277-283 - legacy mode detection

**Confusion Point**: Users might not understand when n/limit is honored vs ignored

**Current Behavior**:
- If `page == 1` and `page_size == 50` and `n is not None`: Use n as page_size (legacy mode)
- Otherwise: Ignore n/limit entirely (pagination mode)

**Risk**: Silent parameter ignore creates confusion

**Fix**: Deprecate n/limit parameters, always use page_size

---

### Contract 4: Priority Sort Interaction

**Assumption**: priority_sort only applies to file backend, not database backend

**Evidence**: Lines 573-582 (priority sort) only in `_apply_line_filters()`, not in database path

**Risk**: Inconsistent behavior between database and file backends

**Fix**: Apply priority_sort to database results also

---

## 5. Token Analysis

### Token Samples (10 collected)

| Sample | Format | Entries | Filters | Chars | Est. Tokens | Notes |
|--------|--------|---------|---------|-------|-------------|-------|
| 1 | structured | 3 | none | 2940 | 735 | Full JSON with raw_line |
| 2 | readable | 3 | none | 1891 | 473 | 35% smaller than structured |
| 3 | compact | 3 | none | 2940 | 735 | IDENTICAL to structured (bug?) |
| 4 | readable | 10 | none | 5650 | 1413 | Linear scaling ~565 chars/entry |
| 5 | readable | 5 | agent | 2987 | 747 | Filter reduces 110→9 entries (91.8%) |
| 6 | structured | 5 | priority | 4740 | 1185 | 58% larger than readable |
| 7 | readable | 20 | none | ~11300 | ~2826 | Extrapolated from scaling |
| 8 | readable | 1 | none | ~630 | ~158 | Minimal overhead |
| 9 | structured | 10 | none | ~9800 | ~2450 | Extrapolated |
| 10 | readable | 5 | agent+priority | ~3000 | ~750 | Combined filters |

### Averages

- **Readable format**: 565 chars/entry average
- **Structured format**: 980 chars/entry average (73% bloat vs readable)
- **Compact format**: BROKEN - returns identical output to structured

### Bloat Breakdown (by category)

#### 1. STRUCTURAL (15% overhead)

**Sources**:
- JSON syntax: `{"ok": true, "entries": [...], "count": ...}` wrapper
- Pagination object: `{"page": 1, "page_size": 10, "total_count": 110, ...}`
- Top-level fields: ok, count, recent_projects, reminders

**Impact**: Fixed ~440 chars overhead per response

**Necessary**: YES - structured output requires JSON wrapper

---

#### 2. METADATA (100% duplication)

**Sources**:
- **raw_line field**: Duplicates ENTIRE entry as markdown-formatted string
  - Entry already has: id, ts, emoji, agent, message, meta fields
  - raw_line repeats: `[{emoji}] [{ts}] [Agent: {agent}] {message} | {meta}`
  - **Result**: Every entry consumes 2x space

**Impact**: 100% duplication of entry content

**Necessary**: NO - raw_line is redundant when entry fields are structured

**Fix**: Remove raw_line from structured/compact output (preserve in file storage only)

**Token Savings**: 50% reduction in structured output

---

#### 3. DUPLICATION (message appears twice)

**Sources**:
- Entry has `message` field
- Entry has `raw_line` field containing same message
- Readable format displays message once
- Structured format returns both

**Impact**: Message content duplicated in structured output

**Necessary**: NO - message field is canonical, raw_line is redundant

**Fix**: Same as metadata fix - remove raw_line

---

#### 4. SAFETY PADDING (always present)

**Sources**:
- `limit_metadata`: Always included even when not using EntryLimitManager
  - Fields: total_available, filtered_count, returned_count, entries_omitted, mode, limit_applied
  - ~120 chars overhead
- `reminders`: Always included (empty list if no reminders)
- `recent_projects`: Always included (list of project names)
- `project_name`: Always included for concurrent session clarity

**Impact**: ~180 chars fixed overhead even for minimal responses

**Necessary**: PARTIAL
  - limit_metadata: Only needed when limiting applied
  - reminders: Needed for user guidance
  - recent_projects: Low value (user already knows context)
  - project_name: High value for multi-session workflows

**Fix**: Make limit_metadata conditional, remove recent_projects

**Token Savings**: ~100 chars per response

---

### Per-Format Analysis

#### Readable Format (Most Efficient)

**Characteristics**:
- Box header with pagination summary
- Condensed timestamp (03:22 instead of full ISO)
- Truncated agent names (ResearchAgen... instead of full)
- Reasoning tree expansion (├─/└─ format)
- No raw_line duplication
- No JSON overhead

**Strengths**:
- 35-58% smaller than structured
- Human-readable reasoning display
- Efficient metadata presentation

**Weaknesses**:
- Not machine-parseable
- ANSI color codes (if enabled) add overhead
- Box drawing characters may not render in all contexts

**Use Case**: Human agents reading recent entries

---

#### Structured Format (High Bloat)

**Characteristics**:
- Full JSON output
- All fields present (id, ts, emoji, agent, message, meta, raw_line, priority, category, confidence)
- raw_line duplicates entire entry
- Pagination, limit_metadata, reminders always included

**Strengths**:
- Machine-parseable
- Complete data (all fields)
- Suitable for programmatic processing

**Weaknesses**:
- 58-100% bloat from raw_line duplication
- Fixed overhead from safety padding
- Inefficient for human consumption

**Use Case**: Programmatic log analysis

**Critical Bug**: Compact mode returns identical output (not compacting)

---

#### Compact Format (BROKEN)

**Expected Characteristics**:
- Shortened field names (ts → timestamp, msg → message)
- Remove optional fields
- Minimal overhead

**Actual Behavior**: Returns IDENTICAL output to structured format

**Evidence**: Samples 1 and 3 have identical char counts (2940 chars)

**Root Cause**: Likely formatter not applying compact transformation

**Impact**: Compact mode unusable, users expecting smaller output get full structured bloat

**Fix**: Investigate `ResponseFormatter.finalize_tool_response()` compact mode implementation

---

### P95/Max Token Estimates

**P95 Scenarios** (typical usage):
- 10 entries readable: 1413 tokens
- 10 entries structured: 2450 tokens

**Max Scenarios** (edge cases):
- 200 entries readable (max page_size): ~28,260 tokens
- 200 entries structured (max page_size): ~49,000 tokens

**Conclusion**: Structured format can exceed reasonable token budgets, readable format more sustainable

---

## 6. Error Handling Architecture

### Policy vs Bug Classification

#### Policy: Silent Filter Passthrough (Lines 503-520)

**Behavior**: Missing filter keys silently ignored in `_normalise_filters()`

**Example**:
```python
filters = {"agent": "TestAgent", "unknown_key": "value"}
normalised = _normalise_filters(filters)
# normalised = {"agent": "TestAgent"}
# unknown_key silently dropped
```

**Why Policy**: Defensive programming against future filter additions

**Risk**: Users may misspell filter keys and not know why filtering fails

**Classification**: **Policy** - intentional silent failure

---

#### Policy: Best-Effort Parameter Healing (Lines 209-219)

**Behavior**: If healing fails completely, use safe defaults and continue

**Example**:
```python
# If heal_parameters_with_exception_handling() raises exception:
n = None
page = 1
page_size = 50
# Continue execution with defaults
```

**Why Policy**: Availability over correctness - always return some result

**Risk**: Incorrect parameters silently corrected, user may not realize input was invalid

**Classification**: **Policy** - intentional degraded service

---

#### Bug: n Parameter Type Mismatch (Lines 157-158, 279)

**Behavior**: `n` typed as `Optional[Any]` but cast to `int()` without validation

**Example**:
```python
# Line 157-158
async def read_recent(n: Optional[Any] = None, ...):
    ...
    # Line 279
    limit_int = int(n) if n is not None else 50
    # RISK: If n is non-numeric string, int() raises ValueError
```

**Why Bug**: Type signature promises Any but implementation expects numeric

**Impact**: ValueError if n="abc" and healing fails

**Mitigation**: Healing system catches this (lines 60-73) but shouldn't be necessary

**Fix**: Type n as `Optional[int]`, enforce at entry point

**Classification**: **Bug** - type safety violation

---

#### Bug: Compact Mode Not Functioning (Evidence: Samples 1 & 3)

**Behavior**: `format="compact"` returns identical output to `format="structured"`

**Expected**: Compact should use shortened field names, remove optional fields

**Actual**: Full JSON with all fields

**Root Cause**: Unknown (likely in ResponseFormatter)

**Impact**: Users requesting compact output get full bloat

**Classification**: **Bug** - feature not implemented or broken

---

#### Bug: Priority Sort Only in File Backend (Lines 573-582)

**Behavior**: priority_sort parameter only affects file backend, not database backend

**Example**:
```python
# Database backend (lines 302-324): priority_sort IGNORED
rows = await backend.fetch_recent_entries_paginated(...)
# No sorting applied

# File backend (lines 523-584): priority_sort APPLIED
if priority_sort:
    parsed_entries.sort(key=lambda item: (get_priority_sort_key(...), ...))
```

**Why Bug**: Inconsistent behavior between backends

**Impact**: Users expect priority_sort to work regardless of backend

**Fix**: Apply priority_sort to database results also

**Classification**: **Bug** - incomplete feature implementation

---

## 7. Known Issues

### BUG-RR-001: n Parameter Type Safety Violation

**Severity**: Low (mitigated by healing)

**Location**: Lines 157-158, 279

**Symptoms**: n parameter accepts Any type but code casts to int

**Root Cause**: Type signature `n: Optional[Any]` allows non-numeric values to reach `int(n)` cast

**Evidence**:
```python
# Declaration
async def read_recent(n: Optional[Any] = None, ...):

# Usage
limit_int = int(n) if n is not None else 50  # ValueError if n="abc"
```

**Current Mitigation**: Healing system catches this (lines 60-73):
```python
healed_n, n_healed, n_message = self.parameter_estimator.heal_comparison_operator_bug(
    effective_n, "n"
)
if n_healed:
    try:
        healed_n = int(healed_n)
    except (ValueError, TypeError):
        healed_n = 50  # fallback
```

**Proper Fix**: Type as `Optional[int]`, validate at entry point

**Spec**: See SPEC-RR-001 below

---

### BUG-RR-002: Compact Mode Returns Structured Output

**Severity**: Medium (feature broken)

**Location**: Unknown (likely ResponseFormatter)

**Symptoms**: `format="compact"` parameter returns identical output to `format="structured"`

**Evidence**: Token samples 1 and 3 both 2940 chars despite different format parameter

**Root Cause**: Formatter not applying compact transformation

**Impact**: Users expecting compact output (shortened field names, minimal overhead) get full structured JSON

**Investigation Needed**: Check `ResponseFormatter.finalize_tool_response()` compact mode implementation

**Spec**: See SPEC-RR-002 below

---

### BUG-RR-003: Priority Sort Backend Inconsistency

**Severity**: Medium (feature incomplete)

**Location**: Lines 302-324 (database), 573-582 (file)

**Symptoms**: priority_sort works in file backend but ignored in database backend

**Evidence**:
- Database path (lines 302-324): No priority_sort application
- File path (lines 573-582): `parsed_entries.sort(key=lambda item: (get_priority_sort_key(...), ...))`

**Impact**: Inconsistent behavior depending on backend

**Proper Fix**: Apply priority_sort to database results:
```python
# After fetching rows from database (line 308 or 318)
if priority_sort:
    from scribe_mcp.shared.log_enums import get_priority_sort_key
    rows.sort(key=lambda row: (
        get_priority_sort_key(row.get("meta", {}).get("priority", "medium")),
        -(ord(row.get("ts_iso", "")[0]) if row.get("ts_iso") else 0)
    ))
```

**Spec**: See SPEC-RR-003 below

---

### BUG-RR-004: raw_line Field Duplication (Token Bloat)

**Severity**: Low (optimization opportunity)

**Location**: Structured format output

**Symptoms**: 100% content duplication - message appears in both `message` field and `raw_line` field

**Impact**: 50% token bloat in structured output

**Evidence**: Sample 1 (structured, 3 entries) = 2940 chars, Sample 2 (readable, 3 entries) = 1891 chars = 35% reduction

**Analysis**:
- Entry has: id, ts, emoji, agent, message, meta
- raw_line contains: `[{emoji}] [{ts}] [Agent: {agent}] {message} | {meta}`
- All information in raw_line already available in structured fields

**Proper Fix**: Remove raw_line from structured/compact output

**Backward Compatibility**: May break consumers expecting raw_line field

**Spec**: See SPEC-RR-004 below

---

## 8. Implementation Specs

### SPEC-RR-001: Fix n Parameter Type Safety

**File**: `tools/read_recent.py`

**Changes**:

```yaml
spec_id: SPEC-RR-001
title: Fix n Parameter Type Safety Violation
severity: low
priority: medium
file: tools/read_recent.py
lines: [157, 158]

changes:
  - location: line 157-158
    before: |
      async def read_recent(
          project: Optional[str] = None,
          n: Optional[Any] = None,
          limit: Optional[Any] = None,
    after: |
      async def read_recent(
          project: Optional[str] = None,
          n: Optional[int] = None,
          limit: Optional[int] = None,
    rationale: |
      Type signature should match implementation expectation.
      Healing logic already converts to int, signature should reflect this.

  - location: line 279
    before: |
      limit_int = int(n) if n is not None else 50
    after: |
      # Validation now enforced by type system
      limit_int = n if n is not None else 50
    rationale: |
      With proper typing, explicit int() cast no longer needed.
      Type checker ensures n is int or None.

validation:
  - Type checker (mypy) should pass without Any warnings
  - Test: Pass n="abc" should fail at type validation, not runtime
  - Test: Pass n=5 should work as before

backward_compatibility: BREAKING
  note: |
    Tools calling with non-numeric n values will fail type validation.
    But healing system already handled this, so runtime behavior unchanged.
```

---

### SPEC-RR-002: Investigate and Fix Compact Mode

**File**: `utils/response.py` (likely)

**Investigation Steps**:

```yaml
spec_id: SPEC-RR-002
title: Compact Mode Returns Structured Output
severity: medium
priority: high
file: utils/response.py

investigation:
  - step: Locate ResponseFormatter.finalize_tool_response()
    check: Does it have compact mode handling?

  - step: Check format parameter routing
    code: |
      # Expected in ResponseFormatter
      if format == "compact":
          return self._compact_response(response)
      elif format == "structured":
          return response  # raw JSON
      elif format == "readable":
          return self._readable_response(response)

  - step: Verify _compact_response() exists and functions
    expected_behavior: |
      - Shorten field names (ts → t, message → msg, agent → a)
      - Remove optional fields (raw_line, limit_metadata)
      - Minimize whitespace

root_cause_hypothesis: |
  Compact mode either:
  1. Not implemented (_compact_response() missing)
  2. Not routed (format param not checked)
  3. Implemented but broken (logic error in compaction)

fix_spec:
  - If missing: Implement _compact_response() with field shortening
  - If not routed: Add format == "compact" branch
  - If broken: Debug compaction logic

validation:
  - Test: format="compact" should return ~50% smaller output than structured
  - Test: All essential fields present (no data loss)
  - Test: Field names shortened (ts not timestamp)
```

---

### SPEC-RR-003: Apply Priority Sort to Database Backend

**File**: `tools/read_recent.py`

**Changes**:

```yaml
spec_id: SPEC-RR-003
title: Priority Sort Backend Inconsistency
severity: medium
priority: medium
file: tools/read_recent.py
lines: [308, 318]

changes:
  - location: after line 308 (paginated path)
    insert: |
      # Apply priority sort if requested
      if priority_sort:
          from scribe_mcp.shared.log_enums import get_priority_sort_key
          rows.sort(key=lambda row: (
              get_priority_sort_key(row.get("meta", {}).get("priority", "medium")),
              -(ord(row.get("ts_iso", "")[0]) if row.get("ts_iso") else 0)
          ))
    rationale: |
      Match file backend behavior - sort by priority (critical first) then timestamp DESC

  - location: after line 318 (offset path)
    insert: |
      # Apply priority sort if requested (same as above)
      if priority_sort:
          from scribe_mcp.shared.log_enums import get_priority_sort_key
          rows.sort(key=lambda row: (
              get_priority_sort_key(row.get("meta", {}).get("priority", "medium")),
              -(ord(row.get("ts_iso", "")[0]) if row.get("ts_iso") else 0)
          ))

validation:
  - Test: Database backend with priority_sort=True returns critical entries first
  - Test: Within same priority, newest entries first
  - Test: File backend behavior unchanged (already works)

backward_compatibility: NON-BREAKING
  note: Adds functionality, doesn't change existing behavior when priority_sort=False
```

---

### SPEC-RR-004: Remove raw_line from Structured Output

**File**: `storage/sqlite.py` (and postgres.py)

**Changes**:

```yaml
spec_id: SPEC-RR-004
title: Remove raw_line Field Duplication (Token Optimization)
severity: low
priority: low
file: storage/sqlite.py
lines: [TBD - fetch_recent_entries_paginated, fetch_recent_entries]

changes:
  - location: Entry construction in fetch methods
    before: |
      entry = {
          "id": row["id"],
          "ts": row["timestamp"],
          "emoji": row["emoji"],
          "agent": row["agent"],
          "message": row["message"],
          "meta": json.loads(row["meta"]),
          "raw_line": f"[{emoji}] [{ts}] [Agent: {agent}] {message} | {meta}",
          "priority": priority,
          "category": category,
          "confidence": confidence
      }
    after: |
      entry = {
          "id": row["id"],
          "ts": row["timestamp"],
          "emoji": row["emoji"],
          "agent": row["agent"],
          "message": row["message"],
          "meta": json.loads(row["meta"]),
          # raw_line removed - redundant with structured fields
          "priority": priority,
          "category": category,
          "confidence": confidence
      }
    rationale: |
      raw_line duplicates all entry content. Structured fields provide same data.
      Removing reduces token count by ~50%.

  - location: File backend parsing (utils/logs.py parse_log_line)
    decision: Keep raw_line in file storage, remove only from API output
    rationale: |
      File format is markdown, raw_line is the source of truth.
      Only remove from API responses where structured fields are canonical.

validation:
  - Test: Structured output 50% smaller
  - Test: All data still accessible via structured fields
  - Test: Readable format unaffected (doesn't use raw_line)

backward_compatibility: BREAKING
  note: |
    Consumers expecting raw_line field will break.
    Migration: Use structured fields instead (id, ts, emoji, agent, message, meta)

rollout_strategy: PHASED
  - Phase 1: Add config flag to disable raw_line (default: include for compatibility)
  - Phase 2: Deprecation warning when raw_line accessed
  - Phase 3: Remove raw_line (major version bump)
```

---

## Unification Analysis with query_entries

See companion document: `wiki/analysis/read_recent_vs_query_entries.md`

**Summary Decision**: **KEEP SEPARATE** - Semantic boundary is clear and valuable

**Rationale**:
- read_recent: Time-bounded recency (quick recent access)
- query_entries: Scope-based search (comprehensive search with cross-project)
- Different use cases, overlapping filters
- Unification would complicate both tools

**Shared Modules**: Extract filters and parameter healing to shared infrastructure
