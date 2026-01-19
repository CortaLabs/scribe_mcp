# list_projects.py - Forensic Audit

**File**: `tools/list_projects.py`
**LOC**: 533
**Size**: 20,297 bytes
**Complexity**: Medium-High
**Paired With**: get_project.py (885 LOC combined)
**Audit Agent**: ResearchAgent-G-ListGetProjects
**Audit Date**: 2026-01-05

---

## 1. Overview

`list_projects.py` is a multi-project enumeration and discovery tool that serves as the primary project browsing interface for Scribe MCP. It provides three distinct output modes based on result count: empty state, detailed single-project view, and paginated table view.

**Purpose**: Enumerate, filter, and present projects from multiple data sources (state.json, SQLite, ProjectRegistry) with intelligent formatting based on result count.

**Key Complexity Drivers**:
- **Data Source Unification**: Merges projects from 3 sources (StorageBackend, state manager, active project cache)
- **3-Way Routing**: Different formatters for 0/1/multiple matches (lines 372-468)
- **TOKEN-001 Bloat**: 1000+ token outputs for multi-project tables (pre-identified issue)
- **DUPLICATION-002**: Doc gathering logic repeated from set_project/get_project (lines 50-128)
- **20+ Parameter Signature**: Complex filter/pagination/format routing (lines 131-144)

**Relationships**:
- **Data Dependencies**: ProjectRegistry, ContextManager, default_formatter
- **Paired Tool**: get_project.py (shared doc gathering logic, similar hash retrieval needs)
- **Unification Candidate**: Could merge with get_project under unified query contract

---

## 2. Sub-System Breakdown

### 2.1 Doc Inventory Gathering [DUPLICATION-002] (Lines 50-128)
**Responsibility**: Scan dev_plan directory for architecture/phase/checklist/progress docs and custom content

**Function**: `_gather_doc_info(project: Dict[str, Any]) -> Dict[str, Any]`

**Returns Structure**:
```python
{
    "architecture": {"exists": True, "lines": 1274, "modified": False},
    "phase_plan": {"exists": True, "lines": 542, "modified": False},
    "checklist": {"exists": True, "lines": 356, "modified": False},
    "progress": {"exists": True, "entries": 298},
    "custom": {
        "research_files": 3,
        "bugs_present": False,
        "jsonl_files": ["TOOL_LOG.jsonl"]
    }
}
```

**CRITICAL DUPLICATION EVIDENCE**:
- Lines 84-106: Identical architecture/phase/checklist checking pattern as `set_project.py:91-113` and `get_project.py:146-165`
- Lines 109-122: Progress log entry counting (same pattern as `set_project.py:36-58` and `get_project.py:43-52`)
- Lines 125: Custom content detection delegates to `default_formatter._detect_custom_content()` (shared with set_project)

**Contract**:
- **Input**: Project dict with `progress_log` path
- **Output**: Doc info dict with existence/line counts/custom content
- **Failure**: Returns `{}` if progress_log missing or invalid (line 76)
- **State**: Read-only, no mutations

**Extractable**: [BUCKET:metadata] `DocInventoryGatherer`
- 90-100 LOC duplicated across 3 tools
- Clear contract: path → doc status dict
- Before/After: See Section 3

### 2.2 Multi-Source Project Collection (Lines 183-251)
**Responsibility**: Merge projects from StorageBackend, state.json, and active project cache into unified `projects_map`

**Data Source Priority**:
1. **StorageBackend** (lines 187-194): Primary source, populates name/root/progress_log
2. **State.json** (lines 196-211): Overlays docs/defaults/description/tags
3. **Active Project** (lines 213-223): Ensures current selection is always included

**Merge Strategy**: Dictionary update pattern with `setdefault()` preserves state.json data over backend data

**State Ownership**: Temporary `projects_map` dict, no persistent mutations

**Contract**:
- **Input**: None (reads from global state)
- **Output**: Dict[name → project_data] with merged fields
- **Failure**: Silent (empty dict if all sources fail)
- **State**: Creates transient data structure, no persistence

### 2.3 ProjectRegistry Enrichment (Lines 226-250)
**Responsibility**: Overlay lifecycle metadata (status, timestamps, entry counts) from ProjectRegistry onto merged projects

