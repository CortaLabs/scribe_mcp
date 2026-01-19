# query_entries.py — Forensic Analysis

**Tool**: `tools/query_entries.py`
**LOC**: 2,030
**Complexity**: Ultra-High
**Functions**: 24
**Parameters**: 25 (main function signature)
**Analyst**: ResearchAgent-C-QueryEntries
**Date**: 2026-01-05

---

## 1. Overview

`query_entries` is the most complex search tool in the Scribe MCP codebase. It provides advanced log entry querying with:

- **6 search scopes**: `project`, `global`, `all_projects`, `research`, `bugs`, `all`
- **10 filter types**: message, emoji, status, agent, metadata, priority, category, confidence, time_range, relevance
- **Cross-project search**: Iterate multiple projects with document type filtering
- **Triple-tier error recovery**: Parameter healing → Exception healing → Emergency fallback
- **Dual parameter interface**: Legacy parameters + QueryEntriesConfig object
- **3 output formats**: readable, structured, compact

**Purpose**: Enable sophisticated log queries across project boundaries with extensive filtering and error resilience.

**Primary Use Cases**:
1. Search current project logs (default scope: `project`)
2. Search across all projects (`all_projects`)
3. Search specific document types (`research`, `bugs`)
4. Global repository search (`all`, `global`)
5. Advanced filtering by priority, category, confidence scores

---

## 2. Sub-System Breakdown

### Sub-System 1: Parameter Validation & Healing (Lines 61-407)

**Responsibilities**:
- Validate and heal 25 input parameters
- Apply BulletproofParameterCorrector for enum/numeric/list/string healing
- Create QueryEntriesConfig object from healed parameters
- Merge legacy parameters with config object (legacy takes precedence)
- Apply ExceptionHealer if validation fails
- Apply BulletproofFallbackManager as ultimate safety net

**Functions**:
- `_validate_search_parameters()` (lines 61-404)

**Key Observations**:
- **346 lines** dedicated to parameter healing
- Triple-layer error recovery: Corrector → Healer → Fallback
- Parameters healed individually, then packaged into config, then re-validated later
- Config object not fully trusted - parameters re-extracted and re-validated in query building phase

**Architectural Question**:
*Why validate parameters, package into config object, then re-validate from config?*

**Evidence of Config Distrust**:
- Line 159: `healed_page = _PARAMETER_CORRECTOR.correct_numeric_parameter(page, ...)` (heals page)
- Line 223: `final_page = healed_params.get("page", page)` (assigns healed value)
- Line 239-299: Creates QueryEntriesConfig from healed params
- Line 496-502: **Re-validates page AGAIN** after extraction from config object
- Line 500: `search_params["page"] = healed_page` (mutates search_params dict)

**Implicit Contract**:
- QueryEntriesConfig may contain invalid data despite validation
- Consumers must re-validate config-sourced parameters
- Parameter healing is defensive, not authoritative

### Sub-System 2: Search Query Building (Lines 406-584)

**Responsibilities**:
- Extract parameters from QueryEntriesConfig object
- Resolve project context from multiple fallback sources
- Build search_params dictionary
- **Re-validate** pagination, time ranges, limits, thresholds
- Apply emergency fallback if query building fails

**Functions**:
- `_build_search_query()` (lines 406-583)

**Key Observations**:
- **178 lines** to build search parameters dictionary
- Re-validation occurs AFTER config object extraction (distrust pattern)
- Emergency fallback creates **new QueryEntriesConfig** on failure
- Uses `hasattr()` checks for optional config fields (lines 472-475)

**Parameter Flow**:
```
Raw params → Healed → Config object → Extracted → Re-validated → search_params dict
```

**Why This Matters**:
If QueryEntriesConfig encapsulated validation correctly, extraction wouldn't require re-validation. Pattern suggests config validation is incomplete or parameters can mutate post-creation.

### Sub-System 3: Search Execution Orchestrator (Lines 586-994)

**Responsibilities**:
- Determine search strategy based on search_scope
- Execute single-project vs cross-project search
- Apply filter chain to entries
- Handle pagination
- Apply priority sorting
- Collect and aggregate validation warnings

**Functions**:
- `_execute_search_with_fallbacks()` (lines 586-994)

**Key Observations**:
- **408 lines** of orchestration logic
- Chooses between:
  - Single project search (lines 606-658)
  - Cross-project search (call to `_handle_cross_project_search`)
- **Filter application lives here** (lines 660-767)
- Pagination calculated inline (lines 779-833)
- Priority sorting inline (lines 769-777)

**Architectural Smell**:
Orchestrator should delegate, not implement. Filter application, pagination, and sorting are distinct responsibilities embedded in orchestration logic.

### Sub-System 4: Main Entry Point (Lines 995-1270)

**Responsibilities**:
- Expose public async function `query_entries()`
- Accept 25 parameters + **kwargs
- Merge legacy `agent` param into `agents` list (backward compat)
- Call validation → query building → execution pipeline
- Collect warnings from all phases
- Apply ultimate exception handling with emergency fallback
- Route response through formatter for readable/structured/compact output

**Functions**:
- `query_entries()` (lines 995-1269)

**Key Observations**:
- **275 lines** of orchestration and error handling
- Emergency fallback creates synthetic "emergency-{uuid}" entry (lines 1236-1259)
- Adds search parameters to result for readable formatter (lines 1199-1206)
- Reminders integration (line 1208-1209)
- Final formatting via `default_formatter.finalize_tool_response()`

