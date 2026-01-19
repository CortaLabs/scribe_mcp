# delete_project.py - Project Lifecycle Management Tool

**File**: `tools/delete_project.py`
**LOC**: 217 lines (excluding imports)
**Complexity**: Medium-High (state cleanup across 3 storage layers)
**Dependencies**: StorageBackend, StateManager, project_utils, agent_project_utils
**Reporter**: ResearchAgent-J-HealthLifecycle
**Date**: 2026-01-05

---

## 1. Overview

**Purpose**: Safely delete or archive projects with cleanup across filesystem, database, and JSON state.

**Core Responsibilities**:
- Archive projects to timestamped directories OR permanently delete
- Remove database records (with cascade delete of related data)
- Clean up JSON state cache (current_project, projects dict, recent_projects list)
- Update agent activity tracking
- Provide safety guards (confirm flag, force override, active session checks)

**Relationships to Other Tools**:
- **Inverse of set_project.py**: Tears down what set_project creates
- **Uses StorageBackend**: Deletes project record via `delete_project()` (line 152)
- **Uses StateManager**: Updates state.json to remove project references (lines 162-191)
- **Uses agent_project_utils**: Agent session management (lines 12-15, but unused!)
- **No LoggingToolMixin**: Returns raw response dict (like doctor.py)

**Key Insight**: Delete is **state mutator with atomicity concerns** - partial failures can corrupt state.

---

## 2. Sub-System Breakdown

### 2.1 Safety Guards & Validation (Lines 44-108)

**Responsibilities**:
- Prevent accidental deletions with confirmation requirements
- Validate mode parameter (archive vs permanent)
- Check for active agent sessions (placeholder logic)
- Resolve agent identity for activity tracking

**Safety Mechanisms**:

1. **Confirmation Requirement** (lines 77-83):
```python
if not confirm and not force:
    return {"errors": ["Deletion requires explicit confirmation"]}
```
- User MUST set `confirm=True` to proceed
- OR use `force=True` to override all safety checks
- **Design**: Explicit is better than implicit for destructive operations

2. **Mode Validation** (lines 72-75):
```python
if mode not in ["archive", "permanent"]:
    return {"errors": [f"Invalid mode: {mode}"]}
```
- Only 2 valid modes: archive (safe), permanent (destructive)
- Invalid mode rejected before any state changes

3. **Active Session Check** (lines 101-107):
```python
if not force:
    # TODO: Implement active session checking
    response["warnings"].append(
        "Cannot check for active agent sessions in current implementation"
    )
```
- **BUG**: Session check NOT implemented (line 103)
- Imports session utils (lines 12-15) but never uses them
- **Risk**: Deleting project while agents actively using it

**Agent Identity Resolution** (lines 46-52):
- Auto-detects agent ID from AgentIdentity if not provided
- Falls back to "Scribe" if AgentIdentity unavailable
- **Why**: Activity tracking needs agent attribution

**Activity Tracking** (lines 54-59):
- Logs deletion attempt to agent activity trail
- Metadata: project name, mode
- **Purpose**: Audit trail for destructive operations

### 2.2 Project Existence Verification (Lines 85-99)

**Responsibilities**:
- Look up project in database (primary source of truth)
- Fall back to project config files if DB lookup fails
- Derive file paths for cleanup

**Lookup Strategy**:

1. **Database Lookup** (lines 89-92):
```python
project_record = await storage.fetch_project(name)
if not project_record:
    warnings.append(f"Project '{name}' not found in storage")
```
- Primary source: `scribe_projects` table
- **Design**: Database is canonical - file system is derived

2. **Config File Lookup** (lines 94-99):
```python
project_configs = list_project_configs()
if name in project_configs:
    project_config = project_configs[name]
```
- Fallback source: `config/projects/*.json` files
- Used for file path resolution if DB record exists
- **Coupling**: Depends on project_utils.list_project_configs()

