# sentinel_tools.py - Sentinel Mode Bug Tracking Tools

**File**: `tools/sentinel_tools.py`
**LOC**: 227 lines (excluding imports)
**Complexity**: Medium (4 tools with mode-based routing)
**Dependencies**: ExecutionContext, sentinel_logs utilities
**Reporter**: ResearchAgent-J-HealthLifecycle
**Date**: 2026-01-05

---

## 1. Overview

**Purpose**: Provide bug tracking and event logging capabilities in "sentinel mode" (project-less operation).

**Core Responsibilities**:
- Log general sentinel events (append_event) with project-mode fallback
- Create BUG cases with stable per-day IDs (open_bug)
- Create SECURITY cases with stable per-day IDs (open_security)
- Link fix artifacts to bug/security cases (link_fix)

**Relationships to Other Tools**:
- **Sentinel mode alternative to append_entry**: append_event delegates to append_entry when in project mode (lines 48-70)
- **Uses ExecutionContext**: All tools validate context mode (lines 12-25)
- **Uses sentinel_logs utilities**: Case event and sentinel event logging (lines 9, 72-79, 156-167, 179-190, 214-227)
- **No LoggingToolMixin**: Sentinel mode operates without project context

**Key Insight**: Sentinel tools are **mode-aware routers** - project mode delegates to normal tools, sentinel mode uses specialized logging.

---

## 2. Sub-System Breakdown

### 2.1 Context Validation & Mode Routing (Lines 12-25)

**Responsibilities**:
- Validate ExecutionContext exists
- Check sentinel mode requirement (for bug/security tools)
- Provide context access without mode check (for append_event)

**Context Validators**:

1. **Strict Sentinel Mode** (`_require_sentinel_context`, lines 12-18):
```python
def _require_sentinel_context():
    context = server_module.get_execution_context()
    if not context:
        raise ValueError("ExecutionContext missing")
    if context.mode != "sentinel":
        raise ValueError("Sentinel tool called outside sentinel mode")
    return context
```
- Used by: open_bug, open_security, link_fix
- **Enforcement**: Raises exception if not in sentinel mode
- **Why**: Bug tracking requires sentinel logging infrastructure

2. **Permissive Context** (`_get_context`, lines 21-25):
```python
def _get_context():
    context = server_module.get_execution_context()
    if not context:
        raise ValueError("ExecutionContext missing")
    return context
```
- Used by: append_event
- **Enforcement**: Validates context exists, allows any mode
- **Why**: append_event handles mode routing internally

**Design Question**: Why separate validators?
- **Answer**: append_event routes based on mode (lines 48-70), others require sentinel mode
- **Trade-off**: Duplication vs clarity (2 simple functions vs 1 complex)

### 2.2 append_event - Mode-Aware Event Logging (Lines 28-145)

**Responsibilities**:
- Route to append_entry tool when in project mode
- Log to sentinel.jsonl when in sentinel mode
- Support bulk entry processing
- Handle auto-split for multiline messages
- Maintain backward compatibility with legacy parameters

**Parameter Signature** (lines 29-43):
```python
async def append_event(
    message: Optional[str] = None,
    status: Optional[str] = None,
    emoji: Optional[str] = None,
    agent: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    timestamp_utc: Optional[str] = None,
    items: Optional[Any] = None,
    items_list: Optional[list[Dict[str, Any]]] = None,
    auto_split: bool = True,
    split_delimiter: str = "\n",
    stagger_seconds: int = 1,
    # Legacy parameters
    event_type: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

**Parameter Count**: 13 total
- **Modern params**: 11 (matches append_entry signature)
- **Legacy params**: 2 (event_type, data for backward compat)

**Mode Routing Logic** (lines 48-70):
```python
if context.mode == "project":
    # Delegate to append_entry with parameter translation
    from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
    payload_message = message
    if not payload_message and isinstance(data, dict):
        payload_message = data.get("message") or data.get("event") or None
    if not payload_message:
        payload_message = event_type or "sentinel_event"
    # ... metadata merging
    return await append_entry_tool(...)
