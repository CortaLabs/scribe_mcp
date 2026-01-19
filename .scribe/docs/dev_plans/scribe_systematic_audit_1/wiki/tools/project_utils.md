# project_utils.py - Forensic Audit Report

**File**: `tools/project_utils.py`
**Size**: 254 LOC | 8,241 bytes
**Complexity**: Medium (Configuration Layer)
**Auditor**: ResearchAgent-K-AdvancedFeatures
**Date**: 2026-01-05

---

## 1. Overview

`project_utils.py` is a **configuration and caching layer** that provides project discovery, config loading, and path normalization utilities. It implements module-level LRU caching and temp project detection heuristics.

**Purpose**: Centralized project configuration management with filesystem-based discovery and defensive loading.

**LOC Breakdown**:
- Config loading & caching: ~67 LOC (26%) - _load_project_file, _PROJECT_CACHE
- Temp project detection: ~53 LOC (21%) - _is_temp_project
- Config discovery: ~27 LOC (11%) - list_project_configs, load_project_config
- Path normalization: ~67 LOC (26%) - _normalise_project_data
- Async state integration: ~12 LOC (5%) - load_active_project
- Helper functions: ~28 LOC (11%) - _read_json, _is_within, slugify_project_name

**Architectural Pattern**: **Configuration Cache Layer**
- Module-level state (_PROJECT_CACHE, lines 15-16)
- 128-entry LRU cache with mtime-based invalidation
- Defensive exception handling (return None/empty dict on errors)
- Path security validation (_is_within checks)

**Relationships**:
- **Depends on**: `config/settings.py` (project root, paths)
- **Depends on**: `state/manager.py` (StateManager for async operations)
- **Used by**: `tools/agent_project_utils.py` (config fallback)
- **Used by**: `tools/set_project.py` (project initialization)
- **Used by**: `tools/list_projects.py` (project discovery)

**Complexity Drivers**:
1. **Temp project detection** - NLP-based heuristics (lines 38-90)
2. **Module-level cache** - Stateful caching with LRU eviction (lines 15-16, 145-161)
3. **Path normalization** - Security-conscious path resolution (lines 189-247)
4. **Multi-source fallback** - Config files → env vars → legacy config (lines 93-117)

---

## 2. Sub-System Breakdown

### Sub-System 1: Module-Level State & Constants (Lines 14-18)

**Responsibility**: Global configuration and caching infrastructure.

**Constants**:
- `PROJECTS_DIR` (line 14): `settings.project_root / "config" / "projects"`
- `_PROJECT_CACHE` (line 15): `Dict[Path, Tuple[float, Dict[str, Any]]]`
- `_SLUG_CLEANER` (line 18): `re.compile(r"[^0-9a-z_]+")`

**Cache Structure**:
```python
_PROJECT_CACHE: Dict[Path, Tuple[float, Dict[str, Any]]]
# Key: Path to project.json file
# Value: (mtime, project_dict)
```

**Cache Policy**:
- LRU eviction at 128 entries (line 159-160)
- mtime-based invalidation (lines 149-154)
- Module-level state (survives across function calls)

**Extractable**: YES [BUCKET:caching]
- Evidence: Lines 15-16, 145-161 implement generic file caching pattern
- Used by: _load_project_file (currently)
- Potential users: Any tool loading config files repeatedly
- Before/After: Before = module-level dict. After = `FileCacheLRU` class in `utils/caching.py`
- Contract:
  - **Input**: File path
  - **Output**: Cached dict if mtime unchanged, None if cache miss
  - **Failure Policy**: Cache miss returns None, reload from disk
  - **State Owner**: Module-level cache dict (mutable global state)

**Risk Assessment**: Medium
- **Duplication Potential**: Other modules may implement similar caching
- **State Management**: Global cache persists across requests (may cause stale reads)
- **Unification Strategy**: Extract to shared caching utility with configurable size/TTL

---

