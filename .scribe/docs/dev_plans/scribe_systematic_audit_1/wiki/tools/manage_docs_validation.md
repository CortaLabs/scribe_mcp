# manage_docs_validation.py - Forensic Audit Report

**File**: `tools/manage_docs_validation.py`
**Size**: 287 LOC | 10,223 bytes
**Complexity**: Low (Test Infrastructure)
**Auditor**: ResearchAgent-K-AdvancedFeatures
**Date**: 2026-01-05

---

## 1. Overview

`manage_docs_validation.py` is a **test infrastructure module** that provides backwards-compatible validation helpers for manage_docs enhancement tests. It intentionally exports symbols to Python builtins namespace for legacy test compatibility.

**Purpose**: Provide stable validation surface area for tests while maintaining backwards compatibility with test modules that reference symbols without importing.

**LOC Breakdown**:
- Validation helpers: ~147 LOC (51%) - EnhancedManageDocsValidator class
- Input validation function: ~115 LOC (40%) - _validate_inputs
- Comparison operator detection: ~8 LOC (3%) - _validate_comparison_symbols
- Backwards compatibility shim: ~9 LOC (3%) - _register_test_globals
- Constants and exceptions: ~8 LOC (3%)

**Architectural Pattern**: **Test Support Library**
- Not used in production code paths
- Minimal validation logic (frozen dataclass)
- Global namespace injection for backwards compatibility (lines 278-288)

**Relationships**:
- **Used by**: Test modules (`tests/test_manage_docs_*.py`)
- **Depends on**: `doc_management/manager.py` (DocumentValidationError)
- **Imported by**: Tests that reference ParameterValidationError without explicit import

**Complexity Drivers**:
1. **Backwards compatibility** - Injects symbols into builtins namespace (lines 278-288)
2. **Security validation** - Comparison operator detection (lines 20, 23-27, 138-144, 266-275)
3. **Minimal validator** - Intentionally simple for test stability

---

## 2. Sub-System Breakdown

### Sub-System 1: Comparison Operator Detection (Lines 20-27)

**Responsibility**: Detect numeric comparison operators in user-provided strings to prevent injection.

**Constants**:
- `COMPARISON_REGEX` (line 20): `r"\b\d+(?:\.\d+)?\s*(?:<=|>=|<|>)\s*\d+(?:\.\d+)?\b"`

**Function**: `_validate_comparison_symbols(text: str)` (23-27)

**Algorithm**:
1. Check if text is string (line 25)
2. Search for comparison pattern (line 27)
3. Return False if found, True otherwise

**Pattern Matched**: Numeric comparisons like "5 > 3", "10.5 <= 20", "3>=2"

**Security Rationale**: Prevents user input that could be misinterpreted as code/logic

**Extractable**: YES [BUCKET:validation]
- Evidence: Lines 20-27 are pure regex validation, used in multiple contexts
- Used by: _validate_inputs (lines 266-275), EnhancedManageDocsValidator (lines 138-144)
- Potential users: Other tools accepting user-provided content
- Before/After: Before = duplicated in multiple validators. After = `SecurityValidator.check_comparison_operators(text)`
- Contract:
  - **Input**: text (string)
  - **Output**: bool (True = safe, False = contains comparison operators)
  - **Failure Policy**: Return True for non-strings (safe default)
  - **State Owner**: None (pure function)

**Risk Assessment**: Low
- Single regex pattern, well-defined
- No dependencies on manage_docs specifics
- Clear security purpose

---

### Sub-System 2: ParameterValidationError Exception (Lines 30-53)

**Responsibility**: Custom exception for manage_docs parameter validation failures.

**Class**: `ParameterValidationError(Exception)` (30-53)

**Attributes**:
- `tool_name`: Tool that raised error (default: "manage_docs")
- `param_name`: Parameter that failed validation (optional)
- `suggestion`: Actionable suggestion for user (optional)

**String Representation** (Lines 46-53):
- Format: `[tool_name] message | Parameter: param_name | Suggestion: suggestion`
- Provides structured error output for debugging

