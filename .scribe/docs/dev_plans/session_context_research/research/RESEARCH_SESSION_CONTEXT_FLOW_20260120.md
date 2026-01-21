---
id: session_context_research-research-session-context-flow-20260120
title: "\U0001F52C Research Session Context Flow 20260120 \u2014 session_context_research"
doc_name: RESEARCH_SESSION_CONTEXT_FLOW_20260120
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

# 🔬 Research Session Context Flow 20260120 — session_context_research
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 05:27:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Investigate ExecutionContext flow and identify root cause of session isolation failures causing cross-project log contamination.

**Key Takeaways:**
- **ROOT CAUSE IDENTIFIED (100% confidence)**: The `agent` parameter is included in session identity hash, creating different `stable_session_id` values when different tools use different agent defaults.
- **Specific failure**: `set_project` (no explicit agent → defaults to "default") binds project to one session, but `append_entry` (with agent="ResearchAgent-SessionContext") looks up a DIFFERENT session, causing binding lookup to fail.
- **Impact**: Multi-project concurrency completely broken - logs go to wrong projects, session isolation fails.
- **Architecture is otherwise sound**: The stable session system using `agent_sessions` table is well-designed; the bug is in inconsistent agent parameter handling.
- **Fix is straightforward**: Either exclude agent from identity hash OR ensure consistent agent propagation across all tool calls within a session.
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-SessionContext

**Investigation Window:** 2026-01-20

**Focus Areas:**
- [x] ExecutionContext creation and propagation from MCP server to tools
- [x] Session ID types: `transport_session_id`, `session_id`, `stable_session_id`
- [x] Identity derivation: `derive_session_identity_preview()` and `agent_sessions` table
- [x] Session binding: `set_project` → `backend.set_session_project()`
- [x] Session resolution: `logging_utils.resolve_logging_context()` → `backend.get_session_project()`
- [x] Debug log analysis: actual production session key mismatches

**Dependencies & Constraints:**
- Analysis based on production debug logs from `/tmp/scribe_session_debug.log`
- Traced complete flow from MCP request → router → ExecutionContext → tool execution
- Examined 6 critical files: execution_context.py, server.py, set_project.py, logging_utils.py, session_utils.py, sqlite.py
<!-- ID: findings -->
### Finding 1: ExecutionContext Architecture (Verified Sound)
- **Summary:** ExecutionContext has THREE session ID fields with distinct purposes
- **Evidence:** 
  - `execution_context.py:35-50`: `transport_session_id` (unstable from MCP transport), `session_id` (stable UUID from router), `stable_session_id` (deterministic from agent_sessions table)
  - `execution_context.py:62-112`: RouterContextManager.get_or_create_session_id() uses 3-tier lookup: memory cache → DB → create new
- **Confidence:** 95%
- **Impact:** Architecture is well-designed for session stability

### Finding 2: Stable Session Derivation (Working as Designed)
- **Summary:** server.py derives stable_session_id from identity_hash BEFORE building ExecutionContext
- **Evidence:**
  - `server.py:567`: `identity_hash, identity_parts = derive_session_identity_preview(context_payload, arguments)`
  - `server.py:582-600`: Calls `backend.get_or_create_agent_session(identity_key=identity_hash)` to get stable_session_id
  - `server.py:600`: Injects stable_session_id into context_payload BEFORE ExecutionContext is built
- **Confidence:** 90%
- **Impact:** Identity derivation happens correctly on every tool call

### Finding 3: Identity Hash Formula (THE PROBLEM)
- **Summary:** Identity hash includes agent_key, fragmenting sessions by agent name
- **Evidence:**
  - `server.py:350`: Project mode: `scope_key = transport_session_id` (stable) ✓
  - `server.py:353`: `agent_key = arguments.get("agent") or "default"` (varies by tool!)
  - `server.py:356`: `identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"` 
  - Result: Different agent parameter → different identity_hash → different stable_session_id
