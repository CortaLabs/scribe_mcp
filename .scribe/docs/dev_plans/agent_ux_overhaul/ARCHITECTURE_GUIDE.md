---
id: agent_ux_overhaul-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 agent_ux_overhaul"
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-19'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — agent_ux_overhaul
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-19 06:54:56 UTC

> Architecture guide for agent_ux_overhaul.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
### 1.1 Context

Scribe MCP tools are designed for AI agents, but two critical UX issues cause agent failures, wasted tokens, and protocol abandonment:

1. **Slugify Inconsistency**: Project names are normalized differently across the codebase. The filesystem uses slugified names (`my_project`), but database and state store raw names (`My-Project`). Agents using hyphens vs underscores get silent lookup failures.

2. **manage_docs Complexity**: 18 actions with overlapping names, inconsistent parameter requirements, and undocumented metadata keys cause agents to fail repeatedly. Five different `create_*` actions, three different `replace_*` actions, and inspection actions that duplicate `read_file` functionality.

### 1.2 Goals

| Goal | Success Metric |
|------|----------------|
| Single-source normalization | Any project name format (hyphens, underscores, spaces, mixed case) resolves correctly |
| Simplified manage_docs | 7 focused actions instead of 18 |
| Conservative healing | Format issues auto-fixed; semantic errors fail fast with suggestions |
| Zero documentation dependency | Tools work without agents reading docs |
| Zero regressions | Existing projects and workflows continue to work |

### 1.3 Non-Goals

- Changing what existing actions DO (behavior preservation)
- Aggressive parameter healing that changes intent
- Breaking existing projects/data
- Rewriting manage_docs from scratch
- Auto-transform by default (opt-in via frontmatter only)
<!-- ID: requirements_constraints -->
### 2.1 Functional Requirements

**Workstream 1: Slugify Consolidation**
- FR-1.1: Create `normalize_project_input()` wrapper function in `utils/slug.py`
- FR-1.2: Apply normalization at EVERY tool entry point that accepts project names
- FR-1.3: Implement collision detection in `set_project` (prevent "my-project" and "my_project" coexisting)
- FR-1.4: Implement lazy DB migration (normalize on first access, not big-bang)
- FR-1.5: Normalize state dict keys for consistent lookups

**Workstream 2: manage_docs Simplification**
- FR-2.1: Consolidate 5 `create_*` actions into single `create` action with `doc_type` routing
- FR-2.2: Keep 6 core editing actions unchanged (replace_section, apply_patch, replace_range, replace_text, append, status_update)
- FR-2.3: Remove/deprecate Category 3+4 actions (normalize_headers, generate_toc, validate_crosslinks, list_sections, list_checklist_items, search, batch)
- FR-2.4: Implement opt-in auto-transform via frontmatter flags
- FR-2.5: Maintain backwards compatibility with old action names as aliases

### 2.2 Non-Functional Requirements

- NFR-1: Zero breaking changes to existing projects (all current calls must continue working)
- NFR-2: No data migration required (lazy normalization on access)
- NFR-3: Clear deprecation warnings for old action names
- NFR-4: All changes must pass existing test suite

### 2.3 Technical Constraints

| Constraint | Impact |
|------------|--------|
| Database stores raw names | Lazy migration required; can't rename existing records |
| State dict keyed by raw names | Must normalize keys or support flexible lookup |
| 18 actions already deployed | Backwards compatibility via aliases |
| BulletproofParameterCorrector exists | Extend rather than replace |
| Frontmatter infrastructure exists | Use for opt-in flags |

### 2.4 Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Collision on lazy migration | HIGH | Detect and warn, don't auto-merge |
| Old action names breaking | MEDIUM | Keep as aliases with deprecation warning |
| Auto-transform corrupting docs | HIGH | Opt-in only via frontmatter, never default |
| Parameter healing hiding bugs | MEDIUM | Always include healing report in response |
<!-- ID: architecture_overview -->
### 3.1 Solution Summary