**Extractable**: YES [BUCKET:validation]
- Evidence: Lines 30-53 are generic validation exception, not manage_docs-specific
- Used by: EnhancedManageDocsValidator, _validate_inputs
- Potential users: Any tool with parameter validation
- Before/After: Before = manage_docs-specific. After = `ParameterValidationError` in `utils/validation.py`
- Contract:
  - **Input**: message, param_name, suggestion, tool_name
  - **Output**: Formatted exception with structured error details
  - **Failure Policy**: N/A (exception class)
  - **State Owner**: None (immutable exception)

---

### Sub-System 3: EnhancedManageDocsValidator Class (Lines 56-165)

**Responsibility**: Minimal validator implementation used by tests.

**Class**: `EnhancedManageDocsValidator` (56-165) - Frozen dataclass

**Methods**:
1. `create_validation_error()` (62-74) - Factory for ParameterValidationError
2. `validate_string_param()` (76-103) - String validation with length constraints
3. `validate_enum_param()` (105-119) - Enum value validation
4. `validate_metadata()` (121-135) - Dict validation with string keys requirement
5. `validate_comparison_operators()` (137-144) - Wrapper for _validate_comparison_symbols
6. `validate_list_param()` (146-165) - List validation with max items constraint

**Design Philosophy**: **Minimal and Stable**
- Frozen dataclass (immutable)
- No complex logic
- Clear error messages with suggestions
- Used by tests, not production code

**Validation Methods Summary**:

| Method | Validates | Required Checks | Optional Checks |
|--------|-----------|-----------------|-----------------|
| validate_string_param | String type | Type, min length | Max length |
| validate_enum_param | Enum membership | Value in allowed set | - |
| validate_metadata | Dict structure | Type, string keys only | - |
| validate_comparison_operators | Security | No numeric comparisons | - |
| validate_list_param | List structure | Type | Max items |

**Extractable**: YES [BUCKET:validation]
- Evidence: Lines 56-165 implement generic validation patterns
- Used by: Tests, _validate_inputs
- Potential users: Any tool with parameter validation needs
- Before/After: Before = manage_docs-specific test validator. After = `ParameterValidator` base class in `utils/validation.py`
- Contract:
  - **Input**: Parameter values to validate
  - **Output**: Validated value or raise ParameterValidationError
  - **Failure Policy**: Raise exception with actionable suggestion
  - **State Owner**: None (stateless validator, frozen dataclass)

**Risk Assessment**: Low
- Intentionally simple for test stability
- No dependencies on manage_docs internals
- Clear validation contracts

---

### Sub-System 4: Validator Factory (Lines 168-169)

**Responsibility**: Create EnhancedManageDocsValidator instance.

**Function**: `create_manage_docs_validator()` (168-169)

**Purpose**: Factory pattern for test instantiation

**Extractable**: NO - Trivial factory, only 2 LOC

---

### Sub-System 5: Comprehensive Input Validation (Lines 172-276)

**Responsibility**: Strict manage_docs validation used by enhancement tests.

**Function**: `_validate_inputs()` (172-276)

**Parameters** (11 total):
- `doc`: Document key
- `action`: Action type
- `section`: Section identifier
- `content`: Content to insert
- `patch`: Patch content
- `patch_source_hash`: Hash for verification
- `edit`: Edit payload dict
- `patch_mode`: Patch mode (structured/unified)
- `start_line` / `end_line`: Line range
- `template`: Template content
- `metadata`: Additional metadata

**Validation Workflow**:
1. Lazy import DocumentValidationError (lines 195-196) **CRITICAL: Avoids circular imports**
2. Create validator instance (line 198)
3. Validate doc and action parameters (lines 200-201)
4. Check action in allowed set (lines 203-223)
5. Action-specific validation (lines 225-263):
   - `replace_section`: Requires section (226-227)
   - `status_update`: Requires metadata (229-232)
   - `apply_patch`: Requires patch_mode and edit (234-244)
   - `replace_range`: Requires start_line and end_line (246-248)
   - `replace_text`: Requires metadata.find (250-255)
   - `create_doc`: Requires metadata (257-259)
   - `validate_crosslinks`: Validates metadata if present (261-263)
6. Validate comparison operators in content/template (lines 266-270)
7. Validate comparison operators in metadata values (lines 272-275)

