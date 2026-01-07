# CLAUDE.md

**Scribe MCP v2.1.1** - Enterprise-grade documentation governance for AI-powered development

This file provides operational guidance to Claude Code (claude.ai/code) when working with this repository.

---

## 🚨 Required Reading (MANDATORY)

Claude Code MUST complete these steps before doing any work:

1. **Invoke the `scribe-mcp-usage` skill** using the Skill tool:
   ```
   /scribe-mcp-usage
   ```
   This loads the minimal enforceable tool-and-logging contract. Do NOT just read the SKILL.md file - invoke the skill properly.

2. **Read `AGENTS.md`** for cross-agent governance + repo-wide commandments

3. **For parameter discovery:** Use `scribe.read_file(mode="search", query="<search_term>", path="docs/Scribe_Usage.md")` to find tool params/patterns

4. **If files are missing:** STOP and report the failure. Do not guess tool parameters.

### 🔒 File Reading Policy (NON-NEGOTIABLE)

**MANDATORY FOR EVERYONE** - orchestrator, subagents, all roles:

- ALL file content reads MUST use `scribe.read_file` (modes: scan_only, chunk, page, line_range, search)
- Do NOT use `cat`, `rg`, or native `Read` tool for file contents
- `rg --files` is allowed ONLY for filename discovery
- **Exception:** Native Read ONLY if Scribe MCP is unavailable or errors irrecoverably - must state exception explicitly
- Default to `format="readable"` unless debugging requires structured output

This is not optional. This is not "when convenient". This applies to **Claude Code orchestrator** and all subagents.

---

## 👥 Agent Identity & Naming

For session concurrency and log clarity:

- **Orchestrator (Claude Code)**: Must use `agent="Orchestrator"` with all Scribe tools
- **Subagents**: Must use unique agent names per session:
  - Examples: `Coder-9289`, `ResearchAgent-A`, `ReviewAgent-Phase3`
  - Prevents log collision when multiple agents work in parallel
- **Codex (OpenAI)**: Must use `agent="Codex"`

The orchestrator MUST pass the current `project_name` to every subagent to prevent cross-project logging confusion.

---

## 🎯 OPERATIONAL CHECKLIST (MANDATORY BEFORE ALL WORK)

**Before starting any task, Claude Code MUST execute these steps in order:**

### Step 1: Context Rehydration (COMMANDMENT #0)
```python
# Check progress log - last 5-10 entries minimum
read_recent(n=10, format="readable")

# For targeted history or architectural decisions
query_entries(message="<search_term>", format="readable")
```
**Purpose:** Understand what's been done, what failed, current project state.
**Violation:** Skipping this = working blind, repeating mistakes, breaking continuity.

### Step 2: Project Confirmation (COMMANDMENT #0)
```python
# Verify active project
get_project(format="readable")
```
**If no active project or wrong project:**
- Creating new feature/fix: Create dedicated project with `set_project(name="<descriptive_name>")`
- Continuing work: Use `set_project(name="<existing_project>")` to activate
- Unsure: ASK USER which project to use

### Step 3: Intent Logging (COMMANDMENT #1)
```python
# Log what you're about to do BEFORE doing it
append_entry(
    message="Starting <task_description>",
    status="info",
    agent="Orchestrator",
    meta={"task": "<task>", "approach": "<approach>"}
)
```
**Purpose:** Create audit trail of decisions, not just results.
**Violation:** If it's not logged, it didn't happen.

### Step 4: Agent Spawning Rules (PROTOCOL ENFORCEMENT)

**When spawning subagents, you MUST provide project context:**

**Option A - Continue existing project:**
```python
Task(
    subagent_type="<agent_type>",
    prompt="<instructions>. Use project_name='<current_project_from_get_project>'"
)
```

**Option B - Create new project for new work:**
```python
Task(
    subagent_type="<agent_type>",
    prompt="Create new project first: set_project(name='<descriptive_name>'). Then <instructions>."
)
```

**NO OTHER OPTIONS.** Spawning without project context = protocol violation.

### Step 5: Work Logging Cadence (COMMANDMENT #1)

**During work, log after every 2-3 significant actions:**
```python
append_entry(
    message="<what_was_done>",
    status="success|info|warn|error",
    agent="Orchestrator",
    meta={"files_changed": [...], "tests": "<status>"}
)
```

**What counts as "significant":**
- File edits (every 2-3 files)
- Test runs
- Bug discoveries
- Architecture decisions
- Blockers encountered

### Enforcement

**If you skip any step:**
1. STOP immediately
2. Complete the skipped step(s)
3. Log the violation with `append_entry(status="warn")`
4. Resume work

