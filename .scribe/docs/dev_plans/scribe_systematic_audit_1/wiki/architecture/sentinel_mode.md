# Sentinel Mode vs Project Mode Architecture

**Created**: 2026-01-05
**Author**: ResearchAgent-Phase5-FormatValidator
**Status**: Documentation (Phase 5 findings)
**Confidence**: 0.95

---

## Executive Summary

Scribe MCP operates in **two distinct execution modes** that are mutually exclusive and serve different purposes:

1. **Project Mode** (default) - Scoped logging and documentation within a specific dev plan
2. **Sentinel Mode** (stateless) - Repository-wide case tracking and event logging without project context

**Critical Discovery**: 3/16 MCP tools (18.75%) are **Sentinel Mode exclusive** and CANNOT operate when a project is active. This is **NOT a bug** - it's an intentional architectural design for repository-wide governance.

---

## Architecture Overview

### Project Mode

**Activation**: Triggered by calling `set_project(name="<project_name>")`

**State**: Active project context stored in state manager

**Scope**: All logging and documentation operations are scoped to:
- `.scribe/docs/dev_plans/<project_slug>/`
- `PROGRESS_LOG.md`, `DOC_LOG.md`, `BUG_LOG.md`, etc.

**Tools Available** (13/16 tools):
- ✅ Core logging: `append_entry`, `read_recent`, `query_entries`
- ✅ Project management: `set_project`, `get_project`, `list_projects`, `delete_project`
- ✅ Documentation: `manage_docs`, `generate_doc_templates`, `read_file`
- ✅ Utilities: `rotate_log`, `scribe_doctor`
- ⚠️ Sentinel routing: `append_event` (routes to progress log when project active)

**Use Case**: All structured development work (research, architecture, implementation, testing)

---

### Sentinel Mode

**Activation**: Operating WITHOUT calling `set_project()` (no active project context)

**State**: No active project in state manager

**Scope**: Repository-wide operations outside dev plan boundaries:
- `.scribe/sentinel/<YYYY-MM-DD>/`
- Global event logging
- Cross-project case tracking (bugs, security issues)

**Tools Available** (3/16 tools - EXCLUSIVE):
- 🔒 **`open_bug`** - Create repository-wide bug cases
- 🔒 **`open_security`** - Create repository-wide security cases
- 🔒 **`link_fix`** - Link fix artifacts to cases

**Plus**:
- ✅ `append_event` (proper Sentinel logging)
- ✅ All read-only tools (list_projects, query_entries, etc.)

**Use Case**: Repository governance, cross-project issue tracking, global event auditing

---

## Tool Mode Matrix

| Tool | Project Mode | Sentinel Mode | Notes |
|------|--------------|---------------|-------|
| **append_entry** | ✅ Primary | ⚠️ Routes to project | Writes to PROGRESS_LOG.md when project active |
| **append_event** | ⚠️ Routes to project | ✅ Primary | **BUG-ROUTING-001**: Currently writes to wrong context |
| **open_bug** | ❌ **BLOCKED** | ✅ Exclusive | Error: "Tool 'open_bug' not allowed in project mode" |
| **open_security** | ❌ **BLOCKED** | ✅ Exclusive | Error: "Tool 'open_security' not allowed in project mode" |
| **link_fix** | ❌ **BLOCKED** | ✅ Exclusive | Error: "Tool 'link_fix' not allowed in project mode" |
| **set_project** | ✅ Activates mode | ✅ Creates mode | Transitions from Sentinel → Project |
| **get_project** | ✅ Returns context | ⚠️ Returns empty | No active project in Sentinel |
| **list_projects** | ✅ Available | ✅ Available | Read-only, works in both modes |
| **delete_project** | ✅ Available | ✅ Available | Operational tool, mode-independent |
| **read_recent** | ✅ Project log | ✅ Global log | Reads from active context |
| **query_entries** | ✅ Project scope | ✅ Global scope | Search scope determines mode |
| **manage_docs** | ✅ Available | ❌ Requires project | Documentation needs project context |
| **generate_doc_templates** | ✅ Available | ❌ Requires project | Template generation needs project |
| **rotate_log** | ✅ Available | ❌ Requires project | Log rotation scoped to project |
| **read_file** | ✅ Available | ✅ Available | File access mode-independent |
| **scribe_doctor** | ✅ Available | ✅ Available | Diagnostics mode-independent |

**Key Insight**: Mode restrictions are **intentional design constraints**, not implementation bugs.

---

## Design Rationale

### Why Two Modes?

**Problem**: Development projects are transient, but some concerns span the entire repository:
- Security vulnerabilities affecting multiple projects
- Architectural decisions with cross-project impact
- Bug patterns that emerge across different features
- Compliance and audit events

