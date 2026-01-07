---
id: scribe_project_sitrep_hash_comparison-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_project_sitrep_hash_comparison"
doc_type: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-06'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_project_sitrep_hash_comparison
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-06 10:33:43 UTC

> Architecture guide for scribe_project_sitrep_hash_comparison.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

**Context:** BUG-001 in set_project/get_project/list_projects tools incorrectly detect project state using `entry_count == 0` logic, which fails after log rotation when PROGRESS_LOG.md becomes empty but the project's architectural documents remain unchanged.

**Current Broken Logic (set_project.py:459):**
```python
is_new = not progress_log_path.exists() or entry_count == 0
```

**The Bug:**
After rotating logs via `rotate_log()`, the progress log becomes empty (`entry_count == 0`), but `set_project` incorrectly displays "NEW PROJECT CREATED" SITREP instead of recognizing it as an existing project.

**Root Cause:**
- Tools ignore existing hash comparison infrastructure in ProjectRegistry
- ProjectRegistry.record_doc_update() tracks baseline_hashes and current_hashes with per-document modification flags
- Tools call ProjectRegistry.get_project() but never read `meta.docs.flags`
- Instead use primitive entry_count logic vulnerable to rotation

**User Requirements:**

1. **Four-State Detection (with Edge Case):**
   - **NEW**: No baseline hashes exist AND no progress log entries exist
   - **EXISTING (Edge Case)**: No baseline hashes exist (legacy project) BUT progress log has entries (count > 0)
   - **UNCHANGED**: Baseline hashes exist AND baseline_hashes == current_hashes
   - **MODIFIED**: Baseline hashes exist AND baseline_hashes != current_hashes

2. **SITREP Content Requirements:**
   - Display 2-5 recent progress log entries (NO truncation of messages)
   - Show total entry count
   - List number of managed docs (base 4 + custom docs)
   - Show which docs exist with modification flags (✏️ for modified)
   - Display project created date and current timestamp
   - Format must be token-efficient (~150-200 tokens per project for readable format)

3. **Output Format Requirements:**
   - **Readable Format**: Compact list box using Rich UI style, shows recent entries inline
   - **JSON Format**: Paginated structured data with full metadata, prevents token explosion

4. **Data Architecture Fix:**
   - `docs_json` column exists in database but NOT in ProjectRecord model (integration gap)
   - Must add `docs_json` field to ProjectRecord to expose custom manage_docs documents
   - ProjectRegistry must integrate baseline/current hash comparison with tools

5. **Infrastructure Reuse (MANDATORY):**
   - Use `backend.count_entries(project, filters)` for entry counting (storage/sqlite.py:505-555)
   - Use `create_pagination_info()` for pagination (utils/estimator.py:42-57)
   - Use `format_readable_log_entries()` for entry display (utils/response.py:604-790)
   - Use `_read_recent_progress_entries()` for recent entries (tools/get_project.py:70-127)
   - Base 4 docs hardcoded in set_project.py:250-255

**Goals:**
- Fix BUG-001 by replacing entry_count logic with hash comparison
- Enable SITREP to show accurate project state (NEW/EXISTING/UNCHANGED/MODIFIED)
- Display per-document modification status in readable and JSON formats
- Handle edge case for legacy projects (no baseline but has entries)
- Maintain backward compatibility with existing SITREP formatters

**Constraints:**
- Must NOT create new infrastructure - reuse existing patterns
- Hash tracking only works for documents modified via manage_docs
- Cannot break abstraction layer (ProjectRegistry uses direct sqlite3, out of scope)
- Must preserve token efficiency for list_projects (target <200 tokens per project)
- Edge case detection requires combining hash comparison with entry counting

**Success Criteria:**
- After log rotation, set_project shows EXISTING/UNCHANGED instead of NEW
- Modified documents show visual indicators (✏️) in SITREP
- Legacy projects (pre-hash-tracking) correctly identified as EXISTING
- All three tools (set/get/list) use consistent three-state detection
- Integration tests pass for all four states (NEW/EXISTING/UNCHANGED/MODIFIED)
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
- Atomic document updates- Jinja2 templates with inheritance
- **Non-Functional Requirements:**
- Backwards-compatible file layout- Sandboxed template rendering
- **Assumptions:**
- Filesystem read/write access- Python runtime available
- **Risks & Mitigations:**
- User edits outside manage_docs- Template misuse causing errors


