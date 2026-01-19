# Base Infrastructure: Settings (Global Configuration)

**File**: `config/settings.py`
**LOC**: 225
**Complexity**: Medium (75 configuration fields + env var loading)
**Relationships**: Imported by ALL modules (singleton settings object)

---

## 1. Overview

Settings module provides **global runtime configuration** loaded from environment variables. This is the single source of truth for all scribe_mcp behavior: paths, storage backends, feature flags, token limits, reminder config, vector indexing settings.

**Purpose**: Centralize configuration so tools don't hardcode paths or settings
**Pattern**: Frozen dataclass loaded once at module import time (singleton)
**Contract**: All modules import `from config.settings import settings` for configuration access

---

## 2. Sub-System Breakdown

### 2.1 Settings Dataclass (Lines 33-74)
**75 configuration fields** grouped by category:

**Paths** (5 fields):
- `project_root`: Scribe MCP repository root (from `SCRIBE_ROOT` env var)
- `default_state_path`: State JSON file path (`.scribe/state.json`)
- `sqlite_path`: SQLite DB path (`data/scribe_projects.db`)
- `dev_plans_base`: Dev plans directory (`.scribe/docs/dev_plans`)

**Storage** (3 fields):
- `storage_backend`: "sqlite" or "postgres"
- `db_url`: PostgreSQL connection string (optional)
- `allow_network`: Enable network access for tools

**Limits** (5 fields):
- `recent_projects_limit`: Max recent projects to track (default: 5)
- `log_rate_limit_count`: Rate limit for log writes (default: 0 = disabled)
- `log_rate_limit_window`: Rate limit window in seconds
- `log_max_bytes`: Max log file size before rotation
- `storage_timeout_seconds`: Database operation timeout (default: 5.0)

**Reminders** (4 fields):
- `reminder_defaults`: JSON blob for reminder behavior customization
- `reminder_idle_minutes`: Gap before new work session resets (default: 45)
- `reminder_warmup_minutes`: Grace period after resuming (default: 5)
- `use_db_cooldown_tracking`: Feature flag (default: False)
- `use_session_aware_hashes`: Feature flag (default: False)

**Vector Indexing** (7 fields):
- `vector_enabled`: Enable vector search (default: from config)
- `vector_backend`: "faiss" or other backend
- `vector_dimension`: Embedding dimension
- `vector_model`: Model name for embeddings
- `vector_gpu`: Use GPU acceleration
- `vector_queue_max`: Max queue size
- `vector_batch_size`: Batch size for indexing

**Token Optimization** (10 fields):
- `default_page_size`: Default pagination size (50)
- `max_page_size`: Max pagination size (100)
- `default_compact_mode`: Default to compact output (False)
- `token_warning_threshold`: Warn if response > N tokens (4000)
- `token_daily_limit`: Daily token budget (100000)
- `token_operation_limit`: Max tokens per operation (8000)
- `token_warning_threshold_percent`: Warn at % of limit (0.8)
- `default_field_selection`: Fields for compact mode
- `tokenizer_model`: Model for token estimation ("gpt-4")

**Other** (3 fields):
- `mcp_server_name`: MCP server identifier
- `extra_options`: Arbitrary JSON config
- `storage_timeout_seconds`: Timeout for DB operations

### 2.2 Settings.load() Class Method (Lines 76-208)
**Responsibility**: Load all settings from environment variables with defaults
**Pattern**: Parse env vars, apply validation, construct Settings dataclass

**Key parsing**:
- Paths: Resolve relative to `SCRIBE_ROOT` (lines 78-97)
- Storage backend: Auto-detect from `SCRIBE_DB_URL` presence (lines 86-90)
- Reminder config: Parse JSON blob from `SCRIBE_REMINDER_DEFAULTS` (line 117)
- Vector config: Delegate to `vector_config.py` (lines 129-140)
- Token config: Parse int/float env vars with defaults (lines 143-161)
- Feature flags: Parse boolean env vars (lines 164-169)

**Validation** (defensive):
- `max(1, int(value))` pattern ensures positive integers
- `max(0.1, float(value))` ensures positive floats
- Boolean parsing: `"true"/"yes"/"1"` (case-insensitive)

### 2.3 Helper Functions (Lines 210-223)
**_default_root()** (lines 211-213): Infer repo root from `__file__` location
**_int_env()** (lines 216-223): Safe int parsing with default fallback
**_load_env_json()** (lines 19-30): Parse JSON from env var string

### 2.4 Singleton Initialization (Line 226)
**Code**: `settings = Settings.load()`
**Pattern**: Module-level singleton loaded at import time
**Consequence**: Settings frozen for entire process lifetime (no hot reload)

---

## 3. Modularization Notes

### NOT Extractable (Intentionally Global)
**Why settings should stay global singleton**:
- **Consistency**: All modules must see same config (no divergence)
- **Performance**: Load once at startup (not per-tool-call)
- **Simplicity**: Import `settings` anywhere, no dependency injection

### Potential Improvement: Config Validation [BUCKET:config]
**Current**: Minimal validation (max() calls ensure positive values)
**Proposal**: Pydantic-style validation with type checking + constraints
**Benefit**: Catch invalid env vars at startup (not at runtime)

---