- **Confidence:** 100%
- **Impact:** THIS IS THE ROOT CAUSE

### Finding 4: set_project Session Binding
- **Summary:** set_project binds project to stable_session_id, but doesn't pass agent parameter explicitly
- **Evidence:**
  - `set_project.py:462`: Gets `stable_session_id` from ExecutionContext
  - `set_project.py:513`: `session_key = stable_session_id or context_session_id or session_id`
  - `set_project.py:517`: `await backend.set_session_project(session_key, name)`
  - Debug log: set_project bound to stable_session_id=4ec1a4e8... (agent_key="default")
- **Confidence:** 95%
- **Impact:** Binding uses session from agent_key="default"

### Finding 5: append_entry Session Lookup
- **Summary:** append_entry looks up with stable_session_id, but agent parameter IS provided
- **Evidence:**
  - `logging_utils.py:91`: `session_key = stable_session_id or session_id`
  - `logging_utils.py:93`: `project_name = await backend.get_session_project(session_key)`
  - Debug log: append_entry looks up stable_session_id=54cf887e... (agent_key="ResearchAgent-SessionContext")
  - Result: NO PROJECT FOUND (wrong session!)
- **Confidence:** 95%
- **Impact:** Lookup uses different session, binding not found

### Finding 6: The Smoking Gun (Debug Logs)
- **Summary:** Production debug logs prove the mismatch
- **Evidence:**
  ```
  set_project binding:
    session_key: 4ec1a4e8-b44e-46de-9fb2-4cf843a604f3
    project_name: session_context_research
    (identity from agent_key="default")
  
  append_entry lookup:
    session_key: 54cf887e-35d6-4887-9f8a-caec573af841
    project_name from DB: None
    (identity from agent_key="ResearchAgent-SessionContext")
  
  read_file lookup:
    session_key: 4ec1a4e8-b44e-46de-9fb2-4cf843a604f3
    project_name from DB: session_context_research ✓
    (identity from agent_key="default")
  ```
- **Confidence:** 100%
- **Impact:** Definitive proof of agent parameter causing different sessions

### Finding 7: session_utils.py Exists But Unused
- **Summary:** Canonical session key function exists but is NOT used by tools
- **Evidence:**
  - `session_utils.py:17-52`: `get_canonical_session_key()` provides single source of truth
  - `set_project.py:513` and `logging_utils.py:91`: Use inline derivation instead
  - Created to fix session isolation bugs, but not integrated
- **Confidence:** 90%
- **Impact:** Opportunity for architectural improvement

### Finding 8: agent_sessions Table Design
- **Summary:** The agent_sessions table correctly implements deterministic session creation
- **Evidence:**
  - `sqlite.py:864-876`: Table schema with identity_key as UNIQUE constraint
  - `sqlite.py:2133-2162`: INSERT OR IGNORE pattern ensures same identity_key returns same session_id
  - Hash formula creates stable identity from (repo_root, mode, scope_key, agent_key)
- **Confidence:** 95%
- **Impact:** Table design is sound, problem is in what goes into the hash

### Finding 9: Multi-Agent Design Intent
- **Summary:** Including agent_key in identity appears intentional for multi-agent isolation
- **Evidence:**
  - `server.py:719`: "AgentContextManager initialized for multi-agent support"
  - Agent-scoped project context suggests agent isolation was a design goal
  - However, implementation doesn't account for inconsistent agent parameter usage
- **Confidence:** 90%
- **Impact:** Design intent conflicts with actual usage patterns

### Finding 10: derive_session_identity() is Dead Code
- **Summary:** The old derive_session_identity() using execution_id is not called
- **Evidence:**
  - `server.py:287-324`: Function exists with execution_id scope_key (unstable)
  - `server.py:567`: Actual call_tool uses derive_session_identity_preview() instead
  - derive_session_identity_preview uses transport_session_id (stable) ✓
- **Confidence:** 98%
- **Impact:** Technical debt - dead function should be removed
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

