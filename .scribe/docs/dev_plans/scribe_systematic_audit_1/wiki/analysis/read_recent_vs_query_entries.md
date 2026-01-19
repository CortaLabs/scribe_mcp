# Unification Analysis: read_recent vs query_entries

**Analyst**: ResearchAgent-H-ReadRecent
**Date**: 2026-01-05
**Question**: Should read_recent and query_entries be unified into a single tool?

---

## Executive Summary

**Decision**: **KEEP SEPARATE**

**Rationale**: Clear semantic boundary between "time-bounded recency" (read_recent) and "scope-based search" (query_entries) provides distinct value to users. Unification would complicate both use cases without significant benefit.

**Recommendation**: Extract shared infrastructure (filters, parameter healing, pagination) into reusable modules, but maintain separate tool interfaces.

---

## Semantic Boundary Analysis

### read_recent: Time-Bounded Recency

**Purpose**: Quick access to the most recent N log entries

**Mental Model**: "Show me the latest activity"

**Key Characteristics**:
- **Single-project focused** - Always operates on current/specified project
- **Recency-first ordering** - Newest entries first, chronological
- **Simple scope** - No cross-project, no document types, no search modes
- **Legacy compatibility** - Supports n parameter for backward compatibility
- **Performance optimized** - Uses read_tail for file backend (efficient recent-first read)

**Primary Use Cases**:
1. Quick status check: "What's happened recently?"
2. Agent-specific review: "What did ResearchAgent do?"
3. Priority triage: "Show me recent critical/high priority entries"
4. Session resumption: "Catch me up on the last 20 entries"

**Parameter Count**: 14

---

### query_entries: Scope-Based Search

**Purpose**: Comprehensive search across projects, document types, and metadata

**Mental Model**: "Search for specific content across the entire system"

**Key Characteristics**:
- **6 search scopes** - project, global, all_projects, research, bugs, all
- **Cross-project iteration** - Search multiple projects simultaneously
- **Message search modes** - substring, regex, exact matching
- **Document type filtering** - progress logs, research docs, architecture docs, bug reports
- **Relevance scoring** - Threshold-based result filtering
- **Code reference verification** - Optional validation of mentioned files

**Primary Use Cases**:
1. Cross-project research: "Find all research on authentication across projects"
2. Bug pattern analysis: "Search for bugs related to hash tracking"
3. Architectural review: "Find all architecture decisions about state management"
4. Global search: "Find all mentions of ProjectRegistry across everything"
5. Relevance-filtered queries: "High-confidence entries about vector search"

**Parameter Count**: 25

---

## Before/After Mental Model

### Before: Two Tools with Distinct Purposes

```
User Intent: "Show me recent activity"
    → read_recent(page_size=20)
    → Returns: 20 newest entries from current project
    → Fast, simple, familiar

User Intent: "Search for authentication bugs across all projects"
    → query_entries(search_scope="bugs", message="authentication")
    → Returns: Bug reports mentioning "authentication" from all projects
    → Comprehensive, powerful, precise
```

**Strengths**:
- **Clear tool selection** - User knows which tool to use based on intent
- **Optimized for use case** - read_recent fast for recency, query_entries thorough for search
- **Simple vs complex** - read_recent easy to learn, query_entries powerful when needed

---

### After: Unified Tool (Hypothetical)

```
query_entries(
    scope="recent",  # New scope option
    page_size=20
)
# vs
query_entries(
    scope="all_projects",
    document_types=["bugs"],
    message="authentication"
)
```

**Problems**:
1. **Cognitive load** - Users must learn 7 scopes (6 existing + recent) instead of 2 tools
2. **Parameter pollution** - 26+ parameters (25 existing + n/limit legacy)
3. **Implementation complexity** - query_entries already 2030 LOC, adding recency adds more
4. **Performance regression** - read_tail optimization lost if merged into search strategy pattern
5. **Backward compatibility nightmare** - Existing read_recent users forced to migrate

