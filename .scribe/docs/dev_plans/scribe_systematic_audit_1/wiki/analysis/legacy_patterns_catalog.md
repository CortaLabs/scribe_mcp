# Legacy Patterns Catalog - Team C (Phase 4)

**Agent**: ResearchAgent-Phase4-LegacyCode
**Created**: 2026-01-05
**Purpose**: Comprehensive catalog of all legacy/fallback patterns in scribe_mcp codebase

---

## Executive Summary

**Total Legacy Patterns Identified**: 110+
**Categories**: 5 major patterns
**Safety Assessment**: Most patterns are intentional compatibility layers
**Removal Risk**: LOW for sys.path (addressable), MEDIUM for template fallback, HIGH for reminders.py (breaking change)

---

## 1. Full File Compatibility Shims

### 1.1 reminders.py - Complete Backward Compatibility Wrapper

**File**: `reminders.py` (418 lines)
**Type**: Full API compatibility shim
**Purpose**: Provides drop-in replacement for old reminders API while routing to new `utils/reminder_engine.py`

**Legacy Components**:
- **Line 50-88**: `get_reminders()` - Main legacy entry point
- **Line 94-234**: `_build_legacy_context()` - Format conversion wrapper
- **Line 246-287**: Legacy dataclasses (`ReminderConfig`, `Reminder`, `ReminderContext`)
- **Line 293-344**: `_build_config()` - Legacy config builder
- **Line 351-374**: Helper wrappers (`_apply_tone`, `_make_reminder`)

**Current State**: Fully functional, actively used by all tools
**Migration Blocker**: All 28 tools import from `reminders.py` - breaking change to remove
**Dependencies**:
- New system: `utils/reminder_engine.py`, `utils/reminder_validator.py`
- Importers: All tools via `from scribe_mcp.reminders import get_reminders`

**Safety Assessment**:
- **KEEP**: Required for backward compatibility
- **Risk Level**: CRITICAL - removal would break all tool integrations
- **Modernization Path**:
  1. Update all 28 tools to import from `utils.reminder_engine` directly
  2. Deprecate `reminders.py` with warnings
  3. Remove after 2-version grace period

**Lines of Code**: 418 lines (100% wrapper code, 0% core logic)

---

## 2. Template Engine Legacy Fallback System

### 2.1 Jinja2 → Legacy {variable} Syntax Fallback

**File**: `template_engine/engine.py`
**Type**: Dual rendering system with automatic fallback
**Purpose**: Maintain compatibility with old `{variable}` template syntax while using modern Jinja2

**Legacy Components**:
- **Line 48-49**: `LEGACY_PATTERN = r'\{(\w+)\}'` - Old template regex
- **Line 380-398**: `_render_legacy_template()` - SafeDict-based format_map() fallback
- **Line 400-458**: `render_template()` - Jinja2 with fallback on error
- **Line 460-505**: `render_string()` - Same dual-path pattern

**Fallback Trigger**:
```python
try:
    # Try Jinja2 rendering
    result = template.render(**context)
except (TemplateSyntaxError, TemplateRuntimeError) as e:
    # Fallback to legacy {variable} syntax
    if fallback and not strict:
        return self._render_legacy_template(source, context)
```

**Configuration**:
- `fallback=True` (default) - Enable legacy fallback
- `strict=True` - Disable fallback, fail-hard mode
- CLI: `--no-fallback` flag in `template_engine/cli.py:50`

**Current Usage**: Unknown - need to check if any templates use old syntax
**Safety Assessment**:
- **CONDITIONAL**: Safe to remove IF all templates use Jinja2 syntax
- **Risk Level**: MEDIUM - could break old templates silently
- **Validation Required**: Scan all template files for `{variable}` patterns (not `{{ variable }}`)

**Lines of Code**: ~125 lines of fallback logic

### 2.2 Template Pack Legacy Layout Fallback

**File**: `template_engine/engine.py:209`
**Type**: Directory search fallback

```python
builtin_root / self.template_pack,  # legacy layout fallback
```

**Purpose**: Support old template directory structure
**Risk Level**: LOW - directory search order, no breaking changes
**Recommendation**: Document expected layout and deprecate old structure

---

## 3. Optional Dependency Import Fallbacks

### 3.1 Vector/ML Dependencies (Graceful Degradation)

**Pattern**: Feature availability flags
**Count**: 7 occurrences

