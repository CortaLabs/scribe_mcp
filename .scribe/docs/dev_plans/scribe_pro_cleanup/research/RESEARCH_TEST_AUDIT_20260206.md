---
id: scribe_pro_cleanup-research-test-audit-20260206
title: "\U0001F52C Research Test Audit 20260206 \u2014 scribe_pro_cleanup"
doc_name: RESEARCH_TEST_AUDIT_20260206
category: engineering
status: draft
version: '0.1'
last_updated: '2026-02-06'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Test Audit 20260206 — scribe_pro_cleanup
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-06 07:56:08 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Comprehensive audit of Scribe MCP test suite to identify organization issues, coverage gaps, quality problems, and cleanup requirements.

**Key Takeaways:**
- **142 test files** in `tests/` directory with **323+ test functions** (200+ async, 123+ sync)
- **560MB of orphaned test data** in `tmp_tests/` directory (365 files dating Oct-Feb) due to inadequate cleanup
- **5 test files misplaced in root directory** (4 legitimate tests + 1 debug script)
- **121 instances of hardcoded paths** reducing test portability
- **No dedicated SQLite storage tests** - tested only through integration tests
- **Formatter coverage excellent** (10 test files), v2.2 tools have good coverage (read_file: 5, search: 2, edit_file: 1)
- **13 skipped/xfail tests** (all vector-related, likely optional dependencies)
- **Fixture cleanup issue:** 97 fixtures, 101 temp directory uses, only 41 cleanup calls
- Test configuration healthy: pytest.ini with proper markers, conftest.py provides isolation
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-TestAudit

**Investigation Window:** 2026-02-06 (Single comprehensive audit)

**Focus Areas:**
- [x] Test inventory (file count, function count, location audit)
- [x] Test configuration (pytest.ini, conftest.py, markers, filters)
- [x] Test fixtures (shared fixtures, database isolation, cleanup patterns)
- [x] Test database handling (temp directories, cleanup issues, production DB safety)
- [x] Broken/skipped tests (skip markers, invalid imports, dead code)
- [x] Coverage gaps (which tools/components lack tests)
- [x] Test quality (assertions, hardcoded paths, flaky patterns, complexity)
- [x] Root directory test files (classification, move vs delete decisions)
- [x] Cleanup strategy recommendations

**Dependencies & Constraints:**
- Investigation limited to static analysis (no test execution)
- Multiline regex patterns unreliable for empty test body detection
- Vector test skips may be due to optional dependencies (not investigated)
- Coverage percentages not measured (would require test execution + coverage.py)
<!-- ID: findings -->
### Finding 1: Test Suite Scale and Organization
- **Summary:** Large, well-structured test suite with 142 test files containing 323+ test functions (200+ async, 123+ sync), primarily organized in `tests/` directory
- **Evidence:** 
  - `find tests -name "test_*.py" | wc -l` → 142 files
  - `search pattern="^async def test_"` → 200+ async functions
  - `search pattern="^def test_"` → 123+ sync functions
  - Integration test approach (test_tools.py: 684 lines, 21 functions)
- **Confidence:** High (0.95)

### Finding 2: Orphaned Test Database Crisis
- **Summary:** 560MB of orphaned test data in `tmp_tests/` from October-February, indicating systemic cleanup failure
- **Evidence:**
  - `du -sh tmp_tests/` → 560MB
  - `find tmp_tests/ -type f | wc -l` → 365 files
  - 101 uses of temp directories vs 41 cleanup calls
  - UUID-named directories from old test runs still present
- **Confidence:** High (0.98) - verified via filesystem inspection
- **Impact:** Disk space waste, potential test isolation contamination

### Finding 3: Root Directory Test File Misplacement
- **Summary:** 5 test files in root directory that should be moved to `tests/` or deleted
- **Evidence:**
  - `test_db_routing.py` (2466 bytes) - DB routing integration test → MOVE
  - `test_phase3_state_manager.py` (5998 bytes) - State management test → MOVE
  - `test_path_resolution_debug.py` (2134 bytes) - Path resolution test → MOVE
  - `test_all_tools_phase5.py` (1522 bytes) - Minimal setup script → UNCERTAIN
  - `debug_append_entry.py` (873 bytes) - One-off debug script → DELETE
