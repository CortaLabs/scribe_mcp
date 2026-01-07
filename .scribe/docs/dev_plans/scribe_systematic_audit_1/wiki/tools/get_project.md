# get_project.py - Forensic Audit

**File**: `tools/get_project.py`
**LOC**: 352
**Size**: 12,757 bytes
**Complexity**: Medium
**Paired With**: list_projects.py (885 LOC combined)
**Audit Agent**: ResearchAgent-G-ListGetProjects
**Audit Date**: 2026-01-05

---

## 1. Overview

`get_project.py` is a single-project context retrieval tool that serves as the "deep dive" complement to list_projects. It provides detailed project status with recent log entries, document inventory, and activity summaries. **CRITICAL for BUG-001 fix**: Contains hash retrieval architecture that exposes ProjectRegistry baseline_hashes/current_hashes for pristine template detection.

**Purpose**: Return active project with full context (recent entries, doc status, activity metadata) for situational awareness during development sessions.

**Key Complexity Drivers**:
- **Hash Retrieval Architecture**: `_compute_doc_status()` exposes registry hash data (lines 28-40) - **CRITICAL for BUG-001 fix**
- **DUPLICATION-002**: Doc gathering logic repeated from set_project/list_projects (lines 130-179)
- **Recent Entry Parsing**: Complex log parsing with complete message preservation (lines 70-127)
- **Format Routing**: Structured vs readable with context hydration (lines 182, 303-345)
- **Multi-Source Resolution**: Project resolution from explicit param, session context, state fallback, or registry (lines 225-286)

**Relationships**:
- **Data Dependencies**: ProjectRegistry (hash data), LoggingContext, default_formatter
- **Paired Tool**: list_projects.py (shared doc gathering, similar registry integration)
- **BUG-001 Dependency**: Exposes hash comparison data needed for set_project "new vs existing" detection
- **Unification Candidate**: Could merge with list_projects under unified query contract (list vs get is just filter + presentation)

---

## 2. Sub-System Breakdown

### 2.1 Hash Retrieval Architecture [CRITICAL FOR BUG-001] (Lines 28-40)
**Responsibility**: Expose ProjectRegistry baseline_hashes and current_hashes for document drift detection and pristine template identification

**Function**: `_compute_doc_status(project_name: str) -> Dict[str, Any]`

**Return Structure**:
```python
{
    "flags": {
        "architecture_touched": True,
        "architecture_modified": False,  # baseline == current (pristine)
        "phase_plan_touched": True,
        "phase_plan_modified": True,     # baseline != current (modified)
        "docs_ready_for_work": True      # All core docs touched
    },
    "baseline_hashes": {
        "architecture": "abc123...",     # Hash when template created
        "phase_plan": "def456...",
        "checklist": "ghi789..."
    },
    "current_hashes": {
        "architecture": "abc123...",     # Same = pristine
        "phase_plan": "xyz999...",       # Different = modified
        "checklist": "ghi789..."
    },
    "last_update_at": "2026-01-05T03:15:00Z",
    "update_count": 7
}
```

**CRITICAL DATA FLOW FOR BUG-001 FIX**:
1. **Template Creation**: `generate_doc_templates()` SHOULD call `ProjectRegistry.record_doc_update(before_hash=None, after_hash=template_hash)` when creating docs
2. **Hash Storage**: `record_doc_update()` stores in `meta.docs.baseline_hashes[doc]` (first time) and `meta.docs.current_hashes[doc]` (every time)
3. **Hash Retrieval**: `_compute_doc_status()` calls `ProjectRegistry.get_project(name).meta.get("docs")` and extracts hashes
4. **Flag Derivation**: ProjectRegistry auto-computes `{doc}_modified` flags by comparing baseline != current (shared/project_registry.py:239-263)
5. **Pristine Detection**: Caller compares `baseline_hashes == current_hashes` for all core docs → if all match, project is pristine (new)

**Why This Matters**:
- set_project's current detection logic (`entry_count == 0`) fails after log rotation
- Correct logic: `all(baseline[d] == current[d] for d in core_docs)` survives rotation
- Hash comparison is semantic: "templates unmodified" = new, "templates edited" = existing
- BUG-001 gap: generate_doc_templates NEVER calls record_doc_update, so baseline_hashes are empty