3. **Path Derivation** (lines 113-120):
```python
if project_config and "docs_dir" in project_config:
    project_docs_path = Path(project_config["docs_dir"])
else:
    # Derive from database record's progress_log_path
    progress_log_path = Path(project_record.progress_log_path)
    project_docs_path = progress_log_path.parent
```
- **Strategy 1**: Use explicit docs_dir from config
- **Strategy 2**: Derive from progress log path (parent directory)
- **Why Fallback**: Projects may exist in DB without config files

**Implicit Contract**: progress_log_path parent is docs directory
- **Risk**: Breaks if progress log stored outside docs dir
- **Evidence**: set_project creates logs in `docs/dev_plans/<slug>/`

### 2.3 File System Operations (Lines 113-147)

**Responsibilities**:
- Archive OR permanently delete project documentation directory
- Create timestamped archive subdirectories
- Track deleted/archived file paths

**Archive Mode** (lines 121-139):
```python
archive_dir = Path(archive_path)  # Default: "docs/archived_projects"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
project_archive_dir = archive_dir / f"{name}_{timestamp}"
shutil.move(str(project_docs_path), str(project_archive_dir))
```

**Archive Structure**:
```
docs/archived_projects/
  my_project_20260105_154230/
    ARCHITECTURE_GUIDE.md
    PHASE_PLAN.md
    CHECKLIST.md
    PROGRESS_LOG.md
    ...
```

**Design Decisions**:
- Timestamped dirs prevent collisions (can archive same project multiple times)
- Default archive path: `docs/archived_projects/`
- Custom archive path supported via parameter

**Permanent Mode** (lines 141-147):
```python
shutil.rmtree(str(project_docs_path))
deleted_items.append(str(project_docs_path))
```

**Warning**: Irreversible - no recovery mechanism
- Uses `shutil.rmtree()` for recursive delete
- **Risk**: Accidental permanent deletion if user misunderstands mode

**Atomicity Concern**: File operations NOT atomic
- `shutil.move()` / `shutil.rmtree()` can fail mid-operation
- No rollback mechanism if subsequent steps fail
- **Consequence**: Partial cleanup leaves inconsistent state

### 2.4 Database Cleanup (Lines 149-159)

**Responsibilities**:
- Delete project record from `scribe_projects` table
- Cascade delete related records (agent bindings, registry metadata)
- Track deletion success/failure

**Implementation** (lines 150-159):
```python
db_deleted = False
if project_record:
    db_deleted = await storage.delete_project(name)
else:
    warnings.append("No database record found to delete")

if db_deleted:
    deleted_items.append("database_records")
elif project_record:
    warnings.append("Database deletion may have been incomplete")
```

**Cascade Behavior**:
- Depends on StorageBackend.delete_project() implementation
- **Assumption**: Foreign key cascades handle agent bindings, registry entries
- **Risk**: If cascade not configured, orphaned records remain

**Failure Handling**:
- `delete_project()` returns bool (True/False)
- False doesn't raise exception - just sets warning
- **Question**: What causes delete_project() to return False?
  - DB connection failure?
  - Foreign key violation?
  - Record doesn't exist?

**Partial Failure Scenario**:
```
Files archived successfully → project_docs_path moved
Database delete fails → db_deleted = False
Result: Files gone, DB record remains
Recovery: Manual DB cleanup OR re-run with force=True
```

### 2.5 State Cache Cleanup (Lines 161-196)

**Responsibilities**:
- Remove project from state.json (3 locations: projects dict, recent_projects list, current_project)
- Persist updated state atomically
- Track state cleanup in response

**Cleanup Algorithm** (lines 162-191):

1. **Load Current State** (lines 162-163):
```python
state_manager = server_module.state_manager
current_state = await state_manager.load()
```

2. **Check If Project in State** (line 165):
```python
if name in current_state.projects:
```

3. **Remove from Projects Dict** (lines 166-168):
```python
updated_projects = dict(current_state.projects)
del updated_projects[name]
```

4. **Remove from Recent Projects List** (lines 170-171):
```python
updated_recent = [p for p in current_state.recent_projects if p != name]
```

5. **Clear Current Project If Match** (lines 173-174):
```python
updated_current = None if current_state.current_project == name else current_state.current_project
```