1. **ExecutionContext Flow (Well-Designed)**
   ```
   MCP Request → server.py call_tool()
     → derive_session_identity_preview(context_payload, arguments)
       → identity_hash = SHA256(repo_root:mode:scope_key:agent_key)
     → backend.get_or_create_agent_session(identity_hash)
       → Returns stable_session_id from agent_sessions table
     → context_payload["stable_session_id"] = stable_session_id
     → router_context_manager.build_execution_context(context_payload)
       → ExecutionContext with stable_session_id populated
     → router_context_manager.set_current(exec_context)
     → Tool function executes with context available
   ```

2. **Session Binding Pattern (set_project)**
   ```
   set_project(name, ...) called (no agent param)
     → arguments.get("agent") = None → defaults to "default"
     → derive_session_identity_preview: agent_key="default"
     → identity_hash_A = SHA256(repo:project:transport_session:default)
     → stable_session_id_A = get_or_create_agent_session(identity_hash_A)
     → backend.set_session_project(stable_session_id_A, name)
       → Writes to session_projects table
   ```

3. **Session Lookup Pattern (append_entry)**
   ```
   append_entry(message, agent="ResearchAgent", ...) called
     → arguments.get("agent") = "ResearchAgent"
     → derive_session_identity_preview: agent_key="ResearchAgent"
     → identity_hash_B = SHA256(repo:project:transport_session:ResearchAgent)
     → stable_session_id_B = get_or_create_agent_session(identity_hash_B)
     → logging_utils.resolve_logging_context()
       → backend.get_session_project(stable_session_id_B)
         → Query session_projects WHERE session_key = stable_session_id_B
         → NO MATCH (binding was with stable_session_id_A!)
     → Falls back to global state (WRONG PROJECT)
   ```

**System Interactions:**

- **agent_sessions table**: Maps identity_key (SHA256 hash) → session_id (UUID)
  - UNIQUE constraint on identity_key ensures determinism
  - INSERT OR IGNORE pattern prevents duplicates
  - Works perfectly for same identity, but identity includes agent!

- **session_projects table**: Maps session_key → project_name
  - session_key is the stable_session_id from agent_sessions
  - Binding and lookup must use SAME session_key
  - Currently fails when agent differs

- **Context propagation**: ExecutionContext correctly carries stable_session_id
  - Problem is NOT in context propagation
  - Problem is that different tools create different stable_session_id values
  - Because arguments["agent"] varies between tool calls

**Risk Assessment:**

- **CRITICAL**: Multi-project concurrency completely broken
  - Logs from one project contaminate another
  - Session isolation fails when agent parameter varies
  - Affects ALL tools that accept agent parameter

- **Data integrity**: session_projects table contains orphaned bindings
  - Each unique (transport_session, agent_key) combination creates new session
  - Database accumulates sessions that are never looked up
  - Cleanup needed after fix

- **User trust**: Silent failures cause mysterious behavior
  - Users see logs in wrong projects with no error message
  - Debugging requires examining /tmp/scribe_session_debug.log
  - No user-facing indication of the problem
<!-- ID: recommendations -->
### Immediate Next Steps

**Option A: Remove agent_key from identity hash (RECOMMENDED)**
- [x] **Simplest fix**: Modify `server.py:356` to exclude agent_key from identity formula
  - Current: `identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"`
  - Proposed: `identity = f"{repo_root}:{mode}:{scope_key}"`
- **Pros**: 
  - One-line change
  - Fixes root cause directly
  - All tools share same session for same transport_session_id
  - No behavior changes for users
- **Cons**:
  - Loses theoretical multi-agent isolation (but this was never working anyway)
  - Would need migration to clean up orphaned agent_sessions entries

**Option B: Consistent agent propagation across all tools**
- [ ] Ensure ALL tools receive same agent parameter value within a session
  - Extract agent from ExecutionContext.agent_identity instead of arguments
  - Pass agent_identity.instance_id (stable per process) instead of display_name
  - Requires changes to derive_session_identity_preview logic
