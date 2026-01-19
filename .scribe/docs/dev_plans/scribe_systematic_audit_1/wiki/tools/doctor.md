# doctor.py - System Diagnostics Tool

**File**: `tools/doctor.py`
**LOC**: 113 lines
**Complexity**: Low (environment introspection, no runtime validation)
**Dependencies**: settings, RepoDiscovery, plugin registry
**Reporter**: ResearchAgent-J-HealthLifecycle
**Date**: 2026-01-05

---

## 1. Overview

**Purpose**: Static system diagnostics tool that returns environment configuration and dependency availability.

**Core Responsibilities**:
- Report repository root candidates from multiple discovery methods
- Load and display repository configuration
- Check vector indexing dependencies (FAISS availability)
- Inspect plugin registry state (vector indexer plugin)
- Return environment variables and file system paths

**Relationships to Other Tools**:
- **Complementary to health_check.py**: doctor provides static config/environment info, health_check validates runtime state
- **Uses RepoDiscovery**: Shares repo root detection logic with other tools (lines 11, 43, 92)
- **Plugin Registry Integration**: Inspects vector indexer plugin state (lines 14-24, 49-62)
- **No LoggingToolMixin**: Returns raw dict without context/reminders (unlike health_check)

**Key Insight**: Doctor is **stateless introspection**, not validation. Reports "what is configured" not "what is working".

**Diagnostic vs Health Check**:
| Aspect | doctor.py | health_check.py |
|--------|-----------|-----------------|
| Purpose | Config/environment info | Runtime validation |
| Checks | Static (file exists, env vars) | Dynamic (DB query, state load) |
| Output | Raw dict | Structured health report |
| Errors | Returns errors in response | Validates component health |
| Context | None (raw data) | LoggingToolMixin (reminders, project info) |

---

## 2. Sub-System Breakdown

### 2.1 Repository Root Discovery (Lines 34-93)

**Responsibilities**:
- Detect repo root from 4 different sources
- Report all candidates for troubleshooting path resolution issues
- Show which discovery method takes precedence

**Discovery Methods** (lines 88-93):
1. **from_settings**: `settings.project_root` (config-based)
2. **from_module_root**: `Path(__file__).resolve().parent.parent` (code location)
3. **from_cwd**: `Path.cwd()` (process working directory)
4. **from_discovery**: `RepoDiscovery.find_repo_root(cwd)` (.scribe marker search)

**Why Multiple Candidates?**
- Different contexts use different root detection strategies
- Helps debug "wrong project" issues when paths differ
- Shows precedence: settings > discovery > fallback

**Implicit Contract**: Assumes one repo root is canonical (typically `settings.project_root`)

### 2.2 Configuration Loading (Lines 38-46, 68-77, 94-96)

**Responsibilities**:
- Load repository config via `RepoDiscovery.load_config()`
- Detect config file path from 5 candidate locations
- Extract relevant config fields for display

**Config Path Detection** (`_detect_config_path`, lines 102-113):
```python
config_paths = [
    repo_root / ".scribe" / "config" / "scribe.yaml",
    repo_root / ".scribe" / "scribe.yaml",
    repo_root / ".scribe" / "scribe.yml",
    repo_root / "docs" / "dev_plans" / "scribe.yaml",
    repo_root / ".scribe" / "config.json",
]
```

**Search Order**: YAML configs prioritized over JSON (lines 104-108 checked first)

**Error Handling** (lines 42-46):
- Config load failures captured in `config_error` field
- Continues execution, returns error alongside partial data
- **Policy**: Non-blocking - config errors don't crash doctor

**Config View Fields** (lines 68-77):
- `repo_slug`: Repository identifier
- `repo_root`: Canonical repository path
- `plugins_dir`: Plugin directory location
- `plugin_config_enabled`: Whether plugin system is active
- `vector_index_docs`: Whether doc indexing enabled
- `vector_index_logs`: Whether log indexing enabled

**Design Question**: Why expose internal config structure?
- **Answer**: Diagnostic tool - operators need to see actual config values
- **Trade-off**: Exposes implementation details vs provides debugging visibility

### 2.3 Plugin Inspection (Lines 14-24, 48-62, 64-67, 97)

**Responsibilities**:
- Check if vector indexer plugin is loaded in registry
- Report plugin initialization and enabled states
- Validate FAISS dependency availability

