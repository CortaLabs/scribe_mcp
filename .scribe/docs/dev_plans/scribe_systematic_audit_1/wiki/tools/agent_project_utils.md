# agent_project_utils.py - Forensic Audit Report

**File**: `tools/agent_project_utils.py`
**Size**: 192 LOC | 7,064 bytes
**Complexity**: Medium (Coordination Layer)
**Auditor**: ResearchAgent-K-AdvancedFeatures
**Date**: 2026-01-05

---

## 1. Overview

`agent_project_utils.py` is a **multi-tier fallback coordination layer** that bridges AgentContextManager (session isolation) with legacy state management for project discovery. It ensures agent-scoped project binding with graceful degradation.

**Purpose**: Provide session-aware project data retrieval with fallback chains for backwards compatibility.

**LOC Breakdown**:
- Primary coordination: ~92 LOC (48%) - get_agent_project_data
- Session management: ~77 LOC (40%) - ensure_agent_session, validate_agent_session
- Fallback helpers: ~23 LOC (12%) - _project_from_state_or_config, _recent_projects_snapshot

**Architectural Pattern**: **Multi-Tier Fallback Coordinator**
- No business logic in this file
- 100% delegation to infrastructure layers with defensive exception handling
- Fallback chain: AgentContextManager → storage_backend → state_manager → config files
- Tool-to-infrastructure ratio: 1:2.7 (192 LOC tool wraps 513 LOC agent_manager)

**Relationships**:
- **Depends on**: `state/agent_manager.py` (AgentContextManager, 513 LOC)
- **Depends on**: `state/agent_identity.py` (session resumption)
- **Depends on**: `tools/project_utils.py` (config loading)
- **Depends on**: `server.py` (global server_module access)
- **Used by**: `tools/vector_search.py` (session-aware search)
- **Used by**: Other tools requiring agent-scoped project context

**Complexity Drivers**:
1. **Multi-tier fallback chain** - 4 levels of fallback for project discovery
2. **Defensive exception handling** - Every external call wrapped in try/except
3. **Session coordination** - Bridges ExecutionContext → AgentIdentity → AgentContextManager
4. **Legacy compatibility** - Must work with and without AgentContextManager

---

## 2. Sub-System Breakdown

### Sub-System 1: Agent Project Data Retrieval (Lines 14-91)

**Responsibility**: Get project data for an agent using AgentContextManager as primary source, with multi-tier fallback.

**Function**: `get_agent_project_data(agent_id: str)` (14-91)

**Return Type**: `Tuple[Optional[Dict[str, Any]], List[str]]`
- Tuple of (project_data, recent_projects)

**Fallback Chain** (4 levels):
1. **Primary**: AgentContextManager.get_current_project() + storage.get_project() (lines 33-67)
2. **Secondary**: AgentContextManager + state/config fallback (lines 72-79)
3. **Tertiary**: Legacy state_manager.load() (lines 28-29, 88-91)
4. **Final**: Return (None, [])

**Workflow** (Level 1 - AgentContextManager Path):
1. Get agent_manager from server_module (line 24)
2. If no agent_manager, fallback to legacy (lines 26-29)
3. Get agent's current project from AgentContextManager (line 33)
4. If project exists, get project_name (lines 35-36)
5. Try to get project data from storage_backend (lines 38-44)
6. Convert database project to project_data dict (lines 46-53)
7. Build recent_projects list from agent + state (lines 56-66)
8. Return (project_data, recent_projects) (line 67)

**Workflow** (Level 2 - Fallback to State/Config):
1. If storage lookup fails, call `_project_from_state_or_config()` (line 72)
2. If fallback project found, augment with session metadata (lines 74-77)
3. Get recent projects snapshot (line 78)
4. Return (project_data, recent_projects) (line 79)

**Workflow** (Level 3 - Legacy Behavior):
1. If AgentContextManager unavailable, use load_active_project() (line 28)
2. Return legacy project data (line 29)

**Exception Handling**:
- Lines 68-69: Catch storage.get_project() failures, continue to fallback
- Lines 88-91: Catch any exception in AgentContextManager path, fallback to legacy