- **Pros**:
  - Preserves multi-agent isolation design
  - More architectural purity
- **Cons**:
  - More complex implementation
  - Still fragments sessions by agent instance (unclear if this is desired)
  - Doesn't solve the fundamental inconsistency problem

**Option C: Use transport_session_id directly as session key**
- [ ] Skip the agent_sessions table entirely for project mode
  - Use transport_session_id directly as session_key
  - Keep agent_sessions only for sentinel mode (where daily scoping makes sense)
- **Pros**:
  - Eliminates indirection
  - Simpler architecture
  - Guaranteed consistency
- **Cons**:
  - Larger refactor
  - Loses benefits of stable session table (persistence across restarts)

**RECOMMENDED APPROACH: Option A**

Implementation steps:
1. Modify `server.py:356` to remove agent_key from identity formula
2. Add database migration to clean up orphaned agent_sessions entries
3. Remove dead code: `derive_session_identity()` function
4. Update tests to verify consistent session behavior
5. Monitor /tmp/scribe_session_debug.log after fix to confirm resolution

### Long-Term Opportunities

1. **Integrate session_utils.py canonical functions**
   - Replace inline session key derivation in set_project.py and logging_utils.py
   - Use `get_canonical_session_key()` as single source of truth
   - Add validation: `validate_session_key_consistency()` in production code

2. **Add session diagnostics tooling**
   - Create admin tool to inspect session_projects and agent_sessions tables
   - Show which sessions are orphaned/unused
   - Provide cleanup commands for stale sessions

3. **Improve error visibility**
   - When session lookup fails, log WARNING with session key details
   - Don't silently fall back to global state - make failures visible
   - Add user-facing session status to get_project output

4. **Formalize multi-agent requirements**
   - Document whether agent isolation is actually needed
   - If yes, design proper agent-scoped session architecture
   - If no, remove agent_key from identity permanently

5. **Add session integration tests**
   - Test: set_project then append_entry with different agent parameters
   - Verify logs go to correct project regardless of agent
   - Test cross-project isolation still works
<!-- ID: appendix -->
### Complete ExecutionContext Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ MCP Client Request                                              │
│ (Claude Code orchestrator calls append_entry)                   │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ server.py: call_tool(name="append_entry", arguments={...})      │
│                                                                  │
│ 1. Extract context_payload from MCP request                     │
│    - transport_session_id (from MCP transport layer)            │
│    - repo_root, mode, intent                                    │
│                                                                  │
│ 2. Call derive_session_identity_preview(context_payload, args)  │
│    ┌──────────────────────────────────────────────────────┐    │
│    │ identity = f"{repo_root}:{mode}:{scope_key}:{agent}" │    │
│    │ where:                                                │    │
│    │   scope_key = transport_session_id (project mode)    │    │
│    │   agent = arguments.get("agent") or "default"        │    │
│    │                                                       │    │
│    │ ⚠️  BUG: agent varies between tools!                 │    │
│    │   set_project: agent="default" (not passed)          │    │
│    │   append_entry: agent="ResearchAgent" (passed)       │    │
│    └──────────────────────────────────────────────────────┘    │
│                                                                  │
│ 3. identity_hash = SHA256(identity)                             │
│                                                                  │
│ 4. Call backend.get_or_create_agent_session(identity_hash)      │
│    ┌──────────────────────────────────────────────────────┐    │
│    │ Query: SELECT session_id FROM agent_sessions         │    │
│    │        WHERE identity_key = ?                        │    │
│    │                                                       │    │
│    │ If not found:                                        │    │
│    │   INSERT INTO agent_sessions                         │    │
│    │   (session_id=UUID(), identity_key=hash, ...)        │    │
│    │                                                       │    │
│    │ Returns: stable_session_id (deterministic UUID)      │    │
│    └──────────────────────────────────────────────────────┘    │
│                                                                  │
│ 5. context_payload["stable_session_id"] = stable_session_id     │
│                                                                  │
│ 6. exec_context = build_execution_context(context_payload)      │
│                                                                  │
│ 7. set_current(exec_context) - store in contextvars             │
│                                                                  │
│ 8. Call tool function: append_entry(**arguments)                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ append_entry: resolve_logging_context()                         │
│                                                                  │
│ 1. Get exec_context from contextvars                            │
│                                                                  │
│ 2. Extract stable_session_id from exec_context                  │
│    session_key = exec_context.stable_session_id                 │
│                                                                  │
│ 3. Query session_projects table                                 │
│    ┌──────────────────────────────────────────────────────┐    │
│    │ SELECT project_name FROM session_projects            │    │
│    │ WHERE session_key = ?                                │    │
│    │                                                       │    │
│    │ ⚠️  FAILS: No binding found!                         │    │
│    │ Because stable_session_id differs from set_project   │    │
│    └──────────────────────────────────────────────────────┘    │
│                                                                  │
│ 4. Fallback to global state (WRONG!)                            │
│    project = state.get_current_project()                        │
│    → Returns LAST project set globally (any session)            │
│                                                                  │
│ 5. Log entry written to WRONG project                           │
└─────────────────────────────────────────────────────────────────┘
```

### Session Key Mismatch Example (Production Debug Logs)

**set_project call:**
```
Tool: set_project
arguments: {name: "session_context_research", ...}
agent_key: "default" (not passed, defaulted)
identity: /repo:project:process:fecf022b:default
identity_hash: abc123...
stable_session_id: 4ec1a4e8-b44e-46de-9fb2-4cf843a604f3