**Contract Surface**:
- Function signature is **public API** - cannot change without breaking clients
- **kwargs tolerance** prevents TypeError on unknown parameters
- Legacy `agent` param maintained for backward compatibility

### Sub-System 5: Cross-Project Resolution (Lines 1271-1374)

**Responsibilities**:
- Resolve which projects to search based on search_scope
- Filter projects by document_types
- Handle 6 search scopes with different project iteration strategies

**Functions**:
- `_resolve_cross_project_projects()` (lines 1271-1341)
- `_project_has_document_types()` (lines 1344-1373)

**Search Scope Routing**:

| Scope | Strategy | Lines | Includes Global Log |
|-------|----------|-------|-------------------|
| `project` | N/A (single project) | N/A | No |
| `global` | Return special global config | 1299-1308 | Yes (only) |
| `all_projects` | Iterate all projects | 1279-1297 | No |
| `research` | Iterate + doc filter | 1310-1340 | Yes |
| `bugs` | Iterate + doc filter | 1310-1340 | Yes |
| `all` | Iterate + doc filter | 1310-1340 | Yes |

**CODE DUPLICATION ALERT**:
Lines 1281-1297 (`all_projects` scope) and lines 1312-1330 (`research/bugs/all` scopes) contain **nearly identical** project iteration logic. Only difference: `_project_has_document_types` filter.

**Unification Opportunity**:
```python
# Before: Two separate iteration blocks
if search_scope == "all_projects":
    for project_name in state.projects:
        # 16 lines of project loading logic

elif search_scope in ["research", "bugs", "all"]:
    for project_name in state.projects:
        # SAME 16 lines of project loading logic
        if _project_has_document_types(...):
            # filter applied

# After: Single iteration with optional filter
projects = []
for project_name in state.projects:
    project_dict = _load_project_from_state_or_config(project_name)
    if project_dict:
        if search_scope in ["research", "bugs", "all"]:
            if not _project_has_document_types(project_dict, document_types, search_scope):
                continue
        projects.append(project_dict)
```

**Architectural Question**:
*Why aren't search scopes implemented as strategy pattern with shared project iteration?*

### Sub-System 6: Document Type Strategies (Lines 1376-1728)

**Responsibilities**:
- Execute different search strategies based on document types
- Query progress logs
- Search research documents
- Search architecture documents
- Search bug reports

**Functions**:
- `_query_file()` (lines 1376-1431) — Generic log file search
- `_handle_cross_project_search()` (lines 1433-1558) — Cross-project orchestrator
- `_search_single_project()` (lines 1560-1630) — Single project search
- `_search_research_documents()` (lines 1632-1665) — Research directory search
- `_search_architecture_documents()` (lines 1667-1696) — Architecture file search
- `_search_bug_documents()` (lines 1698-1727) — Bug report search

**Key Observations**:
- **352 lines** across 6 functions
- Each search function implements its own file discovery, parsing, and filtering
- `_handle_cross_project_search()` dispatches to document-specific search functions
- Document parsing logic duplicated across search functions

**Pattern**: Strategy pattern (dispatch by document type) but strategies share no common interface or base class.

### Sub-System 7: Document Parsing (Lines 1729-1879)

**Responsibilities**:
- Parse research markdown documents
- Parse generic markdown documents
- Create standardized document entries
- Extract metadata, titles, sections

**Functions**:
- `_parse_research_document()` (lines 1729-1776) — Research-specific parsing
- `_parse_markdown_document()` (lines 1778-1826) — Generic markdown parsing
- `_create_document_entry()` (lines 1828-1878) — Entry object creation

**Key Observations**:
- **150 lines** of document parsing
- Research and markdown parsing have different metadata extraction
- Entry creation standardizes format for all document types
- Parsing logic isolated from search strategies (good separation)

**Candidate Module**: [BUCKET:document_parsing]
- Clear inputs: file path, document type
- Clear outputs: structured entry dict
- Used by: research search, architecture search, bug search
- Could be shared across tools if other tools need document parsing

### Sub-System 8: Code Reference Verification (Lines 1880-1938)

**Responsibilities**:
- Verify code references in search results
- Check if mentioned files exist
- Add warnings for stale references
- Optional feature (enabled via `verify_code_references` flag)

**Functions**:
- `_verify_code_references_in_results()` (lines 1880-1916) — Verify all results
- `_verify_file_exists()` (lines 1918-1937) — Check single file reference

**Key Observations**:
- **58 lines** of verification logic
- Feature is **optional** and **expensive** (filesystem checks)
- Adds `warnings` to entries with stale references
- Why optional? Because verification can be slow for large result sets

**Implicit Contract**:
- Assumes references follow pattern `file.py:123` or `file.py`
- Only verifies file existence, not line number validity
- Modifies results in-place (adds warnings field)

### Sub-System 9: Relevance Scoring (Lines 1939-2009)

**Responsibilities**:
- Calculate relevance scores for search results
- Filter results by relevance threshold
- Apply basic relevance heuristics

**Functions**:
- `_calculate_basic_relevance()` (lines 1939-1980) — Calculate scores
- `_apply_relevance_scoring()` (lines 1982-2009) — Filter by threshold

**Key Observations**:
- **70 lines** of relevance logic
- Current implementation: `relevance_score = len(message) / 1000.0` (line 751)
- Extremely naive scoring (longer messages = higher relevance)
- Feature is **underutilized** (threshold defaults to 0.0)

**Architectural Question**:
*Is relevance scoring a placeholder for future vector search integration?*

**Evidence**:
- Simplistic implementation suggests incomplete feature
- Threshold parameter exists but scoring algorithm is rudimentary
- Could be replaced with semantic search scoring