---
## 3. Architecture Overview
<!-- ID: architecture_overview -->
## System Overview & Architecture

**High-Level Architecture:**

The SITREP system determines project state through **hash-based comparison** instead of entry counting. ProjectRegistry maintains baseline and current SHA256 hashes for all managed documents, computing per-document modification flags. Tools consume these flags to display accurate project state.

### Core Components

**1. ProjectRegistry (shared/project_registry.py)**
- **Role**: Central hash tracking and state computation
- **Key Methods**:
  - `record_doc_update(before_hash, after_hash)` - Called by manage_docs after every document edit
  - `get_project(name)` - Returns ProjectInfo with meta.docs.flags
- **Storage**: scribe_projects.meta JSON field
  - `meta.docs.baseline_hashes` - Set once on first edit per document
  - `meta.docs.current_hashes` - Updated on every edit
  - `meta.docs.flags` - Per-document modification flags (e.g., `architecture_modified: true`)

**2. ProjectRecord Model (storage/models.py)**
- **Current**: Has name, root, status, created_at, updated_at
- **Fix Required**: Add `docs_json: Optional[str]` field
- **Purpose**: Expose custom documents created by manage_docs (research, bug reports, reviews)
- **Integration**: Parse JSON string to dict in getter method

**3. Project Tools (tools/)**
- **set_project.py**: Creates/activates projects, displays initial SITREP
- **get_project.py**: Returns current project context with detailed SITREP
- **list_projects.py**: Shows all projects with compact SITREP per project

**4. Existing Infrastructure (REUSED)**
- **Entry Counting**: `backend.count_entries(project, filters)` - SQL COUNT(*) query
- **Pagination**: `create_pagination_info(page, page_size, total)` - PaginationInfo dataclass
- **Recent Entries**: `_read_recent_progress_entries(log_path, limit=5)` - File parser
- **Display Format**: `format_readable_log_entries(entries)` - Rich UI renderer

### Four-State Detection Logic

**Algorithm (Deterministic State Machine):**

```python
def detect_project_state(registry_info: Optional[ProjectInfo], entry_count: int) -> tuple[str, dict]:
    """
    Returns: (state, metadata)
    States: "NEW" | "EXISTING_LEGACY" | "UNCHANGED" | "MODIFIED"
    """
    # State 1: NEW PROJECT
    if not registry_info:
        return ("NEW", {"reason": "no_database_row"})
    
    baseline_hashes = registry_info.meta.get("docs", {}).get("baseline_hashes", {})
    
    if not baseline_hashes:
        # Edge case: Legacy project detection
        if entry_count > 0:
            return ("EXISTING_LEGACY", {
                "reason": "no_baseline_but_has_entries",
                "entry_count": entry_count
            })
        else:
            return ("NEW", {"reason": "no_baseline_no_entries"})
    
    # State 3 & 4: Hash comparison for projects with baseline
    flags = registry_info.meta.get("docs", {}).get("flags", {})
    core_docs = ["architecture", "phase_plan", "checklist"]
    
    modified_docs = [doc for doc in core_docs if flags.get(f"{doc}_modified", False)]
    
    if modified_docs:
        return ("MODIFIED", {
            "modified_docs": modified_docs,
            "baseline_hashes": baseline_hashes,
            "current_hashes": registry_info.meta.get("docs", {}).get("current_hashes", {})
        })
    else:
        return ("UNCHANGED", {
            "verified_docs": core_docs,
            "baseline_matches_current": True
        })
```

**State Transitions:**

```
NEW (no baseline, no entries)
    ↓ (first append_entry call)
EXISTING_LEGACY (no baseline, has entries)
    ↓ (first manage_docs call)
UNCHANGED (baseline == current)
    ↓ (manage_docs with content change)
MODIFIED (baseline != current)
    ↓ (optional: baseline reset)
UNCHANGED
```

### Data Flow