**Files**:
1. `plugins/vector_indexer.py:32` - FAISS + sentence-transformers
2. `tests/test_vector_integration.py:18`
3. `tests/test_vector_search_tools.py:14`
4. `tests/test_vector_performance.py:17`
5. `tests/debug_vector_processing.py:24`
6. `tests/test_vector_complete_integration.py:23`
7. `tests/test_vector_indexer.py:18`

**Pattern**:
```python
try:
    import faiss
    from sentence_transformers import SentenceTransformer
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None
    np = None
```

**Safety Assessment**:
- **KEEP**: Intentional optional dependency pattern
- **Risk Level**: NONE - enables deployment without ML libraries
- **Purpose**: Vector search features are opt-in enhancement

### 3.2 MCP SDK Types (Development Flexibility)

**Files**:
1. `utils/response.py:34` - CallToolResult, TextContent fallback
2. `server.py:25` - Full MCP server graceful degradation

**Pattern**:
```python
try:
    from mcp.types import CallToolResult, TextContent
    MCP_TYPES_AVAILABLE = True
except ImportError:
    CallToolResult = None
    TextContent = None
    MCP_TYPES_AVAILABLE = False
```

**Safety Assessment**:
- **KEEP**: Required for testing without full MCP stack
- **Risk Level**: NONE - enables unit testing in isolation
- **Purpose**: Development and testing flexibility

### 3.3 Token Estimation (tiktoken Optional)

**Files**:
1. `utils/tokens.py:20` - tiktoken with warning fallback
2. `utils/response.py:19` - token_estimator import
3. `utils/estimator.py:28` - token_estimator fallback
4. `utils/context_safety.py:14` - token_estimator fallback

**Pattern**:
```python
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    warnings.warn("tiktoken not available, using basic token estimation")
```

**Fallback Behavior**: Basic estimation (4 chars ≈ 1 token)
**Safety Assessment**:
- **KEEP**: Graceful degradation for installations without tiktoken
- **Risk Level**: LOW - estimation accuracy reduced but functional
- **Purpose**: Avoid hard dependency on tiktoken

### 3.4 OS-Specific File Locking

**File**: `utils/files.py:25-38`
**Pattern**: Multi-tier fallback for cross-platform file locking

```python
try:
    import msvcrt
    HAS_WINDOWS_LOCK = True
except ImportError:
    HAS_WINDOWS_LOCK = False
    try:
        import portalocker
        HAS_PORTALOCKER = True
    except ImportError:
        HAS_PORTALOCKER = False

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
```

**Fallback Chain**: msvcrt (Windows) → portalocker (cross-platform) → fcntl (POSIX) → no locking
**Safety Assessment**:
- **KEEP**: Essential for cross-platform compatibility
- **Risk Level**: NONE - proper OS-specific handling
- **Purpose**: File locking works on Windows, Linux, macOS

### 3.5 Optional Monitoring Dependencies

**Files**:
1. `doc_management/performance_monitor.py:312` - psutil fallback
2. `doc_management/file_watcher.py:17` - watchdog fallback

**Pattern**: Feature degradation when monitoring libraries unavailable
**Safety Assessment**:
- **KEEP**: Monitoring is enhancement, not requirement
- **Risk Level**: NONE - core functionality unaffected

### 3.6 Miscellaneous Import Fallbacks

**Files**:
1. `utils/parameter_validator.py:371` - shared logging utils fallback
2. `utils/optimization.py:34` - settings import fallback
3. `utils/optimization.py:68` - settings import fallback (duplicate pattern)
4. `utils/bulk_processor.py:22` - time utilities fallback
5. `tests/test_append_entry_priority.py:35` - test helper fallback

**Pattern**: Inline fallback implementations
**Safety Assessment**: Mixed - some are technical debt (duplicate fallbacks), others are intentional

---

## 4. sys.path Manipulation Patterns (Import Hacks)

### 4.1 Overview

**Total Occurrences**: 68
**Pattern**: `sys.path.insert(0, str(Path(__file__).parent[.parent]))`
**Purpose**: Enable direct script execution without package installation
**Phase 3 Reference**: Identified as cleanup candidate in import analysis

### 4.2 Distribution

**Tests** (60 files):
- `tests/test_*.py` - Standard pattern: `sys.path.insert(0, str(Path(__file__).parent.parent))`
- Enables `pytest tests/test_file.py` direct execution
- Enables `python tests/test_file.py` direct execution