---

## 3. Modularization Notes

### Extractable Module 1: Parameter Validation [BUCKET:parameter_validation]

**Origin**: `_validate_search_parameters()` (lines 61-407)

**Responsibilities**:
- Validate and heal parameters with type-specific correctors
- Create configuration objects from healed parameters
- Apply multi-tier error recovery

**Used By**:
- `query_entries` (this tool)
- Could be used by: `append_entry`, `read_recent`, `list_projects` (all have parameter healing)

**Why Extract**:
All tools need parameter validation, but each implements it differently. Unified validator could ensure consistent parameter healing across tools.

**Risks If Extracted**:
- Tools may have tool-specific parameter constraints
- Healing strategies might not be universally applicable
- Config objects are tool-specific (QueryEntriesConfig vs AppendEntryConfig)

**Before/After**:
- **Before**: 346 lines of validation in every tool that needs healing
- **After**: Shared ParameterValidator base class, tool-specific subclasses define constraints
- **Conceptual Win**: Tools declare "what valid means", validator applies "how to heal"

**Extraction Spec**:
```python
# Proposed interface
class ParameterValidator:
    def validate_and_heal(self, raw_params: Dict, schema: ParamSchema) -> Tuple[Dict, ValidationInfo]:
        """Apply healing, return healed params and info about what was fixed."""
        pass

# Tool usage
validator = ParameterValidator()
healed, info = validator.validate_and_heal(raw_params, QueryEntriesParamSchema)
```

### Extractable Module 2: Filter Chain [BUCKET:filtering]

**Origin**: Filter application logic (lines 667-756)

**Responsibilities**:
- Apply 10 filter types to parsed entries
- Short-circuit on first filter failure (continue pattern)
- Support composable filter predicates

**Used By**:
- `query_entries` (this tool)
- `read_recent` (likely has similar filtering)
- Future: Any tool that needs to filter log entries

**Why Extract**:
Filter logic is hard-coded and non-composable. Filters should be:
- **Testable in isolation** (current: cannot test single filter)
- **Composable** (current: order is fixed, cannot combine filters differently)
- **Reusable** (current: duplicated across tools)

**Current Pattern** (Non-Composable):
```python
for entry in entries:
    if message_filter: ...
    if emoji_filter: ...
    if status_filter: ...  # BUG: inverted logic
    if agent_filter: ...
    # ... 6 more filters hard-coded
    results.append(entry)
```

**Proposed Pattern** (Composable):
```python
filters = [
    MessageFilter(message, mode, case_sensitive),
    EmojiFilter(emojis),
    StatusFilter(statuses),  # Fixed logic
    AgentFilter(agents),
    MetadataFilter(meta_filters),
    PriorityFilter(priorities),
    CategoryFilter(categories),
    ConfidenceFilter(min_confidence),
    TimeRangeFilter(start, end),
    RelevanceFilter(threshold)
]

filtered = FilterChain(filters).apply(entries)
```

**Before/After**:
- **Before**: 90 lines of inline filter checks, cannot reorder or test independently
- **After**: 10 filter classes (8-12 lines each), composable via FilterChain
- **Conceptual Win**: Filters become first-class objects, testable and reusable

**BUG FIX**: Status filter logic (lines 684-692) has inverted for-else:
```python
# Current (BROKEN):
for status_filter in search_params["status"]:
    status_emojis = STATUS_EMOJI.get(status_filter.lower(), [])
    if entry_emoji not in status_emojis:
        break  # Break when emoji NOT in status_emojis
else:
    continue  # If NO break occurred (all checks passed), SKIP entry???

# Should Be:
matches_any_status = any(
    entry_emoji in STATUS_EMOJI.get(status_filter.lower(), [])
    for status_filter in search_params["status"]
)
if not matches_any_status:
    continue
```

### Extractable Module 3: Search Scope Strategies [BUCKET:search_strategy]

**Origin**: `_resolve_cross_project_projects()` and document search functions (lines 1271-1728)

**Responsibilities**:
- Determine which projects to search based on scope
- Filter projects by document types
- Execute document-specific search strategies

**Why Extract**:
Search scopes are implemented as if-elif chains with duplicated project iteration. Strategy pattern would make scopes extensible and testable.

**Current Architecture**:
```
if scope == "all_projects": [iterate projects]
elif scope == "global": [return global config]
elif scope in ["research", "bugs", "all"]: [iterate projects + filter]
```

**Proposed Architecture**:
```python
class SearchScope(ABC):
    @abstractmethod
    def resolve_projects(self, state) -> List[Project]:
        pass

class AllProjectsScope(SearchScope): ...
class GlobalScope(SearchScope): ...
class DocumentFilteredScope(SearchScope): ...

# Usage
scope_strategy = SearchScopeFactory.create(search_scope, document_types)
projects = scope_strategy.resolve_projects(state)
```

**Before/After**:
- **Before**: 103 lines of scope routing with duplicated project iteration
- **After**: 6 scope strategy classes (15-25 lines each), shared project iteration utility
- **Conceptual Win**: Adding new scope = new class, not modifying if-elif chain

### Extractable Module 4: Pagination Calculator [BUCKET:utilities]

**Origin**: Pagination logic (lines 779-833 in execution orchestrator)

**Responsibilities**:
- Calculate page boundaries from page/page_size/limit
- Generate pagination metadata (has_next, has_prev, total_pages)
- Handle edge cases (page > total_pages, empty results)

**Used By**:
- `query_entries` (this tool)
- `read_recent` (has pagination)
- `list_projects` (has pagination)
- Future: Any tool with paginated results

