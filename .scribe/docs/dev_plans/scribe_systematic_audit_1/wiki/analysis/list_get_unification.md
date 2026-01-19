# list_projects vs get_project - Unification Analysis

**Analysis Type**: Contract Comparison & Unification Opportunity Assessment
**Tools**: list_projects.py (533 LOC) + get_project.py (352 LOC) = 885 LOC combined
**Analyst**: ResearchAgent-G-ListGetProjects
**Date**: 2026-01-05

---

## Executive Summary

**Question**: Should list_projects and get_project be unified under a single query contract?

**Answer**: **PARTIAL UNIFICATION RECOMMENDED**

- **Shared Infrastructure**: Extract DocInventoryGatherer, LogEntryParser, Multi-Source Merger
- **Keep Separate Tools**: Maintain distinct MCP tools due to different use cases and presentation needs
- **Unification Strategy**: Create shared `ProjectQueryEngine` base class that both tools extend

**Rationale**: Tools serve different purposes (enumeration vs deep-dive) but share 60-70% of data gathering logic. Extract shared infrastructure while preserving distinct interfaces.

---

## Contract Comparison

### list_projects Contract

**Purpose**: Enumerate and filter projects from multiple sources with pagination

**Inputs**:
```python
limit: Optional[int] = 5
filter: Optional[str] = None  # Name substring match
compact: bool = False
fields: Optional[List[str]] = None
include_test: bool = False
page: int = 1
page_size: Optional[int] = None
status: Optional[List[str]] = None  # Lifecycle filter
tags: Optional[List[str]] = None
order_by: Optional[str] = None  # created_at|last_entry_at|last_access_at|total_entries
direction: str = "desc"
format: str = "structured"  # structured|readable|compact
```

**Outputs**:
- **Structured/Compact**: JSON list of projects with pagination metadata
- **Readable (0 matches)**: Empty state with filter hints
- **Readable (1 match)**: Single project detail view (calls `_gather_doc_info`)
- **Readable (multiple)**: Paginated table with filter/sort controls

**Failure Policy**: Never fails - returns empty list on errors

**State Ownership**: Read-only (queries state/backend/registry, no mutations)

**Key Behaviors**:
- Multi-source merge (StorageBackend + state.json + active project)
- ProjectRegistry enrichment (best-effort)
- Multi-axis filtering (name + status + tags)
- Sorting by registry timestamps or entry counts
- Temp project auto-filtering (via ContextManager)
- Three-way routing based on result count

---

### get_project Contract

**Purpose**: Retrieve single project with full context (recent entries, doc status, activity)

**Inputs**:
```python
project: Optional[str] = None  # Explicit project name
format: str = "structured"  # structured|readable|compact
```

**Outputs**:
- **Structured/Compact**: JSON project dict with meta.docs_status and meta.log_entry_counts
- **Readable**: Context-hydrated view with recent entries (last 5), doc inventory, activity summary

**Failure Policy**: Returns structured error if project not found or not resolvable

**State Ownership**: Read-only (queries state/backend/registry, no mutations)

**Key Behaviors**:
- Project resolution cascade (explicit param → session context → state → registry last-known)
- Hash retrieval via `_compute_doc_status()` (baseline_hashes, current_hashes, flags)
- Per-log entry counts (progress, doc_updates, bugs, security)
- Recent entry parsing (last 5 with complete messages)
- Doc inventory gathering (existence, line counts)
- Context hydration for readable format

---

## Overlap Analysis

### Shared Logic (60-70% overlap)

| Function | list_projects | get_project | LOC | Extractable? |
|----------|--------------|-------------|-----|--------------|
| **Doc Inventory Gathering** | Lines 50-128 (79 LOC) | Lines 130-179 (50 LOC) | ~90-100 total | ✅ YES [BUCKET:metadata] DocInventoryGatherer |
| **Entry Counting** | Delegates to `_gather_doc_info` | Lines 43-52 (10 LOC) | ~15-20 total | ✅ YES (part of DocInventoryGatherer) |
| **Multi-Source Merge** | Lines 183-251 (69 LOC) | N/A (single project only) | ~69 | ⚠️ MAYBE (needs comparison) |
| **ProjectRegistry Enrichment** | Lines 226-250 (25 LOC) | Via `_compute_doc_status` | ~50 total | ✅ YES (unified registry query pattern) |
| **Format Routing** | Lines 372-468 (97 LOC) | Lines 303-345 (43 LOC) | ~140 total | ❌ NO (different presentation needs) |
| **Recent Entry Parsing** | N/A | Lines 70-127 (58 LOC) | ~58 | ✅ YES [BUCKET:parsing] LogEntryParser |

