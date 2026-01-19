# Deprecation Candidates - Safety Assessment

**Agent**: ResearchAgent-Phase4-LegacyCode
**Created**: 2026-01-05
**Purpose**: Safe removal assessment with risk levels for all legacy patterns

---

## Risk Level Framework

**SAFE** - Can be removed immediately with minimal impact
**CONDITIONAL** - Safe to remove after specific prerequisites met
**RISKY** - Requires careful migration planning
**CRITICAL** - Would break existing functionality, extensive testing required

---

## Category 1: sys.path Manipulation (68 Patterns)

### Risk Assessment: CONDITIONAL (Safe after src/ migration)

**Current State**: All 68 occurrences serve same purpose - enable direct script execution
**Blocking Factor**: No package installation mechanism (setup.py/pyproject.toml)
**Phase 3 Reference**: SPEC-PKG-001 proposes src/ layout migration

### Removal Prerequisites

1. ✅ **Create pyproject.toml** with editable install support
2. ✅ **Migrate to src/ layout** (Phase 3 spec ready)
3. ✅ **Update development docs** to use `pip install -e .`
4. ✅ **Update test runner** to use `pytest` (already standard)
5. ✅ **Update script invocation** to use `python -m scribe_mcp.scripts.*`

### Phased Removal Plan

**Phase 6A: Infrastructure Setup**
- Create `pyproject.toml` with `scribe_mcp` package definition
- Configure editable install: `pip install -e .`
- Verify imports work without sys.path hacks

**Phase 6B: Test Migration (60 files)**
- Remove sys.path from all test files
- Run pytest suite to verify no import errors
- Update any custom test runners

**Phase 6C: Script Migration (7 files)**
- Convert scripts to module execution: `python -m scribe_mcp.scripts.scribe`
- Remove sys.path from script files
- Update documentation and examples

**Phase 6D: Server Cleanup (1 file)**
- Remove sys.path from server.py
- Verify `python -m scribe_mcp.server` works
- Update installation docs

### Estimated Impact

**Files Modified**: 68
**Breaking Changes**: Direct script execution (`python tests/test_file.py`)
**Migration Effort**: 2-3 hours (mostly automated find/replace)
**Testing Effort**: 1-2 hours (run full test suite)
**Documentation Effort**: 1 hour (update CLAUDE.md, README)

### Blocker Dependencies

- ❌ **pyproject.toml not created** (BLOCKING)
- ❌ **src/ migration not complete** (BLOCKING - Phase 3 spec exists but not implemented)
- ✅ **pytest already standard** (READY)

**Recommendation**: DEFER until Phase 6 (after src/ migration complete)

---

## Category 2: Template Engine Legacy Fallback

### Risk Assessment: CONDITIONAL (Safe after template validation)

#### Pattern 2A: Jinja2 → {variable} Fallback

**File**: `template_engine/engine.py`
**Lines**: 48-49, 380-398, 400-458, 460-505
**Removal Prerequisites**: Verify no templates use old `{variable}` syntax

**Validation Steps**:
1. Scan all `.md` template files for `{variable}` patterns (NOT `{{ variable }}`)
2. Test all template rendering with `strict=True, fallback=False`
3. Fix any templates using old syntax
4. Remove fallback code after validation

**Risk Level**: MEDIUM
- If old templates exist and fallback removed → silent rendering failures
- If validation complete → safe to remove ~125 lines

**Validation Command**:
```bash
# Find templates using old {variable} syntax (not Jinja2 {{ variable }})
grep -r '\{[a-zA-Z_][a-zA-Z0-9_]*\}' template_engine/templates/ --include="*.md"
# Exclude Jinja2 patterns: {{ variable }}
```

#### Pattern 2B: Legacy Template Pack Layout

**File**: `template_engine/engine.py:209`
**Code**: `builtin_root / self.template_pack,  # legacy layout fallback`

**Risk Level**: LOW
- Directory search order only
- No breaking changes if removed
- May fail to find templates in old locations

**Validation**:
1. Document current template directory structure
2. Verify all templates in expected locations
3. Remove legacy search path

**Recommendation**: SAFE after template location audit

---

## Category 3: Full File Compatibility Shims

### Pattern 3A: reminders.py Wrapper

**File**: `reminders.py` (418 lines)
**Risk Level**: CRITICAL
**Type**: Full API compatibility shim wrapping `utils/reminder_engine.py`

#### Current Dependencies