**Extractable**: NO - **INTENTIONAL COORDINATION LAYER**
- Reason: Fallback logic is specific to agent-scoped project binding migration
- Evidence: Lines 26-29, 72-79, 88-91 implement backwards compatibility strategy
- Before/After: N/A - This is the correct abstraction for migration period

**Contract**:
- **Input**: agent_id (string)
- **Output**: Tuple of (project_data dict, recent_projects list) OR (None, [])
- **Failure Policy**: Multi-tier fallback, never raise exceptions, return (None, []) as final fallback
- **State Owner**: Read-only (AgentContextManager, storage, state_manager, config files)

**Implicit Assumptions**:
1. AgentContextManager may be None (server started without session management)
2. storage_backend may fail (database unavailable)
3. state_manager always available (fallback guarantee)
4. project_utils config loading never raises (defensive in project_utils.py)

---

### Sub-System 2: Agent Session Establishment (Lines 94-138)

**Responsibility**: Ensure agent has active session, creating or resuming as needed.

**Function**: `ensure_agent_session(agent_id: str, stable_session_id: Optional[str])` (94-138)

**Return Type**: `Optional[str]` (session ID if successful, None otherwise)

**Workflow**:
1. Get agent_manager and agent_identity from server_module (lines 108-109)
2. If either unavailable, return None (lines 111-112)
3. Try to get ExecutionContext (lines 115-120)
4. Extract agent identity metadata from context (lines 122-127)
5. Resume or create session via agent_identity (lines 130-136)
6. Return session_id (line 136)

**Session Metadata Extraction** (Lines 122-127):
- If ExecutionContext available with agent_identity:
  - Extract display_name (line 126)
  - Extract instance_id (line 127)
- Store in session_metadata dict

**Stable Session ID Handling** (Line 133):
- Accepts optional `stable_session_id` parameter
- Passes through to `agent_identity.resume_agent_session()`
- Enables session persistence across MCP reconnections

**Exception Handling**:
- Lines 115-120: Catch ExecutionContext retrieval failures, set context=None
- Lines 137-138: Catch all exceptions in session creation, return None

**Extractable**: NO - **SESSION LIFECYCLE COORDINATION**
- Reason: Bridges three distinct systems (ExecutionContext, AgentIdentity, AgentContextManager)
- Evidence: Lines 115-136 orchestrate cross-system session establishment
- Coupling Justification: Session creation requires synchronized state across 3 components

**Contract**:
- **Input**: agent_id (string), stable_session_id (optional string)
- **Output**: session_id (string) if successful, None otherwise
- **Failure Policy**: Silent failure, return None (caller handles gracefully)
- **State Owner**: AgentContextManager (creates session), AgentIdentity (manages lifecycle)

---

### Sub-System 3: Session Validation (Lines 141-164)

**Responsibility**: Validate that a session is still active for an agent.

**Function**: `validate_agent_session(agent_id: str, session_id: str)` (141-164)

**Return Type**: `bool` (True if valid, False otherwise)

**Workflow**:
1. Get agent_manager from server_module (line 152)
2. If no agent_manager, return True (line 154-155) **POLICY: No session management = always valid**
3. Get agent's current project (line 159)
4. Check if session_id matches current session (lines 160-161)
5. Return validation result (lines 162-163)

**Exception Handling**:
- Lines 163-164: Catch all exceptions, return False

**Policy Decision**: Line 155 - "No session management = always valid"
- **Rationale**: Backwards compatibility with systems not using AgentContextManager
- **Impact**: Validation always passes if session management disabled
- **Alternative Considered**: Return False if no agent_manager (would break legacy systems)
- **Why Current Design**: Graceful degradation, doesn't force session management adoption

**Extractable**: NO - Simple delegation with policy layer

**Contract**:
- **Input**: agent_id (string), session_id (string)
- **Output**: bool (True = valid, False = invalid/expired)
- **Failure Policy**: Return False on any exception (fail closed for security)
- **State Owner**: AgentContextManager (read-only session check)

---

### Sub-System 4: Fallback Helper - Project from State/Config (Lines 166-179)

**Responsibility**: Load project definition from JSON state or config files as fallback.

**Function**: `_project_from_state_or_config(project_name: str)` (166-179)

**Return Type**: `Optional[Dict[str, Any]]`

