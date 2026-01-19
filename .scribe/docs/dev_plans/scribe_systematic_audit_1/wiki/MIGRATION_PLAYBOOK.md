# src/ Layout Migration Playbook

**Specification Reference**: SPEC-PKG-001-src-migration.yaml
**Project**: scribe_systematic_audit_1
**Team**: C (src/ Migration Architect)
**Agent**: ResearchAgent-Phase3-SrcMigration
**Created**: 2026-01-05

---

## Executive Summary

This playbook provides step-by-step instructions for migrating scribe_mcp from flat layout to standard src/ layout.

**Migration Type**: All-at-once (cannot be incremental)
**Estimated Duration**: 32 hours (optimistic: 22h, pessimistic: 48h)
**Files Affected**: 208 Python files
**Complexity**: Medium-High
**Risk Level**: Medium-High (rollback plan included)

**Key Benefit**: Eliminates 70 sys.path hacks (95.7% removal rate)

---

## Table of Contents

1. [Pre-Flight Checklist](#pre-flight-checklist)
2. [Phase 0: Preparation (2 hours)](#phase-0-preparation)
3. [Phase 1: Directory Creation (1 hour)](#phase-1-directory-creation)
4. [Phase 2: Packaging Files (2 hours)](#phase-2-packaging-files)
5. [Phase 3: Production Code Updates (16 hours)](#phase-3-production-code-updates)
6. [Phase 4: Test Updates (8 hours)](#phase-4-test-updates)
7. [Phase 5: Script Migration (3 hours)](#phase-5-script-migration)
8. [Phase 6: Installation Testing (3 hours)](#phase-6-installation-testing)
9. [Phase 7: Documentation (2 hours)](#phase-7-documentation)
10. [Rollback Procedure](#rollback-procedure)
11. [Troubleshooting Guide](#troubleshooting-guide)
12. [Post-Migration Validation](#post-migration-validation)

---

## Pre-Flight Checklist

**Complete these BEFORE starting migration:**

### Dependencies
- [ ] Team A sys.path analysis complete ✅ (70 occurrences documented)
- [ ] Team B import graph available (PENDING - continue with estimates)
- [ ] Team D circular dependencies reviewed (PENDING - note risks)

### Environment
- [ ] Python 3.10+ installed
- [ ] Git working tree clean (`git status` shows no uncommitted changes)
- [ ] All tests passing (`pytest` returns 0 exit code)
- [ ] Virtual environment active (`.venv/bin/activate`)
- [ ] Disk space available (>500MB recommended)

### Backups
- [ ] Current branch backed up: `git branch backup-pre-migration-$(date +%Y%m%d)`
- [ ] Tag created: `git tag pre-src-migration`
- [ ] Pushed to remote: `git push origin --tags`
- [ ] Database backed up (if applicable)

### Time Commitment
- [ ] 32+ hour time block available (4+ days)
- [ ] No conflicting deadlines during migration
- [ ] Team notified of migration timeline

### Decision Points
- [ ] **DECISION REQUIRED**: Scripts migration strategy
  - [ ] Option A: Console scripts (RECOMMENDED - professional packaging)
  - [ ] Option B: Keep scripts/ at root (simpler, less changes)
- [ ] Document decision here: ________________

---

## Phase 0: Preparation (2 hours)

### 0.1 Create Migration Branch

```bash
# Create and switch to migration branch
git checkout -b feature/src-layout-migration

# Verify you're on the new branch
git branch
```

**Checkpoint**: `git branch` shows `* feature/src-layout-migration`

### 0.2 Review Dependencies

```bash
# Review Team A sys.path findings
cat .scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/sys_path_patterns.md | less

# Check if Team B import graph exists
ls -la .scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/*import* 2>/dev/null || echo "Team B pending"

# Check if Team D circular deps exist
ls -la .scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/*circular* 2>/dev/null || echo "Team D pending"
```

### 0.3 Baseline Tests

```bash
# Run full test suite and save results
pytest --tb=short > migration_baseline_tests.log 2>&1

# Count test results
echo "Baseline test count:"
grep -E "passed|failed|error" migration_baseline_tests.log | tail -1
```

**Checkpoint**: All tests passing (or document known failures)

### 0.4 Create Migration Checklist

```bash
# Copy this playbook to working directory for tracking
cp .scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/MIGRATION_PLAYBOOK.md \
   MIGRATION_PROGRESS.md

# You'll check off tasks in MIGRATION_PROGRESS.md as you go
```

### 0.5 Document Rollback Procedure

```bash
# Create rollback script
cat > rollback_migration.sh << 'EOF'
#!/bin/bash
# Emergency rollback script
echo "Rolling back src/ migration..."
git add -A
git commit -m "WIP: Failed migration state (saved for analysis)"
git checkout pre-src-migration
git checkout -b rollback/src-migration-failed
echo "Rollback complete. On branch: $(git branch --show-current)"
echo "Run 'pytest' to verify original code works"
EOF

chmod +x rollback_migration.sh
```

**Checkpoint**: `./rollback_migration.sh --help` shows usage (or at least runs)

---

## Phase 1: Directory Creation (1 hour)

### 1.1 Create src/ Directory Structure

```bash
# Create src/scribe_mcp/ directory
mkdir -p src/scribe_mcp

# Verify creation
ls -la src/
```

**Checkpoint**: `src/scribe_mcp/` directory exists

### 1.2 Move Production Modules

```bash
# Move all production modules to src/scribe_mcp/
mv tools src/scribe_mcp/
mv utils src/scribe_mcp/
mv storage src/scribe_mcp/
mv config src/scribe_mcp/
mv state src/scribe_mcp/
mv db src/scribe_mcp/
mv plugins src/scribe_mcp/
mv shared src/scribe_mcp/
mv template_engine src/scribe_mcp/
mv security src/scribe_mcp/
mv doc_management src/scribe_mcp/
mv templates src/scribe_mcp/

# Verify moves
ls -la src/scribe_mcp/
```

**Checkpoint**: All 12 modules visible in `src/scribe_mcp/`

### 1.3 Move Root Python Files

```bash
# Move root Python files
mv server.py src/scribe_mcp/
mv __init__.py src/scribe_mcp/
mv reminders.py src/scribe_mcp/

# Verify
ls -la src/scribe_mcp/*.py
```

**Checkpoint**: `server.py`, `__init__.py`, `reminders.py` in `src/scribe_mcp/`

### 1.4 Delete Debug Files (Team A Recommendation)

```bash
# Delete temporary debug file
rm -f debug_append_entry.py

# Verify deletion
ls -la debug_append_entry.py 2>&1 | grep "No such file" || echo "WARNING: File still exists"
```

**Checkpoint**: `debug_append_entry.py` deleted

### 1.5 Verify Directory Structure

```bash
# Verify final structure
tree -L 2 -d src/ | head -20
# OR if tree not installed:
find src/ -type d | sort

# Verify tests/ still at root
ls -la tests/ | head -10

# Verify scripts/ still at root (decision point affects this)
ls -la scripts/ | head -10

# Verify demo/ still at root
ls -la demo/
```

**Checkpoint**: Production code in `src/scribe_mcp/`, tests/scripts/demo at root

---

## Phase 2: Packaging Files (2 hours)

### 2.1 Create `__version__.py`

```bash
# Create version file
cat > src/scribe_mcp/__version__.py << 'EOF'
"""Version information for scribe_mcp package."""

__version__ = "2.1.1"
__version_info__ = (2, 1, 1)
EOF

# Verify
cat src/scribe_mcp/__version__.py
```

### 2.2 Update `__init__.py` with Version

```bash
# Backup original
cp src/scribe_mcp/__init__.py src/scribe_mcp/__init__.py.backup

# Add version import (prepend to file)
cat > src/scribe_mcp/__init__.py << 'EOF'
"""Scribe MCP - Enterprise-grade documentation governance for AI-powered development."""

from scribe_mcp.__version__ import __version__, __version_info__

__all__ = ["__version__", "__version_info__"]
EOF

# Verify
cat src/scribe_mcp/__init__.py
```

### 2.3 Create `pyproject.toml`

```bash
# Create pyproject.toml
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "scribe-mcp"
version = "2.1.1"
description = "Enterprise-grade documentation governance for AI-powered development"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}  # Update with actual license
authors = [
    {name = "Scribe MCP Contributors"}  # Update with actual authors
]

dependencies = [
    # Core dependencies (update from requirements.txt)
    "mcp>=0.1.0",
    "pydantic>=2.0.0",
    "jinja2>=3.0.0",
    "pyyaml>=6.0",
    "rich>=13.0.0",
    # Add other dependencies from requirements.txt
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]
postgres = [
    "asyncpg>=0.28.0",
    "psycopg2-binary>=2.9.0",
]
vector = [
    "faiss-cpu>=1.7.0",
    "sentence-transformers>=2.0.0",
]

[project.scripts]
# Option A: Console script entry points (if chosen)
scribe = "scribe_mcp.scripts.scribe:main"
scribe-cli = "scribe_mcp.scripts.scribe_cli:main"
scribe-probe = "scribe_mcp.scripts.scribe_probe:main"
migrate-scribe-db = "scribe_mcp.scripts.migrate_database:main"
reindex-scribe-docs = "scribe_mcp.scripts.reindex_docs:main"
reindex-scribe-vector = "scribe_mcp.scripts.reindex_vector:main"
check-scribe-vector = "scribe_mcp.scripts.check_vector_index:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
scribe_mcp = ["templates/**/*", "config/**/*.yaml", "config/**/*.json"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
EOF

# Verify
cat pyproject.toml | head -30
```

**IMPORTANT**: Update dependencies in `pyproject.toml` from actual `requirements.txt`:

```bash
# Extract dependencies from requirements.txt
cat requirements.txt
# Manually add each to pyproject.toml dependencies list
```

### 2.4 Create `setup.py` (Optional Fallback)

```bash
# Create setup.py for compatibility
cat > setup.py << 'EOF'
"""Setup script for scribe-mcp package."""

from setuptools import setup, find_packages
from pathlib import Path

# Read version from __version__.py
version_file = Path("src/scribe_mcp/__version__.py")
version_info = {}
exec(version_file.read_text(), version_info)

setup(
    name="scribe-mcp",
    version=version_info["__version__"],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
)
EOF

# Verify
python setup.py --version
```

### 2.5 Create `MANIFEST.in`

```bash
# Create MANIFEST.in for non-Python files
cat > MANIFEST.in << 'EOF'
include README.md
include LICENSE
include requirements.txt
recursive-include src/scribe_mcp/templates *
recursive-include src/scribe_mcp/config *.yaml *.json
recursive-exclude tests *
recursive-exclude .scribe *
recursive-exclude scripts *
global-exclude __pycache__
global-exclude *.py[co]
EOF

# Verify
cat MANIFEST.in
```

**Checkpoint**: All packaging files created (`pyproject.toml`, `setup.py`, `MANIFEST.in`, `__version__.py`)

---

## Phase 3: Production Code Updates (16 hours)

### 3.1 Remove sys.path Hacks from Production Code

**Files to update (from Team A findings):**

1. **server.py** (lines 16-18)
2. **utils/tool_logger.py** (line 171)
3. **template_engine/cli.py** (line 10)

#### 3.1.1 Update server.py

```bash
# Edit server.py to remove sys.path bootstrap
# BEFORE:
# _REPO_ROOT = Path(__file__).resolve().parent.parent
# if str(_REPO_ROOT) not in sys.path:
#     sys.path.insert(0, str(_REPO_ROOT))

# AFTER: Just delete those lines (package is installed)

# Verification:
grep -n "sys.path" src/scribe_mcp/server.py || echo "sys.path removed successfully"
```

#### 3.1.2 Update utils/tool_logger.py

```bash
# Remove debug block __main__ section
# Find line 171 and remove:
# if __name__ == "__main__":
#     sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Verification:
grep -n "sys.path" src/scribe_mcp/utils/tool_logger.py || echo "sys.path removed successfully"
```

#### 3.1.3 Update template_engine/cli.py

```bash
# Remove sys.path.insert from line 10

# Verification:
grep -n "sys.path" src/scribe_mcp/template_engine/cli.py || echo "sys.path removed successfully"
```

**Checkpoint**: Zero sys.path occurrences in src/ production code

```bash
# Verify no sys.path in production code
rg "sys\.path\.(insert|append)" src/scribe_mcp/ && echo "ERROR: sys.path still exists" || echo "✓ All sys.path removed"
```

### 3.2 Update Import Statements (If Needed)

**KEY INSIGHT**: Because package name stays `scribe_mcp`, most imports DON'T CHANGE.

```bash
# Verify imports still work (they should)
python -c "import sys; sys.path.insert(0, 'src'); from scribe_mcp import server; print('✓ Imports work')"
```

**Manual Review Required**: Check for any hardcoded paths

```bash
# Find Path(__file__) usage that might break
rg "Path\(__file__\)" src/scribe_mcp/ --type py | grep -v "__pycache__"

# Review each occurrence - look for:
# - Paths going up to parent directories
# - Hardcoded relative paths to config/templates
# - Working directory assumptions
```

**Common Patterns to Fix**:

```python
# BEFORE (might break):
config_path = Path(__file__).parent.parent / "config" / "settings.yaml"

# AFTER (package-relative):
from pathlib import Path
import scribe_mcp
pkg_root = Path(scribe_mcp.__file__).parent
config_path = pkg_root / "config" / "settings.yaml"

# OR use importlib.resources (better):
from importlib.resources import files
config_path = files('scribe_mcp').joinpath('config', 'settings.yaml')
```

### 3.3 Systematic Module Review

**For each module, check**:
1. No sys.path manipulation
2. Imports resolve correctly
3. No hardcoded paths
4. Tests import correctly

```bash
# Create review script
cat > review_module.sh << 'EOF'
#!/bin/bash
module=$1
echo "Reviewing $module..."
echo "1. Check sys.path:"
rg "sys\.path" "src/scribe_mcp/$module/" || echo "  ✓ None found"
echo "2. Check hardcoded paths:"
rg "Path\(__file__\)\.parent\.parent" "src/scribe_mcp/$module/" || echo "  ✓ None found"
echo "3. Test import:"
python -c "import sys; sys.path.insert(0, 'src'); from scribe_mcp.$module import *" 2>&1 | head -5
echo ""
EOF

chmod +x review_module.sh

# Review each module
./review_module.sh tools
./review_module.sh utils
./review_module.sh storage
./review_module.sh config
./review_module.sh state
./review_module.sh db
./review_module.sh doc_management
./review_module.sh shared
./review_module.sh template_engine
./review_module.sh plugins
./review_module.sh security
```

**Estimated time per module**: 15-30 minutes (340 minutes total for tools, 320 for utils, etc. - see SPEC)

**Checkpoint**: All modules reviewed, imports work, no sys.path in production code

---

## Phase 4: Test Updates (8 hours)

### 4.1 Update conftest.py

```bash
# Backup original
cp tests/conftest.py tests/conftest.py.backup

# Edit tests/conftest.py - remove sys.path manipulation
# BEFORE:
# ROOT = Path(__file__).resolve().parents[2]
# sys.path.insert(0, str(ROOT))

# AFTER: Delete those lines (pytest will use installed package)
```

**Verification**:

```bash
grep -n "sys.path" tests/conftest.py && echo "ERROR: sys.path still in conftest" || echo "✓ conftest.py clean"
```

### 4.2 Bulk Update Standard Test Files

**65 test files** need sys.path removal.

#### Option A: Manual (safer but slower)

```bash
# List all files needing update
rg "sys\.path\.insert.*parent\.parent" tests/ --files-with-matches > test_files_to_update.txt

# Review list
cat test_files_to_update.txt

# For each file, remove sys.path lines manually
# Use your editor to remove lines like:
# import sys
# from pathlib import Path
# sys.path.insert(0, str(Path(__file__).parent.parent))
```

#### Option B: Semi-Automated (faster but verify carefully)

```bash
# Create sed script to remove common sys.path pattern
cat > remove_syspath.sed << 'EOF'
# Remove sys.path.insert with parent.parent pattern
/sys\.path\.insert\(0, str\(Path\(__file__\)\.parent\.parent\)\)/d
# Remove parent.parent.parent variant
/sys\.path\.insert\(0, str\(Path\(__file__\)\.parent\.parent\.parent\)\)/d
# Remove literal '.' variant
/sys\.path\.insert\(0, '\.')/d
EOF

# Backup all test files first
cp -r tests tests.backup

# Apply sed to all test files
find tests -name "test_*.py" -type f -exec sed -i -f remove_syspath.sed {} \;

# Verify changes
git diff tests/ | head -100
```

**CRITICAL**: Review changes before committing!

### 4.3 Handle Special Cases (from Team A)

```bash
# 1. test_sandbox_bypass.py - has literal '.' pattern
# Manual edit required - remove: sys.path.insert(0, '.')

# 2. test_db_activation.py - has Path as P alias
# Remove: from pathlib import Path as P
# Remove: sys.path.insert(0, str(P(__file__).parent.parent))

# 3. test_performance.py - uses project_root variable
# Remove entire sys.path block with variable

# 4. test_tool_logger.py - parent.parent.parent
# Remove: sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 5. demo_get_project_formatter.py - demo file
# Remove sys.path.insert
```

### 4.4 Remove Unnecessary Imports

**After removing sys.path, you may have unused imports:**

```bash
# Find test files that import sys/Path but don't use them
for f in tests/test_*.py; do
  if grep -q "^import sys$" "$f" && ! grep -qv "sys.path" "$f" | grep -q "sys\."; then
    echo "$f: sys import may be unused"
  fi
done

# Review and remove unused imports manually
```

### 4.5 Verify Test Discovery

```bash
# Test that pytest can still find all tests
pytest --collect-only > test_collection.log 2>&1

# Count tests discovered
grep -E "test.*\.py::" test_collection.log | wc -l

# Should match original count (from baseline)
```

**Checkpoint**: pytest discovers all 97 test files

---

## Phase 5: Script Migration (3 hours)

### Decision Point: Option A or Option B?

**Review your decision from Pre-Flight Checklist:**

- [ ] Option A: Console scripts (RECOMMENDED)
- [ ] Option B: Keep scripts/ at root

### If Option A: Console Scripts

#### 5.1 Refactor Scripts to Have main() Functions

**Each script needs**:
```python
def main():
    # Script logic here
    pass

if __name__ == "__main__":
    main()
```

**Example for scripts/scribe.py:**

```bash
# Edit scripts/scribe.py
# Move all top-level code into main() function
# Keep imports at top
# Add main() function
# Add if __name__ == "__main__": main()
```

**Apply to all scripts:**
- `scripts/scribe.py`
- `scripts/scribe_cli.py`
- `scripts/scribe_probe.py`
- `scripts/migrate_database.py`
- `scripts/reindex_docs.py`
- `scripts/reindex_vector.py`
- `scripts/check_vector_index.py`

#### 5.2 Move Scripts to src/scribe_mcp/scripts/

```bash
# Option A: Move scripts into package
mv scripts src/scribe_mcp/

# Verify
ls -la src/scribe_mcp/scripts/
```

#### 5.3 Remove sys.path from Scripts

```bash
# Remove sys.path lines from all scripts
rg "sys\.path" src/scribe_mcp/scripts/*.py --files-with-matches | while read f; do
  echo "Editing $f..."
  # Remove sys.path lines manually or with sed
done

# Verify
rg "sys\.path" src/scribe_mcp/scripts/ && echo "ERROR" || echo "✓ All sys.path removed from scripts"
```

#### 5.4 Verify Entry Points in pyproject.toml

Already done in Phase 2.3 - verify:

```bash
grep -A 10 "\[project.scripts\]" pyproject.toml
```

### If Option B: Keep Scripts at Root

#### 5.1 Update Script Imports

```bash
# Scripts stay at root but use installed package
# Remove sys.path.insert lines
# Imports should use: from scribe_mcp.tools import X
```

#### 5.2 Document Script Usage

```bash
# Users must install package first:
# pip install -e .
# Then run: python scripts/scribe.py
```

**Checkpoint**: Scripts functional (test in Phase 6)

---

## Phase 6: Installation Testing (3 hours)

### 6.1 Create Fresh Virtual Environment

```bash
# Deactivate current venv
deactivate

# Create test venv
python3 -m venv .venv-test
source .venv-test/bin/activate

# Verify fresh environment
pip list | wc -l  # Should be minimal (~10 packages)
```

### 6.2 Install Package in Editable Mode

```bash
# Install with editable mode
pip install -e .

# Verify installation
pip show scribe-mcp

# Check console scripts installed (Option A)
which scribe || echo "Scripts not in PATH (may be Option B)"
which scribe-cli || echo "Scripts not in PATH (may be Option B)"
```

### 6.3 Test Imports from External

```bash
# Test import works from external script
python -c "from scribe_mcp.tools.append_entry import append_entry; print('✓ Import works')"

# Test package import
python -c "import scribe_mcp; print(f'✓ Package version: {scribe_mcp.__version__}')"

# Test server import
python -c "from scribe_mcp import server; print('✓ Server import works')"
```

### 6.4 Run Full Test Suite

```bash
# Run pytest
pytest -v > test_results_migration.log 2>&1

# Compare to baseline
diff migration_baseline_tests.log test_results_migration.log | head -50

# Count results
grep -E "passed|failed|error" test_results_migration.log | tail -1
```

**Expected**: All tests pass (or same failures as baseline)

**If failures**: See Troubleshooting Guide section below

### 6.5 Test MCP Server Startup

```bash
# Test server starts
timeout 10 python -m scribe_mcp.server &
SERVER_PID=$!
sleep 5
kill $SERVER_PID 2>/dev/null || echo "Server exited on its own"

# Check for errors
# Should see MCP server startup messages
```

### 6.6 Test Console Scripts (Option A Only)

```bash
# Test each console script
scribe --help
scribe-cli --version
scribe-probe --help
migrate-scribe-db --help
reindex-scribe-docs --help
reindex-scribe-vector --help
check-scribe-vector --help
```

**Expected**: All commands run without import errors

### 6.7 Verify No sys.path Required

```bash
# Search for any remaining sys.path in production code
rg "sys\.path\.(insert|append)" src/scribe_mcp/ --type py

# Expected output: 0 matches

# Check tests don't have sys.path
rg "sys\.path\.(insert|append)" tests/ --type py | wc -l
# Expected: 0 or very few (document any remaining)
```

**Checkpoint**: Package installs, imports work, tests pass, server starts, scripts functional

---

## Phase 7: Documentation (2 hours)

### 7.1 Update CLAUDE.md

```bash
# Edit CLAUDE.md to reflect new structure

# Key changes:
# 1. Import examples now mention src/ layout
# 2. Installation instructions: pip install -e .
# 3. Remove sys.path hack examples
# 4. Update test running instructions
```

**Sections to update:**
- Import best practices
- Testing guide
- Development setup
- Running the server

### 7.2 Update README.md

```bash
# Update installation section:
# pip install -e .  # For development
# pip install .     # For production
# pip install scribe-mcp  # From PyPI (future)
```

### 7.3 Create MIGRATION_NOTES.md

```bash
cat > MIGRATION_NOTES.md << 'EOF'
# src/ Layout Migration Notes

**Date**: 2026-01-05
**Spec**: SPEC-PKG-001-src-migration.yaml
**Playbook**: MIGRATION_PLAYBOOK.md

## What Changed

- Moved all production code to `src/scribe_mcp/`
- Created proper Python package with `pyproject.toml`
- Removed 70 sys.path hacks (65 tests, 5 scripts)
- Enabled pip installation: `pip install -e .`
- Scripts became console entry points (if Option A)

## Breaking Changes

- Direct `python server.py` no longer works
  - Use: `python -m scribe_mcp.server`
  - Or: Install and use as package

- Scripts require installation
  - No more standalone script execution
  - Use console commands: `scribe`, `scribe-cli`, etc.

## Migration Issues Encountered

(Document any issues here)

## Post-Migration Validation

- [ ] All tests passing
- [ ] Server starts successfully
- [ ] Console scripts work
- [ ] No sys.path in production code
- [ ] Imports work from external scripts

## Rollback Information

- Pre-migration tag: `pre-src-migration`
- Rollback branch: `rollback/src-migration-failed` (if needed)
- Rollback script: `./rollback_migration.sh`

EOF
```

**Checkpoint**: Documentation updated

---

## Rollback Procedure

### When to Rollback

**Rollback if**:
- >10% of tests fail
- MCP server won't start
- Circular import errors unresolvable
- >4 hours spent debugging without progress

**Don't rollback if**:
- Minor test failures (fixable)
- Single module import issue (isolatable)
- Documentation gaps

### Rollback Steps

```bash
# 1. Save current state for analysis
git add -A
git commit -m "WIP: Failed migration state (saved for analysis)"

# 2. Return to pre-migration state
git checkout pre-src-migration

# 3. Create rollback branch
git checkout -b rollback/src-migration-failed

# 4. Verify original code works
pytest
python server.py  # Should work

# 5. Document failure reasons
cat > ROLLBACK_REPORT.md << 'EOF'
# Migration Rollback Report

**Date**: $(date)
**Reason**: [Describe why rollback was necessary]

## Issues Encountered

1. [Issue 1]
2. [Issue 2]

## Attempted Solutions

1. [Solution tried]
2. [Solution tried]

## Recommendations for Re-attempt

- [Recommendation 1]
- [Recommendation 2]

EOF

# 6. Notify team
echo "Migration rolled back. See ROLLBACK_REPORT.md"
```

### Post-Rollback Actions

1. Analyze failure reasons
2. Update SPEC-PKG-001 with lessons learned
3. Wait for Team B/D data if missing
4. Schedule re-attempt

---

## Troubleshooting Guide

### Issue 1: pytest Can't Find Tests

**Symptoms**:
```
pytest --collect-only
ERROR: not found: tests/
```

**Diagnosis**:
```bash
# Check pytest config
cat pyproject.toml | grep -A 5 "pytest"

# Check if tests/ directory exists
ls -la tests/
```

**Solutions**:
1. Add to `pyproject.toml`:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   ```

2. Run pytest with explicit path:
   ```bash
   pytest tests/
   ```

### Issue 2: Import Errors in Tests

**Symptoms**:
```
ImportError: No module named 'scribe_mcp'
```

**Diagnosis**:
```bash
# Check if package installed
pip show scribe-mcp

# Check if in editable mode
pip list | grep scribe
```

**Solutions**:
1. Reinstall in editable mode:
   ```bash
   pip install -e .
   ```

2. Verify PYTHONPATH not interfering:
   ```bash
   echo $PYTHONPATH
   # Should be empty or not point to old location
   ```

### Issue 3: Template Files Not Found

**Symptoms**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'templates/...'
```

**Diagnosis**:
```bash
# Check template location
find . -name "*.j2" -o -name "*.jinja"

# Check MANIFEST.in includes templates
cat MANIFEST.in | grep templates
```

**Solutions**:
1. Update template loading to use package resources:
   ```python
   from importlib.resources import files
   template_path = files('scribe_mcp').joinpath('templates', 'template.j2')
   ```

2. Verify MANIFEST.in:
   ```
   recursive-include src/scribe_mcp/templates *
   ```

### Issue 4: Circular Import Detected

**Symptoms**:
```
ImportError: cannot import name 'X' from partially initialized module 'scribe_mcp.Y'
```

**Diagnosis**:
```bash
# Wait for Team D circular dependency report
# Or manually trace import chain
python -c "import scribe_mcp.tools.append_entry"  # See where it fails
```

**Solutions**:
1. Use lazy imports:
   ```python
   def function_needing_import():
       from scribe_mcp.tools import X  # Import inside function
   ```

2. Refactor to break cycle (requires Team D analysis)

### Issue 5: Console Scripts Not in PATH

**Symptoms**:
```bash
scribe --help
bash: scribe: command not found
```

**Diagnosis**:
```bash
# Check if scripts installed
pip show scribe-mcp | grep -A 20 "Entry-points"

# Check if pip bin in PATH
which pip
echo $PATH | grep -o "[^:]*pip[^:]*"
```

**Solutions**:
1. Reinstall package:
   ```bash
   pip install -e .
   ```

2. Check pyproject.toml entry points:
   ```bash
   grep -A 10 "\[project.scripts\]" pyproject.toml
   ```

3. Use full path:
   ```bash
   ~/.local/bin/scribe --help  # Or wherever pip installs scripts
   ```

### Issue 6: Server Won't Start

**Symptoms**:
```
python -m scribe_mcp.server
ImportError: ...
```

**Diagnosis**:
```bash
# Test server import directly
python -c "from scribe_mcp import server; print('OK')"

# Check for sys.path remnants
grep -r "sys.path" src/scribe_mcp/server.py
```

**Solutions**:
1. Verify server.py sys.path removed
2. Check server.py imports are correct
3. Reinstall package: `pip install -e .`

---

## Post-Migration Validation

### Final Checklist

Run through this checklist after Phase 7:

#### Installation
- [ ] `pip install -e .` succeeds
- [ ] `pip show scribe-mcp` shows version 2.1.1
- [ ] Package installed in editable mode

#### Imports
- [ ] `python -c "import scribe_mcp"` works
- [ ] `python -c "from scribe_mcp.tools import append_entry"` works
- [ ] `python -c "from scribe_mcp import server"` works

#### Tests
- [ ] `pytest --collect-only` finds all 97 tests
- [ ] `pytest` passes with 0 failures (or matches baseline)
- [ ] Test output clean (no import warnings)

#### Server
- [ ] `python -m scribe_mcp.server` starts
- [ ] Server responds to test MCP request

#### Scripts (Option A)
- [ ] `scribe --help` works
- [ ] `scribe-cli --version` works
- [ ] All 7 console scripts in PATH

#### Scripts (Option B)
- [ ] `python scripts/scribe.py` works after install
- [ ] No sys.path required

#### Code Quality
- [ ] `rg "sys\.path\.(insert|append)" src/scribe_mcp/` returns 0 matches
- [ ] `rg "sys\.path\.(insert|append)" tests/` returns 0 matches
- [ ] No hardcoded absolute paths in code

#### Documentation
- [ ] CLAUDE.md updated
- [ ] README.md updated
- [ ] MIGRATION_NOTES.md created

### Performance Validation

```bash
# Run performance comparison
pytest --durations=10 > post_migration_perf.log

# Compare to baseline (optional)
# diff migration_baseline_tests.log post_migration_perf.log
```

### Integration Testing

```bash
# Test end-to-end workflow
python -c "
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.append_entry import append_entry

# Set project
result = set_project(name='migration_test')
print(f'Set project: {result}')

# Append entry
result = append_entry(
    message='Migration validation test',
    status='success',
    agent='MigrationValidator'
)
print(f'Append entry: {result}')
print('✓ Integration test passed')
"
```

### Clean Environment Test

```bash
# Create completely fresh venv
python3 -m venv .venv-clean
source .venv-clean/bin/activate

# Install from source
pip install .

# Test basic functionality
python -c "from scribe_mcp.tools import append_entry; print('✓ Works')"

# Deactivate
deactivate
```

---

## Success Criteria

**Migration is COMPLETE when**:

✅ All 97 tests pass
✅ Package installs via `pip install -e .`
✅ MCP server starts with `python -m scribe_mcp.server`
✅ Console scripts functional (Option A) or scripts work with install (Option B)
✅ Zero sys.path hacks in production code
✅ Imports work from external scripts
✅ Documentation updated
✅ Migration merged to main branch

---

## Final Notes

- **Total Time**: Expect 32 hours (22-48 hour range)
- **Point of No Return**: After Phase 3 completes (hard to rollback)
- **Biggest Risk**: Test discovery breaking
- **Key Validation**: pytest must pass
- **Team Dependencies**: Team B data refines estimates, Team D data affects risks

**When in doubt**: Consult SPEC-PKG-001-src-migration.yaml for detailed rationale.

---

**Document Version**: 1.0
**Last Updated**: 2026-01-05
**Next Review**: After Team B/D deliver findings
