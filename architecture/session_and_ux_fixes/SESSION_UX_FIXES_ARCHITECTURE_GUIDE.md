---
id: manage_docs_agent_ux-session-ux-fixes-architecture-guide
title: 'Architecture Guide: Session Isolation & UX Fixes'
doc_name: SESSION_UX_FIXES_ARCHITECTURE_GUIDE
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-20'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Architecture Guide: Session Isolation & UX Fixes

**Project:** manage_docs_agent_ux  
**Sub-Plan:** session_and_ux_fixes  
**Created:** 2026-01-20  
**Status:** Design Phase  
**Architect:** ArchitectAgent

---

<!-- ID: problem_statement -->
## Problem Statement

**Context:** Multiple critical bugs and UX issues exist in the Scribe MCP session management and tool API surface that prevent reliable multi-project concurrency and create agent confusion.

**Research Foundation:**
- RESEARCH_SESSION_ISOLATION_BUG_20260119.md - Session key derivation mismatch
- RESEARCH_CUSTOM_DOC_NAMING_BUG_20260119.md - Parameter precedence bug
- RESEARCH_MULTI_PROJECT_CONCURRENCY_20260119.md - Missing project parameters
- RESEARCH_INDEX_FRONTMATTER_GAPS_20260120.md - Index update asymmetry

**Goals:**
1. Unify session ID system to prevent project resolution drift
2. Enable explicit multi-project tool usage via project parameters
3. Fix custom document naming to respect explicit user intent
4. Ensure index files update on ALL doc changes, not just creation
5. Clean up backup file pollution in research directories

**Success Criteria:**
- Session keys derived consistently across all tools (set_project, append_entry, etc.)
- All tools support explicit `project` parameter for cross-project operations
- Custom doc creation respects `doc_name` parameter over metadata fallbacks
- Index files (INDEX.md, REVIEW_INDEX.md, etc.) update on edits, not just creation
- Inflight/preflight backups stored in dedicated `.scribe/backups/` directory

---

<!-- ID: system_overview -->
## System Overview

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  MCP Request Layer                       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│          ExecutionContext (contextvars)                  │
│  • session_id (UUID - changes per request)               │
│  • stable_session_id (stable per session)                │
│  • project (optional explicit override)                  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│      NEW: get_canonical_session_key()                    │
│  Unified session key resolution function                 │
│  Returns: stable_session_id OR session_id (fallback)     │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ set_project  │   │ append_entry │
│ (session     │   │ (logging)    │
│  binding)    │   │              │
└──────┬───────┘   └───────┬──────┘
       │                   │
       └───────┬───────────┘
               ▼
┌─────────────────────────────────────────────────────────┐
│        StorageBackend (SQLite/Postgres)                  │
│  • set_session_project(session_key, project_name)        │
│  • get_session_project(session_key) -> project_name      │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Single Source of Truth for Session Keys**: One canonical function (`get_canonical_session_key()`) used everywhere
2. **Explicit > Implicit**: Tools accept explicit `project` parameter, always preferred over session/global state
3. **Fail Loud, Not Silent**: Remove silent global fallbacks, replace with explicit errors when context missing
4. **Parameter Precedence Correctness**: Function parameters always take precedence over metadata dictionary values
5. **Complete Event Coverage**: Index updates triggered on ALL document changes, not just creation

---

<!-- ID: component_design -->
## Component Design

### Component 1: Unified Session Key Resolution

**New File:** `shared/session_utils.py`

**Purpose:** Provide single canonical function for deriving session key from ExecutionContext

**Public API:**
```python
def get_canonical_session_key(exec_context: Optional[ExecutionContext]) -> Optional[str]:
    """Return THE canonical session key - stable_session_id always preferred.
    
    Args:
        exec_context: ExecutionContext with session_id and/or stable_session_id
        
    Returns:
        str: stable_session_id if available, else session_id, else None
        
    Design:
        - stable_session_id is DETERMINISTIC (same across MCP session)
        - session_id is EPHEMERAL (UUID per request)
        - Always prefer stable over ephemeral for project binding
    """
    if not exec_context:
        return None
    return exec_context.stable_session_id or exec_context.session_id
```

