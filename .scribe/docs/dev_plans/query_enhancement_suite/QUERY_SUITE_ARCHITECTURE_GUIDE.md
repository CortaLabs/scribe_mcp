---
id: query_enhancement_suite-query-suite-architecture-guide
title: "Query Enhancement Suite \u2014 Architecture Guide"
doc_name: QUERY_SUITE_ARCHITECTURE_GUIDE
category: engineering
status: draft
version: '0.1'
last_updated: '2026-02-02'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Query Enhancement Suite — Architecture Guide

**Project:** query_enhancement_suite  
**Sub-Plan:** query_suite_v1  
**Architect:** ArchitectAgent-QuerySuite  
**Created:** 2026-02-01  
**Status:** Design Complete

---

## Problem Statement
<!-- ID: problem_statement -->

**Context:** Scribe MCP's query and bug reporting tools have three distinct usability gaps identified through research:

1. **Bug/Security Report Template Population Gap**: `open_bug` and `open_security` accept only 5 parameters (title, symptoms, category, affected_paths) but the bug report template expects 25+ fields. This results in 80% of bug report sections containing placeholder text, forcing manual follow-up edits that agents often skip.

2. **Query Tool Stateless Mode Gaps**: `read_recent` and `get_project` return bare errors when no project is set, providing no actionable context. `get_project` already has a good pattern (returns `last_known_project` info), but `read_recent` needs this enhanced.

3. **Session-Based Filtering Missing**: The `scribe_entries` table lacks a `session_id` column, preventing session-based querying. Council_MCP demonstrates this pattern successfully with session FKs on all records.

**Goals:**
- Enable richer bug/security report creation at write-time (not follow-up edits)
- Provide helpful responses when no project context exists
- Support session-based filtering for workflow correlation
- Maintain 100% backward compatibility (no breaking changes)
- Follow existing patterns (migrations, error responses, Council_MCP session model)

**Success Metrics:**
- Bug reports created with ≥50% template completion on first write
- `read_recent()` with no project returns useful info (not error)
- `query_entries(session_id=X)` successfully filters entries by session
- Zero breaking changes to existing tool calls

---

## System Overview
<!-- ID: system_overview -->

**Architecture Pattern:** Incremental enhancement of existing tools via optional parameters and schema additions. No new tools, no major refactoring.

**Three Enhancement Workstreams:**

### Workstream 1: Bug/Security Report Workflow Overhaul (Phase 1)
- **Scope:** Expand `open_bug` and `open_security` parameter schemas
- **Impact:** tools/sentinel_tools.py (2 functions), templates/BUG_REPORT_TEMPLATE.md (template mapping)
- **Risk:** LOW (all new params optional, backward compatible)

### Workstream 2: Query Tool Enhancements (Phase 2)
- **Scope:** Graceful error responses in `read_recent` and `get_project` when no project set
- **Impact:** tools/read_recent.py (error handler), tools/get_project.py (optional enhancement)
- **Risk:** LOW (error handling only, no core logic changes)

### Workstream 3: Session-Aware Filtering (Phase 3)
- **Scope:** Add `session_id` column to `scribe_entries`, wire through append_entry, add filter to query_entries
- **Impact:** storage/sqlite.py (schema + migration), storage/base.py (abstract method), tools/append_entry.py (context wiring), tools/query_entries.py (filter parameter)
- **Risk:** MEDIUM (schema change + multiple integration points)

**Dependencies:**
- Phase 1 standalone (no dependencies)
- Phase 2 standalone (no dependencies)
- Phase 3 depends on ExecutionContext infrastructure (already exists)

---

## Component Design
<!-- ID: component_design -->

### Component 1: Enhanced Bug/Security Report Creation

**Current State:**
```python
async def open_bug(
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
```

**New State:**
```python
async def open_bug(
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
    # NEW optional parameters:
    expected_behaviour: Optional[str] = None,
    steps_to_reproduce: Optional[list[str]] = None,
    root_cause: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,  # Already exists but not exposed
    component: Optional[str] = None,
    environment: Optional[str] = None,
    customer_impact: Optional[str] = None,
) -> Dict[str, Any]:
```

**Design Decisions:**
- **All new params optional** (backward compatibility)
- **Map directly to template fields** (no translation layer)
- **String interpolation at write-time** (not follow-up edits)
- **Consistent [UNFILLED] markers** for unpopulated sections
- **Completeness scoring in response** (filled/total ratio)

**Response Enhancement:**
```python
return {
    "ok": True,
    "case_id": "BUG-2026-02-01-0003",
    "bug_report": "/path/to/report.md",
    "completeness": {
        "score": "7/25",
        "percentage": 28,
        "filled_sections": ["summary", "symptoms", "category", ...],
        "unfilled_sections": ["investigation", "resolution_plan", ...],
    },
    "action_required": "manage_docs(agent='X', action='replace_section', doc_name='BUG-2026-02-01-0003', section='investigation', content='...')"
}
```