**Enrichment Fields** (lines 236-248):
- `description`, `status` - Lifecycle state
- `created_at`, `last_entry_at`, `last_access_at` - Temporal tracking
- `last_status_change` - Lifecycle transitions
- `total_entries`, `total_files`, `total_phases` - Volume metrics
- `meta`, `tags` - Flexible metadata

**Error Handling** (lines 228-232):
```python
try:
    info = _PROJECT_REGISTRY.get_project(name)
except Exception:
    info = None
if not info:
    continue  # Skip enrichment for this project
```

**Policy**: Best-effort enrichment, failures don't block listing

**Contract**:
- **Input**: Merged projects map
- **Output**: Same map with added registry fields
- **Failure**: Silent skip (projects without registry data shown with partial info)
- **State**: Read-only registry queries

### 2.4 Multi-Axis Filtering (Lines 252-289)
**Responsibility**: Apply name/status/tag filters to projects list

**Filter Types**:
1. **Name Filter** (lines 254-259): Case-insensitive substring match
2. **Status Filter** (lines 261-271): Exact match against lifecycle states
3. **Tag Filter** (lines 273-289): Set intersection (match any tag)

**Implicit Behavior**:
- Line 265: Defaults to "planning" status if project.status is None
- Line 288: Tag matching uses set intersection (inclusive OR logic)

**Contract**:
- **Input**: projects_list + filter criteria
- **Output**: Filtered list (may be empty)
- **Failure**: Never fails (invalid filters → no matches)
- **State**: Pure function, no mutations

### 2.5 Sorting & Ordering (Lines 291-327)
**Responsibility**: Sort projects by name (default) or registry timestamp fields

**Sort Modes** (lines 313-321):
- `created_at`, `last_entry_at`, `last_access_at` - Parse ISO timestamps with timezone handling
- `total_entries` - Numeric sort
- Fallback: name-based alpha sort

**Timestamp Parsing** (lines 296-311):
- Primary: `datetime.fromisoformat()` with timezone normalization
- Fallback: SQLite legacy format (`"%Y-%m-%d %H:%M:%S"`)
- Error handling: `datetime.min` for unparseable timestamps

**Contract**:
- **Input**: Filtered projects list + order_by/direction params
- **Output**: Sorted list (stable ordering)
- **Failure**: Falls back to name sort if order_by field unsupported
- **State**: Pure sort, no mutations

### 2.6 Context-Aware Pagination (Lines 329-352)
**Responsibility**: Apply intelligent pagination with temp project filtering via ContextManager

**ContextManager Integration**:
- Lines 330: `ContextManager()` instance for temp project detection
- Lines 343: `effective_page_size` resolution (page_size → limit → default)
- Lines 345-352: `prepare_response()` applies temp filtering + pagination

**Pagination Logic**:
- `include_test` parameter controls temp project visibility (line 348)
- Returns `items`, `pagination`, `total_available`, `filtered` flags

**Contract**:
- **Input**: Sorted projects list + page/page_size/include_test
- **Output**: Dict with paginated items + metadata
- **Failure**: Never fails (returns empty items list for out-of-range pages)
- **State**: Read-only (ContextManager maintains internal temp project registry)

### 2.7 Three-Way Readable Routing [TOKEN-001 SOURCE] (Lines 372-468)
**Responsibility**: Route to different formatters based on result count: 0 → empty state, 1 → detail view, multiple → table view

**Route 1: Empty State** (lines 378-397)
- Trigger: `filtered_count == 0`
- Formatter: `default_formatter.format_no_projects_found(filter_info)`
- Token Cost: ~150-200 tokens (helpful suggestions)
- Output: "No projects found" with filter hints

**Route 2: Single Project Detail** (lines 399-426)
- Trigger: `filtered_count == 1`
- Formatter: `default_formatter.format_project_detail(project, registry_info, docs_info)`
- Token Cost: ~600-800 tokens (full inventory + activity)
- **Calls `_gather_doc_info()`** - DUPLICATION-002 trigger
- Enriches with ProjectRegistry data (lines 406-410)

**Route 3: Multiple Projects Table** (lines 428-468)
- Trigger: `filtered_count > 1`
- Formatter: `default_formatter.format_projects_table(projects, current_name, pagination, filter_info)`
- **TOKEN-001 ROOT CAUSE**: 1000+ tokens for 10-project table (see Section 5)
- Includes pagination controls + filter hints