- **Confidence:** High (0.93)
- **Repository Clutter:** Violates Commandment #4 (proper project structure)

### Finding 4: Test Fixture Cleanup Gap
- **Summary:** 97 pytest fixtures defined, but inadequate cleanup implementation causes test database accumulation
- **Evidence:**
  - `search pattern="@pytest\.fixture"` → 97 fixtures across 6 files
  - `search pattern="tempfile\.mkdtemp|TemporaryDirectory"` → 101 uses
  - `search pattern="\.cleanup\(\)|shutil\.rmtree|os\.remove"` → 41 cleanup calls
  - 60% of temp directory uses lack explicit cleanup
- **Confidence:** High (0.90)
- **Root Cause:** Tests rely on implicit cleanup or fixtures without teardown

### Finding 5: Hardcoded Path Portability Issues
- **Summary:** 121 instances of hardcoded paths (/home/austin, /tmp patterns) reduce test portability across environments
- **Evidence:**
  - `search pattern="/home/austin|/tmp/[^/]+/"` → 121 matches in 5 files
  - Files affected: test_error_handler.py, test_agent_manager.py, test_migration_priority_columns.py, test_response_formatter_readable.py, test_token_count.py
- **Confidence:** High (0.88)
- **Impact:** Tests break on different machines, CI/CD portability issues

### Finding 6: Storage Layer Lacks Dedicated Unit Tests
- **Summary:** SQLiteStorage (storage/sqlite.py) has no dedicated unit test file; tested only indirectly through 94 integration test uses
- **Evidence:**
  - `glob tests/*sqlite*.py` → No results
  - `search pattern="SQLiteStorage"` → 94 uses across test files
  - Integration-heavy approach: test_tools.py, test_agent_manager.py, test_audit_trails.py
- **Confidence:** Medium (0.75) - indirect coverage may be comprehensive but hard to verify without execution
- **Risk:** Schema migrations, connection pooling, error handling may lack edge case coverage

### Finding 7: Excellent Formatter and v2.2 Tool Coverage
- **Summary:** Formatters have 10 dedicated test files; v2.2 tools (read_file, search, edit_file) have good coverage
- **Evidence:**
  - Formatter tests: test_base_formatter.py, test_entry_formatter.py, test_file_formatter.py, test_ui_formatter.py, test_response_formatter_*.py (10 total)
  - read_file: 5 test files (test_read_file_tool.py, test_read_file_enhancements.py, test_read_file_readable.py, test_read_file_dependencies.py, test_read_file_phase4_bugs.py)
  - search: 2 test files (test_search_tool.py, test_search_pagination.py)
  - edit_file: 1 test file (test_edit_file.py)
- **Confidence:** High (0.92)

### Finding 8: Vector Tests Selectively Skipped
- **Summary:** 13 skip/xfail markers across 5 vector-related test files, likely due to optional FAISS dependencies
- **Evidence:**
  - `search pattern="@pytest\.mark\.skip|@pytest\.mark\.xfail"` → 13 matches
  - Files: test_vector_integration.py, test_vector_search_tools.py, test_vector_performance.py, test_vector_complete_integration.py, test_plugin_registry_runtime.py
  - pytest.ini filters distutils deprecation warnings from FAISS/setuptools
- **Confidence:** High (0.90)
- **Impact:** Minimal - optional feature with intentional conditional testing

### Finding 9: Test Configuration Healthy
- **Summary:** pytest.ini and conftest.py provide solid foundation for test execution and isolation
- **Evidence:**
  - pytest.ini: markers (slow, performance), filterwarnings (suppresses noise), standard test discovery
  - conftest.py: Sets up tmp_state directory for test isolation, adds parent to sys.path
  - Performance tests excluded by default: `addopts = -m "not performance"`
- **Confidence:** High (0.95)

### Additional Notes
- No broad `except: pass` blocks found (good practice adherence)
- One suspicious import in test_database_migration.py needs investigation
- Test file naming convention consistent: test_*.py pattern
- Async test support well-integrated throughout suite
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