**Integration Points:**
- `tools/set_project.py` line 513 → Replace inline logic with function call
- `shared/logging_utils.py` line 91 → Replace inline logic with function call
- Any future tools that need session key resolution

**Verification:**
- Unit tests: Different ExecutionContext combinations (stable only, session only, both, neither)
- Integration test: set_project() followed by append_entry() must resolve to same session key

---

### Component 2: Explicit Project Parameters for Tools

**Modified Files:**
- `tools/append_entry.py`
- `tools/read_file.py`
- `tools/generate_doc_templates.py`

**Purpose:** Enable cross-project tool operations without relying on session context

**Design Pattern (Applied to All 3 Tools):**
```python
# Before (append_entry.py example):
async def append_entry(
    message: str = "",
    status: str = "info",
    agent: str = "",
    meta: Optional[Dict[str, Any]] = None,
    ...
) -> Dict[str, Any]:
    # No way to specify project explicitly!
    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=server_module,
        # Relies entirely on ExecutionContext or global state
    )

# After:
async def append_entry(
    message: str = "",
    project: Optional[str] = None,  # NEW: Explicit project override
    status: str = "info",
    agent: str = "",
    meta: Optional[Dict[str, Any]] = None,
    ...
) -> Dict[str, Any]:
    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=server_module,
        explicit_project=project,  # Pass through explicit override
    )
```

**Updated Tools:**

1. **append_entry.py**
   - Add `project: Optional[str] = None` parameter
   - Pass to `resolve_logging_context(explicit_project=project)`
   - Enables: `append_entry(message="test", project="other_project")`

2. **read_file.py**
   - Add `project: Optional[str] = None` parameter
   - Use explicit project for path resolution if provided
   - Enables: `read_file(path="file.py", project="other_project")`

3. **generate_doc_templates.py**
   - Add `project: Optional[str] = None` parameter (currently has `project_name` but different semantics)
   - Clarify that `project` is for WHERE to generate, `project_name` is WHAT to name the project
   - Current API is confusing - fix parameter naming

**Precedence Rules (Applied Consistently):**
```
1. Explicit `project` parameter (highest priority)
2. ExecutionContext session binding (via get_session_project)
3. ExecutionContext project field
4. Global state file (lowest priority, only if require_project=False)
5. Error if require_project=True and no project resolved
```

**Verification:**
- Cross-project logging: Agent in project A can log to project B
- Cross-project file reading: Can read files from different project context
- Error handling: Tools with require_project=True fail cleanly without context

---

### Component 3: Custom Doc Naming Fix

**Modified File:** `doc_management/manager.py`

**Purpose:** Fix parameter precedence bug where `doc_type` in metadata overrides explicit `doc_name` parameter

**Current Buggy Code (Line 828):**
```python
resolved_name = metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type") or doc_name
```

**Problem Flow:**
```python
manage_docs(
    action="create",
    doc_name="COORDINATION_PROTOCOL",  # User's explicit intent
    metadata={"doc_type": "custom"}     # Implementation detail
)
# Bug: Uses "custom" from metadata instead of "COORDINATION_PROTOCOL" from parameter!
```

**Fixed Code:**
```python
resolved_name = doc_name or metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type")
```

**Precedence (Correct Order):**
1. `doc_name` function parameter (explicit user intent)
2. `metadata["doc_name"]` (explicit in dict form)
3. `metadata["register_as"]` (legacy alias)
4. `metadata["doc_type"]` (fallback for type-based naming)

**Verification:**
- New test: `test_doc_name_parameter_takes_precedence_over_metadata()`
- Test ALL combinations:
  - `doc_name` only → uses doc_name ✓
  - `doc_name` + `metadata["doc_type"]` → uses doc_name ✓ (FIX)
  - `metadata["doc_name"]` only → uses metadata.doc_name ✓
  - `metadata["doc_type"]` only → uses metadata.doc_type ✓

---

### Component 4: Index Update Event Coverage

**Modified File:** `tools/manage_docs.py`

**Purpose:** Trigger index updates on ALL document changes, not just creation

**Current Behavior (Lines 2771-2775):**
```python
# Index updates ONLY called for special doc CREATION
if is_special and action == "create":
    index_updater = ...
    await index_updater()
```