**No freestyling. No shortcuts. Follow the checklist.**

---

## 📁 Project Selection (Dynamic Resolution)

**Never hardcode project names in this file or subagent prompts.**

### Orchestrator Workflow:

1. **Check active project:** Call `get_project()`
2. **If no project active:** Call `set_project(name=..., root=...)`
3. **Pass resolved project name** to ALL subagents in their prompts
4. **Rehydrate context when needed:**
   - Project mode: `read_recent(limit=5)` or `query_entries()` (last 5-20 entries)
   - Cross-project/global: `query_entries(search_scope="global")` or `"all_projects"`
   - Use when: fresh context window, unsure of next steps, need architectural decisions

---

## 🚨 Database Schema Management (CRITICAL)

**MANDATORY RULE — VIOLATION = INSTANT REJECTION**

> **NEVER use direct SQL commands (sqlite3, ALTER TABLE, etc.) to modify database schema. ALL schema changes MUST go through migration functions in the code.**

### Rationale

This is a **production system** used by multiple users. Direct SQL modifications:
- ❌ Only affect your local database
- ❌ Don't propagate to other users
- ❌ Break on fresh installations
- ❌ Create schema drift and inconsistencies
- ❌ Are not version-controlled or auditable

### Required Behavior

**For schema changes:**
1. ✅ Add migration code to `storage/sqlite.py` or `storage/postgres.py`
2. ✅ Use `_ensure_column()` for adding columns
3. ✅ Use `_ensure_index()` for adding indexes
4. ✅ Create migration functions like `migrate_add_docs_json_column()`
5. ✅ Call migrations from `_initialise()` method
6. ✅ Make migrations idempotent (safe to run multiple times)

**Example - CORRECT way:**
```python
# In storage/sqlite.py _initialise() method:
await self._ensure_column("scribe_projects", "status", "TEXT DEFAULT 'planning'")
await self._ensure_column("scribe_projects", "docs_json", "TEXT")
```

**Example - WRONG way:**
```bash
# ❌ NEVER DO THIS
sqlite3 db.db "ALTER TABLE scribe_projects ADD COLUMN status TEXT;"
```

### Prohibited Actions

- ❌ Running `sqlite3` commands directly on database files
- ❌ Using `ALTER TABLE` via Bash
- ❌ Manual database modifications
- ❌ Schema changes not in version control

### When You Need Schema Changes

If columns are missing:
1. Check if migration exists in `storage/sqlite.py` (lines 1076-1089, 1112-1113)
2. If migration exists but hasn't run: **Restart MCP server**
3. If migration doesn't exist: **Add migration code, commit, then restart**
4. Verify schema: Check `PRAGMA table_info(table_name)` after restart

**This is NON-NEGOTIABLE. Schema changes MUST be in code, not ad-hoc SQL.**

---

## 🔁 Orchestration Protocol

**Workflow:** 1️⃣ Research → 2️⃣ Architect → 3️⃣ Review → 4️⃣ Code → 5️⃣ Review

**Core Principle:** All work occurs within a dev plan project initialized via `set_project(name="<project_name>")`. The project name must be passed to every subagent.

**Quality Gates:** ≥93% required to proceed between stages. Agents must FIX existing work, never replace files.

### Subagents:

- **Research** (Stage 1): Deep investigation with cross-project search → `RESEARCH_*.md`
- **Architect** (Stage 2): Creates `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`
- **Review** (Stages 3 & 5): Adversarial QC, grades agents, validates ≥93%
- **Coder** (Stage 4): Implements design, logs every 2-5 meaningful changes
- **Bug Hunter** (Auxiliary): Pattern analysis, structured bug reports

### Agent Scribe Requirements:

| Agent | Scribe Name | Must Log |
|-------|-------------|----------|
| Orchestrator | `Orchestrator` | Phase transitions, agent dispatches, decisions |
| Research Agent | `ResearchAgent` | Findings, analysis, sources, confidence |
| Architect Agent | `ArchitectAgent` | Design decisions, trade-offs, constraints |
| Review Agent | `ReviewAgent` | Grades, pass/fail, issues found |
| Coder Agent | `CoderAgent` | Every 3 edits, test results, bugs |
| Bug Hunter | `BugHunterAgent` | Bug lifecycle, root cause, fixes |

---

## 🎯 Orchestrator Responsibilities

Claude Code (orchestrator) must:

1. **Unique agent names:** Assign unique agent names per subagent for session concurrency
2. **Log phase transitions:** `append_entry(agent="Orchestrator", message="Starting Phase 2: Architecture", status="info")`
3. **Enforce quality gates:** No progression without ≥93% review score
4. **Re-dispatch failing agents:** Tell agents to FIX existing docs/code, never REPLACE
5. **Rehydrate context first:** Use `read_recent()` or `query_entries()` before major decisions
6. **Pass project name:** Include `project_name="<current_project>"` in every subagent prompt

---

## 🏗️ Architect Agent Mode Selection (CRITICAL)

**The Architect Agent has TWO distinct modes - you MUST specify which one:**

### Orchestrator Preflight:

Before dispatching Architect Agent:
1. Check if root managed docs already exist for the project
2. If they exist → **Mode 2 ONLY** (sub-plan in `/architecture/<slug>/`)
3. If they do not exist → **Mode 1** scaffold is allowed
4. Failure to specify mode = assumed overwrite risk

### Mode 1: NEW PROJECT SCAFFOLD

**When to use:**
- First time creating project with `set_project()`
- NO existing ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md
- Need initial template documents from scratch

**How to invoke:**
```
"Create initial project scaffold for <project_name>. This is a NEW project with no existing
architecture documents. Generate template ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, and
CHECKLIST.md based on the research."
```

### Mode 2: SUB-PLAN ARCHITECTURE

**When to use:**
- Project ALREADY EXISTS with architecture documents
- Adding NEW feature/fix to existing project
- Existing docs contain prior work that must be preserved

**How to invoke:**
```
"Create sub-plan architecture for <feature_name> in project <project_name>. This is an
EXISTING project with detailed managed docs - NEVER overwrite them. Create new architecture
documents in /architecture/<sub_plan_slug>/ directory:
- <SLUG>_ARCHITECTURE_GUIDE.md
- <SLUG>_PHASE_PLAN.md
- <SLUG>_CHECKLIST.md

Existing architecture documents contain <previous_feature> work that must be preserved untouched."
```

**Sub-Plan Directory Structure:**
```
.scribe/docs/dev_plans/<project>/
├── ARCHITECTURE_GUIDE.md         ← NEVER OVERWRITE (original project architecture)
├── PHASE_PLAN.md                 ← NEVER OVERWRITE (original project phases)
├── CHECKLIST.md                  ← NEVER OVERWRITE (original project checklist)
└── architecture/
    └── <sub_plan_slug>/          ← NEW SUB-PLAN GOES HERE
        ├── <SLUG>_ARCHITECTURE_GUIDE.md
        ├── <SLUG>_PHASE_PLAN.md
        └── <SLUG>_CHECKLIST.md
```

---

## 🚨 Commandments (Critical Failure Modes)

### Commandment #0: Progress Log First
Before starting ANY work, rehydrate context with `read_recent()` or `query_entries()`. The progress log is the source of truth for project state.

### Commandment #0.5: Infrastructure Primacy
NEVER create parallel or replacement files (e.g., enhanced_*, *_v2, *_new). You must modify/extend/refactor existing components directly. Replacing working modules = immediate failure.

### Commandment #1: Log Everything
ALWAYS use `append_entry` to document EVERY significant action, decision, investigation, code change, test result, bug discovery, and planning step. If it's not Scribed, it didn't happen.

### Commandment #2: Reasoning Traces
Every `append_entry` must include `meta.reasoning` with Three-Part Framework:
- `why`: decision point, underlying question
- `what`: constraints, alternatives rejected, constraint coverage
- `how`: methodology, steps taken, uncertainty remaining

### Commandment #3: No Replacement Files
The problem is abandoning existing code and replacing it with new files. ALWAYS work with existing files through proper edits. Never abandon current code for new files when improvements are needed.

### Commandment #4: Proper Project Structure
Tests belong in `/tests` directory with proper naming conventions. Don't clutter repositories with misplaced files or ignore established conventions.

### Commandment #5: Complete the Integration
If you build new infrastructure (DB tables, classes, methods), you MUST wire it to production code in THE SAME implementation phase. Infrastructure that only exists in tests is NOT DONE.

**Violations = INSTANT TERMINATION.**

---

## ✍️ `manage_docs` Usage Playbook

**Use `manage_docs` for ALL managed-document edits. Never hand-edit managed docs.**

### Common Safe Flows:

1. **Update a known section** (recommended for most edits)
   ```python
   manage_docs(action="replace_section", doc="architecture", section="<ID>", content="...")
   # If you don't know section IDs: manage_docs(action="list_sections", doc="architecture")
   ```