1. **Integration-First Testing Strategy**
   - Large integration test files (test_tools.py: 684 lines, 21 functions)
   - Tests often combine multiple tools/components in single test
   - Prefer end-to-end workflows over isolated unit tests
   - Trade-off: Good for detecting integration issues, harder to pinpoint failures

2. **Pytest Fixture Architecture**
   - `isolated_state` and `project_root` fixtures widely used
   - Fixtures provide temp directories and isolated state
   - Fixture scope not always explicit (function/module/session unclear)
   - Issue: Teardown inconsistently implemented

3. **Temp Directory Management Pattern**
   - UUID-based directory naming: `tmp_tests/{uuid}/`
   - TemporaryDirectory context managers used sporadically
   - Many tests create directories without guaranteed cleanup
   - Pattern: `tmp_path.mkdir()` without matching cleanup

4. **Async Test Patterns**
   - 200+ async test functions indicate heavy async codebase
   - Consistent use of async/await throughout test suite
   - No apparent issues with async fixture handling

**System Interactions:**

1. **Database Layer**
   - SQLiteStorage instantiated in most tests with temp DB paths
   - Tests initialize storage backend: `await storage._initialise()`
   - Direct access to `server_module.storage_backend` for DI
   - Pattern: Tests mock at storage layer, not DB level

2. **File System Heavy**
   - Tests create actual files in .scribe/, tmp_tests/, tests/tmp_state/
   - State management tested via real file writes
   - Document templates tested with actual file generation
   - Risk: File system state can leak between tests

3. **Tool Chain Testing**
   - Tests often chain: set_project → append_entry → read_recent → query_entries
   - Full MCP server integration in some tests
   - Tool interdependencies tested implicitly

**Risk Assessment:**

- [x] **Critical: Test Database Accumulation** - 560MB orphaned data indicates cleanup crisis. Tests create databases but don't reliably destroy them. Risk: Disk space exhaustion, test contamination from old data.

- [x] **High: Hardcoded Paths** - 121 instances of `/home/austin` or `/tmp` patterns make tests environment-specific. Risk: CI/CD failures, contributor onboarding friction.

- [x] **Medium: Storage Layer Coverage Gap** - No dedicated storage/sqlite.py unit tests. Complex schema migrations and connection pooling tested only indirectly. Risk: Edge cases in DB layer may be untested.

- [x] **Low: Root Directory Clutter** - 5 test files in wrong location. Risk: Confusion for new contributors, violates repo conventions.

- [x] **Low: Vector Test Skips** - 13 skipped vector tests. Appears intentional for optional dependencies. Risk: Feature drift if vector tests never run.
<!-- ID: recommendations -->
### Immediate Next Steps

#### 1. Clean Up tmp_tests/ Directory (Critical - 560MB)
- [ ] **Backup first:** `tar -czf tmp_tests_backup_$(date +%Y%m%d).tar.gz tmp_tests/`
- [ ] **Delete orphaned test data:** `rm -rf tmp_tests/*/` (keep directory structure)
- [ ] **Document findings:** Note which tests created the most orphaned data
- [ ] **Estimated savings:** 560MB disk space

#### 2. Move Root Directory Test Files (High Priority)
- [ ] Move `test_db_routing.py` → `tests/test_db_routing.py`
- [ ] Move `test_phase3_state_manager.py` → `tests/test_phase3_state_manager.py`
- [ ] Move `test_path_resolution_debug.py` → `tests/test_path_resolution_debug.py`
- [ ] Investigate `test_all_tools_phase5.py` - determine if needed or delete
- [ ] Delete `debug_append_entry.py` (one-off debug script)
- [ ] Verify tests still pass after move: `pytest tests/test_db_routing.py -v`

#### 3. Add Fixture Cleanup Enforcement (High Priority)
- [ ] Audit all 6 files with fixtures for missing teardown
- [ ] Add `yield` + cleanup to fixtures lacking teardown:
  ```python
  @pytest.fixture
  def temp_db(tmp_path):
      db_path = tmp_path / "test.db"
      storage = SQLiteStorage(str(db_path))
      yield storage
      # Cleanup
      storage.close()
      if db_path.exists():
          db_path.unlink()
  ```