Two parallel workstreams that share a common goal: make Scribe tools "just work" without documentation dependency.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT UX OVERHAUL                                │
├─────────────────────────────────────────────────────────────────────┤
│  WORKSTREAM 1: Slugify Consolidation                                │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  User Input                                                    │ │
│  │  "My-Project" / "my_project" / "MY PROJECT"                    │ │
│  │         │                                                      │ │
│  │         ▼                                                      │ │
│  │  ┌─────────────────────────────┐                               │ │
│  │  │ normalize_project_input()  │ ← Single source of truth      │ │
│  │  │ (utils/slug.py)            │                               │ │
│  │  └─────────────────────────────┘                               │ │
│  │         │                                                      │ │
│  │         ▼                                                      │ │
│  │  Canonical: "my_project"                                       │ │
│  │         │                                                      │ │
│  │    ┌────┴────┬─────────┬──────────┐                           │ │
│  │    ▼         ▼         ▼          ▼                           │ │
│  │  DB        State     Filesystem  Config                       │ │
│  │  Lookup    Dict Key  Path        Lookup                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│  WORKSTREAM 2: manage_docs Simplification                           │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                                                                │ │
│  │  BEFORE: 18 Actions                                           │ │
│  │  ├── Creation (5): create_doc, create_research_doc, ...       │ │
│  │  ├── Editing (6): replace_section, apply_patch, ...           │ │
│  │  ├── Transform (3): normalize_headers, generate_toc, ...      │ │
│  │  └── Inspect (4): list_sections, search, ...                  │ │
│  │                                                                │ │
│  │  AFTER: 7 Focused Actions                                      │ │
│  │  ├── create (doc_type="custom|research|bug|review|agent_card")│ │
│  │  ├── replace_section                                          │ │
│  │  ├── apply_patch                                              │ │
│  │  ├── replace_range                                            │ │
│  │  ├── replace_text                                             │ │
│  │  ├── append                                                   │ │
│  │  └── status_update                                            │ │
│  │                                                                │ │
│  │  REMOVED: Transforms (opt-in via frontmatter), Inspect (use   │ │
│  │           read_file instead), batch (power user edge case)    │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Breakdown

**Component 1: Normalization Layer (`utils/slug.py`)**
- New function: `normalize_project_input(name: Optional[str]) -> Optional[str]`
- Wraps existing `slugify_project_name()` with None/empty handling
- Single import point for all tools

**Component 2: Tool Entry Points (8 tools)**
- Each tool calls `normalize_project_input()` immediately on project parameter
- Tools: set_project, get_project, query_entries, read_recent, append_entry, manage_docs, rotate_log, delete_project

**Component 3: Collision Detection (`tools/set_project.py`)**
- Before creating new project, check if canonical name already exists
- Prevent "my-project" when "my_project" exists (and vice versa)
- Emit clear error with suggestion

**Component 4: Lazy Migration (`storage/sqlite.py`, `state/manager.py`)**
- On project lookup, if raw name != canonical, update record
- No big-bang migration required
- Transparent to callers

**Component 5: Action Consolidation (`tools/manage_docs.py`)**
- New `create` action with `doc_type` parameter
- Internal routing to existing handlers
- Old action names kept as aliases with deprecation warning

**Component 6: Auto-Transform Hook (`doc_management/manager.py`)**
- After edit operations, check frontmatter for `auto_normalize_headers` / `auto_generate_toc`
- Only apply if explicitly opted-in
- Location: after line 475 (post-frontmatter pipeline)

### 3.3 Data Flow

**Project Name Flow:**
```
User Input → normalize_project_input() → Canonical Name → [DB/State/FS/Config]
```

**manage_docs Action Flow:**
```
User calls: create(doc_type="research", ...)
      │
      ▼
Action dispatcher recognizes "create"
      │
      ▼
Routes to _handle_special_document_creation()
      │
      ▼
Internal logic uses doc_type to select template
      │
      ▼
Creates document with correct naming/structure
```