### Sub-System 2: Project Name Slugification (Lines 21-24)

**Responsibility**: Convert project names to filesystem-safe slugs.

**Function**: `slugify_project_name(name: str)` (21-24)

**Algorithm**:
1. Strip whitespace, lowercase (line 23)
2. Replace spaces and hyphens with underscores (line 23)
3. Remove all non-alphanumeric characters except underscores (line 24)
4. Strip trailing underscores, default to "project" if empty (line 24)

**Pattern**: `normalize → replace → clean → fallback`

**Examples**:
- "My Project" → "my_project"
- "Test-123" → "test_123"
- "Special!@#$%Chars" → "specialchars"
- "" → "project" (fallback)

**Extractable**: MAYBE [BUCKET:utilities]
- Evidence: Lines 21-24 are pure string transformation, no config-specific logic
- Used by: _normalise_project_data (line 211)
- Potential users: Any tool generating filesystem paths from user input
- Before/After: Before = config-specific. After = `StringUtils.slugify(text, fallback="default")`
- Risk: Low - simple utility function, unlikely to have dependencies

**Comparison with set_project.py**:
- Wave 1 audit: set_project.py likely has similar slugification
- **Cross-cutting concern**: Should be unified in single utility

---

### Sub-System 3: Project Config Discovery (Lines 27-35)

**Responsibility**: List all project config files in projects directory.

**Function**: `list_project_configs()` (27-35)

**Return Type**: `Dict[str, Dict[str, Any]]` (project_name → project_dict)

**Workflow**:
1. Check if PROJECTS_DIR exists (line 29)
2. Glob for `*.json` files, sorted (line 31)
3. Load each project file via `_load_project_file()` (line 32)
4. Skip None results (failed loads) (line 33)
5. Return dict keyed by project name (line 34)

**Extractable**: NO - Config discovery specific to project structure

**Contract**:
- **Input**: None (uses global PROJECTS_DIR)
- **Output**: Dict of all loadable projects
- **Failure Policy**: Return empty dict if directory doesn't exist, skip failed loads
- **State Owner**: Filesystem (read-only), _PROJECT_CACHE (read/write)

---

### Sub-System 4: Temp Project Detection (Lines 38-90)

**Responsibility**: NLP-based detection of temporary/test projects for auto-skip during discovery.

**Function**: `_is_temp_project(project_path: Path)` (38-90)

**Documentation** (Lines 40-67):
- **Purpose**: Prevent auto-switching to test projects
- **Reserved Keywords**: test, temp, tmp, demo, sample, example, mock, fake, dummy, trial, experiment
- **Reserved Patterns**: UUID suffixes (8+ chars), numeric suffixes

**Algorithm**:
1. Lowercase filename and stem (lines 68-69)
2. Check for temp indicators in filename (lines 72-79)
3. Check for UUID-like pattern (8+ char suffix after `-` or `_`) (lines 82-84)
4. Check for numeric suffix pattern (lines 87-88)
5. Return True if any match, False otherwise (line 90)

**Examples** (from docstring, lines 60-66):
- **SKIPPED**: "test-project.json", "history-test-711f48a0.json", "project-123.json"
- **RECOGNIZED**: "my-project.json", "production-app.json", "real-work.json"

**Extractable**: YES [BUCKET:utilities]
- Evidence: Lines 38-90 implement generic filename pattern matching
- Used by: load_project_config (line 107)
- Potential users: Any tool filtering temporary files/directories
- Before/After: Before = project-specific. After = `FileUtils.is_temp_file(path, indicators=[...])`
- Contract:
  - **Input**: Path to file
  - **Output**: bool (True = temp file, False = production file)
  - **Failure Policy**: N/A (pure function, no exceptions)
  - **State Owner**: None (stateless)

**Risk Assessment**: Low
- Well-documented heuristics (lines 40-67)
- Clear examples of skip/recognize cases
- Generic pattern matching, not project-specific

---