**Write Path (Document Updates):**
```
User → manage_docs → compute SHA256(before) and SHA256(after)
                   → ProjectRegistry.record_doc_update()
                   → Update meta.docs in scribe_projects table
                   → Recompute flags (baseline != current)
```

**Read Path (SITREP Generation):**
```
User → set_project/get_project/list_projects
    → ProjectRegistry.get_project(name)
    → backend.count_entries(project) for edge case
    → detect_project_state(registry_info, entry_count)
    → format_sitrep_[new|existing](state, metadata)
    → Return formatted SITREP
```

### Integration Points

**ProjectRegistry ↔ Database:**
- Registry uses direct sqlite3.connect() (technical debt, out of scope)
- Stores JSON in scribe_projects.meta column
- Retrieves via _row_to_project_info() helper

**Tools ↔ ProjectRegistry:**
- Tools call `_PROJECT_REGISTRY.get_project(name)` (singleton instance)
- Consume ProjectInfo.meta.docs.flags for modification status
- NEW: Tools must also call `backend.count_entries()` for edge case detection

**Tools ↔ Storage Backend:**
- Tools call `backend.count_entries(project, filters)` for entry counting
- Tools call `backend.fetch_recent_entries_paginated()` for pagination
- Storage abstraction layer (SQLite default, PostgreSQL optional)

**SITREP Formatters:**
- Existing formatters in utils/response.py
- NEW: Pass `state` and `modified_docs` list to formatters
- Formatters render visual indicators (✏️ for modified, ✓ for unchanged)

### Backward Compatibility

**Legacy Projects (Pre-Hash-Tracking):**
- Projects created before hash infrastructure have no baseline_hashes
- Edge case detection: If entry_count > 0, mark as EXISTING_LEGACY
- State transitions to UNCHANGED after first manage_docs call sets baseline

**Existing SITREP Consumers:**
- All format changes are additive (new fields, not removed)
- JSON format adds `state`, `modified_docs`, `doc_flags` fields
- Readable format adds visual indicators without breaking layout

**No Breaking Changes:**
- set_project still returns same structure, enhanced content
- get_project still returns same structure, enhanced content
- list_projects still returns same structure, per-project state added
<!-- ID: detailed_design -->
## Component Design

### 1. ProjectRecord Model Enhancement (storage/models.py)

**Current Model (Lines 9-15):**
```python
@dataclass
class ProjectRecord:
    name: str
    root: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**REQUIRED Enhancement:**
```python
@dataclass
class ProjectRecord:
    name: str
    root: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    docs_json: Optional[str] = None  # NEW FIELD
    
    @property
    def docs_dict(self) -> Dict[str, str]:
        """Parse docs_json to dictionary for easy access."""
        if not self.docs_json:
            return {}
        try:
            return json.loads(self.docs_json)
        except json.JSONDecodeError:
            return {}
```

**Integration Required:**
- Update `storage/sqlite.py:fetch_project()` to SELECT docs_json column (already exists in DB at line 659)
- Update row parsing to include docs_json in ProjectRecord construction
- No migration required - column already exists, just needs exposure

**Purpose:**
- Expose custom documents created via manage_docs (research reports, bug reports, review reports)
- Enable SITREP to show "4 base docs + 3 custom docs" counts
- Tools can iterate over `project.docs_dict` for complete document inventory

---

### 2. set_project.py Fixes (BUG-001 Resolution)

**File:** `tools/set_project.py`

**CRITICAL Fix - Line 459:**

**BEFORE (BROKEN):**
```python
# Line 459 - THE BUG
is_new = not progress_log_path.exists() or entry_count == 0

# Lines 461-489 - Conditional branches based on is_new
if is_new:
    result = format_project_sitrep_new(...)
else:
    result = format_project_sitrep_existing(...)
```

**AFTER (FIXED):**
```python
# NEW: Hash-based state detection
registry_info = _PROJECT_REGISTRY.get_project(name)
entry_count = await backend.count_entries(project, filters=None) if registry_info else 0

state, state_meta = detect_project_state(registry_info, entry_count)

# Enhanced conditional with four states
if state == "NEW":
    result = format_project_sitrep_new(
        name=name,
        root=root,
        docs_dir=docs_dir,
        status="planning",
        doc_inventory=_build_doc_inventory(docs_dir),
        state="new"
    )