**Legacy Alias Flow:**
```
User calls: create_research_doc(...)  [DEPRECATED]
      │
      ▼
Action dispatcher recognizes alias
      │
      ▼
Emits deprecation warning in response
      │
      ▼
Internally converts to: create(doc_type="research", ...)
```
<!-- ID: detailed_design -->
### 4.1 Workstream 1: Slugify Consolidation

#### 4.1.1 normalize_project_input() Function

**Location:** `utils/slug.py` (after line 35)

```python
def normalize_project_input(name: Optional[str]) -> Optional[str]:
    """Normalize project name input for consistent lookups.
    
    This is the SINGLE SOURCE OF TRUTH for project name normalization.
    All tools MUST call this function on project name parameters.
    
    Args:
        name: Raw project name from user input (may be None)
        
    Returns:
        Canonical slug (lowercase, underscores) or None if input was None/empty
        
    Examples:
        >>> normalize_project_input("My-Project")
        'my_project'
        >>> normalize_project_input("my_project")
        'my_project'
        >>> normalize_project_input("MY PROJECT")
        'my_project'
        >>> normalize_project_input(None)
        None
        >>> normalize_project_input("")
        None
    """
    if not name or not name.strip():
        return None
    return slugify_project_name(name)
```

#### 4.1.2 Tool Entry Point Modifications

**Pattern for each tool:**
```python
# At top of function, before any processing:
from utils.slug import normalize_project_input

# Normalize immediately
project = normalize_project_input(project)  # or 'name' for set_project
```

**Files to modify:**

| File | Parameter | Line (approx) | Change |
|------|-----------|---------------|--------|
| `tools/set_project.py` | `name` | ~300 | Already normalizes for paths; extend to DB storage |
| `tools/get_project.py` | `project` | ~395 | Add normalization before `state.get_project()` |
| `tools/query_entries.py` | `project` | ~1287 | Add normalization before `state.get_project()` |
| `tools/read_recent.py` | `project` | ~155 | Add normalization in project resolution |
| `tools/append_entry.py` | (implicit) | ~550 | Fix inline hyphen normalization |
| `tools/manage_docs.py` | `project` | ~1102 | Add normalization (may already exist) |
| `tools/rotate_log.py` | `project` | ~1367 | Add normalization |
| `tools/delete_project.py` | `name` | ~23 | Add normalization (unused import exists) |
| `tools/project_utils.py` | `project_name` | ~86 | Add normalization in `load_project_config()` |

#### 4.1.3 Collision Detection

**Location:** `tools/set_project.py`, in project creation flow

```python
async def _check_slug_collision(name: str, backend: StorageBackend) -> None:
    """Raise error if canonical slug already exists under different name."""
    canonical = normalize_project_input(name)
    existing_projects = await backend.list_projects()
    
    for proj in existing_projects:
        existing_canonical = normalize_project_input(proj.name)
        if existing_canonical == canonical and proj.name != name:
            raise ValueError(
                f"Project '{name}' would collide with existing project '{proj.name}' "
                f"(both normalize to '{canonical}'). Use the existing project name."
            )
```

**Call site:** Before `backend.upsert_project()` in set_project

#### 4.1.4 Lazy Migration Strategy

**Location:** `storage/sqlite.py` in `fetch_project()`

**Strategy:** When fetching a project, if the stored name differs from canonical form, update it.