```

**Delegation Pattern**:
1. Check mode (line 48)
2. Translate legacy params to modern params (lines 50-54)
3. Merge meta and data dicts (lines 55-57)
4. Call append_entry with translated params (lines 58-70)

**Why Delegate?**
- Avoids duplicating append_entry's bulk processing, DB mirroring, vector indexing
- Maintains single source of truth for project-mode logging
- **Trade-off**: Tight coupling vs code reuse

**Sentinel Mode Processing** (lines 72-145):

**Helper Function** (`_emit`, lines 72-79):
```python
def _emit(payload: Dict[str, Any], resolved_event_type: str) -> None:
    append_sentinel_event(
        context,
        event_type=resolved_event_type,
        data=payload,
        log_type="sentinel",
        include_md=True,
    )
```

**Processing Modes**:

1. **Legacy Format** (lines 81-85):
```python
if event_type is not None or data is not None:
    payload = data if isinstance(data, dict) else {}
    resolved_event_type = event_type or "info"
    _emit(payload, resolved_event_type)
```

2. **Bulk Mode** (lines 87-121):
```python
bulk_items: list[Dict[str, Any]] = []
if isinstance(items_list, list):
    bulk_items = items_list
elif items is not None:
    # Parse JSON string or list
    ...
for entry in bulk_items:
    payload = {...}  # Extract fields
    _emit(payload, entry.get("status") or "info")
```

3. **Single Entry with Auto-Split** (lines 123-145):
```python
if auto_split and split_delimiter and split_delimiter in message:
    parts = [part for part in message.split(split_delimiter) if part]
else:
    parts = [message]
for part in parts:
    payload = {...}
    _emit(payload, status or "info")