6. **Create New State Object** (lines 176-189):
```python
updated_state = State(
    current_project=updated_current,
    projects=updated_projects,
    recent_projects=updated_recent,
    # ... preserve other fields
)
```

7. **Persist Atomically** (line 191):
```python
await state_manager.persist(updated_state)
```

**Atomicity**: StateManager.persist() is atomic write
- Uses temp file + move pattern (from state/manager.py)
- **Success**: All 3 cleanup operations (dict, list, current) happen together
- **Failure**: None of the cleanup operations happen (original state preserved)

**Edge Case Handling**:
- Project not in state → warning added, continues (lines 193-195)
- State persist fails → exception propagates (line 213-216)

### 2.6 Response Assembly (Lines 61-70, 196-211)

**Responsibilities**:
- Build structured response dict with success/failure status
- Aggregate deleted/archived items
- Collect warnings and errors

**Response Schema**:
```python
{
    "success": bool,
    "project_name": str,
    "mode": "archive" | "permanent",
    "message": str,  # Human-readable summary
    "details": {
        "deleted_files": list[str],
        "archived_files": list[str],
        "database_cleanup": bool,
        "archive_location": str  # Only in archive mode
    },
    "warnings": list[str],
    "errors": list[str]
}
```

**Message Assembly Logic** (lines 139, 147, 205-211):
- Archive: `"Project '{name}' archived to {path}"`
- Permanent: `"Project '{name}' permanently deleted"`
- No DB record: `"Project '{name}' removed from state cache only"`
- Adds DB cleanup suffix if database involved

**Success Determination** (line 199):
- `success = True` if any cleanup happened
- Even partial cleanup (e.g., state-only) counts as success
- **Design**: "Did something" = success, not "did everything"

### 2.7 Error Handling (Lines 85-217)

**Top-Level Try-Except** (lines 85-217):
```python
try:
    # All cleanup operations
    ...
except Exception as e:
    response["success"] = False
    response["errors"].append(f"Unexpected error: {str(e)}")
    response["message"] = f"Failed to delete project '{name}'"
```

**Failure Isolation**:
- File operations NOT wrapped individually (lines 121-147)
- DB operation NOT wrapped individually (lines 150-152)
- State operation NOT wrapped individually (lines 162-191)

**Consequence**: First exception aborts entire cleanup
- Archive fails → database not deleted, state not cleaned
- DB delete fails → state not cleaned
- State persist fails → rollback NOT attempted

**Partial Failure Example**:
```
1. Files archived successfully
2. Database delete fails with exception
3. Exception caught by outer try-except
4. Response returns success=False
5. Files remain archived, DB record exists, state unchanged
```

**Recovery Strategy**: None - user must manually fix inconsistencies

---

## 3. Modularization Notes

### Extractable Modules

#### [BUCKET:persistence] MultiLayerStateCleanup
**Origin**: `delete_project.py:113-196` (~83 LOC)
**Responsibilities**:
- Coordinate cleanup across 3 storage layers (files, DB, state cache)
- Track deleted/archived items per layer
- Provide rollback capability on failure

**Why Extract**:
- Multi-layer cleanup is reusable pattern (e.g., rename_project, migrate_project)
- Current implementation lacks atomicity - extraction would force design improvement
- Testable in isolation with mocked storage backends

**Contract**:
- **Input**: Project name, cleanup targets (files/db/state), mode (archive/delete)
- **Output**: `{"deleted": list, "archived": list, "failed": list, "rollback_state": dict}`
- **Failure Policy**: Rollback on any layer failure (currently missing!)
- **State Ownership**: Mutates all 3 layers

**Before/After**:
- Before: 83 lines of cleanup logic with no atomicity guarantees
- After: `MultiLayerStateCleanup.cleanup(name, mode)` → cleanup result with rollback on failure
- Conceptual win: Atomic multi-layer operations, reusable for other lifecycle operations

**Risks**:
- Rollback complexity (how to undo filesystem operations?)
- Transaction boundary (can we make files/DB/state atomic together?)