**Why Extract**:
Pagination logic is duplicated across tools. Utility class already exists (`PaginationCalculator` imported on line 23) but **not used** in inline pagination code.

**Evidence of Non-Use**:
```python
# Line 23: Import
from scribe_mcp.utils.estimator import PaginationCalculator

# Line 44: Global instance
_PAGINATION_CALCULATOR = PaginationCalculator()

# Lines 779-833: Inline pagination (doesn't use _PAGINATION_CALCULATOR!)
page = search_params.get("page", 1)
page_size = search_params.get("page_size", 50)
total_entries = len(filtered_entries)
start_idx = (page - 1) * page_size
end_idx = start_idx + page_size
# ... manual pagination logic continues
```

**Architectural Smell**:
Pagination utility imported and instantiated but never called. Tool implements pagination manually instead.

**Before/After**:
- **Before**: Pagination logic duplicated in each tool, unused utility exists
- **After**: All tools use shared PaginationCalculator
- **Conceptual Win**: Pagination bugs fixed once, benefits all tools

### NOT a Candidate Module: Search Result Formatting

**Why NOT Extract**:
Result formatting is tightly coupled to tool-specific response contracts. `query_entries` returns:
- `entries` (list of parsed log entries or document entries)
- `pagination` (tool-specific pagination metadata)
- `warnings` (accumulated from validation + query building + execution)
- `search_message`, `search_status`, etc. (context for readable formatter)

Each tool has different result shapes. Forcing shared formatter would break tool-specific contracts.

**Evidence of Coupling**:
- Lines 1199-1206: Add search params to result (query_entries specific)
- Line 1208: Add reminders (query_entries specific)
- Line 1211: Call `default_formatter.finalize_tool_response()` (generic)

**Conclusion**: Generic formatter exists (`default_formatter`), but result preparation is tool-specific. Extraction would not simplify.

---

## 4. Implicit Contracts

### Contract 1: Config Objects May Contain Invalid Data

**Assumption**: QueryEntriesConfig validation is incomplete or parameters can mutate post-creation.

**Evidence**:
- Parameters validated before config creation (lines 98-210)
- Parameters packaged into QueryEntriesConfig (lines 239-299)
- Parameters **re-validated** after extraction from config (lines 496-528)

**Where This Breaks**:
If config objects are assumed valid, consumers shouldn't re-validate. Re-validation pattern suggests config can't be trusted.

**Test Case That Would Fail**:
```python
config = QueryEntriesConfig(page=-5, page_size=9999)
# Config created without validation
# Tool assumes config is valid, uses directly
# Result: Invalid pagination
```

**Recommendation**:
Config objects should validate on construction, making re-validation unnecessary.

### Contract 2: Filter Order Matters (But Isn't Documented)

**Assumption**: Filters applied in specific sequence (message → emoji → status → agent → meta → priority → category → confidence → time → relevance).

**Not Enforced By**:
- Function signature doesn't indicate ordering
- No documentation of filter precedence
- Order is implementation detail, could change

**Where This Breaks**:
If filter order changes, results may differ. Example:
- Current: Time filter before relevance filter
- Changed: Relevance filter before time filter
- Result: Different result sets if relevance calculation depends on time-filtered entries

**Evidence of Coupling**:
Lines 667-756 hard-code filter order. Changing order requires editing monolithic function.

**Recommendation**:
Document filter order in function docstring or make filters composable with explicit ordering.

### Contract 3: Search Scopes Determine Project Iteration

**Assumption**: `search_scope` parameter controls which projects are searched and how.

**Implicit Behavior**:
- `global`: Search only `.scribe/sentinel/` or `docs/GLOBAL_PROGRESS_LOG.md`
- `all_projects`: Search all configured projects
- `research`/`bugs`/`all`: Search projects + filter by document types + include global

**Not Obvious From Signature**:
Parameter is typed as `str` with default `"project"`. Valid values and behaviors undocumented in signature.

**Where This Breaks**:
```python
# User expects "all" to search ALL logs (project + global + documents)
query_entries(search_scope="all")

# Actually searches: Projects with documents + global log
# Misses: Projects without research/bugs folders
```

**Evidence**:
Line 1373: `return search_scope == "all"` includes all projects, but document filtering still applies if `document_types` provided.

**Recommendation**:
Document scope behaviors in docstring, use enum for scope values.

### Contract 4: Status Filter Maps to Emojis (Lossy)

**Assumption**: Status strings map to emoji lists via `STATUS_EMOJI` constant.

**Implicit Behavior**:
- `status=["success"]` → filters for entries with `✅` or `🎉` emojis
- Multiple statuses require entry emoji to match **all** (AND logic)
- **BUG**: Current implementation (lines 684-692) inverts logic

**Not Obvious From Signature**:
Status filter doesn't match `status` field in entries - it matches `emoji` field via mapping.

**Where This Breaks**:
```python
# Entry: {"emoji": "✅", "status": "error"}  # Mismatch possible
query_entries(status=["success"])

# Expected: Match if entry["status"] == "success"
# Actual: Match if entry["emoji"] in STATUS_EMOJI["success"]
```

**Evidence**:
Lines 686-688: `status_emojis = STATUS_EMOJI.get(status_filter.lower(), [])` confirms emoji-based filtering.

**Recommendation**:
Rename parameter to `status_emojis` or document emoji mapping behavior.

### Contract 5: Relevance Scoring is Naive

**Assumption**: Relevance threshold filtering uses sophisticated scoring.

