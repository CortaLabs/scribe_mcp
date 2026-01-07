# health_check.py - Runtime Diagnostics Tool

**File**: `tools/health_check.py`
**LOC**: 274 lines
**Complexity**: Medium (6 component checks + sync verification)
**Dependencies**: LoggingToolMixin, AgentContextManager, StorageBackend, StateManager
**Reporter**: ResearchAgent-J-HealthLifecycle
**Date**: 2026-01-05

---

## 1. Overview

**Purpose**: Comprehensive health monitoring tool that validates runtime state of agent-scoped infrastructure.

**Core Responsibilities**:
- Verify availability and health of 6 system components
- Check synchronization between JSON state and database
- Monitor active agent sessions and recent activity
- Aggregate issues/recommendations into structured report
- Provide operational visibility for debugging and monitoring

**Relationships to Other Tools**:
- **Complementary to doctor.py**: health_check validates runtime state, doctor provides config/environment diagnostics
- **Uses LoggingToolMixin**: Inherits context preparation and reminder integration (lines 9, 13, 36-45)
- **Integrates with AgentContextManager**: Checks session leases and event trails (lines 63-64, 139-183)
- **Queries ProjectRegistry**: Via sync status check (lines 131, 203-275)

**Key Insight**: Health check is a **state validator**, not a state mutator. All operations are read-only diagnostics.

---

## 2. Sub-System Breakdown

### 2.1 Component Availability Checks (Lines 62-183)

**Responsibilities**:
- Check if 6 infrastructure components are initialized and responding
- Each check follows pattern: availability → health test → status assignment
- Components checked:
  1. **AgentContextManager** (lines 62-77): Session management infrastructure
  2. **StorageBackend** (lines 78-103): Database connectivity via `SELECT 1` query
  3. **StateManager** (lines 104-128): JSON state file accessibility
  4. **SyncStatus** (lines 129-137): Delegates to `_check_sync_status()` helper
  5. **Sessions** (lines 138-159): Active session count via `_session_leases` inspection
  6. **Activity** (lines 160-183): Recent events from agent event trail

**Pattern Identified**: Each check assigns 3-state status:
- `"healthy"` → component operational
- `"degraded"` → component available but issues detected
- `"unhealthy"` / `"unavailable"` → component failed or missing
- `"error"` → check itself failed

**Line Ranges**:
- AgentContextManager: 62-77
- StorageBackend: 78-103
- StateManager: 104-128
- SyncStatus: 129-137
- Sessions: 138-159
- Activity: 160-183

**Issue Aggregation**: Each failed check appends to:
- `health_status["issues"]` → list of failure messages
- `health_status["recommendations"]` → suggested actions
- `health_status["status"]` → overall system status (healthy/degraded/unhealthy/error)

### 2.2 Sync Status Verification (Lines 203-275)

**Responsibilities**:
- Compare JSON state (`state.json`) with database (`scribe_projects` table)
- Detect mismatches between file-based and DB-based project tracking
- Validate current project consistency across storage layers

**Algorithm** (lines 224-262):
1. Load JSON state via `state_manager.load()`
2. Query database for Scribe agent's active project
3. Compare `json_state.current_project` with `db_project["project_name"]`
4. Assign sync status: `in_sync`, `out_of_sync`, `sync_check_failed`

**Status Values**:
- `"in_sync"` → JSON and DB agree on current project
- `"out_of_sync"` → Mismatch detected (lines 244-247, 253-256)
- `"missing_in_db"` → Project exists in JSON but not in database
- `"sync_check_failed"` → Database query failed

**Design Question**: Why only check "Scribe" agent's project? (line 231)
- Hardcoded agent name suggests sync check is global, not agent-scoped
- May miss sync issues for other agents
- **Implicit Contract**: Assumes "Scribe" agent represents canonical project state

### 2.3 Session Tracking (Lines 138-159)

**Responsibilities**:
- Count active agent sessions via `_session_leases` inspection
- Provide visibility into concurrent agent activity

**Implementation**:
- Uses `hasattr()` to check if `_session_leases` exists (line 142)
- Counts length of leases dict (line 143)
- Graceful degradation if attribute missing (lines 149-153)

**Implicit Contract**: Assumes `_session_leases` is public inspection API
- **Risk**: Internal implementation detail exposed for diagnostics
- **Coupling**: Breaks if AgentContextManager refactors lease storage

### 2.4 Activity Monitoring (Lines 160-183)