2. **Precision edits** (line-level)
   ```python
   # Preferred: structured patch
   manage_docs(action="apply_patch", doc="architecture", edit={...})

   # Or: explicit line range
   manage_docs(action="replace_range", doc="architecture", start_line=12, end_line=15, content="...")
   ```

3. **Checklists**
   ```python
   manage_docs(action="status_update", doc="checklist", section="<ID>",
               metadata={"status": "done", "proof": "..."})
   # If you don't know IDs: manage_docs(action="list_checklist_items", doc="checklist")
   ```

4. **Creating new managed docs**
   ```python
   # Research docs
   manage_docs(action="create_research_doc", doc_name="RESEARCH_<topic>_<YYYYMMDD>", metadata={...})

   # Bug reports
   manage_docs(action="create_bug_report", metadata={"category": "...", "slug": "...", ...})

   # New managed doc type
   manage_docs(action="create_doc", doc="<new_doc>", content="...", template="...")
   ```

**For exact params/edge cases:** Search `docs/Scribe_Usage.md` with `scribe.read_file(mode="search", query="manage_docs <action>")`.

---

## 🔧 Essential Tools Quick Reference

### Project Management
- `set_project(name)` - Initialize/select project (auto-bootstraps docs)
- `get_project()` - Get current context
- `list_projects()` - Discover projects (lifecycle, activity, doc hygiene)

### Logging (PRIMARY TOOL)
- `append_entry(message, status, meta)` - Single entry mode
- `append_entry(items=[{...}, {...}])` - Bulk entry mode

### Documentation
- `manage_docs(action, doc, ...)` - Atomic doc updates (see playbook above)
- `generate_doc_templates(project_name)` - Template scaffolding
- `rotate_log()` - Archive logs

### v2.1.1 NEW Tools
- `read_file(path, mode, include_dependencies, structure_filter, structure_page, structure_page_size)` - Repo-scoped file access with:
  - AST structure extraction (Python/Markdown/JS)
  - Full signatures with types, defaults, return types, line ranges
  - Method display under classes with async markers
  - Structure filtering (regex-based class/function search in scan_only mode)
  - **Structure pagination** (browse large classes/modules page-by-page, default: 10 items/page)
  - Dependency analysis with impact radius (blast radius)
  - Boundary enforcement (forbidden import detection)
  - Regex search (default mode, changed from literal)
  - SKILL.md urgent detection
- `scribe_doctor()` - Environment diagnostics
- `manage_docs(action="search")` - Semantic search across docs

### Format Options
All tools support `format` parameter:
- `readable` (default) - Clean display with actual newlines
- `structured` - Raw dict/JSON for programmatic parsing
- `compact` - Minimal dict for token conservation

### ANSI Color Policy
- **High-frequency tools** (`append_entry`, `set_project`): Colors OFF (hardcoded)
- **Display-heavy tools** (`read_file`, `read_recent`, `query_entries`): Config-driven (`.scribe/config/scribe.yaml`)

---

## 📋 Critical Import Patterns

**⚠️ MOST IMPORTANT:** MCP_SPINE is NOT a Python module!

**❌ WRONG - WILL FAIL:**
```python
from MCP_SPINE.scribe_mcp.tools.append_entry import append_entry
import MCP_SPINE.scribe_mcp.config.settings as settings
```

**✅ CORRECT - WILL WORK:**
```python
# When working within scribe_mcp server
from scribe_mcp.tools.append_entry import append_entry
import scribe_mcp.config.settings as settings

# When writing tests, add MCP_SPINE to Python path first
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scribe_mcp.storage.sqlite import SQLiteStorage
```

### Working Directory Context Awareness

1. **Inside scribe_mcp server** (`MCP_SPINE/scribe_mcp/`):
   ```python
   from tools.append_entry import append_entry  # Relative imports within server
   ```

2. **From MCP_SPINE root**:
   ```python
   from scribe_mcp.tools.append_entry import append_entry  # Full server module paths
   ```

3. **From tests directory**:
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent.parent))  # Add parent to path
   from scribe_mcp.tools.health_check import health_check
   ```

**Key Principle:** Each MCP server handles its own imports. Never import MCP_SPINE as if it were a package.

---

## 📚 Additional Resources

- **`AGENTS.md`** - Complete protocol details, commandments, MCP_SPINE architecture
- **`docs/Scribe_Usage.md`** - Comprehensive tool reference (all params, examples, edge cases)
- **`.codex/skills/scribe-mcp-usage/SKILL.md`** - Minimal enforceable contract

**When in doubt:** Search `Scribe_Usage.md` using `scribe.read_file(mode="search")` for the answer.

---

*Scribe MCP v2.1.1 - Operational guidance for Claude Code orchestration*
