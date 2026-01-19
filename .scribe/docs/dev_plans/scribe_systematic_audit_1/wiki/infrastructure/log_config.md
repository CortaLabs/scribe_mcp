# Base Infrastructure: Log Configuration (Multi-Log Routing)

**File**: `config/log_config.json`
**LOC**: 32 (JSON config file)
**Complexity**: Low (declarative config)
**Relationships**: Loaded by logging_utils, used by ALL logging tools

---

## 1. Overview

log_config.json defines the **multi-log routing system**—a declarative configuration mapping log types to file paths, formats, metadata requirements, and rotation settings. This enables tools to write to different logs (progress, doc_updates, security, bugs, global, tool_logs) based on `log_type` parameter.

**Purpose**: Decouple log destinations from tool code
**Pattern**: JSON config loaded once, cached for performance
**Contract**: Tools call `resolve_log_definition(project, log_type)` to get path + requirements

---

## 2. Sub-System Breakdown

### 2.1 Progress Log (Lines 3-5) - DEFAULT
```json
"progress": {
  "path": "{progress_log}"
}
```
**Template variable**: `{progress_log}` resolves to project's `progress_log` field
**Metadata requirements**: None (accepts any metadata)
**Usage**: Default log for all append_entry calls without explicit log_type

### 2.2 Doc Updates Log (Lines 6-9)
```json
"doc_updates": {
  "path": "{docs_dir}/DOC_LOG.md",
  "metadata_requirements": ["doc", "section", "action"]
}
```
**Template variable**: `{docs_dir}` resolves to `.scribe/docs/dev_plans/<project>/`
**Metadata requirements**: `doc`, `section`, `action` (enforced by logging_utils)
**Usage**: Automatic via manage_docs (tracks document edits)
**Auto-writer**: manage_docs tool appends here automatically

### 2.3 Security Log (Lines 10-13)
```json
"security": {
  "path": "{docs_dir}/SECURITY_LOG.md",
  "metadata_requirements": ["severity", "area", "impact"]
}
```
**Usage**: Security audit entries (manual via append_entry)
**Metadata requirements**: `severity` (low/medium/high/critical), `area` (component), `impact` (description)

### 2.4 Bugs Log (Lines 14-17)
```json
"bugs": {
  "path": "{docs_dir}/BUG_LOG.md",
  "metadata_requirements": ["severity", "component", "status"]
}
```
**Usage**: Bug tracking lifecycle (investigation → fixed → verified)
**Metadata requirements**: `severity`, `component`, `status`
**Auto-writer**: Bug Hunter agent uses this log type

### 2.5 Global Log (Lines 18-23)
```json
"global": {
  "path": "docs/GLOBAL_PROGRESS_LOG.md",
  "metadata_requirements": ["project", "entry_type"],
  "description": "Repository-wide progress log for project lifecycle events and milestones",
  "auto_events": ["project_created", "project_phase_change", "project_completed", "research_completed", "architecture_approved", "implementation_completed"]
}
```
**Path**: NOT project-scoped (no template variables)
**Usage**: Repository-wide milestones (cross-project events)
**Metadata requirements**: `project` (which project), `entry_type` (event type)
**Auto-events**: List of lifecycle events that should trigger global log entries

### 2.6 Tool Logs (Lines 24-31) - AUDIT TRAIL
```json
"tool_logs": {
  "path": "{docs_dir}/TOOL_LOG.jsonl",
  "format": "jsonl",
  "metadata_requirements": ["tool", "format_requested"],
  "rotation_threshold": 1000,
  "description": "Structured JSON audit trail for all tool calls"
}
```
**Format**: JSONL (not Markdown) for structured parsing
**Metadata requirements**: `tool` (tool name), `format_requested` (readable/structured/compact)
**Rotation**: Auto-rotate after 1000 entries
**Usage**: Audit log for ALL tool invocations (automatic)

---

## 3. Modularization Notes

### NOT Extractable (Intentionally Declarative)
**Why JSON config should stay**:
- **Declarative**: No code execution, pure data
- **Extensible**: Add new log types without code changes
- **Validatable**: JSON schema could enforce structure

### Potential Improvement: JSON Schema Validation [BUCKET:config]
**Current**: No validation (invalid config causes runtime errors)
**Proposal**: Define JSON schema, validate on load
**Benefit**: Catch config errors at startup (not when log type accessed)

---

## 4. Implicit Contracts