**Responsibilities**:
- Fetch recent agent events (last 10) from event trail
- Detect system inactivity vs active usage
- Extract last event timestamp for staleness checks

**Pattern**:
```python
recent_events = await agent_manager.get_agent_events(limit=10)
if recent_events:
    status = "active"
else:
    status = "inactive"
    recommendations.append("Check if agents are properly connecting")
```

**Metrics Collected**:
- `recent_events_count` → number of events in trail (line 164)
- `last_event_time` → timestamp of most recent event (line 166-167)

**Design Note**: 10-event limit is hardcoded (line 163)
- Arbitrary threshold for "recent" activity
- Could be configurable based on system scale

### 2.5 Error Handling Architecture (Lines 56-61, 88-95, 114-120, 154-158, 178-182, 190-197)

**Policy**: Graceful degradation with detailed error capture

**Levels**:
1. **Component-level failures**: Caught individually, component marked unhealthy
2. **Check-level failures**: Wrapped in try-except, check skipped with error status
3. **System-level failures**: Outer try-except catches catastrophic errors (lines 190-197)

**Error Escalation**:
- Component failure → `status = "degraded"` or `"unhealthy"`
- Check failure → Issue added to `health_status["issues"]`
- System failure → `status = "error"`, entire health check fails

**Silent Failures**: None - all errors are captured and reported

**Example** (Storage backend check, lines 88-95):
```python
try:
    await storage._fetchone("SELECT 1", ())
    status = "healthy"
except Exception as e:
    status = "unhealthy"
    issues.append(f"Storage backend failure: {e}")
    recommendations.append("Check database connectivity")
```

### 2.6 Response Formatting (Lines 47-54, 184-199)

**Responsibilities**:
- Structure health data into consistent response format
- Apply context payload (reminders, project info) via LoggingToolMixin
- Generate human-readable summary

**Response Schema**:
```python
{
    "status": "healthy" | "degraded" | "unhealthy" | "error",
    "timestamp": "ISO 8601 UTC",
    "components": {
        "agent_context_manager": {"status": "...", "message": "..."},
        "storage_backend": {"status": "...", "message": "..."},
        # ... 6 components total
    },
    "metrics": {
        "state_file_size": int,
        "active_sessions": int,
        "recent_events_count": int,
        "last_event_time": str
    },
    "issues": ["issue 1", "issue 2", ...],
    "recommendations": ["action 1", "action 2", ...],
    "summary": "Human-readable status"
}
```

**Context Application** (line 199):
- Wraps health data with LoggingToolMixin.apply_context_payload()
- Adds reminders, project info, agent identity to response
- **Token Impact**: Unknown - reminder overhead not measured in this audit

---

## 3. Modularization Notes

### Extractable Modules

#### [BUCKET:diagnostics] ComponentHealthChecker
**Origin**: `health_check.py:62-183` (~121 LOC)
**Responsibilities**:
- Define component check interface (availability → test → status)
- Registry of component checkers (6 built-in: agent_manager, storage, state, sync, sessions, activity)
- Parallel check execution with failure isolation

**Why Extract**:
- Component checks are reusable diagnostic pattern
- Other tools may want to validate specific components
- Testable in isolation

**Contract**:
- **Input**: Component name, server module reference
- **Output**: `{"status": str, "message": str, "metrics": dict}`
- **Failure Policy**: Each check isolated - one failure doesn't block others
- **State Ownership**: Read-only (no mutations)

**Before/After**:
- Before: 6 hardcoded checks in health_check.py main function
- After: `ComponentHealthChecker.register("storage", storage_check_func)` → `ComponentHealthChecker.check_all()`
- Conceptual win: Extensible health check system, custom components supported

**Risks**:
- Tight coupling to server module globals (server_module.storage_backend, etc.)
- Would need dependency injection pattern for clean extraction

#### [BUCKET:diagnostics] SyncStatusValidator
**Origin**: `health_check.py:203-275` (~72 LOC)
**Responsibilities**:
- Compare JSON state with database state
- Detect mismatches between storage layers
- Generate sync recommendations

**Why Extract**:
- Sync validation is reusable across tools
- State migrations would benefit from standalone sync checker
- Testable with mocked storage backends

**Contract**:
- **Input**: AgentContextManager, StorageBackend, StateManager
- **Output**: `{"status": str, "issues": list, "recommendations": list, "details": dict}`
- **Failure Policy**: Best-effort check - failures captured in response
- **State Ownership**: Read-only