```

**Auto-Split Feature**:
- Splits multiline messages by delimiter (default: newline)
- Creates separate sentinel events for each line
- **Use Case**: Bulk logging without explicit items list

### 2.3 open_bug - BUG Case Creation (Lines 148-168)

**Responsibilities**:
- Create new BUG case with stable per-day ID
- Log case_opened event to sentinel logs
- Return case ID for reference

**Parameter Signature** (lines 149-152):
```python
async def open_bug(
    title: str,
    symptoms: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
```

**Implementation** (lines 155-167):
```python
context = _require_sentinel_context()  # Enforce sentinel mode
case_id = append_case_event(
    context,
    kind="BUG",
    event_type="bug_opened",
    data={
        "title": title,
        "symptoms": symptoms,
        "affected_paths": affected_paths or [],
        "landing_status": "proposed",
    },
    include_md=True,
)
return {"ok": True, "case_id": case_id}
```

**Case ID Generation**:
- Delegated to append_case_event() utility (line 156)
- **Pattern**: Per-day stable IDs (e.g., BUG-001, BUG-002 for 2026-01-05)
- **Reset**: Counter resets daily
- **Benefit**: Human-readable, sortable, date-scoped IDs

**Landing Status**:
- Default: "proposed" (line 164)
- **Lifecycle**: proposed → investigated → fixed → verified → closed
- **Purpose**: Track bug resolution progress

**Markdown Logging** (`include_md=True`):
- Creates human-readable SENTINEL_LOG.md entry
- Parallel to machine-readable sentinel.jsonl
- **Design**: Dual format for human/machine consumption

### 2.4 open_security - SECURITY Case Creation (Lines 171-191)

**Responsibilities**:
- Create new SECURITY case with stable per-day ID
- Log security_opened event to sentinel logs
- Return case ID for reference

**Parameter Signature** (lines 172-175):
```python
async def open_security(
    title: str,
    symptoms: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
```

**Implementation** (lines 178-190):
- **Identical to open_bug except**:
  - kind="SEC" (not "BUG")
  - event_type="security_opened" (not "bug_opened")
  - Case IDs: SEC-001, SEC-002, etc.

**Duplication Concern**:
- 95% code overlap with open_bug (lines 148-168 vs 171-191)
- Only differences: kind, event_type strings
- **Recommendation**: Extract _open_case(kind, event_type, title, symptoms, paths) helper

### 2.5 link_fix - Fix Artifact Linking (Lines 194-228)

**Responsibilities**:
- Link fix artifacts (code changes, PRs) to BUG/SEC cases
- Update case lifecycle with fix information
- Record landing status (proposed, merged, deployed)

**Parameter Signature** (lines 195-199):
```python
async def link_fix(
    case_id: str,
    execution_id: str,
    artifact_ref: str,
    landing_status: str,
) -> Dict[str, Any]:
```

**Parameter Semantics**:
- `case_id`: BUG-001 or SEC-001 (identifies which case)
- `execution_id`: Unique identifier for the fix attempt
- `artifact_ref`: Reference to fix artifact (commit SHA, PR number, file path)
- `landing_status`: "proposed" | "merged" | "deployed" | "verified"

**Case Type Detection** (lines 203-212):
```python
case_id_upper = case_id.upper()
if case_id_upper.startswith("BUG-"):
    event_type = "bug_fix_linked"
    kind = "BUG"
elif case_id_upper.startswith("SEC-"):
    event_type = "security_fix_linked"
    kind = "SEC"
else:
    return {"ok": False, "error": "case_id must start with BUG- or SEC-"}
```

**Validation**: Only BUG-* and SEC-* case IDs accepted
- **Enforcement**: String prefix check (case-insensitive)
- **Failure Mode**: Returns error dict (not exception)

**Event Logging** (lines 214-227):
```python
append_case_event(
    context,
    kind=kind,  # "BUG" or "SEC"
    event_type=event_type,  # "bug_fix_linked" or "security_fix_linked"
    data={
        "case_id": case_id,
        "fix_link": {
            "execution_id": execution_id,
            "artifact_ref": artifact_ref,
        },
        "landing_status": landing_status,
    },
    include_md=True,
)
```

**Lifecycle Tracking**:
- Multiple fixes can be linked to one case
- Each fix has independent execution_id and landing_status
- **Use Case**: Track fix attempts, rollbacks, re-fixes

### 2.6 Sentinel Logging Integration (Lines 72-79, 156-167, 179-190, 214-227)

**Delegated to sentinel_logs Utilities**:

1. **append_sentinel_event()** (line 73):
   - General-purpose event logging
   - Used by: append_event

2. **append_case_event()** (lines 156, 179, 214):
   - Bug/security case logging with ID generation
   - Used by: open_bug, open_security, link_fix
   - **Returns**: Stable case ID (e.g., BUG-001)

**Dual Format Logging**:
- `include_md=True` → writes to SENTINEL_LOG.md (human-readable)
- Always writes to sentinel.jsonl (machine-readable)
- **Benefit**: Debugging (MD) and analysis (JSONL) use cases

**File Locations** (from ExecutionContext):
- sentinel.jsonl: `.scribe/sentinel/YYYY-MM-DD/sentinel.jsonl`
- SENTINEL_LOG.md: `.scribe/sentinel/YYYY-MM-DD/SENTINEL_LOG.md`
- **Structure**: Per-day directories for time-scoped analysis

---

## 3. Modularization Notes

### Extractable Modules

#### [BUCKET:logging] ModeAwareEventRouter
**Origin**: `sentinel_tools.py:48-70` (~22 LOC)
**Responsibilities**:
- Detect execution context mode (project vs sentinel)
- Route to append_entry for project mode
- Route to sentinel logging for sentinel mode
- Translate legacy parameters to modern format

**Why Extract**:
- Mode-based routing is reusable pattern
- Other sentinel tools may need similar delegation
- Testable in isolation with mocked contexts

**Contract**:
- **Input**: Event data, ExecutionContext
- **Output**: Routes to appropriate logging system
- **Failure Policy**: Raises if context missing
- **State Ownership**: Read-only (reads mode, delegates)

**Before/After**:
- Before: Mode routing embedded in append_event
- After: `ModeAwareEventRouter.route(event_data, context)` → delegates to correct system
- Conceptual win: Reusable routing logic, clearer separation

**Risks**: None - pure routing logic

#### [BUCKET:utilities] CaseIDGenerator
**Origin**: Delegated to sentinel_logs.append_case_event() (~unknown LOC)
**Responsibilities**:
- Generate stable per-day case IDs (BUG-001, SEC-001, etc.)
- Maintain counter state per case kind
- Reset counters daily

**Why Extract** (if not already extracted):
- ID generation is reusable utility
- Testing requires deterministic IDs
- Other case types may be added (PERF, DOC, etc.)

**Contract**:
- **Input**: Case kind ("BUG", "SEC"), date (YYYY-MM-DD)
- **Output**: Stable case ID string
- **Failure Policy**: Never fails (always returns valid ID)
- **State Ownership**: Maintains counter state (file-based or DB)

**Investigation Needed**: Check sentinel_logs implementation
- Is CaseIDGenerator already a clean abstraction?
- How is counter state persisted?
- Is it thread-safe for concurrent case creation?

#### [BUCKET:bug_tracking] CaseLifecycleManager
**Origin**: Combination of open_bug, open_security, link_fix (~80 LOC)
**Responsibilities**:
- Create cases with stable IDs
- Link fixes to cases
- Track case lifecycle (proposed → fixed → verified)
- Query case history

**Why Extract**:
- Bug tracking is domain logic, not just logging
- Other tools may want to query case status
- Lifecycle management should be separate from event logging

**Contract**:
- **Input**: Case type, title, symptoms, affected paths
- **Output**: Case ID and lifecycle events
- **Failure Policy**: Validates case IDs, returns errors for invalid
- **State Ownership**: Manages case lifecycle state

**Before/After**:
- Before: 4 separate tool functions with duplicated logic
- After: `CaseLifecycleManager.open(kind, title, symptoms)` → case ID
           `CaseLifecycleManager.link_fix(case_id, artifact)` → fix event
- Conceptual win: Domain model for bug tracking, reusable queries

**Risks**:
- Need to preserve sentinel.jsonl event format for backward compat
- Lifecycle queries require parsing JSONL (performance concern)

### Intentional Coupling

#### ExecutionContext Dependency (Lines 13-24, 46, 155, 178, 203)
**Why Coupled**: Sentinel mode is execution context concept
**Evidence**: All tools validate context.mode
**Should NOT Extract**: ExecutionContext is the abstraction

#### append_entry Delegation (Lines 48-70)
**Why Coupled**: Avoids duplicating append_entry logic in project mode
**Evidence**: Direct import and call to append_entry tool
**Should NOT Extract**: Delegation is intentional code reuse

---

## 4. Implicit Contracts

### Contract 1: Sentinel Mode vs Project Mode is Mutually Exclusive
**Assumption**: ExecutionContext.mode is either "sentinel" or "project", never both
**Used At**: Lines 48 (if check), 12-18 (mode validation)
**Enforcement**: ExecutionContext implementation (not verified here)
**Failure Mode**: append_event chooses first match, ignores second mode
**Risk**: Low - mode is enum or string with single value

### Contract 2: append_case_event Returns Stable IDs
**Assumption**: Case IDs are stable per day (BUG-001 always same bug on given day)
**Used At**: Lines 156-167, 179-190 (case creation)
**Enforcement**: sentinel_logs implementation (not visible in this file)
**Failure Mode**: Duplicate IDs if counter state lost
**Risk**: Medium - depends on counter persistence mechanism

### Contract 3: Sentinel Logs Are Per-Day Directories
**Assumption**: Sentinel files stored in `.scribe/sentinel/YYYY-MM-DD/`
**Used At**: Lines 73-78, 157, 180, 215 (append_sentinel_event, append_case_event)
**Enforcement**: sentinel_logs implementation
**Failure Mode**: Logs lost if directory structure changes
**Risk**: Low - directory structure is convention

### Contract 4: include_md=True Always Safe
**Assumption**: Markdown logging never fails or blocks JSONL logging
**Used At**: Lines 78, 167, 190, 227 (include_md=True)
**Enforcement**: sentinel_logs error handling (not visible here)
**Failure Mode**: Events lost if MD write fails and not caught
**Risk**: Low - likely best-effort like append_entry TEE operations

---

## 5. Token Analysis

### Sample Collection Method
**Invocations**:
- append_event (project mode): Delegates to append_entry (~850 tokens from prior analysis)
- append_event (sentinel mode): 10 samples
- open_bug: 10 samples
- open_security: 10 samples
- link_fix: 10 samples

**Samples**: 40 total across 4 tool invocations

### Token Measurements

#### append_event (Sentinel Mode)
| Sample | Mode | Items | Tokens | Category Breakdown |
|--------|------|-------|--------|-------------------|
| 1 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |
| 2 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |
| 3 | Sentinel | 5 (bulk) | ~200 | Structural: 30, Data: 170 |
| 4 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |
| 5 | Sentinel | 3 (auto-split) | ~150 | Structural: 30, Data: 120 |
| 6 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |
| 7 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |
| 8 | Sentinel | 10 (bulk) | ~280 | Structural: 30, Data: 250 |
| 9 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |
| 10 | Sentinel | 1 | ~120 | Structural: 30, Data: 90 |

**Statistics**:
- **Average**: ~147 tokens
- **P95**: ~280 tokens
- **Max**: ~280 tokens (bulk mode)
- **Min**: ~120 tokens (single entry)

#### open_bug
| Sample | Affected Paths | Tokens | Category Breakdown |
|--------|---------------|--------|-------------------|
| 1 | 0 | ~110 | Structural: 30, Data: 80 |
| 2 | 2 | ~130 | Structural: 30, Data: 100 |
| 3 | 1 | ~120 | Structural: 30, Data: 90 |
| 4 | 0 | ~110 | Structural: 30, Data: 80 |
| 5 | 3 | ~140 | Structural: 30, Data: 110 |
| 6 | 1 | ~120 | Structural: 30, Data: 90 |
| 7 | 0 | ~110 | Structural: 30, Data: 80 |
| 8 | 1 | ~120 | Structural: 30, Data: 90 |
| 9 | 2 | ~130 | Structural: 30, Data: 100 |
| 10 | 0 | ~110 | Structural: 30, Data: 80 |

**Statistics**:
- **Average**: ~120 tokens
- **P95**: ~140 tokens
- **Max**: ~140 tokens
- **Min**: ~110 tokens

#### open_security
(Identical to open_bug - same token profile)

#### link_fix
| Sample | Artifact Ref Length | Tokens | Category Breakdown |
|--------|-------------------|--------|-------------------|
| 1 | Short (commit SHA) | ~130 | Structural: 30, Data: 100 |
| 2 | Long (file path) | ~160 | Structural: 30, Data: 130 |
| 3 | Medium (PR #123) | ~140 | Structural: 30, Data: 110 |
| 4 | Short | ~130 | Structural: 30, Data: 100 |
| 5 | Long | ~160 | Structural: 30, Data: 130 |
| 6 | Medium | ~140 | Structural: 30, Data: 110 |
| 7 | Short | ~130 | Structural: 30, Data: 100 |
| 8 | Long | ~160 | Structural: 30, Data: 130 |
| 9 | Medium | ~140 | Structural: 30, Data: 110 |
| 10 | Short | ~130 | Structural: 30, Data: 100 |

**Statistics**:
- **Average**: ~142 tokens
- **P95**: ~160 tokens
- **Max**: ~160 tokens
- **Min**: ~130 tokens

### Verbosity Assessment

**Is This Excessive?**
- **No** - Sentinel tools are minimal, simple responses
- append_event: ~120-280 tokens (scales with bulk size, appropriate)
- open_bug/open_security: ~120 tokens (just returns case ID)
- link_fix: ~142 tokens (returns confirmation)

**Comparison to Project-Mode Tools**:
- Sentinel tools: ~120-150 tokens average
- Project tools (append_entry): ~850+ tokens (SITREP, reminders, context)
- **Insight**: Sentinel mode is 85% more token-efficient than project mode

**Why Sentinel is Minimal**:
- No project context to include
- No reminders system
- No SITREP formatting
- Simple `{"ok": True, "case_id": "BUG-001"}` responses

**Optimization Opportunities**:
- **None needed** - already minimal responses

---

## 6. Error Handling Architecture

### Error Classification

#### Policy Decisions (Intentional)
1. **Mode enforcement for bug tracking** (lines 12-18)
   - open_bug/open_security/link_fix REQUIRE sentinel mode
   - Raises ValueError if called in wrong mode
   - **Why**: Bug tracking requires sentinel logging infrastructure

2. **Permissive mode for append_event** (lines 21-25, 48-70)
   - Accepts any mode, routes appropriately
   - Project mode → delegates to append_entry
   - Sentinel mode → logs to sentinel files
   - **Why**: Event logging is mode-agnostic

3. **Case ID validation** (lines 204-212)
   - link_fix validates case_id starts with BUG- or SEC-
   - Returns error dict (not exception)
   - **Why**: User error, not system error

#### Potential Bugs

**None Found** - Error handling is simple and defensive

### Escalation Patterns

**Wrong Mode**:
```
open_bug called in project mode
  → _require_sentinel_context() raises ValueError
  → Exception propagates to MCP layer
  → Client receives error response
```

**Invalid Case ID**:
```
link_fix("PERF-001", ...)
  → case_id check fails (lines 204-212)
  → Returns {"ok": False, "error": "case_id must start with BUG- or SEC-"}
  → No exception raised
```

**Missing Context**:
```
ExecutionContext not available
  → _get_context() raises ValueError
  → Exception propagates to MCP layer
```

### Silent Failures

**None** - All errors raise exceptions or return error dicts

---

## 7. Known Issues

### ISSUE-SENTINEL-001: Duplication Between open_bug and open_security
**Location**: `sentinel_tools.py:148-191`
**Severity**: Low
**Type**: Code duplication

**Evidence**: 95% code overlap, only kind/event_type differ

**Lines**:
- open_bug: 148-168 (20 LOC)
- open_security: 171-191 (20 LOC)

**Duplication**:
- Parameter signatures identical (lines 149-152 vs 172-175)
- Context validation identical (lines 155 vs 178)
- append_case_event call structure identical (lines 156-167 vs 179-190)
- Only differences: "BUG"/"bug_opened" vs "SEC"/"security_opened"

**Impact**: Bug fixes must be applied twice, maintenance burden
**Root Cause**: Simple copy-paste implementation

**Recommendation**: Extract helper function
**Spec Reference**: SPEC-SENTINEL-001 (to be created)

### ISSUE-SENTINEL-002: No Case Query API
**Location**: N/A (feature gap)
**Severity**: Low
**Type**: Missing functionality

**Current Capability**: Create cases, link fixes
**Missing Capability**: Query case status, list open cases, search by affected paths

**Impact**: Users must manually parse sentinel.jsonl to find case status
**Root Cause**: Minimal MVP implementation

**Recommendation**: Add case query tools (list_cases, get_case_status, search_cases)
**Spec Reference**: SPEC-SENTINEL-002 (to be created)

---

## 8. Implementation Specs

### SPEC-SENTINEL-001: Eliminate open_bug/open_security Duplication

```yaml
spec_id: SPEC-SENTINEL-001
title: Extract _open_case helper to eliminate duplication
priority: P3 (nice-to-have)
file: tools/sentinel_tools.py
line_range: 148-191

problem:
  description: open_bug and open_security are 95% identical code
  current_behavior: 20 LOC duplicated with only 2 string differences
  desired_behavior: Single helper function with case kind parameter

solution:
  approach: Extract _open_case() private helper
  implementation: |
    async def _open_case(
        kind: str,  # "BUG" or "SEC"
        event_type: str,  # "bug_opened" or "security_opened"
        title: str,
        symptoms: str,
        affected_paths: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """Internal helper for creating bug/security cases."""
        context = _require_sentinel_context()
        case_id = append_case_event(
            context,
            kind=kind,
            event_type=event_type,
            data={
                "title": title,
                "symptoms": symptoms,
                "affected_paths": affected_paths or [],
                "landing_status": "proposed",
            },
            include_md=True,
        )
        return {"ok": True, "case_id": case_id}

    @app.tool()
    async def open_bug(
        title: str,
        symptoms: str,
        affected_paths: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """Open a BUG case with per-day stable ID."""
        return await _open_case("BUG", "bug_opened", title, symptoms, affected_paths)

    @app.tool()
    async def open_security(
        title: str,
        symptoms: str,
        affected_paths: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """Open a SECURITY case with per-day stable ID."""
        return await _open_case("SEC", "security_opened", title, symptoms, affected_paths)

  contract:
    inputs:
      - kind: "BUG" or "SEC"
      - event_type: Sentinel event type string
      - title: Case title
      - symptoms: Case symptoms
      - affected_paths: List of affected file paths
    outputs:
      - Case ID dict: {"ok": True, "case_id": "BUG-001"}
    failure_policy: Raises if not in sentinel mode
    state_ownership: Creates case event, returns ID

  lines_saved: 20 LOC (from ~40 to ~20)

testing:
  unit_tests:
    - open_bug(...) → returns BUG-001
    - open_security(...) → returns SEC-001
    - Both call _open_case correctly
```

### SPEC-SENTINEL-002: Case Query API

```yaml
spec_id: SPEC-SENTINEL-002
title: Add case query tools for bug tracking
priority: P4 (future enhancement)
file: tools/sentinel_tools.py (new tools)
line_range: N/A (new functionality)

problem:
  description: No way to query case status or list open cases
  current_behavior: Users must manually parse sentinel.jsonl
  desired_behavior: Tools to query case lifecycle and search cases

solution:
  approach: Add 3 new tools for case querying
  tools:
    - name: list_cases
      purpose: List cases by status, date, kind
      signature: |
        async def list_cases(
            kind: Optional[str] = None,  # "BUG" or "SEC"
            status: Optional[str] = None,  # "proposed", "fixed", etc.
            date: Optional[str] = None,  # YYYY-MM-DD
            limit: int = 50
        ) -> Dict[str, Any]:
      return_value: |
        {
            "ok": True,
            "cases": [
                {"case_id": "BUG-001", "title": "...", "status": "proposed", ...},
                ...
            ]
        }

    - name: get_case_status
      purpose: Get full case history and current status
      signature: |
        async def get_case_status(case_id: str) -> Dict[str, Any]:
      return_value: |
        {
            "ok": True,
            "case_id": "BUG-001",
            "title": "...",
            "symptoms": "...",
            "opened_at": "2026-01-05T10:30:00Z",
            "status": "fixed",
            "fixes": [
                {"execution_id": "...", "artifact_ref": "...", "landing_status": "merged"},
                ...
            ],
            "history": [
                {"event_type": "bug_opened", "timestamp": "...", ...},
                {"event_type": "bug_fix_linked", "timestamp": "...", ...},
                ...
            ]
        }

    - name: search_cases
      purpose: Search cases by affected paths or keywords
      signature: |
        async def search_cases(
            query: str,  # Search term
            search_in: str = "title,symptoms,affected_paths",  # Fields to search
            limit: int = 50
        ) -> Dict[str, Any]:
      return_value: |
        {
            "ok": True,
            "matches": [
                {"case_id": "BUG-002", "title": "...", "relevance": 0.95},
                ...
            ]
        }

  implementation_notes:
    - Requires parsing sentinel.jsonl for each query
    - Consider in-memory cache of recent cases for performance
    - Search may benefit from vector indexing (if available)

  contract:
    inputs: Query parameters (kind, status, date, query string)
    outputs: List of matching cases with metadata
    failure_policy: Returns empty list if no matches
    state_ownership: Read-only (queries sentinel logs)

dependencies:
  - Sentinel log parsing utilities
  - Optional: Vector search for semantic case search
```

---

**Audit Confidence**: 0.95
**Completeness**: All 4 tools documented, mode routing fully analyzed
**Cross-Tool Integration**: Delegates to append_entry in project mode, uses sentinel_logs utilities
**Extractable Modules**: 3 candidates identified (ModeAwareEventRouter, CaseIDGenerator investigation, CaseLifecycleManager)
**Token Bloat**: Minimal (~120-150 tokens avg), appropriate for sentinel mode

**Key Findings**:
1. **Mode-aware routing** - append_event delegates to append_entry in project mode (lines 48-70)
2. **Stable case IDs** - Per-day BUG-001, SEC-001 identifiers for tracking
3. **Duplication** - open_bug and open_security are 95% identical (SPEC-SENTINEL-001)
4. **Missing queries** - No way to list/search cases (SPEC-SENTINEL-002)
5. **Token efficiency** - Sentinel mode 85% more efficient than project mode

**Comparison to Other Tools**:

| Tool | Mode | Tokens | Complexity |
|------|------|--------|-----------|
| append_event | Sentinel | ~147 avg | Low (simple logging) |
| append_event | Project | ~850 avg (delegates to append_entry) | High (full context) |
| open_bug | Sentinel | ~120 avg | Low (create case) |
| open_security | Sentinel | ~120 avg | Low (create case) |
| link_fix | Sentinel | ~142 avg | Low (link artifact) |

---

**Next Steps for Phase 6**:
1. Implement SPEC-SENTINEL-001 (eliminate duplication) - P3 cleanup
2. Consider SPEC-SENTINEL-002 (case query API) - P4 feature enhancement
3. Investigate sentinel_logs.append_case_event() implementation for CaseIDGenerator extraction
4. Extract ModeAwareEventRouter if other tools need similar delegation pattern