### Sub-System 5: Project Config Loading (Lines 93-117)

**Responsibility**: Load project config with multi-source fallback.

**Function**: `load_project_config(project_name: Optional[str])` (93-117)

**Fallback Chain** (3 levels):
1. **Named project**: Load from `{PROJECTS_DIR}/{project_name}.json` (lines 94-97)
2. **Environment variable**: Load from `SCRIBE_DEFAULT_PROJECT` env var (lines 99-103)
3. **First non-temp project**: Glob all *.json, skip temp projects (lines 105-111)
4. **Legacy config**: Fallback to `config/project.json` (lines 113-116)

**Workflow**:
1. If project_name provided, try loading directly (94-97)
2. If env var set and different from project_name, try that (99-103)
3. Iterate sorted *.json files, skip temp projects, return first valid (105-111)
4. Final fallback to legacy single config file (114-116)

**Temp Project Filtering** (Lines 106-108):
```python
if _is_temp_project(path):
    continue  # Skip temp/test projects
```

**Extractable**: NO - Config discovery specific to Scribe project structure

**Contract**:
- **Input**: Optional project_name
- **Output**: Project dict or None
- **Failure Policy**: Multi-tier fallback, return None if all sources fail
- **State Owner**: Filesystem (read-only), _PROJECT_CACHE (read/write)

---

### Sub-System 6: Project Config Loading by Path (Lines 120-124)

**Responsibility**: Load project config from specific file path.

**Function**: `load_project_config_by_path(path: Path)` (120-124)

**Workflow**:
1. Try _load_project_file (line 121)
2. If successful, return project dict (line 122)
3. If failed, read JSON directly and normalize (line 123-124)

**Extractable**: NO - Trivial wrapper, only 5 LOC

---

### Sub-System 7: Legacy Alias (Lines 127-128)

**Responsibility**: Backwards compatibility alias for load_project_config.

**Function**: `load_config_project(project_name: Optional[str])` (127-128)

**Purpose**: Alias for load_project_config (name consistency)

**Extractable**: NO - Backwards compatibility shim

---

### Sub-System 8: Async State Integration (Lines 131-142)

**Responsibility**: Load active project from StateManager with config fallback.

**Function**: `load_active_project(state_manager: StateManager)` (131-142)

**Return Type**: `Tuple[Optional[Dict[str, Any]], Optional[str], Tuple[str, ...]]`
- (project_dict, current_project_name, recent_projects_tuple)

**Workflow**:
1. Load state from StateManager (line 132)
2. Get project from state.current_project (line 133)
3. If found, return project + state data (line 134-135)
4. Fallback to load_project_config (lines 137-139)
5. If config found, update StateManager and reload (lines 139-141)
6. Return state data (line 142)

**Extractable**: NO - State integration specific to Scribe architecture

**Contract**:
- **Input**: StateManager instance
- **Output**: Tuple of (project, current_name, recent_projects)
- **Failure Policy**: Return (None, current_project, recent_projects) if project not found
- **State Owner**: StateManager (read/write)

---

### Sub-System 9: Project File Loading with Caching (Lines 145-161)

**Responsibility**: Load project file with mtime-based cache invalidation and LRU eviction.

**Function**: `_load_project_file(path: Path)` (145-161)

**Workflow**:
1. Check file existence (lines 146-147)
2. Get file mtime (lines 148-150)
3. Check cache for path (line 152)
4. If cached and mtime matches, return cached data (lines 153-154)
5. Read JSON and normalize (lines 155-156)
6. Cache result if successful (lines 157-158)
7. LRU eviction if cache > 128 entries (lines 159-160)
8. Return project dict (line 161)

**Cache Invalidation**:
- mtime-based: If file modified, cache miss (lines 153-154)
- LRU eviction: Pop first entry when >128 items (lines 159-160)

**Exception Handling**:
- Lines 148-150: OSError on stat() → return None

