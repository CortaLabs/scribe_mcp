---
id: query_enhancement_suite-query-suite-phase-plan
title: "Query Enhancement Suite \u2014 Phase Plan"
doc_name: QUERY_SUITE_PHASE_PLAN
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
# Query Enhancement Suite — Phase Plan

**Project:** query_enhancement_suite  
**Sub-Plan:** query_suite_v1  
**Architect:** ArchitectAgent-QuerySuite  
**Created:** 2026-02-01

---

## Phase Overview

| Phase | Name | Estimated Complexity | Dependencies | Risk Level |
|-------|------|----------------------|--------------|------------|
| 1 | Bug/Security Workflow Overhaul | Medium (1-2 sessions) | None | LOW |
| 2 | Query Tool Enhancements | Low (1 session) | None | LOW |
| 3 | Session-Aware Filtering | Medium-High (2-3 sessions) | ExecutionContext (exists) | MEDIUM |

**Implementation Order Rationale:**
- **Phase 1 first:** Self-contained, high user impact, no schema changes, safe
- **Phase 2 second:** Quick wins, improves UX, no dependencies
- **Phase 3 last:** Highest complexity, schema changes, requires testing

---

## Phase 1: Bug/Security Workflow Overhaul

**Goal:** Enable richer bug/security report creation at write-time by expanding `open_bug` and `open_security` parameter schemas.

**Success Criteria:**
- Bug reports created with ≥50% template completion on first write
- Completeness scoring returned in response
- Unfilled sections use consistent `[UNFILLED]` marker
- Zero breaking changes to existing calls

### Task Package 1.1: Expand open_bug Parameter Schema

**Scope:** Add 8 optional parameters to `open_bug` function signature and wire to metadata dict

**Files to Modify:**
- `tools/sentinel_tools.py` (lines 278-380, `open_bug` function only)

**Dependencies:** None

**Specifications:**

1. **Update function signature** (line 278-284):
   ```python
   async def open_bug(
       agent: str,
       title: str,
       symptoms: str,
       category: str,
       affected_paths: Optional[list[str]] = None,
       # NEW optional parameters (add these):
       expected_behaviour: Optional[str] = None,
       steps_to_reproduce: Optional[list[str]] = None,
       root_cause: Optional[str] = None,
       resolution_notes: Optional[str] = None,
       severity: Optional[str] = None,  # Overrides default "medium"
       component: Optional[str] = None,
       environment: Optional[str] = None,
       customer_impact: Optional[str] = None,
   ) -> Dict[str, Any]:
   ```

2. **Expand metadata dict** (lines 336-350):
   - Add conditional mappings for each new parameter
   - Use `if param is not None` checks to avoid overwriting defaults
   - Map to correct template field names:
   
   ```python
   metadata = {
       "doc_type": "bug",
       "category": category,
       "slug": case_id,
       "title": title,
       "case_id": case_id,
       "symptoms": symptoms,
       "summary_long": symptoms,
       "actual_behavior": symptoms,
       "affected_paths": affected_paths or [],
       "affected_areas": affected_paths or [],
       "reporter": agent,
       "status": "INVESTIGATING",
       "severity": severity if severity is not None else "medium",
       # NEW mappings:
       "expected_behavior": expected_behaviour if expected_behaviour is not None else "[UNFILLED]",
       "reproduction_steps": steps_to_reproduce if steps_to_reproduce is not None else ["[UNFILLED]"],
       "root_cause": root_cause if root_cause is not None else "[UNFILLED]",
       "immediate_actions": resolution_notes if resolution_notes is not None else "[UNFILLED]",
       "component": component if component is not None else "[UNFILLED]",
       "environment": environment if environment is not None else "[UNFILLED]",
       "customer_impact": customer_impact if customer_impact is not None else "[UNFILLED]",
   }
   ```

3. **Update docstring** (lines 285-293):
   - Add documentation for new parameters
   - Include type hints and descriptions

**Verification:**
- [ ] `open_bug` with minimal params (existing behavior) works unchanged
- [ ] `open_bug` with new params populates template fields correctly
- [ ] Unpopulated fields show `[UNFILLED]` marker
- [ ] Docstring includes all new parameters

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify `open_security` yet (separate task)
- Do NOT modify template file (template already supports these fields)
- Do NOT change existing return value structure (Task 1.3 handles that)