**Allowed Actions** (Lines 203-221):
```python
allowed_actions = {
    "replace_section", "append", "status_update", "list_sections",
    "list_checklist_items", "batch", "apply_patch", "replace_range",
    "replace_text", "normalize_headers", "generate_toc", "create_doc",
    "validate_crosslinks", "create_research_doc", "create_bug_report",
    "create_review_report", "create_agent_report_card"
}
```

**Security Checks** (Lines 266-275):
- Validates content for comparison operators (lines 266-268)
- Validates template for comparison operators (lines 269-270)
- Validates all metadata values for comparison operators (lines 272-275)

**Extractable**: MAYBE [BUCKET:validation]
- Evidence: Lines 172-276 implement manage_docs contract validation
- Used by: Tests (via builtins namespace)
- Potential users: Production manage_docs (if contract enforcement needed)
- Before/After: Before = test-only validation. After = Shared validation in doc_management/validation.py
- Risk: High coupling to manage_docs action types (lines 203-221)
- Unification strategy: Extract action-agnostic validation patterns, keep action-specific logic in manage_docs

**Assessment**: **KEEP AS TEST INFRASTRUCTURE**
- Rationale: Hardcoded to test expectations, may diverge from production
- Production path: Use DocumentValidationError in doc_management/manager.py (line 195)
- Test path: Use ParameterValidationError in this module

---

### Sub-System 6: Backwards Compatibility Shim (Lines 278-288)

**Responsibility**: Inject validation symbols into Python builtins namespace for legacy test compatibility.

**Function**: `_register_test_globals()` (279-286)
**Invocation**: Line 288 (module-level call)

**Injected Symbols**:
1. `builtins.ParameterValidationError` (line 282)
2. `builtins._validate_inputs` (line 283)
3. `builtins._validate_comparison_symbols` (line 284)
4. `builtins.create_manage_docs_validator` (line 285)

**Rationale**: Tests reference these symbols without importing
- Legacy tests may have: `if ParameterValidationError:`
- Without imports, would raise NameError
- Injecting into builtins makes symbols globally available

**Extractable**: NO - **INTENTIONAL TEST HACK**
- Reason: Backwards compatibility shim for legacy tests
- Evidence: Module docstring explicitly states this purpose (lines 1-11)
- Before/After: N/A - This is temporary migration support
- Alternative: Update all tests to import symbols explicitly
- Why Not Done: Preserves test backwards compatibility during refactoring

**Risk**: Medium
- Pollutes global namespace
- Makes tests harder to understand (symbols appear from nowhere)
- Fragile if builtins change

**Mitigation**:
- Document clearly (done in lines 1-11)
- Plan removal after test migration
- Keep injection minimal (only 4 symbols)

---

## 3. Modularization Notes

### Test Infrastructure Assessment

**Conclusion**: manage_docs_validation.py is **INTENTIONAL TEST INFRASTRUCTURE** with extractable validation patterns.

**Evidence**:
1. **Module docstring** (lines 1-11): "expected by manage_docs enhancement tests"
2. **Builtins injection** (lines 278-288): Backwards compatibility for tests
3. **Minimal validator** (lines 56-165): "small, stable surface area used by tests"
4. **Not imported by production code**: Only used in tests/ directory

**What SHOULD Be Extracted**:

1. **Comparison Operator Validation** [BUCKET:validation]
   - Lines 20-27 (_validate_comparison_symbols)
   - Security-focused, reusable across tools
   - Extract to `utils/security_validation.py`

2. **ParameterValidationError Exception** [BUCKET:validation]
   - Lines 30-53 (custom exception class)
   - Generic validation exception, not test-specific
   - Extract to `utils/validation.py`

3. **Validation Method Patterns** [BUCKET:validation]
   - Lines 76-165 (EnhancedManageDocsValidator methods)
   - Patterns reusable (string validation, enum validation, etc.)
   - Extract base class `ParameterValidator` to `utils/validation.py`

**What Should STAY as Test Infrastructure**:
- `_validate_inputs()` (lines 172-276) - Test-specific contract validation
- `_register_test_globals()` (lines 278-288) - Backwards compatibility shim
- `create_manage_docs_validator()` (lines 168-169) - Test factory

**Migration Path**:
1. Extract validation patterns to `utils/validation.py`
2. Update production code to use extracted validators
3. Update tests to import symbols explicitly (remove builtins injection)
4. Archive manage_docs_validation.py as legacy test support
5. Timing: Post Phase 6, during test modernization