**Contract**:
- **Input**: project_name (string)
- **Output**: Dict with flags, baseline_hashes, current_hashes, timestamps
- **Failure**: Returns `{}` if ProjectRegistry.get_project() fails (line 30)
- **State**: Read-only (queries registry, no mutations)

**Evidence**:
```python
# Lines 29-40
info = _PROJECT_REGISTRY.get_project(project_name)
if not info:
    return {}
docs_meta = (info.meta or {}).get("docs") or {}
flags = docs_meta.get("flags") or {}
return {
    "flags": flags,
    "baseline_hashes": docs_meta.get("baseline_hashes") or {},
    "current_hashes": docs_meta.get("current_hashes") or {},
    "last_update_at": docs_meta.get("last_update_at"),
    "update_count": docs_meta.get("update_count"),
}
```

### 2.2 Entry Counting Helper (Lines 43-52)
**Responsibility**: Count log entries using parse_log_line() utility

**Function**: `_count_log_entries(log_path) -> int`

**DUPLICATION-001 VARIANT**:
- Uses `parse_log_line()` utility (contrast with set_project.py regex pattern)
- Same purpose as set_project.py:36-58 but different implementation
- Returns 0 on any exception (silent failure)

**Contract**:
- **Input**: Path to log file
- **Output**: Integer entry count
- **Failure**: Returns 0 if file unreadable or parsing fails
- **State**: Read-only file access

### 2.3 Per-Log Entry Counts (Lines 55-67)
**Responsibility**: Count entries in all log types (progress, doc_updates, bugs, security) for comprehensive activity summary

**Function**: `_compute_log_counts(project: Dict[str, Any]) -> Dict[str, Any]`

**Return Structure**:
```python
{
    "progress": 145,
    "doc_updates": 23,
    "bugs": 5,
    "security": 0,
    "custom_log_type": 7  # Any log type from log_config.json
}
```

**Features**:
- Iterates all log types from `log_config_module.load_log_config()`
- Uses `resolve_log_definition()` to get path for each log type
- Skips non-existent logs gracefully (sets count to 0)
- Swallows exceptions per log type (lines 65-66) - policy: partial counts acceptable

**Contract**:
- **Input**: Project dict with paths
- **Output**: Dict mapping log_type → entry count
- **Failure**: Silent skip for individual logs (returns partial dict)
- **State**: Read-only

**Use Case**: Enables agents to see activity breakdown (e.g., "5 bug reports, 23 doc updates")

### 2.4 Recent Entry Parsing [DUPLICATION-002] (Lines 70-127)
**Responsibility**: Parse last N entries from progress log with COMPLETE message preservation (no truncation)

**Function**: `_read_recent_progress_entries(progress_log_path: str, limit: int = 5) -> List[Dict[str, Any]]`

**Return Structure**:
```python
[
    {
        "emoji": "ℹ️",
        "timestamp": "2026-01-03 09:53:42 UTC",
        "agent": "Orchestrator",
        "message": "Full message text with no truncation"
    },
    ...
]
```

**Entry Parsing Logic** (lines 100-119):
```python
# Format: [emoji] [timestamp] [Agent: name] [Project: name] message
parts = line.split('] ', 4)  # Split on '] ' up to 5 parts
emoji = parts[0].strip('[')
timestamp = parts[1].strip('[')
agent_part = parts[2].strip('[')  # "Agent: name"
# Skip project part (parts[3])
message = parts[4]  # COMPLETE MESSAGE - NO TRUNCATION!
```

**CRITICAL REQUIREMENT**: Messages must be complete for context hydration (line 80 comment, line 118 comment)

**Error Handling**:
- Invalid line format → skip (line 103, 120-121)
- File read errors → return empty list (line 126)

**Contract**:
- **Input**: progress_log_path, limit (default 5)
- **Output**: List of entry dicts (last N entries)
- **Failure**: Returns `[]` if file missing or unreadable
- **State**: Read-only

### 2.5 Doc Inventory Gathering [DUPLICATION-002] (Lines 130-179)
**Responsibility**: Scan dev_plan directory for architecture/phase/checklist/progress docs

**Function**: `_gather_doc_info(project: Dict[str, Any]) -> Dict[str, Any]`

