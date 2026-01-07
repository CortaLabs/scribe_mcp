# Base Infrastructure: Parameter Normalizer

**File**: `tools/base/parameter_normalizer.py`
**LOC**: 163
**Complexity**: Low (pure utility functions)
**Relationships**: Used by tools handling MCP client parameters (dict/list serialization)

---

## 1. Overview

Parameter normalizer provides **MCP JSON deserialization healing**. The MCP framework serializes Python dicts and lists as JSON strings when passing parameters from external clients. This module provides robust parsing to handle both native Python types AND JSON-serialized strings.

**Purpose**: Solve the MCP parameter serialization problem:
- MCP client sends `{"meta": {"key": "value"}}` → MCP framework serializes → tool receives `'{"key": "value"}'`
- Without healing: Tool receives string, tries to use as dict → fails
- With healing: `normalize_dict_param()` detects string, parses JSON, returns dict

**Key Pattern**: Similar to `append_entry.py` metadata normalization (proven pattern from Wave 1)

---

## 2. Sub-System Breakdown

### 2.1 Dict Parameter Normalization (Lines 13-80)
**Responsibility**: Heal dict parameters from MCP JSON serialization
**Contract**: `normalize_dict_param(param, param_name) -> Optional[Dict[str, Any]]`

**Input handling priority**:
1. `None` or empty → return `None`
2. Already dict → return as-is
3. JSON string → parse with `json.loads()`
4. Legacy CLI format `"key=value,key2=value2"` → parse as dict
5. Invalid type → raise `ValueError`

**Legacy CLI support** (lines 56-75):
- Detects `=` in string (not valid JSON)
- Tries comma-separated: `"key=value,key2=value2"`
- Tries space-separated: `"key=value key2=value2"`
- Falls back to `{"message": value}` if no equals sign

**Example transformations**:
```python
normalize_dict_param({"key": "value"})  # → {"key": "value"}
normalize_dict_param('{"key": "value"}')  # → {"key": "value"}
normalize_dict_param("key=value,key2=value2")  # → {"key": "value", "key2": "value2"}
normalize_dict_param(None)  # → None
```

### 2.2 List Parameter Normalization (Lines 83-116)
**Responsibility**: Heal list parameters from MCP JSON serialization
**Contract**: `normalize_list_param(param, param_name) -> Optional[List[Any]]`

**Input handling priority**:
1. `None` or empty → return `None`
2. Already list → return as-is
3. JSON string → parse with `json.loads()`
4. Invalid type → raise `ValueError`