---

## 4. Implicit Contracts

### Contract 1: Test Module Import Expectations

**Assumption**: Tests reference symbols without explicit imports

**Evidence**: Lines 278-286 inject into builtins namespace

**Risk**: Tests break if injection removed
**Mitigation**: Gradual migration to explicit imports

### Contract 2: DocumentValidationError Availability

**Assumption**: `doc_management.manager.DocumentValidationError` exists and is importable

**Evidence**: Line 195 lazy import

**Risk**: If DocumentValidationError moved or renamed, _validate_inputs breaks
**Mitigation**: Keep DocumentValidationError stable, version interface

### Contract 3: Comparison Operator Pattern Stability

**Assumption**: COMPARISON_REGEX pattern (line 20) catches security violations

**Evidence**: Used in lines 27, 138-144, 266-275

**Risk**: Pattern may have false positives/negatives
**Validation Needed**: Security review of regex pattern

**Test Coverage Needed**:
- Edge cases: "3.14159 > 2.71828"
- False positives: "Using > character in text"
- Bypass attempts: "5 &gt; 3" (HTML entities)

### Contract 4: Allowed Actions List Completeness

**Assumption**: Lines 203-221 list contains ALL valid manage_docs actions

**Evidence**: Line 222-223 raises DocumentValidationError if action not in set

**Risk**: If production manage_docs adds new action, tests will fail
**Mitigation**: Keep allowed_actions in sync with production action types

---

## 5. Token Analysis

### Token Impact: ZERO

**Rationale**: This module is **TEST INFRASTRUCTURE ONLY**, not used in production code paths.

**Usage Pattern**:
- Imported by: `tests/test_manage_docs_*.py`
- Invoked during: pytest test execution
- Not invoked by: MCP tools, production code

**Actual Token Producers**:
- `tools/manage_docs.py` - Uses DocumentValidationError (production validation)
- Tests have no token impact (not user-facing)

**Category**: N/A - Test support infrastructure

---

## 6. Error Handling Architecture

### Policy 1: Raise on Validation Failure

**Location**: All validate_* methods (lines 76-165), _validate_inputs (lines 172-276)
**Behavior**: Raise ParameterValidationError or DocumentValidationError on validation failure
**Classification**: **POLICY** (test contract enforcement)

**Rationale**:
- Tests expect exceptions on invalid inputs
- Fail-fast validation for test reliability
- Clear error messages guide test debugging

**Evidence**:
- Line 86-90: Raise if not string
- Line 91-96: Raise if length < min_length
- Line 97-102: Raise if length > max_length
- Pattern repeated in all validators

### Policy 2: Safe Defaults for Non-Critical Checks

**Location**: Line 25-26 (_validate_comparison_symbols)
**Behavior**: Return True for non-strings (safe default)
**Classification**: **POLICY** (defensive programming)

**Rationale**:
- Comparison operator check only meaningful for strings
- Non-string inputs can't contain text patterns
- Avoid false positives

**Evidence**:
```python
if not isinstance(text, str):
    return True  # Safe default for non-strings
```

### Bug vs Policy Classification

**No bugs identified** in error handling. All exception raising is intentional test contract enforcement.

**Design Validation**: Exception handling matches test expectations
- Tests expect ParameterValidationError with structured error details
- Tests rely on fail-fast validation
- Error messages guide test debugging

---

## 7. Known Issues

### ISSUE-VAL-001: Comparison Regex May Have False Positives

**Severity**: Low (Security Validation)
**Location**: Line 20 (COMPARISON_REGEX pattern)

**Description**: Regex pattern may match benign text like "Chapter 5 > Section 3" or "Version 2.0 >= 1.5 required".

**Evidence**:
```python
COMPARISON_REGEX = re.compile(r"\b\d+(?:\.\d+)?\s*(?:<=|>=|<|>)\s*\d+(?:\.\d+)?\b")
```

**Pattern Matches**:
- "5 > 3" ✓ (intended)
- "10.5 <= 20" ✓ (intended)
- "Chapter 5 > Section 3" ✓ (FALSE POSITIVE)
- "Version 2.0 >= 1.5 required" ✓ (FALSE POSITIVE)