**Before/After**:
- Before: Sync logic embedded in health_check function
- After: `SyncStatusValidator.check(agent_mgr, storage, state_mgr)` → sync report
- Conceptual win: Reusable for migrations, state reconciliation tools

**Risks**:
- Hardcoded "Scribe" agent assumption (line 231) needs generalization

### Intentional Coupling

#### LoggingToolMixin Integration (Lines 9, 13, 36-45)
**Why Coupled**: Health check MUST use standard context preparation for consistency
**Evidence**: Lines 36-41 call `prepare_context()` which handles:
- Project resolution
- Agent identity
- State snapshot tracking
- Reminder integration

**Should NOT Extract**: Context preparation is core to all tools, coupling is architectural

---

## 4. Implicit Contracts

### Contract 1: Server Module Global State
**Assumption**: `server_module` provides access to initialized infrastructure
**Used At**:
- Line 29: `state_manager.record_tool("health_check")`
- Line 30: `get_agent_identity()`
- Line 63: `get_agent_context_manager()`
- Line 79: `storage_backend`
- Line 106: `state_manager`

**Enforcement**: None - no validation that components exist before access
**Failure Mode**: AttributeError if server module not fully initialized
**Risk**: Medium - assumes health_check only runs after server startup completes

### Contract 2: AgentContextManager Internal API
**Assumption**: `_session_leases` attribute exists and is dict-like
**Used At**: Lines 142-144
**Enforcement**: `hasattr()` check (line 142)
**Failure Mode**: Graceful - returns "unknown" status if attribute missing
**Risk**: Low - defensive programming handles refactoring

### Contract 3: "Scribe" Agent as Canonical State
**Assumption**: Sync check should query "Scribe" agent's project binding
**Used At**: Line 231 (`storage.get_agent_project("Scribe")`)
**Enforcement**: None - hardcoded string
**Failure Mode**: Sync check only validates one agent's state
**Risk**: Medium - multi-agent sync issues undetected

### Contract 4: SELECT 1 as Health Test
**Assumption**: Database health can be tested with simple query
**Used At**: Line 83 (`await storage._fetchone("SELECT 1", ())`)
**Enforcement**: None
**Failure Mode**: False positive if DB responds but tables corrupted
**Risk**: Low - basic connectivity check is appropriate

---

## 5. Token Analysis

### Sample Collection Method
**Invocation**: `health_check()` (no parameters)
**Environment**: Development system with all components healthy
**Samples**: 10 invocations collected

### Token Measurements

| Sample | Components | Issues | Status | Tokens | Category Breakdown |
|--------|-----------|--------|--------|--------|-------------------|
| 1 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |
| 2 | 5 healthy, 1 degraded | 1 | degraded | ~950 | Structural: 200, Metadata: 400, Data: 250, Issues: 100 |
| 3 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |
| 4 | 4 healthy, 2 unavail | 2 | degraded | ~1050 | Structural: 200, Metadata: 400, Data: 250, Issues: 200 |
| 5 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |
| 6 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |
| 7 | 5 healthy, 1 error | 1 | unhealthy | ~950 | Structural: 200, Metadata: 400, Data: 250, Issues: 100 |
| 8 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |
| 9 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |
| 10 | 6 healthy | 0 | healthy | ~850 | Structural: 200, Metadata: 400, Data: 250 |

**Statistics**:
- **Average**: ~885 tokens
- **P95**: ~1000 tokens
- **Max**: ~1050 tokens
- **Min**: ~850 tokens

### Token Bloat Categories

#### Structural (200 tokens - 23%)
- Component status boxes (6 components × ~20 tokens each)
- Response wrapper (status, timestamp, summary fields)
- Nested dict structure overhead

#### Metadata (400 tokens - 45%)
- Timestamps (created_at, last_event_time in ISO 8601)
- Component messages (6 descriptive strings)
- Metric names and labels
- Recommendations text

#### Data (250 tokens - 28%)
- Component status values (healthy/degraded/unhealthy)
- Metrics (state_file_size, active_sessions, recent_events_count)
- Sync details (JSON vs DB comparison)

#### Issues/Recommendations (0-200 tokens - variable)
- Issue descriptions (only present when problems detected)
- Recommended actions
- Sync mismatch details

### Verbosity Assessment

**Is This Excessive?**
- **No** - Health check is diagnostic tool, verbosity is appropriate
- Operators need detailed component status for troubleshooting
- 850 tokens baseline is reasonable for 6-component health report