```python
async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
    canonical = normalize_project_input(name)
    
    # Try exact match first
    row = await self._execute("SELECT ... WHERE name = ?", (name,))
    if row:
        return ProjectRecord(**row)
    
    # Try canonical match (lazy migration trigger)
    row = await self._execute("SELECT ... WHERE name = ?", (canonical,))
    if row:
        # Found under canonical name - return as-is
        return ProjectRecord(**row)
    
    # Try flexible match (find any name that canonicalizes to same slug)
    all_projects = await self._execute("SELECT name FROM scribe_projects")
    for proj_name in all_projects:
        if normalize_project_input(proj_name) == canonical:
            row = await self._execute("SELECT ... WHERE name = ?", (proj_name,))
            if row:
                # Optionally update to canonical form here
                return ProjectRecord(**row)
    
    return None
```

### 4.2 Workstream 2: manage_docs Simplification

#### 4.2.1 New Action Registry

**Location:** `tools/manage_docs.py`, replace `valid_actions` set

```python
# Primary actions (documented, recommended)
PRIMARY_ACTIONS = {
    "create",           # NEW: Unified creation with doc_type
    "replace_section",  # Section-based editing
    "apply_patch",      # Unified diff editing
    "replace_range",    # Line-based editing
    "replace_text",     # Find/replace
    "append",           # Add content
    "status_update",    # Checklist updates
}

# Deprecated aliases (emit warning, route to primary)
DEPRECATED_ALIASES = {
    "create_doc": ("create", {"doc_type": "custom"}),
    "create_research_doc": ("create", {"doc_type": "research"}),
    "create_bug_report": ("create", {"doc_type": "bug"}),
    "create_review_report": ("create", {"doc_type": "review"}),
    "create_agent_report_card": ("create", {"doc_type": "agent_card"}),
}

# Hidden actions (still work, but removed from docs)
HIDDEN_ACTIONS = {
    "normalize_headers",      # Use frontmatter opt-in instead
    "generate_toc",           # Use frontmatter opt-in instead
    "validate_crosslinks",    # Scrapped
    "list_sections",          # Use read_file(mode="scan_only")
    "list_checklist_items",   # Just read the file
    "search",                 # Use query_entries or read_file
    "batch",                  # Power user edge case
}

valid_actions = PRIMARY_ACTIONS | set(DEPRECATED_ALIASES.keys()) | HIDDEN_ACTIONS
```

#### 4.2.2 create Action with doc_type Routing

**Location:** `tools/manage_docs.py`, in action dispatcher

```python
if action == "create" or action in DEPRECATED_ALIASES:
    # Handle deprecation
    if action in DEPRECATED_ALIASES:
        primary_action, default_params = DEPRECATED_ALIASES[action]
        healing_messages.append(
            f"DEPRECATED: '{action}' is deprecated. "
            f"Use create(doc_type='{default_params['doc_type']}') instead."
        )
        # Apply defaults if not overridden
        if not metadata.get("doc_type"):
            metadata["doc_type"] = default_params["doc_type"]
        action = "create"
    
    # Route based on doc_type
    doc_type = metadata.get("doc_type", "custom")
    
    if doc_type == "research":
        return await _handle_research_doc_creation(...)
    elif doc_type == "bug":
        return await _handle_bug_report_creation(...)
    elif doc_type == "review":
        return await _handle_review_report_creation(...)
    elif doc_type == "agent_card":
        return await _handle_agent_card_creation(...)
    else:  # custom
        return await _handle_custom_doc_creation(...)
```

#### 4.2.3 Auto-Transform Hook (Opt-in via Frontmatter)

**Location:** `doc_management/manager.py`, after line 480 (post-frontmatter pipeline)

```python
# After updated_text is computed, before writing:

# Check for opt-in auto-transforms
frontmatter_data = original_parsed.frontmatter_data or {}

if frontmatter_data.get("auto_normalize_headers") and action not in {"normalize_headers", "generate_toc"}:
    updated_body = _normalize_headers_text(updated_body)
    frontmatter_extra["auto_normalized_headers"] = True

if frontmatter_data.get("auto_generate_toc") and action not in {"normalize_headers", "generate_toc"}:
    updated_body = _generate_toc_text(updated_body)
    frontmatter_extra["auto_generated_toc"] = True

# Recompute updated_text if transforms were applied
if frontmatter_extra.get("auto_normalized_headers") or frontmatter_extra.get("auto_generated_toc"):
    updated_text = _combine_frontmatter_and_body(original_parsed.frontmatter_data, updated_body)
```