**Direct Importers** (estimated 28 tools):
- All tools import: `from scribe_mcp.reminders import get_reminders`
- Some tools import legacy dataclasses

**Migration Blockers**:
1. ❌ **28 tools need import updates** (BLOCKING)
2. ❌ **No deprecation warnings in place** (BLOCKING)
3. ❌ **No migration guide exists** (BLOCKING)

#### Phased Deprecation Strategy

**Phase 1: Add Deprecation Warnings** (Safe, non-breaking)
```python
# reminders.py - add at module level
import warnings

def get_reminders(*args, **kwargs):
    warnings.warn(
        "reminders.get_reminders is deprecated. "
        "Use utils.reminder_engine.ReminderEngine directly. "
        "This compatibility shim will be removed in v3.0",
        DeprecationWarning,
        stacklevel=2
    )
    # ... existing wrapper code
```

**Phase 2: Create Migration Guide** (Documentation)
- Document new API usage patterns
- Provide before/after examples
- Add to upgrade guide

**Phase 3: Update All Tools** (28 file changes)
```python
# OLD (deprecated)
from scribe_mcp.reminders import get_reminders

# NEW (direct engine usage)
from scribe_mcp.utils.reminder_engine import ReminderEngine
from scribe_mcp.utils.reminder_validator import validate_and_load_engine
```

**Phase 4: Remove Shim** (After 2 version releases)
- Verify no internal usage of old API
- Remove reminders.py entirely
- Clean up 418 lines of wrapper code

#### Estimated Impact

**Files Modified**: 28+ tools
**Breaking Changes**: YES (if done immediately)
**Migration Effort**: 6-8 hours (update all tools)
**Testing Effort**: 4-5 hours (test all reminder integration)
**Version Requirement**: Minimum 2 releases with deprecation warnings

**Recommendation**: DEFER - Add deprecation warnings now, remove in v3.0

---

## Category 4: Optional Dependency Import Fallbacks (20 Patterns)

### Risk Assessment: KEEP PERMANENTLY

**Rationale**: These are intentional graceful degradation patterns, not technical debt

#### Pattern 4A: Vector/ML Dependencies (7 occurrences)

**Risk Level**: NONE (Keep indefinitely)
**Purpose**: Allow deployment without heavy ML dependencies
**Fallback Behavior**: Vector search features disabled gracefully

**Files**:
- `plugins/vector_indexer.py`
- 6 test files

**Recommendation**: KEEP - This is proper optional dependency handling

#### Pattern 4B: MCP SDK Types (2 occurrences)

**Risk Level**: NONE (Keep indefinitely)
**Purpose**: Enable testing without full MCP stack
**Fallback Behavior**: Use dict responses instead of MCP types

**Files**:
- `utils/response.py`
- `server.py`

**Recommendation**: KEEP - Essential for development/testing

#### Pattern 4C: Token Estimation (4 occurrences)

**Risk Level**: LOW (Consider making tiktoken required)
**Purpose**: Optional tiktoken dependency
**Fallback Behavior**: Basic estimation (4 chars ≈ 1 token)

**Alternative Strategy**: Make tiktoken required dependency
- Accuracy improves significantly with real tokenizer
- tiktoken is small dependency (~1MB)
- Fallback estimation often inaccurate

**Recommendation**: CONDITIONAL
- If accuracy matters: Add tiktoken to core dependencies, remove fallbacks
- If flexibility matters: Keep current optional pattern

#### Pattern 4D: OS-Specific File Locking (3 occurrences)

**Risk Level**: NONE (Keep indefinitely)
**Purpose**: Cross-platform file locking
**Fallback Chain**: msvcrt → portalocker → fcntl → no locking

**Recommendation**: KEEP - Proper OS-specific handling

#### Pattern 4E: Monitoring Dependencies (2 occurrences)

**Risk Level**: NONE (Keep indefinitely)
**Purpose**: Optional psutil and watchdog
**Fallback Behavior**: Basic metrics without these libraries

**Recommendation**: KEEP - Monitoring is enhancement, not requirement

#### Pattern 4F: Miscellaneous (2 occurrences)

**Files**:
1. `utils/parameter_validator.py:371` - shared logging utils
2. `utils/bulk_processor.py:22` - time utilities

**Risk Level**: LOW (Code smell - investigate)
**Issue**: Inline fallback implementations suggest circular imports or poor module organization

**Recommendation**: INVESTIGATE
- Why do these modules need fallback implementations?
- Are there circular import issues?
- Should these utilities be extracted to shared module?

---