**Workflow**:
1. Try loading from state_manager.load() (lines 168-173)
2. If found in state.projects, return dict (lines 171-172)
3. Fallback to load_project_config() from project_utils (lines 176-178)
4. Return None if neither source has project (line 179)

**Exception Handling**:
- Lines 173-174: Catch state_manager failures, continue to config fallback

**Extractable**: NO - Trivial fallback logic, only 13 LOC

**Contract**:
- **Input**: project_name (string)
- **Output**: project dict or None
- **Failure Policy**: Return None on all failures (silent fallback)
- **State Owner**: Read-only (state_manager, project_utils)

---

### Sub-System 5: Fallback Helper - Recent Projects Snapshot (Lines 182-192)

**Responsibility**: Return ordered list of recent projects with current name first.

**Function**: `_recent_projects_snapshot(current_name: str)` (182-192)

**Return Type**: `List[str]`

**Workflow**:
1. Initialize snapshot list with current_name (line 184)
2. Load state from state_manager (line 186)
3. Append other projects from state.recent_projects (lines 187-189)
4. Skip duplicates (line 188)
5. Return ordered list (line 192)

**Exception Handling**:
- Lines 190-191: Catch state_manager failures, return minimal list

**Extractable**: NO - Trivial helper, only 10 LOC

**Contract**:
- **Input**: current_name (string)
- **Output**: List of project names (current first, recent appended)
- **Failure Policy**: Return [current_name] on state_manager failure
- **State Owner**: Read-only (state_manager)

---

## 3. Modularization Notes

### Coordination Layer Assessment

**Conclusion**: agent_project_utils.py is an **INTENTIONAL COORDINATION LAYER** for migration to agent-scoped context and should NOT be extracted.

**Evidence**:
1. **Tool-to-infrastructure ratio**: 1:2.7 (192 LOC tool wraps 513 LOC agent_manager)
2. **Zero business logic**: 100% delegation with fallback chains
3. **Migration Strategy**: Bridges new (AgentContextManager) with legacy (state_manager)
4. **Single Responsibility**: Provide backwards-compatible agent project discovery

**Why This Design is Correct**:
- **Migration Path**: Enables gradual adoption of agent-scoped sessions
- **Backwards Compatibility**: Systems without AgentContextManager still work
- **Defensive Design**: Multi-tier fallbacks prevent total failure
- **Clean Separation**: Session logic in agent_manager, coordination here

**What Should STAY Coupled**:
- Fallback chain logic (migration-specific)
- Session coordination (bridges ExecutionContext → AgentIdentity → AgentContextManager)
- Exception handling (coordination layer must never fail)
- Legacy compatibility shims (temporary, will be removed post-migration)

**Future Evolution**:
Once migration to agent-scoped context is complete:
1. Remove state_manager fallback paths (lines 26-29, 88-91)
2. Make AgentContextManager required (remove None checks)
3. Simplify to single-tier lookup
4. **Expected LOC reduction**: ~40% (from 192 to ~115 LOC)

**Timing**: Post Phase 6 (after agent-scoped migration complete)

---

## 4. Implicit Contracts

### Contract 1: Server Module Global Access

**Assumption**: `server_module` provides global access to infrastructure components
- `get_agent_context_manager()` - Returns AgentContextManager or None
- `get_agent_identity()` - Returns AgentIdentity or None
- `get_execution_context()` - Returns ExecutionContext or None (may raise)
- `storage_backend` - Global storage instance
- `state_manager` - Global state manager instance

**Evidence**: Lines 24, 108-109, 116-118, 39, 60, 169, 186

**Risk**: If server_module globals change, all fallback chains break
**Mitigation**: Server module interface should be stable, versioned

### Contract 2: AgentContextManager Availability

**Assumption**: AgentContextManager may be None (server started without sessions)

**Evidence**: Lines 26-29 (fallback if no agent_manager), lines 111-112, lines 154-155

**Policy Decision**: Agent session management is **OPTIONAL FEATURE**
- Tools must work with and without AgentContextManager
- Fallback to legacy state_manager always available

**Risk**: None - intentional design for migration period

### Contract 3: ExecutionContext Availability

**Assumption**: `server_module.get_execution_context()` may raise exception

**Evidence**: Lines 115-120 defensive try/except