- [ ] Consider `pytest-tmp-path-cleanup` plugin for automatic cleanup
- [ ] Add pre-commit hook to verify fixture cleanup patterns

#### 4. Replace Hardcoded Paths (Medium Priority)
- [ ] Audit 5 files with hardcoded paths:
  - `tests/test_error_handler.py`
  - `tests/test_agent_manager.py`
  - `tests/test_migration_priority_columns.py`
  - `tests/test_response_formatter_readable.py`
  - `tests/test_token_count.py`
- [ ] Replace `/home/austin` with `tmp_path` fixture
- [ ] Replace `/tmp/` patterns with `tempfile.mkdtemp()` or `tmp_path`
- [ ] Add CI check: `rg "/home/austin" tests/ && exit 1`

#### 5. Investigate test_database_migration.py Import Issue (Medium Priority)
- [ ] Read `tests/test_database_migration.py` to find suspicious import
- [ ] Verify import still valid or remove if testing removed feature
- [ ] Run test to confirm it doesn't fail on import: `pytest tests/test_database_migration.py -v`

### Long-Term Opportunities

#### 1. Add Dedicated Storage Layer Unit Tests
**Why:** SQLiteStorage is critical infrastructure tested only indirectly. Schema migrations, connection pooling, and error handling need explicit unit tests.

**Approach:**
- Create `tests/test_sqlite_storage.py` with tests for:
  - Schema initialization and migrations
  - Connection pooling behavior (min/max connections)
  - Error handling (locked DB, corrupted schema)
  - Transaction rollback scenarios
  - Concurrent access patterns
- Target 80%+ line coverage for `storage/sqlite.py`

#### 2. Standardize Fixture Architecture
**Why:** 97 fixtures with inconsistent teardown and unclear scope. Consolidate common patterns.

**Approach:**
- Create `tests/fixtures/` directory
- Split conftest.py into logical modules:
  - `tests/fixtures/storage.py` - DB fixtures with guaranteed cleanup
  - `tests/fixtures/projects.py` - Project setup fixtures
  - `tests/fixtures/paths.py` - Temp directory fixtures with auto-cleanup
- Document fixture scope (function/module/session) explicitly
- Add fixture dependency graph visualization

#### 3. Improve Test Discovery and Organization
**Why:** 142 test files is large - categorize by feature area for better navigation.

**Approach:**
- Organize tests by functional area:
  ```
  tests/
    ├── unit/           # Unit tests (storage, utils, formatters)
    ├── integration/    # Integration tests (tool chains)
    ├── tools/          # Tool-specific tests (read_file, search, edit_file)
    ├── docs/           # Document management tests
    ├── vector/         # Vector/semantic search tests
    └── fixtures/       # Shared fixtures
  ```
- Update pytest.ini with additional markers: `@pytest.mark.unit`, `@pytest.mark.integration`
- Add test coverage reports: `pytest --cov=scribe_mcp --cov-report=html`

#### 4. Add Pre-Commit Hooks for Test Quality
**Why:** Prevent regressions in test quality (hardcoded paths, missing cleanup).

**Hooks to add:**
- Verify no hardcoded paths: `rg "/home/austin" tests/ && exit 1`
- Verify fixture cleanup: Check for `yield` without cleanup block
- Verify test naming: Enforce `test_*.py` pattern
- Run fast test subset on pre-commit: `pytest -m "not slow and not performance"`

#### 5. Create Test Database Cleanup Automation
**Why:** Prevent future 560MB accumulation.

**Approach:**
- Add pytest plugin/hook to track created temp directories
- Auto-cleanup at end of test session: `pytest_sessionfinish` hook
- Add GitHub Actions workflow to check for orphaned test data:
  ```yaml
  - name: Check for orphaned test data
    run: |
      SIZE=$(du -sm tmp_tests/ | cut -f1)
      if [ $SIZE -gt 50 ]; then
        echo "ERROR: tmp_tests/ exceeds 50MB"
        exit 1
      fi
  ```