**Extractable**: PARTIAL [BUCKET:caching]
- Evidence: Lines 145-161 implement generic file caching with mtime
- Used by: list_project_configs, load_project_config, load_project_config_by_path
- Reusable pattern: File caching with invalidation
- Before/After: Before = inline caching. After = `FileCache.load(path, parser=json.load)`
- Risk: Moderate - caching logic is generic, but integrated with _read_json and _normalise_project_data

---

### Sub-System 10: Legacy Config Loading (Lines 164-178)

**Responsibility**: Load legacy single config file (config/project.json).

**Function**: `_load_legacy_config()` (164-178)

**Workflow**:
1. Check legacy path existence (lines 165-167)
2. Read JSON (lines 168-170)
3. Normalize project name (lines 171-172)
4. Normalize defaults (lines 173-177)
5. Call _normalise_project_data (line 178)

**Legacy Format Normalization**:
- `project_name` → `name` (lines 171-172)
- `default_emoji`, `default_agent` → `defaults` dict (lines 173-177)

**Extractable**: NO - Legacy compatibility logic, temporary

---

### Sub-System 11: JSON Reading (Lines 181-186)

**Responsibility**: Defensively read JSON files.

**Function**: `_read_json(path: Path)` (181-186)

**Workflow**:
1. Open file with UTF-8 encoding (line 183)
2. Parse JSON (line 184)
3. Catch FileNotFoundError and JSONDecodeError (line 185)
4. Return empty dict on error (line 186)

**Extractable**: YES [BUCKET:utilities]
- Evidence: Lines 181-186 are pure JSON loading, no project-specific logic
- Used by: _load_project_file, _load_legacy_config
- Potential users: Any tool reading JSON config files
- Before/After: Before = local helper. After = `FileUtils.read_json(path, default={})`

---

### Sub-System 12: Project Data Normalization (Lines 189-247)

**Responsibility**: Normalize and validate project configuration data.

**Function**: `_normalise_project_data(data: Dict[str, Any], base_dir: Path)` (189-247)

**Validation & Normalization**:
1. **Name extraction** (lines 190-192): Get "name" or "project_name", return None if missing
2. **Root path resolution** (lines 194-203):
   - Use data.get("root") or default to settings.project_root
   - Expand ~ (user home) (line 196)
   - Resolve relative paths (lines 197-199)
   - Resolve absolute paths (lines 200-201)
3. **Docs dir resolution** (lines 205-214):
   - Use data.get("docs_dir") or generate from slug
   - Resolve relative to root (lines 208-209)
   - Slugify project name if generating path (line 211)
4. **Security check** (line 213-214): Ensure docs_path within root_path
5. **Progress log path resolution** (lines 216-224):
   - Use data.get("progress_log") or default to `{docs_path}/PROGRESS_LOG.md`
   - Resolve relative to root
6. **Security check** (line 223-224): Ensure log_path within root_path
7. **Defaults normalization** (lines 226-231): Filter out None/empty values
8. **Docs dict construction** (lines 233-238): Standard doc paths
9. **Return normalized dict** (lines 240-247)

**Security Feature**: `_is_within()` checks (lines 213-214, 223-224)
- Prevents path traversal attacks
- Ensures all paths stay within project root

**Extractable**: MAYBE [BUCKET:config]
- Evidence: Lines 189-247 implement generic config normalization pattern
- Used by: _load_project_file, load_project_config_by_path, _load_legacy_config
- Reusable pattern: Config validation + path resolution + security checks
- Before/After: Before = project-specific. After = `ConfigNormalizer` with custom path rules
- Risk: High coupling to Scribe project structure (lines 233-238 hardcode doc paths)

---

### Sub-System 13: Path Security Helper (Lines 250-255)

**Responsibility**: Validate that path is within parent directory (prevent path traversal).

**Function**: `_is_within(path: Path, parent: Path)` (250-255)

**Algorithm**:
1. Try `path.relative_to(parent)` (line 252)
2. If succeeds, path is within parent → return True (line 253)
3. If ValueError (not within), return False (line 255)