**Problem:** Edit operations (replace_section, apply_patch, replace_range, etc.) on special docs don't update indexes

**Fixed Behavior:**
```python
# After apply_doc_change() returns successfully (line ~1800)
result = await apply_doc_change(...)

if result.status == "success":
    # NEW: Check if document is a special type that needs index update
    doc_category = determine_doc_category(doc_name_or_path, metadata)
    
    if doc_category in ["research", "bugs", "review", "agent_cards"]:
        # Determine which index updater to call
        index_updater_map = {
            "research": _update_research_index,
            "bugs": _update_bug_index,
            "review": _update_review_index,
            "agent_cards": _update_agent_card_index,
        }
        
        updater = index_updater_map.get(doc_category)
        if updater:
            await updater(project_name, project_root, doc_dir)
```

**Actions That Should Trigger Index Update:**
- `create` (already works)
- `replace_section` (NEW)
- `apply_patch` (NEW)
- `replace_range` (NEW)
- `replace_text` (NEW)
- `append` (NEW)
- `status_update` for checklists (NEW - if checklist is a special doc)

**Verification:**
- Edit research doc → INDEX.md updated
- Edit bug report → bugs/INDEX.md updated
- Edit review report → REVIEW_INDEX.md updated
- Multiple edits → index reflects final state
- Index shows correct last_updated timestamp

---

### Component 5: Backup File Location Cleanup

**Modified Files:**
- `doc_management/manager.py` (backup creation logic)
- `tools/manage_docs.py` (preflight/inflight backup calls)

**Purpose:** Move backup files from polluting source directories to dedicated backup location

**Current Behavior:**
```python
# Backups created next to source files:
# .scribe/docs/dev_plans/project/research/RESEARCH_DOC.md
# .scribe/docs/dev_plans/project/research/RESEARCH_DOC.md.bak  ← POLLUTION
# .scribe/docs/dev_plans/project/research/RESEARCH_DOC.md.preflight.bak  ← POLLUTION
```

**Fixed Behavior:**
```python
# Backups in dedicated directory:
# .scribe/backups/
#   ├── 2026-01-20/
#   │   ├── manage_docs_agent_ux/
#   │   │   ├── research/
#   │   │   │   ├── RESEARCH_DOC.md.1705750000.bak
#   │   │   │   ├── RESEARCH_DOC.md.1705750100.preflight.bak
```

**Design:**
1. Create `get_backup_path()` utility function
2. Input: original file path, backup type (inflight/preflight/manual)
3. Output: path in `.scribe/backups/{date}/{project}/{relative_path}/`
4. Preserve directory structure but isolate from working docs
5. Include timestamp in filename for multi-backup safety

**Implementation:**
```python
def get_backup_path(
    original_path: Path,
    project_name: str,
    backup_type: str = "inflight"  # inflight, preflight, manual
) -> Path:
    """Generate backup path in dedicated backup directory.
    
    Args:
        original_path: Original file path (e.g., .scribe/docs/dev_plans/proj/research/DOC.md)
        project_name: Project name for organization
        backup_type: Type of backup (inflight, preflight, manual)
        
    Returns:
        Path: .scribe/backups/{date}/{project}/{relative_path}/{filename}.{timestamp}.{type}.bak
    """
    from datetime import datetime
    
    # Extract relative path from project root
    # e.g., "research/RESEARCH_DOC.md"
    relative = original_path.relative_to(project_root_somehow())
    
    # Generate backup directory
    backup_root = Path(".scribe/backups")
    date_dir = datetime.now().strftime("%Y-%m-%d")
    backup_dir = backup_root / date_dir / project_name / relative.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamped filename
    timestamp = int(datetime.now().timestamp())
    backup_filename = f"{original_path.stem}.{timestamp}.{backup_type}.bak"
    
    return backup_dir / backup_filename
```

**Verification:**
- Create/edit doc → backup appears in `.scribe/backups/`
- Original directory clean (no .bak files)
- Multiple edits → multiple timestamped backups
- Backup retention: Optional cleanup of backups older than 30 days

---

<!-- ID: data_flow -->
## Data Flow

### Session Isolation Flow (Fixed)