---

### Task Package 1.2: Expand open_security Parameter Schema

**Scope:** Apply identical changes to `open_security` function

**Files to Modify:**
- `tools/sentinel_tools.py` (lines 399-500, `open_security` function only)

**Dependencies:** Task 1.1 (use as reference implementation)

**Specifications:**

1. **Copy signature changes** from Task 1.1
2. **Copy metadata mappings** from Task 1.1 (same 8 new params)
3. **Update docstring** with same parameter descriptions

**Verification:**
- [ ] `open_security` signature matches `open_bug` signature (param-for-param)
- [ ] Security reports populate identically to bug reports
- [ ] All Task 1.1 verification criteria apply

**Out of Scope:**
- Do NOT diverge from `open_bug` implementation
- Do NOT add security-specific params (keep schemas identical)

---

### Task Package 1.3: Add Completeness Scoring to Response

**Scope:** Calculate and return completeness metadata in `open_bug` and `open_security` responses

**Files to Modify:**
- `tools/sentinel_tools.py` (return statements in both functions)

**Dependencies:** Tasks 1.1 and 1.2 (param expansion must be complete)

**Specifications:**

1. **Define template field list** (add as module constant at top of file):
   ```python
   # After imports, before functions:
   _BUG_TEMPLATE_FIELDS = [
       "summary", "symptoms", "category", "severity", "status",
       "expected_behavior", "actual_behavior", "reproduction_steps",
       "component", "environment", "customer_impact", "affected_areas",
       "root_cause", "immediate_actions",
       # Add remaining template fields from BUG_REPORT_TEMPLATE.md
       # (check template for complete list)
   ]
   ```

2. **Calculate completeness** before return statement (both functions):
   ```python
   # Count filled vs unfilled fields
   filled_sections = []
   unfilled_sections = []
   
   for field in _BUG_TEMPLATE_FIELDS:
       value = metadata.get(field)
       if value and value != "[UNFILLED]" and value != ["[UNFILLED]"]:
           filled_sections.append(field)
       else:
           unfilled_sections.append(field)
   
   total_fields = len(_BUG_TEMPLATE_FIELDS)
   filled_count = len(filled_sections)
   percentage = int((filled_count / total_fields) * 100) if total_fields > 0 else 0
   ```

3. **Enhance return value** (lines 365-380 for open_bug, similar for open_security):
   ```python
   return {
       "ok": True,
       "case_id": str(case_id),
       "entry_id": str(result.get("id", "")),
       "path": str(result.get("path", "")),
       "project_name": str(result.get("project_name", "")),
       "bug_report": str(doc_result.get("path", "")),
       # NEW completeness metadata:
       "completeness": {
           "score": f"{filled_count}/{total_fields}",
           "percentage": percentage,
           "filled_sections": filled_sections,
           "unfilled_sections": unfilled_sections,
       },
       # UPDATED action_required (more specific guidance):
       "action_required": (
           f"Bug report {percentage}% complete. "
           f"Use manage_docs(agent='{agent}', action='replace_section', "
           f"doc_name='{case_id}', section='<section_id>', content='...') "
           f"to fill remaining sections: {', '.join(unfilled_sections[:5])}"
       ),
   }
   ```

