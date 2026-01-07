# Base Infrastructure: LoggingToolMixin

**File**: `shared/base_logging_tool.py`
**LOC**: 139
**Complexity**: Low (base class mixin)
**Relationships**: Used by all logging tools, depends on logging_utils, response.py, ProjectRegistry

---

## 1. Overview

LoggingToolMixin is a **base class contract enforcer** that provides standardized context resolution for all logging-oriented MCP tools. It's not a tool itself—it's a mixin that tools inherit to gain consistent project/reminder/session handling.

**Purpose**: Eliminate context resolution duplication across 10+ logging tools by providing:
- Unified project resolution (session-scoped, agent-scoped, explicit, sentinel mode)
- Reminder integration
- Response formatting contracts
- Error handling standardization

**Key Insight**: This is the **infrastructure primacy** pattern—all logging tools MUST use this mixin to participate in the project context system. Tools that bypass it (by implementing their own context resolution) violate architectural contracts.

---

## 2. Sub-System Breakdown

### 2.1 Context Preparation (Lines 29-51)
**Responsibility**: Delegate to `resolve_logging_context()` from logging_utils
**Contract**: Tools call `prepare_context()`, receive `LoggingContext` dataclass
**Required Input**: `tool_name`, optional `agent_id`, `explicit_project`, `require_project`

**What it does**:
- Validates `server_module` attribute exists (from BaseTool)
- Calls `logging_utils.resolve_logging_context()` (266 LOC monolith)
- Returns `LoggingContext(tool_name, project, recent_projects, state_snapshot, reminders, agent_id)`

### 2.2 Response Payload Assembly (Lines 53-64)
**Responsibility**: Attach context (reminders, recent_projects) to tool responses
**Contract**: Tools call `apply_context_payload(response, context)` before returning

**What it does**:
- Pops existing `recent_projects` and `reminders` from response (if present)
- Re-adds them at the END for readability (ensures context appears last)

### 2.3 Error Response Standardization (Lines 66-82)
**Responsibility**: Generate consistent error payloads
**Contract**: `error_response(message, suggestion=None, context=None, extra=None)`

**Payload structure**:
```python
{
    "ok": False,
    "error": message,
    "suggestion": suggestion,  # Optional
    **extra,  # Optional additional fields
    "recent_projects": [...],  # From context
    "reminders": [...]  # From context
}
```

### 2.4 Entry Formatting (Lines 84-104)
**Responsibility**: Format log entries using response.py formatter
**Contract**: `success_with_entries(entries, context, compact, fields, include_metadata, pagination, extra_data)`

**Critical dependency**: Calls `default_formatter.format_response()` from utils/response.py
**This is the TOKEN-001 coupling point**: All tools route through response.py for formatting

### 2.5 Metadata Validation (Lines 106-112)
**Responsibility**: Delegate to log_config metadata requirement checker
**Contract**: `validate_metadata_requirements(log_definition, meta_payload)`

**What it validates**: Checks if required metadata fields (from log_config.json) are present

### 2.6 Project Error Translation (Lines 114-139)
**Responsibility**: Convert `ProjectResolutionError` into tool-friendly response
**Contract**: `translate_project_error(error) -> Dict[str, Any]`

**What it does**:
- Extracts `recent_projects` from error
- Best-effort lookup of `last_known_project` from ProjectRegistry
- Calculates `minutes_ago` since last access
- Returns helpful error with suggestions

---

## 3. Modularization Notes

### NOT Extractable (Intentionally Coupled)

**Why this should stay a mixin**:
- **State leaks**: Requires `server_module` attribute from concrete tool
- **Inheritance boundary**: Mixins provide shared behavior without forcing single inheritance
- **Contract enforcement**: Tools MUST provide `server_module` or mixin raises `RuntimeError`

### Extractable Module Candidates