elif state == "EXISTING_LEGACY":
    # Legacy project (no baseline but has entries)
    result = format_project_sitrep_existing(
        name=name,
        status=registry_info.status,
        doc_inventory=_build_doc_inventory(docs_dir),
        activity_summary={"total_entries": entry_count, "last_entry_at": registry_info.last_entry_at},
        state="legacy",
        warning="Project created before hash tracking - will transition to UNCHANGED after first manage_docs edit"
    )
elif state == "UNCHANGED":
    result = format_project_sitrep_existing(
        name=name,
        status=registry_info.status,
        doc_inventory=_build_doc_inventory(docs_dir, flags=state_meta.get("doc_flags", {})),
        activity_summary=_build_activity_summary(registry_info),
        state="unchanged",
        verified_docs=state_meta.get("verified_docs", [])
    )
else:  # MODIFIED
    result = format_project_sitrep_existing(
        name=name,
        status=registry_info.status,
        doc_inventory=_build_doc_inventory(docs_dir, flags=state_meta.get("doc_flags", {})),
        activity_summary=_build_activity_summary(registry_info),
        state="modified",
        modified_docs=state_meta.get("modified_docs", []),
        baseline_hashes=state_meta.get("baseline_hashes", {}),
        current_hashes=state_meta.get("current_hashes", {})
    )
```

**Helper Functions (NEW):**

```python
def detect_project_state(
    registry_info: Optional[ProjectInfo], 
    entry_count: int
) -> tuple[str, dict]:
    """
    Four-state detection logic.
    Returns: (state, metadata)
    """
    # Implementation from architecture_overview section
    # States: NEW | EXISTING_LEGACY | UNCHANGED | MODIFIED
    ...

def _build_doc_inventory(
    docs_dir: str, 
    flags: Optional[Dict[str, bool]] = None
) -> Dict[str, Any]:
    """
    Build document inventory with modification flags.
    
    Returns:
        {
            "architecture": {"exists": True, "lines": 250, "modified": False},
            "phase_plan": {"exists": True, "lines": 180, "modified": True},
            ...
        }
    """
    base_docs = ["architecture", "phase_plan", "checklist", "progress_log"]
    inventory = {}
    flags = flags or {}
    
    for doc_key in base_docs:
        doc_path = os.path.join(docs_dir, DOC_FILENAMES[doc_key])
        inventory[doc_key] = {
            "exists": os.path.exists(doc_path),
            "lines": _count_lines(doc_path) if os.path.exists(doc_path) else 0,
            "modified": flags.get(f"{doc_key}_modified", False)
        }
    
    return inventory

def _build_activity_summary(registry_info: ProjectInfo) -> Dict[str, Any]:
    """Extract activity metrics from registry."""
    return {
        "total_entries": registry_info.total_entries,
        "last_entry_at": registry_info.last_entry_at,
        "last_access_at": registry_info.last_access_at,
        "status": registry_info.status
    }
```

**Files Modified:**
- `tools/set_project.py` - Lines 459-502 (BUG-001 fix, state detection)
- No changes to `utils/response.py` formatters (additive parameters only)

---

### 3. get_project.py Enhancement

**File:** `tools/get_project.py`

**Current Implementation (Lines 315-321):**
```python
# Calls registry but ignores hash data
registry_info = _PROJECT_REGISTRY.get_project(current_name)
activity_summary = {
    "total_entries": registry_info.total_entries,
    "last_entry_at": registry_info.last_entry_at,
    "status": registry_info.status
}
# IGNORES: registry_info.meta.docs.flags
```

**ENHANCED Implementation:**
```python
# NEW: Include hash-based state detection
registry_info = _PROJECT_REGISTRY.get_project(current_name)
entry_count = await backend.count_entries(project, filters=None)

state, state_meta = detect_project_state(registry_info, entry_count)

# Enhanced activity summary with state
activity_summary = {
    "total_entries": registry_info.total_entries,
    "last_entry_at": registry_info.last_entry_at,
    "last_access_at": registry_info.last_access_at,
    "status": registry_info.status,
    "state": state,  # NEW
    "doc_flags": registry_info.meta.get("docs", {}).get("flags", {})  # NEW
}