**Unfilled Section Marker:**
- Use consistent `[UNFILLED]` marker instead of varied placeholder text
- Enables easy grep for incomplete sections
- Clear signal for agents that content is missing

### Component 2: Graceful Stateless Mode Responses

**Pattern (from get_project.py:435-461):**
```python
except ProjectResolutionError as exc:
    extra = {}
    try:
        last_known = _PROJECT_REGISTRY.get_last_known_project()
        if last_known and last_known.last_access_at:
            extra["last_known_project"] = last_known.project_name
            extra["last_known_project_minutes_ago"] = calculate_minutes_ago(...)
            extra["last_known_project_last_access_at"] = last_known.last_access_at.isoformat()
    except Exception:
        pass
    return {"ok": False, "error": str(exc), "extra": extra}
```

**Apply to read_recent.py:**
- Copy pattern from get_project
- Add helpful suggestion: "Invoke set_project or use query_entries with search_scope='all_projects'"
- Include last_known_project info when available

**Optional get_project enhancement:**
- Add brief project list (top 3-5 by activity)
- Keep response compact (names + last_activity only)

### Component 3: Session-Aware Filtering

**Schema Change:**
```sql
-- Add to scribe_entries table
ALTER TABLE scribe_entries ADD COLUMN session_id TEXT;
CREATE INDEX IF NOT EXISTS idx_entries_session ON scribe_entries(session_id);
```

**Migration (in storage/sqlite.py _initialise):**
```python
await self._ensure_column("scribe_entries", "session_id", "TEXT")
await self._execute(
    "CREATE INDEX IF NOT EXISTS idx_entries_session ON scribe_entries(session_id);"
)
```

**insert_entry Signature Update:**
```python
# storage/base.py (abstract)
async def insert_entry(
    self,
    *,
    entry_id: str,
    project: ProjectRecord,
    ts: datetime,
    emoji: str,
    agent: Optional[str],
    message: str,
    meta: Optional[Dict[str, Any]],
    raw_line: str,
    sha256: str,
    session_id: Optional[str] = None,  # NEW
) -> None:

# storage/sqlite.py (implementation)
# Add session_id to INSERT statement columns and values
```

**append_entry Integration:**
```python
# In tools/append_entry.py _process_single_entry (around line 633)
session_id = context.session_id if context else None
await backend.insert_entry(
    # ... existing params ...
    session_id=session_id,
)
```

**query_entries Filter Addition:**
```python
# tools/query_entries.py signature
async def query_entries(
    agent: str,
    project: Optional[str] = None,
    session_id: Optional[str] = None,  # NEW
    agents: Optional[List[str]] = None,
    # ... existing params ...
)

# storage/sqlite.py query_entries WHERE clause
if session_id:
    clauses.append("e.session_id = ?")
    params.append(session_id)
```

---

## Data Flow
<!-- ID: data_flow -->

### Flow 1: Enhanced Bug Report Creation

```
1. Agent calls open_bug with optional params
   ↓
2. sentinel_tools.py builds metadata dict
   - Maps all provided params to template fields
   - Unpopulated fields remain as [UNFILLED]
   ↓
3. manage_docs(action="create", metadata={...})
   - Routes to bug report template
   - String interpolation at write-time
   ↓
4. Response includes completeness scoring
   - Calculates filled/total ratio
   - Lists unfilled sections
   - Provides exact manage_docs call pattern
```

### Flow 2: Stateless Mode Response

```
1. read_recent() called with no project set
   ↓
2. ProjectResolutionError raised
   ↓
3. Error handler catches exception
   - Queries _PROJECT_REGISTRY.get_last_known_project()
   - Adds last_known_project info to extra dict
   ↓
4. Returns helpful error with context
   - Error message
   - Last known project name + timestamp
   - Suggested next steps
```

### Flow 3: Session-Aware Filtering

```
1. append_entry called (ExecutionContext available)
   ↓
2. context.session_id extracted
   - Already computed via SHA256(repo:mode:scope:agent)
   ↓
3. backend.insert_entry(..., session_id=X)
   - Persists to scribe_entries.session_id column
   ↓
4. query_entries(session_id=X)
   - Adds WHERE clause filter
   - Returns entries from specific session
   ↓
5. Results chronologically ordered within session
```

---

## API Design
<!-- ID: api_design -->

### Enhanced open_bug/open_security

**New Optional Parameters:**