```
1. MCP Request arrives
   ↓
2. ExecutionContext created with stable_session_id
   ↓
3. set_project() called
   ↓
4. get_canonical_session_key(exec_context)
   → Returns: stable_session_id
   ↓
5. backend.set_session_project(session_key, "project_name")
   → Stores: {"stable_xyz_123": "my_project"}
   ↓
6. append_entry() called (same session)
   ↓
7. get_canonical_session_key(exec_context)
   → Returns: stable_xyz_123 (SAME KEY)
   ↓
8. backend.get_session_project(session_key)
   → Returns: "my_project" (CORRECT RESOLUTION)
   ↓
9. Log written to correct project ✓
```

**Before Fix:** Step 4 and 7 used DIFFERENT logic, returned DIFFERENT keys → wrong project

**After Fix:** Step 4 and 7 use SAME function, return SAME key → correct project

---

### Multi-Project Tool Usage Flow (New Capability)

```
Scenario: Agent working on Project A needs to log to Project B

1. Agent calls:
   append_entry(
       message="Cross-project note",
       project="project_b",  # NEW: Explicit override
       agent="ArchitectAgent"
   )
   ↓
2. resolve_logging_context(explicit_project="project_b")
   ↓
3. Precedence check:
   - explicit_project="project_b" (HIGHEST) ✓
   - session binding (ignored, explicit wins)
   - global state (ignored)
   ↓
4. Returns: LoggingContext(project="project_b", ...)
   ↓
5. Log written to project_b progress log ✓
```

**Use Cases:**
- Orchestrator logging to multiple sub-projects
- Research agent creating findings in dedicated research project
- Coder agent logging implementation to feature-specific project

---

### Index Update Flow (Fixed)

```
1. User calls: manage_docs(action="replace_section", doc="RESEARCH_AUTH", ...)
   ↓
2. apply_doc_change() executes edit
   ↓
3. Frontmatter updated (already works)
   ↓
4. NEW: Check if doc is special type
   → doc_category = "research" ✓
   ↓
5. NEW: Call index updater
   → _update_research_index(project_name, project_root, doc_dir)
   ↓
6. Index scans all research docs
   ↓
7. INDEX.md regenerated with updated metadata
   ↓
8. Result: Index reflects latest edit ✓
```

**Before Fix:** Steps 4-7 only ran on creation, not edits → stale indexes

**After Fix:** Steps 4-7 run on ALL document changes → always fresh

---

<!-- ID: testing_strategy -->
## Testing Strategy

### Unit Tests

**Test Suite 1: Session Key Resolution**
- File: `tests/test_session_utils.py` (NEW)
- Coverage:
  - ✓ ExecutionContext with stable_session_id only
  - ✓ ExecutionContext with session_id only
  - ✓ ExecutionContext with both (stable preferred)
  - ✓ ExecutionContext with neither (returns None)
  - ✓ None ExecutionContext (returns None)

**Test Suite 2: Explicit Project Parameters**
- File: `tests/test_tool_project_params.py` (NEW)
- Coverage:
  - ✓ append_entry with explicit project parameter
  - ✓ read_file with explicit project parameter
  - ✓ generate_doc_templates with explicit project parameter
  - ✓ Precedence: explicit > session > global
  - ✓ Error when require_project=True and no project available

**Test Suite 3: Custom Doc Naming**
- File: `tests/test_manage_docs_create_doc.py` (EXTEND)
- Coverage:
  - ✓ doc_name parameter only
  - ✓ doc_name parameter + metadata.doc_type (doc_name wins)
  - ✓ metadata.doc_name only
  - ✓ metadata.doc_type only
  - ✓ All four precedence levels tested

**Test Suite 4: Index Updates**
- File: `tests/test_index_updates.py` (NEW)
- Coverage:
  - ✓ Create research doc → INDEX.md updated
  - ✓ Edit research doc → INDEX.md updated (NEW)
  - ✓ Create bug report → bugs/INDEX.md updated
  - ✓ Edit bug report → bugs/INDEX.md updated (NEW)
  - ✓ Multiple edits → index shows final state

**Test Suite 5: Backup Location**
- File: `tests/test_backup_paths.py` (NEW)
- Coverage:
  - ✓ Backup created in .scribe/backups/
  - ✓ Original directory clean (no .bak files)
  - ✓ Timestamp included in filename
  - ✓ Directory structure preserved
  - ✓ Multiple backups don't overwrite