# Add state-specific metadata
if state == "MODIFIED":
    activity_summary["modified_docs"] = state_meta.get("modified_docs", [])
    activity_summary["baseline_hashes"] = state_meta.get("baseline_hashes", {})
    activity_summary["current_hashes"] = state_meta.get("current_hashes", {})
elif state == "UNCHANGED":
    activity_summary["verified_docs"] = state_meta.get("verified_docs", [])
```

**SITREP Display Enhancement (Readable Format):**

Add recent entries display using EXISTING helper:

```python
# Use existing helper from lines 70-127
recent_entries = await _read_recent_progress_entries(
    progress_log_path=str(progress_log),
    limit=5  # Show 2-5 recent entries (user requirement)
)

# Pass to formatter (utils/response.py already handles this)
result = format_project_context(
    name=current_name,
    root=project.root,
    docs_dir=docs_dir,
    activity_summary=activity_summary,
    recent_entries=recent_entries,  # NEW
    doc_inventory=_build_doc_inventory(docs_dir, flags=activity_summary.get("doc_flags")),
    state=state
)
```

**JSON Format Enhancement:**

```python
if format == "json":
    return {
        "project": current_name,
        "root": project.root,
        "status": project.status,
        "state": state,  # NEW
        "activity": activity_summary,
        "documents": _build_doc_inventory(docs_dir, flags=activity_summary.get("doc_flags")),
        "recent_entries": recent_entries[:5],  # NEW - limit to 5 for token efficiency
        "modified_docs": activity_summary.get("modified_docs", []) if state == "MODIFIED" else [],
        "timestamps": {
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "last_entry_at": activity_summary.get("last_entry_at"),
            "last_access_at": activity_summary.get("last_access_at")
        }
    }
```

**Files Modified:**
- `tools/get_project.py` - Lines 315-350 (state detection, recent entries, enhanced output)

---

### 4. list_projects.py Enhancement

**File:** `tools/list_projects.py`

**Current Implementation (Lines 84-106):**
```python
# Lines 89, 97, 105 - Hardcoded False with TODO
result["architecture"] = {
    "exists": True,
    "lines": default_formatter._get_doc_line_count(arch_file),
    "modified": False  # TODO: Check against registry hashes if needed
}
```

**ENHANCED Implementation:**

```python
# NEW: Read registry info for each project
for project_name in project_names:
    project = await backend.fetch_project(project_name)
    registry_info = _PROJECT_REGISTRY.get_project(project_name)
    entry_count = await backend.count_entries(project, filters=None) if project else 0
    
    state, state_meta = detect_project_state(registry_info, entry_count)
    
    # Build enhanced doc inventory with actual modification flags
    doc_flags = registry_info.meta.get("docs", {}).get("flags", {}) if registry_info else {}
    
    result = {
        "name": project_name,
        "root": project.root,
        "status": project.status,
        "state": state,  # NEW
        "documents": {
            "architecture": {
                "exists": arch_exists,
                "lines": _count_lines(arch_path),
                "modified": doc_flags.get("architecture_modified", False)  # FIXED
            },
            "phase_plan": {
                "exists": phase_exists,
                "lines": _count_lines(phase_path),
                "modified": doc_flags.get("phase_plan_modified", False)  # FIXED
            },
            "checklist": {
                "exists": check_exists,
                "lines": _count_lines(check_path),
                "modified": doc_flags.get("checklist_modified", False)  # FIXED
            },
            "progress_log": {
                "exists": log_exists,
                "lines": entry_count,  # Use DB count, not file parsing
                "modified": False  # Progress log not tracked for modification
            }
        },
        "activity": {
            "total_entries": entry_count,
            "last_entry_at": registry_info.last_entry_at if registry_info else None,
            "created_at": project.created_at.isoformat() if project.created_at else None
        },
        "modified_docs": state_meta.get("modified_docs", []) if state == "MODIFIED" else []
    }
    
    projects.append(result)