DB Operation:
INSERT INTO session_projects (session_key, project_name)
VALUES ('4ec1a4e8-b44e-46de-9fb2-4cf843a604f3', 'session_context_research')
```

**append_entry call (same session, different agent):**
```
Tool: append_entry
arguments: {message: "...", agent: "ResearchAgent-SessionContext", ...}
agent_key: "ResearchAgent-SessionContext" (passed explicitly)
identity: /repo:project:process:fecf022b:ResearchAgent-SessionContext
identity_hash: def456...  ⚠️  DIFFERENT HASH!
stable_session_id: 54cf887e-35d6-4887-9f8a-caec573af841  ⚠️  DIFFERENT ID!

DB Lookup:
SELECT project_name FROM session_projects
WHERE session_key = '54cf887e-35d6-4887-9f8a-caec573af841'
→ NO ROWS RETURNED (binding was with different session_key!)

Fallback to global state:
→ Gets LAST project set globally (might be wrong project!)
```

### Files Analyzed

| File | Purpose | Key Findings |
|------|---------|--------------|
| `shared/execution_context.py` | ExecutionContext dataclass and RouterContextManager | Three session ID types, architecture sound |
| `server.py` | MCP server and call_tool routing | derive_session_identity_preview() includes agent_key (BUG) |
| `tools/set_project.py` | Project binding | Uses stable_session_id from ExecutionContext, agent defaults to "default" |
| `shared/logging_utils.py` | Session resolution for logging | Uses stable_session_id for lookup, fails when agent differs |
| `shared/session_utils.py` | Canonical session key functions | Exists but unused - integration opportunity |
| `storage/sqlite.py` | Database operations | agent_sessions table design is sound, problem is input data |

### References

- **Debug logs**: `/tmp/scribe_session_debug.log` (production evidence)
- **Related files**: 
  - `shared/session_utils.py` - Canonical functions for future integration
  - `state/agent_manager.py` - AgentContextManager for multi-agent support
- **Database schema**:
  - `agent_sessions` table (lines 864-885 in sqlite.py)
  - `session_projects` table (lines 912-920 in sqlite.py)

---

**Research Complete: 2026-01-20 05:30 UTC**
**Confidence: 100% (root cause definitively identified)**
**Next Phase: Architecture/Implementation to fix agent_key in identity hash**