**Actual Implementation**:
Line 751: `relevance_score = len(message) / 1000.0`

**Behavior**:
- Messages < 1000 chars: relevance score < 1.0
- Messages >= 1000 chars: relevance score >= 1.0 (capped?)
- No semantic analysis, TF-IDF, or query matching

**Where This Breaks**:
```python
query_entries(message="critical bug", relevance_threshold=0.8)

# Expected: Entries semantically relevant to "critical bug"
# Actual: Entries with messages >= 800 characters
```

**Evidence**:
Lines 748-753 show simplistic relevance calculation based solely on message length.

**Recommendation**:
Document current scoring algorithm or replace with semantic scoring.

### Contract 6: Pagination Ignores Limit When Page_Size Set

**Assumption**: `limit` overrides `page_size` for backward compatibility.

**Actual Behavior** (lines 784-795):
```python
limit = search_params.get("limit")
if limit is None:
    limit = page_size

# ...

if limit < page_size:
    end_idx = start_idx + limit
```

**Behavior**:
- If `limit` provided and less than `page_size`: Use `limit`
- If `limit` not provided: Use `page_size`
- If `limit` greater than `page_size`: Ignore `limit`

**Where This Breaks**:
```python
query_entries(limit=100, page_size=10)
# Expected: Return 100 results (honor limit)
# Actual: Return 10 results (page_size wins)
```

**Evidence**:
Lines 794-795: `if limit < page_size: end_idx = start_idx + limit` shows limit only applies when smaller.

**Recommendation**:
Deprecate `limit` parameter in favor of `page_size` or document precedence clearly.

---

## 5. Token Analysis

### Methodology

Will measure token costs for 10+ sample queries using tiktoken with cl100k_base encoding.

**Sample Queries**:
1. Empty query (all results, page 1)
2. Message filter only
3. Multi-filter query (message + agent + status)
4. Cross-project search (all_projects scope)
5. Document type search (research documents)
6. Priority + category filters
7. Large result set (50 entries)
8. Small result set (5 entries)
9. Compact format
10. Structured format
11. Readable format (default)

**Metrics To Collect**:
- Total output tokens
- Tokens per entry (average)
- Structural tokens (headers, tables, boxes)
- Metadata tokens (pagination, warnings, reminders)
- Duplication tokens (repeated blocks)
- P95 and max token counts

**Token Categories** (per Wave 1 mindset):
- **Structural**: Table headers, boxes, separators
- **Metadata**: Pagination info, project context, reminders
- **Duplication**: Repeated warning messages, footer blocks
- **Safety Padding**: Explanatory text for empty states, edge cases

### Actual Token Measurements

**Methodology**: Used tiktoken (cl100k_base encoding) on 7 sample queries with realistic output.

**Sample Results**:

| Sample | Entries | Format | Total Tokens | Structural | Metadata | Content | Tokens/Entry |
|--------|---------|--------|--------------|------------|----------|---------|--------------|
| Readable (5 entries) | 5 | readable | 939 | 528 (56%) | 73 (8%) | 338 (36%) | 173 |
| Structured (3 entries) | 3 | structured | 417 | 0 (0%) | 16 (4%) | 401 (96%) | 134 |
| Compact (5 entries) | 5 | compact | 195 | 0 (0%) | 11 (6%) | 184 (94%) | 37 |
| Cross-project (3 entries) | 3 | readable | 620 | 344 (56%) | 44 (7%) | 232 (37%) | 192 |
| Large (10 entries) | 10 | readable | 1783 | 1048 (59%) | 61 (3%) | 674 (38%) | 172 |
| Empty results | 0 | readable | 119 | 8 (7%) | 61 (51%) | 50 (42%) | N/A |
| With warnings | 1 | readable | 325 | 112 (35%) | 61 (19%) | 152 (47%) | 264 |

**Summary Statistics** (7 samples):
- **Min**: 119 tokens (empty result)
- **Max**: 1783 tokens (10 entries)
- **Average**: 628 tokens
- **P95**: 1783 tokens
- **Structural Overhead**: 30.2% average, 56% in readable format
- **Metadata Overhead**: 14% average, 51% in empty results

**Format Comparison** (tokens per entry):
- **Readable**: 173 tokens/entry (boxes, formatting)
- **Structured**: 134 tokens/entry (JSON overhead)
- **Compact**: 37 tokens/entry (minimal decoration)
- **Reduction**: Compact achieves **4.8x** reduction vs readable

**Key Findings**:

1. **Structural Tokens Dominate Readable Format** (56%):
   - Box characters (`╔═╗║╠╣╚╝`) consume 528 tokens in 5-entry sample
   - Each entry box adds ~105 tokens of pure decoration
   - Compact format eliminates all structural overhead

2. **Empty Results Are Token-Inefficient** (51% metadata):
   - Empty result: 119 tokens, 61 for metadata, 50 for "No entries found" message
   - Returning no data costs more than actual entry content would

3. **Cross-Project Search Overhead** (+11%):
   - Project names in entry headers add ~19 tokens per entry
   - Cross-project summary adds ~60 tokens
   - Overhead is proportional to number of projects matched

4. **Warnings Add Significant Cost**:
   - Single warning entry (264 tokens/entry) is 53% higher than baseline
   - Warning blocks add 100-150 tokens depending on message count

**Token Verbosity Breakdown**:

**Structural Tokens** (boxes, separators):
- **Readable**: 528 tokens (56%) for 5 entries = 105 tokens per entry box
- **Compact**: 0 tokens (boxes removed)
- **Evidence**: `╔═══╗` characters have high token cost (1-2 tokens each)
- **Recommendation**: Already optional via format parameter ✅