| Parameter | Type | Default | Template Field | Description |
|-----------|------|---------|----------------|-------------|
| `expected_behaviour` | `str` | `None` | `expected_behavior` | What should happen normally |
| `steps_to_reproduce` | `list[str]` | `None` | `reproduction_steps` | Ordered steps to reproduce |
| `root_cause` | `str` | `None` | `root_cause` | Suspected or confirmed root cause |
| `resolution_notes` | `str` | `None` | `immediate_actions` | Immediate fix actions taken |
| `severity` | `str` | `"medium"` | `severity` | Severity level (low/medium/high/critical) |
| `component` | `str` | `None` | `component` | Component or subsystem affected |
| `environment` | `str` | `None` | `environment` | Environment (local/staging/production) |
| `customer_impact` | `str` | `None` | `customer_impact` | Customer-facing impact description |

**Response Schema Enhancement:**
```python
{
    "ok": True,
    "case_id": str,
    "bug_report": str,  # Path to report.md
    "completeness": {
        "score": str,  # "7/25"
        "percentage": int,  # 28
        "filled_sections": list[str],
        "unfilled_sections": list[str],
    },
    "action_required": str,  # Exact manage_docs call pattern
}
```

### Enhanced read_recent Stateless Mode

**Before:**
```python
{
    "ok": False,
    "error": "No project configured. Invoke set_project."
}
```

**After:**
```python
{
    "ok": False,
    "error": "No project configured. Invoke set_project.",
    "extra": {
        "last_known_project": "my_project",
        "last_known_project_minutes_ago": 5,
        "last_known_project_last_access_at": "2026-02-01T23:00:00Z"
    },
    "suggestion": "Try: set_project(agent='X', name='my_project') or query_entries(agent='X', search_scope='all_projects')"
}
```

### Session-Aware query_entries

**New Parameter:**
- `session_id: Optional[str] = None`

**Behavior:**
- When provided, adds `WHERE session_id = ?` to SQL query
- Results ordered chronologically within session
- Works across projects (if search_scope permits)
- NULL-safe (existing entries with NULL session_id are excluded)

**Example:**
```python
query_entries(
    agent="Orchestrator",
    session_id="abc123def456",
    format="readable"
)
# Returns all entries from that session, any project
```

---

## Security Considerations
<!-- ID: security_considerations -->

1. **SQL Injection Protection**: All parameters use parameterized queries (existing pattern maintained)
2. **Session ID Integrity**: Session IDs computed via SHA256, not user-provided (prevents session hijacking)
3. **Backward Compatibility**: NULL session_id for old entries (no data loss)
4. **Permission Model**: Session filtering respects existing project permissions (no new attack surface)
5. **Input Validation**: All optional params validated before persistence (existing validation extended)

**Risk Assessment:**
- **Schema Migration**: LOW (column addition is safe, backward compatible)
- **API Expansion**: LOW (all new params optional, existing calls unchanged)
- **Error Response Changes**: LOW (errors already returned, just enriched with context)

---

## Testing Strategy
<!-- ID: testing_strategy -->

### Phase 1: Bug/Security Workflow Tests
- Unit test: `open_bug` with minimal params (existing behavior)
- Unit test: `open_bug` with all optional params (full population)
- Unit test: `open_security` with mixed params (partial population)
- Integration test: Bug report file content verification
- Integration test: Completeness scoring calculation
- Regression test: Existing `open_bug` calls from progress logs

### Phase 2: Query Tool Enhancement Tests
- Unit test: `read_recent` stateless mode response structure
- Unit test: `get_project` stateless mode enhancement (if implemented)
- Integration test: `last_known_project` retrieval from registry
- Edge case test: No projects exist (should gracefully handle)

### Phase 3: Session Filtering Tests
- Migration test: `session_id` column added successfully
- Migration test: Index created on `session_id` column
- Unit test: `insert_entry` with session_id
- Unit test: `insert_entry` with session_id=None (backward compat)
- Unit test: `query_entries` with session_id filter
- Integration test: End-to-end session filtering
- Integration test: Bulk append_entry with consistent session_id
- Performance test: Session filtering on large datasets

### Test Verification Criteria
- All existing tests pass (no regressions)
- New tests achieve ≥90% coverage of new code paths
- Integration tests verify end-to-end workflows
- Performance tests confirm <100ms overhead for session filtering

---

## Deployment Strategy
<!-- ID: deployment_strategy -->

**Phased Rollout:**

1. **Phase 1 Deployment** (Bug/Security Workflow)
   - Deploy: tools/sentinel_tools.py changes
   - Verify: Create test bug with new params
   - Rollback plan: Revert sentinel_tools.py (no schema changes)

2. **Phase 2 Deployment** (Query Tool Enhancements)
   - Deploy: tools/read_recent.py changes
   - Verify: Call read_recent with no project, check response
   - Rollback plan: Revert read_recent.py (no schema changes)