**Format Finalization** (lines 397, 426, 468):
- All routes call `default_formatter.finalize_tool_response(format="readable")`
- Adds reminders, ANSI color processing, structural boxes

**Contract**:
- **Input**: Filtered/paginated projects + format="readable"
- **Output**: Human-readable string (150-1200 tokens depending on route)
- **Failure**: Never fails (default to empty state on errors)
- **State**: Read-only (formatters are pure functions)

### 2.8 Structured/Compact Mode (Lines 470-535)
**Responsibility**: Return JSON responses with token guards and context safety metadata

**Token Guard** (lines 471-473):
- Estimates tokens via `context_manager.token_guard.check_limits()`
- Returns warning/critical flags if thresholds exceeded

**Response Structure** (lines 483-497):
- Core: `projects`, `count`, `pagination`, `total_available`, `filtered`
- Context: `recent_projects`, `active_project`, `context_safety`
- Warnings: `token_warning`, `token_critical` (lines 499-512)

**Field Compaction** (lines 356-363):
- `COMPACT_FIELD_MAP` reduces field names (e.g., `name` → `n`, `total_entries` → `te`)
- Applied when `compact=True` parameter set

**Contract**:
- **Input**: Formatted projects + format="structured|compact"
- **Output**: JSON dict with metadata
- **Failure**: Token warnings added, never blocks response
- **State**: Records token usage via `token_estimator` (lines 518-533)

---

## 3. Modularization Notes

### [BUCKET:metadata] DocInventoryGatherer (CRITICAL UNIFICATION)
**Origin**: `list_projects.py:50-128` + `set_project.py:61-127` + `get_project.py:130-179`
**LOC Impact**: ~90-100 LOC duplicated 3x = 270-300 LOC total waste

**Responsibilities**:
- Check existence of ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST, PROGRESS_LOG
- Count lines in each document (via `default_formatter._get_doc_line_count()`)
- Count entries in progress log (via entry marker detection)
- Detect custom content (research files, bugs, jsonl files)
- Optionally compute doc hashes for drift detection (get_project variant only)

**Used By**: list_projects (single detail route), set_project (existing project SITREP), get_project (context formatter)

**Contract Definition**:
```python
@dataclass
class DocInventory:
    architecture: Optional[DocInfo]
    phase_plan: Optional[DocInfo]
    checklist: Optional[DocInfo]
    progress: Optional[ProgressInfo]
    custom: CustomContent

@dataclass
class DocInfo:
    exists: bool
    lines: int
    modified: bool  # Only populated if hash tracking enabled
    hash: Optional[str]  # Only if compute_hashes=True

class DocInventoryGatherer:
    def gather(
        self,
        dev_plan_dir: Path,
        compute_hashes: bool = False
    ) -> DocInventory:
        """Gather document inventory for a project.

        Args:
            dev_plan_dir: Path to .scribe/docs/dev_plans/<project>
            compute_hashes: If True, compute SHA256 for each doc

        Returns:
            DocInventory with all document status

        Failure Policy:
            - Missing directory → return empty inventory
            - Individual doc missing → None for that field
            - Line counting errors → lines=0
        """
```

**Why Extract**:
- 3x duplication creates maintenance burden (bug fixes must be replicated)
- Inconsistent implementations (set_project uses regex, get_project uses parse_log_line)
- Hash tracking only in get_project variant (should be universal capability)
- All tools need identical "project state" definition

**Risks if Extracted**:
- Custom content detection varies by tool (set_project includes different metadata)
- Hash tracking is optional feature (not all callers need it)
- Mitigation: Use feature flags (`compute_hashes`, `include_custom_metadata`)

**Before/After**:
- **Before**: 3 tools independently decide what "project inventory" means, leading to inconsistencies
- **After**: Single `DocInventoryGatherer` defines canonical project state, tools adapt results to presentation needs
- **Conceptual Win**: "Get project doc status" becomes a named, testable operation with consistent semantics

---

### [BUCKET:formatting] Three-Way Routing Formatter (OPTIONAL EXTRACTION)
**Origin**: `list_projects.py:372-468` (3-way readable routing logic)

