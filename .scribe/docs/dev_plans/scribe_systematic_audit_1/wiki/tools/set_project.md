# set_project.py - Forensic Audit

**File**: `tools/set_project.py`
**LOC**: 807
**Size**: 30,093 bytes
**Complexity**: High
**Solo Ownership**: ResearchAgent-E-SetProject
**Audit Date**: 2026-01-05

---

## 1. Overview

`set_project.py` is the primary project lifecycle orchestrator for the Scribe MCP system. It handles:
- Project creation/selection with full documentation scaffolding
- Agent-scoped session binding (Phase 1 integration)
- Database mirroring across SQLite projects, dev_plans, and session tables
- SITREP generation (new vs existing project status reports)
- Doc inventory gathering and validation

**Purpose**: Create/activate projects and establish them as the current context for logging operations.

**Key Complexity Drivers**:
- Multiple storage backends (state.json, SQLite, ProjectRegistry)
- Dual SITREP formatters (new vs existing) with different output shapes
- Agent session management with optimistic concurrency control
- Document inventory gathering duplicated across tools
- 20+ optional parameters with complex normalization logic

---

## 2. Sub-System Breakdown

### 2.1 Parameter Normalization & Validation (Lines 131-233)
**Responsibility**: Heal incoming parameters from MCP framework, normalize dict/list params, resolve agent identity

**Key Functions**:
- `normalize_dict_param()` for `defaults` parameter (lines 168-185)
- `normalize_list_param()` for `tags` parameter (lines 207-215)
- `_normalise_defaults()` - merge emoji/agent from multiple sources (lines 594-621)

**Implicit Contracts**:
- Assumes MCP framework may send stringified JSON for dict params
- Silently falls back to empty dict if normalization fails
- Agent ID auto-detection via `get_agent_identity()` if not provided (line 160-165)

**Extractable Module Candidate**: [BUCKET:parameter_healing]
- Logic appears in append_entry, manage_docs, query_entries
- Clear contract: string → typed param with fallback handling
- Before/After: Before = each tool implements its own JSON parsing with different error handling. After = single ParameterHealer with consistent fallback policy

### 2.2 Path Resolution & Validation (Lines 219-243, 548-591, 691-739)
**Responsibility**: Resolve root/docs_dir/progress_log paths, validate permissions, detect collisions

**Key Functions**:
- `_resolve_root()` - handle absolute/relative roots (lines 548-560)
- `_resolve_docs_dir()` - .scribe vs legacy docs/dev_plans (lines 563-573)
- `_resolve_log()` - ensure log is within project root (lines 576-591)
- `_validate_project_paths()` - collision detection (lines 691-738)

**Design Decision**:
- Prefers `.scribe/docs/dev_plans/` over legacy `docs/dev_plans/` but maintains backward compat (line 567-573)
- Validates writability before attempting creation (lines 717-736)

**Implicit Contracts**:
- Progress log MUST be within project root (throws ValueError otherwise)
- Checks `os.W_OK` on first existing parent, not final path
- Silently skips temp test projects via `_is_temp_path()` check (lines 786-789)

### 2.3 Document Creation & Inventory (Lines 61-127, 624-688)
**Responsibility**: Bootstrap project documentation, gather inventory of existing docs

**Key Functions**:
- `_gather_project_inventory()` - scan docs for existence/line counts (lines 61-127)
- `_ensure_documents()` - idempotent doc generation (lines 624-688)

**DUPLICATION-002 FLAGGED** [BUCKET:metadata]:
- Same doc gathering logic exists in:
  - `set_project.py` lines 61-127 (this file)
  - `list_projects.py` lines ~200-350 (confirmed via brief)
  - `get_project.py` (mentioned in brief)
- Differences:
  - set_project: checks existence + line counts + custom content detection
  - list_projects: same checks but different return shape
  - get_project: adds doc hash tracking