**Verification:**
- [ ] Completeness score calculated correctly
- [ ] `filled_sections` lists only non-`[UNFILLED]` fields
- [ ] `unfilled_sections` lists `[UNFILLED]` fields
- [ ] Percentage calculation accurate
- [ ] Response structure backward compatible (adds fields, doesn't remove)

**Out of Scope:**
- Do NOT make completeness configurable (hardcode for MVP)
- Do NOT add completeness validation (scoring only, no enforcement)

---

## Phase 2: Query Tool Enhancements

**Goal:** Provide graceful error responses when no project context exists.

**Success Criteria:**
- `read_recent()` with no project returns helpful info (not bare error)
- Response includes `last_known_project` metadata when available
- Suggested next steps included in error response

### Task Package 2.1: Enhance read_recent Stateless Mode

**Scope:** Add last_known_project info to error response when no project set

**Files to Modify:**
- `tools/read_recent.py` (error handler, around lines 263-276)

**Dependencies:** None (copies existing pattern from get_project)

**Specifications:**

1. **Locate ProjectResolutionError handler** (around line 263):
   - Find: `except ProjectResolutionError as exc:`

2. **Replace bare error return** with enhanced error response:
   ```python
   except ProjectResolutionError as exc:
       # Enhanced error response with last_known_project info
       extra = {}
       try:
           from scribe_mcp.state.project_registry import _PROJECT_REGISTRY
           last_known = _PROJECT_REGISTRY.get_last_known_project()
           if last_known and last_known.last_access_at:
               from datetime import datetime, timezone
               now = datetime.now(timezone.utc)
               delta = now - last_known.last_access_at
               minutes_ago = int(delta.total_seconds() / 60)
               
               extra["last_known_project"] = last_known.project_name
               extra["last_known_project_minutes_ago"] = minutes_ago
               extra["last_known_project_last_access_at"] = last_known.last_access_at.isoformat()
       except Exception:
           pass  # Fail gracefully if last_known unavailable
       
       base_response = _READ_RECENT_HELPER.translate_project_error(exc)
       base_response["extra"] = extra
       base_response["suggestion"] = (
           "Try: set_project(agent='<agent_name>', name='<project_name>') or "
           "query_entries(agent='<agent_name>', search_scope='all_projects')"
       )
       return base_response
   ```

3. **Import statements** (add at top if not present):
   - Verify `_PROJECT_REGISTRY` import exists or add it
   - Verify `datetime, timezone` imports exist or add them

**Verification:**
- [ ] `read_recent` with no project returns enhanced error
- [ ] `extra` dict includes `last_known_project` when available
- [ ] `extra` dict empty when no last_known (graceful degradation)
- [ ] `suggestion` field provides actionable next steps
- [ ] No exceptions raised during error handling

**Out of Scope:**
- Do NOT modify core read_recent logic (error handler only)
- Do NOT modify get_project (optional enhancement deferred)
- Do NOT add project list (future enhancement)

---

## Phase 3: Session-Aware Filtering

**Goal:** Add session-based filtering to query_entries by persisting session_id on log entries.

**Success Criteria:**
- `session_id` column exists on `scribe_entries` table
- New entries populate `session_id` from ExecutionContext
- `query_entries(session_id=X)` filters entries by session
- Zero breaking changes (NULL session_id for old entries)

### Task Package 3.1: Schema Migration

**Scope:** Add `session_id` column to `scribe_entries` table and create index

**Files to Modify:**
- `storage/sqlite.py` (_initialise method, around lines 1076-1113)

**Dependencies:** None

**Specifications:**

1. **Locate migration section** in `_initialise` method:
   - Find existing `_ensure_column` calls (priority, category, tags, confidence)
   - Add new migration after existing ones

2. **Add session_id migration**:
   ```python
   # Add after existing _ensure_column calls (around line 1113):
   await self._ensure_column("scribe_entries", "session_id", "TEXT")
   
   # Add index for efficient session filtering:
   await self._execute(
       "CREATE INDEX IF NOT EXISTS idx_entries_session ON scribe_entries(session_id);"
   )
   ```

3. **Verify idempotency**:
   - `_ensure_column` is already idempotent (checks if column exists)
   - `CREATE INDEX IF NOT EXISTS` is idempotent

**Verification:**
- [ ] After MCP server restart, `session_id` column exists
- [ ] `PRAGMA table_info(scribe_entries)` shows `session_id TEXT` column
- [ ] `idx_entries_session` index exists on `session_id` column
- [ ] Existing entries have NULL `session_id` (no data loss)
- [ ] Migration runs successfully on fresh database

**Out of Scope:**
- Do NOT modify table structure beyond adding column
- Do NOT backfill session_id for old entries (NULL is correct)
- Do NOT add foreign key constraints (session_id is denormalized)

---

### Task Package 3.2: Update insert_entry Signatures

**Scope:** Add `session_id` parameter to abstract and concrete `insert_entry` methods

**Files to Modify:**
- `storage/base.py` (abstract method signature, around lines 76-88)
- `storage/sqlite.py` (concrete implementation, around lines 319-370)

**Dependencies:** Task 3.1 (column must exist before inserting)

**Specifications:**

1. **Update abstract signature** in `storage/base.py` (line 76-88):
   ```python
   @abstractmethod
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
       session_id: Optional[str] = None,  # NEW parameter
   ) -> None:
       """Insert a progress log entry and update metrics."""
   ```

2. **Update concrete signature** in `storage/sqlite.py` (line 319-336):
   - Add `session_id: Optional[str] = None` to parameter list (after existing params)

3. **Update INSERT statement** in `storage/sqlite.py` (lines 364-370):
   ```python
   await self._execute(
       """
       INSERT OR IGNORE INTO scribe_entries
           (id, project_id, ts, emoji, agent, message, meta, raw_line, sha256, ts_iso, priority, category, tags, confidence, log_type, session_id)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
       """,
       (
           entry_id, project.id, ts.strftime("%Y-%m-%d %H:%M:%S.%f"),
           emoji, agent, message, meta_json, raw_line, sha256, ts_iso,
           priority, category, tags, confidence, log_type, session_id,  # Add session_id
       ),
   )
   ```

**Verification:**
- [ ] Abstract signature includes `session_id` parameter
- [ ] Concrete signature matches abstract signature
- [ ] INSERT statement includes `session_id` in columns and values
- [ ] Parameter order matches between signature and INSERT tuple
- [ ] Existing tests pass (session_id=None is valid)

**Out of Scope:**
- Do NOT modify query_entries signature yet (Task 3.4)
- Do NOT modify other storage backend methods
- Do NOT add session_id to other tables (scribe_entries only)

---

### Task Package 3.3: Wire session_id Through append_entry

**Scope:** Extract session_id from ExecutionContext and pass to insert_entry

**Files to Modify:**
- `tools/append_entry.py` (_process_single_entry function, around line 633)

**Dependencies:** Task 3.2 (insert_entry signature must accept session_id)

**Specifications:**

1. **Locate insert_entry call** in `_process_single_entry` (around line 633):
   - Find: `await backend.insert_entry(...)`

2. **Extract session_id from context** before insert_entry call:
   ```python
   # Extract session_id from context (if available)
   session_id = context.session_id if context else None
   ```

3. **Add session_id to insert_entry call**:
   ```python
   await backend.insert_entry(
       entry_id=entry_id,
       project=project,
       ts=ts,
       emoji=emoji,
       agent=agent,
       message=message,
       meta=meta,
       raw_line=raw_line,
       sha256=sha256_hash,
       session_id=session_id,  # NEW parameter
   )
   ```

4. **Verify bulk mode** handles session_id consistently:
   - Bulk entries all use the same context.session_id (loop doesn't change context)
   - No special handling needed

**Verification:**
- [ ] New entries populate `session_id` column with context.session_id value
- [ ] Entries without context (None) have NULL session_id (backward compat)
- [ ] Bulk append_entry creates entries with consistent session_id
- [ ] ExecutionContext.session_id format matches expected SHA256 pattern

**Out of Scope:**
- Do NOT modify ExecutionContext (already computes session_id)
- Do NOT add session_id validation (accept value as-is)
- Do NOT backfill session_id for existing entries

---

### Task Package 3.4: Add session_id Filter to query_entries

**Scope:** Add optional `session_id` parameter to query_entries tool and storage method

**Files to Modify:**
- `tools/query_entries.py` (signature and parameter handling)
- `storage/sqlite.py` (query_entries WHERE clause, around lines 613-649)

**Dependencies:** Tasks 3.1, 3.2, 3.3 (session_id must be persisted before querying)

**Specifications:**

1. **Update tool signature** in `tools/query_entries.py` (function signature):
   ```python
   async def query_entries(
       agent: str,
       project: Optional[str] = None,
       session_id: Optional[str] = None,  # NEW parameter
       agents: Optional[List[str]] = None,
       # ... existing parameters ...
   ) -> Dict[str, Any]:
   ```

2. **Update docstring** to document session_id parameter:
   ```python
   """
   Args:
       agent: Agent identifier (for audit trail)
       project: Project name filter
       session_id: Filter entries by session ID (optional)
       agents: Filter by agent names (search filter, NOT caller identity)
       ...
   """
   ```

3. **Pass session_id to storage layer** (find backend.query_entries call):
   - Add `session_id=session_id` to backend.query_entries call

4. **Update storage signature** in `storage/sqlite.py` (around line 594):
   ```python
   async def query_entries(
       self,
       *,
       project: ProjectRecord,
       session_id: Optional[str] = None,  # NEW parameter
       # ... existing parameters ...
   ) -> List[Dict[str, Any]]:
   ```

5. **Add WHERE clause filter** in `storage/sqlite.py` (around line 630):
   ```python
   # After existing WHERE clauses:
   if session_id:
       clauses.append("e.session_id = ?")
       params.append(session_id)
   ```

**Verification:**
- [ ] `query_entries(session_id="abc123")` returns only entries with that session_id
- [ ] `query_entries()` without session_id works unchanged (backward compat)
- [ ] Entries with NULL session_id excluded when session_id filter provided
- [ ] Session filtering works across projects (if search_scope permits)
- [ ] Results ordered chronologically within session

**Out of Scope:**
- Do NOT add session_id to read_recent (different tool, future enhancement)
- Do NOT add session_id validation (accept any string)
- Do NOT add session analytics (filtering only)

---

## Implementation Order Summary

**Week 1:**
- Task 1.1 (open_bug params) → Task 1.2 (open_security params) → Task 1.3 (completeness scoring)
- Tasks 1.1-1.3 can be done in single session (related code)

**Week 2:**
- Task 2.1 (read_recent enhancement) — standalone, quick win

**Week 3:**
- Task 3.1 (migration) → restart MCP → verify schema
- Task 3.2 (insert_entry sigs) → Task 3.3 (append_entry wiring) — same session
- Task 3.4 (query_entries filter) — separate session, requires 3.1-3.3 complete

**Critical Path:**
- Phase 3 tasks MUST be done in order (3.1 → 3.2 → 3.3 → 3.4)
- Phase 1 and 2 are independent (can be parallelized if multiple coders)

---

## Testing Requirements

**Phase 1 Tests:**
```python
# tests/test_sentinel_tools.py

def test_open_bug_minimal_params():
    """Existing behavior: minimal params work unchanged"""
    
def test_open_bug_full_params():
    """New behavior: all optional params populate template"""
    
def test_open_bug_completeness_scoring():
    """Completeness calculation accurate"""

def test_open_security_matches_open_bug():
    """open_security has identical param schema"""
```

**Phase 2 Tests:**
```python
# tests/test_read_recent.py

def test_read_recent_stateless_enhanced_error():
    """Error response includes last_known_project"""
    
def test_read_recent_stateless_no_last_known():
    """Graceful degradation when no last_known"""
```

**Phase 3 Tests:**
```python
# tests/test_storage_sqlite.py

def test_session_id_column_exists():
    """Migration adds session_id column"""
    
def test_insert_entry_with_session_id():
    """session_id persisted correctly"""

# tests/test_append_entry.py

def test_append_entry_wires_session_id():
    """Context.session_id passed to insert_entry"""

# tests/test_query_entries.py

def test_query_entries_session_filter():
    """session_id filter works correctly"""
    
def test_query_entries_session_null_excluded():
    """NULL session_id entries excluded from results"""
```

---

## Rollback Plan

**Phase 1 Rollback:**
- Revert `tools/sentinel_tools.py` to previous version
- No database changes to rollback
- Risk: LOW (pure code change)

**Phase 2 Rollback:**
- Revert `tools/read_recent.py` to previous version
- No database changes to rollback
- Risk: LOW (error handling only)

**Phase 3 Rollback:**
- **DO NOT drop session_id column** (NULL values safe, backward compatible)
- Revert code changes: base.py, sqlite.py, append_entry.py, query_entries.py
- Database backup recommended before Phase 3 deployment
- Risk: MEDIUM (schema change, but backward compatible)

---

*Phase Plan v1.0 — Query Enhancement Suite — ArchitectAgent-QuerySuite — 2026-02-01*