3. **Phase 3 Deployment** (Session-Aware Filtering)
   - **Pre-deploy:** Backup database
   - Deploy: storage/sqlite.py migration + storage/base.py + tools/append_entry.py + tools/query_entries.py
   - Verify: Restart MCP server (runs migration), check column exists, create entry with session_id, query by session_id
   - Rollback plan: Restore database backup (column can remain, backward compatible)

**Migration Safety:**
- Phase 3 migration uses `_ensure_column` (idempotent, safe)
- Column is nullable (existing entries unaffected)
- Index creation is conditional (IF NOT EXISTS)
- No data loss on rollback (column can remain empty)

**Monitoring:**
- Check TOOL_LOG.jsonl for errors after each phase
- Verify completeness scores in bug reports (Phase 1)
- Verify session_id population in new entries (Phase 3)
- Monitor query performance with session filtering (Phase 3)

---

## Implementation Notes
<!-- ID: implementation_notes -->

### Critical Patterns to Follow

1. **Migration Pattern** (from storage/sqlite.py:1076-1113):
   ```python
   await self._ensure_column("table_name", "column_name", "TYPE")
   ```
   - Used for priority, category, tags, confidence columns
   - Idempotent, safe for repeated runs

2. **Error Response Enhancement** (from tools/get_project.py:435-461):
   ```python
   extra = {}
   try:
       last_known = _PROJECT_REGISTRY.get_last_known_project()
       # ... populate extra ...
   except Exception:
       pass  # Fail gracefully
   return {"ok": False, "error": str(exc), "extra": extra}
   ```

3. **Context Extraction** (from tools/append_entry.py):
   ```python
   session_id = context.session_id if context else None
   ```
   - Safe None-check pattern
   - Used throughout codebase

### Gotchas to Avoid

1. **DO NOT merge agent (caller) into agents (filter)** — This bug was just fixed at query_entries.py:1079-1082
2. **DO NOT use direct SQL commands** — Always use migration functions
3. **DO NOT break existing calls** — All new params must be optional with defaults
4. **DO NOT forget to restart MCP server** — Migrations run in _initialise(), triggered on server start

### Files Modified Summary

**Phase 1:**
- `tools/sentinel_tools.py` (open_bug, open_security functions)
- `templates/documents/BUG_REPORT_TEMPLATE.md` (verify field mapping)

**Phase 2:**
- `tools/read_recent.py` (error handler)
- `tools/get_project.py` (optional enhancement)

**Phase 3:**
- `storage/base.py` (insert_entry signature)
- `storage/sqlite.py` (migration + insert_entry + query_entries)
- `tools/append_entry.py` (context.session_id wiring)
- `tools/query_entries.py` (session_id parameter + filter)

---

## Open Questions
<!-- ID: open_questions -->

1. **Should get_project enhancement include project list?** — Research suggests optional, low priority. Decision: defer to Phase 2 implementation feedback.

2. **Should completeness scoring be configurable?** — Some teams may want different thresholds. Decision: hardcode initially, make configurable if needed later.

3. **Should session_id be indexed uniquely or non-uniquely?** — Non-unique correct (many entries per session). Decision: non-unique index confirmed.

4. **Should unfilled marker be configurable?** — Currently hardcoded `[UNFILLED]`. Decision: keep consistent, change globally if needed.

5. **Should session filtering work across projects?** — Yes, session_id is cross-project by design (SHA256 includes repo_root, not project_name). Decision: support confirmed.

---

## Appendix
<!-- ID: appendix -->

### Research Documents Referenced
- `.scribe/docs/dev_plans/query_enhancement_suite/research/RESEARCH_QUERY_TOOLS_20260201.md`
- `.scribe/docs/dev_plans/query_enhancement_suite/research/RESEARCH_COUNCIL_SESSIONS_20260201.md`
- `.scribe/docs/dev_plans/query_enhancement_suite/research/RESEARCH_BUG_WORKFLOW_20260201.md`
- `.scribe/docs/dev_plans/query_enhancement_suite/PROJECT_BRIEF.md`

### Code Verification
- `tools/sentinel_tools.py:278-380` (open_bug implementation)
- `storage/sqlite.py:854-867` (scribe_entries schema)
- `storage/base.py:76-88` (insert_entry abstract signature)
- `tools/query_entries.py:1079-1082` (bug fix verification)

### Related Issues
- BUG-2026-02-01-0002: query_entries agent filter contamination (FIXED)
- BUG-2026-02-01-0001: Bug report template population gaps (ADDRESSING)

---

*Architecture Guide v1.0 — Query Enhancement Suite — ArchitectAgent-QuerySuite — 2026-02-01*
