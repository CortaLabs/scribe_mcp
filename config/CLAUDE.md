# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🚨 COMMANDMENTS - CRITICAL RULES


**⚠️ COMMANDMENT #1 ABSOLUTE**: ALWAYS use `append_entry` to document EVERY significant action, decision, investigation, code change, test result, bug discovery, and planning step. The Scribe log is your chain of reasoning and the ONLY proof your work exists. If it's not Scribed, it didn't fucking happen.

**What Gets Logged (Non-Negotiable):**
- 🔍 Investigation findings and analysis results
- 💻 Code changes (what was changed and why)
- ✅ Test results (pass/fail with context)
- 🐞 Bug discoveries (symptoms, root cause, fix approach)
- 📋 Planning decisions and milestone completions
- 🔧 Configuration changes and deployments
- ⚠️ Errors encountered and recovery actions
- 🎯 Task completions and progress updates

**Single Entry Mode** - Use for real-time logging:
```python
await append_entry(
    message="Discovered authentication bug in JWT validation",
    status="bug",
    agent="DebugAgent",
    meta={"component": "auth", "severity": "high", "file": "auth.py:142"}
)
```

**Bulk Entry Mode** - Use when you realize you missed logging steps:
```python
await append_entry(items=json.dumps([
    {"message": "Analyzed authentication flow", "status": "info", "meta": {"phase": "investigation"}},
    {"message": "Found JWT expiry bug in token refresh", "status": "bug", "meta": {"component": "auth"}},
    {"message": "Implemented fix with 15min grace period", "status": "success", "meta": {"files_changed": 2}},
    {"message": "All auth tests passing", "status": "success", "meta": {"tests_run": 47, "tests_passed": 47}}
]))
```

**Why This Matters:**
- Creates auditable trail of ALL decisions and changes
- Enables debugging by reviewing reasoning chain
- Prevents lost work and forgotten context
- Allows other agents to understand what was done and why
- Makes project state queryable and analyzable

**If You Missed Entries:** Use bulk mode IMMEDIATELY to backfill your work trail. NEVER let gaps exist in the Scribe log - every action must be traceable. The log is not optional documentation, it's the PRIMARY RECORD of all development activity.


---

## 🏗️ MCP_SPINE ARCHITECTURE

### **MCP_SPINE: The Multi-MCP Infrastructure Spinal Cord**

MCP_SPINE is designed to house **multiple independent MCP servers** as the central infrastructure for all our Model Context Protocol tools. Think of it as a spinal cord connecting and organizing various MCP capabilities.

**Architecture Principles:**
- **Independent MCP Servers**: Each subdirectory (like `scribe_mcp`) is a self-contained MCP server
- **Shared Infrastructure**: Common patterns, utilities, and architectural decisions
- **Loose Coupling**: Servers can operate independently or together
- **Scalable Design**: Easy to add new MCP servers without disrupting existing ones

### **Directory Structure**
```
MCP_SPINE/
├── scribe_mcp/          # Project documentation and logging MCP server
├── code_analyzer_mcp/   # Future: Code analysis MCP server
├── test_runner_mcp/     # Future: Automated testing MCP server
├── deploy_mcp/          # Future: Deployment automation MCP server
├── shared_utils/        # Future: Common utilities for all MCP servers
└── docs/               # Shared documentation and architectural guides
```

**Key Design Decision**: MCP_SPINE is **NOT** a Python package - it's a collection of independent MCP servers. Each server manages its own dependencies and imports.

---

## 📋 IMPORT BEST PRACTICES

### **Understanding the Import Structure**

**Critical**: MCP_SPINE is NOT a Python module - it's a directory containing independent MCP servers. Each MCP server handles its own imports internally.

**❌ WRONG Import Patterns:**
```python
# These will FAIL because MCP_SPINE is not a Python module
from scribe_mcp.tools.append_entry import append_entry
import MCP_SPINE.scribe_mcp.config.settings as settings
```

**✅ CORRECT Import Patterns:**
```python
# When working within an MCP server
from scribe_mcp.tools.append_entry import append_entry
import scribe_mcp.config.settings as settings

# When writing tests, add MCP_SPINE to Python path first
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### **Test File Import Patterns**

**Standard Test Pattern:**
```python
#!/usr/bin/env python3
"""Test file for MCP server functionality."""

import sys
from pathlib import Path

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Now import from the specific MCP server
from scribe_mcp.tools.health_check import health_check
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### **Working Directory Context**

**When running code from different contexts:**

1. **From MCP server root (MCP_SPINE/scribe_mcp/):**
   ```python
   # Direct imports work
   from tools.append_entry import append_entry
   ```

2. **From MCP_SPINE root:**
   ```python
   # Use full server module path
   from scribe_mcp.tools.append_entry import append_entry
   ```