**Responsibilities**:
- Determine route based on result count (0/1/multiple)
- Call appropriate formatter (format_no_projects_found, format_project_detail, format_projects_table)
- Apply format finalization (reminders, ANSI colors)

**Why Extract**:
- Pattern is reusable for other query tools (e.g., query_entries could benefit)
- Reduces tool complexity (routing logic separate from query logic)
- Single place to optimize TOKEN-001 (formatter selection policy)

**Risks if Extracted**:
- Routing logic is tightly coupled to list_projects semantics (what counts as "empty"?)
- Different tools may need different thresholds (1 vs 5 vs 10 results)
- Extraction may not reduce complexity materially

**Decision**: **KEEP COUPLED** - Routing logic is tool-specific presentation concern, not shared infrastructure

---

### [BUCKET:persistence] Multi-Source Project Merger (POTENTIAL EXTRACTION)
**Origin**: `list_projects.py:183-251` (data source unification logic)

**Responsibilities**:
- Query StorageBackend for project records
- Overlay state.json data for docs/defaults
- Ensure active project is included
- Enrich with ProjectRegistry metadata

**Why Extract**:
- Pattern appears in get_project (lines 226-244) and potentially other query tools
- Unification logic is complex (priority rules, setdefault pattern)
- Single source of truth for "how to merge project data"

**Risks if Extracted**:
- Merge priority rules may differ by tool (list_projects prefers state.json, others may prefer registry)
- Active project inclusion is list_projects-specific behavior
- Extraction may create coupling to global state

**Decision**: **DEFER** - Needs comparison with get_project's merge logic before extraction

---

## 4. Implicit Contracts

### 4.1 Data Source Priority
**Locations**: Lines 187-211
**Contract**: state.json overrides StorageBackend data when both present
**Not Enforced**: No validation that state.json data is fresher/more authoritative
**Assumption**: State manager is source of truth for docs/defaults
**Failure Mode**: If state.json is stale, users see outdated metadata
**Policy Decision**: Acceptable (state manager is authoritative by design)

### 4.2 Best-Effort Registry Enrichment
**Location**: Lines 228-232
**Contract**: ProjectRegistry failures don't block project listing
**Not Enforced**: No logging/tracking of enrichment failures
**Assumption**: Registry is optional enhancement, not required
**Failure Mode**: Projects without registry data show with partial info (no status, entry counts)
**Policy Decision**: Acceptable (silent fallback is intentional)

### 4.3 Temp Project Auto-Filtering
**Location**: Lines 345-352 (ContextManager.prepare_response)
**Contract**: Projects matching temp/test patterns excluded by default unless `include_test=True`
**Not Enforced**: Temp detection logic is opaque (buried in ContextManager)
**Assumption**: ContextManager correctly identifies temp projects
**Failure Mode**: Real projects with "test" in name hidden from users
**Testing Gap**: No explicit test that include_test=False filters correctly

### 4.4 Timestamp Parsing Fallbacks
**Location**: Lines 296-311
**Contract**: Unparseable timestamps default to datetime.min (pushed to sort end)
**Not Enforced**: No warning when timestamp parsing fails
**Assumption**: datetime.min is acceptable sentinel value
**Failure Mode**: Projects with bad timestamps always sorted to end (may hide recent activity)
**Policy Decision**: Acceptable (silent fallback prevents crashes)

---

## 5. Token Analysis

### TOKEN-001: Multi-Project Table Bloat (CRITICAL)

**Status**: Confirmed 1000+ tokens for 10-project table (target: <400 tokens, 60% reduction required)

**Sample Breakdown** (10 projects, page 1 of 2):

```
📋 PROJECTS - 20 total (Page 1 of 2, showing 10)
╔══════════════════════════════════════════════════════════╗
║ 📋 PROJECTS - 20 total (Page 1 of 2, showing 10)        ║
╚══════════════════════════════════════════════════════════╝

NAME                          STATUS        ENTRIES  LAST ACTIVITY
──────────────────────────────────────────────────────────────────
⭐ scribe_tool_output_refin   in_progress      145  2 hours ago
   token_optimization         complete          89  5 days ago
   scribe_security_audit      archived          67  12 days ago
   [... 7 more rows ...]

📄 Page 1 of 2 | Use page=2 to see more
🔍 Filters: none | Order: last_entry_at (desc)
```