**Benefits**:
1. **Single search interface** - One tool for all querying
2. **Consistent filtering** - Same filters across all scopes

**Verdict**: Benefits don't outweigh costs

---

## Comparison Matrix

| Aspect | read_recent | query_entries | Overlap |
|--------|-------------|---------------|---------|
| **LOC** | 586 | 2,030 | - |
| **Parameters** | 14 | 25 | 11 shared |
| **Complexity** | Medium | Ultra-High | - |
| **Scopes** | 1 (current project) | 6 (project/global/all_projects/research/bugs/all) | None |
| **Search Modes** | None | 3 (substring/regex/exact) | None |
| **Message Filtering** | No | Yes | NO |
| **Time-Range Filtering** | No | Yes | NO |
| **Relevance Scoring** | No | Yes | NO |
| **Code Verification** | No | Yes | NO |
| **Cross-Project** | No | Yes | NO |
| **Document Types** | 1 (progress log) | 5 (progress/research/architecture/bugs/global) | progress only |
| **Agent Filter** | Yes | Yes | ✅ SHARED |
| **Status/Emoji Filter** | Yes | Yes | ✅ SHARED |
| **Priority Filter** | Yes | Yes | ✅ SHARED |
| **Category Filter** | Yes | Yes | ✅ SHARED |
| **Confidence Filter** | Yes | Yes | ✅ SHARED |
| **Priority Sort** | Yes | No | Inverse |
| **Pagination** | Yes (simple) | Yes (complex after filtering) | Similar |
| **Format Routing** | readable/structured/compact | readable/structured/compact | ✅ SHARED |
| **Backend Fallback** | Database + file | Database only | Partial |
| **Legacy n param** | Yes | No | Unique to read_recent |
| **Parameter Healing** | Yes | Yes | ✅ SHARED |

---

## Filter Analysis

### Filters in BOTH Tools (7 total)

**EXACT implementation duplication**:

1. **Agent filter**:
   - read_recent: lines 505-506, 543-544
   - query_entries: lines 694-698
   - Logic: Exact agent name match

2. **Status/Emoji filter**:
   - read_recent: lines 507-511, 545-546
   - query_entries: lines 678-692
   - Logic: Status → emoji mapping, then emoji match
   - **BUG in query_entries**: Inverted for-else logic (line 684-692)

3. **Priority filter**:
   - read_recent: lines 512-513, 553-557
   - query_entries: lines 710-714
   - Logic: `entry.meta.priority in priority_list`

4. **Category filter**:
   - read_recent: lines 514-515, 559-563
   - query_entries: lines 716-720
   - Logic: `entry.meta.category in category_list`

5. **Confidence filter**:
   - read_recent: lines 516-517, 565-569
   - query_entries: lines 722-726
   - Logic: `entry.meta.confidence >= min_confidence`

6. **Pagination**:
   - Both implement page/page_size
   - Different strategies (read_recent: before filtering for file backend, query_entries: after filtering)

7. **Format routing**:
   - Both use ResponseFormatter.finalize_tool_response()
   - Same format options (readable/structured/compact)

### Filters ONLY in query_entries (3 total)

1. **Message filter** (lines 669-676):
   - 3 modes: substring, regex, exact
   - Case-sensitive option
   - Why not in read_recent: Recency tools don't typically search message content

2. **Metadata filter** (lines 700-708):
   - Key-value matching
   - Normalization (string "true" → boolean)
   - Why not in read_recent: Advanced use case, adds complexity

3. **Time range filter** (lines 728-746):
   - Start/end timestamp bounds
   - DateTime parsing
   - Why not in read_recent: Recency already implies time bounds (recent N)

4. **Relevance filter** (lines 748-753):
   - Naive scoring (message length / 1000)
   - Threshold-based filtering
   - Why not in read_recent: Search-specific feature

### Filter NOT in query_entries

1. **Priority sort** (read_recent lines 573-582):
   - Sort by priority (critical first) then timestamp
   - Why not in query_entries: Not yet implemented (should be)