### Integration Tests

**Integration Test 1: Session Isolation End-to-End**
```python
async def test_session_isolation_end_to_end():
    # 1. set_project binds session to project_a
    await set_project(name="project_a")
    
    # 2. append_entry in same session
    result = await append_entry(message="test", agent="TestAgent")
    
    # 3. Verify log written to project_a (not global, not wrong project)
    assert result["project"] == "project_a"
    assert log_exists_in_project("project_a", "test")
```

**Integration Test 2: Cross-Project Tool Usage**
```python
async def test_cross_project_logging():
    # Agent context: project_a active
    await set_project(name="project_a")
    
    # Log to different project explicitly
    result = await append_entry(
        message="cross-project note",
        project="project_b",  # Explicit override
        agent="TestAgent"
    )
    
    # Verify logged to project_b, not project_a
    assert result["project"] == "project_b"
    assert log_exists_in_project("project_b", "cross-project note")
    assert not log_exists_in_project("project_a", "cross-project note")
```

**Integration Test 3: Index Update on Edit**
```python
async def test_index_updates_on_edit():
    # 1. Create research doc
    await manage_docs(
        action="create",
        metadata={"doc_type": "research", "research_goal": "Initial"}
    )
    
    # 2. Verify INDEX.md created
    index_before = read_index("research/INDEX.md")
    assert "Initial" in index_before
    
    # 3. Edit research doc
    await manage_docs(
        action="replace_section",
        doc_name="RESEARCH_TEST",
        section="research_goal",
        content="Updated goal"
    )
    
    # 4. Verify INDEX.md updated (NOT STALE)
    index_after = read_index("research/INDEX.md")
    assert "Updated goal" in index_after
    assert index_after != index_before  # Changed!
```

---

<!-- ID: security_considerations -->
## Security Considerations

### 1. Session Isolation Enforcement

**Risk:** Cross-session project contamination if session keys inconsistent

**Mitigation:**
- Single canonical session key function prevents drift
- Session binding stored in database (survives restarts)
- Optional validation: Check session-project binding before every operation

### 2. Cross-Project Access Control

**Risk:** Explicit `project` parameter allows agents to access any project

**Current State:** No project-level access control exists (out of scope)

**Future Work:**
- Add project access control layer
- Validate agent has permission to access specified project
- Audit log for cross-project operations

### 3. Backup File Security

**Risk:** Backups may contain sensitive information

**Mitigation:**
- Backups stored in `.scribe/backups/` (already in .gitignore)
- Same permission model as original files
- Optional: Add backup encryption for sensitive projects

### 4. Index Update Race Conditions

**Risk:** Concurrent edits to same doc may cause index corruption

**Mitigation:**
- Index updates are idempotent (full regeneration each time)
- File system atomic writes used
- Future: Add optimistic locking for index updates

---

<!-- ID: deployment_strategy -->
## Deployment Strategy

### Phase 1: Session Isolation (CRITICAL - High Risk)

**Deployment Order:**
1. Add `shared/session_utils.py` with `get_canonical_session_key()`
2. Update `tools/set_project.py` to use new function
3. Update `shared/logging_utils.py` to use new function
4. Deploy + restart MCP server
5. Monitor session binding logs for 24 hours
6. Verify no cross-project contamination in production

**Rollback Plan:**
- Revert commits in reverse order
- Session binding table persists (safe, just unused)
- No data loss risk

**Risk Level:** HIGH (core session management)

---

### Phase 2: Multi-Project Parameters (MEDIUM - Breaking API Change)

**Deployment Order:**
1. Add `project` parameter to append_entry, read_file, generate_doc_templates
2. Update resolve_logging_context to handle explicit_project
3. Update tool documentation
4. Deploy with backward compatibility (parameter optional)
5. Monitor for errors in logs

**Rollback Plan:**
- Parameter is optional, so existing code works
- Can remove parameter without data impact
- Safe rollback

**Risk Level:** MEDIUM (API change but backward compatible)

---

### Phase 3: Custom Doc Naming (LOW - Simple Fix)