**Token Categorization**:

| Category | Token Estimate | Evidence | Removable? |
|----------|----------------|----------|------------|
| **Structural** | 350-400 | Box drawing (╔═╗), header, column headers, separator lines | Partially (compact mode can skip boxes) |
| **Metadata** | 200-250 | Project names (30 chars each × 10 = 300 chars), status (12 chars × 10), entries (8 chars × 10), timestamps (15 chars × 10) | No (essential data) |
| **Duplication** | 150-200 | Header text repeated in box, pagination shown twice (page info + "Use page=N"), filter hints | Yes (consolidate header, single pagination line) |
| **Safety Padding** | 150-200 | "Use page=2 to see more" instruction, filter hints, emoji markers | Partially (move to docs, use symbols only) |

**TOTAL**: ~850-1050 tokens (matches 1000+ token observation)

**Optimization Targets**:
1. **Remove box drawing in compact mode**: -100 tokens (use simple header line)
2. **Consolidate pagination**: -50 tokens (single line: "Page 1/2 | Filters: none")
3. **Abbreviate column headers**: -30 tokens (NAME → N, ENTRIES → ENT)
4. **Remove instructional text**: -70 tokens (eliminate "Use page=X" hints)
5. **Symbolic status indicators**: -50 tokens (in_progress → ⏩, complete → ✅)

**AFTER OPTIMIZATION**: ~500-600 tokens (40-50% reduction, close to <400 target)

**Remaining Gap**: Additional 100-200 token reduction requires:
- Further abbreviation of project names (truncate at 20 chars instead of 27)
- Remove relative time formatting (show ISO dates only)
- Skip empty state messaging entirely (return raw table only)

**Risk**: Over-optimization sacrifices usability (context hints help users)

---

### Readable Mode Token Profiles

**Route 1: Empty State**
```
No projects found matching your criteria.

🔍 Filters applied:
   name: "production"
   status: ["in_progress"]

💡 Try:
   - Remove name filter
   - Expand status to include "planning"
   - Use list_projects() with no filters
```

**Token Estimate**: 150-200 tokens
**Breakdown**:
- Structural (header, bullets): 50 tokens
- Metadata (filter values): 40 tokens
- Safety padding (suggestions): 60-110 tokens

**Optimization**: Keep as-is (empty state should be helpful)

---

**Route 2: Single Project Detail**
```
╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT: scribe_systematic_audit_1                    ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/scribe_systematic_audit_1/

📊 Documentation Inventory:
  ✓ ARCHITECTURE_GUIDE.md (768 lines)
  ✓ PHASE_PLAN.md (922 lines)
  ✓ CHECKLIST.md (322 lines)
  ✓ PROGRESS_LOG.md (45 entries)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 45
  Last Entry: 2 hours ago
  Created: 3 days ago

📁 Custom Content:
  Research Files: 5
  Bug Reports: 2
  TOOL_LOG.jsonl (3847 lines)
```

**Token Estimate**: 600-800 tokens
**Breakdown**:
- Structural (boxes, headers, bullets): 200 tokens
- Metadata (paths, doc counts, timestamps): 250 tokens
- Duplication (location shown twice): 0 (no duplication)
- Safety padding (section labels, emoji): 150-350 tokens

**Optimization Opportunity**:
- Compact mode: Remove box drawing (-80 tokens)
- Abbreviate section headers (-30 tokens)
- Remove emoji (-20 tokens)
- **AFTER**: 470-670 tokens (21-16% reduction)

---

## 6. Error Handling Architecture

### 6.1 Silent Failures (Policy Decisions)

**ProjectRegistry Enrichment** (Lines 228-232):
```python
try:
    info = _PROJECT_REGISTRY.get_project(name)
except Exception:
    info = None
if not info:
    continue  # Skip enrichment silently
```
- **Policy**: Registry failures don't block listing
- **Rationale**: Projects list should always succeed (registry is enhancement)
- **State Mutation**: None (enrichment is additive)
- **Acceptable**: YES - documented best-effort behavior