---

## Shared Infrastructure Opportunities

### Module 1: Filter Chain [BUCKET:filtering]

**Extraction Target**: ~120 LOC duplicated across both tools

**Proposed Architecture**:
```python
# Shared filter infrastructure
class FilterChain:
    """Composable filter system for log entries."""

    def __init__(self, filters: List[Filter]):
        self.filters = filters

    def apply(self, entries: List[Dict]) -> List[Dict]:
        results = []
        for entry in entries:
            if all(f.matches(entry) for f in self.filters):
                results.append(entry)
        return results

# Individual reusable filters
class AgentFilter(Filter):
    def __init__(self, agent: str):
        self.agent = agent

    def matches(self, entry: Dict) -> bool:
        return entry.get("agent") == self.agent

class PriorityFilter(Filter):
    def __init__(self, priorities: List[str]):
        self.priorities = priorities

    def matches(self, entry: Dict) -> bool:
        priority = entry.get("meta", {}).get("priority", "medium")
        return priority in self.priorities

# ... CategoryFilter, ConfidenceFilter, EmojiFilter, etc.
```

**Usage in read_recent**:
```python
from scribe_mcp.shared.filtering import FilterChain, AgentFilter, PriorityFilter, CategoryFilter

filters = []
if agent:
    filters.append(AgentFilter(agent))
if priority:
    filters.append(PriorityFilter(priority))
if category:
    filters.append(CategoryFilter(category))

chain = FilterChain(filters)
filtered_entries = chain.apply(entries)
```

**Usage in query_entries**:
```python
from scribe_mcp.shared.filtering import FilterChain, MessageFilter, PriorityFilter, TimeRangeFilter

filters = [
    MessageFilter(message, mode, case_sensitive) if message else None,
    PriorityFilter(priority) if priority else None,
    TimeRangeFilter(start, end) if start or end else None,
    # ... etc
]
chain = FilterChain([f for f in filters if f])
filtered_entries = chain.apply(entries)
```

**Benefits**:
- **Testability**: Each filter testable in isolation
- **Composability**: Filters can be reordered, combined, or excluded
- **Reusability**: New tools can use same filters
- **Bug fixes**: Fix status filter bug in ONE place (currently broken in query_entries)

**Lines Saved**: ~120 LOC (from 200+ duplicated to 80 shared)

---

### Module 2: Parameter Healer [BUCKET:parameter_validation]

**Extraction Target**: ~146 LOC duplicated across both tools

**read_recent healing** (lines 33-148):
- n/limit → int with fallback 50
- page → int, min 1
- page_size → int, clamp 1-200
- compact → boolean
- fields → list
- include_metadata → boolean

**query_entries healing** (lines 61-407):
- All of read_recent's parameters
- Plus: search_scope, document_types, message_mode, case_sensitive, time ranges, etc.

**Proposed Architecture**:
```python
class ParameterHealer:
    """Unified parameter healing with tool-specific schemas."""

    def heal(self, raw_params: Dict, schema: ParamSchema) -> HealedResult:
        healed = {}
        messages = []

        for param_name, param_config in schema.params.items():
            raw_value = raw_params.get(param_name)
            healed_value, msg = self._heal_parameter(
                raw_value,
                param_config.type,
                param_config.default,
                param_config.constraints
            )
            healed[param_name] = healed_value
            if msg:
                messages.append(msg)

        return HealedResult(params=healed, messages=messages, applied=bool(messages))

# Tool-specific schemas
ReadRecentParamSchema = ParamSchema({
    "n": ParamConfig(type=int, default=None, constraints={"min": 1, "max": 200}),
    "page": ParamConfig(type=int, default=1, constraints={"min": 1}),
    "page_size": ParamConfig(type=int, default=10, constraints={"min": 1, "max": 200}),
    "compact": ParamConfig(type=bool, default=False),
    # ...
})

QueryEntriesParamSchema = ParamSchema({
    # Includes all ReadRecentParamSchema params
    # Plus query-specific params
    "search_scope": ParamConfig(type=str, default="project", constraints={"enum": VALID_SCOPES}),
    "message_mode": ParamConfig(type=str, default="substring", constraints={"enum": ["substring", "regex", "exact"]}),
    # ...
})
```