**Total Extractable**: ~230-280 LOC (26-32% of combined 885 LOC)

### Distinct Responsibilities

| Responsibility | list_projects Only | get_project Only |
|----------------|-------------------|-----------------|
| **Multi-project enumeration** | ✅ Core purpose | ❌ Not applicable |
| **Filtering (name/status/tags)** | ✅ Lines 252-289 | ❌ Not applicable |
| **Sorting & ordering** | ✅ Lines 291-327 | ❌ Not applicable |
| **Pagination** | ✅ Lines 329-352 | ❌ Single project only |
| **Three-way routing** | ✅ Lines 372-468 | ❌ Single format only |
| **Hash retrieval** | ❌ Not implemented | ✅ Lines 28-40 (CRITICAL for BUG-001) |
| **Per-log entry counts** | ❌ Not implemented | ✅ Lines 55-67 |
| **Recent entry parsing** | ❌ Not implemented | ✅ Lines 70-127 |
| **Context hydration** | ❌ Not implemented | ✅ Lines 303-345 |
| **Project resolution cascade** | ❌ Assumes active project | ✅ Lines 225-286 |

---

## Use Case Analysis

### When Should Users Call list_projects?

1. **Browse available projects**: "Show me all my projects"
2. **Filter by status**: "Show me all in_progress projects"
3. **Search by name**: "Find projects with 'audit' in the name"
4. **Sort by activity**: "Show me projects I haven't touched in 30+ days"
5. **Paginate large lists**: "Show me page 2 of my projects"

**Expected Result Count**: 0-N projects (typically 5-20)

**Output Focus**: Breadth (many projects, minimal detail per project)

---

### When Should Users Call get_project?

1. **Get current context**: "What project am I working on?"
2. **Deep dive single project**: "Show me everything about project X"
3. **Recent activity review**: "What were my last 5 log entries?"
4. **Doc status check**: "Are my architecture docs modified?"
5. **Hash retrieval for automation**: "Get baseline_hashes for pristine detection"

**Expected Result Count**: Exactly 1 project (or error)

**Output Focus**: Depth (single project, maximum detail)

---

## Unification Scenarios

### Scenario 1: Full Merge (Single Tool)
**Proposal**: Merge both tools into unified `query_projects(filter, limit, detail_level)`

**Pros**:
- Single interface for all project queries
- Eliminates duplication entirely
- Consistent parameter naming

**Cons**:
- Confusing API (when to use `limit=1` vs `project="name"`?)
- Breaks existing user workflows ("Why can't I just get my current project?")
- Overloaded parameters (filter+pagination+detail+context hydration)
- **20+ parameter signature** (already a problem in individual tools)

**Decision**: **REJECT** - Violates principle of focused interfaces

---

### Scenario 2: Shared Base Class (Recommended)
**Proposal**: Extract shared logic into `ProjectQueryEngine`, keep separate MCP tools

**Architecture**:
```python
class ProjectQueryEngine:
    """Shared infrastructure for project queries."""

    def __init__(self, registry: ProjectRegistry, state_manager: StateManager):
        self.registry = registry
        self.state_manager = state_manager
        self.doc_gatherer = DocInventoryGatherer(compute_hashes=True)
        self.entry_parser = LogEntryParser()

    async def merge_project_sources(self) -> Dict[str, Dict[str, Any]]:
        """Merge projects from StorageBackend, state.json, and active project cache."""
        # Lines from list_projects.py:183-251
        ...

    async def enrich_with_registry(self, projects: Dict[str, Dict]) -> None:
        """Overlay ProjectRegistry metadata (best-effort)."""
        # Lines from list_projects.py:226-250
        ...

    async def gather_doc_inventory(self, dev_plan_dir: Path) -> DocInventory:
        """Gather document inventory with optional hash computation."""
        return self.doc_gatherer.gather(dev_plan_dir)

    async def parse_recent_entries(self, log_path: Path, limit: int = 5) -> List[LogEntry]:
        """Parse recent log entries with complete messages."""
        return self.entry_parser.parse_file(log_path, limit=limit)

    async def get_doc_status(self, project_name: str) -> Dict[str, Any]:
        """Retrieve hash data and doc flags from registry."""
        # Lines from get_project.py:28-40
        ...

    async def count_log_entries(self, project: Dict[str, Any]) -> Dict[str, int]:
        """Count entries across all log types."""
        # Lines from get_project.py:55-67
        ...

# Then tools become thin wrappers:
@app.tool()
async def list_projects(...):
    engine = ProjectQueryEngine(registry, state_manager)
    projects = await engine.merge_project_sources()
    await engine.enrich_with_registry(projects)
    # Apply filtering, sorting, pagination (tool-specific logic)
    # Format output based on result count (tool-specific)
    ...

@app.tool()
async def get_project(...):
    engine = ProjectQueryEngine(registry, state_manager)
    # Resolve project (tool-specific cascade logic)
    doc_status = await engine.get_doc_status(project_name)
    recent_entries = await engine.parse_recent_entries(log_path, limit=5)
    doc_inventory = await engine.gather_doc_inventory(dev_plan_dir)
    log_counts = await engine.count_log_entries(project)
    # Format output (tool-specific context hydration)
    ...
```