**Impact**:
- Rejects valid user input in edge cases
- Forces users to rephrase benign text
- May cause confusion ("why can't I mention version requirements?")

**Recommendation**: Context-aware validation
```python
def _is_likely_code_comparison(text: str) -> bool:
    """
    Check if comparison appears in code context.
    Heuristics:
    - Surrounded by operators/keywords (if, while, etc.)
    - Part of expression (parentheses, semicolons)
    - Not part of prose (preceded by article/noun)
    """
    # More sophisticated pattern matching
    ...
```

**Not Critical Because**:
- Edge case (rare in manage_docs content)
- Security-first approach justified (better false positive than injection)
- Easy workaround (rephrase text)

---

### ISSUE-VAL-002: Builtins Injection is Fragile

**Severity**: Medium (Test Maintainability)
**Location**: Lines 278-288 (_register_test_globals, module-level call)

**Description**: Injecting symbols into builtins namespace is fragile and makes tests harder to understand.

**Evidence**:
```python
def _register_test_globals() -> None:
    import builtins
    builtins.ParameterValidationError = ParameterValidationError  # type: ignore
    builtins._validate_inputs = _validate_inputs  # type: ignore
    ...
```

**Impact**:
- Tests reference symbols without visible imports
- Hard to trace where symbols come from
- Pollutes global namespace
- Breaks if builtins change

**Recommendation**: Migrate tests to explicit imports
```python
# In test files, replace:
if ParameterValidationError:  # Symbol from nowhere

# With explicit import:
from scribe_mcp.tools.manage_docs_validation import ParameterValidationError
```

**Migration Plan**:
1. Add explicit imports to all test files
2. Remove builtins injection (lines 278-288)
3. Verify all tests still pass
4. Update documentation

**Risk Level**: Medium - Affects test maintainability, not production
**Timing**: Phase 6 test modernization

---

### ISSUE-VAL-003: Allowed Actions Hardcoded in Test Module

**Severity**: Low (Maintenance Burden)
**Location**: Lines 203-221 (allowed_actions set)

**Description**: Test validation has hardcoded list of allowed actions that may diverge from production manage_docs.

**Evidence**:
```python
allowed_actions = {
    "replace_section", "append", "status_update", ...
}
```

**Impact**:
- Tests fail if production adds new action
- Duplicate action list (also in manage_docs.py)
- Synchronization maintenance burden

**Recommendation**: Import allowed actions from production
```python
# In manage_docs.py
ALLOWED_ACTIONS = frozenset([...])

# In manage_docs_validation.py
from scribe_mcp.tools.manage_docs import ALLOWED_ACTIONS
allowed_actions = ALLOWED_ACTIONS
```

**Not Critical Because**: Test-only impact, easy to sync manually

---

## 8. Implementation Specs

### SPEC-VAL-001: Extract Validation Utilities to Shared Module

**Priority**: Medium
**Bucket**: [BUCKET:validation]
**Estimated Impact**: Medium (enables reuse across tools)

**Motivation**: Validation patterns in this module are generic and reusable across multiple tools.