**Security Purpose**: Prevent directory traversal attacks
- Example: `../../etc/passwd` would fail this check

**Extractable**: YES [BUCKET:utilities]
- Evidence: Lines 250-255 are pure path validation, no config-specific logic
- Used by: _normalise_project_data (lines 213-214, 223-224)
- Potential users: Any tool validating user-provided paths
- Before/After: Before = local helper. After = `PathUtils.is_within(path, parent)`

---

## 3. Modularization Notes

### Configuration Layer Assessment

**Conclusion**: project_utils.py contains **SHARED UTILITIES** with extractable patterns but some project-specific coupling.

**Evidence**:
1. **Module-level cache** (lines 15-16, 145-161): Generic file caching pattern
2. **Slugification** (lines 21-24): Generic string transformation
3. **Temp detection** (lines 38-90): Generic filename filtering
4. **Path security** (lines 250-255): Generic path validation
5. **JSON reading** (lines 181-186): Generic file I/O

**What SHOULD Be Extracted**:

1. **File Caching Module** [BUCKET:caching]
   - Lines 15-16 (_PROJECT_CACHE), 145-161 (_load_project_file cache logic)
   - Generic mtime-based caching with LRU eviction
   - Extract to `utils/file_cache.py`

2. **String Utilities** [BUCKET:utilities]
   - Lines 21-24 (slugify_project_name)
   - Extract to `utils/string_utils.py`

3. **Path Security** [BUCKET:utilities]
   - Lines 250-255 (_is_within)
   - Extract to `utils/path_utils.py`

4. **File I/O Utilities** [BUCKET:utilities]
   - Lines 181-186 (_read_json)
   - Extract to `utils/file_utils.py`

5. **Temp File Detection** [BUCKET:utilities]
   - Lines 38-90 (_is_temp_project)
   - Extract to `utils/file_utils.py` or `utils/path_utils.py`

**What Should STAY Coupled**:
- Config discovery (lines 27-35, 93-117) - Scribe-specific structure
- State integration (lines 131-142) - StateManager dependency
- Project data normalization (lines 189-247) - Hardcoded Scribe doc structure
- Legacy config loading (lines 164-178) - Temporary backwards compatibility

**Comparison with Wave 1/2 Tools**:
- **Duplication Alert**: set_project.py (Wave 1) likely has similar:
  - Slugification logic (should use this module)
  - Path normalization (should use this module)
  - Config loading (may duplicate)
- **Unification Opportunity**: Extract shared patterns to prevent divergence

---

## 4. Implicit Contracts

### Contract 1: Project Directory Structure

**Assumption**: Project configs live in `config/projects/*.json`

**Evidence**: Line 14 (PROJECTS_DIR = settings.project_root / "config" / "projects")

**Risk**: If directory structure changes, all config discovery breaks
**Mitigation**: Centralize path constants in settings.py

### Contract 2: Project Dict Schema

**Assumption**: Normalized project dicts have specific keys
- Required: `name`, `root`, `progress_log`, `docs_dir`, `docs`, `defaults`
- `docs` dict has keys: `architecture`, `phase_plan`, `checklist`, `progress_log`

**Evidence**: Lines 240-247 (_normalise_project_data return dict)

**Risk**: If schema changes, downstream tools break
**Mitigation**: Schema versioning, validation on load

### Contract 3: Temp Project Indicators Never Change

**Assumption**: Reserved keywords (lines 72-74) and pattern heuristics (lines 82-88) remain stable

**Evidence**: Hardcoded indicator list and regex patterns

**Risk**: If temp detection heuristics change, auto-discovery behavior changes
**Mitigation**: Document heuristics clearly (done in lines 40-67)

### Contract 4: File Caching is Transparent

**Assumption**: Callers don't know/care about caching, just call load functions

**Evidence**: _PROJECT_CACHE is module-private (line 15)