3. **From tests directory:**
   ```python
   # Add parent directories to path
   sys.path.insert(0, str(Path(__file__).parent.parent))
   from scribe_mcp.tools.append_entry import append_entry
   ```

### **Environment Variables for Context**

**Set SCRIBE_ROOT when working across directories:**
```python
import os
from pathlib import Path

# Set the MCP_SPINE root for context
os.environ["SCRIBE_ROOT"] = str(Path(__file__).parent.parent)
```

### **Common Import Error Patterns & Solutions**

| Error Pattern | Cause | Solution |
|-------------|-------|----------|
| `ModuleNotFoundError: No module named 'MCP_SPINE'` | Trying to import MCP_SPINE as Python module | Use direct server module imports |
| `ImportError: attempted relative import beyond top-level package` | Wrong Python path context | Add correct directories to sys.path |
| `ModuleNotFoundError: No module named 'scribe_mcp'` | Python can't find the server module | Add MCP_SPINE to Python path |

### **Best Practices Checklist**

**Before writing imports:**
- [ ] Identify if you're in the MCP server, tests, or external context
- [ ] Add appropriate paths to sys.path if needed
- [ ] Use direct server module paths (not MCP_SPINE prefixed)
- [ ] Test imports before committing code

**When creating new files:**
- [ ] Determine the correct import context
- [ ] Use relative imports within the same server
- [ ] Use absolute imports from the server root
- [ ] Add path setup for test files

**When moving files:**
- [ ] Update import statements to match new context
- [ ] Verify Python path setup
- [ ] Test from different working directories

---

**⚠️ COMMANDMENT #11 CRITICAL**: NEVER write replacement files. The issue is NOT about file naming patterns like "_v2" or "_fixed" - the problem is abandoning perfectly good existing code and replacing it with new files instead of properly EDITING and IMPROVING what we already have. This is lazy engineering that creates technical debt and confusion.

**ALWAYS work with existing files through proper edits. NEVER abandon current code for new files when improvements are needed.**
---
**⚠️ COMMANDMENT #12 CRITICAL**: Follow proper project structure and best practices. Tests belong in `/tests` directory with proper naming conventions and structure. Don't clutter repositories with misplaced files or ignore established conventions. Keep the codebase clean and organized.

Violations = INSTANT TERMINATION. Reviewers who miss commandment violations get 80% pay docked. Nexus coders who implement violations face $1000 fine.

---

## Common Development Commands

### Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r MCP_SPINE/requirements.txt
```

**Important**: The virtual environment must be activated for all CLI and server commands.

### Running the Scribe MCP Server
```bash
# Primary method - stdio server for MCP clients
python -m MCP_SPINE.scribe_mcp.server

# With environment variables for PostgreSQL backend
export SCRIBE_ROOT=/home/austin/projects/MCP_SPINE
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL=postgresql://user:pass@host/db
python -m MCP_SPINE.scribe_mcp.server
```

### Testing
```bash
# Run all tests
pytest MCP_SPINE/tests

# Run specific test file
pytest MCP_SPINE/tests/test_tools.py
pytest MCP_SPINE/tests/test_utils.py

# Run standalone test files (when pytest doesn't work)
python -m MCP_SPINE.tests.test_agent_manager
python -m MCP_SPINE.tests.test_tools

# Smoke test the MCP server
python MCP_SPINE/scripts/test_mcp_server.py
```

### CLI Companion Scripts
```bash
# Run with virtual environment activated and correct Python path
source .venv/bin/activate

# List available projects
python -m MCP_SPINE.scripts.scribe --list-projects

# Append a log entry (primary usage)
python -m MCP_SPINE.scripts.scribe "Your message here" --status success --meta phase=development

# Append with custom agent and metadata
python -m MCP_SPINE.scripts.scribe "Fixed authentication bug" --status bug --agent DebugBot --meta component=auth,tests=fixed

# Use specific project configuration
python -m MCP_SPINE.scripts.scribe "Database migration completed" --project my_project --status success