```

**Pagination (JSON Format):**

```python
if format == "json":
    # Use existing pagination infrastructure
    total_count = len(all_projects)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated = all_projects[start_idx:end_idx]
    
    pagination = create_pagination_info(page, page_size, total_count)
    
    return {
        "projects": paginated,
        "pagination": pagination.to_dict(),
        "summary": {
            "total_projects": total_count,
            "states": {
                "new": sum(1 for p in all_projects if p["state"] == "NEW"),
                "existing_legacy": sum(1 for p in all_projects if p["state"] == "EXISTING_LEGACY"),
                "unchanged": sum(1 for p in all_projects if p["state"] == "UNCHANGED"),
                "modified": sum(1 for p in all_projects if p["state"] == "MODIFIED")
            }
        }
    }
```

**Readable Format (Compact):**

```python
if format == "readable":
    # Token-efficient list box per project
    lines = []
    for proj in paginated:
        state_icon = {
            "NEW": "🆕",
            "EXISTING_LEGACY": "📦",
            "UNCHANGED": "✅",
            "MODIFIED": "✏️"
        }[proj["state"]]
        
        modified_indicator = ""
        if proj["state"] == "MODIFIED":
            modified_indicator = f" (modified: {', '.join(proj['modified_docs'])})"
        
        lines.append(
            f"{state_icon} {proj['name']} - {proj['status']}{modified_indicator}\n"
            f"   {proj['activity']['total_entries']} entries | "
            f"Last: {proj['activity']['last_entry_at'] or 'never'}"
        )
    
    return format_compact_list(
        title=f"Projects (page {page} of {pagination.total_pages})",
        items=lines,
        footer=f"Total: {total_count} projects"
    )
```

**Files Modified:**
- `tools/list_projects.py` - Lines 84-250 (state detection per project, enhanced output)

---

### 5. SITREP Output Format Specifications

**Readable Format Design (Target: ~150-200 tokens per project):**

**NEW Project:**
```
╔══════════════════════════════════════════════════════════╗
║ ✨ NEW PROJECT CREATED: project_name                    ║
╚══════════════════════════════════════════════════════════╝

📂 Location: /path/to/root
  Dev Plan: .scribe/docs/dev_plans/project_name/

📄 Documents Created:
  ✓ ARCHITECTURE_GUIDE.md (template, 112 lines)
  ✓ PHASE_PLAN.md (template, 74 lines)
  ✓ CHECKLIST.md (template, 29 lines)
  ✓ PROGRESS_LOG.md (empty, ready for entries)

🎯 Status: planning (new project)
💡 Next: Start with research or architecture phase
```

**EXISTING - UNCHANGED Project:**
```
╔══════════════════════════════════════════════════════════╗
║ 📌 PROJECT ACTIVATED: project_name                       ║
╚══════════════════════════════════════════════════════════╝

📂 Location: /path/to/root
🎯 Status: in_progress (no document changes since baseline)
📊 Activity: 47 entries | Last: 2026-01-06 12:30:15 UTC

📄 Documents: All up-to-date
  ✓ ARCHITECTURE_GUIDE.md (250 lines)
  ✓ PHASE_PLAN.md (180 lines)
  ✓ CHECKLIST.md (95 lines)
  ✓ PROGRESS_LOG.md (47 entries)

📝 Recent Entries:
  [✅] 12:30 | CoderAgent | Phase 2 implementation complete
  [ℹ️] 12:15 | CoderAgent | Updated authentication flow
  [✅] 11:45 | ArchitectAgent | Architecture review passed
```

**EXISTING - MODIFIED Project:**
```
╔══════════════════════════════════════════════════════════╗
║ 📌 PROJECT ACTIVATED: project_name                       ║
╚══════════════════════════════════════════════════════════╝

📂 Location: /path/to/root
🎯 Status: in_progress (documents modified since baseline)
📊 Activity: 47 entries | Last: 2026-01-06 12:30:15 UTC

⚠️ Modified Documents:
  ✏️ ARCHITECTURE_GUIDE.md (baseline: abc123..., current: def456...)
  ✏️ PHASE_PLAN.md (modified)

✓ Unchanged Documents:
  ✓ CHECKLIST.md