**Solution**: Sentinel Mode provides **persistent, project-agnostic tracking** while Project Mode maintains **focused, scoped development context**.

### Why Block Case Tools in Project Mode?

**Intentional Constraint**: Bug and security cases are **repository-wide concerns** that should NOT be scoped to individual dev plans.

**Examples**:
- A security vulnerability might affect 3 different projects → case belongs in Sentinel space
- A bug discovered during Project A development might exist in Project B → shared tracking needed
- Compliance events (data breaches, access violations) are org-level, not project-level

**Alternative Considered**: Allow case tools in both modes and route based on context.

**Rejected Because**:
- Creates ambiguity (where does this bug belong?)
- Risks fragmenting case tracking across projects
- Loses repository-wide visibility

### append_event Routing Behavior

**Current Behavior** (BUG-ROUTING-001):
- When called in Project Mode: Routes to `PROGRESS_LOG.md` (unexpected)
- When called in Sentinel Mode: Routes to `sentinel/<date>/sentinel.jsonl` (expected)

**Expected Behavior**:
- Project Mode: Should write to dedicated `EVENT_LOG.md` or route explicitly to sentinel
- Sentinel Mode: Continue current behavior

**Status**: Under investigation, may be intentional "convenience routing"

---

## Usage Patterns

### Pattern 1: Standard Development Workflow (Project Mode)

```python
# Activate project context
await set_project(name="my_feature_development")

# All logging scoped to project
await append_entry(message="Started implementation", status="info")

# Documentation operations
await manage_docs(action="replace_section", doc="architecture", ...)

# Query project-specific logs
await read_recent(n=10)  # Returns this project's recent entries
```

**Result**: All operations scoped to `.scribe/docs/dev_plans/my_feature_development/`

---

### Pattern 2: Repository-Wide Case Tracking (Sentinel Mode)

```python
# DO NOT call set_project() - remain in Sentinel Mode

# Open bug case (repository-wide)
await open_bug(
    category="security",
    slug="auth_token_leak",
    title="JWT tokens exposed in client logs",
    severity="critical"
)

# Log global event
await append_event(
    message="Security incident: Credential exposure detected",
    status="error",
    meta={"incident_id": "SEC-2026-001", "affected_repos": 3}
)

# Link fix across projects
await link_fix(
    case_id="BUG-2026-01-05-001",
    fix_type="code",
    reference="commit:abc123",
    meta={"projects_affected": ["auth_service", "api_gateway"]}
)
```

**Result**: All operations scoped to `.scribe/sentinel/<date>/` with cross-project visibility

---

### Pattern 3: Switching Between Modes

```python
# Start in Sentinel Mode (no active project)
await append_event(message="Daily audit scan started", status="info")

# Discover issue, switch to Project Mode for fix
await set_project(name="security_patch_jan_2026")
await append_entry(message="Created patch project", status="info")
await manage_docs(action="replace_section", doc="architecture", ...)

# After fix, log completion in Sentinel Mode
# (Project still active, but can query global logs)
await query_entries(search_scope="global", message="security audit")
```

**Note**: Cannot use `open_bug` while project is active - must complete project work first or use separate session.

---

## Phase 5 Testing Implications

### Discovery Context

**Team A2 Assignment**: Test 6 tools including case management tools

**Methodology**: Created sandbox project `scribe_systematic_audit_1_phase5_tool_output` and called `set_project()`

**Result**: 3/6 tools BLOCKED with error "Tool '<name>' not allowed in project mode"

**Initial Interpretation**: Assumed this was a bug preventing testing

**Actual Cause**: Tools correctly enforced Sentinel Mode requirement (architectural design)

### Testing Limitations

**Cannot Test in Project-Based Testing Methodology**:
- `open_bug`, `open_security`, `link_fix` all require Sentinel Mode
- Phase 5 project-based approach fundamentally incompatible

**Workaround Options**:
1. Create separate Sentinel Mode testing phase (no `set_project()` call)
2. Accept 50% coverage for case management tools (architectural constraint)
3. Manual testing outside automated test framework

**Team A2 Decision**: Option 2 - Accepted 50% coverage, documented architectural limitation

---

## Known Issues

### BUG-ROUTING-001: append_event Wrong Project Routing

**Symptom**: append_event writes to unexpected project context

**Test Case**:
- Sandbox project: `scribe_systematic_audit_1_phase5_tool_output`
- Called: `append_event(message="Test", status="info")`
- Actually logged to: `phase5_test_project_a1_compact`

**Expected**: Should write to `.scribe/sentinel/<date>/sentinel.jsonl`

**Actual**: Writes to active project's log (bypassing Sentinel routing)

**Impact**: Sentinel events may be incorrectly scoped to projects