**Simpler than dict normalization**: No legacy CLI support (lists don't have `key=value` format)

**Example transformations**:
```python
normalize_list_param(["a", "b"])  # → ["a", "b"]
normalize_list_param('["a", "b"]')  # → ["a", "b"]
normalize_list_param(None)  # → None
```

### 2.3 Safe Nested Access (Lines 119-140)
**Responsibility**: Get nested dict values without KeyError
**Contract**: `safe_get_nested(data, *keys, default=None) -> Any`

**Usage pattern**:
```python
config = {"server": {"port": 8080}}
port = safe_get_nested(config, "server", "port", default=3000)  # → 8080
missing = safe_get_nested(config, "server", "host", default="localhost")  # → "localhost"
```

**Why this exists**: Avoid `config.get("server", {}).get("port", 3000)` pyramid of doom

### 2.4 Type Validation (Lines 143-163)
**Responsibility**: Validate parameter types match expected types
**Contract**: `validate_param_types(params_dict, expected_types) -> Dict[str, str]`

**Returns**: Dict of validation errors (empty if all valid)

**Example**:
```python
params = {"page": "5", "compact": True}
expected = {"page": int, "compact": bool}
errors = validate_param_types(params, expected)
# → {"page": "Expected int, got str"}
```

**Usage**: Pre-flight validation before processing parameters

---

## 3. Modularization Notes

### Already Extracted (Good Architecture)
**This IS the extracted module**: Parameter normalization was previously embedded in individual tools (see Wave 1: append_entry had inline metadata parsing). Creating this module was the RIGHT move.

### Unification Opportunity [BUCKET:config]
**Related code**: `logging_utils.py:269-477` (metadata normalization)
**Overlap**:
- Both normalize dict-like inputs
- Both support JSON strings
- Both support legacy `key=value` formats
- Both have `_try_parse_json_like()` helpers

**Unification potential**:
```
Before:
- tools/base/parameter_normalizer.py: normalize_dict_param() for MCP params
- shared/logging_utils.py: coerce_metadata_mapping() for metadata payloads

After:
- utils/parameter_healer.py:
  - normalize_dict_param() (MCP deserialization)
  - normalize_list_param() (MCP deserialization)
  - coerce_metadata_mapping() (metadata healing)
  - normalize_metadata() (tuple format for file writes)
  - clean_list() (deduplication)
```

**Benefit**: Single source of truth for parameter healing across ALL contexts

### NOT Extractable
None—all functions are pure utilities with no side effects.

---

## 4. Implicit Contracts

### Contract 1: JSON Parsing Never Fails (Controlled Failure)
**Assumption**: `normalize_dict_param()` either returns dict OR raises `ValueError`
**Violation consequence**: Tools expect exception, not None/garbage
**Why this matters**: Callers wrap in try-except for error handling

### Contract 2: Legacy CLI Support is Permanent
**Assumption**: `"key=value,key2=value2"` format must be supported forever
**Violation consequence**: CLI users break if legacy support removed
**Why this is risky**: No deprecation path—legacy format is permanent contract

### Contract 3: None Means "Not Provided"
**Assumption**: `normalize_dict_param(None)` returns `None` (not empty dict)
**Violation consequence**: Tools distinguish "not provided" vs "empty dict"
**Why this matters**: Semantic difference between optional param omitted vs param={}

### Contract 4: Type Validation is Non-Blocking
**Assumption**: `validate_param_types()` returns errors but doesn't raise
**Violation consequence**: Callers decide whether to proceed with type mismatches
**Why this is flexible**: Allows graceful degradation (e.g., coerce "5" → 5)

---

## 5. Token Analysis

**Direct output**: 0 tokens (utilities don't produce output)
**Indirect impact**: Enables healing, prevents parameter errors

**Optimization**: N/A (pure utilities, no token costs)

---

## 6. Error Handling Architecture

### Policy: Raise on Invalid Input
**Locations**: Lines 53, 77, 114
**Pattern**: Raise `ValueError` with descriptive message
**Why intentional**: Callers MUST handle invalid parameters explicitly

**Examples**:
- `ValueError: metadata parameter is not valid JSON`
- `ValueError: Could not parse metadata parameter as key=value pairs`
- `ValueError: items parameter has unsupported type: int`

### Policy: None is Success
**Pattern**: `None` input → `None` output (not an error)
**Why intentional**: Distinguishes "not provided" from "invalid"

---

## 7. Known Issues

**None**—this is well-designed utility module with clear contracts.

**Potential improvement**: Merge with `logging_utils.py` metadata normalization (see Section 3).

---

## 8. Implementation Specs

### SPEC-BASE-004: Unify Parameter Healing

**Problem**: Parameter normalization logic duplicated between parameter_normalizer.py and logging_utils.py
**Location**: `tools/base/parameter_normalizer.py:13-116` + `shared/logging_utils.py:269-477`

```yaml
spec_id: SPEC-BASE-004
title: Unify parameter healing into single module
priority: P3 (code quality, not critical)
files:
  - tools/base/parameter_normalizer.py (entire file)
  - shared/logging_utils.py:269-477
  - NEW: utils/parameter_healer.py
changes:
  - action: create_module
    path: utils/parameter_healer.py
    content: |
      class ParameterHealer:
          @staticmethod
          def normalize_dict_param(param, param_name) -> Optional[Dict]:
              # Move from parameter_normalizer.py:13-80

          @staticmethod
          def normalize_list_param(param, param_name) -> Optional[List]:
              # Move from parameter_normalizer.py:83-116

          @staticmethod
          def coerce_metadata_mapping(meta, allow_pair_strings) -> Tuple[Dict, Optional[str]]:
              # Move from logging_utils.py:269-338

          @staticmethod
          def normalize_metadata(meta, allow_pair_strings) -> Tuple[Tuple[str, str], ...]:
              # Move from logging_utils.py:341-385

          @staticmethod
          def clean_list(values, coerce_lower) -> List[str]:
              # Move from logging_utils.py:443-477

  - action: update_imports
    files:
      - tools/base/parameter_normalizer.py → import from utils.parameter_healer
      - shared/logging_utils.py → import from utils.parameter_healer

benefits:
  - Single source of truth for ALL parameter healing
  - Easier to maintain (one module instead of two)
  - Consistent behavior across MCP params and metadata
  - Clear module boundary (ParameterHealer class)
risks:
  - Circular import if utils/ depends on shared/ or tools/
  - Breaking change if tools import directly from old locations
migration_strategy:
  - Create new module first
  - Keep old modules as deprecated wrappers (import + delegate)
  - Update all tools to use new module
  - Remove deprecated wrappers in next major version
test_verification:
  - "All existing parameter healing tests pass"
  - "No circular imports detected"
```

---

## Cross-Cutting Concerns

- **[BUCKET:config]** Parameter healing pattern (shared with logging_utils)
- **[BUCKET:utilities]** Pure utility functions (no side effects)
- **[BUCKET:error_handling]** Controlled failure (ValueError on invalid input)

**Impact**: Used by tools that accept dict/list parameters from MCP clients. Changes here affect parameter validation across multiple tools.

**Relationship to Wave 1**: append_entry used to have inline metadata parsing (before this module existed). Creating parameter_normalizer was extraction done RIGHT—pure utilities with clear contracts.