#### 4.2.4 Deprecation Warning Format

```python
{
    "ok": True,
    "action": "create",
    "deprecated": "Action 'create_research_doc' is deprecated. Use create(doc_type='research') instead.",
    "path": "...",
    # ... rest of response
}
```
<!-- ID: directory_structure -->
**Files Modified by This Project:**

```
/home/austin/projects/MCP_SPINE/scribe_mcp/
├── utils/
│   └── slug.py                    # ADD: normalize_project_input()
├── tools/
│   ├── set_project.py             # ADD: collision detection, normalize for DB
│   ├── get_project.py             # ADD: normalize before lookup
│   ├── query_entries.py           # ADD: normalize project filter
│   ├── read_recent.py             # ADD: normalize project filter
│   ├── append_entry.py            # FIX: inline hyphen normalization
│   ├── manage_docs.py             # MAJOR: action consolidation, deprecation aliases
│   ├── rotate_log.py              # ADD: normalize project name
│   ├── delete_project.py          # ADD: normalize (fix unused import)
│   └── project_utils.py           # ADD: normalize in load_project_config()
├── storage/
│   └── sqlite.py                  # ADD: lazy migration in fetch_project()
├── state/
│   └── manager.py                 # ADD: normalize dict keys
├── doc_management/
│   └── manager.py                 # ADD: auto-transform hook (opt-in)
└── tests/
    ├── test_slugify_normalization.py   # NEW: normalization tests
    └── test_manage_docs_consolidation.py # NEW: action consolidation tests

**Documentation Updates (23 files):**
├── CRITICAL (must update):
│   ├── docs/Scribe_Usage.md
│   ├── CLAUDE.md
│   ├── config/CLAUDE.md
│   ├── .codex/skills/scribe-mcp-usage/references/manage_docs.md
│   ├── .codex/skills/scribe-mcp-usage/references/Scribe_Usage.md
│   └── .codex/skills/scribe-mcp-usage/SKILL.md
├── HIGH (agent definitions):
│   ├── AGENTS.md
│   ├── docs/guides/manage_docs_agent_guide.md
│   └── .codex/skills/.../sections/documentation_management.md
├── MEDIUM (agent instructions):
│   ├── .claude/agents/scribe-*.md (5 files)
│   ├── docs/guides/manage_docs_troubleshooting.md
│   ├── PROJECT_NAMING.md
│   └── README.md
└── LOW (supporting):
    └── Various .codex reference files, whitepapers
```
<!-- ID: data_storage -->
### 6.1 Database Changes

**No schema changes required.** The project uses lazy migration:

- Project names stored as-is (backwards compatible)
- Lookups normalize input before querying
- Optional: Update records to canonical form on access

### 6.2 State File Changes

**state.json structure unchanged.** Key normalization handled at application layer:

```python
# Before: state.projects["My-Project"]
# After: state.projects["my_project"] (normalized on access)
```

### 6.3 Migration Strategy

**Lazy Migration (Recommended):**
1. No upfront migration script
2. Projects normalized on first access
3. Collision detection prevents new collisions
4. Old data continues to work

**Why not big-bang migration:**
- 59 existing projects in database
- Some may have external references
- Risk of breaking existing workflows
- Lazy migration is transparent
<!-- ID: testing_strategy -->
### 7.1 Unit Tests