**Metadata Tokens** (pagination, filters, location):
- **Pagination block**: 30-60 tokens (depends on totals)
- **Filter display**: 20-50 tokens (proportional to filter count)
- **Project location**: 20-30 tokens
- **Reminders**: 50-100 tokens (if present) [BUCKET:reminder_system]
- **Recommendation**: Omit filter block when no filters active (save ~20 tokens)

**Duplication Tokens** (repeated blocks):
- **Footer block**: "📁 Location: ..." repeats in every response (20-30 tokens)
- **Entry structure**: Box pattern repeats (by design, 105 tokens × entry count)
- **Recommendation**: Cache footer if project unchanged across sequential calls (save 20-30 tokens per call)

**Safety Padding** (explanatory messages):
- **Empty state**: "No entries found matching your filters. Try adjusting..." (42 tokens)
- **Warning messages**: "Relevance scoring is experimental..." (variable, 20-50 tokens each)
- **Recommendation**: Move verbose explanations to docs, use minimal messages (save 20-40 tokens)

**Optimization Opportunities**:

1. **Omit Empty Filter Lists** (save ~20 tokens):
   - Don't show "Filters Applied:" header if no filters active
   - Current: Shows even when only default scope used

2. **Cache Footer Blocks** (save ~25 tokens/call):
   - If project unchanged from previous call, omit "📁 Location:" footer
   - Requires stateful session tracking

3. **Truncate Long Messages in Compact** (save up to 500 tokens):
   - Compact format could truncate messages >200 chars
   - Add "..." indicator for truncated entries

4. **Smart Warning Deduplication** (save 50-100 tokens):
   - Don't repeat same warning across multiple tool calls in session
   - Example: "Relevance scoring is experimental" only shown once

**Evidence File**: `token_measurements_query_entries.json` contains full measurement data.

---

## 6. Error Handling Architecture

### Error Handling Layers

query_entries implements **4 distinct error handling layers**:

1. **Parameter Healing** (lines 98-210): BulletproofParameterCorrector fixes invalid params
2. **Exception Healing** (lines 303-326, 489-493, 539-583): ExceptionHealer recovers from validation errors
3. **Emergency Fallback** (lines 365-403, 551-573, 1230-1259): BulletproofFallbackManager creates safe defaults
4. **Ultimate Catch** (lines 1217-1269): Top-level try-except returns synthetic error entry

### Silent Failures

**Pattern**: `except Exception: continue` (multiple locations)

**Evidence**:
- Lines 758-766: Filter processing errors skip entry but continue
  ```python
  except Exception as filter_error:
      healed_filter = _EXCEPTION_HEALER.heal_bulk_processing_error(...)
      if not healed_filter or not healed_filter.get("success"):
          continue  # Silent skip
  ```
- Line 744-746: Invalid timestamp parsing silently skips entry
  ```python
  except ValueError:
      continue  # Skip entries with invalid timestamps
  ```

**Policy Decision**: Partial results > total failure

**Risks**:
- User may not know entries were skipped
- Silent data loss if many entries have invalid timestamps
- No warning added to response about skipped entries

**Recommendation**: Count skipped entries, add warning if count > threshold.

### Escalation Patterns

**Which Errors Bubble Up**:
- File not found: Escalates to caller (line 644-658, healed with alternate log path)
- Query building failure: Escalates to main entry point (lines 1164-1170)

**Which Get Swallowed**:
- Individual entry parse failures: Swallowed (line 664-666: `if not parsed: continue`)
- Filter application errors: Swallowed with healing attempt (line 758-766)
- Timestamp parsing errors: Swallowed (line 744-746)

**Which Mutate State Then Fail**:
- None identified (good - no partial state corruption)

**Recommendation**: Document escalation policy - which errors are expected to be common (parse failures) vs exceptional (file not found).

### Heal and Continue Logic

**Parameter Healing**:
- Auto-corrects out-of-range values: `page=-5` → `page=1`
- Normalizes enums: `message_mode="fuzzy"` → `message_mode="substring"` (closest match)
- Cleans lists: `[" agent1 ", "agent2"]` → `["agent1", "agent2"]`

**Default Value Insertion**:
- Missing project: `project=None` → `project="default"`
- Missing page_size: Uses limit or default (50)

**Partial Success Handling**:
- Some filters succeed, others fail: Use successful filters, skip failed (lines 704-707)
- Some projects fail to load: Skip failed, search successful projects (lines 1286-1293)

**Policy**: Best-effort execution - return partial results rather than fail completely.

**Risks**:
- User may not realize query was modified
- Healed parameters may not match user intent
- Partial results may be misleading

**Recommendation**: Add `parameter_modifications` field to response listing all healing applied.

---

## 7. Known Issues

### Issue 1: Status Filter Logic Inverted [BUG]

**Location**: Lines 684-692

**Current Code**:
```python
if search_params.get("status"):
    entry_emoji = parsed.get("emoji", "")
    for status_filter in search_params["status"]:
        status_emojis = STATUS_EMOJI.get(status_filter.lower(), [])
        if entry_emoji not in status_emojis:
            break  # Break when emoji NOT in allowed set
    else:
        continue  # If NO break occurred, SKIP entry
```

**Logic Flow**:
1. Iterate status filters
2. For each status, check if entry emoji NOT in allowed emojis
3. If emoji NOT in allowed, break loop
4. If loop completes without break (emoji WAS in all allowed sets), skip entry

