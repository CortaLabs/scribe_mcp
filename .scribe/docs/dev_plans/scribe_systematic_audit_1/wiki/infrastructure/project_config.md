# Base Infrastructure: Project Configuration

**Files**: `config/projects/*.json` (3 files, ~10 lines each)
**LOC**: ~30 total (simple JSON schemas)
**Complexity**: Low (declarative config)
**Relationships**: Loaded by tools/project_utils.py, used by project resolution

---

## 1. Overview

Project configuration files are **per-project JSON schemas** defining project name, root path, progress log location, and default emoji/agent. These files enable persistent project metadata outside the database (legacy support for pre-registry projects).

**Purpose**: Store project-specific settings in version control
**Pattern**: One JSON file per project in `config/projects/`
**Contract**: Projects can exist in JSON OR database (dual source of truth)

**Example** (manual_demo.json):
```json
{
  "name": "manual_demo",
  "root": ".",
  "progress_log": "docs/dev_plans/manual_demo/PROGRESS_LOG.md",
  "docs_dir": "docs/dev_plans/manual_demo",
  "defaults": {
    "emoji": "🧪",
    "agent": "LabTech"
  }
}
```

---

## 2. Sub-System Breakdown

### 2.1 Required Fields
**name** (string): Unique project identifier (used for lookups)
**root** (string): Project root directory (relative or absolute path)
**progress_log** (string): Path to PROGRESS_LOG.md file

### 2.2 Optional Fields
**docs_dir** (string): Dev plan directory (usually `docs/dev_plans/<name>/`)
**defaults** (object): Default values for log entries
  - **emoji** (string): Default emoji for entries (e.g., "🧪")
  - **agent** (string): Default agent name (e.g., "LabTech")

### 2.3 Template Variables (Implicit)
**Not in file**: `{project_slug}`, `{docs_dir}`, `{progress_log}` available for log_config.json resolution

---

## 3. Modularization Notes

### Legacy System (Deprecated but Not Removed)
**Status**: Project configs are LEGACY—new projects use `scribe_projects` DB table
**Why they still exist**: Backwards compatibility for pre-registry projects
**Migration path**: `set_project()` creates DB row, JSON config is optional

### NOT Extractable (Intentionally Simple)
**Why JSON configs should stay**:
- **Version control**: Projects can be committed to repo
- **Human-readable**: Easy to edit manually
- **Backwards compatible**: Pre-registry projects still work

---

## 4. Implicit Contracts

### Contract 1: Name Must Match Filename (Convention)
**Assumption**: `manual_demo.json` contains `"name": "manual_demo"`
**Violation consequence**: Confusing mismatches (file vs name)
**Why this is convention**: No enforcement, just best practice

### Contract 2: Paths Relative to SCRIBE_ROOT
**Assumption**: Relative paths resolved relative to `settings.project_root`
**Violation consequence**: Absolute paths work but break portability
**Why this matters**: Projects should be relocatable

### Contract 3: Dual Source of Truth (JSON OR DB)
**Assumption**: Project can exist in JSON config OR scribe_projects table (or both)
**Violation consequence**: Priority: DB > JSON (DB wins if both exist)
**Why this is confusing**: Two places to look for project metadata

### Contract 4: defaults.emoji and defaults.agent are Optional
**Assumption**: If missing, tools fall back to STATUS_EMOJI["info"] and no agent
**Violation consequence**: Tools handle missing defaults gracefully
**Why this works**: Defaults are truly optional (not required)

---

## 5. Token Analysis

**Direct output**: 0 tokens (config files don't produce output)
**Indirect impact**: None (loaded silently)

---

## 6. Error Handling Architecture

### Policy: Silent Fallback if File Missing
**Pattern**: `load_project_config(name)` returns `None` if JSON missing
**Why intentional**: Project may exist in DB only (JSON is legacy)

### Policy: JSON Parse Errors Propagate
**Pattern**: Invalid JSON raises `json.JSONDecodeError`
**Why intentional**: Better to fail than load corrupted config

---

## 7. Known Issues

### CONFIG-PROJ-001: Dual Source of Truth (P1 - Architecture Smell)
**Location**: JSON configs vs scribe_projects DB table
**Evidence**: Tools check DB first, fall back to JSON (logging_utils.py:108-133)
**Impact**:
- Confusion: which source is canonical?
- Sync issues: DB and JSON can diverge
- Maintenance burden: update both places

**Recommendation**: Deprecate JSON configs
- Phase 1: Add migration tool to import JSON → DB
- Phase 2: Mark JSON configs as deprecated (emit warnings)
- Phase 3: Remove JSON loading code (DB-only)

### CONFIG-PROJ-002: No Validation (P2)
**Location**: config/projects/*.json files
**Evidence**: No schema validation, arbitrary fields allowed
**Impact**: Typos in field names cause silent failures
**Recommendation**: JSON schema validation (like log_config.json SPEC-CONFIG-LOG-001)

---

## 8. Implementation Specs

### SPEC-CONFIG-PROJ-001: Deprecate JSON Project Configs

**Problem**: Dual source of truth (JSON vs DB) causes confusion and sync issues
**Location**: config/projects/*.json + loading code in tools/project_utils.py

```yaml
spec_id: SPEC-CONFIG-PROJ-001
title: Migrate JSON project configs to database-only
priority: P1 (architecture cleanup)
files:
  - config/projects/*.json (all files)
  - tools/project_utils.py (load_project_config)
  - shared/logging_utils.py:108-133 (fallback logic)
changes:
  - phase: 1_migration_tool
    action: create_script
    path: scripts/migrate_json_to_db.py
    content: |
      # Read all config/projects/*.json
      # For each project:
      #   - Check if row exists in scribe_projects table
      #   - If not, insert from JSON config
      #   - Log migration result

  - phase: 2_deprecation_warnings
    action: add_warnings
    files:
      - tools/project_utils.py
    content: |
      import warnings

      def load_project_config(name):
          warnings.warn(
              f"JSON project configs deprecated: {name}.json will be ignored in future releases. "
              "Use set_project() to create database-backed projects.",
              DeprecationWarning
          )
          # ... existing JSON loading logic

  - phase: 3_removal
    action: delete_code
    timeline: "2-3 releases after phase 2"
    files:
      - config/projects/*.json (delete all)
      - tools/project_utils.py (remove load_project_config)
      - shared/logging_utils.py:123-133 (remove JSON fallback)

benefits:
  - Single source of truth (DB only)
  - No sync issues between JSON and DB
  - Simpler code (no fallback logic)
  - Better performance (no file I/O for config)
risks:
  - Breaking change for projects relying on JSON configs
  - Need migration period (3+ releases)
migration_strategy:
  - Release 1: Add migration tool + warnings
  - Release 2-3: Warnings only (grace period)
  - Release 4: Remove JSON support entirely
```

---

## Cross-Cutting Concerns

- **[BUCKET:config]** Per-project configuration (legacy system)
- **[BUCKET:persistence]** Dual source of truth with DB (architecture smell)
- **[BUCKET:state]** Project metadata storage

**Impact**: JSON configs are LEGACY. New projects use `scribe_projects` DB table. JSON loading is backwards compatibility only—should be deprecated.

**Relationship to other config**: Works alongside `settings.py` (global) and `log_config.json` (multi-log), but conflicts with `scribe_projects` DB table (dual source of truth).