**DUPLICATION EVIDENCE**:
- Lines 146-165: Identical pattern to `list_projects.py:84-106` and `set_project.py:91-113`
- Lines 168-176: Same progress entry counting as list_projects
- NO custom content detection (unlike list_projects variant)
- NO hash computation (unlike what SHOULD exist for proper drift detection)

**Return Structure**:
```python
{
    "architecture": {"exists": True, "lines": 768},
    "phase_plan": {"exists": True, "lines": 922},
    "checklist": {"exists": True, "lines": 322},
    "progress": {"exists": True, "entries": 45}
}
```

**Contract**:
- **Input**: Project dict with progress_log path
- **Output**: Doc info dict with existence/counts
- **Failure**: Returns `{}` if progress_log missing (line 139)
- **State**: Read-only

**Extractable**: [BUCKET:metadata] `DocInventoryGatherer` (same as list_projects.md Section 3)

### 2.6 Project Resolution Logic (Lines 225-286)
**Responsibility**: Resolve target project from explicit parameter, session context, state fallback, or registry last-known

**Resolution Cascade**:
1. **Explicit project parameter** (lines 225-244): Load from state/config
2. **Session context** (lines 246-254): Use ExecutionContext project if mode is "project" or "sentinel"
3. **State fallback** (lines 255-259): Load active project from state manager
4. **Registry last-known** (lines 261-286): Get most recently accessed project from recent_projects candidates

**Error Responses**:
- Project not found (line 236-242): Structured error with suggestion
- No session project (line 248-254): Error if in session mode but no project set
- No project anywhere (line 279-286): Error with last_known_project hint if available

**Last-Known Project Metadata** (lines 261-277):
```python
extra = {
    "last_known_project": "scribe_systematic_audit_1",
    "last_known_project_minutes_ago": 45,
    "last_known_project_last_access_at": "2026-01-05T02:30:00Z"
}
```

**Contract**:
- **Input**: Optional project name, execution context, state manager
- **Output**: Resolved project dict OR error response
- **Failure**: Structured error with suggestions (never crashes)
- **State**: Read-only (queries state/registry)

### 2.7 Doc Status & Log Counts Enrichment (Lines 293-300)
**Responsibility**: Add doc_status and log_entry_counts to response metadata for quick situational awareness

**Enrichment Logic**:
```python
response["meta"]["docs_status"] = await _compute_doc_status(current_name)
response["meta"]["log_entry_counts"] = await _compute_log_counts(response)
```

**Purpose**: Provide agents with:
- Document drift flags (`architecture_modified`, `docs_ready_for_work`)
- Hash data for pristine detection (`baseline_hashes`, `current_hashes`)
- Per-log activity breakdown (progress: 145, bugs: 5, doc_updates: 23)

**Error Handling**: Lines 299 - swallows all exceptions (best-effort enrichment)

**Contract**:
- **Input**: project_name, project dict
- **Output**: Enriched response with meta.docs_status and meta.log_entry_counts
- **Failure**: Silent (enrichment skipped if functions fail)
- **State**: Read-only

### 2.8 Readable Format with Context Hydration (Lines 303-345)
**Responsibility**: Format human-readable output with recent entries, doc info, and activity summary

**Context Hydration Steps**:
1. Read last 5 progress log entries (COMPLETE messages) - line 307-310
2. Gather doc inventory (existence/line counts) - line 313
3. Get activity summary from registry (total_entries, last_entry_at, status) - line 316-322
4. Format via `default_formatter.format_project_context()` - line 325-330

**Output Structure**:
```
╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT CONTEXT: scribe_systematic_audit_1           ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/scribe_systematic_audit_1/

📊 Documentation Status:
  ✓ ARCHITECTURE_GUIDE.md (768 lines)
  ✓ PHASE_PLAN.md (922 lines)
  ✓ CHECKLIST.md (322 lines)
  ✓ PROGRESS_LOG.md (45 entries)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 45
  Last Entry: 2 hours ago

📝 Recent Entries (last 5):
  [ℹ️] [2026-01-05 03:15:00] [Orchestrator] Research phase complete
  [✅] [2026-01-05 02:30:00] [ResearchAgent] Wiki documentation created
  [ℹ️] [2026-01-05 01:45:00] [Orchestrator] Subsystem analysis in progress
  ...
```

