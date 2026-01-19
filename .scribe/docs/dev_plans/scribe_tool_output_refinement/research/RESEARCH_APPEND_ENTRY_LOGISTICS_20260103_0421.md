# RESEARCH: Append Entry Logistics & Log Query Architecture

**Project:** scribe_tool_output_refinement
**Researcher:** Research Analyst
**Date:** 2026-01-03
**Research Goal:** Analyze append_entry structure, design priority/category enums, query optimization, display projection, and token budget replacement strategy for 200kb+ reasoning trace support

**Confidence Level:** HIGH (0.95)
**Status:** Complete

---

## Executive Summary

This research investigates the current architecture of `append_entry`, log query mechanisms, and token budget management to address critical limitations in handling large reasoning traces (200kb+) and enable intelligent log filtering.

**Critical Findings:**
1. **Token Budget Timing Bug**: TokenBudgetManager truncates entries BEFORE readable formatting, causing data loss even when `format="readable"` is requested
2. **Missing Priority Infrastructure**: No priority, category, or importance fields exist in schema or metadata
3. **Tool Inconsistency**: `query_entries` works perfectly (no token budget), while `read_recent` truncates aggressively
4. **Readable Formatter Ready**: `format_readable_log_entries` already designed for full message display without truncation

**Recommended Actions:**
1. Move token budget AFTER format selection (or bypass for `format="readable"`)
2. Add `priority` and `category` fields to metadata schema with validation
3. Replace blind truncation with entry count limits and priority-based inclusion
4. Add database indexes on priority/category for efficient filtering

---

## 1. Current State Analysis

### 1.1 Append Entry Implementation

**File:** `tools/append_entry.py` (2134 lines)

**Current Metadata Structure:**
```python
@dataclass
class AppendEntryConfig:
    # Core content parameters
    message: str = ""
    status: Optional[str] = None  # info|success|warn|error|bug|plan (6 values)
    emoji: Optional[str] = None
    agent: Optional[str] = None
    meta: Optional[Any] = field(default_factory=dict)  # FREEFORM - no schema!
    timestamp_utc: Optional[str] = None

    # Bulk processing parameters
    items: Optional[str] = None
    items_list: Optional[List[Dict[str, Any]]] = None
    auto_split: bool = True

    # System parameters
    agent_id: Optional[str] = None
    log_type: Optional[str] = "progress"
```

**Findings:**
- `meta` is unstructured `Any` type, normalized to dict via `_normalise_meta()`
- No priority, category, importance, or classification fields
- Status limited to 6 hardcoded values (cannot extend for categorization)
- All filtering must parse JSON meta or rely on emoji/agent fields
- **Confidence:** 0.95

### 1.2 Database Schema

**File:** `storage/sqlite.py:569-581`

**Current `scribe_entries` Table:**
```sql
CREATE TABLE IF NOT EXISTS scribe_entries (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    ts_iso TEXT NOT NULL,
    emoji TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    meta TEXT,              -- Freeform JSON blob
    raw_line TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Findings:**
- 11 columns total
- `meta` is TEXT field storing JSON (no structured columns)
- No indexes on meta contents (cannot efficiently query JSON fields)
- No priority, category, entry_type, or importance columns
- **Confidence:** 1.0

### 1.3 Token Budget Architecture Flaw

**File:** `tools/read_recent.py:295-340`

**Execution Flow (BROKEN):**
```
1. Build response with entries array       (line 276)
2. TokenBudgetManager.truncate_response    (line 301) ← STRIPS ENTRIES HERE
3. finalize_tool_response                  (line 338) ← Converts to readable format
```

**The Problem:**
- Token budget runs on structured response BEFORE format selection
- `truncate_response_to_budget()` removes entries from `response["entries"]` array
- Default limit: 8000 tokens
- Binary search algorithm finds truncation point, drops remaining entries
- Readable formatter receives already-truncated data
- **No way to bypass** - happens regardless of `format` parameter

**Comparison with query_entries:**
- `query_entries.py` has **ZERO** TokenBudgetManager calls
- Relies on pagination and database limits only
- Returns complete entries with full reasoning traces
- **This is why it works when read_recent fails**
- **Confidence:** 1.0

### 1.4 Readable Formatter Analysis

**File:** `utils/response.py:584-751`

**Current Capabilities:**
```python
def format_readable_log_entries(entries, pagination, search_context):
    """
    Phase 3a enhancements:
    - Parse and display meta.reasoning blocks as tree structure
    - Smarter message truncation with word boundaries
    - Compact timestamp format (HH:MM)
    - Better pagination display
    - ANSI colors enabled (config-driven)
    """
    # Line 728: NO truncation - full messages for context rehydration
    message = entry.get('message', '')
    # NO truncation

    # Lines 738-751: Reasoning tree display (NO truncation)
    reasoning = self._parse_reasoning_block(meta)
    if reasoning:
        parts.append(f"    ├─ Why: {reasoning.get('why', 'N/A')}")
        parts.append(f"    ├─ What: {reasoning.get('what', 'N/A')}")
        parts.append(f"    └─ How: {reasoning.get('how', 'N/A')}")