**Risk**: Stale cache if files modified externally
**Mitigation**: mtime-based invalidation (lines 149-154)

### Contract 5: Settings Module Provides project_root

**Assumption**: `settings.project_root` exists and is valid Path

**Evidence**: Lines 14, 203, 218

**Risk**: If settings.project_root changes, all path resolution breaks
**Mitigation**: Centralize settings access, version settings schema

---

## 5. Token Analysis

### Token Impact: ZERO

**Rationale**: This module provides **INTERNAL UTILITIES** to other tools, not MCP tool endpoints.

**Usage Pattern**:
- Imported by: `tools/agent_project_utils.py`, `tools/set_project.py`, `tools/list_projects.py`
- Invoked by: Config discovery and project initialization flows
- Not invoked by: MCP clients directly

**Actual Token Producers**:
- `tools/set_project.py` - Uses config loading internally
- `tools/list_projects.py` - Uses config discovery internally
- **Indirect token impact**: Via tools that call these utilities

**Category**: N/A - Configuration utilities, not user-facing

---

## 6. Error Handling Architecture

### Policy 1: Silent Failure on Config Loading Errors

**Location**: Lines 148-150, 185-186
**Behavior**: Return None or empty dict on errors, never raise exceptions
**Classification**: **POLICY** (defensive configuration loading)

**Rationale**:
- Config loading must not crash server
- Missing configs handled gracefully by fallback chains
- Callers can handle None/empty dict returns

**Evidence**:
- Line 150: `except OSError: return None` (file stat failed)
- Line 185-186: `except (FileNotFoundError, json.JSONDecodeError): return {}` (JSON read failed)

### Policy 2: Multi-Tier Config Fallback

**Location**: Lines 93-117 (load_project_config)
**Behavior**: Try multiple sources, return first successful
**Classification**: **POLICY** (robustness via redundancy)

**Fallback Chain**:
1. Named project config (lines 94-97)
2. Environment variable (lines 99-103)
3. First non-temp project (lines 105-111)
4. Legacy config file (lines 114-116)

**Rationale**:
- Provides multiple ways to configure projects
- Handles missing configs gracefully
- Backwards compatibility with legacy setup

### Policy 3: Path Security Enforcement

**Location**: Lines 213-214, 223-224 (_normalise_project_data)
**Behavior**: Return None if paths escape project root
**Classification**: **SECURITY POLICY**

**Security Check**:
```python
if not _is_within(docs_path, root_path):
    return None  # Security: prevent path traversal
```

**Rationale**:
- Prevent directory traversal attacks
- Ensure all project paths within project root
- Fail closed (return None) on security violation

**Evidence**: Lines 213-214, 223-224

### Bug vs Policy Classification

**No bugs identified** in error handling. All exception handling and fallbacks are intentional defensive design.

**Security Validation**: Path security checks are correct defensive measures

---

## 7. Known Issues

### ISSUE-UTIL-001: Module-Level Cache is Global Mutable State

**Severity**: Medium (State Management)
**Location**: Lines 15-16, 145-161

**Description**: Module-level _PROJECT_CACHE dict persists across all requests, potentially causing stale reads.

**Evidence**:
```python
_PROJECT_CACHE: Dict[Path, Tuple[float, Dict[str, Any]]] = {}

# Cache persists across function calls
cached = _PROJECT_CACHE.get(path)
if cached and cached[0] == mtime:
    return cached[1]  # May be stale if file changed on disk
```

**Impact**:
- If file modified by external process, cache may miss mtime change
- Multiple workers may have inconsistent cache views
- Memory grows unbounded until LRU eviction at 128 entries

**Recommendation**: Extract to class-based cache with explicit invalidation
```python
class ProjectConfigCache:
    def __init__(self, max_size=128, ttl_seconds=300):
        self._cache = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, path: Path) -> Optional[Dict]:
        # Check mtime AND TTL
        ...

    def invalidate(self, path: Optional[Path] = None):
        # Explicit cache clearing
        ...
```

