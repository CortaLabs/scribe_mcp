---
id: manage_docs_agent_ux-research-multi-project-concurrency-20260119
title: "\U0001F52C Research Multi Project Concurrency 20260119 \u2014 manage_docs_agent_ux"
doc_name: RESEARCH_MULTI_PROJECT_CONCURRENCY_20260119
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

# 🔬 Research Multi Project Concurrency 20260119 — manage_docs_agent_ux
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 04:11:20 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

Scribe MCP currently supports **only one active project at a time** within a session, but the infrastructure for multi-project concurrency is **already partially implemented** at the database and session management layers. The limitation stems from an incomplete application of this infrastructure to all tools and a reliance on global fallback state.

### Current State
- Global `current_project` in StateManager (JSON state file)
- Agent-scoped sessions with 15-minute TTL in AgentContextManager
- Session-project bindings in storage backend (upsert_session, get_session_project)
- Hybrid context resolution: session-aware + global fallback

### The Gap
Multiple critical tools lack explicit `project` parameters and rely entirely on implicit session context resolution, which falls back to global state when session context is unavailable.

### Path Forward
Complete the multi-project support by:
1. Adding explicit `project` parameters to all tools that log or access projects
2. Making tools session-aware by default, with explicit project as override
3. Establishing clear precedence rules (explicit param > session context > global state)
4. Validating all tools can resolve project context without breaking existing workflows

This research identifies the architectural foundation, gaps, and concrete implementation path.
<!-- ID: research_scope -->
**Research Lead:** Scribe

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### Finding 1: Three-Layer Project Context Architecture Exists

**Summary:** Scribe has three distinct layers of project context management.

**Evidence:**
- **Layer 1 (Global):** StateManager (state/manager.py:22-31) maintains single `current_project` in persistent JSON state with fields `current_project`, `projects`, `recent_projects`
- **Layer 2 (Agent-Scoped Sessions):** AgentContextManager (state/agent_manager.py:18-36) provides agent-scoped sessions with 15-minute TTL and optimistic concurrency control via `set_current_project()` method
- **Layer 3 (Session-Project Binding):** Storage backend methods `set_session_project()`, `get_session_project()`, `upsert_session()` bind sessions to projects in database (referenced in set_project.py:515-539)

**File References:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/state/manager.py:22-31` - State dataclass definition
- `/home/austin/projects/MCP_SPINE/scribe_mcp/state/agent_manager.py:18-36` - AgentContextManager class definition
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/set_project.py:512-542` - Session binding implementation

**Confidence:** 0.95 - Direct code inspection confirms full implementation

---

### Finding 2: Tools Use Hybrid Context Resolution (Session + Fallback)

**Summary:** Tools resolve project context via `resolve_logging_context()` which checks session context first, then falls back to global state.

**Evidence:**
- `resolve_logging_context()` (shared/logging_utils.py:41-200) implements three-tier resolution:
  1. If execution context mode == "project": query backend for session-project binding (lines 84-142)
  2. Fallback to JSON state's session_projects dict (lines 143-147)
  3. Final fallback to global current_project if no session context (lines 150+)
- This pattern prevents multi-project parallelism: when session context unavailable or not set up, tools default to global state
- Session context relies on ExecutionContext which is set once per tool invocation

**File References:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/shared/logging_utils.py:41-200` - resolve_logging_context implementation
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/append_entry.py:1459-1475` - Tool usage example

**Confidence:** 0.93 - Code inspection and trace analysis

---

### Finding 3: Inconsistent Project Parameter Support Across Tools

**Summary:** Some tools have explicit `project` parameters; others rely entirely on implicit resolution, creating an incomplete multi-project interface.

**Evidence:**
Tools WITH explicit `project` parameter (6 tools):
- `manage_docs.py` - line 24: `project: Optional[str] = None`
- `query_entries.py` - explicit project override for cross-project search
- `read_recent.py` - explicit project parameter
- `rotate_log.py` - explicit project parameter
- `get_project.py` - explicit project parameter