**Token Estimate**: 400-600 tokens (detailed context for single project)

**Format Finalization** (lines 341-345):
- Calls `default_formatter.finalize_tool_response(format="readable", tool_name="get_project")`
- Adds reminders, ANSI colors, structural boxes

**Contract**:
- **Input**: Project, recent entries, docs info, activity summary
- **Output**: Formatted string (400-600 tokens)
- **Failure**: Never fails (formatter handles missing data gracefully)
- **State**: Read-only

---

## 3. Modularization Notes

### [BUCKET:metadata] DocInventoryGatherer (SHARED WITH list_projects)
**Origin**: `get_project.py:130-179` + `list_projects.py:50-128` + `set_project.py:61-127`
**Status**: See list_projects.md Section 3 for full analysis

**get_project Variant Notes**:
- NO custom content detection (simpler than list_projects)
- NO hash computation (despite _compute_doc_status existing separately!)
- SHOULD integrate hash computation into gatherer for unified "doc status" concept

**Integration Opportunity**:
```python
# Current: doc gathering and hash retrieval are separate
docs_info = await _gather_doc_info(project)  # Lines 130-179
doc_status = await _compute_doc_status(project_name)  # Lines 28-40

# After extraction: unified doc inventory with hashes
inventory = DocInventoryGatherer(compute_hashes=True).gather(dev_plan_dir)
# Returns: architecture/phase/checklist/progress with lines AND hashes
```

---

### [BUCKET:formatting] Context Formatter (KEEP COUPLED)
**Origin**: `get_project.py:303-345` (readable format with context hydration)

**Why NOT Extract**:
- Context hydration is get_project-specific (recent entries + doc info + activity)
- list_projects has different context needs (pagination + filter hints)
- No other tool needs "single project deep dive" formatting
- Extraction would create coupling without reusability

**Decision**: **KEEP COUPLED** - Tool-specific presentation logic

---

### [BUCKET:parsing] Recent Entry Parser (POTENTIAL EXTRACTION)
**Origin**: `get_project.py:70-127` (_read_recent_progress_entries)

**Responsibilities**:
- Parse log entry format: `[emoji] [timestamp] [Agent: name] [Project: name] message`
- Extract components without truncation
- Return last N entries

**Reusability**:
- read_recent.py might benefit from same parser
- query_entries.py could use for entry formatting
- append_entry.py writes entries, so parser should match that format

**Before/After**:
- **Before**: Each tool parses log format independently (potential inconsistencies)
- **After**: Single `LogEntryParser.parse_line()` used by all query tools
- **Conceptual Win**: Log format is centrally defined, tools don't know parsing details

**Decision**: **DEFER** - Needs investigation of read_recent/query_entries parsing logic first

---

## 4. Implicit Contracts

### 4.1 Hash Retrieval for BUG-001 Fix
**Location**: Lines 28-40
**Contract**: ProjectRegistry.meta.docs contains baseline_hashes and current_hashes populated by manage_docs/generate_doc_templates
**Not Enforced**: No validation that hashes exist (returns empty dicts if missing)
**Assumption**: generate_doc_templates calls record_doc_update() to populate baseline hashes
**VIOLATION**: generate_doc_templates DOES NOT call record_doc_update (BUG-001 root cause)
**Impact**: Hash-based pristine detection fails because baseline_hashes are always empty

### 4.2 Complete Message Preservation
**Location**: Lines 80, 118 (comments emphasize "COMPLETE, no truncation!")
**Contract**: Recent entry messages must be fully preserved for context hydration
**Not Enforced**: No validation that split('] ', 4) succeeded
**Assumption**: Log format is always `[emoji] [timestamp] [Agent: name] [Project: name] message`
**Failure Mode**: Malformed log lines skipped silently (line 120-121)
**Testing Gap**: No test for malformed log entries

### 4.3 Best-Effort Enrichment
**Location**: Line 299 (try/except around doc_status/log_counts)
**Contract**: Enrichment failures don't block get_project response
**Not Enforced**: No logging of enrichment failures
**Assumption**: Core project data (name, root, progress_log) is sufficient even without enrichment
**Failure Mode**: Agents miss doc_status/log_counts but tool succeeds
**Policy Decision**: Acceptable (enrichment is nice-to-have, not required)