**Pros**:
- Eliminates 230-280 LOC duplication
- Keeps focused tool interfaces
- Shared infrastructure is testable independently
- Easy to add new query tools (e.g., `search_projects` with semantic search)

**Cons**:
- Adds abstraction layer
- Requires careful interface design (what goes in base vs tool?)

**Decision**: **ACCEPT** - Balances code reuse with interface clarity

---

### Scenario 3: Independent Tools with Shared Utilities (Current State + Extraction)
**Proposal**: Extract only utilities (DocInventoryGatherer, LogEntryParser), keep tools independent

**Architecture**:
```python
# utils/doc_inventory.py
class DocInventoryGatherer:
    def gather(self, dev_plan_dir: Path) -> DocInventory: ...

# utils/log_parser.py
class LogEntryParser:
    def parse_file(self, log_path: Path, limit: int) -> List[LogEntry]: ...

# tools/list_projects.py
_doc_gatherer = DocInventoryGatherer()
_entry_parser = LogEntryParser()

async def list_projects(...):
    # Still has multi-source merge logic (lines 183-251)
    # Still has filtering/sorting/pagination (lines 252-352)
    # Uses _doc_gatherer instead of duplicating logic
    ...

# tools/get_project.py
_doc_gatherer = DocInventoryGatherer()
_entry_parser = LogEntryParser()

async def get_project(...):
    # Still has resolution cascade (lines 225-286)
    # Still has context hydration (lines 303-345)
    # Uses _doc_gatherer and _entry_parser instead of duplicating
    ...
```

**Pros**:
- Minimal change (only extract proven duplicates)
- No new abstraction layers
- Tools remain independent (easy to modify)

**Cons**:
- Doesn't eliminate all duplication (multi-source merge still duplicated)
- Misses opportunity for unified registry query pattern
- Future tools still need to duplicate merge/enrichment logic

**Decision**: **DEFER** - Acceptable as Phase 1, but Scenario 2 is better long-term

---

## Recommended Unification Strategy

### Phase 1: Extract Proven Duplicates (Immediate)
**Priority**: P1 (addresses DUPLICATION-002)

1. **Extract DocInventoryGatherer** [BUCKET:metadata]
   - Consolidate list_projects.py:50-128 + get_project.py:130-179 + set_project.py:61-127
   - Add hash computation support (optional parameter)
   - Target: ~90-100 LOC reduction

2. **Extract LogEntryParser** [BUCKET:parsing]
   - Consolidate get_project.py:70-127
   - Reuse in read_recent.py, query_entries.py (if applicable)
   - Target: ~58 LOC reduction

**Impact**: 150-160 LOC reduction (17-18% of combined 885 LOC)

---

### Phase 2: Create ProjectQueryEngine Base (Future)
**Priority**: P2 (architectural improvement)

1. **Extract Multi-Source Merger**
   - Consolidate list_projects.py:183-251
   - Verify get_project doesn't need multi-source (it has resolution cascade instead)
   - Decision: May not be shared after all (different semantics)

2. **Extract ProjectRegistry Enrichment Pattern**
   - Consolidate list_projects.py:226-250 + get_project.py:28-40
   - Unified: `enrich_with_registry(projects, include_hashes=True)`
   - Target: ~50 LOC reduction