**Scripts** (7 files):
1. `scripts/scribe.py:32`
2. `scripts/scribe_cli.py:15`
3. `scripts/scribe_probe.py:24`
4. `scripts/reindex_docs.py:26`
5. `scripts/reindex_vector.py:47`
6. `scripts/check_vector_index.py:19`
7. `template_engine/cli.py:10`

**Server** (1 file):
- `server.py:18` - Special case: enables `python -m server` from package directory

### 4.3 Pattern Analysis

**Common Variations**:
```python
# Pattern 1: Parent directory (most common)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Pattern 2: Grandparent (for nested files)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Pattern 3: Current directory (dangerous)
sys.path.insert(0, '.')  # tests/test_sandbox_bypass.py:10

# Pattern 4: Conditional (server.py)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
```

### 4.4 Safety Assessment

**Current State**: Functional but fragile
**Problems**:
1. Breaks when files are moved
2. Pollutes sys.path with multiple entries
3. Import order becomes unpredictable
4. Doesn't work with editable installs (`pip install -e .`)

**Phase 3 Context**: 95.7% of import issues solvable with `src/` layout migration
**Recommendation**: REMOVE after src/ migration (Phase 6)

**Risk Level**:
- **SAFE to remove** IF:
  1. Package installed via `pip install -e .`
  2. Tests run via `pytest` (auto-discovers package)
  3. Scripts invoked via `python -m scribe_mcp.scripts.scribe`
- **BREAKING** IF:
  1. Direct execution expected: `python tests/test_file.py`
  2. Scripts run without installation: `python scripts/scribe.py`

**Migration Blocker**:
- No `setup.py` or `pyproject.toml` for editable install
- Phase 3 SPEC-PKG-001 proposes src/ migration
- Requires coordinated change across all 68 files

---

## 5. Other Fallback Patterns

### 5.1 DEPRECATED Markers

**Occurrences**: 2

1. **tools/base/tool_metadata.py:446**
```python
help_text.append(f"⚠️ **DEPRECATED:** {metadata.deprecation_message or 'This tool is deprecated'}")
```
- **Purpose**: Display deprecation warnings in tool help
- **Assessment**: KEEP - infrastructure for future deprecations

2. **utils/files.py:775**
```python
"""
DEPRECATED: Use template_content parameter in rotate_file instead.
"""
```
- **Purpose**: Docstring warning about old parameter usage
- **Assessment**: Informational only - check if old parameter still accepted

### 5.2 "old_" Variable Naming

**File**: `plugins/vector_indexer.py:790-814`
```python
old_entries = self.index_metadata.total_entries if self.index_metadata else 0
# ... later ...
"old_entries_count": old_entries,
```

- **Assessment**: NOT legacy code - just naming for "previous value"
- **Risk Level**: NONE - false positive

### 5.3 Fallback Configuration Patterns

**File**: `utils/reminder_validator.py`
- **Line 152**: `get_fallback_config()` - Emergency configuration
- **Line 177**: `get_fallback_reminders()` - Minimal safe defaults

**Purpose**: System keeps running even with corrupt configuration
**Safety Assessment**: KEEP - critical resilience feature

---

## Summary Statistics

| Pattern Type | Count | Risk Level | Recommendation |
|-------------|--------|-----------|----------------|
| Full File Shims | 1 (reminders.py) | CRITICAL | Keep until tools migrated |
| Template Fallbacks | 2 systems | MEDIUM | Validate template syntax first |
| Import Fallbacks (Optional Deps) | 20 | NONE | Keep - intentional design |
| sys.path Hacks | 68 | SAFE* | Remove after src/ migration |
| Misc Legacy Markers | 3 | VARIES | Case-by-case assessment |

**Total Legacy Patterns**: 94+ distinct occurrences
**Safe to Remove Now**: 0 (all have dependencies or serve purpose)
**Conditional Removal**: 70 (sys.path + template fallback after validation)
**Keep Permanently**: 24 (optional dependency patterns)

---

## Cross-References

**Team A (Dead Code)**: May find unused fallback code paths
**Team B (Duplication)**: Note duplicate ImportError patterns (settings fallback in utils/optimization.py appears twice)
**Team D (API Validation)**: Should verify deprecated tool parameters from tools/base/tool_metadata.py

---

**Next Steps**: See `deprecation_candidates.md` for removal safety assessment and `SPEC-LEGACY-001-cleanup-plan.yaml` for phased migration strategy.
