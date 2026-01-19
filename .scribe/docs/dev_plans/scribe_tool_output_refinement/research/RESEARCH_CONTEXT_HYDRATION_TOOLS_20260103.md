# Research Report: Context Hydration Tools (Phase 4)

**Project:** scribe_tool_output_refinement
**Author:** Orchestrator (with User)
**Date:** 2026-01-03
**Status:** Design Complete - Ready for Implementation

---

## Executive Summary

This research documents the design for Phase 4 of the tool output refinement project: transforming `list_projects`, `get_project`, and `set_project` into **context hydration tools** that provide agents with clean, actionable situational awareness.

**Key Insight:** These tools should act as "where am I?" and "what's here?" commands, not JSON dumps. Use the existing `format` parameter system (readable/structured/compact) - no new flags needed.

**Token Savings:** Estimated 90% reduction in typical usage (2000+ tokens → 200-300 tokens per workflow).

---

## Current State Analysis

### Tool Audit Results

#### **list_projects** (350 lines of code)
- **Current Behavior:** Returns massive JSON array with full project dictionaries
- **Registry Enrichment:** Adds status, created_at, last_entry_at, last_access_at, total_entries, total_files, meta, tags
- **Pagination:** Already has `page` and `page_size` parameters but output is still overwhelming
- **Token Impact:** 2000+ tokens for 5 projects with all metadata
- **Problem:** Agents get flooded with data they don't need for basic project browsing

#### **get_project** (188 lines)
- **Current Behavior:** Returns full project dict + `docs_status` object + `log_entry_counts` for ALL log types
- **Computation Cost:** Counts entries in progress, bugs, doc_updates, security, global logs
- **Token Impact:** 500-1000 tokens per call with all metadata
- **Problem:** Too much data when agent just needs "what project am I in?"

#### **set_project** (631 lines)
- **Current Behavior:** Returns detailed bootstrap info (validation, doc creation, registry updates, reminder resets)
- **Token Impact:** 300-800 tokens per call
- **Problem:** Doesn't distinguish between "new project" vs "existing project" context

---

## Design Decisions

### Core Principle: Context Hydration

**Tools should answer:**
1. **list_projects:** "What projects exist? Which one should I work on?"
2. **get_project:** "Where am I? What's the current state?"
3. **set_project:** "What am I walking into? New or existing project?"

### Use Existing `format` Parameter

- **`format="readable"`** (default): Clean, context-aware output for agents
- **`format="structured"`**: Current full JSON (backward compatible)
- **`format="compact"`**: Minimal output for token conservation

**No new parameters needed!** We already have the infrastructure.

---

## Tool Designs

### 1. list_projects - Project Search Interface

#### Behavior Logic

```python
# After applying filters (name, status, tags, order_by)
filtered_count = len(projects_list)

if format == "readable":
    if filtered_count == 0:
        return format_no_projects_found(filter_info)
    elif filtered_count == 1:
        # Single match - show detailed view
        return format_project_detail(projects_list[0], registry_info)
    else:
        # Multiple matches - show table with pagination
        return format_projects_table(projects_list, pagination_info, filter_info)
```

#### Output Format A: Multiple Projects (List View)

```
╔══════════════════════════════════════════════════════════╗
║ 📋 PROJECTS - 15 total (Page 1 of 3, showing 5)         ║
╚══════════════════════════════════════════════════════════╝

NAME                           STATUS        ENTRIES  LAST ACTIVITY
─────────────────────────────────────────────────────────────────────
⭐ scribe_tool_output_refine   in_progress      259   2 hours ago
  scribe_sentinel_concurrency  in_progress      142   1 day ago
  sentinel                     planning          12   3 days ago
  scribe_mcp                   complete         500   1 week ago
  phase4_enhancements          planning           8   2 weeks ago

📄 Page 1 of 3 | Use page=2 to see more
🔍 Filter: none | Sort: last_entry_at (desc)
💡 Tip: Add filter="scribe" to narrow results, or filter="exact_name" to see details
```

**Token Estimate:** ~200 tokens (vs 2000+ currently)

#### Output Format B: Single Project Match (Detail View)