Tools WITHOUT explicit `project` parameter (critical tools):
- `append_entry.py` - No project parameter; relies entirely on resolve_logging_context()
- `read_file.py` - No project parameter; uses implicit project resolution
- `generate_doc_templates.py` - No project parameter; depends on context

**Impact:** Agents switching between projects will have append_entry() logs go to the wrong project because the tool can't accept explicit project specification.

**File References:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/append_entry.py:1385-1410` - Tool signature (no project param)
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/manage_docs.py:85-100` - Tool signature (has project param)

**Confidence:** 0.98 - Direct inspection of tool signatures

---

### Finding 4: Session Context Requires Execution Context, May Be Unavailable

**Summary:** Session-based project resolution depends on ExecutionContext being set, which may not exist in all invocation contexts (e.g., tests, direct API calls).

**Evidence:**
- resolve_logging_context() (line 77-81) tries to get ExecutionContext but silently continues if unavailable
- If ExecutionContext unavailable or mode != "project", resolution falls back to global state (line 150+)
- This fallback masks concurrency issues: parallel agents on different projects will silently collide at global state level
- set_project.py (lines 458-463) explicitly tries to get ExecutionContext and catches all exceptions

**Impact:** 
- When ExecutionContext unavailable, multi-project concurrency is impossible (both agents use global state)
- No error signals when tools fall back to global state during concurrent work
- Agents may not realize their logs are going to wrong project

**File References:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/shared/logging_utils.py:77-81` - Exception handling on ExecutionContext access
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/set_project.py:458-465` - set_project ExecutionContext usage

**Confidence:** 0.90 - Code patterns suggest design intent but fallback behavior creates issue

---

### Finding 5: Optimistic Concurrency Control Exists But Not Enforced for Tools

**Summary:** AgentContextManager implements optimistic concurrency control for `set_current_project()` (expected_version parameter), but this control doesn't prevent data races at the tool invocation level.

**Evidence:**
- AgentContextManager.set_current_project() (state/agent_manager.py:80-140) accepts `expected_version` parameter
- set_project.py (line 198) passes expected_version to set_current_project()
- However, tools using implicit project resolution (append_entry, read_file) cannot specify version expectations
- Multiple agents on different projects will write to their respective session_projects in database, but if session context is unavailable, they collide at global JSON state level

**Impact:** Version conflict detection only works when tools explicitly pass expected_version, which requires explicit project parameter.

**File References:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/state/agent_manager.py:80-140` - set_current_project with version control
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/set_project.py:478-484` - Passing version to agent manager

**Confidence:** 0.88 - Implementation partially complete

---

### Finding 6: Session TTL (15 minutes) Creates Time-Window Limitation

**Summary:** Agent sessions expire after 15 minutes of inactivity, which could cause project context loss for long-running agent workflows.

**Evidence:**
- AgentContextManager (state/agent_manager.py:35): `_session_ttl_minutes = 15`
- Session lease validation in set_current_project() (line 104)
- Expired sessions fall back to global state

**Impact:** Agents working on multi-project tasks for > 15 minutes may lose session context and start using global state, causing log collisions.

**File References:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/state/agent_manager.py:35` - TTL definition

**Confidence:** 0.95 - Direct code inspection
<!-- ID: technical_analysis -->
## Technical Analysis: Three Design Options

### Option A: Explicit Project Parameters (Recommended)

**Design:** Add `project: Optional[str]` parameter to all tools that lack it. Establish precedence: explicit param > session context > global state.

**Affected Tools (3 critical):**
1. `append_entry.py` - Add `project` param, use in resolve_logging_context()
2. `read_file.py` - Add `project` param for cross-project file access
3. `generate_doc_templates.py` - Add `project` param to generate in specified project

**Implementation Pattern:**
```python
async def append_entry(
    message: str = "",
    project: Optional[str] = None,  # NEW: Explicit project override
    ...
) -> Dict[str, Any]:
    # In resolve_logging_context call:
    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=server_module,
        explicit_project=project,  # Pass explicit project as override
        require_project=True
    )