**Benefits**:
- **Consistency**: All tools heal parameters the same way
- **Declarative**: Schema defines "what valid means", healer applies "how to heal"
- **Testability**: Healer testable independently of tools
- **Maintainability**: Update healing logic in one place

---

### Module 3: Pagination Calculator [BUCKET:utilities]

**Extraction Target**: ~40 LOC duplicated

**Current Duplication**:
- read_recent: lines 309-324 (database), 413-417 (file)
- query_entries: lines 779-833

**Different Strategies**:
- read_recent: Paginate BEFORE filtering (file backend) or AFTER filtering (database backend)
- query_entries: Paginate AFTER filtering (always)

**Proposed Architecture**:
```python
class Paginator:
    """Reusable pagination logic."""

    @staticmethod
    def paginate(items: List[T], page: int, page_size: int) -> PaginatedResult[T]:
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

    @staticmethod
    def create_info(page: int, page_size: int, total: int) -> Dict:
        """Generate pagination metadata dict."""
        return {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "has_next": (page * page_size) < total,
            "has_prev": page > 1
        }
```

**Benefits**:
- Consistent pagination logic
- Testable in isolation
- Easy to add features (e.g., total_pages calculation)

---

## Unification Decision Matrix

| Factor | Keep Separate | Unified | Weight | Winner |
|--------|---------------|---------|--------|--------|
| **User Experience** | Clear tool selection | One tool to learn | High | SEPARATE |
| **Performance** | Optimized per use case | Generic implementation | High | SEPARATE |
| **Cognitive Load** | 2 tools, distinct purposes | 1 tool, 7 scopes | High | SEPARATE |
| **Parameter Count** | 14 + 25 = distributed | 26+ in one tool | Medium | SEPARATE |
| **Implementation Complexity** | 586 + 2030 = isolated | ~2500 monolithic | High | SEPARATE |
| **Filter Reusability** | Duplicate 7 filters | Shared 10 filters | Medium | UNIFIED |
| **Backward Compatibility** | No breaking changes | Breaking for read_recent users | High | SEPARATE |
| **Maintenance** | Update 2 tools | Update 1 tool | Low | UNIFIED |
| **Code Duplication** | ~120 LOC duplicated | 0 LOC duplicated | Low | UNIFIED |

**Score**: SEPARATE wins 7/9 factors (weighted by importance)

---

## Recommendation

### Decision: Keep Separate Tools

**Rationale**:
1. **Semantic boundary is clear and valuable**:
   - read_recent = "Show me recent activity" (time-bounded recency)
   - query_entries = "Search for X across Y" (scope-based search)
   - Different mental models, different use cases

2. **Performance optimization per use case**:
   - read_recent uses read_tail (efficient recent-first file read)
   - query_entries uses search strategies (cross-project iteration)
   - Merging would force one-size-fits-all implementation

3. **User experience clarity**:
   - Tool selection is obvious based on intent
   - read_recent is simple to learn (14 params)
   - query_entries is powerful when needed (25 params)
   - Unified tool would be confusing (26+ params, 7 scopes)

4. **Backward compatibility**:
   - Merging breaks existing read_recent users
   - n parameter legacy mode lost
   - Migration cost high, benefit low

5. **Implementation complexity**:
   - query_entries already 2030 LOC (ultra-high complexity)
   - Adding recency logic increases complexity further
   - Separate tools are easier to maintain

---

### Recommendation: Extract Shared Infrastructure

**Instead of unifying tools, extract shared modules**:

1. **FilterChain [BUCKET:filtering]**:
   - Extract 7 shared filters (agent, status/emoji, priority, category, confidence, pagination, format)
   - Saves ~120 LOC duplication
   - Enables reuse in future tools
   - Fixes status filter bug in ONE place