- **Unification Opportunity**: Extract `DocInventoryGatherer` base contract that all 3 can use
- Before/After Mental Model:
  - Before: 3 responsibilities mixed (doc checking + line counting + hash tracking) in each tool
  - After: Single `DocInventoryGatherer` handles invariant checks, tools adapt results to their needs
  - Conceptual win: Tools reason about 'get doc status' not 'check files + count lines + hash content'

**Evidence**:
```python
# Lines 91-113: Standard doc checking pattern
arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
if arch_file.exists():
    result["docs"]["architecture"] = {
        "exists": True,
        "lines": default_formatter._get_doc_line_count(arch_file),
        "modified": False
    }
```

### 2.4 Database Mirroring (Lines 286-346, 408-440)
**Responsibility**: Mirror project data to SQLite (projects, dev_plans, sessions, agent tracking)

**Key Operations**:
- `backend.upsert_project()` - create/update project record (lines 290-294)
- `ProjectRegistry.ensure_project()` + `touch_access()` - registry tracking (lines 297-306, 336-346)
- `backend.upsert_dev_plan()` - populate dev_plans table for core docs (lines 310-334)
- `backend.set_session_project()` - critical session binding (line 415)
- `backend.upsert_agent_recent_project()` - agent tracking (line 440)

**CRITICAL BUG PREVENTION**:
Lines 410-437 use **stable_session_id** instead of unstable UUIDs for session binding
```python
# Line 411: Use stable session (deterministic) not context session (unstable UUID)
session_key = stable_session_id or context_session_id or session_id
```

**Error Handling**: Silent failures with print() fallback (lines 305, 333, 345, 391)
- Policy: Database mirroring failures should not block project creation
- Rationale: State.json is source of truth, SQLite is supplementary
- Tag: [BUCKET:error_handling] - Defensive swallowing with logging

### 2.5 Agent Session Binding (Lines 349-402)
**Responsibility**: Link agent to project via AgentContextManager with optimistic concurrency

**Key Functions**:
- `ensure_agent_session()` - create/reuse agent session (line 365)
- `agent_manager.set_current_project()` - bind project with version check (lines 376-381)

**Phase 1 Integration**:
- Uses `stable_session_id` from ExecutionContext (lines 358-359)
- Fallback to UUID session creation if stable session unavailable (lines 367-373)

**Optimistic Concurrency**:
- `expected_version` parameter enables conflict detection (line 139, 380)
- Version info returned in response (lines 383-386)

**Fallback Path**:
- If AgentContextManager fails, falls back to legacy global state (lines 389-393)
- `mirror_global = True` triggers JSON state update (line 401)

### 2.6 SITREP Formatting (Lines 454-531)
**Responsibility**: Generate human-readable status reports for new vs existing projects

**Two-Path Formatter**:
1. **New Project SITREP** (lines 463-489): "✨ NEW PROJECT CREATED" with docs listed
2. **Existing Project SITREP** (lines 491-531): Inventory + activity summary

**BUG-001 IDENTIFIED** (Line 461):
```python
# Line 460-461: BUG - entry_count check is wrong
entry_count = await _count_log_entries(progress_log_path)
is_new = not progress_log_path.exists() or entry_count == 0
```

**Issue**: `entry_count == 0` incorrectly treats empty logs as new projects
- Reproduction: Create project → rotate log (empty file) → call set_project again
- Expected: "Project activated" (existing SITREP)
- Actual: "New project created" (new SITREP)
- Root Cause: Should check file existence only, not entry count --- Nope, Incorrect.  We need to use the HASHES of the initial templated documents when they auto gen by set_project.  Check hashes and file size.   Ensure DB mirrors stats easily.

**Token Verbosity Analysis** (preliminary):
- New SITREP: ~400-500 tokens (4 docs listed + location box + status)
- Existing SITREP: ~600-800 tokens (inventory table + activity + reminders)
- Source: Delegated to `default_formatter.format_project_sitrep_new/existing()` (lines 472, 512)
- Tag: [BUCKET:formatting] - SITREP generation is shared concern

---

## 3. Modularization Notes