**Slugify Normalization (`tests/test_slugify_normalization.py`):**
```python
def test_normalize_project_input_variants():
    assert normalize_project_input("My-Project") == "my_project"
    assert normalize_project_input("my_project") == "my_project"
    assert normalize_project_input("MY PROJECT") == "my_project"
    assert normalize_project_input("My-Project Name") == "my_project_name"
    assert normalize_project_input(None) is None
    assert normalize_project_input("") is None

def test_collision_detection():
    # Create "my-project", then attempt "my_project" -> error
    pass

def test_lazy_migration():
    # Create project with raw name, fetch with canonical -> works
    pass
```

**manage_docs Consolidation (`tests/test_manage_docs_consolidation.py`):**
```python
def test_create_action_routing():
    # create(doc_type="research") routes correctly
    pass

def test_deprecated_alias_warning():
    # create_research_doc -> warning + works
    pass

def test_hidden_actions_still_work():
    # list_sections still works (just hidden from docs)
    pass
```

### 7.2 Integration Tests

**Cross-tool consistency:**
```python
def test_project_lookup_consistency():
    # set_project(name="My-Project")
    # get_project(project="my_project") -> same project
    # query_entries(project="MY PROJECT") -> same entries
```

### 7.3 Regression Tests

- All existing tests must pass unchanged
- No breaking changes to API signatures
- Deprecated actions must continue working

### 7.4 Manual QA Checklist

- [ ] Create project with hyphens, access with underscores
- [ ] Use deprecated create_research_doc, verify warning appears
- [ ] Add frontmatter auto_normalize_headers, verify headers normalized
- [ ] Attempt collision (my-project when my_project exists), verify error
<!-- ID: deployment_operations -->
### 8.1 Rollout Strategy

**Phase 1 (Slugify):** Low risk, can deploy incrementally
- Add normalize_project_input() first
- Add to tools one at a time
- Each change is backwards compatible

**Phase 2 (manage_docs):** Medium risk, deploy together
- All action changes in single commit
- Deprecation warnings enable gradual transition
- Old action names continue working

**Phase 3 (Docs):** No code risk
- Update documentation after code is stable
- Can be done incrementally

### 8.2 Rollback Plan

**If issues arise:**
1. Slugify changes are additive - can disable normalization calls
2. manage_docs aliases are backwards compatible - old code still works
3. Auto-transform is opt-in - no action needed to disable

### 8.3 Monitoring

**Success indicators:**
- Reduced "project not found" errors in logs
- Reduced manage_docs action errors
- Deprecation warnings appearing (shows adoption path)

**Watch for:**
- Collision detection false positives
- Lazy migration causing unexpected behavior
- Auto-transform corrupting documents (should be impossible with opt-in)
<!-- ID: open_questions -->
| Item | Owner | Status | Decision |
|------|-------|--------|----------|
| Display names: Store pretty name separately? | Architect | RESOLVED | No - use canonical everywhere, simplify |
| Alias deprecation timeline | Product | OPEN | Suggest: 2 release cycles with warnings |
| search action destination | Architect | RESOLVED | Use query_entries or read_file, don't create new tool |
| Auto-transform CLI override flag | Architect | DEFERRED | Not needed for MVP; frontmatter is sufficient |
| Minimum header count for auto-TOC | Architect | DEFERRED | Not needed for MVP; user controls via frontmatter |
<!-- ID: references_appendix -->
| Document | Key Findings |
|----------|--------------|
| RESEARCH_slugify_input_boundaries_20260119.md | 6 tools don't normalize, load_project_config gap |
| RESEARCH_slugify_storage_migration_20260119.md | DB stores raw, filesystem uses slugified, collision risk |
| RESEARCH_manage_docs_action_taxonomy_20260119.md | 18 actions mapped, 4 categories, consolidation opportunities |
| RESEARCH_manage_docs_error_healing_20260119.md | BulletproofParameterCorrector exists, can extend |
| RESEARCH_auto_transform_viability_20260119.md | DO NOT auto-enable; opt-in via frontmatter recommended |

---
*Architecture Guide v1.0 - Agent UX Overhaul*
*Generated: 2026-01-19 by ArchitectAgent*