### 4.4 Resolution Cascade Priority
**Location**: Lines 225-286 (project resolution logic)
**Contract**: Priority order: explicit param > session context > state fallback > registry last-known
**Not Enforced**: No validation that cascade is correct
**Assumption**: ExecutionContext.mode distinguishes session-bound vs global state usage
**Failure Mode**: Session-bound agents may get wrong project if cascade mis-prioritizes
**Testing Gap**: No test covering all cascade paths

---

## 5. Token Analysis

### Readable Format Token Profile

**Sample Output** (single project context):
```
╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT CONTEXT: scribe_systematic_audit_1           ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/scribe_systematic_audit_1/

📊 Documentation Status:
  ✓ ARCHITECTURE_GUIDE.md (768 lines)
  ✓ PHASE_PLAN.md (922 lines)
  ✓ CHECKLIST.md (322 lines)
  ✓ PROGRESS_LOG.md (45 entries)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 45
  Last Entry: 2 hours ago

📝 Recent Entries (last 5):
  [ℹ️] [2026-01-05 03:15:00] [Orchestrator] Research phase complete - moving to architecture planning
  [✅] [2026-01-05 02:30:00] [ResearchAgent] Wiki documentation created for list_projects and get_project
  [ℹ️] [2026-01-05 01:45:00] [Orchestrator] Subsystem analysis in progress for Wave 2 tools
  [🐞] [2026-01-05 00:20:00] [BugHunter] Discovered TOKEN-001 in list_projects formatting
  [ℹ️] [2026-01-04 23:15:00] [ArchitectAgent] Phase plan updated with Wave 2 assignments
```

**Token Estimate**: 450-650 tokens

**Breakdown**:

| Category | Token Estimate | Evidence | Optimizable? |
|----------|----------------|----------|--------------|
| **Structural** | 180-200 | Box drawing (╔═╗), section headers (📂, 📊, 📈, 📝), bullet markers | Partially (-80 in compact) |
| **Metadata** | 150-200 | Paths (2 lines × 50 chars), doc info (4 lines × 40 chars), activity (3 lines × 30 chars) | No (essential data) |
| **Recent Entries** | 100-200 | 5 entries × 20-40 chars/entry (messages vary) | Partially (limit to 3 entries?) |
| **Duplication** | 0 | No repeated content | N/A |
| **Safety Padding** | 20-50 | Section headers with emoji, status labels | Partially (-20 with text-only headers) |

**TOTAL**: 450-650 tokens (acceptable for single project deep-dive)

**Optimization Opportunities**:
1. **Compact mode**: Remove box drawing (-80 tokens)
2. **Reduce recent entries**: Show 3 instead of 5 (-40-80 tokens)
3. **Text-only headers**: Remove emoji from section headers (-20 tokens)
4. **AFTER**: 310-470 tokens (31-28% reduction)

**Recommendation**: Keep current verbosity - get_project is MEANT for detailed context (unlike list_projects table which shows 10+ projects)

---

### Structured Format Token Profile

**Sample Output**:
```json
{
  "ok": true,
  "project": {
    "name": "scribe_systematic_audit_1",
    "root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
    "progress_log": ".scribe/docs/dev_plans/scribe_systematic_audit_1/PROGRESS_LOG.md",
    "docs": {...},
    "defaults": {...},
    "meta": {
      "current_project": "scribe_systematic_audit_1",
      "docs_status": {
        "flags": {...},
        "baseline_hashes": {...},
        "current_hashes": {...}
      },
      "log_entry_counts": {
        "progress": 45,
        "doc_updates": 8,
        "bugs": 2
      }
    }
  },
  "recent_projects": ["scribe_systematic_audit_1", "scribe_tool_output_refinement"]
}
```

**Token Estimate**: 250-400 tokens (depends on meta blob size)

**Breakdown**:
- Core fields: 100-150 tokens
- Meta.docs_status: 50-100 tokens (hash dicts can be large)
- Meta.log_entry_counts: 20-30 tokens
- Recent projects: 30-50 tokens

**No optimization needed** - Structured format is already compact

---

## 6. Error Handling Architecture

### 6.1 Silent Failures (Policy Decisions)