```

**Findings:**
- **Already designed for full message display** (line 728 comment)
- Reasoning blocks displayed inline without truncation
- Filters `tool_logs` entries automatically
- Supports search_context display
- Compact timestamps (HH:MM) to save space
- Agent names truncated to 12 chars (reasonable)
- **The formatter is not the problem - it's perfect for our needs**
- **Confidence:** 1.0

---

## 2. Priority/Category Enum Schema Design

### 2.1 Proposed Metadata Schema

```python
class LogPriority(Enum):
    """Priority levels for log entries - determines retention and display order"""
    CRITICAL = "critical"  # Security issues, blocking bugs, architectural decisions
    HIGH = "high"          # Implementation milestones, test failures, major findings
    MEDIUM = "medium"      # Code changes, successful tests, investigation results
    LOW = "low"            # Debug info, minor updates, routine operations

class LogCategory(Enum):
    """Semantic categorization for intelligent filtering"""
    DECISION = "decision"              # Architectural or design decisions
    INVESTIGATION = "investigation"     # Research and analysis
    BUG = "bug"                        # Bug discovery and fixes
    IMPLEMENTATION = "implementation"   # Code changes
    TEST = "test"                      # Test results
    MILESTONE = "milestone"            # Project milestones
    CONFIG = "config"                  # Configuration changes
    SECURITY = "security"              # Security-related events
    PERFORMANCE = "performance"        # Performance analysis
    DOCUMENTATION = "documentation"    # Documentation updates

class EntryMetadata:
    """Structured metadata for log entries"""
    priority: LogPriority = LogPriority.MEDIUM  # Default to medium
    category: Optional[LogCategory] = None
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0  # 0.0-1.0
    reasoning: Optional[ReasoningTrace] = None
    related_files: List[str] = field(default_factory=list)

    # Existing freeform fields preserved for backward compatibility
    extra: Dict[str, Any] = field(default_factory=dict)
```

### 2.2 Database Schema Migration

**Add to `scribe_entries` table:**
```sql
ALTER TABLE scribe_entries ADD COLUMN priority TEXT DEFAULT 'medium';
ALTER TABLE scribe_entries ADD COLUMN category TEXT;
ALTER TABLE scribe_entries ADD COLUMN tags TEXT;  -- JSON array
ALTER TABLE scribe_entries ADD COLUMN confidence REAL DEFAULT 1.0;