2. **ParameterHealer [BUCKET:parameter_validation]**:
   - Extract parameter healing to shared utility
   - Tool-specific schemas define constraints
   - Saves ~146 LOC duplication
   - Consistent healing across all tools

3. **Paginator [BUCKET:utilities]**:
   - Extract pagination calculation
   - Saves ~40 LOC duplication
   - Consistent pagination behavior

**Total LOC Saved**: ~306 LOC

**Benefits**:
- **Reduced duplication** without sacrificing tool clarity
- **Shared bug fixes** (filter bug fix helps both tools)
- **Easier testing** (modules testable in isolation)
- **Consistent behavior** across tools

---

## Contract Boundary Definition

If tools remain separate, what's the contract boundary?

### read_recent Contract

**Purpose**: Time-bounded recency query for current project

**Guarantees**:
- Returns up to N most recent entries from current/specified project
- Recency-first ordering (newest first)
- Supports basic filters (agent, status, priority, category, confidence)
- Single-project scope only
- Fast performance (optimized for recency)

**When to Use**:
- "What happened recently?"
- "Catch me up"
- "Show me latest from [agent]"
- "What are recent critical issues?"

**When NOT to Use**:
- Cross-project search → use query_entries
- Message content search → use query_entries
- Document type filtering (research/bugs) → use query_entries
- Relevance-based ranking → use query_entries

---

### query_entries Contract

**Purpose**: Comprehensive scope-based search with cross-project support

**Guarantees**:
- Search across 6 scopes (project, global, all_projects, research, bugs, all)
- Message content search (substring/regex/exact)
- Document type filtering (progress/research/architecture/bugs/global)
- Cross-project iteration
- Relevance scoring and filtering
- Code reference verification (optional)

**When to Use**:
- "Find all bugs related to X"
- "Search research docs for Y"
- "Find mentions of Z across all projects"
- "What architecture decisions about W?"

**When NOT to Use**:
- Just want recent entries → use read_recent (faster)
- No search/filter needed → use read_recent (simpler)

---

## Migration Path (If Unification Required Later)

**If future requirements change and unification becomes necessary**:

### Phase 1: Extract Shared Infrastructure (Current Recommendation)

1. Extract FilterChain
2. Extract ParameterHealer
3. Extract Paginator
4. Both tools use shared modules

### Phase 2: Add "recent" Scope to query_entries

1. Add `search_scope="recent"` option to query_entries
2. Implement recency logic in query_entries (using read_tail strategy)
3. read_recent becomes thin wrapper around `query_entries(search_scope="recent")`

### Phase 3: Deprecate read_recent

1. Add deprecation warning to read_recent
2. Documentation redirects users to query_entries
3. Maintain read_recent for backward compatibility (no new features)

### Phase 4: Remove read_recent (Major Version Bump)

1. Remove read_recent tool entirely
2. query_entries is the single query interface

**Timeline**: 12-18 months minimum (3-6 months per phase)

**Cost**: High (breaking change, migration effort, testing, documentation)

**Benefit**: Single query interface, less code duplication

**Risk**: User confusion, implementation complexity increase

---

## Conclusion

**Keep read_recent and query_entries separate.**

**Semantic boundary is clear**:
- read_recent = Time-bounded recency (recent N from project)
- query_entries = Scope-based search (search X across Y)

**Extract shared infrastructure** to reduce duplication without sacrificing clarity:
- FilterChain [BUCKET:filtering] - 7 shared filters
- ParameterHealer [BUCKET:parameter_validation] - Consistent healing
- Paginator [BUCKET:utilities] - Consistent pagination

**Result**:
- Reduced code duplication (~306 LOC saved)
- Maintained clear user experience (2 distinct tools)
- Shared bug fixes (filter fixes help both)
- Easier testing (modules testable in isolation)
- Future-proof (can unify later if needed via migration path)