**Doc Status Retrieval** (Line 30):
```python
info = _PROJECT_REGISTRY.get_project(project_name)
if not info:
    return {}  # Empty dict, no error
```
- **Policy**: Missing registry data → empty doc_status
- **Rationale**: Project may not be in registry yet (new projects)
- **State Mutation**: None
- **Acceptable**: YES - caller interprets empty dict as "no doc metadata"

**Entry Counting** (Line 47):
```python
try:
    lines = await read_all_lines(log_path)
except Exception:
    return 0  # Default to 0 entries
```
- **Policy**: File read errors → 0 entries
- **Rationale**: Log may be corrupted or permission-denied
- **State Mutation**: None
- **Acceptable**: QUESTIONABLE - silent 0 may mislead (should log warning)

**Log Counts** (Lines 65-66):
```python
except Exception:
    continue  # Skip this log type
```
- **Policy**: Per-log failures don't block overall counts
- **Rationale**: Partial activity data better than no data
- **State Mutation**: None
- **Acceptable**: YES - best-effort enrichment is intentional

**Enrichment** (Line 299):
```python
try:
    response["meta"]["docs_status"] = await _compute_doc_status(current_name)
    response["meta"]["log_entry_counts"] = await _compute_log_counts(response)
except Exception:
    pass  # Enrichment is optional
```
- **Policy**: Enrichment failures silently ignored
- **Rationale**: Core project data sufficient without enrichment
- **State Mutation**: None
- **Acceptable**: YES - documented best-effort behavior

### 6.2 Escalation Patterns

**Project Not Found** (Lines 236-242):
```python
return _GET_PROJECT_HELPER.apply_context_payload(
    _GET_PROJECT_HELPER.error_response(
        f"Project '{project}' not found.",
        suggestion="Ensure the project is registered via set_project or exists in config/projects/",
    ),
    context,
)
```
- Structured error with actionable suggestion
- No state mutation
- Clean failure