**Doc Inventory Gathering** (Line 76):
```python
if not progress_log or not Path(progress_log).exists():
    return {}  # Empty inventory, no error
```
- **Policy**: Missing progress log → empty doc info
- **Rationale**: Project may exist without docs (new/corrupted state)
- **State Mutation**: None
- **Acceptable**: YES - caller interprets empty dict as "no docs found"

**Entry Counting** (Lines 121-122):
```python
except:
    result["progress"] = {"exists": True, "entries": 0}
```
- **Policy**: File read errors default to 0 entries
- **Rationale**: Progress log exists but is unreadable (corruption, permissions)
- **State Mutation**: None
- **Acceptable**: QUESTIONABLE - silent 0 may mislead users (should log warning)

### 6.2 Escalation Patterns

**Parameter Validation** (No explicit validation):
- Tools rely on MCP framework + Python type hints
- No validation that `limit` is positive, `page` is >= 1
- **Result**: Invalid params may cause unexpected behavior (e.g., page=0 → empty results)

**Filter Validation** (No validation):
- Name/status/tag filters accept any values
- Invalid status values → no matches (silent failure)
- **Result**: User confusion when typos cause empty results

**Timestamp Parsing Failures** (Lines 307-311):
```python
except Exception:
    return datetime.min.replace(tzinfo=timezone.utc)
```
- Falls back to datetime.min for unparseable timestamps
- **Result**: Projects with bad timestamps sorted to end (may hide recent activity)

### 6.3 Data Integrity Assumptions

**Multi-Source Merge** (Lines 196-211):
- Assumes state.json and backend data have compatible schemas
- No validation that merged data is consistent
- **Risk**: Partial updates could create frankenstein records

**Pagination Boundaries** (Lines 345-352):
- ContextManager handles out-of-range pages
- Assumes pagination math is correct (total_pages calculation)
- **Risk**: Off-by-one errors could cause missing/duplicate projects

---

## 7. Known Issues

### TOKEN-001: Multi-Project Table Bloat
**Severity**: High
**Status**: Confirmed (Wave 2 pre-identified)
**Impact**: 1000+ tokens for 10-project table (target: <400 tokens, 60% reduction required)

**Root Cause**: Structural verbosity in `default_formatter.format_projects_table()`
- Box drawing: 100-150 tokens
- Repeated pagination info: 50-80 tokens
- Instructional hints: 70-100 tokens
- Long column headers: 30-50 tokens

**Reproduction**:
```python
projects = await list_projects(limit=10, format="readable")
# Returns 1000+ token table with boxes, headers, pagination
```

**Fix Strategy**: See SPEC-LIST-001 in Section 8

---

### DUPLICATION-002: Doc Gathering Logic Repeated
**Severity**: Medium
**Status**: Confirmed (Wave 2 pre-identified)
**Impact**: 90-100 LOC duplicated across list_projects, set_project, get_project

**Root Cause**: No shared `DocInventoryGatherer` utility
- Each tool implements doc scanning independently
- Inconsistent entry counting (regex vs parse_log_line)
- Hash tracking only in get_project variant

**Reproduction**: Compare lines 50-128 (list_projects) vs set_project.py:61-127 vs get_project.py:130-179

**Fix Strategy**: Extract [BUCKET:metadata] DocInventoryGatherer (see Section 3)

---

### BUG-LIST-001: Pagination Calculation Potential Off-By-One
**Severity**: Low
**Status**: Suspected (needs verification)
**Impact**: Last page may show incorrect item counts

**Location**: Lines 431-437 (total_pages calculation)
```python
total_pages = (pagination_info["total_count"] + pagination_info["page_size"] - 1) // pagination_info["page_size"]
```

**Issue**: Standard ceiling division formula, but relies on ContextManager pagination being correct