📝 Recent Entries:
  [✅] 12:30 | ArchitectAgent | Updated system architecture
  [✏️] 12:15 | ArchitectAgent | Revised phase 3 requirements
  [ℹ️] 11:45 | ResearchAgent | Completed infrastructure research
```

**JSON Format Design (Paginated):**

```json
{
  "project": "project_name",
  "root": "/path/to/root",
  "status": "in_progress",
  "state": "MODIFIED",
  "activity": {
    "total_entries": 47,
    "last_entry_at": "2026-01-06T12:30:15Z",
    "last_access_at": "2026-01-06T13:00:00Z"
  },
  "documents": {
    "architecture": {
      "exists": true,
      "lines": 250,
      "modified": true,
      "baseline_hash": "abc123...",
      "current_hash": "def456..."
    },
    "phase_plan": {
      "exists": true,
      "lines": 180,
      "modified": true
    },
    "checklist": {
      "exists": true,
      "lines": 95,
      "modified": false
    },
    "progress_log": {
      "exists": true,
      "entries": 47,
      "modified": false
    }
  },
  "recent_entries": [
    {
      "emoji": "✅",
      "timestamp": "2026-01-06T12:30:15Z",
      "agent": "ArchitectAgent",
      "message": "Updated system architecture"
    }
  ],
  "modified_docs": ["architecture", "phase_plan"],
  "timestamps": {
    "created_at": "2026-01-03T10:00:00Z",
    "last_entry_at": "2026-01-06T12:30:15Z",
    "last_access_at": "2026-01-06T13:00:00Z"
  }
}
```

---

### 6. Testing Strategy

**Unit Tests (Per Component):**

**test_project_record_enhancement.py:**
- Test docs_json field exposure in ProjectRecord
- Test docs_dict property with valid/invalid JSON
- Test fetch_project includes docs_json

**test_detect_project_state.py:**
- Test NEW state (no registry_info)
- Test NEW state (registry exists but no baseline, no entries)
- Test EXISTING_LEGACY state (no baseline but entry_count > 0)
- Test UNCHANGED state (baseline == current, all flags False)
- Test MODIFIED state (baseline != current, at least one flag True)

**test_set_project_bug_fix.py:**
- Test log rotation scenario (entry_count == 0 but baseline exists → UNCHANGED not NEW)
- Test new project creation (no registry → NEW)
- Test legacy project activation (no baseline but has entries → EXISTING_LEGACY)
- Test modified project activation (baseline != current → MODIFIED)

**test_get_project_sitrep.py:**
- Test recent entries display (2-5 entries, no truncation)
- Test doc inventory with modification flags
- Test JSON format includes all required fields
- Test readable format rendering

**test_list_projects_sitrep.py:**
- Test per-project state detection
- Test pagination (50 projects, page_size=10)
- Test modification flags no longer hardcoded False
- Test readable format token efficiency (<200 per project)

**Integration Tests:**

**test_full_sitrep_lifecycle.py:**
- Create project → verify NEW state
- Add entries → verify transitions to EXISTING_LEGACY (if no manage_docs yet)
- Call manage_docs → verify transitions to UNCHANGED
- Edit doc via manage_docs → verify transitions to MODIFIED
- Rotate log → verify remains UNCHANGED (not NEW) - **PRIMARY BUG FIX VALIDATION**

**Performance Tests:**
- list_projects with 100 projects (ensure <2s response)
- get_project with 1000 entries (ensure pagination works)

**Success Criteria:**
- All 8-10 unit tests per component pass
- Integration test validates BUG-001 fix (rotation doesn't mark as NEW)
- Token count for list_projects readable format <200 per project
- No breaking changes to existing API contracts
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/scribe_project_sitrep_hash_comparison
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.


---
## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown', 'SQLite mirror']
- **Indexes & Performance:** FTS for sections
- **Migrations:** Sequential migrations tracked in storage layer


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Unit Tests:** Template rendering + doc ops
- **Integration Tests:** manage_docs tool exercises real files
- **Manual QA:** Project review after each release
- **Observability:** Structured logging via doc_updates log


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md- ARCHITECTURE_GUIDE.md
Generated via generate_doc_templates.


---