**No Session Project** (Lines 248-254):
```python
return _GET_PROJECT_HELPER.apply_context_payload(
    _GET_PROJECT_HELPER.error_response(
        "No session-scoped project configured.",
        suggestion="Invoke set_project before using this tool",
    ),
    context,
)
```
- Context-aware error (knows it's in session mode)
- Suggests correct fix (call set_project)
- Clean failure

**No Project Anywhere** (Lines 279-286):
- Checks registry for last_known_project
- Includes helpful metadata (minutes_ago, last_access_at)
- Provides breadcrumbs for user ("You last used project X 45 minutes ago")

### 6.3 Data Integrity Assumptions

**Log Entry Parsing** (Lines 100-119):
- Assumes log format: `[emoji] [timestamp] [Agent: name] [Project: name] message`
- No validation that split('] ', 4) produces 5 parts
- Malformed lines skipped silently
- **Risk**: Format changes break parsing with silent failures

**Project Resolution Cascade** (Lines 225-286):
- Assumes ExecutionContext.mode is reliable
- No validation that resolved project is consistent with session
- **Risk**: Cascade mis-prioritization could return wrong project

**Hash Data Availability** (Lines 28-40):
- Assumes meta.docs.baseline_hashes exists if doc was templated
- **VIOLATION**: generate_doc_templates doesn't populate baseline_hashes
- **Risk**: BUG-001 fix depends on this data being present

---

## 7. Known Issues

### BUG-001 Hash Data Missing (CRITICAL FOR FIX)
**Severity**: High (blocks correct fix for BUG-001 in set_project)
**Status**: Integration gap confirmed
**Impact**: Hash-based pristine detection fails because baseline_hashes never populated

**Root Cause**: `generate_doc_templates.py` does NOT call `ProjectRegistry.record_doc_update()` when creating templates

**Expected Behavior**:
```python
# generate_doc_templates.py should call after template write:
content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()
_PROJECT_REGISTRY.record_doc_update(
    project_name,
    doc="architecture",  # or phase_plan, checklist, etc.
    action="template_created",
    before_hash=None,
    after_hash=content_hash
)
```

**Actual Behavior**: Template created but NO call to record_doc_update → baseline_hashes empty → hash comparison fails

**Impact on BUG-001 Fix**:
- set_project CANNOT use hash comparison for "new vs existing" detection
- Correct logic: `all(baseline[d] == current[d] for d in core_docs)` requires baseline_hashes to exist
- Without baseline_hashes, comparison is always False (always treats as modified/existing)

**Reproduction**:
```python
project = await get_project(name="newly_created_project")
doc_status = project["meta"]["docs_status"]
assert doc_status["baseline_hashes"] == {}  # EMPTY - should have template hashes!
```

**Fix Strategy**: See wiki/bugs/BUG-001-set-project-empty-log.md for complete analysis

---

### DUPLICATION-002: Doc Gathering Logic Repeated
**Severity**: Medium
**Status**: Confirmed (shared with list_projects/set_project)
**Impact**: 90-100 LOC duplicated across 3 tools

**Evidence**: Lines 130-179 duplicate list_projects.py:50-128 and set_project.py:61-127

**Fix Strategy**: Extract [BUCKET:metadata] DocInventoryGatherer (see list_projects.md Section 3)

---

## 8. Implementation Specs

### SPEC-GET-001: Hash Retrieval Integration Test

**File**: New test `tests/test_hash_retrieval_integration.py`
**Priority**: P0 (validates BUG-001 fix infrastructure)

**Test Cases**:
```python
async def test_hash_retrieval_after_template_creation():
    """Verify that get_project exposes template hashes after set_project creates docs."""
    # Step 1: Create project (generates templates)
    await set_project(name="hash_test_project")

    # Step 2: Get project and check doc_status
    result = await get_project(name="hash_test_project")
    doc_status = result["meta"]["docs_status"]

    # CURRENTLY FAILS - baseline_hashes should be populated but aren't
    assert doc_status["baseline_hashes"]["architecture"] is not None
    assert doc_status["baseline_hashes"]["phase_plan"] is not None
    assert doc_status["baseline_hashes"]["checklist"] is not None

    # Verify flags are correct for pristine templates
    assert doc_status["flags"]["architecture_touched"] is True
    assert doc_status["flags"]["architecture_modified"] is False  # baseline == current
    assert doc_status["flags"]["docs_ready_for_work"] is True

async def test_hash_changes_after_doc_modification():
    """Verify that doc modification updates current_hashes but not baseline_hashes."""
    # Step 1: Create project
    await set_project(name="hash_modification_test")

    # Step 2: Modify a document
    await manage_docs(
        action="replace_section",
        doc="architecture",
        section="problem_statement",
        content="Modified content"
    )

    # Step 3: Check that current_hash changed but baseline_hash stayed same
    result = await get_project(name="hash_modification_test")
    doc_status = result["meta"]["docs_status"]

    baseline_arch = doc_status["baseline_hashes"]["architecture"]
    current_arch = doc_status["current_hashes"]["architecture"]

    assert baseline_arch is not None
    assert current_arch is not None
    assert baseline_arch != current_arch  # Doc was modified
    assert doc_status["flags"]["architecture_modified"] is True
```

---

### SPEC-GET-002: Recent Entry Parser Extraction

**Target**: New file `utils/log_parser.py`
**Priority**: P2 (code reuse opportunity)

**Interface**:
```python
@dataclass
class LogEntry:
    emoji: str
    timestamp: str
    agent: str
    project: str
    message: str
    raw_line: str

class LogEntryParser:
    @staticmethod
    def parse_line(line: str) -> Optional[LogEntry]:
        """Parse a single log entry line.

        Expected format:
            [emoji] [timestamp] [Agent: name] [Project: name] message

        Returns:
            LogEntry if parsing succeeds, None if line is malformed
        """
        parts = line.split('] ', 4)
        if len(parts) < 5:
            return None

        try:
            return LogEntry(
                emoji=parts[0].strip('['),
                timestamp=parts[1].strip('['),
                agent=parts[2].strip('[').replace('Agent: ', ''),
                project=parts[3].strip('[').replace('Project: ', ''),
                message=parts[4],
                raw_line=line
            )
        except IndexError:
            return None

    @staticmethod
    def parse_file(log_path: Path, limit: Optional[int] = None) -> List[LogEntry]:
        """Parse entire log file and return entries.

        Args:
            log_path: Path to log file
            limit: If set, return last N entries only

        Returns:
            List of LogEntry objects (newest last)
        """
```

**Migration Plan**:
1. Implement LogEntryParser in utils/log_parser.py
2. Update get_project.py lines 70-127 to use parser
3. Update read_recent.py to use parser (if applicable)
4. Update query_entries.py to use parser (if applicable)
5. Remove duplicated parsing logic after migration verified

---

### SPEC-GET-003: Context Hydration Token Optimization

**File**: `utils/response.py`
**Target Method**: `DefaultFormatter.format_project_context()` (referenced at line 325)
**Priority**: P3 (optimization, not required)

**Changes**:
1. Add `compact_context` parameter (default False)
2. When True:
   - Remove box drawing
   - Reduce recent entries from 5 to 3
   - Use text-only section headers (no emoji)
3. Expected token reduction: 31-28% (450-650 → 310-470 tokens)

**Note**: Low priority because get_project is meant for detailed context (not high-frequency like list_projects table)

---

## Notes for Phase 6

**Critical Insights**:
1. **BUG-001 Hash Retrieval Complete**: Full data flow documented (generate_doc_templates → record_doc_update → registry → get_project → caller)
2. **Integration Gap Confirmed**: generate_doc_templates missing record_doc_update() call is root cause
3. **DocInventoryGatherer Extraction**: Should integrate hash computation for unified "doc status" concept
4. **Recent Entry Parser**: Reusable across read_recent/query_entries if they need entry formatting
5. **Context Hydration**: Tool-specific, don't extract (similar to list_projects' three-way routing)