#### 6. Document Vector Test Skip Strategy
**Why:** 13 skipped tests with unclear rationale.

**Approach:**
- Add documentation: `tests/vector/README.md` explaining optional FAISS dependency
- Document how to enable vector tests: `pip install scribe-mcp[vector]`
- Add CI job that runs vector tests with dependencies installed
<!-- ID: appendix -->
### Test File Inventory (Complete List)

**Root Directory Files (5 total):**
1. `test_db_routing.py` - 76 lines, DB routing test → **MOVE to tests/**
2. `test_phase3_state_manager.py` - 142 lines, state management test → **MOVE to tests/**
3. `test_path_resolution_debug.py` - 74 lines, path resolution test → **MOVE to tests/**
4. `test_all_tools_phase5.py` - 50 lines, minimal setup script → **INVESTIGATE**
5. `debug_append_entry.py` - 33 lines, one-off debug script → **DELETE**

**Tests Directory Files (142 total):**
- See complete list via: `find tests -name "test_*.py" -type f | sort`

**Test Files by Category:**
- **Tool tests:** test_read_file*.py (5), test_search*.py (2), test_edit_file.py (1), test_manage_docs*.py (10+)
- **Formatter tests:** test_*formatter*.py (10)
- **Integration tests:** test_tools.py, test_integration*.py, test_*_integration.py (20+)
- **Storage tests:** test_reminder_storage.py (1) - No dedicated SQLite tests
- **Vector tests:** test_vector*.py (5+) - Many with skip markers
- **Config/utility tests:** test_config*.py, test_*_utils.py (15+)
- **State/project tests:** test_project*.py, test_state*.py, test_agent*.py (10+)

### Key Metrics Summary

| Metric | Count | Notes |
|--------|-------|-------|
| Total test files | 147 | 142 in tests/, 5 in root |
| Test functions | 323+ | 200+ async, 123+ sync |
| Pytest fixtures | 97 | Across 6 files |
| Temp directory uses | 101 | 60% lack cleanup |
| Cleanup calls | 41 | Insufficient coverage |
| Hardcoded paths | 121 | 5 files affected |
| Skipped/xfail tests | 13 | All vector-related |
| Orphaned test data | 560MB | 365 files in tmp_tests/ |
| Formatter test coverage | 10 files | Excellent |
| Storage unit test coverage | 0 files | Gap identified |

### References

- **Test configuration:** `/pytest.ini`, `/tests/conftest.py`
- **Temp directory location:** `/tmp_tests/` (orphaned), `/tests/tmp_state/` (active)
- **Storage backend:** `/storage/sqlite.py` (no dedicated tests)
- **Formatters:** `/utils/formatters/*.py` (10 test files)
- **v2.2 tools:** `/tools/read_file.py`, `/tools/search.py`, `/tools/edit_file.py`

### Search Queries Used in Research

```bash
# Test file discovery
find tests -name "test_*.py" -type f | wc -l

# Function counting
search pattern="^async def test_"  # 200+ async functions
search pattern="^def test_"        # 123+ sync functions

# Fixture analysis
search pattern="@pytest\.fixture"  # 97 fixtures
search pattern="tempfile\.mkdtemp|TemporaryDirectory"  # 101 uses
search pattern="\.cleanup\(\)|shutil\.rmtree|os\.remove"  # 41 cleanup calls

# Quality checks
search pattern="@pytest\.mark\.skip|@pytest\.mark\.xfail"  # 13 skips
search pattern="/home/austin|/tmp/[^/]+/"  # 121 hardcoded paths
search pattern="SQLiteStorage"  # 94 uses in tests

# Coverage checks
glob "tests/*sqlite*.py"  # No results
glob "tests/*formatter*.py"  # 10 files
glob "tests/test_read_file*.py"  # 5 files
```

### Attachments

- Progress log entries: 11 total with full reasoning traces
- Tool usage: scribe.search (20+ queries), scribe.read_file (10+ files), glob (5+ patterns)
- Confidence scores: 0.75-0.98 across findings (avg: 0.91)