**Reproduction**: Unknown (needs test with total_count that doesn't divide evenly by page_size)

**Fix Strategy**: Add explicit pagination tests with edge cases (e.g., 11 items / 5 per page = 3 pages)

---

## 8. Implementation Specs

### SPEC-LIST-001: Token Optimization for format_projects_table

**File**: `utils/response.py`
**Target Method**: `DefaultFormatter.format_projects_table()` (lines 1122-1223+)
**Priority**: P1 (TOKEN-001 fix)

**Changes Required**:
1. Add `compact_structural` parameter (default False)
2. When True:
   - Skip box drawing (lines 1161-1163)
   - Use single-line header: `"📋 PROJECTS - {total_count} (page {page}/{total_pages})"`
   - Remove duplicate pagination info (line 1206-1209)
   - Abbreviate column headers: NAME → N, STATUS → S, ENTRIES → ENT, LAST ACTIVITY → LAST
3. Add `symbolic_status` parameter (default False)
4. When True:
   - Map status to emoji: `{"in_progress": "⏩", "complete": "✅", "planning": "📋", "blocked": "🚫", "archived": "📦"}`
   - Reduce status column to 3 chars (emoji only)

**Expected Impact**: 40-50% token reduction (1000 → 500-600 tokens)

**Test Coverage**:
```python
# Standard mode (baseline)
result = format_projects_table(projects, None, pagination, filters)
assert token_count(result) >= 900  # Current behavior

# Compact mode
result = format_projects_table(
    projects, None, pagination, filters,
    compact_structural=True, symbolic_status=True
)
assert token_count(result) <= 600  # Target after optimization
```

---

### SPEC-LIST-002: DocInventoryGatherer Extraction

**Target**: New file `utils/doc_inventory.py`
**Priority**: P2 (DUPLICATION-002 fix)

**Interface**:
```python
@dataclass
class DocInfo:
    exists: bool
    lines: int
    modified: bool = False
    hash: Optional[str] = None

@dataclass
class ProgressInfo:
    exists: bool
    entries: int

@dataclass
class CustomContent:
    research_files: int = 0
    bugs_present: bool = False
    jsonl_files: List[str] = field(default_factory=list)

@dataclass
class DocInventory:
    architecture: Optional[DocInfo] = None
    phase_plan: Optional[DocInfo] = None
    checklist: Optional[DocInfo] = None
    progress: Optional[ProgressInfo] = None
    custom: CustomContent = field(default_factory=CustomContent)

class DocInventoryGatherer:
    def __init__(self, compute_hashes: bool = False):
        self.compute_hashes = compute_hashes

    def gather(self, dev_plan_dir: Path) -> DocInventory:
        """Gather document inventory for a project.

        Returns:
            DocInventory with all document status

        Failure Policy:
            - Missing directory → return empty DocInventory()
            - Individual doc missing → None for that field
            - Line counting errors → lines=0
        """
```

**Migration Plan**:
1. Implement DocInventoryGatherer in utils/doc_inventory.py
2. Update list_projects.py lines 50-128 to use gatherer
3. Update set_project.py lines 61-127 to use gatherer
4. Update get_project.py lines 130-179 to use gatherer
5. Remove duplicated code after migration verified

---

### SPEC-LIST-003: Pagination Test Coverage

**File**: New test `tests/test_list_projects_pagination.py`
**Priority**: P3 (regression prevention)

**Test Cases**:
```python
async def test_pagination_edge_cases():
    # Test 1: Exact multiple (10 items, 5 per page = 2 pages)
    result = await list_projects(page=1, page_size=5)
    assert result["pagination"]["total_pages"] == 2
    assert len(result["projects"]) == 5

    # Test 2: Remainder (11 items, 5 per page = 3 pages)
    result = await list_projects(page=3, page_size=5)
    assert result["pagination"]["total_pages"] == 3
    assert len(result["projects"]) == 1  # Last page has 1 item

    # Test 3: Out of range (page=10 when only 2 pages exist)
    result = await list_projects(page=10, page_size=5)
    assert len(result["projects"]) == 0
    assert result["pagination"]["page"] == 10  # Returns requested page number
```

---

## Notes for Phase 6

**Critical Insights**:
1. TOKEN-001 fix MUST preserve usability (don't remove essential context)
2. DocInventoryGatherer extraction enables consistent hash tracking across tools
3. Three-way routing is list_projects-specific, don't over-generalize
4. Multi-source merge logic may need unification with get_project (investigate first)

**Recommended Extraction Order**:
1. DocInventoryGatherer (SPEC-LIST-002) - unblocks BUG-001 fix in set_project
2. Token optimization (SPEC-LIST-001) - addresses high-priority TOKEN-001
3. Pagination tests (SPEC-LIST-003) - regression prevention

**Defer Decisions**:
- Multi-source merger extraction (needs get_project comparison first)
- Three-way routing extraction (tool-specific, may not be reusable)