```

**Pros:**
- ✅ Matches existing pattern in manage_docs, query_entries, etc.
- ✅ Explicit control: agents specify which project they're working on
- ✅ Works even without ExecutionContext (true cross-project support)
- ✅ Backward compatible: explicit param is optional
- ✅ No architectural changes needed; uses existing resolve_logging_context()

**Cons:**
- Agents must pass project on every tool call (slightly more verbose)
- Existing code/agents that don't pass project still use global state

**Effort:** 5-8 hours
- Modify 3 tool signatures: 1 hour
- Update resolve_logging_context() precedence logic: 1 hour
- Test cross-project append_entry: 2 hours
- Test cross-project read_file: 2 hours
- Update tool documentation: 1 hour

---

### Option B: Session-First Enforcement (Requires Refactoring)

**Design:** Remove fallback to global state; require ExecutionContext/session in all cases. Make session context mandatory for parallel work.

**Implementation:**
- Modify resolve_logging_context() to raise error if session context unavailable (no fallback to global)
- Require agents to call set_project() before using tools
- Store agent's current project in session only (not global state)

**Pros:**
- ✅ Single source of truth: session binding in database
- ✅ Natural parallelism: each agent/session has own project context
- ✅ Automatic isolation: no cross-project data races

**Cons:**
- ❌ Breaking change: tools will error if session context unavailable
- ❌ Large refactoring: test infrastructure, legacy API calls will break
- ❌ Requires ExecutionContext in all invocation contexts (not guaranteed)
- ❌ 15-minute TTL creates workflow complexity (long tasks lose context)

**Effort:** 15-20 hours (major refactoring)
- Modify resolve_logging_context(): 2 hours
- Update all tools to handle missing session: 3 hours
- Refactor tests to set up session context: 5 hours
- Handle legacy API calls: 3 hours
- Document session requirements: 2 hours

---

### Option C: Project Registry (Advanced, Future Work)

**Design:** Use ProjectRegistry as source of truth for agent->project mappings, making global state a read-only cache.

**Implementation:**
- Extend ProjectRegistry to track agent->project bindings with timestamps
- Query registry instead of global state as final fallback
- Use database as authoritative store (current implementation partially does this)

**Pros:**
- ✅ Scalable: supports N projects and M concurrent agents
- ✅ Audit trail: ProjectRegistry tracks all agent->project transitions
- ✅ No session TTL issues: registry persists across sessions

**Cons:**
- ❌ Complex: requires ProjectRegistry enhancements
- ❌ Adds query overhead on every tool invocation
- ❌ Not yet fully designed

**Effort:** 20+ hours (future enhancement)

---

## Recommended Path: Option A (Explicit Parameters)

**Rationale:**
1. **Minimal changes:** Only 3 tool signatures need updates
2. **No breaking changes:** Optional parameter is backward compatible
3. **Uses existing infrastructure:** resolve_logging_context() already supports explicit_project
4. **Immediate impact:** Agents can work on multiple projects immediately
5. **Foundation for Option B/C:** Makes Session-First or Registry approaches easier later

**Implementation Sequence:**
1. Phase 1: Add `project` param to append_entry.py (2 hours)
2. Phase 2: Add `project` param to read_file.py (2 hours)
3. Phase 3: Add `project` param to generate_doc_templates.py (2 hours)
4. Phase 4: Test cross-project workflows (3 hours)
5. Phase 5: Documentation + examples (1 hour)

**Total Estimated Effort:** 5-8 hours development + 2-3 hours testing = 7-11 hours

**Success Criteria:**
- All 3 tools have explicit `project` parameter
- Tools use explicit_project in resolve_logging_context() calls
- Cross-project append_entry() logs go to correct project regardless of session context
- Backward compatibility maintained: tools still work without project param
- Tests verify multi-project concurrency (2+ agents on different projects)
<!-- ID: recommendations -->
## Recommendations & Handoff Notes for Architect/Coder

### Primary Recommendation: Implement Option A (Explicit Project Parameters)

**Why This Approach:**
- Least disruptive: only 3 tool changes needed
- Leverages existing infrastructure (resolve_logging_context already supports explicit_project)
- No breaking changes: backward compatible
- Solves the immediate problem: agents can explicitly specify which project to work on
- Creates foundation for future improvements (Session-First, Registry-based)

### Concrete Action Items for Architect

1. **Design Tool Update Pattern**
   - Define standardized signature for tools with project parameter
   - Establish precedence rules: explicit project > session context > global state
   - Document when explicit project is required vs optional

2. **Define Session Context Enhancement**
   - Update resolve_logging_context() to accept and prioritize explicit_project parameter
   - Ensure explicit_project overrides session context fallback behavior
   - Add logging/diagnostics when explicit_project is used to override session context

3. **Create Test Scenarios**
   - Single agent, multiple projects (same session, different projects per call)
   - Multiple agents, different projects (parallel work with session isolation)
   - Fallback testing (missing ExecutionContext, verify explicit project still works)

### Concrete Action Items for Coder

1. **append_entry.py** - Critical for logging to correct project
   ```python
   # Add to function signature
   project: Optional[str] = None
   
   # In tool implementation
   context = await resolve_logging_context(
       tool_name="append_entry",
       explicit_project=project,  # NEW: Pass explicit override
       require_project=True
   )
   ```

2. **read_file.py** - Enable cross-project file access
   ```python
   # Add to function signature
   project: Optional[str] = None
   
   # Resolve project context with explicit override
   context = await resolve_logging_context(
       tool_name="read_file",
       explicit_project=project,
       require_project=True
   )
   ```

3. **generate_doc_templates.py** - Generate templates in specified project
   ```python
   # Add to function signature
   project: Optional[str] = None
   
   # Use explicit project to determine target directory
   ```

4. **Testing Requirements**
   ```python
   # Test 1: append_entry to project A while session context is project B
   append_entry(project="projectA", message="Log to A")
   # Verify log appears in projectA, not projectB
   
   # Test 2: read_file from different project
   content = read_file(project="projectB", path="...")
   # Verify reads from projectB regardless of session
   
   # Test 3: Backward compatibility
   append_entry(message="Log without explicit project")
   # Verify uses session context or global fallback as before
   ```

### Design Decisions for Architect to Clarify

1. **When is explicit project required?**
   - Always optional? Or required when ExecutionContext unavailable?
   - Recommendation: Always optional (backward compat), but log warning if session context unavailable

2. **Error Handling**
   - What if explicit project doesn't exist? (raise error vs create?)
   - Current pattern: resolve_logging_context() returns error via response, not exception

3. **Session Context Interaction**
   - Should explicit project invalidate session context for that call?
   - Recommendation: Yes - explicit param should fully override session for that invocation

4. **Documentation**
   - Add examples showing multi-project workflows
   - Document precedence: explicit > session > global
   - Add troubleshooting guide for wrong-project issues

### Why This Solves the Problem

**Before:** Agents can only work on one project at a time because tools fall back to global state.
```
Agent A: set_project("projectA") → global state = projectA
Agent B: set_project("projectB") → global state = projectB
Agent A: append_entry("log") → logs to projectB (uses global state)  ❌ WRONG
```

**After:** Agents can specify project explicitly on each call.
```
Agent A: append_entry(project="projectA", message="log") → logs to projectA ✅ CORRECT
Agent B: append_entry(project="projectB", message="log") → logs to projectB ✅ CORRECT
```

### Open Questions for Architect

1. Should we add validation to ensure the specified project exists before using it?
2. Should we add audit logging when explicit project differs from session context?
3. Should we extend this pattern to other tools (delete_project, list_projects, etc.)?
4. How should we document this for agent developers?

### Migration Path (Optional Future Work)

1. **Phase 1 (Current):** Add explicit project params to append_entry, read_file, generate_doc_templates
2. **Phase 2 (Future):** Add to remaining tools (delete_project, etc.) if needed
3. **Phase 3 (Future):** Consider Session-First enforcement (Option B) once critical tools are updated
4. **Phase 4 (Future):** Consider ProjectRegistry approach (Option C) for further scalability
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---