3. **Create ProjectQueryEngine Base Class**
   - Hosts shared methods: merge_sources, enrich_registry, gather_inventory, parse_entries, get_doc_status, count_logs
   - Tools extend base and add tool-specific logic (filtering, sorting, formatting)

**Impact**: Additional 80-100 LOC reduction (9-11% of combined 885 LOC)

**TOTAL REDUCTION**: 230-260 LOC (26-29% of combined 885 LOC)

---

## Before/After Mental Model

### Before (Current State)

```
User → list_projects
        ├─ Multi-source merge (69 LOC) ─────────┐
        ├─ Registry enrichment (25 LOC) ────────┤
        ├─ Doc gathering (79 LOC) ──────────────┤  DUPLICATION
        ├─ Filtering/sorting (67 LOC)          │
        ├─ Pagination (23 LOC)                 │
        └─ Three-way routing (97 LOC)          │
                                                │
User → get_project                               │
        ├─ Resolution cascade (62 LOC)          │
        ├─ Hash retrieval (13 LOC) ─────────────┤
        ├─ Doc gathering (50 LOC) ──────────────┤
        ├─ Entry parsing (58 LOC) ──────────────┤
        ├─ Log counts (13 LOC)                 │
        └─ Context hydration (43 LOC)          │
                                                ↓
                                        ~230-280 LOC duplicated
```

### After (Phase 1 + Phase 2)

```
                ProjectQueryEngine (Shared Base)
                ├─ merge_project_sources() ──────────┐
                ├─ enrich_with_registry()            │  SHARED
                ├─ DocInventoryGatherer.gather()     │  INFRASTRUCTURE
                ├─ LogEntryParser.parse_file()       │  (~230-280 LOC)
                ├─ get_doc_status() (hash retrieval) │
                └─ count_log_entries()               │
                                                      ↓
User → list_projects (Tool-Specific: ~300 LOC)
        ├─ Uses engine.merge_project_sources()
        ├─ Uses engine.enrich_with_registry()
        ├─ Uses engine.gather_doc_inventory() [when single match]
        ├─ Filtering/sorting (67 LOC) ────────────┐
        ├─ Pagination (23 LOC)                    │  DISTINCT
        └─ Three-way routing (97 LOC)             │  TOOL LOGIC
                                                   │
User → get_project (Tool-Specific: ~150 LOC)      │
        ├─ Resolution cascade (62 LOC) ───────────┤
        ├─ Uses engine.get_doc_status()           │
        ├─ Uses engine.parse_recent_entries()     │
        ├─ Uses engine.gather_doc_inventory()     │
        └─ Context hydration (43 LOC)             │
                                                   ↓
                                        Shared: ~230-280 LOC
                                        list_projects: ~300 LOC
                                        get_project: ~150 LOC
                                        ────────────────────────
                                        TOTAL: ~680-730 LOC
                                        (Down from 885 LOC, 17-23% reduction)
```

**Conceptual Win**:
- **Before**: Tools independently decide what "project data" means
- **After**: ProjectQueryEngine defines canonical project truth, tools adapt to presentation needs
- **Maintainability**: Bug fixes in data gathering happen once, not 3x
- **Extensibility**: New query tools (search_projects, filter_projects) inherit proven infrastructure

---

## Risks & Mitigations

### Risk 1: Over-Abstraction
**Concern**: ProjectQueryEngine becomes a god object with too many responsibilities

**Mitigation**:
- Keep engine focused on data gathering only (no formatting, no business logic)
- Tools retain ownership of filtering, sorting, pagination, formatting
- Clear contract: engine provides raw data, tools decide presentation

---

### Risk 2: Breaking Changes
**Concern**: Extraction requires modifying working tools (introduces regression risk)

**Mitigation**:
- Phase 1 (utility extraction) is low-risk (pure functions, no coupling)
- Phase 2 (engine creation) happens after Phase 1 proves stability
- Comprehensive test coverage before extraction (see SPEC-LIST-003, SPEC-GET-001)
- Keep old code until new code verified (parallel implementation, then swap)

---

### Risk 3: Performance Overhead
**Concern**: Abstraction layer adds function call overhead

**Mitigation**:
- Extractable functions are already async (function call overhead negligible)
- Profile before/after to verify no regression
- Most cost is I/O (file reads, DB queries), not function calls

---

## Decision Matrix

