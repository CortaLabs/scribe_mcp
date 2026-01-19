# Base Infrastructure: Logging Utilities

**File**: `shared/logging_utils.py`
**LOC**: 574
**Complexity**: High (monolithic context resolver + utilities)
**Relationships**: Core dependency for ALL logging tools via LoggingToolMixin

---

## 1. Overview

Logging utilities consolidate project resolution, metadata normalization, and log composition logic previously duplicated across multiple tools. This is the **nervous system** of Scribe's logging infrastructure.

**Purpose**: Provide unified primitives for:
- Project context resolution (session-scoped, agent-scoped, explicit, sentinel mode)
- Metadata payload normalization (dict/string/JSON/legacy key=value)
- Log line composition (emoji + timestamp + agent + project + message + meta)
- Log configuration integration (multi-log routing)

**Critical Observation**: `resolve_logging_context()` is a **266-line monolith** (lines 41-266) with 4 fallback paths and **debug logging to /tmp/** (production antipattern).

---

## 2. Sub-System Breakdown

### 2.1 LoggingContext Dataclass (Lines 22-30)
**Responsibility**: Immutable context container for tools
**Fields**: `tool_name`, `project`, `recent_projects`, `state_snapshot`, `reminders`, `agent_id`
**Usage**: All logging tools receive this from `resolve_logging_context()`

### 2.2 ProjectResolutionError (Lines 33-38)
**Responsibility**: Custom exception for missing project context
**Payload**: Includes `recent_projects` list for helpful error messages
**Usage**: Raised when `require_project=True` but no project found

### 2.3 resolve_logging_context() MONOLITH (Lines 41-266)
**LOC**: 266 (46% of entire file!)
**Complexity**: Very High (4 fallback paths, debug logging, session routing)

**Routing Priority** (first match wins):
1. **Session-scoped** (lines 84-157): ExecutionContext.mode == "project"
   - Try `storage_backend.get_session_project(stable_session_id)`
   - Try `scribe_projects` DB table lookup
   - Fallback to JSON config files
   - Fallback to `state_manager.get_session_project()`
   - **ANTIPATTERN**: Debug logging to `/tmp/scribe_session_debug.log` (lines 95-147)

2. **Agent-scoped** (lines 159-163): If `agent_id` provided
   - Call `get_agent_project_data(agent_id)` from agent_project_utils
   - Returns `(project, recent_projects)` tuple

3. **Explicit project** (lines 165-172): If `explicit_project` parameter passed
   - Direct `load_project_config(explicit_project)` call
   - Used by query_entries for cross-project search

4. **Sentinel mode** (lines 174-194): ExecutionContext.mode == "sentinel"
   - FORBIDS project resolution (raises error if `require_project=True`)
   - Returns empty context with `project=None`
   - Used for stateless operations

5. **Global state fallback** (lines 214-228): No ExecutionContext
   - Call `load_active_project(state_manager)` (legacy path)
   - Merges recent projects from state
   - **Deprecated**: Only for backwards compatibility

**Reminders integration** (lines 236-257):
- Call `reminders.get_reminders()` if project exists
- Swallow ALL exceptions (reminders must never block tools)
- Try new signature with `agent_id`, fallback to old signature

### 2.4 Metadata Normalization (Lines 269-410)
**Responsibility**: Heal arbitrary metadata inputs into canonical format

**Two flavors**:
1. `coerce_metadata_mapping()` (lines 269-338): Input → `Dict[str, Any]`
   - Handles: dict, Mapping, str (JSON/legacy), Sequence (pairs), objects with `__dict__`
   - Fallback: Wraps unrecognized types in `{"raw_meta": str(value)}`

2. `normalize_metadata()` (lines 341-385): Input → `Tuple[Tuple[str, str], ...]`
   - Canonical format for append_entry file writes
   - Sorts keys alphabetically (deterministic output)
   - Sanitizes keys (`_sanitize_meta_key`) and values (`_stringify`)

**Healing patterns**:
- JSON string → parse with `json.loads()`
- Legacy `"key=value,key2=value2"` → split and parse
- List of pairs → dict conversion
- Objects → extract `__dict__` attributes

### 2.5 Meta Filters Normalization (Lines 413-440)
**Responsibility**: Validate metadata filters for query tools
**Contract**: `normalize_meta_filters(meta_filters) -> (Dict[str, str], Optional[error])`

**Validation rules**:
- Keys must match `META_KEY_PATTERN` regex: `^[A-Za-z0-9_.:-]+$`
- Null keys rejected
- Empty keys rejected
- Values coerced to strings

### 2.6 List Cleaning (Lines 443-477)
**Responsibility**: Normalize list-like inputs (status, agents, emoji filters)
**Features**:
- Deduplication (preserves order, uses `seen` set)
- Lowercase coercion (optional)
- JSON string parsing
- Tuple → list conversion

### 2.7 Log Definition Resolution (Lines 480-499)
**Responsibility**: Resolve log file path from log_config.json
**Contract**: `resolve_log_definition(project, log_type, cache) -> (Path, Dict)`
**Caching**: Optional cache parameter for repeated lookups

**Integration point**: Calls `log_config_module.get_log_definition()` and `resolve_log_path()`

### 2.8 Log Line Composition (Lines 502-528)
**Responsibility**: Build formatted log line string
**Format**: `[emoji] [timestamp] [Agent: name] [Project: name] [ID: id] message | key=value; key=value`

**Features**:
- Optional entry_id (deterministic UUIDs from append_entry)
- Metadata pairs formatted with semicolon separators
- Consistent segment ordering

### 2.9 Metadata Requirements Validation (Lines 531-540)
**Responsibility**: Check log_config.json metadata requirements
**Contract**: `ensure_metadata_requirements(definition, meta_payload) -> Optional[error_str]`
**Usage**: Called by LoggingToolMixin before writing entries

### 2.10 Status Emoji Resolution (Lines 543-559)
**Responsibility**: Map status strings to emoji defaults
**Fallback chain**:
1. Explicit emoji parameter (if provided)
2. STATUS_EMOJI mapping from constants.py
3. Project defaults (`project["defaults"]["emoji"]`)
4. Global default (`STATUS_EMOJI["info"]`)

### 2.11 Internal Utilities (Lines 562-574)
**Responsibility**: String sanitization helpers
- `_sanitize_meta_key()`: Replace spaces with underscores, strip pipes
- `_clean_meta_value()`: Remove newlines/carriage returns, strip pipes
- `_stringify()`: JSON-serialize complex values

---

## 3. Modularization Notes

### Extractable Module: ParameterHealer [BUCKET:config]
**Origin**: Lines 269-477 (metadata/filter/list normalization)
**Responsibilities**: Heal MCP JSON serialization, normalize filters, deduplicate lists
**Used by**: append_entry, query_entries, all logging tools
**Why extractable**: Pure transformation functions, no side effects
**Before/After**:
- Before: 200+ lines of normalization scattered in logging_utils
- After: `ParameterHealer.normalize_metadata()`, `ParameterHealer.normalize_filters()`, `ParameterHealer.clean_list()`
- Conceptual win: Tools don't know about MCP serialization quirks

### NOT Extractable: resolve_logging_context() Monolith
**Why it should stay coupled**:
- **State leaks**: Requires `server_module`, `state_manager`, `storage_backend`, `ExecutionContext`
- **Fallback complexity**: 4 routing paths with subtle precedence rules
- **Session isolation**: Changing routing order breaks session-scoped project isolation

**What SHOULD be done**: Break into smaller internal functions (one per routing path), but keep in same file.

### CRITICAL BUG: Debug Logging in Production [BUG-BASE-001]
**Location**: Lines 95-147
**Problem**: Production code writes to `/tmp/scribe_session_debug.log`
**Impact**:
- File handle leaks (opens file 3 times per context resolution)
- Unbounded disk usage (no rotation)
- Security issue (world-readable /tmp file)
**Fix**: Remove debug logging OR gate behind `SCRIBE_DEBUG_SESSION_ROUTING` env var

---

## 4. Implicit Contracts

### Contract 1: Routing Priority is Semantic, Not Documented
**Assumption**: Tools expect session-scoped > agent-scoped > explicit > sentinel > global fallback
**Violation consequence**: Changing order breaks project isolation guarantees
**Why this is risky**: Priority logic spans 225 lines with no single authoritative comment

### Contract 2: Reminders Must Never Block
**Assumption**: `get_reminders()` exceptions silently swallowed (lines 252-257)
**Violation consequence**: Tools proceed without reminders (intentional)
**Why this is policy**: Reminders are nice-to-have, not critical path

### Contract 3: Sentinel Mode Forbids Project Resolution
**Assumption**: Sentinel mode NEVER resolves project (even if state exists)
**Violation consequence**: Stateless guarantees break
**Why this matters**: sentinel.jsonl writes must not pollute project logs

### Contract 4: Metadata Normalization Never Fails
**Assumption**: `coerce_metadata_mapping()` wraps unrecognized types in `{"raw_meta": ...}`
**Violation consequence**: Tools can pass ANY type, normalization will heal it
**Why this is powerful**: Enables gradual migration from legacy metadata formats

---

## 5. Token Analysis

**Direct output**: 0 tokens (utilities don't produce output directly)
**Indirect impact**:
- Reminders integration adds 80-200 tokens per tool call (via `get_reminders()`)
- Recent projects list adds 20-50 tokens per tool call
- Log line composition is compact (emoji + timestamp + message)

**Optimization potential**: Reminders are attached by resolve_logging_context, not by tools. Could make reminders opt-in instead of automatic.

---

## 6. Error Handling Architecture

### Policy: Silent Fallbacks (Best-Effort)
**Locations**: Lines 156-157, 252-257
**Pattern**: Catch ALL exceptions, proceed with empty/None values
**Why intentional**:
- Session routing fallback: Try DB → try JSON → try state → succeed with None
- Reminders: Never block tool execution

### Policy: Strict Validation (Fail-Fast)
**Locations**: Lines 431-438 (meta filter validation)
**Pattern**: Return error string immediately on validation failure
**Why intentional**: Query filters MUST be valid (garbage in = garbage results)

### Policy: Healing (Never Fail)
**Locations**: Lines 269-338 (metadata coercion)
**Pattern**: Wrap unrecognized types in `{"raw_meta": ...}` instead of raising
**Why intentional**: Preserve user data even if format is wrong

---

## 7. Known Issues

### BUG-BASE-001: Debug Logging in Production (P0 - CRITICAL)
**Location**: Lines 95-147
**Evidence**:
```python
from pathlib import Path
from datetime import datetime, timezone
debug_log = Path("/tmp/scribe_session_debug.log")
with open(debug_log, "a") as f:
    f.write(f"\n=== get_session_project query ===\n")
    # ... more debug writes
```
**Impact**:
- File handle leaks (opens 3x per resolve_logging_context call)
- Unbounded disk growth (no log rotation)
- Security: world-readable /tmp file may leak project names
**Repro**: Call any logging tool → check `/tmp/scribe_session_debug.log` size

### BUG-BASE-002: resolve_logging_context Complexity (P2)
**Location**: Lines 41-266 (266 LOC monolith)
**Evidence**: Single function with 4 routing paths, 7 try-except blocks, debug logging
**Impact**:
- Difficult to test (4 paths × 2 modes = 8 test cases minimum)
- Difficult to reason about routing priority
- Debugging requires reading 266 lines
**Recommendation**: Break into `_resolve_session_project()`, `_resolve_agent_project()`, etc.

---

## 8. Implementation Specs

### SPEC-BASE-002: Remove Debug Logging

**Problem**: Production code writes to `/tmp/scribe_session_debug.log`
**Location**: `shared/logging_utils.py:95-147`

```yaml
spec_id: SPEC-BASE-002
title: Remove or gate debug logging in resolve_logging_context
priority: P0 (CRITICAL - security + file handle leak)
files:
  - shared/logging_utils.py:95-147
changes:
  - action: delete_lines
    lines: 95-102, 120-127, 140-147
    reason: Debug logging in production violates security and causes file handle leaks
  - action: alternative
    condition: "If debug logging needed for development"
    content: |
      import os
      DEBUG_SESSION = os.getenv("SCRIBE_DEBUG_SESSION_ROUTING", "false") == "true"

      if DEBUG_SESSION:
          debug_log = Path("/tmp/scribe_session_debug.log")
          with open(debug_log, "a") as f:
              f.write(...)  # existing debug writes
benefits:
  - Eliminates file handle leaks
  - Prevents unbounded disk growth
  - Fixes security issue (no world-readable tmp files)
  - Reduces LOC by ~30 lines
risks:
  - May need debug logging during development (use env var gate)
test_verification:
  - "After fix: call append_entry 100x, verify /tmp/scribe_session_debug.log not created"
```

### SPEC-BASE-003: Break resolve_logging_context Monolith

**Problem**: 266-line function with 4 routing paths is untestable
**Location**: `shared/logging_utils.py:41-266`

```yaml
spec_id: SPEC-BASE-003
title: Refactor resolve_logging_context into routing path functions
priority: P2 (maintainability)
files:
  - shared/logging_utils.py:41-266
changes:
  - action: extract_function
    name: _resolve_session_scoped_project
    lines: 84-157
    params: [server_module, exec_context]
    returns: Optional[Dict[str, Any]]

  - action: extract_function
    name: _resolve_agent_scoped_project
    lines: 159-163
    params: [agent_id]
    returns: Tuple[Optional[Dict], List[str]]

  - action: extract_function
    name: _resolve_explicit_project
    lines: 165-172
    params: [explicit_project]
    returns: Optional[Dict[str, Any]]

  - action: extract_function
    name: _handle_sentinel_mode
    lines: 174-194
    params: [require_project, recent_projects, tool_name, state_snapshot, agent_id]
    returns: LoggingContext

  - action: refactor_main
    new_structure: |
      async def resolve_logging_context(...) -> LoggingContext:
          # 1. Try session-scoped
          if exec_context and exec_context.mode == "project":
              project, recent = _resolve_session_scoped_project(server_module, exec_context)
              if project:
                  return _build_context(...)

          # 2. Try agent-scoped
          if agent_id:
              project, recent = _resolve_agent_scoped_project(agent_id)
              if project:
                  return _build_context(...)

          # 3. Try explicit project
          if explicit_project:
              project = _resolve_explicit_project(explicit_project)
              if project:
                  return _build_context(...)

          # 4. Handle sentinel mode
          if exec_context and exec_context.mode == "sentinel":
              return _handle_sentinel_mode(...)

          # 5. Global fallback (legacy)
          ...
benefits:
  - Each routing path testable in isolation
  - Clear routing priority (5 if statements top-to-bottom)
  - Easier debugging (grep for specific path function)
  - Reduces main function to ~50 LOC
risks:
  - Breaking routing priority if refactor wrong
test_verification:
  - "Test each routing path independently"
  - "Integration test: all 5 paths with different scenarios"
```

---

## Cross-Cutting Concerns

- **[BUCKET:config]** Metadata normalization (extractable ParameterHealer)
- **[BUCKET:state]** Session routing + agent routing (intentionally coupled)
- **[BUCKET:error_handling]** Silent fallbacks vs strict validation policy split
- **[BUCKET:reminders]** Automatic reminder integration (opt-in opportunity)
- **[BUCKET:formatting]** Log line composition (canonical format)

**Impact**: This file is imported by LoggingToolMixin, which is used by 10+ tools. Changes here affect ALL logging tools simultaneously.