**Risk Level**: Medium - May cause hard-to-debug stale config issues
**Timing**: Phase 6, during caching framework extraction (SPEC-UTIL-001)

---

### ISSUE-UTIL-002: Slugification May Duplicate set_project.py Logic

**Severity**: Low (Duplication Risk)
**Location**: Lines 21-24 (slugify_project_name)

**Description**: set_project.py (Wave 1 audit) likely has similar slugification logic. Should be unified.

**Evidence**:
```python
# In project_utils.py
def slugify_project_name(name: str) -> str:
    normalised = name.strip().lower().replace(" ", "_").replace("-", "_")
    return _SLUG_CLEANER.sub("_", normalised).strip("_") or "project"
```

**Impact**:
- Logic duplication between modules
- If slugification rules change, must update both
- May have subtle differences (bugs)

**Recommendation**: Wave 1 audit should have documented set_project.py slugification
- Compare implementations
- Extract to single source of truth
- Reference SPEC-UTIL-001 for extraction plan

**Cross-Reference**: Wave 1 findings for set_project.py

---

### ISSUE-UTIL-003: Temp Project Detection May Have False Positives

**Severity**: Low (User Experience)
**Location**: Lines 38-90 (_is_temp_project)

**Description**: Heuristics may incorrectly flag production projects with certain naming patterns.

**Evidence**:
- "my-test-suite" → SKIPPED (contains "test")
- "project-2024" → SKIPPED (numeric suffix)
- "sample-app" → SKIPPED (contains "sample")

**Impact**:
- Users may be confused why their project is auto-skipped
- Valid projects with unfortunate names ignored

**Recommendation**: Make temp detection configurable
```python
def _is_temp_project(
    project_path: Path,
    strict_mode: bool = True,  # If False, only check filename start/end
    custom_indicators: Optional[List[str]] = None
) -> bool:
    ...
```

**Not Critical Because**:
- Users can override by specifying project name explicitly
- Well-documented in docstring (lines 40-67)
- Affects auto-discovery only, not explicit selection

---

## 8. Implementation Specs

### SPEC-UTIL-001: Extract Configuration Utilities to Shared Modules

**Priority**: Medium
**Bucket**: [BUCKET:utilities], [BUCKET:caching], [BUCKET:config]
**Estimated Impact**: High (enables reuse across tools, reduces duplication)

**Motivation**: Multiple utilities in project_utils.py are generic and reusable across tools.