# Dry run to preview entry
python -m MCP_SPINE.scripts.scribe "Test message" --dry-run
```

## Doc Management & Multi-Log Logging

### `manage_docs`
- Structured editor for ARCH/PHASE/CHECKLIST docs with atomic writes, dry-run previews, and checklist status toggles.
- Requires anchors like `<!-- ID: problem_statement -->` so section replacements are deterministic.
- Every successful edit is tracked in the `doc_changes` table and automatically logged to the `doc_updates` log via `append_entry(log_type="doc_updates")`.

### Log routing via `config/log_config.json`
- `append_entry` (and `scripts/scribe.py --log ...`) accept a `log_type` key; defaults ship with `progress`, `doc_updates`, `security`, and `bugs` (each with their own metadata requirements).
- Repo-level config defines paths like `{docs_dir}/SECURITY_LOG.md` or `{docs_dir}/BUG_LOG.md` and enforces metadata (e.g., `severity`, `component`).
- Add more logs by editing `config/log_config.json` with path templates using `{project_slug}`, `{docs_dir}`, `{progress_log}` placeholders.

## Architecture Overview

### Core Components

**Scribe MCP Server** (`MCP_SPINE/scribe_mcp/server.py`)
- MCP server implementation exposing tools for project documentation and progress logging
- Hybrid storage backend: SQLite (default) or PostgreSQL (optional)
- Graceful fallback when MCP SDK is not installed

**Tools Architecture** (`MCP_SPINE/scribe_mcp/tools/`)
- `set_project.py` - Project creation and documentation bootstrapping
- `append_entry.py` - Progress log entry creation with metadata
- `list_projects.py` - Project discovery and management
- `get_project.py` - Active project context retrieval
- `read_recent.py` - Recent log entries with filtering
- `query_entries.py` - Advanced log searching and filtering
- `generate_doc_templates.py` - Documentation template generation
- `rotate_log.py` - Log archiving and cleanup
- `search.py` - Multi-file codebase search (grep/rg replacement)
- `edit_file.py` - Safe file editing with exact string replacement

**Storage Layer** (`MCP_SPINE/scribe_mcp/storage/`)
- `base.py` - Abstract storage interface
- `sqlite.py` - SQLite backend implementation
- `postgres.py` - PostgreSQL backend with asyncpg
- `models.py` - Data models and schemas

**State Management** (`MCP_SPINE/scribe_mcp/state/`)
- `manager.py` - Project state and configuration management
- `state.json` - Persistent state storage

### Project Structure

- **MCP_SPINE/** - Main package containing the Scribe MCP server
- **config/projects/** - Per-project JSON configuration files
- **docs/dev_plans/** - Auto-generated documentation per project:
  - `ARCHITECTURE_GUIDE.md` - System design and technical blueprint
  - `PHASE_PLAN.md` - Development roadmap with phases and tasks
  - `CHECKLIST.md` - Verification ledger with acceptance criteria
  - `PROGRESS_LOG.md` - Append-only audit trail (UTC timestamps)
- **example_code/modules/** - Reusable Rich UI components (menus, tables, progress bars)
- **scripts/** - CLI utilities and test harnesses

### Key Design Patterns

**Hybrid Storage**: Tools abstract over storage backends via the `StorageBackend` protocol, supporting both SQLite (zero-config) and PostgreSQL (shared/team usage).

**Project-Centric Documentation**: Each project gets its own documentation suite under `docs/dev_plans/<slug>/`. The `set_project` tool automatically bootstraps this structure.

**Metadata-Driven Logging**: All log entries support structured metadata for traceability:
- Common keys: `phase`, `checklist_id`, `component`, `tests`, `confidence`
- Format: key=value pairs in CLI, dict in MCP tools
- Essential for linking work to specific tasks and requirements

**Graceful Degradation**: The server provides helpful error messages and maintains functionality even when optional dependencies (MCP SDK, PostgreSQL) are missing.

## Configuration

### Environment Variables
- `SCRIBE_ROOT` - Root directory for project configurations (auto-detected as MCP_SPINE directory)
- `SCRIBE_STORAGE_BACKEND` - Storage backend: `sqlite` (default) or `postgres`
- `SCRIBE_DB_URL` - PostgreSQL connection URL (required for postgres backend)
- `SCRIBE_DEFAULT_PROJECT` - Default project name
- `SCRIBE_REMINDER_DEFAULTS` - JSON blob for reminder behavior customization
- `SCRIBE_REMINDER_IDLE_MINUTES` - Gap before new work session resets (default: 45)
- `SCRIBE_REMINDER_WARMUP_MINUTES` - Grace period after resuming (default: 5)

### Project Configuration Files
Store per-project settings in `config/projects/<project_name>.json`:
```json
{
  "name": "project_name",
  "root": "/path/to/project",
  "progress_log": "docs/dev_plans/project_name/PROGRESS_LOG.md",
  "defaults": {
    "emoji": "🧪",
    "agent": "AgentName",
    "reminder": {
      "log_warning_minutes": 15,
      "tone": "friendly"
    }
  }
}
```

## MCP Integration

The Scribe MCP server exposes these tools (all return reminders about stale docs, overdue logging, and project state):

### 🔧 Tool API Reference

#### Core Project Management
**`set_project`** - Create/select project and bootstrap docs (auto-generates all 4 doc files)
```python
# Required: name (string)
# Optional: root (string), progress_log (string), defaults (dict)
await set_project(name="My Project")
await set_project(name="My Project", defaults={"emoji": "🧪", "agent": "MyAgent"})
```

#### Project Naming Guidelines

**⚠️ IMPORTANT:** The Scribe MCP system automatically detects and skips temp/test projects during project auto-selection.

**Avoid These Patterns in Real Project Names:**

**Reserved Keywords:**
- `test`, `temp`, `tmp`, `demo`, `sample`, `example`
- `mock`, `fake`, `dummy`, `trial`, `experiment`

**Reserved Patterns:**
- UUID suffixes: `project-xxxxxxxx` (8+ chars)
- Numeric suffixes: `project-123`, `test_001`

**Good Real Project Names:**
- `my-project`, `production-app`, `client-work-2024`
- `enhanced-log-rotation`, `authentication-system`

**Temp/Test Names (will be auto-skipped):**
- `test-project`, `temp-project`, `demo-project-123`
- `history-test-711f48a0`, `project-456`

See the Architecture Guide for complete details on temp project detection logic.

**`get_project`** - Get current project context and configuration
```python
# No parameters
await get_project()
```

**`list_projects`** - Discover available projects and their configurations
```python
# No parameters
await list_projects()
```

#### Logging Operations
**`append_entry`** - **PRIMARY TOOL** - Add structured log entries with metadata
```python
# Single entry mode:
# Required: message (string)
# Optional: status (info|success|warn|error|bug|plan), emoji (string), agent (string), meta (dict), timestamp_utc (string)
await append_entry(message="Fixed authentication bug", status="success", meta={"phase": "bugfix", "component": "auth"})
await append_entry(message="Database migration completed", status="info", emoji="🗄️")