**Deployment Order:**
1. Fix line 828 in manager.py (precedence order)
2. Add regression test
3. Deploy
4. Test with actual custom doc creation

**Rollback Plan:**
- Single line change, easy revert
- No data corruption risk (just naming)
- Safe rollback

**Risk Level:** LOW (simple parameter precedence fix)

---

### Phase 4: Index Updates (MEDIUM - May Impact Performance)

**Deployment Order:**
1. Add index update check after apply_doc_change()
2. Test index update performance (may add latency)
3. Deploy with monitoring
4. Watch for slow edit operations
5. Optimize if needed (async index updates)

**Rollback Plan:**
- Remove index update calls
- Indexes become stale but no data loss
- Can manually regenerate indexes

**Risk Level:** MEDIUM (performance impact possible)

---

### Phase 5: Backup Cleanup (LOW - Cosmetic)

**Deployment Order:**
1. Add `get_backup_path()` utility
2. Update backup creation to use new path
3. Deploy
4. Verify backups appear in correct location
5. Optional: Cleanup script for old .bak files

**Rollback Plan:**
- Revert to old backup location
- No functionality impact (just file location)
- Safe rollback

**Risk Level:** LOW (cosmetic cleanup)

---

<!-- ID: performance_considerations -->
## Performance Considerations

### Index Update Performance

**Concern:** Index updates on EVERY edit may add latency

**Measurement:**
- Current index update time: ~50-100ms (scanning directory)
- Edit operation time: ~10-20ms (file write)
- Total impact: 2-5x increase in edit latency

**Optimization Options:**

1. **Async Index Updates (Recommended)**
   - Queue index update task
   - Return edit success immediately
   - Update index in background
   - Trade-off: Eventual consistency (index lags by ~100ms)

2. **Incremental Index Updates**
   - Don't rescan entire directory
   - Update only the changed document's entry
   - Requires index format change (more complex)

3. **Lazy Index Updates**
   - Mark index as stale
   - Regenerate only when INDEX.md is read
   - Trade-off: First read after edit is slow

**Recommendation:** Start with synchronous updates (simple), optimize to async if latency becomes issue

---

### Session Key Lookup Performance

**Concern:** Database lookup on every tool call

**Measurement:**
- SQLite lookup time: ~1-2ms
- Tool call overhead: Negligible (<1% of total time)

**Optimization:**
- Session binding cache (in-memory, TTL 15 minutes)
- Invalidate on set_project() calls
- Expected impact: 0.5-1ms saved per tool call

**Recommendation:** Implement caching in Phase 1 if needed, but likely not required

---

### Backup File I/O

**Concern:** Creating backups adds I/O overhead

**Current State:** Backups already created (just changing location)

**Impact:** No change in I/O volume, just different path

**Future Optimization:** Optional backup disable for non-critical projects

---

<!-- ID: future_enhancements -->
## Future Enhancements

### 1. Session-Scoped Project Isolation (Advanced)

**Current:** Session binding stored in database, but no enforcement

**Enhancement:**
- Validate project access on EVERY tool call
- Reject operations on projects not bound to current session
- Requires: Session-to-project permission model

**Benefit:** True multi-user isolation in shared MCP server

---

### 2. Project Access Control Layer

**Current:** No project-level permissions exist

**Enhancement:**
- Define project ownership/access rules
- Agents must request permission for cross-project operations
- Audit log for denied access attempts

**Benefit:** Security for sensitive projects

---

### 3. Backup Retention Policies

**Current:** Backups accumulate indefinitely

**Enhancement:**
- Configurable retention period (default: 30 days)
- Automatic cleanup of old backups
- Optional backup compression (gzip)

**Benefit:** Disk space management

---

### 4. Index Update Optimizations

**Current:** Full directory scan on every edit

**Enhancement:**
- Incremental index updates (single entry)
- Parallel index generation for large directories
- Index caching with invalidation

**Benefit:** Reduced latency for large projects

---

<!-- ID: verification_criteria -->
## Verification Criteria

### Acceptance Tests

**Session Isolation:**
- [ ] set_project() followed by append_entry() in same session → correct project
- [ ] set_project() in session A, set_project() in session B → no cross-contamination
- [ ] Session binding survives MCP server restart
- [ ] No "EmergencyFallback" entries in logs after fix