```
╔══════════════════════════════════════════════════════════╗
║ 📁 PROJECT DETAIL: scribe_tool_output_refinement        ║
║    (1 match found for filter: "tool_output")            ║
╚══════════════════════════════════════════════════════════╝

Status: in_progress ⭐ (active)
Root: /home/austin/projects/MCP_SPINE/scribe_mcp
Dev Plan: .scribe/docs/dev_plans/scribe_tool_output_refinement/

📊 Activity:
  • Total Entries: 259 (progress: 259, doc_updates: 13, bugs: 0)
  • Last Entry: 2 hours ago (2026-01-03 09:53 UTC)
  • Last Access: 5 minutes ago
  • Created: 2 weeks ago

📄 Documents:
  ✓ ARCHITECTURE_GUIDE.md (1274 lines, modified)
  ✓ PHASE_PLAN.md (542 lines)
  ✓ CHECKLIST.md (356 lines)
  ✓ PROGRESS_LOG.md (298 entries)

📁 Custom Content:
  • research/ (3 files)
  • TOOL_LOG.jsonl (present)

🏷️  Tags: phase4, output-refinement, tokens
⚠️  Docs Status: Architecture modified - not ready for work

💡 Use get_project() to see recent progress entries
```

**Token Estimate:** ~400 tokens (vs 2000+ currently)

#### Output Format C: No Matches (Helpful Guidance)

```
╔══════════════════════════════════════════════════════════╗
║ 📋 PROJECTS - 0 matches for filter: "nonexistent"       ║
╚══════════════════════════════════════════════════════════╝

No projects found matching your criteria.

🔍 Active Filters:
  • Name: "nonexistent"

💡 Try:
  • Remove filters: list_projects()
  • Broader search: list_projects(filter="scribe")
  • Check status: list_projects(status=["planning", "in_progress"])
```

**Token Estimate:** ~100 tokens

#### Implementation Requirements

**ResponseFormatter Methods:**
- `format_projects_table(projects, active, pagination_info, filter_info)` - List view
- `format_project_detail(project, registry_info, docs_info)` - Detail view
- `format_no_projects_found(filter_info)` - Empty state with tips

**Data Gathering:**
- Project registry info (status, created_at, last_entry_at, total_entries)
- Active project indicator from state
- Document existence checks (if single match)
- Line counts for documents (if single match)
- Custom content detection (research/, TOOL_LOG.jsonl, etc.)

---

### 2. get_project - "Where Am I?" Command

#### Purpose

Provide instant situational awareness when returning to a project:
- Project location and structure
- Document inventory
- Recent activity preview (last 5 progress entries)

#### Output Format (Readable)

```
╔══════════════════════════════════════════════════════════╗
║ 🎯 CURRENT PROJECT: scribe_tool_output_refinement       ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/scribe_tool_output_refinement/

📄 Documents:
  • ARCHITECTURE_GUIDE.md (1274 lines)
  • PHASE_PLAN.md (542 lines)
  • CHECKLIST.md (356 lines)
  • PROGRESS_LOG.md (298 entries)

📊 Recent Activity (last 5 entries):
    1. [🧭] 09:53 | Orchestrator | Refined approach: Use existing format parameter...
    2. [🧭] 09:48 | Orchestrator | Code audit complete: list_projects returns massive JSON...
    3. [🧭] 09:45 | Orchestrator | Planning session started: Phase 4 continuation...
    4. [✅] 05:24 | Orchestrator | Fixed test_query_priority_filters.py - Root cause...
    5. [⚠️] 05:18 | Orchestrator | Batch 3 Complete (with test issues)...

⏰ Status: in_progress | Entries: 259 | Last: 2 hours ago
```

**Token Estimate:** ~300 tokens (vs 800-1000 currently)

#### Implementation Requirements

**ResponseFormatter Methods:**
- `format_project_context(project, recent_entries, docs_info, activity_summary)`