**Risk**: None - handled defensively

### Contract 4: Storage Backend Schema

**Assumption**: `storage.get_project(name)` returns dict with specific keys
- Expected keys: `name`, `repo_root`, `progress_log_path`
- Returned in lines 46-53 transformation

**Evidence**: Lines 43-53 assume dict schema

**Risk**: If ProjectRegistry schema changes, dict transformation breaks
**Mitigation**: Schema versioning in storage layer

### Contract 5: Project Utils Never Raises

**Assumption**: `load_project_config()` never raises exceptions, returns None on failure

**Evidence**: Line 176 - no try/except around call

**Risk**: Low - project_utils.py has defensive implementation
**Validation**: Confirmed in project_utils.py audit (lines 93-117 have defensive exception handling)

---

## 5. Token Analysis

### Sample 1: get_agent_project_data (Success Case - AgentContextManager Path)
**Scenario**: Agent has active project, storage lookup succeeds
**Token Estimate**: N/A - **NOT AN MCP TOOL** (internal utility function)

**Note**: This module provides utilities to OTHER tools (like vector_search.py) but doesn't expose MCP tools itself.

**Actual Token Impact**: Zero (no direct MCP tool exposure)

### Sample 2: ensure_agent_session (Success)
**Scenario**: Session created successfully
**Token Estimate**: N/A - **NOT AN MCP TOOL**

**Note**: Returns session_id string only, no formatted response

### Sample 3: validate_agent_session (Success)
**Scenario**: Session validated
**Token Estimate**: N/A - **NOT AN MCP TOOL**

**Note**: Returns boolean only

### Token Analysis Summary

**This module has ZERO token impact** - it provides internal utility functions to other tools, not MCP tool endpoints.

**Actual Token Producers**:
- `tools/vector_search.py` - Uses get_agent_project_data() internally
- Other tools that need agent-scoped context

**Token Impact**: Indirect only (via tool that calls these functions)

**Category**: N/A - Infrastructure utilities, not user-facing tools

---

## 6. Error Handling Architecture

### Policy 1: Silent Fallback on Infrastructure Unavailability

**Location**: Lines 26-29, 111-112, 154-155
**Behavior**: If AgentContextManager unavailable, fallback to legacy behavior
**Classification**: **POLICY** (not a bug)

**Rationale**:
- Agent sessions are optional feature during migration
- Tools must work in legacy mode for backwards compatibility
- Graceful degradation preferred over hard failures

**Evidence**:
- Line 26: `if not agent_manager:` returns legacy project data
- Line 111: `if not agent_manager or not agent_identity:` returns None
- Line 154: `if not agent_manager:` returns True (always valid)

**Alternative Considered**: Raise exception if AgentContextManager required
**Why Rejected**: Would force all tools to adopt agent sessions immediately (breaks backwards compatibility)

### Policy 2: Multi-Tier Fallback Chain

**Location**: Lines 33-91 (get_agent_project_data)
**Behavior**: Try multiple sources for project data, fallback on each failure
**Classification**: **POLICY** (not a bug)

**Fallback Order**:
1. AgentContextManager + storage_backend (lines 33-67)
2. AgentContextManager + state/config fallback (lines 72-79)
3. Legacy state_manager (lines 88-91)
4. Final fallback: (None, []) (line 82)

**Rationale**:
- Project data may exist in multiple places during migration
- Storage backend may be unavailable (database down)
- State manager is most reliable fallback (always available)

**Evidence**: Lines 68-69, 88-91 have try/except with fallback logic

### Policy 3: Never Raise Exceptions to Caller

**Location**: All functions (lines 88-91, 137-138, 163-164, 173-174, 190-191)
**Behavior**: Catch all exceptions, return safe defaults
**Classification**: **POLICY** (not a bug)

**Safe Defaults**:
- `get_agent_project_data`: (None, [])
- `ensure_agent_session`: None
- `validate_agent_session`: False
- `_project_from_state_or_config`: None
- `_recent_projects_snapshot`: [current_name]

**Rationale**:
- Coordination layer must never crash calling tools
- Callers can handle None/False gracefully
- Better to degrade functionality than fail completely

**Evidence**: Every function has catch-all exception handler

### Bug vs Policy Classification