## Category 5: Configuration Fallbacks

### Pattern 5A: Settings Import Fallbacks (utils/optimization.py)

**Occurrences**: 2 (lines 34 and 68)
**Pattern**: Duplicate code - same fallback in two functions

```python
try:
    from scribe_mcp.config.settings import settings
    threshold = token_warning_threshold or settings.token_warning_threshold
except ImportError:
    threshold = token_warning_threshold or 4000
```

**Issues**:
1. **Code duplication** (Team B should flag this)
2. **Why would settings import fail?** - Suggests architectural issue
3. **Hardcoded fallback values** - Magic numbers scattered in code

**Risk Level**: MEDIUM (architectural smell)
**Root Cause**: Unclear why settings would be unavailable

**Recommendation**: INVESTIGATE & REFACTOR
1. Determine why ImportError catch is needed
2. If settings should always be available, remove fallback
3. If fallback needed, extract to shared constant
4. Consolidate duplicate code

---

## Category 6: Deprecated Markers

### Pattern 6A: Tool Metadata Deprecation Infrastructure

**File**: `tools/base/tool_metadata.py:446`
**Purpose**: Display deprecation warnings in tool help
**Risk Level**: NONE (infrastructure, not deprecated code)

**Recommendation**: KEEP - This is the deprecation system itself

### Pattern 6B: Files.py Docstring Warning

**File**: `utils/files.py:775`
**Warning**: "DEPRECATED: Use template_content parameter in rotate_file instead"

**Risk Level**: LOW (needs verification)
**Questions**:
1. Is old parameter still accepted?
2. Is there actual deprecated code, or just documentation?
3. Can old parameter usage be removed?

**Action Required**:
1. Check `rotate_file()` signature for deprecated parameters
2. Grep codebase for usage of old parameter name
3. If unused, remove deprecated parameter
4. If used, add runtime deprecation warning

**Recommendation**: VERIFY & REMOVE if unused

---

## Summary Risk Matrix

| Pattern Category | Count | Risk Level | Action | Phase |
|-----------------|-------|------------|--------|-------|
| sys.path hacks | 68 | CONDITIONAL | Remove after src/ migration | Phase 6 |
| Template fallback | 2 systems | CONDITIONAL | Remove after validation | Phase 6 |
| reminders.py shim | 1 file | CRITICAL | Deprecate → Remove v3.0 | Multi-phase |
| Optional deps | 20 | NONE | KEEP permanently | N/A |
| Settings fallbacks | 2 | MEDIUM | Investigate & refactor | Phase 5-6 |
| Deprecated markers | 2 | VARIES | Case-by-case | Phase 5 |

**Total Patterns**: 95
**Safe to Remove Now**: 0
**Conditional Removal (with prerequisites)**: 70
**Keep Permanently**: 20
**Needs Investigation**: 5

---

## Migration Dependency Graph

```
Phase 3 (Complete) → SPEC-PKG-001 (src/ migration spec)
    ↓
Phase 6A → Create pyproject.toml + src/ layout
    ↓
Phase 6B → Remove sys.path from tests (68 → 8 remaining)
    ↓
Phase 6C → Remove sys.path from scripts (8 → 1 remaining)
    ↓
Phase 6D → Remove sys.path from server.py (1 → 0 remaining)
    ↓
Phase 6E → Validate template syntax (scan for {var})
    ↓
Phase 6F → Remove template fallback code (~125 lines)

Parallel Track:
Phase 5 → Add reminders.py deprecation warnings
    ↓
v2.2 Release → Warnings in place
    ↓
v2.3 Release → Warnings remain
    ↓
v3.0 Release → Remove reminders.py (418 lines)
```

---

## Immediate Actions (No Blockers)

1. ✅ **Add deprecation warnings to reminders.py** - Non-breaking, starts migration clock
2. ✅ **Investigate settings import fallbacks** - Understand why catch needed
3. ✅ **Verify files.py deprecated parameter usage** - May be removable now
4. ✅ **Document template syntax requirements** - Prepare for fallback removal

## Blocked Actions (Prerequisites Required)

1. ❌ **Remove sys.path patterns** - Blocked by: pyproject.toml creation (Phase 6)
2. ❌ **Remove template fallback** - Blocked by: template syntax validation
3. ❌ **Remove reminders.py** - Blocked by: 28 tool migrations + 2 version grace period

---

**Next Document**: See `SPEC-LEGACY-001-cleanup-plan.yaml` for machine-readable implementation specifications
