---
id: manage_docs_agent_ux-research-session-isolation-bug-20260119
title: "\U0001F52C Research Session Isolation Bug 20260119 \u2014 manage_docs_agent_ux"
doc_name: RESEARCH_SESSION_ISOLATION_BUG_20260119
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

# 🔬 Research Session Isolation Bug 20260119 — manage_docs_agent_ux
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 04:13:36 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Investigate why logs from one agent/project appear in a different project's progress log, breaking audit trail trust.

**Root Cause Summary:**
The session isolation bug stems from **multiple session ID sources with inconsistent derivation** and a **global state fallback path** that allows cross-project contamination when session-based resolution fails.

**Key Takeaways:**
1. **Session ID Mismatch**: Three different session ID types (context_session_id, stable_session_id, session_id) with fallback cascade can produce different keys for the same logical session between set_project and append_entry calls.
2. **Global State Fallback**: When ExecutionContext is missing or session resolution fails, the system falls back to `state.json` `current_project` which is shared across ALL agents connected to the same MCP server.
3. **Shared Singleton Architecture**: Single MCP server instance shares state_manager, storage_backend, and router_context_manager - isolation depends entirely on correct context propagation.

**Impact:** Critical - Audit trail corruption makes it impossible to trust which project logs belong to. Multi-agent workflows are fundamentally broken.

**Confidence:** 95% - Root cause verified through comprehensive code analysis with file:line references.
<!-- ID: research_scope -->
---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent

**Investigation Window:** 2026-01-19 — 2026-01-20

**Focus Areas:**
- [x] Project context flow from set_project() to append_entry()
- [x] State management in .scribe/state.json
- [x] Agent session isolation via AgentContextManager
- [x] MCP server concurrency model and singleton patterns
- [x] Session ID derivation and session_projects table
- [x] Global state fallback in logging_utils.py

**Dependencies & Constraints:**
- MCP Python SDK provides transport layer session IDs that may be unstable
- Claude Code subagents share parent's MCP connection
- Database (SQLite) stores session-project bindings
- JSON state file (state.json) provides fast cache but is shared globally
<!-- ID: findings -->
---
## Findings
<!-- ID: findings -->

### Finding 1: Global State File is Shared Mutable State
- **Summary:** `.scribe/state.json` contains a single `current_project` field (line 2) that is shared across ALL agents/sessions connected to the same MCP server. When Agent A calls `set_project('X')`, it updates this global value, which can then be used by Agent B if session-based resolution fails.
- **Evidence:** 
  - File: `.scribe/state.json`, line 2: `"current_project": "manage_docs_agent_ux"`
  - File: `state/manager.py`, line 189: `current_project = name if mirror_global else existing.get("current_project")`
- **Confidence:** 95%

### Finding 2: 4-Layer Project Resolution Cascade with Global Fallback
- **Summary:** `resolve_logging_context()` in `shared/logging_utils.py` uses a 4-layer resolution cascade: 1) Session-scoped project, 2) Explicit project override, 3) Agent-specific context, 4) GLOBAL FALLBACK. The global fallback (lines 267-306) is triggered when `exec_context is None and not project`.
- **Evidence:**
  - File: `shared/logging_utils.py`, lines 41-312
  - Line 269: `if not project and not exec_context:` triggers global fallback
  - Line 272: `active_project, active_name, recent = await load_active_project(server_module.state_manager)`
- **Confidence:** 95%

### Finding 3: Session ID Mismatch Between Operations
- **Summary:** Three different session ID sources with fallback cascade can produce different keys: `stable_session_id`, `context_session_id`, `session_id`. The session key for storing project binding may differ from the key used to query it.
- **Evidence:**
  - File: `tools/set_project.py`, line 513: `session_key = stable_session_id or context_session_id or session_id`
  - File: `shared/logging_utils.py`, lines 91-92: `session_key = getattr(exec_context, "stable_session_id", None) or getattr(exec_context, "session_id", None)`
- **Confidence:** 90%

### Finding 4: ExecutionContext Uses contextvars (Proper Isolation When Used)
- **Summary:** `ExecutionContext` uses Python's `contextvars.ContextVar` which provides proper async context isolation per-request. However, isolation only works if context is properly set via the router wrapper.
- **Evidence:**
  - File: `shared/execution_context.py`, line 15: `_CURRENT_CONTEXT: contextvars.ContextVar[...] = contextvars.ContextVar(...)`
  - File: `server.py`, line 614: `token = router_context_manager.set_current(exec_context)`
