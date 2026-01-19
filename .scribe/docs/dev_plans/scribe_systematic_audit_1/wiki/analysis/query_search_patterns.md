# Search Pattern Analysis — query_entries.py

**Analysis Date**: 2026-01-05
**Analyst**: ResearchAgent-C-QueryEntries
**Scope**: Search scope routing, filter composition, and cross-project query patterns

---

## Overview

`query_entries` implements **6 distinct search scopes** with overlapping implementation patterns. This analysis examines:

1. **Search Scope Architecture**: How scopes differ and what they share
2. **Filter Composition Patterns**: How filters combine and interact
3. **Cross-Project Query Mechanics**: Project iteration and result aggregation
4. **Unification Opportunities**: Where duplication can be eliminated

---

## 1. Search Scope Architecture

### Scope Taxonomy

| Scope | Purpose | Projects Searched | Document Types | Includes Global | Lines |
|-------|---------|-------------------|----------------|-----------------|-------|
| `project` | Current project only | 1 (active) | progress log | No | N/A (default) |
| `global` | Global log only | 0 (special) | sentinel/global | Yes (only) | 1299-1308 |
| `all_projects` | All configured projects | N (all) | progress logs | No | 1279-1297 |
| `research` | Research docs across projects | N (filtered) | research/* | Yes | 1310-1340 |
| `bugs` | Bug reports across projects | N (filtered) | bugs/* | Yes | 1310-1340 |
| `all` | Everything everywhere | N (all) | all types | Yes | 1310-1340 |

### Scope Implementation Patterns

**Pattern 1: Single Project** (`project` scope)
- Uses active project from context
- No cross-project iteration
- Implemented in `_search_single_project()` (lines 1560-1630)

**Pattern 2: Global Only** (`global` scope)
- Creates special config pointing to global log
- Returns single-item project list
- Lines 1299-1308

**Pattern 3: All Projects Iteration** (`all_projects` scope)
- Iterates all projects from state
- Loads project config from state or fallback
- No document type filtering
- Lines 1279-1297

**Pattern 4: Filtered Projects Iteration** (`research`, `bugs`, `all` scopes)
- **IDENTICAL** iteration logic to Pattern 3
- Adds `_project_has_document_types()` filter
- Always includes global log at end
- Lines 1310-1340

### Code Duplication Evidence

**Blocks 1 and 2** (49 lines duplicated):

```python
# Block 1: all_projects scope (lines 1281-1297)
for project_name in state.projects:
    project_dict = state.get_project(project_name)
    if project_dict:
        if not project_dict.get("progress_log"):
            fallback_project = load_project_config(project_name)
            if fallback_project:
                project_dict = fallback_project
                project_dict["name"] = project_name
            else:
                continue  # Skip projects without valid config
        else:
            project_dict["name"] = project_name
        projects.append(project_dict)  # Unconditional append

# Block 2: research/bugs/all scopes (lines 1312-1330)
for project_name in state.projects:
    project_dict = state.get_project(project_name)  # IDENTICAL
    if project_dict:                                 # IDENTICAL
        if not project_dict.get("progress_log"):    # IDENTICAL
            fallback_project = load_project_config(project_name)  # IDENTICAL
            if fallback_project:                     # IDENTICAL
                project_dict = fallback_project      # IDENTICAL
                project_dict["name"] = project_name  # IDENTICAL
            else:                                    # IDENTICAL
                continue                             # IDENTICAL
        else:                                        # IDENTICAL
            project_dict["name"] = project_name     # IDENTICAL
        # ONLY DIFFERENCE: conditional append with filter
        if _project_has_document_types(project_dict, document_types, search_scope):
            projects.append(project_dict)
```

**Difference**: Single conditional at append point (1 line out of 49).

### Unification Strategy

**Current Architecture** (Duplicated):
```
all_projects: iterate → load → append
research/bugs/all: iterate → load → filter → append
```

**Proposed Architecture** (Unified):
```python
def _load_all_projects(state) -> List[Project]:
    """Load all projects from state with fallback to config."""
    projects = []
    for project_name in state.projects:
        project_dict = _load_project_with_fallback(state, project_name)
        if project_dict:
            projects.append(project_dict)
    return projects

def _load_project_with_fallback(state, project_name: str) -> Optional[Dict]:
    """Load single project from state or config fallback."""
    project_dict = state.get_project(project_name)
    if not project_dict:
        return None

    if not project_dict.get("progress_log"):
        fallback = load_project_config(project_name)
        if fallback:
            fallback["name"] = project_name
            return fallback
        return None

    project_dict["name"] = project_name
    return project_dict

def _resolve_cross_project_projects(scope, document_types):
    if scope == "global":
        return [_create_global_config()]

    projects = _load_all_projects(state)

    if scope == "all_projects":
        return projects

    if scope in ["research", "bugs", "all"]:
        filtered = [
            p for p in projects
            if _project_has_document_types(p, document_types, scope)
        ]
        filtered.append(_create_global_config())
        return filtered

    return []  # Unknown scope
```

**Impact**:
- **Lines saved**: ~30 (from 103 to 73)
- **Bugs fixed**: 1 location for project loading logic = easier to fix bugs
- **Maintainability**: Adding new scope = add case to routing, not duplicate iteration

---

## 2. Filter Composition Patterns

### Filter Application Order

**Current Sequence** (lines 667-756):

1. **Message filter** (lines 669-676): substring/regex/exact matching
2. **Emoji filter** (lines 678-682): exact emoji match
3. **Status filter** (lines 684-692): status → emoji mapping (BUGGY)
4. **Agent filter** (lines 694-698): exact agent name match
5. **Metadata filter** (lines 700-708): key-value matching with normalization
6. **Priority filter** (lines 710-714): priority level from metadata
7. **Category filter** (lines 716-720): category from metadata
8. **Confidence filter** (lines 722-726): minimum confidence threshold
9. **Time range filter** (lines 728-746): timestamp bounds
10. **Relevance filter** (lines 748-753): naive message length scoring

### Filter Characteristics

| Filter | Type | Short-Circuit | Expensive | Stateful | Bug |
|--------|------|---------------|-----------|----------|-----|
| Message | String match | Yes | Medium | No | No |
| Emoji | Exact match | Yes | Cheap | No | No |
| Status | Mapping + match | Yes | Cheap | No | **YES** |
| Agent | Exact match | Yes | Cheap | No | No |
| Metadata | Dict matching | Yes | Medium | No | No |
| Priority | Meta lookup | Yes | Cheap | No | No |
| Category | Meta lookup | Yes | Cheap | No | No |
| Confidence | Numeric compare | Yes | Cheap | No | No |
| Time range | DateTime parse | Yes | Expensive | No | No |
| Relevance | Calculation | No | Medium | No | No |

**Short-circuit**: Filter uses `continue` to skip entry immediately on mismatch.
**Expensive**: Filter requires parsing, normalization, or calculation.
**Stateful**: Filter depends on previous entries or external state.

### Filter Ordering Analysis

**Current Order Rationale** (inferred):
1. Message first: Most common filter, reject early
2. Emoji/status next: Cheap exact matches
3. Agent: Cheap exact match
4. Metadata/priority/category: Medium cost, check after cheap filters
5. Time range: Expensive (datetime parsing), check late
6. Relevance: No short-circuit, always evaluated

**Optimization Opportunity**:
Move time range filter earlier if timestamp is already parsed (check `parsed.get("ts_iso")`).

**Problem**: Filters applied in fixed order, cannot:
- Reorder dynamically based on filter selectivity
- Apply most selective filter first
- Skip expensive filters if cheap filters already rejected entry

### Filter Composition Patterns

**Current Pattern** (Imperative):
```python
for entry in entries:
    if condition1: continue
    if condition2: continue
    # ... 8 more filters
    results.append(entry)
```

**Characteristics**:
- **Not composable**: Cannot combine filters programmatically
- **Not testable**: Cannot test single filter in isolation
- **Not reorderable**: Order is hard-coded
- **Not extensible**: Adding filter requires editing monolith

**Proposed Pattern** (Functional):
```python
class Filter(ABC):
    @abstractmethod
    def matches(self, entry: Dict) -> bool:
        pass

class MessageFilter(Filter):
    def __init__(self, pattern: str, mode: str, case_sensitive: bool):
        self.pattern = pattern
        self.mode = mode
        self.case_sensitive = case_sensitive

    def matches(self, entry: Dict) -> bool:
        message = entry.get("message", "")
        return message_matches(message, self.pattern, self.mode, self.case_sensitive)

# Similarly: EmojiFilter, AgentFilter, etc.

class FilterChain:
    def __init__(self, filters: List[Filter]):
        self.filters = filters

    def apply(self, entries: List[Dict]) -> List[Dict]:
        return [
            entry for entry in entries
            if all(f.matches(entry) for f in self.filters)
        ]

# Usage
filters = [
    MessageFilter(message, mode, case_sensitive),
    AgentFilter(agents),
    TimeRangeFilter(start, end),
]
filtered = FilterChain(filters).apply(entries)
```

**Characteristics**:
- **Composable**: Filters are first-class objects
- **Testable**: Each filter tested independently
- **Reorderable**: Pass filters in any order
- **Extensible**: Add new filter = new class, no monolith changes

### Filter Interaction Analysis

**Independent Filters** (no interaction):
- Message, emoji, agent, time range, relevance

**Dependent Filters** (share data source):
- Priority, category, confidence all read from `entry["meta"]`
- Could be unified into MetadataFilter with predicates

**Conflicting Filters** (potential bugs):
- Emoji filter + status filter: Status maps to emojis, applying both may be redundant
- If emoji="✅" and status=["error"], no matches (emoji not in error emoji set)

**Current Behavior** (AND logic):
All filters must match for entry to be included.

**Missing Behavior** (OR logic):
Cannot express "entries with status=success OR status=info"
Must be done via status=["success", "info"] which checks if emoji in union of status emojis.

---

## 3. Cross-Project Query Mechanics

### Project Iteration Strategy

**Step 1: Project Discovery** (lines 1276-1340)
- Load project names from `state.projects`
- For each project:
  - Try `state.get_project(name)` first
  - Fallback to `load_project_config(name)` if state incomplete
  - Skip projects without valid progress_log

**Step 2: Project Filtering** (lines 1344-1373)
- Apply `_project_has_document_types()` filter
- Check if project has requested document types
- Document type detection:
  - `research`: Check if `docs_dir/research/` exists
  - `architecture`: Check if `ARCHITECTURE_GUIDE.md` exists
  - `bugs`: Check if `BUG_LOG.md` exists
  - `progress`: Always true (all projects have progress logs)
  - `global`: Skip (global log handled separately)

**Step 3: Document Search** (lines 1433-1728)
- For each project, dispatch to document-specific search:
  - Progress logs: `_query_file()` (generic log parsing)
  - Research docs: `_search_research_documents()` (markdown parsing)
  - Architecture docs: `_search_architecture_documents()` (markdown parsing)
  - Bug docs: `_search_bug_documents()` (structured report parsing)

**Step 4: Result Aggregation** (lines 1433-1558)
- Collect results from all projects
- Apply global filters to aggregated results
- Apply pagination to final result set
- Add project context to each entry

### Result Aggregation Pattern

**Current** (lines 1433-1558):
```python
all_results = []
for project in projects:
    project_results = await _search_single_project(project, ...)
    # Add project name to each entry
    for entry in project_results:
        entry["project"] = project["name"]
    all_results.extend(project_results)

# Apply pagination to aggregated results
paginated = all_results[start:end]
```

**Characteristics**:
- Sequential project search (not parallel)
- Result sets merged before pagination
- Project context added post-search
- No per-project result limits (could return 1000 entries from one project, 0 from others)

**Optimization Opportunity**:
Parallel project search with `asyncio.gather()`:

```python
tasks = [_search_single_project(p, ...) for p in projects]
project_results = await asyncio.gather(*tasks)
all_results = [entry for results in project_results for entry in results]
```

**Performance Impact**:
- Current: O(N × T) where N=projects, T=search time per project
- Parallel: O(T_max) where T_max=slowest project search
- Speedup: Up to Nx for N projects (assuming I/O bound)

### Cross-Project Pagination Issues

**Problem**: Pagination applied after aggregation.

**Scenario**:
- Page 1: Projects A, B, C each have 100 matching entries
- Total: 300 entries
- Page size: 10
- Result: Page 1 shows first 10 entries from Project A (skewed distribution)

**User Expectation**:
Page 1 shows mixed results from all projects (round-robin or interleaved).

**Current Behavior**:
Page 1 shows results in project discovery order (Projects added to list sequentially).

**Fix** (not currently implemented):
Interleave results by timestamp or round-robin by project before pagination.

---

## 4. Unification Opportunities

### Opportunity 1: Shared Project Loader [BUCKET:project_management]

**Current**: Duplicated project loading in lines 1281-1297 and 1312-1330.

**Proposed**: Extract `_load_all_projects(state)` and `_load_project_with_fallback(state, name)`.

**Impact**:
- Lines saved: ~30
- Bugs centralized: Project loading logic in one place
- Extensibility: Easy to add caching, error handling, or alternative loaders

**Used By**:
- `query_entries` (this tool)
- `list_projects` (likely has similar logic)
- Any future cross-project tools

### Opportunity 2: Filter Chain Abstraction [BUCKET:filtering]

**Current**: 10 hard-coded inline filters (lines 667-756).

**Proposed**: 10 filter classes implementing `Filter` interface, composed via `FilterChain`.

**Impact**:
- Lines added: +80 (filter classes in separate module)
- Lines removed: ~50 (from inline checks)
- Net: +30 lines but vastly improved testability
- Bugs fixed: Status filter inversion bug fixed during refactor

**Used By**:
- `query_entries` (this tool)
- `read_recent` (has similar filtering)
- `list_projects` (could filter projects by criteria)

### Opportunity 3: Document Search Strategies [BUCKET:search_strategy]

**Current**: 4 document-specific search functions with duplicated parsing logic.

**Proposed**: Strategy pattern with shared `DocumentSearchStrategy` base class.

```python
class DocumentSearchStrategy(ABC):
    @abstractmethod
    async def search(self, project: Dict, filters: FilterChain) -> List[Dict]:
        pass

class ProgressLogStrategy(DocumentSearchStrategy):
    async def search(self, project, filters):
        # Search PROGRESS_LOG.md
        pass

class ResearchDocStrategy(DocumentSearchStrategy):
    async def search(self, project, filters):
        # Search research/*.md
        pass

# Usage
strategy = DocumentSearchStrategyFactory.create(document_type)
results = await strategy.search(project, filters)
```

**Impact**:
- Lines reorganized: ~350 lines across 4 functions → 4 strategy classes
- Extensibility: Add new document type = new strategy class
- Testability: Each strategy testable independently

**Used By**:
- `query_entries` (this tool)
- Future: Document indexing, migration, archival tools

### Opportunity 4: Pagination Utility Usage [BUCKET:utilities]

**Current**: Manual pagination calculation (lines 779-833) despite importing `PaginationCalculator` (line 23).

**Proposed**: Use existing `_PAGINATION_CALCULATOR` instance.

```python
# Replace lines 779-833 with:
pagination_result = _PAGINATION_CALCULATOR.calculate(
    total_items=len(filtered_entries),
    page=page,
    page_size=page_size,
    limit=limit
)

paginated_entries = filtered_entries[pagination_result["start_idx"]:pagination_result["end_idx"]]
pagination_info = pagination_result["metadata"]
```

**Impact**:
- Lines saved: ~40 (from 54 to 14)
- Consistency: All tools use same pagination logic
- Bugs centralized: Pagination bugs fixed once, affect all tools

**Used By**:
- `query_entries` (this tool)
- `read_recent` (has pagination)
- `list_projects` (has pagination)

### Opportunity 5: Config Object Trust [BUCKET:config]

**Current**: Parameters validated → packaged into config → re-validated after extraction.

**Proposed**: Move validation into `QueryEntriesConfig.__init__()`, trust extracted parameters.

**Impact**:
- Lines removed: ~30 (from `_build_search_query`)
- Trust boundary: Config objects are authoritative
- Performance: Eliminate redundant validation

**Philosophy**:
Config objects should encapsulate validation. If config exists, parameters are valid.

---

## 5. Search Pattern Taxonomy

### Pattern: Single-Project Direct Search

**Used By**: Default `project` scope

**Characteristics**:
- Searches one log file
- No cross-project iteration
- Fastest query pattern

**Implementation**: `_search_single_project()` + `_query_file()`

### Pattern: Cross-Project Scatter-Gather

**Used By**: `all_projects`, `research`, `bugs`, `all` scopes

**Characteristics**:
- Iterate all projects
- Search each project's logs
- Aggregate results
- Apply global pagination

**Implementation**: `_resolve_cross_project_projects()` + `_handle_cross_project_search()`

**Optimization**: Parallelize with `asyncio.gather()`

### Pattern: Document-Type Filtered Search

**Used By**: `research`, `bugs` scopes

**Characteristics**:
- Iterate all projects
- Filter by document type presence
- Search only matching documents

**Implementation**: `_project_has_document_types()` + document-specific search strategies

### Pattern: Global-Only Search

**Used By**: `global` scope

**Characteristics**:
- Bypasses project iteration
- Searches special global log
- Fastest cross-cutting query

**Implementation**: Special config pointing to `docs/GLOBAL_PROGRESS_LOG.md`

---

## 6. Performance Characteristics

### Single-Project Query

**Complexity**: O(N) where N = entries in log file

**Bottlenecks**:
- File I/O: `read_all_lines(log_path)`
- Parsing: `parse_log_line(line)` for each entry
- Filtering: 10 filter checks per entry

**Optimizations**:
- Early filtering (message/emoji/agent) reduces parse count
- Pagination limits result set size
- Compact format reduces token generation

### Cross-Project Query

**Complexity**: O(P × N) where P = projects, N = avg entries per project

**Bottlenecks**:
- Sequential project iteration (not parallel)
- Repeated file I/O per project
- Result aggregation and re-pagination

**Optimizations**:
- Parallelize with `asyncio.gather()` → O(N_max)
- Per-project result limits (not implemented)
- Early termination if pagination quota met

### Document-Type Filtered Query

**Complexity**: O(P × D × N) where P = projects, D = docs per project, N = entries per doc

**Bottlenecks**:
- Markdown parsing overhead
- Filesystem checks (`exists()` for each doc type)
- Repeated normalization and parsing

**Optimizations**:
- Cache document existence checks
- Lazy document loading (only parse if matched)
- Index document metadata (not implemented)

---

## 7. Anti-Patterns Identified

### Anti-Pattern 1: Duplicated Iteration Logic

**Evidence**: Lines 1281-1297 vs 1312-1330 (49 lines duplicated)

**Impact**: Bug fixes must be applied twice, divergence risk

**Solution**: Extract shared `_load_all_projects()` utility

### Anti-Pattern 2: Inline Filter Composition

**Evidence**: Lines 667-756 (10 filters hard-coded)

**Impact**: Cannot test, reorder, or extend filters without editing monolith

**Solution**: Filter classes with composable `FilterChain`

### Anti-Pattern 3: Unused Utility Import

**Evidence**: `PaginationCalculator` imported (line 23) but manual pagination used (lines 779-833)

**Impact**: Code duplication, inconsistency across tools

**Solution**: Use `_PAGINATION_CALCULATOR` instance

### Anti-Pattern 4: Config Distrust Pattern

**Evidence**: Parameters validated → config → re-validated (lines 61-407, 496-528)

**Impact**: Redundant validation, config objects not authoritative

**Solution**: Trust config validation, remove post-extraction checks

### Anti-Pattern 5: Sequential Cross-Project Search

**Evidence**: `for project in projects:` loop (lines 1433-1558)

**Impact**: O(P × T) latency for P projects, slow for large project counts

**Solution**: Parallel search with `asyncio.gather()`

---

## 8. Recommendations

### High Priority

1. **Unify Project Loading Logic** [BUCKET:project_management]
   - Extract `_load_all_projects()` to eliminate 49-line duplication
   - Estimated effort: 1 hour
   - Impact: -30 LOC, centralized bug fixes

2. **Fix Status Filter Bug** [BUG]
   - Correct inverted for-else logic (lines 684-692)
   - Estimated effort: 15 minutes
   - Impact: Filter works correctly

3. **Use Pagination Calculator** [BUCKET:utilities]
   - Replace manual pagination with `_PAGINATION_CALCULATOR`
   - Estimated effort: 30 minutes
   - Impact: -40 LOC, consistency across tools

### Medium Priority

4. **Extract Filter Chain** [BUCKET:filtering]
   - Implement 10 filter classes with `FilterChain` composer
   - Estimated effort: 4 hours
   - Impact: +30 LOC net, vastly improved testability

5. **Parallelize Cross-Project Search**
   - Use `asyncio.gather()` for parallel project queries
   - Estimated effort: 2 hours
   - Impact: Up to Px speedup for P projects

### Low Priority

6. **Centralize Config Validation** [BUCKET:config]
   - Move validation into config constructors, eliminate re-validation
   - Estimated effort: 3 hours
   - Impact: -30 LOC from `_build_search_query`, clearer trust boundaries

7. **Document Search Strategy Pattern** [BUCKET:search_strategy]
   - Refactor 4 document search functions into strategy classes
   - Estimated effort: 6 hours
   - Impact: Improved extensibility, clearer separation of concerns

---

## Cross-Cutting Concerns

Patterns identified in query_entries that likely appear across Wave 1 tools:

- **[BUCKET:project_management]**: Project loading, state/config fallback
- **[BUCKET:filtering]**: Entry filtering logic
- **[BUCKET:utilities]**: Pagination calculation
- **[BUCKET:config]**: Config object validation and trust
- **[BUCKET:search_strategy]**: Search routing and dispatch
- **[BUCKET:error_handling]**: Multi-tier error recovery (in main wiki doc)

---

**End of Search Pattern Analysis**

**Next Steps**:
1. Aggregate [BUCKET:*] tags across Wave 1 tools
2. Identify modules shared by 2+ tools
3. Create implementation specs for unification opportunities