## 4. Implicit Contracts

### Contract 1: Settings Immutable After Load
**Assumption**: `frozen=True` dataclass prevents mutation after initialization
**Violation consequence**: Attempting `settings.project_root = ...` raises `FrozenInstanceError`
**Why this matters**: Ensures consistent config across all tool calls

### Contract 2: Environment Variables are Truth
**Assumption**: All config comes from env vars (no config files)
**Violation consequence**: Changing settings requires process restart
**Why this is limiting**: No dynamic reconfiguration (requires MCP server restart)

### Contract 3: Defaults are Hardcoded
**Assumption**: Default values in `Settings.load()` are canonical
**Violation consequence**: No override mechanism besides env vars
**Why this is risky**: Changing defaults requires code change + redeploy

### Contract 4: Vector Config Delegated
**Assumption**: `vector_config.py` module exists and provides `load_vector_config()`
**Violation consequence**: ImportError if vector_config.py missing
**Why this is coupling**: Settings depends on another config module

---

## 5. Token Analysis

**Direct output**: 0 tokens (config doesn't produce output)
**Indirect impact**:
- `token_warning_threshold`: Controls when warnings appear (default 4000)
- `default_compact_mode`: Could default to compact (not implemented)
- `default_field_selection`: Fields for compact mode (not widely used)

**Optimization**: Most token config fields are defined but not enforced consistently

---

## 6. Error Handling Architecture

### Policy: Defensive Defaults (Never Fail)
**Pattern**: All env var parsing wrapped in try-except with fallback defaults
**Examples**:
- Invalid int → use default (lines 108-111, 216-223)
- Missing JSON → empty dict (lines 19-30)
- Invalid path → resolve relative to root

**Why intentional**: Settings load MUST succeed (server can't start otherwise)

---

## 7. Known Issues

### CONFIG-001: No Config Validation Framework (P2)
**Location**: Lines 76-208 (manual validation scattered throughout)
**Evidence**: Validation is ad-hoc (`max()` calls, try-except)
**Impact**: Invalid env vars may pass validation, cause runtime errors
**Recommendation**: Use Pydantic for structured validation

### CONFIG-002: 75 Fields is Excessive (P3 - Design Smell)
**Location**: Lines 33-74
**Evidence**: Settings dataclass has 75 fields (config complexity explosion)
**Impact**: Hard to understand what settings exist, which are used
**Recommendation**: Group related settings into nested dataclasses
**Example**:
```python
@dataclass
class TokenConfig:
    warning_threshold: int
    daily_limit: int
    operation_limit: int
    # ... 7 more fields

@dataclass
class Settings:
    token_config: TokenConfig
    vector_config: VectorConfig
    reminder_config: ReminderConfig
    # ... only 10-15 top-level fields
```

---

## 8. Implementation Specs

### SPEC-CONFIG-001: Group Settings into Nested Dataclasses

**Problem**: 75 flat fields is unmaintainable config complexity
**Location**: `config/settings.py:33-74`

```yaml
spec_id: SPEC-CONFIG-001
title: Refactor Settings into nested config groups
priority: P3 (maintainability)
files:
  - config/settings.py:33-74
changes:
  - action: create_config_groups
    groups:
      - PathConfig: project_root, default_state_path, sqlite_path, dev_plans_base
      - StorageConfig: storage_backend, db_url, allow_network, storage_timeout_seconds
      - LimitConfig: recent_projects_limit, log_rate_limit_count, log_rate_limit_window, log_max_bytes
      - ReminderConfig: reminder_defaults, reminder_idle_minutes, reminder_warmup_minutes, use_db_cooldown_tracking, use_session_aware_hashes
      - VectorConfig: (already exists in vector_config.py - import it)
      - TokenConfig: default_page_size, max_page_size, default_compact_mode, token_warning_threshold, token_daily_limit, token_operation_limit, token_warning_threshold_percent, default_field_selection, tokenizer_model

  - action: refactor_settings
    new_structure: |
      @dataclass(frozen=True)
      class Settings:
          paths: PathConfig
          storage: StorageConfig
          limits: LimitConfig
          reminders: ReminderConfig
          vector: VectorConfig
          tokens: TokenConfig
          mcp_server_name: str
          extra_options: Dict[str, Any]

benefits:
  - Settings reduced from 75 flat fields → 8 top-level fields
  - Logical grouping (easier to find related settings)
  - Each config group self-contained (easier to test)
  - Migration path: settings.paths.project_root (was settings.project_root)
risks:
  - Breaking change for all imports (need migration guide)
  - More dataclasses to maintain
migration_strategy:
  - Keep old flat access as @property wrappers for backwards compatibility
  - Deprecate flat access over 2-3 releases
```

---

## Cross-Cutting Concerns

- **[BUCKET:config]** Central configuration system (affects ALL modules)
- **[BUCKET:utilities]** Env var parsing helpers (_int_env, _load_env_json)
- **[BUCKET:error_handling]** Defensive defaults (never fail on invalid env vars)

**Impact**: Changes to settings.py affect ALL modules (imported everywhere). Adding new config fields requires updating Settings dataclass + Settings.load().

**Relationship to other config**: Works alongside `log_config.json` (multi-log definitions) and `vector_config.py` (vector settings).