- **Confidence:** 95%

### Finding 5: Single MCP Server Shares All Singletons
- **Summary:** A single MCP server instance handles ALL connected clients. Global singletons (`state_manager`, `storage_backend`, `router_context_manager`) are shared. Per-request isolation relies entirely on correct context propagation through the router wrapper.
- **Evidence:**
  - File: `server.py` - singleton pattern for state_manager, storage_backend, router_context_manager
  - No per-connection isolation at server level
- **Confidence:** 95%

### Finding 6: Subagents May Not Receive Proper Context
- **Summary:** When Claude Code spawns subagents (Task tool), they may share the parent's MCP connection but not receive proper ExecutionContext if the MCP client doesn't propagate context payload correctly. This causes fallback to global state.
- **Evidence:**
  - File: `server.py`, lines 395-399: `context_payload = arguments.pop("context", None)` - relies on client providing context
  - If `context_payload` is empty or missing session identity, global fallback occurs
- **Confidence:** 85%

### Additional Notes
- The bug is most likely to occur when:
  1. Multiple agents work concurrently on different projects
  2. Subagents are spawned without proper context propagation
  3. MCP transport session IDs are unstable between requests
- Repo scoping (lines 274-294) provides partial protection for cross-repo contamination but not within same repo
<!-- ID: technical_analysis -->
---
## Technical Analysis
<!-- ID: technical_analysis -->

### State Flow Diagram

```
                    MCP Client Request
                           │
                           ▼
                    ┌──────────────┐
                    │ server.py    │
                    │ router wrap  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        context_payload  arguments   transport_id
              │            │            │
              └────────────┴────────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ derive_session_      │
                │ identity_preview()   │
                │ (server.py:326)      │
                └──────────┬───────────┘
                           │
                           ▼
                   stable_session_id
                           │
                           ▼
                ┌──────────────────────┐
                │ build_execution_     │
                │ context()            │
                │ (execution_context.py│
                │  :131)               │
                └──────────┬───────────┘
                           │
                           ▼
                   ExecutionContext
                   (stored in ContextVar)
                           │
                           ▼
                    ┌──────────────┐
                    │ Tool Handler │
                    │ (set_project/│
                    │  append_entry)│
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    set_project stores           append_entry queries
    session_key -> project       session_key -> project
              │                         │
              └────────────┬────────────┘
                           │
            ┌──────────────┴──────────────┐
            │  IF session_key MISMATCH:   │
            │                              │
            │  Query returns NULL          │
            │           │                  │
            │           ▼                  │
            │  Global fallback triggered   │
            │  (state.json current_project)│
            │           │                  │
            │           ▼                  │
            │  WRONG PROJECT USED!         │
            └──────────────────────────────┘
```

### Code Patterns Identified

**Anti-Pattern 1: Session Key Fallback Cascade**
```python
# set_project.py:513
session_key = stable_session_id or context_session_id or session_id

# logging_utils.py:91-92
session_key = getattr(exec_context, "stable_session_id", None) or getattr(exec_context, "session_id", None)
```
Problem: If stable_session_id is available during set_project but not during append_entry, different keys are used.

**Anti-Pattern 2: Silent Global Fallback**
```python
# logging_utils.py:269
if not project and not exec_context:
    active_project, active_name, recent = await load_active_project(...)
```
Problem: No warning or error - silently uses potentially stale global state.

**Anti-Pattern 3: Shared Mutable State**
```python
# state.json
{"current_project": "X", ...}  # Single global value, not per-session
```
Problem: Any agent can overwrite, affecting all other agents.

### System Interactions

1. **MCP Client -> Server**: Provides transport_session_id (potentially unstable)
2. **Server -> RouterContextManager**: Derives stable_session_id from identity hash
3. **RouterContextManager -> ContextVar**: Stores ExecutionContext for current request
4. **Tool -> storage_backend**: Stores/queries session-project binding
5. **Tool -> state_manager**: Updates JSON state (includes global current_project)

### Risk Assessment

- [x] **CRITICAL**: Multi-agent workflows produce corrupted audit trails
- [x] **HIGH**: Parallel agent work on same repo writes to wrong projects
- [x] **HIGH**: Debugging becomes impossible when logs are misattributed
- [x] **MEDIUM**: Cross-repo protection exists but same-repo contamination is not prevented
<!-- ID: recommendations -->
---
## Recommendations
<!-- ID: recommendations -->