| Criterion | Full Merge | Shared Base (Recommended) | Independent + Utils |
|-----------|-----------|---------------------------|---------------------|
| **Code Reuse** | 100% (one tool) | 60-70% (shared engine) | 30-40% (utils only) |
| **Interface Clarity** | ❌ Poor (overloaded params) | ✅ Excellent (focused tools) | ✅ Excellent (no change) |
| **Maintainability** | ⚠️ Medium (complex tool) | ✅ High (shared infra) | ⚠️ Medium (still duplicated merge logic) |
| **Extensibility** | ❌ Hard (modify mega-tool) | ✅ Easy (extend engine) | ⚠️ Medium (duplicate base logic) |
| **Migration Risk** | 🔴 High (rewrite both tools) | 🟡 Medium (extract in phases) | 🟢 Low (extract utils only) |
| **Testing Burden** | 🔴 High (full regression) | 🟡 Medium (incremental) | 🟢 Low (minimal change) |

**Recommended**: **Shared Base (Phase 1 → Phase 2 approach)**

---

## Implementation Roadmap

### Phase 1: Utility Extraction (Wave 2 → Phase 6 boundary)
**Target Date**: Phase 6 Sprint 1
**Deliverables**:
- `utils/doc_inventory.py` - DocInventoryGatherer class
- `utils/log_parser.py` - LogEntryParser class
- Updated list_projects.py (uses DocInventoryGatherer)
- Updated get_project.py (uses both utilities)
- Updated set_project.py (uses DocInventoryGatherer)
- Test coverage: 90%+ for new utilities

**Success Criteria**:
- All 3 tools pass existing tests
- Doc gathering logic consolidated (90-100 LOC reduction)
- Entry parsing logic consolidated (58 LOC reduction)

---

### Phase 2: Engine Creation (Phase 6 Sprint 2-3)
**Target Date**: Phase 6 Sprint 2-3
**Deliverables**:
- `shared/project_query_engine.py` - ProjectQueryEngine base class
- Updated list_projects.py (extends engine)
- Updated get_project.py (extends engine)
- Architectural decision record (why we chose shared base over full merge)
- Test coverage: 95%+ for engine

**Success Criteria**:
- Multi-source merge logic consolidated
- Registry enrichment pattern unified
- Hash retrieval abstracted (get_doc_status method)
- Tools maintain same external interface (backward compatible)
- Performance neutral or improved

---

### Phase 3: New Query Tools (Future)
**Target Date**: TBD
**Potential Tools**:
- `search_projects` - Semantic search across project metadata
- `filter_projects` - Advanced filtering with boolean logic
- `compare_projects` - Side-by-side comparison of 2+ projects

**All Future Tools**:
- Extend ProjectQueryEngine base
- Inherit proven data gathering infrastructure
- Focus on unique filtering/presentation logic

---

## Conclusion

**Should list_projects and get_project be unified?**

**Answer**: **Yes, but not as a single tool**

**Strategy**: Extract shared infrastructure into ProjectQueryEngine base class while maintaining distinct MCP tools for different use cases.

**Rationale**:
- Tools serve different purposes (enumeration vs deep-dive) → keep separate interfaces
- Tools share 60-70% of data gathering logic → extract shared infrastructure
- Future query tools will benefit from proven base class → extensibility win

**Phase 1 (Immediate)**: Extract DocInventoryGatherer + LogEntryParser utilities (150-160 LOC reduction, 17-18%)

**Phase 2 (Future)**: Create ProjectQueryEngine base class (additional 80-100 LOC reduction, 9-11%)

**Total Impact**: 230-260 LOC reduction (26-29% of combined 885 LOC)

**Before/After**:
- **Before**: 885 LOC with ~230-280 LOC duplicated across 3 tools
- **After**: ~680-730 LOC with shared infrastructure + focused tool logic
- **Conceptual Win**: "Get project data" becomes a named, testable operation; tools focus on presentation

---

## Notes for Phase 6

**Critical Decisions**:
1. **Phase 1 MUST happen before Phase 2** - Prove utility extraction works before creating engine
2. **Test coverage is mandatory** - Extract with confidence, not hope
3. **Backward compatibility is non-negotiable** - External tool interface must not change
4. **Multi-source merge may not be shared** - list_projects merges 3 sources, get_project has resolution cascade (different semantics, investigate first)

**Defer Until After Phase 1**:
- Engine creation (wait for utility extraction to prove extraction methodology)
- Multi-source merger investigation (need to verify get_project doesn't need it)
- New query tool planning (wait for engine stability)