### Contract 1: Template Variables Must Exist in Project
**Assumption**: `{progress_log}`, `{docs_dir}` fields exist in project dict
**Violation consequence**: `KeyError` during path resolution
**Why this is risky**: No validation that project has required fields

### Contract 2: Metadata Requirements are Enforced by logging_utils
**Assumption**: `ensure_metadata_requirements()` validates before write
**Violation consequence**: Writes blocked if required metadata missing
**Why this matters**: Prevents incomplete log entries

### Contract 3: Log Type Keys are Lowercase
**Assumption**: All log type keys lowercase (`"progress"`, not `"Progress"`)
**Violation consequence**: Case-sensitive lookup fails
**Why this is convention**: logging_utils normalizes log_type to lowercase

### Contract 4: Path Templates are Resolved at Runtime
**Assumption**: Template variables like `{docs_dir}` resolved when log written
**Violation consequence**: Static paths can't adapt to project changes
**Why this is powerful**: Same config works for all projects

---

## 5. Token Analysis

**Direct output**: 0 tokens (config file doesn't produce output)
**Indirect impact**: None (routing logic is invisible to users)

---

## 6. Error Handling Architecture

### Policy: Fail if Log Type Unknown
**Pattern**: `get_log_definition(log_type)` raises `KeyError` if type not in config
**Why intentional**: Better to fail fast than write to wrong log

### Policy: Fail if Metadata Missing
**Pattern**: `ensure_metadata_requirements()` returns error string
**Why intentional**: Required metadata enforces log entry quality

---

## 7. Known Issues

### CONFIG-LOG-001: No JSON Schema Validation (P2)
**Location**: config/log_config.json (entire file)
**Evidence**: No validation that config is well-formed
**Impact**: Invalid config causes runtime errors (not startup errors)
**Recommendation**: Add JSON schema + validation at load time

### CONFIG-LOG-002: Template Variable Escaping Not Supported (P3)
**Location**: Path templates (`{progress_log}`, `{docs_dir}`)
**Evidence**: No way to escape `{` or `}` in paths
**Impact**: Can't use literal braces in log paths
**Recommendation**: Add escape syntax (`{{` → `{`)

---

## 8. Implementation Specs

### SPEC-CONFIG-LOG-001: Add JSON Schema Validation

**Problem**: Invalid log_config.json causes runtime errors, not startup errors
**Location**: config/log_config.json + loading code

```yaml
spec_id: SPEC-CONFIG-LOG-001
title: Add JSON schema validation for log_config.json
priority: P2 (config safety)
files:
  - config/log_config.json
  - config/log_config.py (loading code)
  - NEW: config/log_config.schema.json
changes:
  - action: create_schema
    path: config/log_config.schema.json
    content: |
      {
        "type": "object",
        "properties": {
          "logs": {
            "type": "object",
            "patternProperties": {
              "^[a-z_]+$": {
                "type": "object",
                "required": ["path"],
                "properties": {
                  "path": {"type": "string"},
                  "format": {"enum": ["markdown", "jsonl"]},
                  "metadata_requirements": {
                    "type": "array",
                    "items": {"type": "string"}
                  },
                  "rotation_threshold": {"type": "integer", "minimum": 1},
                  "description": {"type": "string"},
                  "auto_events": {
                    "type": "array",
                    "items": {"type": "string"}
                  }
                }
              }
            }
          }
        },
        "required": ["logs"]
      }

  - action: add_validation
    file: config/log_config.py
    content: |
      import json
      import jsonschema

      def load_log_config():
          with open("config/log_config.json") as f:
              config = json.load(f)
          with open("config/log_config.schema.json") as f:
              schema = json.load(f)
          jsonschema.validate(config, schema)  # Raises if invalid
          return config

benefits:
  - Invalid config caught at startup (not runtime)
  - Self-documenting schema (defines valid structure)
  - Easier to add new log types (schema enforces contracts)
risks:
  - Requires jsonschema dependency
  - Schema must stay in sync with config
```

---

## Cross-Cutting Concerns

- **[BUCKET:config]** Multi-log routing system (affects ALL logging tools)
- **[BUCKET:persistence]** Defines where logs are written
- **[BUCKET:metadata]** Enforces metadata requirements via `ensure_metadata_requirements()`

**Impact**: Adding new log types requires updating log_config.json + documenting metadata requirements. Changes here affect ALL tools that use multi-log routing.

**Relationship to other config**: Works alongside `settings.py` (global config) and project JSON configs (per-project settings).