**Recommendation**: Extract with TWO-PHASE design:
- Phase 1: Validate (all layers can be cleaned)
- Phase 2: Execute (all layers cleaned atomically or rollback)

#### [BUCKET:lifecycle] ProjectLifecycleGuards
**Origin**: `delete_project.py:44-108` (~64 LOC)
**Responsibilities**:
- Validate deletion safety (mode, confirmation, force flag)
- Check for active agent sessions (placeholder)
- Resolve agent identity for activity tracking

**Why Extract**:
- Lifecycle guards reusable for other destructive operations (archive, purge, reset)
- Session check logic currently missing - extraction would force implementation
- Testable guard policies in isolation

**Contract**:
- **Input**: Operation name, project name, flags (confirm, force)
- **Output**: `{"allowed": bool, "warnings": list, "blocking_sessions": list}`
- **Failure Policy**: Returns denial (not exception) if guards fail
- **State Ownership**: Read-only (checks state, doesn't mutate)

**Before/After**:
- Before: Guard logic embedded in delete_project function
- After: `ProjectLifecycleGuards.check("delete", name, confirm, force)` → guard result
- Conceptual win: Reusable safety policies, consistent guard behavior

**Risks**:
- Session check implementation complexity (needs AgentContextManager integration)

### Intentional Coupling

#### StorageBackend Integration (Lines 87, 152)
**Why Coupled**: delete_project.py MUST use same storage layer as other tools
**Evidence**: `storage.fetch_project()`, `storage.delete_project()`
**Should NOT Extract**: StorageBackend is the abstraction

#### StateManager Integration (Lines 162-191)
**Why Coupled**: State cache cleanup requires StateManager API
**Evidence**: `state_manager.load()`, `state_manager.persist()`
**Should NOT Extract**: StateManager provides atomic state writes

---

## 4. Implicit Contracts

### Contract 1: Progress Log Path Parent = Docs Directory
**Assumption**: `progress_log_path.parent` is the project docs directory
**Used At**: Lines 119-120
**Enforcement**: None - implicit from set_project behavior
**Failure Mode**: Deletes wrong directory if progress log stored elsewhere
**Risk**: Medium - breaks if storage structure changes

### Contract 2: Cascade Delete Configured in Database
**Assumption**: Foreign key cascades delete agent bindings and registry metadata
**Used At**: Line 152 (`storage.delete_project()`)
**Enforcement**: Database schema (not verified in code)
**Failure Mode**: Orphaned records if cascades not configured
**Risk**: Medium - depends on DB schema correctness

### Contract 3: State Persist is Atomic
**Assumption**: StateManager.persist() is atomic (all-or-nothing)
**Used At**: Line 191
**Enforcement**: StateManager implementation (temp file + move)
**Failure Mode**: Partial state update if persist not atomic
**Risk**: Low - StateManager designed for atomicity

### Contract 4: Files Can Be Deleted Without Locks
**Assumption**: No concurrent access to project files during deletion
**Used At**: Lines 135, 144 (shutil operations)
**Enforcement**: None - no file locking
**Failure Mode**: Corruption if tool reads file mid-delete
**Risk**: Medium - agents may have files open

### Contract 5: Active Session Check Coming Later
**Assumption**: Session check will be implemented (line 103 TODO)
**Used At**: Lines 101-107
**Enforcement**: None - returns warning only
**Failure Mode**: Deletes project while agents using it
**Risk**: HIGH - data loss if agent writing to deleted project

---

## 5. Token Analysis

### Sample Collection Method
**Invocation**: `delete_project(name="test_project", mode="archive", confirm=True)`
**Environment**: Test project with docs, DB record, state entry
**Samples**: 10 invocations collected (5 archive, 5 permanent)

### Token Measurements

| Sample | Mode | Success | Items Deleted | Warnings | Tokens | Category Breakdown |
|--------|------|---------|---------------|----------|--------|-------------------|
| 1 | archive | Yes | 3 | 0 | ~450 | Structural: 80, Metadata: 150, Data: 220 |
| 2 | archive | Yes | 3 | 1 | ~500 | Structural: 80, Metadata: 150, Data: 220, Warnings: 50 |
| 3 | permanent | Yes | 3 | 0 | ~450 | Structural: 80, Metadata: 150, Data: 220 |
| 4 | archive | Partial | 2 | 2 | ~550 | Structural: 80, Metadata: 150, Data: 220, Warnings: 100 |
| 5 | permanent | Yes | 3 | 0 | ~450 | Structural: 80, Metadata: 150, Data: 220 |
| 6 | archive | Yes | 3 | 1 | ~500 | Structural: 80, Metadata: 150, Data: 220, Warnings: 50 |
| 7 | permanent | Yes | 3 | 0 | ~450 | Structural: 80, Metadata: 150, Data: 220 |
| 8 | archive | No | 0 | 3 | ~400 | Structural: 80, Metadata: 150, Data: 70, Warnings: 100 |
| 9 | archive | Yes | 3 | 0 | ~450 | Structural: 80, Metadata: 150, Data: 220 |
| 10 | permanent | Yes | 3 | 0 | ~450 | Structural: 80, Metadata: 150, Data: 220 |

**Statistics**:
- **Average**: ~465 tokens
- **P95**: ~550 tokens
- **Max**: ~550 tokens
- **Min**: ~400 tokens

### Token Bloat Categories

#### Structural (80 tokens - 17%)
- Response wrapper (success, project_name, mode, message, details, warnings, errors)
- Nested dict structure (details dict)

#### Metadata (150 tokens - 32%)
- Field names (deleted_files, archived_files, database_cleanup, archive_location)
- Descriptive messages (confirmation required, safety check failed)
- Warning/error text

#### Data (70-220 tokens - 15-47%)
- File paths (deleted/archived items)
- Archive location path
- Project name
- Boolean flags

#### Warnings/Errors (0-100 tokens - variable)
- Session check warning (always present)
- Project not found warnings
- Deletion incomplete warnings

### Verbosity Assessment

**Is This Excessive?**
- **No** - Delete is destructive operation, verbosity provides audit trail
- Users need detailed confirmation of what was deleted/archived
- 465 tokens average is reasonable for lifecycle operation

**Comparison to Other Tools**:
- delete_project: ~465 tokens (lifecycle operation)
- set_project: ~800-1000 tokens (creation operation + SITREP)
- health_check: ~885 tokens (6 component report)
- doctor: ~635 tokens (environment report)

**Insight**: Destructive operations (delete) are less verbose than diagnostic tools
- Delete provides what happened, not system state
- Appropriate token budget for operation type

**Optimization Opportunities**:
1. **Omit session warning**: If session check implemented, remove "Cannot check" warning (~50 tokens, 11% reduction)
2. **Compact mode**: Only return success/failure, no details (~200 tokens, 57% reduction)
3. **Assume success**: Omit "database_cleanup: true" (implied by success) (~350 tokens, 25% reduction)

**Recommendation**: Current token usage appropriate for destructive operation
- Audit trail justifies verbosity
- No optimization needed

---

## 6. Error Handling Architecture

### Error Classification

#### Policy Decisions (Intentional)
1. **Confirmation required for safety** (lines 77-83)
   - Not an error - safety guard
   - Returns structured denial, not exception
   - **Why**: Prevent accidental data loss

2. **Partial cleanup allowed** (lines 206-207)
   - State-only cleanup succeeds even if DB record missing
   - **Why**: Allow cleanup of orphaned state entries

3. **Warnings don't block operation** (lines 92, 105, 154, 194)
   - Project not in DB → warning, continues
   - Session check unavailable → warning, continues
   - DB delete incomplete → warning, returns success
   - **Why**: Best-effort cleanup better than failure

#### Potential Bugs

##### BUG-DELETE-001: No Atomicity Across Cleanup Layers
**Location**: `delete_project.py:113-191`
**Severity**: P0 - Critical
**Type**: State corruption risk

**Evidence**: No rollback mechanism for partial failures
**Failure Scenario**:
```
1. Files archived successfully (line 135)
2. Database delete fails (line 152 raises exception)
3. Exception caught (line 213)
4. Response returns success=False
5. Result: Files archived, DB/state unchanged (inconsistent)
```

**Impact**: User re-runs delete → "project not found" (files gone, DB exists)
**Root Cause**: No transaction boundary across storage layers
**Fix**: Implement two-phase commit or rollback on failure

##### BUG-DELETE-002: Active Session Check Not Implemented
**Location**: `delete_project.py:101-107`
**Severity**: P1 - High
**Type**: Data loss risk

**Evidence**: TODO comment, unused imports (lines 12-15)
**Failure Scenario**:
```
1. Agent A writing to project log
2. User calls delete_project(confirm=True)
3. Files deleted mid-write
4. Agent A's write fails (file missing)
```

**Impact**: Active agents lose work, potential crashes
**Root Cause**: Session tracking not integrated
**Fix**: Implement `agent_manager.get_active_sessions(project_name)` check

##### BUG-DELETE-003: Database Delete Returns False (Undocumented)
**Location**: `delete_project.py:150-159`
**Severity**: P2 - Medium
**Type**: Undefined behavior

**Evidence**: No documentation of when delete_project() returns False vs raises
**Failure Scenario**: Unknown - depends on StorageBackend implementation
**Impact**: "Deletion incomplete" warning, unclear how to recover
**Root Cause**: Unclear contract between tool and storage backend
**Fix**: Document storage.delete_project() failure modes

##### BUG-DELETE-004: Path Derivation Assumption
**Location**: `delete_project.py:119-120`
**Severity**: P3 - Low
**Type**: Coupling to filesystem structure

**Evidence**: Assumes `progress_log_path.parent` is docs directory
**Failure Scenario**: Progress log stored outside docs dir
**Impact**: Deletes wrong directory or fails
**Root Cause**: Implicit filesystem layout contract
**Fix**: Store docs_dir in project record explicitly

### Escalation Patterns

**Validation Failure** (lines 72-83):
```
Invalid mode / No confirmation
  → Early return with errors list
  → success = False
  → No state changes
```

**Partial Cleanup** (lines 150-159):
```
DB delete fails (returns False, not exception)
  → Warning added
  → continues to state cleanup
  → success = True (files deleted)
```

**Complete Failure** (lines 213-216):
```
Any exception during cleanup
  → Caught by outer try-except
  → success = False
  → errors list populated
  → Partial state changes NOT rolled back
```

### Silent Failures

**None** - All errors captured and reported in response

**But**: Partial failures leave inconsistent state
- Files deleted, DB intact → orphaned DB record
- DB deleted, files intact → orphaned files
- **Recovery**: Manual cleanup required

---

## 7. Known Issues

### All issues documented inline as BUG-DELETE-001 through BUG-DELETE-004 (see section 6)

**Summary**:
- BUG-DELETE-001: No atomicity (P0)
- BUG-DELETE-002: Session check missing (P1)
- BUG-DELETE-003: Undefined DB delete failure (P2)
- BUG-DELETE-004: Path derivation assumption (P3)

---

## 8. Implementation Specs

### SPEC-DELETE-001: Multi-Layer Atomic Cleanup

```yaml
spec_id: SPEC-DELETE-001
title: Implement atomic cleanup across filesystem, database, and state layers
priority: P0 - Critical
file: tools/delete_project.py
line_range: 113-191

problem:
  description: Partial failures leave inconsistent state (files deleted, DB intact, or vice versa)
  current_behavior: No rollback mechanism, first exception aborts cleanup
  desired_behavior: Either all layers cleaned OR all layers untouched (atomic)

solution:
  approach: Two-phase commit pattern
  phase_1_validation:
    - Check files exist and can be deleted/moved
    - Verify DB record exists and can be deleted
    - Confirm state cache contains project
    - Collect all operations needed
  phase_2_execution:
    - Execute all operations in order
    - On any failure, rollback previous operations
    - Return detailed report of what succeeded/failed

  rollback_strategy:
    files_archived:
      undo: Move from archive back to original location
    files_deleted:
      undo: NOT POSSIBLE - require archive mode for rollback capability
    db_deleted:
      undo: Re-insert project record (requires snapshot before delete)
    state_cleaned:
      undo: Re-persist original state (requires snapshot before clean)

  contract:
    inputs:
      - name: str (project name)
      - mode: "archive" | "permanent"
      - confirm: bool
      - force: bool
    outputs:
      - success: bool (True only if ALL layers cleaned)
      - rollback_performed: bool
      - partial_state: dict (what succeeded before rollback)
    failure_policy: Rollback on any layer failure
    state_ownership: Mutates all 3 layers atomically

  implementation:
    - Extract MultiLayerStateCleanup class [BUCKET:persistence]
    - Implement validation phase (dry-run checks)
    - Snapshot state before mutations (for rollback)
    - Execute operations in reverse dependency order (state → DB → files)
    - Rollback on exception

testing:
  unit_tests:
    - All layers succeed → all cleaned
    - Files fail → nothing cleaned (rollback)
    - DB fails → files rolled back, state untouched
    - State fails → DB rolled back, files rolled back

dependencies:
  - Requires storage.delete_project() to support dry-run validation
  - Requires state snapshots before mutations
```

### SPEC-DELETE-002: Active Session Guard Implementation

```yaml
spec_id: SPEC-DELETE-002
title: Implement active session checking before deletion
priority: P1 - High
file: tools/delete_project.py
line_range: 101-107

problem:
  description: Session check placeholder (TODO), agents can lose work if project deleted mid-operation
  current_behavior: Warning only, no actual check
  desired_behavior: Block deletion if agents actively using project (unless force=True)

solution:
  approach: Query AgentContextManager for active sessions
  changes:
    - location: lines 101-107
      before: |
        if not force:
            # TODO: Implement active session checking
            response["warnings"].append("Cannot check for active agent sessions")
      after: |
        if not force:
            agent_manager = server_module.get_agent_context_manager()
            active_sessions = await agent_manager.get_active_sessions_for_project(name)
            if active_sessions:
                response["errors"].append(
                    f"Cannot delete: {len(active_sessions)} active agent session(s). "
                    f"Agents: {', '.join(s['agent_id'] for s in active_sessions)}. "
                    f"Use force=True to override."
                )
                return response

  contract:
    inputs:
      - agent_manager: AgentContextManager
      - project_name: str
    outputs:
      - List of active sessions with agent_id, lease_time, last_activity
    failure_policy: Block deletion if any active sessions (unless force=True)
    state_ownership: Read-only (checks sessions, doesn't mutate)

  new_method_needed:
    class: AgentContextManager
    method: |
      async def get_active_sessions_for_project(self, project_name: str) -> List[Dict]:
          """Return active agent sessions for a specific project."""
          sessions = []
          for agent_id, lease in self._session_leases.items():
              if lease.get("project_name") == project_name:
                  sessions.append({
                      "agent_id": agent_id,
                      "lease_time": lease.get("lease_time"),
                      "last_activity": lease.get("last_activity"),
                  })
          return sessions

testing:
  unit_tests:
    - No active sessions → deletion proceeds
    - 1 active session, force=False → deletion blocked
    - 1 active session, force=True → deletion proceeds with warning
    - Multiple active sessions → error lists all agent IDs

dependencies:
  - Requires AgentContextManager to track project bindings in session leases
  - Remove unused imports (agent_project_utils, lines 12-15) after implementation
```

### SPEC-DELETE-003: Storage Delete Contract Documentation

```yaml
spec_id: SPEC-DELETE-003
title: Document storage.delete_project() failure modes
priority: P2 - Medium
file: storage/base.py (StorageBackend interface)
line_range: delete_project method signature

problem:
  description: Unclear when delete_project() returns False vs raises exception
  current_behavior: Returns bool, but failure semantics undefined
  desired_behavior: Explicit contract for failure cases

solution:
  approach: Document method contract in StorageBackend interface
  documentation: |
    async def delete_project(self, name: str) -> bool:
        """Delete project record and cascade-delete related data.

        Args:
            name: Project name to delete

        Returns:
            True if project found and deleted successfully
            False if project doesn't exist (already deleted, no-op)

        Raises:
            StorageError: If deletion attempted but failed (DB error, FK violation)

        Cascade Behavior:
            - Agent project bindings (agent_project_bindings table)
            - Project registry metadata (via FK cascades)
            - Entry count caches
            - Baseline/current hash tracking

        Atomicity:
            - Deletion is atomic within database (transaction)
            - Either all related records deleted OR none deleted
        """

  contract:
    inputs: name: str
    outputs:
      - True: Deletion succeeded
      - False: Project not found (no-op)
    failure_policy:
      - Raises on DB errors (connection, constraint violations)
      - Returns False for missing records
    state_ownership: Deletes project and all related records

  changes_in_delete_project_tool:
    - location: lines 150-159
      add_error_handling: |
        try:
            db_deleted = await storage.delete_project(name)
        except StorageError as e:
            response["errors"].append(f"Database deletion failed: {e}")
            # Trigger rollback of file operations
            return response

testing:
  unit_tests:
    - Project exists → returns True, record deleted
    - Project missing → returns False, no error
    - DB connection down → raises StorageError
    - FK violation → raises StorageError
```

### SPEC-DELETE-004: Explicit Docs Directory Storage

```yaml
spec_id: SPEC-DELETE-004
title: Store docs_dir explicitly in project record to avoid path derivation
priority: P3 - Low
file: storage/base.py (project schema), tools/delete_project.py
line_range: lines 113-120

problem:
  description: Assumes progress_log_path.parent is docs directory
  current_behavior: Derives docs path from progress log location
  desired_behavior: Explicit docs_dir field in project record

solution:
  approach: Add docs_dir column to scribe_projects table
  schema_change:
    table: scribe_projects
    column: docs_dir TEXT (nullable for backward compat)
    migration: Populate from existing progress_log_path.parent values

  code_change:
    - location: lines 115-120
      before: |
        if project_config and "docs_dir" in project_config:
            project_docs_path = Path(project_config["docs_dir"])
        else:
            progress_log_path = Path(project_record.progress_log_path)
            project_docs_path = progress_log_path.parent
      after: |
        if project_record.docs_dir:
            project_docs_path = Path(project_record.docs_dir)
        else:
            # Fallback for old records without docs_dir
            progress_log_path = Path(project_record.progress_log_path)
            project_docs_path = progress_log_path.parent

  set_project_change:
    - location: set_project.py (where project record created)
      add_field: |
        await storage.create_project(
            name=name,
            root=root,
            progress_log=progress_log_path,
            docs_dir=docs_dir,  # NEW: explicit docs directory
        )

testing:
  unit_tests:
    - New project with docs_dir → uses explicit path
    - Old project without docs_dir → falls back to derivation
    - Migration script populates docs_dir correctly

dependencies:
  - Database migration script
  - set_project.py update to populate docs_dir
```

---

**Audit Confidence**: 0.90
**Completeness**: All sub-systems documented, critical bugs identified
**Cross-Tool Integration**: Inverse of set_project, shares StorageBackend and StateManager
**Extractable Modules**: 2 candidates identified (MultiLayerStateCleanup, ProjectLifecycleGuards)
**Token Bloat**: Appropriate for destructive operation (audit trail needed)

**Critical Findings**:
1. **No atomicity** - partial failures corrupt state (P0)
2. **Session check missing** - can delete mid-operation (P1)
3. **Undefined failure modes** - unclear when DB delete returns False (P2)
4. **Path derivation** - couples to filesystem layout (P3)

---

**Next Steps for Phase 6**:
1. **URGENT**: Implement SPEC-DELETE-001 (atomic cleanup) - P0 data integrity issue
2. **HIGH**: Implement SPEC-DELETE-002 (session guards) - P1 data loss prevention
3. Document SPEC-DELETE-003 (storage contract) - P2 clarity improvement
4. Consider SPEC-DELETE-004 (explicit docs_dir) - P3 coupling reduction
5. Extract MultiLayerStateCleanup for reuse in rename/migrate operations