**Module Contract**:
```yaml
name: ParameterValidator
location: utils/validation.py
bucket: validation

interface:
  ParameterValidationError:
    type: Exception
    attributes:
      - tool_name: str
      - param_name: Optional[str]
      - suggestion: Optional[str]
    methods:
      - __str__(): str  # Formatted error message

  SecurityValidator:
    methods:
      check_comparison_operators:
        inputs:
          - text: str
        outputs:
          - is_safe: bool
        description: "Detect numeric comparison operators in user input"

  ParameterValidator:
    methods:
      validate_string:
        inputs:
          - value: Any
          - param_name: str
          - required: bool = True
          - min_length: int = 1
          - max_length: Optional[int] = None
        outputs:
          - validated: str
        raises: ParameterValidationError

      validate_enum:
        inputs:
          - value: Any
          - param_name: str
          - allowed_values: Iterable[str]
        outputs:
          - validated: str
        raises: ParameterValidationError

      validate_metadata:
        inputs:
          - value: Any
          - param_name: str = "metadata"
        outputs:
          - validated: Dict[str, Any]
        raises: ParameterValidationError

      validate_list:
        inputs:
          - value: Any
          - param_name: str
          - max_items: Optional[int] = None
        outputs:
          - validated: List[Any]
        raises: ParameterValidationError

usage_example: |
  from scribe_mcp.utils.validation import ParameterValidator, ParameterValidationError

  validator = ParameterValidator(tool_name="my_tool")

  try:
      action = validator.validate_enum(
          user_input,
          param_name="action",
          allowed_values=["create", "update", "delete"]
      )
  except ParameterValidationError as e:
      return {"ok": False, "error": str(e)}

migration_plan:
  1. Create utils/validation.py with extracted classes
  2. Update manage_docs_validation.py to inherit from ParameterValidator
  3. Update production tools to use shared validation
  4. Add security validator tests (regex pattern validation)
  5. Update tests to import from utils/validation.py
  6. Remove builtins injection (ISSUE-VAL-002)

affected_files:
  - tools/manage_docs_validation.py (refactor to use shared base)
  - tools/manage_docs.py (production validation)
  - tools/append_entry.py (parameter validation)
  - tools/query_entries.py (filter validation)
  - tests/test_*.py (update imports)

testing_requirements:
  - Unit tests for each validation method
  - Security tests for comparison operator detection
  - Edge case tests (false positives, unicode, etc.)
  - Integration tests with manage_docs

risks:
  - Comparison regex may need refinement (ISSUE-VAL-001)
  - Tests may have implicit dependencies on current behavior
  - Migration requires updating many test files

mitigation:
  - Comprehensive test coverage before extraction
  - Feature flag for gradual rollout
  - Security review of regex pattern
```

**Timing**: Phase 6, during validation framework unification

---

### SPEC-VAL-002: Remove Builtins Injection and Modernize Tests

**Priority**: Low (Test Quality)
**Bucket**: [BUCKET:test_modernization]
**Estimated Impact**: Low (test maintainability improvement)

**Motivation**: Builtins injection makes tests harder to understand and maintain. Explicit imports are clearer.

**Implementation**:
```yaml
name: Test Import Modernization
location: tests/test_manage_docs_*.py, tools/manage_docs_validation.py
bucket: test_modernization

preconditions:
  - SPEC-VAL-001 complete (validation utils extracted)
  - All tests have explicit imports added

changes:
  - location: tools/manage_docs_validation.py
    action: remove_builtins_injection
    remove_lines: [278-288]
    remove_function: _register_test_globals

  - location: tests/test_*.py
    action: add_explicit_imports
    add_imports: |
      from scribe_mcp.utils.validation import (
          ParameterValidationError,
          ParameterValidator,
          SecurityValidator
      )

  - location: tools/manage_docs_validation.py
    action: update_module_docstring
    new_docstring: |
      """Validation helpers for manage_docs tests.

      This module provides backwards-compatible validation for legacy tests.
      New tests should import from utils.validation instead.

      Deprecated: This module will be removed in future version.
      Use scribe_mcp.utils.validation for new code.
      """

migration_steps:
  1. Add explicit imports to all test files
  2. Run full test suite to verify no breakage
  3. Remove _register_test_globals() and call
  4. Run tests again to verify explicit imports work
  5. Add deprecation warning to module docstring
  6. Schedule module removal for next major version

testing:
  - Run full pytest suite before and after changes
  - Verify no import errors
  - Verify all validation behavior unchanged

risks:
  - Some tests may have hidden dependencies on builtins injection
  - May reveal undiscovered test coupling

mitigation:
  - Gradual rollout (add imports first, remove injection later)
  - Comprehensive test coverage
  - Rollback plan if issues discovered
```

**Timing**: Phase 6 test modernization, after SPEC-VAL-001

---

**End of manage_docs_validation.py Audit**

**Summary**:
- Architecture: Test infrastructure module with extractable validation patterns
- Extractable modules: 3 (comparison operator validation, ParameterValidationError, validator base class)
- Known issues: 3 (false positive regex, builtins injection fragility, hardcoded action list)
- Token profile: N/A (test infrastructure, not production code)
- Error handling: All intentional test contract enforcement
- Recommendation: **Extract validation patterns (SPEC-VAL-001), remove builtins injection (SPEC-VAL-002), keep as test infrastructure temporarily**
- Future state: Deprecated after validation framework unified and tests modernized