**Multi-Project Parameters:**
- [ ] append_entry(project="other") logs to specified project, not active project
- [ ] read_file(project="other") reads from specified project context
- [ ] generate_doc_templates(project="other") generates in specified project
- [ ] Error when require_project=True and no project available (no silent fallback)

**Custom Doc Naming:**
- [ ] manage_docs(doc_name="X", metadata={"doc_type": "Y"}) creates X.md, not Y.md
- [ ] All 4 precedence levels tested and work correctly
- [ ] Regression test added to prevent future bugs

**Index Updates:**
- [ ] Edit research doc → INDEX.md updated
- [ ] Edit bug report → bugs/INDEX.md updated
- [ ] Edit review report → REVIEW_INDEX.md updated
- [ ] Edit agent card → AGENT_CARDS_INDEX.md updated
- [ ] Timestamp in index reflects latest edit

**Backup Location:**
- [ ] Backups created in .scribe/backups/
- [ ] Original directories clean (no .bak files)
- [ ] Backup filename includes timestamp
- [ ] Multiple backups don't overwrite each other

---

<!-- ID: dependencies -->
## Dependencies

### Internal Dependencies

**Phase 1 (Session Isolation):**
- Requires: `shared/execution_context.py` (already exists)
- Requires: `storage/base.py` with session binding methods (already exists)
- No new dependencies

**Phase 2 (Multi-Project Parameters):**
- Depends on: Phase 1 completion (unified session keys)
- Requires: `shared/logging_utils.py` (already exists)
- No new dependencies

**Phase 3 (Custom Doc Naming):**
- Independent (can deploy standalone)
- No dependencies

**Phase 4 (Index Updates):**
- Depends on: Index updater functions (already exist)
- Requires: `doc_management/manager.py` (already exists)
- No new dependencies

**Phase 5 (Backup Location):**
- Independent (can deploy standalone)
- No new dependencies

### External Dependencies

- None (all changes internal to scribe_mcp)

---

<!-- ID: risks -->
## Risks & Mitigation

### Risk 1: Session Binding Migration

**Risk:** Existing sessions have no binding in database

**Impact:** First tool call after deployment may use wrong project

**Mitigation:**
- On MCP server start, clear session binding table (fresh start)
- Force all agents to call set_project() at session start
- Add validation: Warn if session_id != stable_session_id

**Severity:** MEDIUM (temporary confusion, self-correcting)

---

### Risk 2: Index Update Performance Degradation

**Risk:** Index updates slow down edit operations

**Impact:** User experience degradation for large projects

**Mitigation:**
- Measure performance before deployment
- Set alert threshold (edit > 500ms = alert)
- Implement async updates if needed
- Can disable index updates per project if critical

**Severity:** MEDIUM (performance, mitigatable)

---

### Risk 3: Backup Directory Migration

**Risk:** Old .bak files remain in source directories

**Impact:** Cosmetic pollution, no functional impact

**Mitigation:**
- Optional cleanup script: Find and move old .bak files
- Document manual cleanup process
- Gradual cleanup over time

**Severity:** LOW (cosmetic only)

---

### Risk 4: Cross-Project Access Abuse

**Risk:** Explicit project parameter allows unauthorized access

**Impact:** Agent can log to any project, read any file

**Mitigation:**
- Document security consideration
- Future: Add access control layer
- Audit logging for cross-project operations

**Severity:** LOW (feature working as designed, future enhancement needed)

---

## Summary

This architecture addresses 5 critical bugs and UX issues in Scribe MCP:

1. **Session Isolation** - Unified session key derivation prevents project resolution drift
2. **Multi-Project Concurrency** - Explicit project parameters enable cross-project operations
3. **Custom Doc Naming** - Fixed parameter precedence respects user intent
4. **Index Updates** - Complete event coverage keeps indexes fresh
5. **Backup Cleanup** - Dedicated backup directory reduces pollution

All designs are grounded in verified code analysis and follow existing architectural patterns. Each phase is independently testable and deployable with clear rollback plans.

**Handoff to Coder:** Detailed task packages in PHASE_PLAN.md, verification criteria in CHECKLIST.md.