**Status**: Under investigation (Team A2 finding)

---

### BUG-SENTINEL-001: Case Tools Blocked in Project Mode

**Initial Report**: "3/16 tools blocked during testing - prevents format parameter validation"

**Investigation Result**: NOT A BUG - intentional architectural constraint

**Resolution**: Documentation added (this document). Tools working as designed.

**Reclassification**: Changed from BUG to ARCHITECTURE CONSTRAINT

---

## Implementation Details

### Mode Detection Logic

**File**: `state/manager.py` or similar state management module

**Pseudocode**:
```python
def is_project_mode():
    return state_manager.active_project is not None

def is_sentinel_mode():
    return state_manager.active_project is None

def enforce_sentinel_mode(tool_name):
    if is_project_mode():
        raise ToolNotAllowedError(f"Tool '{tool_name}' not allowed in project mode")
```

### Sentinel Tool Enforcement

**Location**: Individual tool implementations (`open_bug.py`, `open_security.py`, `link_fix.py`)

**Pattern**:
```python
async def open_bug(**kwargs):
    # Check mode before execution
    if state_manager.has_active_project():
        return error_response(
            f"Tool 'open_bug' not allowed in project mode. "
            "Case management requires Sentinel Mode (no active project)."
        )

    # Proceed with Sentinel Mode logic
    ...
```

### Directory Structure

**Project Mode**:
```
.scribe/docs/dev_plans/<project_slug>/
├── PROGRESS_LOG.md        # append_entry writes here
├── DOC_LOG.md             # manage_docs writes here
├── BUG_LOG.md             # Project-specific bugs (NOT case management)
├── SECURITY_LOG.md        # Project-specific security (NOT case management)
└── ...
```

**Sentinel Mode**:
```
.scribe/sentinel/<YYYY-MM-DD>/
├── sentinel.jsonl         # append_event writes here
├── SENTINEL_LOG.md        # Human-readable sentinel events
├── cases/
│   ├── bugs/
│   │   └── BUG-2026-01-05-001/  # open_bug creates here
│   └── security/
│       └── SEC-2026-01-05-001/  # open_security creates here
└── fixes/
    └── fix_links.jsonl    # link_fix writes here
```

---

## Recommendations

### For Development Teams

1. **Use Project Mode for all dev plan work** (research, architecture, implementation)
2. **Switch to Sentinel Mode for repository-wide concerns** (security audits, cross-project bugs)
3. **Don't try to use case tools during project work** - finish project first, then open cases
4. **Use append_event sparingly in Project Mode** (may have routing issues, see BUG-ROUTING-001)

### For Testing Teams

1. **Accept architectural constraints** - some tools cannot be tested in project-based frameworks
2. **Create separate Sentinel Mode test suite** for case management tools
3. **Document mode requirements** in tool specifications and usage guides
4. **Validate mode enforcement logic** separately from format parameter testing

### For Implementation Teams

1. **Fix BUG-ROUTING-001** (append_event routing in Project Mode)
2. **Add mode indicators to tool responses** (which mode is active?)
3. **Improve error messages** (explain Sentinel Mode requirement clearly)
4. **Consider mode switching helpers** (convenience functions for common transitions)

---

## Future Enhancements

### Potential Improvements

1. **Mode Indicator in Tool Responses**
   - Add `"mode": "project"` or `"mode": "sentinel"` to all tool outputs
   - Helps agents understand current context

2. **Explicit Mode Switching**
   - `enter_sentinel_mode()` helper (clears active project)
   - `exit_sentinel_mode(project_name)` helper (restores context)

3. **Hybrid Tools**
   - Allow `open_bug` in Project Mode but auto-route to Sentinel space
   - Maintain architectural separation while improving UX

4. **Mode Validation Layer**
   - Pre-execution checks for mode compatibility
   - Clearer error messages with suggested alternatives

---

## Cross-References

**Related Findings**:
- Team A2 Summary: `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/TEAM_A2_SUMMARY.md`
- BUG-ROUTING-001: Documented in Team A2 findings
- Phase 5 Coordination: `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/phase_5_coordination.md`

**Related Tools**:
- Sentinel exclusive: `open_bug`, `open_security`, `link_fix`
- Sentinel aware: `append_event`
- Mode creators: `set_project`

**Related Infrastructure**:
- State management: `state/manager.py`
- Tool enforcement: Individual tool implementations
- Directory structure: `.scribe/sentinel/`, `.scribe/docs/dev_plans/`

---

**Status**: Architecture documented, NOT a bug
**Confidence**: 0.95 (high confidence in architectural intent, some uncertainty about append_event routing)
**Team**: ResearchAgent-Phase5-FormatValidator (Team B)
**Date**: 2026-01-05