### Candidate Module: DocInventoryGatherer [BUCKET:metadata]
**Origin**: set_project.py:61-127, list_projects.py:~200-350, get_project.py
**Responsibilities**:
- Check existence of ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST, PROGRESS_LOG
- Count lines in each document
- Detect custom content (research files, bugs, jsonl files)
- Calculate doc hashes for drift detection (get_project variant)

**Used By**: set_project, list_projects, get_project, (potentially manage_docs for validation)

**Why it should be shared**:
- All tools need identical doc discovery logic
- Differences in return shape are tool-specific presentation, not core logic
- Current duplication risks inconsistency (e.g., one tool checks file X, another doesn't)

**Risks if extracted**:
- Tools may have subtle differences in what constitutes "custom content"
- Hash tracking only needed by get_project (optional extension point)

**Before/After**:
- Before: Doc checking + line counting + custom detection mixed with tool business logic in 3 places
- After: Single `DocInventoryGatherer` with clear contract, tools call `.gather(dev_plan_dir)` and adapt results
- Conceptual win: "Get doc status" is now a named, testable operation

---

### Candidate Module: ParameterHealer [BUCKET:parameter_healing]
**Origin**: set_project.py:168-185, append_entry.py (unknown lines), manage_docs.py (unknown lines)
**Responsibilities**:
- Detect MCP framework JSON-stringified params
- Attempt normalize_dict_param/normalize_list_param
- Fallback to safe defaults (empty dict, single-item list)
- Consistent error handling policy

**Used By**: All monster tools (append_entry, manage_docs, query_entries, rotate_log, set_project)

**Why it should be shared**:
- MCP framework quirks affect all tools equally
- Current duplication means different fallback behavior per tool
- Single source of truth for "what happens when normalization fails"

**Before/After**:
- Before: Each tool tries JSON parsing with different fallback strategies
- After: ParameterHealer.heal(param, expected_type, fallback) with consistent behavior
- Conceptual win: Parameter healing is policy, not scattered try/except blocks

---

### NOT a Candidate Module: Path Resolution
**Why it should NOT be modularized**:
- Path resolution logic is tightly coupled to set_project's specific contract
- _resolve_root, _resolve_docs_dir, _resolve_log all depend on settings.project_root and backward compat rules
- Extracting would require passing 5+ context params, no clarity gain

**Evidence of coupling**:
- Line 567-573: .scribe vs legacy docs/dev_plans logic is set_project-specific
- Line 582-584: Progress log must be within project root - enforcement unique to set_project
- No other tool needs these specific path resolution rules

**Decision**: Keep path resolution as internal helpers to set_project

---

## 4. Implicit Contracts

### 4.1 Session Binding Assumption
**Location**: Lines 410-437
**Contract**: `stable_session_id` from ExecutionContext is the canonical session key
**Not Enforced**: No validation that stable_session_id is actually stable (could be None)
**Failure Mode**: Falls back to context_session_id (unstable UUID), breaks session persistence
**Testing Gap**: No test verifies stable_session_id is used when available

### 4.2 Silent Database Failures
**Locations**: Lines 305, 333, 345, 391
**Contract**: Database mirroring failures are non-fatal
**Not Enforced**: No structured error tracking, just print() statements
**Failure Mode**: Agent loses project context in DB but state.json is fine (split brain)
**Policy Decision**: Acceptable because state.json is source of truth
**Tag**: [BUCKET:error_handling]

### 4.3 Doc Inventory Completeness
**Location**: Lines 91-113
**Contract**: Only checks 4 standard docs (arch, phase, checklist, progress)
**Not Enforced**: Custom content detection is best-effort (line 125)
**Assumption**: `default_formatter._detect_custom_content()` catches everything else
**Testing Gap**: Unknown what "custom content" includes (research files mentioned in brief, but no spec)

### 4.4 Project Registry Touch
**Location**: Lines 304, 344
**Contract**: ProjectRegistry.touch_access() should update last_access_at
**Not Enforced**: Wrapped in try/except, failures silently ignored
**Failure Mode**: Project appears stale in registry but is actually active
**Impact**: list_projects may deprioritize recently-used projects

---

## 5. Token Analysis

**Status**: Preliminary - requires ≥10 samples for statistical analysis

**Initial Observations**:
- SITREP formatting is delegated to `default_formatter` (lines 472, 512)
- Token consumption happens in:
  1. Box drawing (headers, separators)
  2. Doc listing (4 files × ~40 tokens = 160 tokens)
  3. Inventory tables (existing projects)
  4. Activity summary (entry counts, timestamps)
  5. Reminder blocks (context-dependent)

**Sampling Plan**:
1. New project with no reminders (baseline)
2. New project with 3 reminders (reminder overhead)
3. Existing project, minimal inventory (baseline existing)
4. Existing project, full inventory (research files, bugs, jsonl)
5. Existing project with per-log counts (activity detail)
6-10. Variations of above with different custom content

**Categorization Framework** (from brief):
- **Structural**: Headers, boxes, table formatting
- **Metadata**: Paths, timestamps, version numbers
- **Duplication**: Same location block in multiple responses
- **Safety padding**: Explanatory text that could be moved to docs

**Target**: <200 tokens for compact mode (50% reduction from current 400-800 range)

**Next Steps**:
1. Generate 10 SITREP samples via test calls
2. Measure with tiktoken
3. Categorize each token bucket
4. Identify removable/optional sections

---

## 6. Error Handling Architecture

### 6.1 Silent Failures [BUCKET:error_handling]

**Database Mirroring** (Lines 305, 333, 345):
```python
except Exception as exc:  # pragma: no cover - defensive
    print(f"⚠️  ProjectRegistry ensure/touch_access failed in set_project: {exc}")
```
- **Policy**: DB failures don't block project creation
- **Rationale**: state.json is source of truth, SQLite is supplementary
- **Swallows**: All exceptions, logs to stdout only
- **State Mutation**: Project exists in state.json but not in DB (split brain)
- **Acceptable?**: YES - documented fallback behavior

**Agent Context Management** (Line 389-393):
```python
except Exception as e:
    print(f"⚠️  Agent context management failed: {e}")
    print("   💡 Falling back to legacy global state management")
    mirror_global = True
```
- **Policy**: Agent session binding failures fall back to global state
- **Escalation**: Sets flag to trigger legacy behavior
- **State Mutation**: Partial - continues execution with fallback
- **Acceptable?**: YES - graceful degradation

### 6.2 Escalation Patterns

**Parameter Normalization Failures** (Lines 178-185):
- Returns error_response immediately (line 221-224)
- No state mutation, clean failure
- Error message bubbled to caller

**Path Validation Failures** (Lines 241-242):
- Returns validation error dict immediately
- No state mutation attempted
- Caller receives structured error

**Document Creation Failures** (Line 248-249):
- Bubbles up error from _ensure_documents
- Prevents incomplete project state
- Clean transaction boundary

### 6.3 Heal and Continue Logic

**Defaults Normalization** (Lines 168-185):
- Attempts normalize_dict_param()
- Falls back to JSON parsing
- Falls back to empty dict {}
- **Never fails** - always returns valid defaults

**Tags Normalization** (Lines 207-215):
- Attempts normalize_list_param()
- Falls back to single-item list [tags]
- **Never fails** - always returns valid list

**Agent ID Auto-Detection** (Lines 160-165):
- Tries get_agent_identity()
- Falls back to "Scribe"
- **Never fails** - always has agent ID

**Policy Decision**: User-facing parameters are healed to prevent CLI/MCP mismatches. This is architectural, not a bug.

---

## 7. Known Issues

### BUG-001: Empty Log Treated as New Project

**File**: `tools/set_project.py`
**Line**: 461
**Severity**: Medium
**Category**: Logic

**Description**:
The new/existing project detection incorrectly treats empty progress logs as "new" projects, triggering the wrong SITREP formatter.

**Root Cause**:
```python
# Line 460-461
entry_count = await _count_log_entries(progress_log_path)
is_new = not progress_log_path.exists() or entry_count == 0
```
The logic checks `entry_count == 0` to determine if project is new. This fails for:
- Rotated logs (empty file exists)
- Manually cleared logs (file exists but no entries)

**Reproduction**:
1. Create project: `set_project(name="test")`
2. Add entry: `append_entry(message="test")`
3. Rotate log: `rotate_log()` (creates empty PROGRESS_LOG.md)
4. Call set_project again: `set_project(name="test")`

**Expected**: "📂 PROJECT ACTIVATED" (existing SITREP with inventory)
**Actual**: "✨ NEW PROJECT CREATED" (new SITREP with "Documents Created")

**Impact**:
- Misleading output confuses users/agents
- Inventory information hidden (doesn't show research files, bugs, etc.)
- Activity summary lost (entry counts, last_entry_at)

**Fix Required**:
Change line 461 to check file existence only:
```python
# BEFORE
is_new = not progress_log_path.exists() or entry_count == 0

# AFTER
is_new = not progress_log_path.exists()
```

**Rationale**:
- File existence is canonical signal for "project has been used"
- Entry count is irrelevant (empty log ≠ new project)
- Rotated logs should still show existing SITREP

**Testing**:
- Add test: create project → rotate → call set_project → assert existing SITREP
- Add test: create project → manual clear → call set_project → assert existing SITREP

---

## 8. Implementation Specs

### SPEC-SET-001: Fix BUG-001 Empty Log Detection

**File**: `tools/set_project.py`
**Lines**: 461
**Change Type**: Logic fix
**Risk**: Low (single boolean expression)

**Before**:
```python
# Line 460-461
entry_count = await _count_log_entries(progress_log_path)
is_new = not progress_log_path.exists() or entry_count == 0
```

**After**:
```python
# Line 460-461
entry_count = await _count_log_entries(progress_log_path)  # Still needed for inventory
is_new = not progress_log_path.exists()
```

**Justification**:
- File existence is the canonical "has this project been used" signal
- Entry count is still needed for inventory gathering (line 494: `inventory = await _gather_project_inventory(project_data)`)
- Rotated logs (empty file) should show existing SITREP, not new SITREP

**Test Coverage Required**:
```python
async def test_empty_log_shows_existing_sitrep():
    """Rotated/empty logs should show existing SITREP, not new."""
    # Create project
    await set_project(name="test_empty_log")

    # Add entry to make it "used"
    await append_entry(message="test")

    # Rotate log (creates empty file)
    await rotate_log()

    # Call set_project again
    result = await set_project(name="test_empty_log", format="readable")

    # Should show EXISTING sitrep, not NEW
    assert result["is_new"] == False
    assert "inventory" in result  # Existing SITREP includes inventory
    assert "📂 PROJECT ACTIVATED" in result["readable_content"]
```

**Verification**:
- Manual test: Follow reproduction steps above, verify SITREP type changes
- Unit test: Add test case to test_set_project.py
- Integration test: Verify inventory gathering still works for empty logs

---

## Cross-Cutting Concerns

See separate `cross_cutting_concerns.md` for [BUCKET:*] tags aggregation.

**Flagged for Unification**:
- [BUCKET:metadata] - DocInventoryGatherer (set_project, list_projects, get_project)
- [BUCKET:parameter_healing] - ParameterHealer (all monster tools)
- [BUCKET:formatting] - SITREP generation (set_project delegates to default_formatter)
- [BUCKET:error_handling] - Silent DB failure policy (appears in multiple tools)

---

## Next Steps

1. ✅ Wiki stub created
2. ✅ BUG-001 confirmed with line-level evidence
3. ✅ Sub-system breakdown complete
4. ⏳ Token sampling (need 10 samples)
5. ⏳ Cross-tool pattern validation (check list_projects, get_project for doc gathering)
6. ⏳ Create BUG-001 report in wiki/bugs/
7. ⏳ Create SPEC-SET-001.yaml
8. ⏳ Finalize cross_cutting_concerns.md with [BUCKET] aggregations

---

**Audit Progress**: 3/10 logs, 0/10 token samples, 1/1 bug confirmed, 2/4 extractable modules identified