**Recommended Extraction Order**:
1. Fix BUG-001 integration gap (generate_doc_templates calls record_doc_update) - **UNBLOCKS EVERYTHING**
2. DocInventoryGatherer extraction (SPEC-LIST-002 from list_projects.md) - **REQUIRES hash integration**
3. LogEntryParser extraction (SPEC-GET-002) - **NICE-TO-HAVE code reuse**

**Defer Decisions**:
- Context hydration optimization (get_project verbosity is acceptable for single-project detail view)
- Resolution cascade refactoring (needs full session identity audit first)

---

## Hash Retrieval Architecture Summary (BUG-001 Fix Reference)

**Complete Data Flow**:
1. **Template Creation** (generate_doc_templates.py:220-224):
   - Renders template with Jinja2
   - Writes to file
   - **SHOULD call** `ProjectRegistry.record_doc_update(before_hash=None, after_hash=sha256(template))`
   - **CURRENTLY MISSING** this call → baseline_hashes never populated

2. **Hash Storage** (shared/project_registry.py:187-282):
   - `record_doc_update()` receives doc name, action, before_hash, after_hash
   - If doc NOT in baseline_hashes map AND before_hash provided: `baseline_hashes[doc] = before_hash` (line 230-231)
   - Always: `current_hashes[doc] = after_hash` (line 232-233)
   - Computes flags: `{doc}_modified = (baseline != current)` (lines 245-252)
   - Stores in `meta.docs` JSON blob (line 265)

3. **Hash Retrieval** (get_project.py:28-40):
   - Calls `ProjectRegistry.get_project(project_name)` (line 29)
   - Extracts `info.meta.get("docs")` (line 32)
   - Returns baseline_hashes, current_hashes, flags (lines 34-39)

4. **Pristine Detection** (CORRECT LOGIC for set_project.py):
   ```python
   # Instead of: is_new = entry_count == 0 (BROKEN)
   # Use:
   doc_status = await _compute_doc_status(project_name)
   baseline = doc_status.get("baseline_hashes", {})
   current = doc_status.get("current_hashes", {})
   core_docs = {"architecture", "phase_plan", "checklist"}
   is_new = all(baseline.get(d) == current.get(d) for d in core_docs if d in baseline)
   # Pristine = all core docs have baseline == current (templates unmodified)
   ```

**Why This Works**:
- Survives log rotation (hash comparison unaffected by entry_count)
- Survives manual clearing (hash comparison unaffected)
- Semantic correctness: "templates unmodified" = new, "templates edited" = existing
- Uses existing infrastructure (no new code needed in set_project)

**Why Current Fix Fails**:
- `is_new = not progress_log_path.exists()` breaks because set_project creates PROGRESS_LOG.md before check
- Result: file.exists() is ALWAYS True after first call → is_new is ALWAYS False

**Correct Fix Location**: `generate_doc_templates.py` lines 220-224 (add record_doc_update call)