### Immediate Priority Fixes (High Impact)

#### Fix 1: Unify Session Key Derivation (CRITICAL)
**Location:** `tools/set_project.py`, `shared/logging_utils.py`

Create a single canonical function for deriving session key:
```python
# New: shared/session_utils.py
def get_canonical_session_key(exec_context: Optional[ExecutionContext]) -> Optional[str]:
    """Return THE session key - stable_session_id always preferred."""
    if not exec_context:
        return None
    return exec_context.stable_session_id or exec_context.session_id
```

Use this function in BOTH set_project and append_entry/logging_utils.

**Estimated Effort:** 2-3 hours

#### Fix 2: Remove Silent Global Fallback (CRITICAL)
**Location:** `shared/logging_utils.py`, lines 267-306

Replace silent global fallback with explicit error:
```python
# logging_utils.py:269 - CHANGE FROM:
if not project and not exec_context:
    active_project, active_name, recent = await load_active_project(...)

# TO:
if not project and not exec_context:
    if require_project:
        raise ProjectResolutionError(
            "No ExecutionContext available and require_project=True. "
            "This indicates a tool call outside the MCP router wrapper.",
            recent_projects,
        )
    # Only allow None project for tools that don't require it
    return LoggingContext(tool_name=tool_name, project=None, ...)
```

**Estimated Effort:** 1-2 hours

#### Fix 3: Add Session Key Validation (HIGH)
**Location:** `tools/append_entry.py`

Add validation that session-project binding exists before logging:
```python
# Before writing to log:
if exec_context and exec_context.stable_session_id:
    expected_project = await backend.get_session_project(exec_context.stable_session_id)
    if expected_project and expected_project != resolved_project.get("name"):
        raise ProjectResolutionError(
            f"Session bound to '{expected_project}' but resolved to '{resolved_project.get('name')}'"
        )
```

**Estimated Effort:** 2-3 hours

### Long-Term Opportunities

1. **Per-Session State Isolation**: Replace global `current_project` in state.json with per-session tracking only (already partially implemented with `session_projects` table - complete the transition)

2. **Defensive Logging**: Add telemetry to track when fallback paths are triggered, enabling detection of isolation failures in production

3. **Context Propagation Contract**: Define explicit MCP client contract requiring stable session identity in all tool calls

4. **Integration Tests**: Create test suite that spawns multiple concurrent agents and verifies log isolation

### Reproduction Steps for Testing

1. Start MCP server
2. Connect Agent A, call `set_project(name="project_a")`
3. Connect Agent B (same MCP server), call `set_project(name="project_b")`
4. From Agent A, call `append_entry(message="test from A")` WITHOUT proper context
5. Check which project received the log entry
6. Expected: project_a, Actual (bug): project_b (whatever current_project was set to last)
<!-- ID: appendix -->
---
## Appendix
<!-- ID: appendix -->

### References

| File | Lines | Purpose |
|------|-------|---------|
| `shared/logging_utils.py` | 41-312 | resolve_logging_context() - 4-layer resolution cascade |
| `shared/execution_context.py` | 15, 35-51 | ExecutionContext definition and ContextVar |
| `tools/set_project.py` | 450-543 | Session binding and project setting |
| `tools/append_entry.py` | 1457-1540 | Context resolution for logging |
| `state/manager.py` | 158-218 | StateManager.set_current_project with mirror_global |
| `state/agent_manager.py` | 18-157 | AgentContextManager for agent-scoped context |
| `storage/sqlite.py` | 1950-1969 | set_session_project / get_session_project |
| `server.py` | 550-620 | Router wrapper and context building |
| `.scribe/state.json` | 1-2 | Global current_project field |

### Key Database Tables

- `session_projects`: Maps session_id -> project_name
- `agent_sessions`: Stores stable agent sessions
- `scribe_projects`: Project definitions and metadata

### Session ID Types

| Type | Source | Stability |
|------|--------|-----------|
| `transport_session_id` | MCP client | Potentially unstable (may change per-request) |
| `context_session_id` | ExecutionContext.session_id | UUID per transport session |
| `stable_session_id` | Derived from identity hash | Stable across restarts |
| `session_id` | AgentContextManager | Per-agent session tracking |

### Related Issues

- Custom doc naming bug (RESEARCH_MANAGE_DOCS_UX_20260119_0402.md)
- Multi-project concurrency limitations (same root cause)