# Bulk entry mode (NEW):
# Required: items (JSON string array)
# Each item requires: message (string)
# Each item optional: status, emoji, agent, meta, timestamp_utc
await append_entry(items=json.dumps([
  {"message": "First task completed", "status": "success"},
  {"message": "Bug found in auth module", "status": "bug", "agent": "DebugBot"},
  {"message": "Database migration finished", "status": "info", "meta": {"component": "database", "phase": "deployment"}}
]))
```

#### Query and Analysis
**`read_recent`** - Retrieve recent log entries (⚠️ currently has parameter type issues)
```python
# Optional: n (int, default 50), filter (dict)
# NOTE: n parameter currently broken, returns all recent entries
await read_recent()
# await read_recent(n=5)  # Currently fails with type error
```

**`query_entries`** - Advanced log searching and filtering
```python
# Optional: project (string), start (string), end (string), message (string), message_mode (string), case_sensitive (bool)
await query_entries(message="bug", message_mode="substring")
await query_entries(start="2025-10-23", end="2025-10-24")
```

#### Documentation Management
**`generate_doc_templates`** - Create/update documentation templates for a project
```python
# Required: project_name (string)
# Optional: author (string), overwrite (bool), documents (list), base_dir (string)
await generate_doc_templates(project_name="My Project", author="MyAgent")
await generate_doc_templates(project_name="My Project", documents=["architecture", "phase_plan"])
```

**`rotate_log`** - Archive current progress log and start fresh file
```python
# No parameters - archives current project's log automatically
await rotate_log()
```

### 📋 Usage Pattern
1. **Initialize**: `set_project(name="ProjectName")` to select/initialize project (auto-bootstraps docs)
2. **Log Everything**: `append_entry()` after every meaningful action or discovery
3. **Add Context**: Include metadata like `phase`, `checklist_id`, `component` for traceability
4. **Review Progress**: Use `read_recent()` or `query_entries()` to review progress
5. **Maintain Docs**: Update `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md` as plans evolve

---

## 🚨 IMPORT RULES - CRITICAL TO UNDERSTAND

### **When to Use Which Import Pattern**

**✅ Test files in tests/ directory:**
```python
# ALWAYS add MCP_SPINE to Python path first, then import directly
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.append_entry import append_entry
```


## 🧪 TESTING GUIDE

### **Running Tests**

**All Functional Tests (Default):**
```bash
pytest
# OR
pytest -q
```
- Runs all 69 functional tests
- Performance tests automatically excluded for speed
- Clean output with only failure details

**Performance Tests (When Needed):**
```bash
pytest -m performance
# OR
pytest -m performance -v
```
- Runs optimized performance test suite (0.5MB, 1MB, 2MB files)
- Measures rotation throughput, integrity verification, memory usage
- All temp files automatically cleaned up

### **Test Organization:**
- **Functional Tests**: 69 tests covering core functionality
- **Performance Tests**: 1 comprehensive test with multiple file sizes
- **Performance Tests**: Always behind `-m performance` flag for speed

**Performance Test Features:**
- Reasonable file sizes (max 2MB instead of 50MB)
- Automatic cleanup of all temporary files
- Comprehensive metrics collection and JSON results saving
- Integrity verification and throughput benchmarking