**Data Gathering:**
- Project metadata (name, root, dev plan path, status)
- Document existence + line counts (stat files, don't read full content)
- Last 5 progress log entries (use existing log parser on PROGRESS_LOG.md)
- Activity summary from registry (total_entries, last_entry_at)

**Key Optimization:**
- **Don't** compute per-log-type entry counts (skip progress, bugs, doc_updates, security counts)
- **Don't** include full docs_status object
- **Do** show just enough to orient the agent

---

### 3. set_project - Situational Report (SITREP)

#### Purpose

Provide immediate context about what the agent is walking into:
- Is this a brand new project or existing work?
- What already exists (logs, docs, custom content)?
- What's the current state (modified docs, activity level)?

#### Output Format A: New Project

```
╔══════════════════════════════════════════════════════════╗
║ ✨ NEW PROJECT CREATED: my_new_feature                  ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/my_new_feature/

📄 Documents Created:
  ✓ ARCHITECTURE_GUIDE.md (template, 120 lines)
  ✓ PHASE_PLAN.md (template, 80 lines)
  ✓ CHECKLIST.md (template, 60 lines)
  ✓ PROGRESS_LOG.md (empty, ready for entries)

🎯 Status: planning (new project)
💡 Next: Start with research or architecture phase
```

**Token Estimate:** ~150 tokens

#### Output Format B: Existing Project (Active Work)

```
╔══════════════════════════════════════════════════════════╗
║ 📌 PROJECT ACTIVATED: scribe_tool_output_refinement     ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/scribe_tool_output_refinement/

📊 Existing Project Inventory:
  • Status: in_progress (active work)
  • Total Entries: 259 (progress: 259, doc_updates: 13)
  • Last Activity: 2 hours ago

📄 Documents (4 total):
  ⚠️ ARCHITECTURE_GUIDE.md (1274 lines, modified recently)
  ✓ PHASE_PLAN.md (542 lines)
  ✓ CHECKLIST.md (356 lines)
  ✓ PROGRESS_LOG.md (298 entries)

📁 Custom Documents:
  • research/ (3 files)
  • TOOL_LOG.jsonl (present)

💡 Context: Continuing active development - review recent progress entries
```

**Token Estimate:** ~250 tokens (vs 500-800 currently)

#### Implementation Requirements

**ResponseFormatter Methods:**
- `format_project_sitrep_new(project, docs_created)`
- `format_project_sitrep_existing(project, inventory, activity)`

**Detection Logic:**
```python
# Detect new vs existing
is_new = not progress_log_path.exists() or progress_log_entry_count == 0
```

**Data Gathering:**
- Check if PROGRESS_LOG.md exists and has entries
- Document inventory (standard + custom)
- Registry metadata (status, total_entries, last_entry_at)
- Modified docs detection (compare hashes from registry)
- Custom content detection (scan for research/, bugs/, custom .jsonl files)

---

## Implementation Plan

### Phase 1: ResponseFormatter Extensions

**New Methods to Add:**

```python
# In utils/response.py

# list_projects formatters
def format_projects_table(self, projects, active_name, pagination, filters):
    """Format project list as minimal table with pagination."""
    pass

def format_project_detail(self, project, registry_info, docs_info):
    """Format single project deep dive with full details."""
    pass

def format_no_projects_found(self, filter_info):
    """Format helpful empty state with search tips."""
    pass

# get_project formatter
def format_project_context(self, project, recent_entries, docs_info, activity):
    """Format current project context with recent activity."""
    pass

# set_project formatters
def format_project_sitrep_new(self, project, docs_created):
    """Format SITREP for newly created project."""
    pass

def format_project_sitrep_existing(self, project, inventory, activity):
    """Format SITREP for existing project activation."""
    pass
```

**Helper Functions Needed:**
- `_format_relative_time(timestamp)` - "2 hours ago", "3 days ago"
- `_get_doc_line_count(file_path)` - Fast line count without full read
- `_detect_custom_content(docs_dir)` - Scan for research/, bugs/, .jsonl files
- `_truncate_message(message, max_length)` - Truncate long log messages

### Phase 2: Tool Integration

#### **list_projects.py**

```python
# After filtering logic
filtered_count = len(projects_list)

if format == "readable":
    if filtered_count == 0:
        return formatter.format_no_projects_found({
            "name_filter": filter,
            "status_filter": status,
            "tags_filter": tags
        })
    elif filtered_count == 1:
        project = projects_list[0]
        # Gather detailed info
        registry_info = _PROJECT_REGISTRY.get_project(project["name"])
        docs_info = await _gather_doc_info(project)
        return formatter.format_project_detail(project, registry_info, docs_info)
    else:
        pagination_info = {
            "page": page,
            "page_size": actual_page_size,
            "total": total_count,
            "total_pages": total_pages
        }
        filter_info = {
            "name": filter,
            "status": status,
            "tags": tags,
            "order_by": order_by,
            "direction": direction
        }
        return formatter.format_projects_table(
            projects_list,
            current_name,
            pagination_info,
            filter_info
        )
```

#### **get_project.py**

```python
# After resolving target_project
if format == "readable":
    # Read last 5 progress log entries
    recent_entries = await _read_recent_progress_entries(
        target_project["progress_log"],
        limit=5
    )

    # Gather doc info
    docs_info = await _gather_doc_info(target_project)

    # Activity summary from registry
    registry_info = _PROJECT_REGISTRY.get_project(current_name)
    activity_summary = {
        "total_entries": registry_info.total_entries if registry_info else 0,
        "last_entry_at": registry_info.last_entry_at if registry_info else None,
        "status": registry_info.status if registry_info else "unknown"
    }

    return formatter.format_project_context(
        target_project,
        recent_entries,
        docs_info,
        activity_summary
    )
```

#### **set_project.py**

```python
# After project setup
if format == "readable":
    progress_log_path = Path(resolved_log)
    is_new = not progress_log_path.exists() or await _count_log_entries(progress_log_path) == 0

    if is_new:
        docs_created = {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(resolved_log)
        }
        return formatter.format_project_sitrep_new(project_data, docs_created)
    else:
        # Gather inventory
        inventory = await _gather_project_inventory(project_data)
        registry_info = _PROJECT_REGISTRY.get_project(name)
        activity = {
            "status": registry_info.status if registry_info else "unknown",
            "total_entries": registry_info.total_entries if registry_info else 0,
            "last_entry_at": registry_info.last_entry_at if registry_info else None
        }
        return formatter.format_project_sitrep_existing(
            project_data,
            inventory,
            activity
        )
```

### Phase 3: Testing Strategy

**Unit Tests (ResponseFormatter):**
- Test each formatter method with sample data
- Verify ASCII box alignment at 80, 120, 160 character widths
- Test relative time formatting ("2 hours ago", "3 days ago", "2 weeks ago")
- Test truncation of long messages
- Test empty states and edge cases

**Integration Tests:**

**list_projects:**
- Test multi-project list view with pagination
- Test single-project detail view (filter narrows to 1)
- Test no matches empty state
- Test all format modes (readable/structured/compact)
- Test backward compatibility (existing tests should pass)

**get_project:**
- Test readable format with recent entries
- Test with new project (no entries yet)
- Test with missing documents
- Test format modes
- Test backward compatibility

**set_project:**
- Test new project SITREP
- Test existing project SITREP
- Test with custom content (research/, TOOL_LOG.jsonl)
- Test format modes
- Test backward compatibility

---

## Token Savings Analysis

### Current State (format="structured")

| Tool Call | Current Tokens | Use Case |
|-----------|----------------|----------|
| `list_projects()` | ~2000 | List 5 projects with full metadata |
| `list_projects(filter="scribe")` | ~1500 | Filtered list (3 projects) |
| `get_project()` | ~800 | Get current project with all counts |
| `set_project("new")` | ~500 | Create new project |
| `set_project("existing")` | ~700 | Activate existing project |

**Total workflow (typical):** ~3000-4000 tokens

### Proposed State (format="readable")

| Tool Call | New Tokens | Savings |
|-----------|------------|---------|
| `list_projects()` | ~200 | 90% ↓ |
| `list_projects(filter="scribe")` | ~150 | 90% ↓ |
| `get_project()` | ~300 | 62% ↓ |
| `set_project("new")` | ~150 | 70% ↓ |
| `set_project("existing")` | ~250 | 64% ↓ |

**Total workflow (typical):** ~500-700 tokens

**Net Savings:** 2500-3300 tokens per workflow (83-85% reduction)

---

## Implementation Checklist

### Phase 1: ResponseFormatter (Foundation)
- [ ] Add `_format_relative_time()` helper
- [ ] Add `_get_doc_line_count()` helper
- [ ] Add `_detect_custom_content()` helper
- [ ] Add `_truncate_message()` helper
- [ ] Implement `format_projects_table()`
- [ ] Implement `format_project_detail()`
- [ ] Implement `format_no_projects_found()`
- [ ] Implement `format_project_context()`
- [ ] Implement `format_project_sitrep_new()`
- [ ] Implement `format_project_sitrep_existing()`
- [ ] Unit tests for all formatters (100% coverage)

### Phase 2: list_projects Integration
- [ ] Add filtering result count logic
- [ ] Add `_gather_doc_info()` helper function
- [ ] Implement 3-way routing (no matches / single match / multiple matches)
- [ ] Wire up `format_projects_table()` for multi-project view
- [ ] Wire up `format_project_detail()` for single-project view
- [ ] Wire up `format_no_projects_found()` for empty state
- [ ] Integration tests for all 3 scenarios
- [ ] Verify backward compatibility (existing tests pass)

### Phase 3: get_project Integration
- [ ] Add `_read_recent_progress_entries()` helper
- [ ] Add `_gather_doc_info()` helper (shared with list_projects)
- [ ] Wire up `format_project_context()`
- [ ] Integration tests for readable format
- [ ] Test with new project (no entries)
- [ ] Test with missing documents
- [ ] Verify backward compatibility

### Phase 4: set_project Integration
- [ ] Add `_gather_project_inventory()` helper
- [ ] Add new vs existing detection logic
- [ ] Wire up `format_project_sitrep_new()`
- [ ] Wire up `format_project_sitrep_existing()`
- [ ] Integration tests for both scenarios
- [ ] Test with custom content detection
- [ ] Verify backward compatibility

### Phase 5: Documentation & Polish
- [ ] Update tool docstrings with format parameter examples
- [ ] Update CLAUDE.md with new tool behaviors
- [ ] Visual validation of all output formats
- [ ] Performance benchmarks (verify <5ms overhead)
- [ ] Code review and merge

---

## Risk Assessment

### Low Risk
- **Backward Compatibility:** Default to `format="structured"` maintains existing behavior
- **Performance:** Minimal overhead for formatting (estimated <5ms)
- **Testing:** Can test all scenarios independently

### Medium Risk
- **Line Count Performance:** Reading file stats for 5-8 projects could be slow on slow filesystems
  - **Mitigation:** Cache line counts in registry metadata, update on doc changes
- **Progress Log Parsing:** Reading last 5 entries requires parsing from end of file
  - **Mitigation:** Use existing `read_all_lines()` + slice last 5, optimize later if needed

### Mitigated Risk
- **Filter Logic Complexity:** Single-match detection could be buggy
  - **Mitigation:** Comprehensive integration tests, edge case coverage
- **Custom Content Detection:** Scanning directories could be expensive
  - **Mitigation:** Only scan when filter narrows to 1 project (detail view)

---

## Success Criteria

1. **Token Efficiency:** ≥80% reduction in typical tool usage workflows
2. **Agent Usability:** Agents prefer readable format over structured format in practice
3. **Backward Compatibility:** All existing tests pass without modification
4. **Performance:** Readable format adds <5ms overhead per tool call
5. **Code Quality:** 100% test coverage for new formatter methods
6. **Documentation:** Clear examples in tool docstrings and CLAUDE.md

---

## Next Steps

1. **Assign to Scribe Coder:** Implement ResponseFormatter methods (Phase 1)
2. **Integrate list_projects:** Wire up 3-way routing logic (Phase 2)
3. **Integrate get_project:** Add recent entries preview (Phase 3)
4. **Integrate set_project:** Add SITREP logic (Phase 4)
5. **Test & Validate:** Comprehensive integration testing (Phase 5)
6. **Document & Ship:** Update docs and merge to main

---

## Appendix: Example Tool Calls

### list_projects Examples

```python
# List all projects (default - multi-project view)
await list_projects()
# Returns: Table with 5-8 projects, pagination info

# Search for specific project
await list_projects(filter="scribe")
# Returns: Filtered table (3 projects match)

# Narrow to single project (detail view)
await list_projects(filter="tool_output_refinement")
# Returns: Detailed single-project view (exactly 1 match)

# Paginate through all projects
await list_projects(page=2, page_size=10)
# Returns: Table showing page 2 (projects 11-20)

# Filter by status
await list_projects(status=["in_progress", "blocked"])
# Returns: Table showing only active work

# Get structured JSON (backward compatible)
await list_projects(format="structured")
# Returns: Current full JSON array
```

### get_project Examples

```python
# Get current project context (readable)
await get_project()
# Returns: Context box with location, docs, last 5 entries

# Get full JSON (backward compatible)
await get_project(format="structured")
# Returns: Current full JSON response
```

### set_project Examples

```python
# Create new project (readable SITREP)
await set_project(name="my_new_feature")
# Returns: "NEW PROJECT CREATED" SITREP

# Activate existing project (readable SITREP)
await set_project(name="scribe_tool_output_refinement")
# Returns: "PROJECT ACTIVATED" SITREP with inventory

# Get full JSON (backward compatible)
await set_project(name="project", format="structured")
# Returns: Current full JSON response
```

---

**End of Research Report**