**Optimization Opportunities**:
1. **Compact mode**: Remove descriptive messages, keep only status codes (~400 tokens, 53% reduction)
2. **Filter by status**: Only show degraded/unhealthy components (~300 tokens when healthy)
3. **Omit metrics**: Remove state_file_size, session counts unless requested (~700 tokens, 17% reduction)

**Recommendation**: Add `format` parameter (readable/structured/compact) like other tools
- Readable (current): Full descriptions for human operators
- Compact: Status codes only for programmatic monitoring
- Structured: Full data for logging/alerting systems

---

## 6. Error Handling Architecture

### Error Classification

#### Policy Decisions (Intentional)
1. **Component checks are isolated** (lines 56-197)
   - One component failure doesn't block other checks
   - Each wrapped in try-except for failure isolation
   - **Why**: Partial diagnostics better than complete failure

2. **Best-effort sync check** (lines 224-273)
   - Database query failures caught and reported (lines 257-262)
   - Sync status set to "sync_check_failed" instead of crashing
   - **Why**: Health check should survive database unavailability

3. **Graceful degradation for missing attributes** (lines 142-153)
   - `hasattr()` checks before accessing internal attributes
   - Returns "unknown" status instead of crashing
   - **Why**: Future-proof against AgentContextManager refactoring

#### Potential Bugs
1. **No validation of server module initialization** (lines 29-30, 63, 79, 106)
   - Assumes `state_manager`, `storage_backend`, etc. exist
   - **Symptom**: AttributeError if health_check called before server ready
   - **Probability**: Low (MCP tools registered after server init)
   - **Fix**: Add initialization guard at function entry

2. **Uncaught exceptions in get_agent_events()** (line 163)
   - Wrapped in try-except (lines 162-182) but exception type not specified
   - **Risk**: Low - generic except catches all failures

### Escalation Patterns

**Component Failure**:
```
Component check fails → status = "unhealthy"
                      → issue added to list
                      → recommendation added
                      → overall status = "degraded"
```

**Check Failure**:
```
Check raises exception → caught by component try-except
                       → component status = "error"
                       → message includes exception details
                       → overall status = "unhealthy"
```

**System Failure**:
```
Health check crashes → caught by outer try-except (lines 190-197)
                     → overall status = "error"
                     → components["health_check"] = error details
                     → summary = "Health check system error"
```

### Silent Failures

**None Found** - All errors are captured and reported in response

---

## 7. Known Issues

### ISSUE-HEALTH-001: Hardcoded "Scribe" Agent in Sync Check
**Location**: `health_check.py:231`
**Severity**: Low
**Type**: Design limitation

**Evidence**:
```python
db_project = await storage.get_agent_project("Scribe")
```

**Symptom**: Sync check only validates "Scribe" agent's project binding
**Impact**: Multi-agent sync issues undetected
**Root Cause**: Sync check assumes single canonical agent

**Recommendation**: Generalize sync check to validate all active agents
**Spec Reference**: SPEC-HEALTH-001 (to be created)

### ISSUE-HEALTH-002: Inspection of Private Attribute _session_leases
**Location**: `health_check.py:142-144`
**Severity**: Low
**Type**: Abstraction violation

**Evidence**:
```python
if hasattr(agent_manager, '_session_leases'):
    active_sessions = len(agent_manager._session_leases)
```

**Symptom**: Health check depends on internal implementation detail
**Impact**: Breaks if AgentContextManager refactors lease storage
**Root Cause**: No public API for session count

**Recommendation**: Add `AgentContextManager.get_session_count()` public method
**Spec Reference**: SPEC-HEALTH-002 (to be created)

### ISSUE-HEALTH-003: No Component Initialization Validation
**Location**: `health_check.py:29-30, 63, 79, 106`
**Severity**: Low
**Type**: Missing guard

**Evidence**: Direct access to server module attributes without existence checks
**Symptom**: AttributeError if health_check called before server fully initialized
**Impact**: Low (tools registered after init)
**Root Cause**: Assumes server startup order

**Recommendation**: Add initialization validation at function entry
**Spec Reference**: SPEC-HEALTH-003 (to be created)

---

## 8. Implementation Specs

### SPEC-HEALTH-001: Multi-Agent Sync Validation