**No bugs identified** in error handling. All exception handling is intentional defensive coordination for backwards compatibility.

**Design Validation**: Exception handling matches migration strategy
- New path: Try AgentContextManager
- Fallback path: Use legacy state_manager
- Final safety: Return safe defaults

---

## 7. Known Issues

### ISSUE-AGT-001: Missing Logging for Fallback Paths

**Severity**: Low (Observability)
**Location**: Lines 68-69, 88-91 (silent exception swallowing)

**Description**: When fallbacks occur (storage failure, AgentContextManager exceptions), no logging indicates which path was taken.

**Evidence**:
```python
except Exception:
    pass  # Line 69 - storage lookup failed, continuing to fallback

except Exception:
    # Fallback to legacy behavior on any error
    project, _, recent = await load_active_project(server_module.state_manager)
    return project, list(recent)  # Line 88-91 - no logging
```

**Impact**:
- Developers can't diagnose why fallbacks triggered
- Migration tracking difficult (can't measure AgentContextManager adoption)
- Silent failures hide infrastructure problems

**Recommendation**: Add debug-level logging
```python
except Exception as e:
    logging.debug(
        f"Storage lookup failed for {project_name}, using state/config fallback: {e}",
        extra={"agent_id": agent_id, "fallback_tier": 2}
    )
```

**Not a Bug Because**: Functionality works correctly, just missing observability

---

### ISSUE-AGT-002: ExecutionContext Retrieval Uses hasattr Instead of Proper Check

**Severity**: Low (Code Quality)
**Location**: Lines 116-118

**Description**: Uses `hasattr(server_module, "get_execution_context")` instead of proper interface check.

**Evidence**:
```python
if hasattr(server_module, "get_execution_context"):
    try:
        context = server_module.get_execution_context()
```

**Impact**:
- Fragile dependency on server_module implementation details
- Breaks if method renamed or moved
- Makes refactoring harder

**Recommendation**: Use protocol/interface check or feature flags
```python
try:
    context = getattr(server_module, 'get_execution_context', lambda: None)()
except Exception:
    context = None
```

**Not Critical Because**: Works reliably in practice, server_module interface stable

---

### ISSUE-AGT-003: Tight Coupling to server_module Global State

**Severity**: Medium (Architectural Coupling)
**Location**: Lines 24, 39, 60, 108-109, 116-118, 169, 186

**Description**: All functions depend on global `server_module` import, making unit testing difficult.

**Evidence**:
```python
from scribe_mcp import server as server_module

agent_manager = server_module.get_agent_context_manager()  # Line 24
storage = server_module.storage_backend  # Line 39
state = await server_module.state_manager.load()  # Line 60, 169, 186
```

**Impact**:
- Unit testing requires mocking global server_module
- Functions can't be tested in isolation
- Harder to refactor server architecture

**Recommendation**: Dependency injection pattern
```python
async def get_agent_project_data(
    agent_id: str,
    agent_manager: Optional[AgentContextManager] = None,
    storage = None,
    state_manager: Optional[StateManager] = None
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    # Use provided dependencies or fall back to globals
    agent_manager = agent_manager or server_module.get_agent_context_manager()
    ...
```

**Risk Level**: Medium - Makes testing harder, couples to global state
**Timing**: Address during Phase 6 refactoring (after agent session migration complete)

---

## 8. Implementation Specs

### SPEC-AGT-001: Add Fallback Path Logging

**Priority**: Low (Observability)
**Bucket**: [BUCKET:error_handling]
**Estimated Impact**: Low (debugging aid during migration)

**Motivation**: Track which fallback paths are used to measure agent session adoption and diagnose infrastructure issues.

**Implementation**:
```yaml
name: Fallback Path Logging
location: tools/agent_project_utils.py
bucket: error_handling

changes:
  - location: Line 69
    action: add_logging
    before: |
      except Exception:
          pass
    after: |
      except Exception as e:
          logging.debug(
              f"Storage lookup failed for project {project_name}, falling back to state/config: {e}",
              extra={
                  "agent_id": agent_id,
                  "project_name": project_name,
                  "fallback_tier": 2,
                  "error_type": type(e).__name__
              }
          )

  - location: Line 88
    action: add_logging
    before: |
      except Exception:
          # Fallback to legacy behavior on any error
          project, _, recent = await load_active_project(server_module.state_manager)
          return project, list(recent)
    after: |
      except Exception as e:
          logging.debug(
              f"AgentContextManager path failed for {agent_id}, using legacy fallback: {e}",
              extra={
                  "agent_id": agent_id,
                  "fallback_tier": 3,
                  "error_type": type(e).__name__
              }
          )
          project, _, recent = await load_active_project(server_module.state_manager)
          return project, list(recent)

rationale:
  - Enable monitoring of fallback usage
  - Track agent session adoption rate
  - Diagnose infrastructure failures

implementation_notes:
  - Use debug level (not info) to avoid noise
  - Include structured metadata for log aggregation
  - Don't expose to users (internal observability only)

testing:
  - Mock agent_manager to return None, verify debug log
  - Mock storage to raise exception, verify tier-2 fallback logged
  - Verify no logs for successful happy path
```

**Affected Lines**: 69, 88, (optionally 137, 163, 173, 190)

**Testing Requirements**:
- Unit tests with log capture
- Integration tests for each fallback tier
- Verify no performance impact

**Implementation Priority**: Low (nice-to-have during migration, not critical)

---

### SPEC-AGT-002: Simplify Post-Migration (Future)

**Priority**: Low (Future Enhancement)
**Bucket**: [BUCKET:migration_cleanup]
**Estimated Impact**: Medium (reduce complexity after migration complete)

**Motivation**: Once agent-scoped session migration is 100% complete, remove legacy fallback paths.

**Implementation**:
```yaml
name: Post-Migration Simplification
location: tools/agent_project_utils.py
bucket: migration_cleanup

preconditions:
  - Agent-scoped session migration 100% complete
  - All tools using AgentContextManager
  - Legacy state_manager project tracking deprecated

changes:
  - function: get_agent_project_data
    action: remove_fallback_paths
    remove_lines: [26-29, 72-79, 88-91]
    expected_loc_reduction: ~40 LOC (from 92 to ~52)

    before_migration: |
      # Multi-tier fallback chain (4 levels)
      if not agent_manager:
          # Legacy fallback
          project, _, recent = await load_active_project(...)
          return project, list(recent)

      try:
          # AgentContextManager path with fallbacks
          ...
      except Exception:
          # Final fallback to legacy
          ...

    after_migration: |
      # Simple single-tier lookup (AgentContextManager required)
      agent_manager = server_module.get_agent_context_manager()
      if not agent_manager:
          raise RuntimeError("AgentContextManager required but not available")

      agent_project = await agent_manager.get_current_project(agent_id)
      if not agent_project:
          return None, []

      # Direct lookup, no fallbacks needed
      ...

  - function: ensure_agent_session
    action: require_agent_manager
    change: Make agent_manager required (remove None check at line 111)

  - function: validate_agent_session
    action: require_agent_manager
    change: Remove "always valid if no agent_manager" policy (line 154-155)

expected_outcomes:
  - LOC reduction: 40% (192 → ~115 LOC)
  - Complexity reduction: Remove 3 fallback tiers
  - Error clarity: Explicit failures instead of silent fallbacks
  - Testing simplification: No need to test fallback paths

risks:
  - Breaking change if any tools still use legacy state_manager
  - Requires coordinated rollout across all tools

mitigation:
  - Feature flag for migration period
  - Gradual deprecation warnings
  - Comprehensive integration tests

timing:
  - After Phase 6 complete
  - After 100% agent session adoption measured
  - Coordinate with major version bump
```

**Estimated Timeline**: 6-12 months post Phase 6 (depends on adoption rate)

---

**End of agent_project_utils.py Audit**

**Summary**:
- Architecture: Intentional multi-tier fallback coordination layer (1:2.7 LOC ratio to agent_manager)
- Extractable modules: 0 (coordination logic is migration-specific)
- Known issues: 3 (all low-medium severity observability/refactoring opportunities)
- Token profile: N/A (not an MCP tool, provides utilities to other tools)
- Error handling: All intentional policy for backwards compatibility
- Recommendation: **Keep as coordination layer, simplify post-migration (SPEC-AGT-002)**
- Future state: 40% LOC reduction possible after agent session migration complete