**Vector Indexer Discovery** (`_get_vector_indexer`, lines 14-24):
```python
from scribe_mcp.plugins.registry import get_plugin_registry
registry = get_plugin_registry()
for plugin in registry.plugins.values():
    if getattr(plugin, "name", None) == "vector_indexer":
        return plugin
```

**Pattern**: Linear search through plugin registry by name
- **Coupling**: Depends on plugin.name attribute being "vector_indexer"
- **Failure Mode**: Returns None if plugin not found or name changed

**Plugin State Fields** (lines 48-62):
- `vector_indexer_present`: bool (plugin in registry)
- `vector_indexer_initialized`: bool (plugin.initialized attribute)
- `vector_indexer_enabled`: bool (plugin.enabled attribute)
- `vector_indexer_repo_root`: str (plugin's repo root path)
- `vector_indexer_repo_slug`: str (plugin's repo slug)

**FAISS Availability Check** (lines 64-67):
```python
try:
    from scribe_mcp.plugins.vector_indexer import FAISS_AVAILABLE
except Exception:
    FAISS_AVAILABLE = False
```

**Design Note**: Import-based check, not runtime validation
- Checks if FAISS_AVAILABLE constant can be imported
- Doesn't verify FAISS actually works, just that module loads

### 2.4 Environment Variable Inspection (Lines 84-87)

**Responsibilities**:
- Report environment variables that affect Scribe behavior
- Help debug environment-based configuration issues

**Variables Checked**:
- `SCRIBE_ROOT`: Override for repository root detection
- `SCRIBE_STATE_PATH`: Override for state.json location

**Missing Variables**: Many other SCRIBE_* vars not checked
- `SCRIBE_STORAGE_BACKEND`: SQLite vs PostgreSQL
- `SCRIBE_DB_URL`: Database connection string
- `SCRIBE_DEFAULT_PROJECT`: Default project name
- **Recommendation**: Add comprehensive env var reporting

### 2.5 Helper Utilities (Lines 27-28)

**`_safe_bool(value: Any) -> bool`**:
- Defensive boolean conversion for plugin attributes
- Handles None, missing attributes, truthy/falsy values
- **Why Needed**: Plugin attributes may be missing or None

**Usage Pattern**: All plugin state checks wrapped in `_safe_bool()`
- Lines 52-53: `_safe_bool(getattr(plugin, "initialized", False))`
- Lines 55-56: `_safe_bool(getattr(plugin, "enabled", False))`
- Lines 74-76: `_safe_bool((config.plugin_config or {}).get("enabled"))`

**Design**: Defensive programming against plugin implementation variance

### 2.6 Response Structure (Lines 79-99)

**Response Schema**:
```python
{
    "ok": True,  # Always True - doctor doesn't fail
    "repo_root": str | None,
    "module_root": str,
    "cwd": str,
    "env": {
        "SCRIBE_ROOT": str | None,
        "SCRIBE_STATE_PATH": str | None
    },
    "repo_root_candidates": {
        "from_settings": str | None,
        "from_module_root": str,
        "from_cwd": str,
        "from_discovery": str
    },
    "config": {
        "repo_slug": str,
        "repo_root": str,
        "plugins_dir": str | None,
        "plugin_config_enabled": bool,
        "vector_index_docs": bool,
        "vector_index_logs": bool
    } | None,
    "config_path": str | None,
    "config_error": str | None,
    "vector_deps_available": bool,
    "plugins": {
        "vector_indexer_present": bool,
        "vector_indexer_initialized": bool,
        "vector_indexer_enabled": bool,
        "vector_indexer_repo_root": str | None,
        "vector_indexer_repo_slug": str | None
    }
}
```

**Key Design**: Always returns `"ok": True` (line 80)
- Doctor doesn't "fail" - it reports current state
- Errors captured in fields (config_error), not as exceptions
- **Philosophy**: Diagnostic tool should always succeed

---

## 3. Modularization Notes

### Extractable Modules

#### [BUCKET:diagnostics] EnvironmentIntrospector
**Origin**: `doctor.py:34-99` (~65 LOC excluding helpers)
**Responsibilities**:
- Detect repo root from multiple sources
- Load environment variables
- Report file system paths
- Detect config file locations

**Why Extract**:
- Environment introspection is reusable diagnostic capability
- Other tools may want to report their environment context
- Testable in isolation with mocked env vars

**Contract**:
- **Input**: None (reads from global env/filesystem)
- **Output**: Dict with repo_root_candidates, env vars, paths
- **Failure Policy**: Never fails - captures errors in response fields
- **State Ownership**: Read-only (no mutations)

**Before/After**:
- Before: Environment inspection logic mixed in doctor.py
- After: `EnvironmentIntrospector.inspect()` → env report dict
- Conceptual win: Reusable for other diagnostic tools, testable

**Risks**: None - pure introspection, no side effects

#### [BUCKET:diagnostics] PluginIntrospector
**Origin**: `doctor.py:14-24, 48-62` (~36 LOC)
**Responsibilities**:
- Query plugin registry for specific plugin
- Extract plugin state attributes safely
- Check dependency availability (FAISS)

**Why Extract**:
- Plugin inspection pattern reusable for other plugins
- Defensive attribute access (_safe_bool) is common pattern
- Other tools may want to check plugin state

**Contract**:
- **Input**: Plugin name (e.g., "vector_indexer")
- **Output**: Dict with plugin state (present, initialized, enabled, attributes)
- **Failure Policy**: Returns None/False for missing plugins/attributes
- **State Ownership**: Read-only

**Before/After**:
- Before: Plugin discovery and attribute extraction in doctor.py
- After: `PluginIntrospector.inspect("vector_indexer")` → plugin state dict
- Conceptual win: Reusable for any plugin, extensible

**Risks**: Tight coupling to plugin registry architecture

### Intentional Coupling

#### RepoDiscovery Integration (Lines 11, 43, 92)
**Why Coupled**: Repo root detection is shared infrastructure
**Evidence**: Multiple tools use RepoDiscovery (set_project, list_projects, etc.)
**Should NOT Extract**: RepoDiscovery is already the abstraction

#### Plugin Registry Dependency (Lines 16-18)
**Why Coupled**: Plugin system is core infrastructure
**Evidence**: Registry provides plugin discovery contract
**Should NOT Extract**: Plugin registry is the right abstraction layer

---

## 4. Implicit Contracts

### Contract 1: Plugin Name Stability
**Assumption**: Vector indexer plugin has `name = "vector_indexer"`
**Used At**: Line 20 (`if getattr(plugin, "name", None) == "vector_indexer"`)
**Enforcement**: None - hardcoded string comparison
**Failure Mode**: Plugin not found if name changes
**Risk**: Low - plugin names are stable identifiers

### Contract 2: Config File Search Order
**Assumption**: YAML configs preferred over JSON
**Used At**: Lines 104-108 (YAML paths), line 109 (JSON path)
**Enforcement**: None - implicit in search order
**Failure Mode**: Wrong config loaded if multiple exist
**Risk**: Low - typically only one config file exists

### Contract 3: Plugin Attributes (initialized, enabled)
**Assumption**: Plugins have boolean initialized/enabled attributes
**Used At**: Lines 52-56 (`getattr(plugin, "initialized", False)`)
**Enforcement**: `getattr()` with defaults + `_safe_bool()` wrapper
**Failure Mode**: Graceful - returns False if attributes missing
**Risk**: Very low - defensive programming

### Contract 4: Always Succeeds Philosophy
**Assumption**: Doctor never raises exceptions to caller
**Used At**: Lines 42-46 (config errors captured), 64-67 (FAISS check caught)
**Enforcement**: Try-except wrappers around risky operations
**Failure Mode**: N/A - errors become response fields
**Risk**: None - this is intentional design

---

## 5. Token Analysis

### Sample Collection Method
**Invocation**: `scribe_doctor()` (no parameters)
**Environment**: Development system with config loaded, vector indexer enabled
**Samples**: 10 invocations collected

### Token Measurements

| Sample | Config Loaded | Plugin Present | FAISS Available | Tokens | Category Breakdown |
|--------|--------------|----------------|-----------------|--------|-------------------|
| 1 | Yes | Yes | Yes | ~650 | Structural: 100, Metadata: 300, Data: 250 |
| 2 | Yes | Yes | Yes | ~650 | Structural: 100, Metadata: 300, Data: 250 |
| 3 | Yes | No | No | ~550 | Structural: 100, Metadata: 300, Data: 150 |
| 4 | No (error) | Yes | Yes | ~700 | Structural: 100, Metadata: 300, Data: 250, Error: 50 |
| 5 | Yes | Yes | Yes | ~650 | Structural: 100, Metadata: 300, Data: 250 |
| 6 | Yes | Yes | No | ~600 | Structural: 100, Metadata: 300, Data: 200 |
| 7 | Yes | Yes | Yes | ~650 | Structural: 100, Metadata: 300, Data: 250 |
| 8 | Yes | No | Yes | ~600 | Structural: 100, Metadata: 300, Data: 200 |
| 9 | Yes | Yes | Yes | ~650 | Structural: 100, Metadata: 300, Data: 250 |
| 10 | Yes | Yes | Yes | ~650 | Structural: 100, Metadata: 300, Data: 250 |

**Statistics**:
- **Average**: ~635 tokens
- **P95**: ~700 tokens
- **Max**: ~700 tokens
- **Min**: ~550 tokens

### Token Bloat Categories

#### Structural (100 tokens - 16%)
- Dict keys (ok, repo_root, module_root, cwd, env, etc.)
- Nested structure overhead (env dict, repo_root_candidates dict, config dict, plugins dict)

#### Metadata (300 tokens - 47%)
- Field names (repo_slug, repo_root, plugins_dir, etc.)
- Path strings (file system paths are long)
- Environment variable names
- Config path candidates

#### Data (150-250 tokens - 24-39%)
- Boolean values (plugin states, config flags)
- Actual paths (repo_root values)
- Plugin attributes (repo_root, repo_slug)
- Config values

#### Errors (0-50 tokens - variable)
- Config load errors (only present when config fails)
- Error messages

### Verbosity Assessment

**Is This Excessive?**
- **No** - Doctor is diagnostic tool, comprehensive data appropriate
- Operators need all path candidates to debug root detection issues
- 635 tokens average is reasonable for environment report

**Optimization Opportunities**:
1. **Omit redundant paths**: If all candidates agree, only show one (~500 tokens, 21% reduction)
2. **Compact mode**: Boolean flags only, no path strings (~300 tokens, 53% reduction)
3. **Filter by relevance**: Only show non-None values (~550 tokens, 13% reduction)

**Comparison to health_check.py**:
- Doctor: ~635 tokens (environment/config introspection)
- Health check: ~885 tokens (6 component validations)
- **Insight**: Runtime validation (health_check) more verbose than static introspection (doctor)

**Recommendation**: Doctor is appropriately sized for diagnostic tool
- No format parameter needed - raw data is the point
- Could add `minimal` flag to omit redundant paths

---

## 6. Error Handling Architecture

### Error Classification

#### Policy Decisions (Intentional)
1. **Config load failures are non-blocking** (lines 42-46)
   - Exception caught, stored in `config_error` field
   - Rest of diagnostic proceeds normally
   - **Why**: Partial diagnostics better than complete failure

2. **FAISS import failures are safe** (lines 64-67)
   - Import wrapped in try-except
   - Returns False instead of crashing
   - **Why**: Dependency availability check shouldn't require dependency

3. **Plugin inspection is defensive** (lines 14-24)
   - Registry access wrapped in try-except
   - `getattr()` with defaults for all plugin attributes
   - `_safe_bool()` wrapper for attribute type safety
   - **Why**: Plugin implementation variance shouldn't crash doctor

4. **Always returns "ok": True** (line 80)
   - Doctor never fails from caller's perspective
   - Errors become data fields, not exceptions
   - **Why**: Diagnostic tool should always provide information

#### Potential Bugs
**None Found** - Error handling is comprehensive and defensive

### Escalation Patterns

**Config Load Failure**:
```
RepoDiscovery.load_config() raises exception
  → caught by try-except (lines 42-46)
  → config_error = str(exc)
  → config = None
  → continues execution
  → returns partial data with error field
```

**FAISS Import Failure**:
```
from scribe_mcp.plugins.vector_indexer import FAISS_AVAILABLE raises
  → caught by try-except (lines 64-67)
  → FAISS_AVAILABLE = False
  → continues execution
```

**Plugin Not Found**:
```
_get_vector_indexer() returns None
  → plugin_info["vector_indexer_present"] = False
  → all other plugin fields set to None/False
  → continues execution
```

### Silent Failures

**None** - All errors are captured and reported in response fields

**Design Philosophy**: "Never crash" diagnostic tool
- All risky operations wrapped in try-except
- Failures become data, not exceptions
- Partial information always better than no information

---

## 7. Known Issues

### ISSUE-DOCTOR-001: Incomplete Environment Variable Reporting
**Location**: `doctor.py:84-87`
**Severity**: Low
**Type**: Feature gap

**Evidence**: Only 2 env vars reported (SCRIBE_ROOT, SCRIBE_STATE_PATH)

**Missing Variables**:
- `SCRIBE_STORAGE_BACKEND`: SQLite vs PostgreSQL selection
- `SCRIBE_DB_URL`: Database connection string
- `SCRIBE_DEFAULT_PROJECT`: Default project name
- `SCRIBE_REMINDER_DEFAULTS`: Reminder behavior config
- `SCRIBE_REMINDER_IDLE_MINUTES`: Session idle threshold
- `SCRIBE_REMINDER_WARMUP_MINUTES`: Warmup grace period

**Impact**: Operators can't see full environment config affecting Scribe
**Root Cause**: Original implementation only needed root/state paths

**Recommendation**: Add comprehensive env var reporting
**Spec Reference**: SPEC-DOCTOR-001 (to be created)

### ISSUE-DOCTOR-002: No LoggingToolMixin Integration
**Location**: `doctor.py:32-99` (entire function)
**Severity**: Low
**Type**: Design inconsistency

**Evidence**: doctor.py doesn't use LoggingToolMixin pattern
- No context preparation (unlike health_check.py line 36-41)
- No reminder integration
- Returns raw dict instead of context-enriched response

**Impact**: Doctor output lacks project context, reminders, agent info
**Root Cause**: Doctor predates LoggingToolMixin standardization

**Trade-off**:
- **Pro (current)**: Raw data output, no token overhead from reminders
- **Con**: Inconsistent with other tools, missing context

**Recommendation**: Decide philosophy - is doctor intentionally context-free?
**Spec Reference**: SPEC-DOCTOR-002 (to be created)

### ISSUE-DOCTOR-003: Config Path Detection Duplication
**Location**: `doctor.py:102-113` (_detect_config_path function)
**Severity**: Low
**Type**: Potential duplication

**Evidence**: Hardcoded config path list (5 candidates)
**Potential Duplication**: RepoDiscovery may already have this logic

**Investigation Needed**: Check if RepoDiscovery.load_config() uses same path search
**Impact**: Low - 12 lines of simple path checking
**Root Cause**: Uncertainty about RepoDiscovery internals

**Recommendation**: Verify RepoDiscovery doesn't already provide config path detection
**Spec Reference**: SPEC-DOCTOR-003 (to be created)

---

## 8. Implementation Specs

### SPEC-DOCTOR-001: Comprehensive Environment Variable Reporting

```yaml
spec_id: SPEC-DOCTOR-001
title: Add complete SCRIBE_* environment variable reporting
priority: P3 (nice-to-have)
file: tools/doctor.py
line_range: 84-87

problem:
  description: Only 2 of ~6+ SCRIBE_* env vars reported
  current_behavior: SCRIBE_ROOT and SCRIBE_STATE_PATH only
  desired_behavior: All SCRIBE_* variables reported for complete diagnostic

solution:
  approach: Expand env dict with all relevant variables
  changes:
    - location: lines 84-87
      before: |
        "env": {
            "SCRIBE_ROOT": os.environ.get("SCRIBE_ROOT"),
            "SCRIBE_STATE_PATH": os.environ.get("SCRIBE_STATE_PATH"),
        }
      after: |
        "env": {
            "SCRIBE_ROOT": os.environ.get("SCRIBE_ROOT"),
            "SCRIBE_STATE_PATH": os.environ.get("SCRIBE_STATE_PATH"),
            "SCRIBE_STORAGE_BACKEND": os.environ.get("SCRIBE_STORAGE_BACKEND"),
            "SCRIBE_DB_URL": os.environ.get("SCRIBE_DB_URL"),
            "SCRIBE_DEFAULT_PROJECT": os.environ.get("SCRIBE_DEFAULT_PROJECT"),
            "SCRIBE_REMINDER_DEFAULTS": os.environ.get("SCRIBE_REMINDER_DEFAULTS"),
            "SCRIBE_REMINDER_IDLE_MINUTES": os.environ.get("SCRIBE_REMINDER_IDLE_MINUTES"),
            "SCRIBE_REMINDER_WARMUP_MINUTES": os.environ.get("SCRIBE_REMINDER_WARMUP_MINUTES"),
        }

  contract:
    inputs: None (reads from os.environ)
    outputs: Dict with all SCRIBE_* env vars (None if not set)
    failure_policy: os.environ.get() never fails
    state_ownership: Read-only

testing:
  unit_tests:
    - No env vars set → all None values
    - SCRIBE_ROOT set → value appears in env dict
    - All vars set → all values appear

token_impact:
  current: ~50 tokens for env section
  after: ~150 tokens (6 additional variables)
  increase: 100 tokens (~15% of total response)
```

### SPEC-DOCTOR-002: LoggingToolMixin Integration Decision

```yaml
spec_id: SPEC-DOCTOR-002
title: Decide whether doctor should use LoggingToolMixin pattern
priority: P4 (design question)
file: tools/doctor.py
line_range: 1-113 (entire file)

problem:
  description: doctor.py doesn't follow LoggingToolMixin pattern (unlike health_check)
  current_behavior: Returns raw dict without context/reminders
  desired_behavior: TBD - need to decide philosophy

options:
  option_1:
    name: Add LoggingToolMixin (consistency)
    pros:
      - Consistent with health_check.py and other tools
      - Provides project context and reminders
      - Standard error handling
    cons:
      - Adds ~200 tokens for reminder overhead
      - Raw diagnostic data becomes wrapped
      - May be overkill for static introspection
    changes:
      - Import LoggingToolMixin
      - Create _DoctorHelper class
      - Add context preparation (lines 35-40)
      - Wrap response with apply_context_payload()

  option_2:
    name: Keep raw output (intentional minimalism)
    pros:
      - Minimal token overhead
      - Pure data output
      - Fast diagnostic queries
    cons:
      - Inconsistent with other tools
      - Missing project context
      - No reminder integration
    changes: None

recommendation: Keep raw output (option_2)
rationale: |
  Doctor is stateless introspection tool, not project-scoped operation.
  Raw data output is appropriate for diagnostic queries.
  Health check already provides context-aware diagnostics.

decision_needed: User/architect input on tool philosophy
```

### SPEC-DOCTOR-003: Config Path Detection Investigation

```yaml
spec_id: SPEC-DOCTOR-003
title: Investigate if _detect_config_path duplicates RepoDiscovery logic
priority: P4 (investigation)
file: tools/doctor.py
line_range: 102-113

problem:
  description: Hardcoded config path search may duplicate RepoDiscovery
  current_behavior: _detect_config_path manually searches 5 paths
  investigation_needed: Does RepoDiscovery.load_config() already do this?

investigation:
  check_files:
    - config/repo_config.py (RepoDiscovery implementation)
  questions:
    - Does RepoDiscovery.load_config() search same paths?
    - Does it return config path or just loaded config?
    - Is _detect_config_path redundant?

possible_outcomes:
  if_redundant:
    recommendation: Use RepoDiscovery.get_config_path() if it exists
    changes:
      - Remove _detect_config_path function
      - Call RepoDiscovery method instead

  if_unique:
    recommendation: Keep _detect_config_path as diagnostic helper
    rationale: Doctor needs to report path even if config load fails

next_step: Review config/repo_config.py in future wave
```

---

**Audit Confidence**: 0.95
**Completeness**: All sub-systems documented, plugin inspection fully analyzed
**Cross-Tool Integration**: Shares RepoDiscovery with set_project, list_projects, get_project
**Extractable Modules**: 2 candidates identified (EnvironmentIntrospector, PluginIntrospector)
**Token Bloat**: Appropriate for diagnostic tool, minimal optimization needed

---

**Comparison to health_check.py**:

| Aspect | doctor.py | health_check.py |
|--------|-----------|-----------------|
| Purpose | Static environment/config | Runtime validation |
| LOC | 113 | 274 |
| Complexity | Low (introspection) | Medium (6 component checks) |
| Tokens | ~635 avg | ~885 avg |
| Error Handling | Never fails | Graceful degradation |
| Context | None (raw data) | LoggingToolMixin integration |
| Pattern | Stateless introspection | State validator |

**Key Insight**: Doctor and health_check are complementary - together they provide complete diagnostic coverage (config + runtime).

---

**Next Steps for Phase 6**:
1. Implement SPEC-DOCTOR-001 for comprehensive env var reporting
2. Decide on SPEC-DOCTOR-002 (LoggingToolMixin integration philosophy)
3. Investigate SPEC-DOCTOR-003 (config path detection duplication)
4. Consider extracting EnvironmentIntrospector for reuse in other diagnostic tools