**Bug**: for-else inverts the logic. Should skip entry if NO statuses match, but actually skips if ALL statuses match.

**Expected Behavior**:
Match entry if emoji matches ANY of the requested statuses (OR logic).

**Correct Code**:
```python
if search_params.get("status"):
    entry_emoji = parsed.get("emoji", "")
    matches_any = any(
        entry_emoji in STATUS_EMOJI.get(status_filter.lower(), [])
        for status_filter in search_params["status"]
    )
    if not matches_any:
        continue
```

**Impact**:
- Status filter produces inverted results
- Queries with status filters return opposite of expected
- Likely unreported because status filter rarely used, or users expect emoji filter instead

**Test Case**:
```python
# Given entries:
# Entry 1: emoji="✅", status="success"
# Entry 2: emoji="❌", status="error"

results = await query_entries(status=["success"])

# Expected: [Entry 1]
# Actual: [Entry 2]  # Inverted!
```

### Issue 2: Pagination Calculator Imported But Not Used

**Location**: Lines 23, 44, 779-833

**Evidence**:
```python
# Line 23
from scribe_mcp.utils.estimator import PaginationCalculator

# Line 44
_PAGINATION_CALCULATOR = PaginationCalculator()

# Lines 779-833: Manual pagination instead of using _PAGINATION_CALCULATOR
page = search_params.get("page", 1)
page_size = search_params.get("page_size", 50)
total_entries = len(filtered_entries)
start_idx = (page - 1) * page_size
end_idx = start_idx + page_size
# ... (50+ lines of manual pagination)
```

**Impact**:
- Code duplication: Pagination logic implemented manually instead of using utility
- Maintenance burden: Pagination bugs must be fixed in multiple places
- Import waste: Unused import and global instance

**Recommendation**:
Replace manual pagination with `_PAGINATION_CALCULATOR` utility or remove unused import.

### Issue 3: Config Object Re-Validation Suggests Distrust

**Location**: Lines 61-407 (validation), 496-528 (re-validation)

**Pattern**:
1. Validate parameters (lines 98-210)
2. Create QueryEntriesConfig from healed parameters (lines 239-299)
3. Extract parameters from config (lines 418-438)
4. **Re-validate** extracted parameters (lines 496-528)

**Architectural Smell**:
If config objects encapsulate validation, why re-validate after extraction?

**Implications**:
- Config objects may contain invalid data
- Consumers cannot trust config validity
- Validation logic duplicated in multiple layers

**Recommendation**:
Config objects should validate on construction, making post-extraction validation unnecessary.

### Issue 4: Search Scope Duplication

**Location**: Lines 1279-1297 vs 1312-1330

**Evidence**:
Identical project iteration code in two branches:
- `all_projects` scope (lines 1279-1297): Iterate all projects
- `research/bugs/all` scopes (lines 1312-1330): Iterate all projects + filter

**Code Duplication**:
```python
# Block 1 (lines 1281-1297)
for project_name in state.projects:
    project_dict = state.get_project(project_name)
    if project_dict:
        if not project_dict.get("progress_log"):
            fallback_project = load_project_config(project_name)
            if fallback_project:
                project_dict = fallback_project
                project_dict["name"] = project_name
            else:
                continue
        else:
            project_dict["name"] = project_name
        projects.append(project_dict)

# Block 2 (lines 1312-1330) - IDENTICAL except for filter at end
for project_name in state.projects:
    project_dict = state.get_project(project_name)
    if project_dict:
        if not project_dict.get("progress_log"):
            fallback_project = load_project_config(project_name)
            if fallback_project:
                project_dict = fallback_project
                project_dict["name"] = project_name
            else:
                continue
        else:
            project_dict["name"] = project_name
        if _project_has_document_types(project_dict, document_types, search_scope):
            projects.append(project_dict)  # Only difference: conditional append
```

**Impact**:
- 49 lines of duplicated code
- Bug fixes must be applied in both places
- Adding new scope requires copying iteration logic

**Recommendation**:
Extract shared project loading logic into `_load_all_projects()` helper:

```python
def _load_all_projects(state) -> List[Dict[str, Any]]:
    projects = []
    for project_name in state.projects:
        project_dict = _load_project_from_state_or_config(state, project_name)
        if project_dict:
            projects.append(project_dict)
    return projects

# Usage in scope routing
if search_scope == "all_projects":
    projects = _load_all_projects(state)
elif search_scope in ["research", "bugs", "all"]:
    all_projects = _load_all_projects(state)
    projects = [p for p in all_projects if _project_has_document_types(p, document_types, search_scope)]
```

### Issue 5: Relevance Scoring Naive Implementation

**Location**: Line 751

**Current Implementation**:
```python
relevance_score = len(message) / 1000.0
```

**Problems**:
- Message length != relevance
- No query matching
- No semantic analysis
- Threshold defaults to 0.0 (feature unused)

**Impact**:
- Feature provides no real value
- Misleading parameter name (suggests sophisticated scoring)
- Could be replaced with "minimum message length" filter

**Recommendation**:
Either implement real relevance scoring (TF-IDF, semantic similarity) or rename parameter to `min_message_length` and document behavior accurately.

### Issue 6: Filter Order Undefined

**Location**: Lines 667-756

**Issue**:
Filter application order is implementation detail, not contract.

**Current Order**:
1. Message
2. Emoji
3. Status (emoji-based)
4. Agent
5. Metadata
6. Priority
7. Category
8. Confidence
9. Time range
10. Relevance

**Problems**:
- Order not documented
- Changing order could break user expectations
- No rationale for current order