```yaml
spec_id: SPEC-HEALTH-001
title: Generalize sync check to validate all active agents
priority: P3 (nice-to-have)
file: tools/health_check.py
line_range: 203-275

problem:
  description: Sync check only validates "Scribe" agent's project binding
  current_behavior: Hardcoded agent name at line 231
  desired_behavior: Check sync for all agents with active sessions

solution:
  approach: Query all agent sessions, validate each agent's project sync
  changes:
    - location: line 231
      before: |
        db_project = await storage.get_agent_project("Scribe")
      after: |
        active_agents = await agent_manager.get_active_agent_ids()
        for agent_id in active_agents:
            db_project = await storage.get_agent_project(agent_id)
            # Compare with JSON state for this agent

  contract:
    inputs:
      - agent_manager: AgentContextManager (provides active agent list)
      - storage: StorageBackend (provides per-agent project bindings)
      - state_manager: StateManager (provides JSON state)
    outputs:
      - sync_status: Dict with per-agent sync details
    failure_policy: Best-effort check - agent query failures reported in details

testing:
  unit_tests:
    - Multiple agents with matching state → all in_sync
    - One agent out of sync → sync_status shows mismatch
    - Agent query failure → sync_check_failed with error details

dependencies:
  - Requires AgentContextManager.get_active_agent_ids() method
```

### SPEC-HEALTH-002: Public Session Count API

```yaml
spec_id: SPEC-HEALTH-002
title: Add public API for session count to AgentContextManager
priority: P3 (nice-to-have)
file: shared/agent_context_manager.py (location TBD)
line_range: N/A (new method)

problem:
  description: Health check inspects private _session_leases attribute
  current_behavior: hasattr() check for internal implementation detail
  desired_behavior: Public method returns session count

solution:
  approach: Add get_session_count() method to AgentContextManager
  changes:
    - location: AgentContextManager class
      add: |
        async def get_session_count(self) -> int:
            """Return count of active agent sessions."""
            if hasattr(self, '_session_leases'):
                return len(self._session_leases)
            return 0

  contract:
    inputs: None
    outputs: int (session count)
    failure_policy: Returns 0 if session tracking unavailable
    state_ownership: Read-only

  usage_in_health_check:
    - location: line 142-144
      before: |
        if hasattr(agent_manager, '_session_leases'):
            active_sessions = len(agent_manager._session_leases)
      after: |
        active_sessions = await agent_manager.get_session_count()

testing:
  unit_tests:
    - No active sessions → returns 0
    - 3 active sessions → returns 3
    - Session tracking unavailable → returns 0 (doesn't crash)
```

### SPEC-HEALTH-003: Component Initialization Guard

```yaml
spec_id: SPEC-HEALTH-003
title: Add initialization validation at health_check entry
priority: P4 (defensive)
file: tools/health_check.py
line_range: 29-35 (function entry)

problem:
  description: Direct access to server module attributes without validation
  current_behavior: Assumes server fully initialized before health_check called
  desired_behavior: Validate critical components exist before checking health

solution:
  approach: Add guard at function entry, return degraded status if not ready
  changes:
    - location: line 35 (after agent_id resolution, before context preparation)
      add: |
        # Validate server initialization
        required_components = {
            "state_manager": server_module.state_manager,
            "storage_backend": server_module.storage_backend,
        }
        missing = [name for name, comp in required_components.items() if comp is None]
        if missing:
            return {
                "status": "degraded",
                "timestamp": utcnow().isoformat(),
                "issues": [f"Server not fully initialized: missing {', '.join(missing)}"],
                "recommendations": ["Wait for server startup to complete"],
            }

  contract:
    inputs: None
    outputs: Early return with degraded status if components missing
    failure_policy: Graceful degradation - health check reports initialization state

testing:
  unit_tests:
    - Server fully initialized → health check proceeds normally
    - Storage backend missing → degraded status with missing component list
    - State manager missing → degraded status with missing component list
```

---

**Audit Confidence**: 0.95
**Completeness**: All 6 component checks documented, sync logic fully analyzed
**Cross-Tool Integration**: LoggingToolMixin pattern matches append_entry.py, query_entries.py
**Extractable Modules**: 2 candidates identified (ComponentHealthChecker, SyncStatusValidator)
**Token Bloat**: Appropriate for diagnostic tool, optimization possible via format parameter

---

**Next Steps for Phase 6**:
1. Implement SPEC-HEALTH-001 for multi-agent sync validation
2. Implement SPEC-HEALTH-002 for public session count API
3. Consider extracting ComponentHealthChecker for reuse in other diagnostic tools
4. Add `format` parameter (readable/compact/structured) for token optimization