**Module Contracts**:
```yaml
name: Configuration Utilities Extraction
buckets: [utilities, caching, config]

modules:
  - name: FileCache
    location: utils/file_cache.py
    bucket: caching
    interface:
      FileCache:
        constructor:
          - max_size: int = 128
          - ttl_seconds: Optional[int] = None
        methods:
          get:
            inputs:
              - path: Path
              - loader: Callable[[Path], Dict]  # e.g., json.load
            outputs:
              - cached_data: Optional[Dict]
          invalidate:
            inputs:
              - path: Optional[Path]  # None = clear all
          stats:
            outputs:
              - hit_rate: float
              - size: int
              - oldest_mtime: datetime

  - name: StringUtils
    location: utils/string_utils.py
    bucket: utilities
    interface:
      slugify:
        inputs:
          - text: str
          - fallback: str = "default"
          - separator: str = "_"
        outputs:
          - slug: str
        description: "Convert text to filesystem-safe slug"

  - name: PathUtils
    location: utils/path_utils.py
    bucket: utilities
    interface:
      is_within:
        inputs:
          - path: Path
          - parent: Path
        outputs:
          - within: bool
        description: "Check if path is within parent (prevent traversal)"

      resolve_safe:
        inputs:
          - path: Union[str, Path]
          - base_dir: Path
          - must_exist: bool = False
        outputs:
          - resolved: Optional[Path]
        description: "Safely resolve path relative to base, return None if escapes"

  - name: FileUtils
    location: utils/file_utils.py
    bucket: utilities
    interface:
      read_json:
        inputs:
          - path: Path
          - default: Dict = {}
        outputs:
          - data: Dict
        description: "Defensively read JSON, return default on error"

      is_temp_file:
        inputs:
          - path: Path
          - indicators: List[str] = TEMP_INDICATORS
          - strict: bool = True
        outputs:
          - is_temp: bool
        description: "Detect temp/test files by naming patterns"

migration_plan:
  1. Create utils/ modules with extracted functions
  2. Update project_utils.py to import from utils/
  3. Search for slugification in set_project.py (Wave 1 audit)
  4. Unify slugification logic across tools
  5. Update all tools using these patterns
  6. Add comprehensive unit tests

affected_files:
  - tools/project_utils.py (refactor to use utils/)
  - tools/set_project.py (likely has slugification duplication)
  - tools/list_projects.py (uses config loading)
  - tools/agent_project_utils.py (uses config loading)

testing_requirements:
  - Unit tests for each utility function
  - Cache invalidation tests (mtime changes, TTL expiry)
  - Path security tests (traversal attempts)
  - Temp file detection tests (false positives/negatives)
  - Integration tests with existing tools

risks:
  - Slugification may differ between set_project.py and project_utils.py
  - Cache behavior changes may affect performance
  - Path resolution changes may break existing projects

mitigation:
  - Compare set_project.py slugification before extraction
  - Add performance benchmarks for cache
  - Comprehensive integration tests before deployment
```

**Cross-Reference**: Wave 1 audit for set_project.py duplication

---

### SPEC-UTIL-002: Improve Temp Project Detection

**Priority**: Low (Enhancement)
**Bucket**: [BUCKET:utilities]
**Estimated Impact**: Low (user experience improvement)

**Motivation**: Reduce false positives in temp project auto-skip behavior.

**Implementation**:
```yaml
name: Configurable Temp Project Detection
location: utils/file_utils.py (after SPEC-UTIL-001)
bucket: utilities

enhancements:
  - Add strict_mode parameter (default True for backwards compatibility)
  - Add custom_indicators parameter for user overrides
  - Add position-based heuristics (only check prefix/suffix)

  strict_mode: true (current behavior):
    - Check entire filename for indicators
    - Check for UUID/numeric suffixes
    - Used for auto-discovery

  strict_mode: false (relaxed):
    - Only check filename prefix (test_, temp_, etc.)
    - Only check filename suffix (_test, _temp, etc.)
    - Reduce false positives

configuration:
  location: scribe.yaml
  option: temp_project_detection
  values:
    mode: "strict" | "relaxed" | "custom"
    custom_indicators: ["indicator1", "indicator2"]

usage_example: |
  # In scribe.yaml
  temp_project_detection:
    mode: "relaxed"  # Fewer false positives

  # Or custom
  temp_project_detection:
    mode: "custom"
    indicators: ["test_", "_test", "tmp_"]

implementation:
  - Add config parsing in settings.py
  - Pass config to is_temp_file()
  - Default to strict mode for backwards compatibility

testing:
  - Test cases for strict vs relaxed modes
  - Validate false positive reduction
  - Ensure backwards compatibility
```

**Timing**: Low priority, after SPEC-UTIL-001

---

**End of project_utils.py Audit**

**Summary**:
- Architecture: Configuration and caching layer with extractable utilities
- Extractable modules: 5 (file cache, string utils, path utils, file I/O, temp detection)
- Known issues: 3 (module-level cache state, slugification duplication, temp detection false positives)
- Token profile: N/A (internal utilities, not MCP tools)
- Error handling: All intentional defensive configuration loading
- Recommendation: **Extract shared utilities (SPEC-UTIL-001), compare with set_project.py for duplication**
- Cross-cutting concern: Slugification likely duplicated in set_project.py (Wave 1) - needs unification