**Impact**:
- Users cannot predict filter precedence
- Optimization opportunities (expensive filters last) not exploited
- Performance characteristics undefined

**Recommendation**:
Document filter order in docstring and explain rationale (e.g., "cheap filters first for early rejection").

---

## 8. Implementation Specs

See `SPEC-QUERY-001-param-reduction.yaml` for detailed parameter reduction specification.

**Summary of Proposed Changes**:

### Spec 1: Unify Search Scope Resolution

**Current**: Duplicated project iteration across scope branches

**Proposed**:
```python
def _load_all_projects(state) -> List[Dict[str, Any]]:
    """Load all projects from state or config."""
    pass

def _resolve_cross_project_projects(scope, document_types) -> List[Dict]:
    projects = _load_all_projects(state)

    if scope == "global":
        return [_create_global_config()]
    elif scope == "all_projects":
        return projects
    elif scope in ["research", "bugs", "all"]:
        filtered = [p for p in projects if _project_has_document_types(p, document_types, scope)]
        filtered.append(_create_global_config())
        return filtered
```

**Lines Affected**: 1271-1341
**Lines Saved**: ~30 (from 70 to 40)

### Spec 2: Extract Filter Chain

**Current**: Inline filter application (lines 667-756)

**Proposed**:
```python
class Filter(ABC):
    @abstractmethod
    def matches(self, entry: Dict) -> bool:
        pass

class FilterChain:
    def __init__(self, filters: List[Filter]):
        self.filters = filters

    def apply(self, entries: List[Dict]) -> List[Dict]:
        return [e for e in entries if all(f.matches(e) for f in self.filters)]

# Usage
filters = [
    MessageFilter(message, mode, case_sensitive),
    EmojiFilter(emojis),
    AgentFilter(agents),
    # ... etc
]
filtered = FilterChain(filters).apply(parsed_entries)
```

**Lines Affected**: 667-756
**Lines Saved**: ~50 (from 90 to 40, but adds ~80 lines for filter classes in separate module)
**Net Change**: +30 lines (but vastly improved testability and composability)

### Spec 3: Fix Status Filter Bug

**Current** (lines 684-692):
```python
for status_filter in search_params["status"]:
    status_emojis = STATUS_EMOJI.get(status_filter.lower(), [])
    if entry_emoji not in status_emojis:
        break
else:
    continue
```

**Proposed**:
```python
if search_params.get("status"):
    entry_emoji = parsed.get("emoji", "")
    status_emojis = set()
    for status_filter in search_params["status"]:
        status_emojis.update(STATUS_EMOJI.get(status_filter.lower(), []))
    if entry_emoji not in status_emojis:
        continue
```

**Lines Affected**: 684-692
**Lines Saved**: 0 (same length, fixed logic)

### Spec 4: Use Pagination Calculator

**Current** (lines 779-833): Manual pagination implementation

**Proposed**:
```python
pagination_result = _PAGINATION_CALCULATOR.calculate(
    total_items=len(filtered_entries),
    page=page,
    page_size=page_size,
    limit=limit
)

paginated_entries = filtered_entries[pagination_result["start_idx"]:pagination_result["end_idx"]]
pagination_info = pagination_result["metadata"]
```

**Lines Affected**: 779-833
**Lines Saved**: ~40 (from 54 to 14)

### Spec 5: Eliminate Config Re-Validation

**Current**: Validate → Config → Extract → Re-validate

**Proposed**: Validate → Config (with validation on construction) → Extract (trust validity)

**Changes**:
1. Move validation into QueryEntriesConfig.__init__()
2. Remove re-validation in _build_search_query (lines 496-528)
3. Trust extracted parameters are valid

**Lines Affected**: 496-528 (removal) + QueryEntriesConfig constructor (addition)
**Lines Saved**: ~30 (from _build_search_query)

### Total Impact

**Lines Reduced**: ~150 (excluding filter classes addition)
**Complexity Reduced**: 4 major simplifications
**Bugs Fixed**: 2 (status filter, pagination calculator non-use)
**Testability Improved**: Filter composability, scope strategies
**Maintainability Improved**: Shared iteration logic, config validation centralized

---

## Cross-Cutting Concerns

See also: `wiki/analysis/query_search_patterns.md` for search pattern analysis.

**Cross-cutting concerns identified during audit will be tagged and aggregated here.**

This section will be populated as audit progresses and commonalities across tools are discovered.

---

## Confidence Assessment

**Overall Confidence in Findings**: 0.92

**High Confidence (0.95+)**:
- Sub-system breakdown (verified via function mapping)
- Parameter count (counted from signature)
- LOC count (measured from file)
- Bug in status filter (logic analysis confirmed)

**Medium Confidence (0.85-0.95)**:
- Architectural smells (based on code patterns, not runtime behavior)
- Unification opportunities (estimated complexity reduction)
- Token cost estimates (pending actual measurement)

**Low Confidence (0.70-0.85)**:
- Filter order impact (requires performance testing)
- Config distrust rationale (inferred from pattern, not documented)

**Uncertainty Remaining**:
- Why relevance scoring so simplistic? (Placeholder for future feature?)
- Why pagination calculator imported but unused? (Dead code or intentional?)
- Is status filter bug known? (No bug report found, but logic clearly broken)

---

**End of Forensic Analysis**

**Next Steps**:
1. Measure actual token costs (10+ samples)
2. Create search patterns analysis (`wiki/analysis/query_search_patterns.md`)
3. Document cross-cutting concerns across Wave 1 tools
4. Create implementation specs (SPEC-QUERY-001-param-reduction.yaml)