-- Create indexes for efficient filtering
CREATE INDEX IF NOT EXISTS idx_entries_priority ON scribe_entries(priority, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_category ON scribe_entries(category, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_priority_category ON scribe_entries(priority, category, ts_iso DESC);
```

### 2.3 Backward Compatibility Strategy

**Phase 1: Additive Changes**
- Add new fields as OPTIONAL with sensible defaults
- Existing entries get `priority='medium'`, `category=NULL`
- Metadata parser handles both old (freeform) and new (structured) formats

**Phase 2: Gradual Migration**
- Update `append_entry` to accept `priority` and `category` parameters
- Auto-detect from status: `bug` → `priority=high`, `category=bug`
- Extract from meta if present: `meta.priority` → structured field

**Phase 3: Query Enhancement**
- Add priority/category filters to `read_recent` and `query_entries`
- Support composite filters: `priority=high AND category=bug`
- Enable sorting by priority within time ranges

---

## 3. Query Optimization Architecture

### 3.1 Indexing Strategy

**Current Indexes:**
```sql
idx_entries_project_ts ON scribe_entries(project_id, ts_iso DESC)
```

**Proposed Additional Indexes:**
```sql
-- Priority-based queries
CREATE INDEX idx_entries_priority_ts ON scribe_entries(priority, ts_iso DESC);

-- Category-based queries
CREATE INDEX idx_entries_category_ts ON scribe_entries(category, ts_iso DESC);

-- Composite filtering
CREATE INDEX idx_entries_project_priority_category
    ON scribe_entries(project_id, priority, category, ts_iso DESC);

-- Agent-based filtering (already efficient via existing patterns)
CREATE INDEX idx_entries_agent_ts ON scribe_entries(agent, ts_iso DESC);
```

### 3.2 Query Patterns

**Pattern 1: Priority-First Query**
```python
# Get highest priority entries first, then fill with medium priority
async def query_by_priority(
    project_id: int,
    limit: int = 50,
    priorities: List[LogPriority] = [LogPriority.CRITICAL, LogPriority.HIGH]
) -> List[Dict]:
    """Fetch entries by priority order"""
    query = """
        SELECT * FROM scribe_entries
        WHERE project_id = ? AND priority IN (?, ?)
        ORDER BY priority ASC, ts_iso DESC
        LIMIT ?
    """
    # ASC on priority enum order: critical < high < medium < low
```

**Pattern 2: Category Filtering**
```python
# Find all bugs and security issues in last 7 days
async def query_by_category_and_time(
    project_id: int,
    categories: List[LogCategory],
    start_time: str,
    end_time: str
) -> List[Dict]:
    """Time-bound category search"""
    query = """
        SELECT * FROM scribe_entries
        WHERE project_id = ?
          AND category IN (?, ?)
          AND ts_iso BETWEEN ? AND ?
        ORDER BY ts_iso DESC
    """
```

**Pattern 3: Semantic Search Preparation**
```python
# Tag-based filtering (JSON array search)
async def query_by_tags(
    project_id: int,
    tags: List[str],
    match_mode: str = "any"  # "any" or "all"
) -> List[Dict]:
    """Tag-based search for FAISS semantic hooks"""
    # SQLite JSON array search
    if match_mode == "any":
        # Match any tag
        conditions = " OR ".join([f"json_extract(tags, '$') LIKE '%{tag}%'" for tag in tags])
    else:
        # Match all tags
        conditions = " AND ".join([f"json_extract(tags, '$') LIKE '%{tag}%'" for tag in tags])

    query = f"""
        SELECT * FROM scribe_entries
        WHERE project_id = ? AND ({conditions})
        ORDER BY ts_iso DESC
    """
```

### 3.3 Performance Considerations

**For 200kb+ Reasoning Traces:**
- Don't load full `message` and `meta` in list queries
- Use projection: `SELECT id, ts_iso, priority, category, agent, LEFT(message, 100) AS summary`
- Load full entry only when user requests detail expansion
- Implement lazy loading: summary view → detail on demand

**Pagination Requirements:**
- Default page_size: 20 entries (not 50)
- Max page_size: 100 entries (prevent abuse)
- Cursor-based pagination for large result sets
- Count queries cached for 60 seconds

---

## 4. Display Projection Rules

### 4.1 Three Display Modes

**Summary Mode (Default):**
```
[🔍] 04:21 | Research Analyst | Analyzed append_entry.py - Current metadata is...
```
- Emoji + compact time (HH:MM) + agent (max 12 chars) + first line of message
- NO reasoning block display
- Priority indicator: CRITICAL entries get ⚠️ prefix
- Token estimate: ~150 tokens per entry

**Full Mode (format="readable"):**
```
[🔍] 04:21 | Research Analyst | Analyzed append_entry.py - Current metadata is unstructured dict, no priority/category enums exist

   Reasoning:
   ├─ Why: Need to understand current metadata capabilities to design priority/category system
   ├─ What: Current: meta accepts Any type, normalized to dict via _normalise_meta...
   └─ How: Read append_entry.py lines 1-1250, AppendEntryConfig dataclass...
```
- Full message (NO truncation)
- Full reasoning tree display
- All metadata shown
- Token estimate: 500-2000 tokens per entry (depends on reasoning size)

**Expandable Mode (NEW - format="expandable"):**
```
[🔍] 04:21 | Research Analyst | Analyzed append_entry.py - Current metadata... [expand]

# User clicks/requests expand:
[🔍] 04:21 | Research Analyst | Analyzed append_entry.py - Current metadata is unstructured dict, no priority/category enums exist

   Reasoning:
   ├─ Why: Need to understand current metadata capabilities...
   [Full reasoning displayed]

   Files: tools/append_entry.py, tools/config/append_entry_config.py
   Confidence: 0.95
```
- Summary by default
- Expand trigger returns full entry detail
- Lazy loading via entry ID: `read_entry_detail(entry_id)`
- Token estimate: 150 tokens summary, 500-2000 on expand

### 4.2 Priority-Based Display

**Critical Entries (priority=CRITICAL):**
- Always shown first, regardless of time
- Red/bold formatting
- Expanded by default
- ⚠️ CRITICAL prefix

**High Priority (priority=HIGH):**
- Shown before medium/low at same time
- Yellow formatting
- Summary by default, easy expand

**Medium/Low Priority:**
- Standard display
- Can be collapsed/hidden in summary mode

### 4.3 Collapsing Strategy (Carl's "Collapse WIDTH not DEPTH")

**Bad (Current TokenBudget Approach):**
```python
# Drops entire entries
entries = entries[:5]  # Only 5 entries shown, rest lost
```

**Good (Recommended Approach):**
```python
# Return fewer entries, but complete entries
def apply_display_budget(entries, mode, token_limit=8000):
    if mode == "summary":
        # More entries, less detail per entry
        max_entries = 50
        tokens_per_entry = 150
    elif mode == "full":
        # Fewer entries, full detail per entry
        max_entries = 10
        tokens_per_entry = 1000
    elif mode == "expandable":
        # Many entries in summary, expand on demand
        max_entries = 50
        tokens_per_entry = 150
        # Full details loaded lazily

    # Return complete entries, not partial/truncated
    budget_entries = min(max_entries, token_limit // tokens_per_entry)
    return entries[:budget_entries]  # Complete entries only
```

---

## 5. Token Budget Replacement Strategy

### 5.1 Critical Architectural Fix

**Current (BROKEN):**
```python
# tools/read_recent.py:295-340
response = success_with_entries(entries=db_entries, ...)  # Line 276
truncated, _, _ = token_budget_manager.truncate_response_to_budget(response)  # Line 301
return formatter.finalize_tool_response(truncated, format, "read_recent")  # Line 338
```

**Fixed (Recommended):**
```python
# tools/read_recent.py - NEW FLOW
response = success_with_entries(entries=db_entries, ...)

# FORMAT SELECTION FIRST
if format == "readable":
    # Bypass token budget for readable - let formatter handle display
    return await formatter.finalize_tool_response(response, format, "read_recent")
else:
    # Apply token budget only for structured/compact formats
    truncated, _, _ = token_budget_manager.truncate_response_to_budget(response)
    return await formatter.finalize_tool_response(truncated, format, "read_recent")
```

### 5.2 Entry Count Limits (Not Token Limits)

**Replace TokenBudgetManager with EntryLimitManager:**
```python
class EntryLimitManager:
    """Intelligent entry limiting based on priority and display mode"""

    def limit_entries(
        self,
        entries: List[Dict],
        mode: str = "summary",
        priority_filter: Optional[List[LogPriority]] = None,
        max_entries: Optional[int] = None
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        Limit entries intelligently:
        - Priority-first ordering
        - Entry count limits (not token limits)
        - Complete entries only (no truncation)
        """
        # Sort by priority first, then time
        sorted_entries = sorted(
            entries,
            key=lambda e: (
                self._priority_sort_key(e.get('priority', 'medium')),
                e.get('ts_iso', '')
            ),
            reverse=True  # Most recent critical entries first
        )

        # Determine limit based on mode
        if max_entries is None:
            max_entries = {
                "summary": 50,
                "full": 10,
                "expandable": 50,
                "structured": 100,
                "compact": 200
            }.get(mode, 50)

        # Filter by priority if requested
        if priority_filter:
            filtered = [e for e in sorted_entries if e.get('priority') in priority_filter]
        else:
            filtered = sorted_entries

        # Return complete entries only
        limited = filtered[:max_entries]

        metadata = {
            "total_available": len(entries),
            "filtered_count": len(filtered),
            "returned_count": len(limited),
            "entries_omitted": len(filtered) - len(limited),
            "mode": mode
        }

        return limited, metadata
```

### 5.3 Priority-Based Inclusion

**Smart Entry Selection:**
```python
def select_entries_by_priority(
    entries: List[Dict],
    target_count: int = 50,
    priority_weights: Dict[str, float] = {
        "critical": 1.0,  # Always include
        "high": 0.8,      # Include 80%
        "medium": 0.5,    # Include 50%
        "low": 0.2        # Include 20%
    }
) -> List[Dict]:
    """
    Select entries based on priority distribution.

    Example: If target_count=50:
    - All CRITICAL entries (assume 5)
    - 80% of HIGH entries (40 available → 32 selected)
    - 50% of MEDIUM entries (100 available → 13 selected to reach 50 total)
    - LOW entries only if space remains
    """
    buckets = {p: [] for p in ["critical", "high", "medium", "low"]}
    for entry in entries:
        priority = entry.get('priority', 'medium')
        buckets[priority].append(entry)

    selected = []
    remaining = target_count

    # Include all critical
    selected.extend(buckets["critical"])
    remaining -= len(buckets["critical"])

    # Include weighted HIGH
    high_count = min(len(buckets["high"]), int(len(buckets["high"]) * priority_weights["high"]))
    selected.extend(buckets["high"][:high_count])
    remaining -= high_count

    # Fill remaining with medium/low
    if remaining > 0:
        medium_count = min(remaining, len(buckets["medium"]))
        selected.extend(buckets["medium"][:medium_count])
        remaining -= medium_count

    if remaining > 0:
        selected.extend(buckets["low"][:remaining])

    return selected
```

### 5.4 Pagination as Primary Mechanism

**New Default Behavior:**
- Default page_size: 20 entries (reduced from 50)
- User can request more: `page_size=100` (capped at 200)
- No arbitrary token truncation
- Clear pagination metadata: "Showing 20 of 487 entries (page 1 of 25)"
- Encourage pagination over larger page sizes

**Benefits:**
- Predictable response sizes
- No data loss
- User controls detail level via page_size parameter
- Works with priority filtering: "Show HIGH priority, 50 per page"

---

## 6. Implementation Recommendations

### 6.1 Phase 1: Critical Fixes (Week 1)

**Priority: CRITICAL**

1. **Fix token budget execution order** (read_recent.py)
   - Move token budget AFTER format selection
   - Bypass for `format="readable"`
   - Estimated effort: 2 hours
   - Risk: Low (isolated change)

2. **Add EntryLimitManager** (new file: utils/entry_limit.py)
   - Replace token-based with count-based limits
   - Implement priority-based ordering
   - Estimated effort: 4 hours
   - Risk: Low (new utility)

3. **Update read_recent to use EntryLimitManager**
   - Replace TokenBudgetManager calls
   - Add priority parameter support
   - Estimated effort: 3 hours
   - Risk: Medium (affects existing tool)

**Success Criteria:**
- `read_recent(format="readable")` returns full entries
- No truncation of reasoning traces
- Pagination works correctly

### 6.2 Phase 2: Priority/Category Infrastructure (Week 2)

**Priority: HIGH**

1. **Database Schema Migration**
   - Add priority, category, tags, confidence columns
   - Create indexes
   - Migration script with backward compatibility
   - Estimated effort: 6 hours
   - Risk: Medium (schema change, needs testing)

2. **Update append_entry**
   - Add priority/category parameters
   - Validate enum values
   - Auto-detect from status/meta
   - Estimated effort: 8 hours
   - Risk: Medium (core tool change)

3. **Update query tools**
   - Add priority/category filters to read_recent
   - Add priority/category filters to query_entries
   - Add priority-based sorting
   - Estimated effort: 6 hours
   - Risk: Low (additive changes)

**Success Criteria:**
- Can log entries with priority/category
- Can query by priority/category
- Old entries still work (backward compatible)

### 6.3 Phase 3: Advanced Display (Week 3)

**Priority: MEDIUM**

1. **Implement expandable mode**
   - Add format="expandable"
   - Create read_entry_detail tool for lazy loading
   - Update formatters
   - Estimated effort: 8 hours
   - Risk: Low (new feature)

2. **Priority-based display formatting**
   - CRITICAL entries with ⚠️ prefix
   - Color coding by priority
   - Auto-expand CRITICAL entries
   - Estimated effort: 4 hours
   - Risk: Low (display only)

3. **Performance optimization**
   - Add projection queries (summary fields only)
   - Implement result caching
   - Optimize index usage
   - Estimated effort: 6 hours
   - Risk: Low (optimization)

**Success Criteria:**
- Can handle 200kb+ reasoning traces
- Fast queries with priority filtering
- Expandable mode works smoothly

### 6.4 Testing Strategy

**Unit Tests:**
- EntryLimitManager priority ordering
- Priority/category enum validation
- Database migration rollback
- Query performance benchmarks

**Integration Tests:**
- read_recent with priority filters
- query_entries with category filters
- Expandable mode lazy loading
- 200kb reasoning trace handling

**Regression Tests:**
- Old entries still readable
- Existing workflows unaffected
- Performance not degraded

---

## 7. Risk Analysis

### 7.1 High Risks

**Database Migration:**
- Risk: Schema changes could corrupt data
- Mitigation: Backup database before migration, test rollback procedure
- Contingency: Keep old schema as fallback

**Token Budget Removal:**
- Risk: Response sizes could explode without limits
- Mitigation: Implement EntryLimitManager first, test with large datasets
- Contingency: Keep TokenBudgetManager as optional fallback

### 7.2 Medium Risks

**Backward Compatibility:**
- Risk: Old code expects different response structure
- Mitigation: Extensive regression testing, gradual rollout
- Contingency: Feature flags for new behavior

**Performance Degradation:**
- Risk: Priority queries could be slow without proper indexes
- Mitigation: Create indexes during migration, benchmark queries
- Contingency: Add query timeout limits

### 7.3 Low Risks

**Display Mode Changes:**
- Risk: Users confused by new formats
- Mitigation: Clear documentation, preserve old defaults
- Contingency: Easy to revert (display-only changes)

---

## 8. Open Questions

1. **Should priority be required or optional?**
   - Recommendation: Optional with default='medium' for ease of use

2. **How to handle priority conflicts in bulk mode?**
   - Recommendation: Allow per-entry priority in items_list

3. **Should we add entry_type field in addition to category?**
   - Recommendation: No - category is sufficient, avoid schema bloat

4. **What's the maximum reasonable page_size?**
   - Recommendation: 200 entries (configurable per tool)

5. **Should we support custom priority levels?**
   - Recommendation: No - keep enum fixed for consistency

---

## 9. References

### Files Analyzed
- `tools/append_entry.py` (2134 lines) - Entry creation logic
- `tools/read_recent.py` (537 lines) - Token budget bug location
- `tools/query_entries.py` - Comparison tool (no token budget)
- `storage/sqlite.py` (1399 lines) - Database schema
- `utils/response.py` (1403 lines) - Formatting logic
- `utils/config_manager.py` - TokenBudgetManager implementation

### Bugs Discovered
1. **Timestamp parsing bug** (fixed): 'T' in "2026-01-02 13:48:13 UTC" matched because "UTC" contains "T"
2. **Variable collision bug** (fixed): `parts` used for both output list and timestamp parsing
3. **Token budget truncation bug** (UNFIXED): Truncates before readable formatting
4. **read_recent vs query_entries inconsistency** (UNFIXED): Only read_recent has token budget

### External Review
- GPT 5.2 "Carl" review emphasized: "One canonical payload, multiple views"
- Recommendation: Collapse WIDTH not DEPTH (fewer complete entries vs many partial entries)
- Key insight: Raw data should be addressable, not embedded

---

## Conclusion

The current append_entry and log query architecture has significant limitations in handling large reasoning traces and lacks intelligent filtering capabilities. The token budget timing bug is the most critical issue, causing data loss even when users request full formatting.

**Immediate Action Required:**
1. Fix token budget execution order (2 hours)
2. Implement EntryLimitManager (4 hours)
3. Add priority/category schema (6 hours migration + 8 hours append_entry updates)

**Expected Outcomes:**
- Support for 200kb+ reasoning traces without truncation
- Intelligent priority-based filtering
- Predictable response sizes via entry count limits
- Backward compatible with existing logs

**Timeline:** 3 weeks for full implementation
**Confidence:** HIGH (0.95)
**Status:** Ready for architecture review

---

**Research Analyst**
2026-01-03 04:21 UTC