**None identified**—all methods are thin delegates to other modules:
- Context resolution → `logging_utils.resolve_logging_context()`
- Formatting → `response.py::default_formatter`
- Metadata validation → `logging_utils.ensure_metadata_requirements()`
- Registry lookups → `ProjectRegistry.get_last_known_project()`

**This is GOOD architecture**: Mixin is a thin coordination layer, not a business logic container.

---

## 4. Implicit Contracts

### Contract 1: `server_module` Attribute Required
**Assumption**: All concrete tools provide `server_module` attribute (from BaseTool inheritance)
**Violation consequence**: `RuntimeError` at line 41
**Why this is unsafe**: No type checking enforces this at class definition time

### Contract 2: LoggingContext Shape Stability
**Assumption**: `LoggingContext` dataclass never changes shape (6 fields)
**Violation consequence**: Tools expecting old shape will break
**Why this matters**: 10+ tools depend on this dataclass structure

### Contract 3: Response Payload Mutation
**Assumption**: `apply_context_payload()` mutates response dict in-place
**Violation consequence**: Callers expect mutation, not immutable return
**Why this is risky**: Side-effect heavy API (pop + re-add pattern)

### Contract 4: default_formatter Singleton
**Assumption**: `utils.response.default_formatter` exists and is initialized
**Violation consequence**: `AttributeError` if response.py not imported
**Why this is fragile**: Implicit dependency on module-level singleton

---

## 5. Token Analysis

**Mixin itself**: 0 tokens (no direct output)
**Via delegation**: All token costs delegated to:
- `response.py::default_formatter` (TOKEN-001 source)
- `reminders.get_reminders()` (80-200 tokens per reminder)

**Multiplier effect**: Since ALL logging tools use this mixin, any bloat in response.py or reminders affects ALL tools uniformly.

---

## 6. Error Handling Architecture

### Policy: Best-Effort ProjectRegistry Lookups
**Location**: Lines 123-138
**Pattern**: `try-except-pass` around `get_last_known_project()`
**Why intentional**: Last-known project hint is nice-to-have, not critical
**Evidence**: Line 137 swallows ALL exceptions silently

### Policy: Strict `server_module` Requirement
**Location**: Lines 40-41
**Pattern**: Raise `RuntimeError` immediately if missing
**Why intentional**: Context resolution CANNOT proceed without server state

---

## 7. Known Issues

**None**—this is well-designed infrastructure with clear contracts.

**Potential improvement**: Type hints for `server_module` attribute (use Protocol to enforce interface)

---

## 8. Implementation Specs

### SPEC-BASE-001: Type-Safe server_module Contract

**Problem**: `server_module` attribute required but not type-checked
**Location**: `shared/base_logging_tool.py:27, 40-41`

**Proposed solution**:
```yaml
spec_id: SPEC-BASE-001
title: Type-safe server_module contract via Protocol
priority: P3 (nice-to-have)
files:
  - shared/base_logging_tool.py:27
changes:
  - action: add_protocol
    content: |
      from typing import Protocol

      class ServerModule(Protocol):
          state_manager: StateManager
          storage_backend: StorageBackend
          get_agent_identity: Callable
          get_execution_context: Callable
  - action: replace_annotation
    line: 27
    old: "server_module: Any"
    new: "server_module: ServerModule"
benefits:
  - Static type checking enforces contract at class definition
  - IDE autocomplete for server_module methods
  - Explicit documentation of required interface
risks:
  - Requires defining StateManager, StorageBackend protocols
  - Backwards compatibility if Protocol unavailable (Python <3.8)
```

---

## Cross-Cutting Concerns

- **[BUCKET:config]** Couples to logging_utils context resolution (266 LOC)
- **[BUCKET:formatting]** Couples to response.py default_formatter (TOKEN-001 source)
- **[BUCKET:reminders]** Implicit reminder system integration via context
- **[BUCKET:error_handling]** Standardizes error response format across ALL tools

**Impact**: Changes to LoggingToolMixin affect 10+ logging tools simultaneously. This is intentional—mixin exists to enforce consistency.
