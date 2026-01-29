# Scribe MCP Tool Contracts Reference
**Author:** ResearchAgent-ToolContracts
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-29 06:12 UTC
**Confidence:** 0.95

> Comprehensive reference for onboarding agents and projects to the Scribe MCP toolset. Every signature, parameter, and behavioral detail is grounded in actual source code from `scribe_mcp/tools/`.

---
## Executive Summary
<!-- ID: executive_summary -->

This document catalogs all 14+ Scribe MCP tools with their exact function signatures, parameter defaults, behavioral constraints, and error codes -- all verified from source code. It is intended as the canonical basis for creating instructional prompts that onboard agents in external projects to the Scribe toolset.

**Key Takeaways:**
- All tools require `agent: str` as first parameter for session isolation
- `manage_docs` has 7 primary actions, 5 deprecated aliases, and 7 hidden actions
- `edit_file` enforces read-before-edit at the tool level (not just policy)
- `read_file` has 5 modes with AST structure extraction and dependency analysis
- The file reading policy (read_file over cat, search over grep, edit_file over sed) is non-negotiable

---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-ToolContracts

**Investigation Window:** 2026-01-29

**Focus Areas:**
- [x] Protocol pipeline (5-stage workflow)
- [x] Complete tool signatures from source code
- [x] manage_docs deep dive (all actions)
- [x] read_file modes and behaviors
- [x] search tool parameters
- [x] edit_file enforcement and error codes
- [x] File reading policy rules
- [x] Drop-in snippet for external projects

---
## Findings
<!-- ID: findings -->

## 1. The Scribe Protocol Pipeline

Scribe operates within a 5-stage PROTOCOL workflow:

```
1. Research -> 2. Architect -> 3. Review -> 4. Code -> 5. Review
```

| Stage | Agent | Produces | Quality Gate |
|-------|-------|----------|-------------|
| 1 | Research Agent | `RESEARCH_*.md` documents, progress log entries | Confidence scores on all findings |
| 2 | Architect Agent | `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md` | Review Agent approval >= 93% |
| 3 | Review Agent | Pre-implementation review, feasibility validation | Pass/fail with grade |
| 4 | Coder Agent | Working code, `IMPLEMENTATION_REPORT.md` | Tests pass, code matches specs |
| 5 | Review Agent | Post-implementation review, agent grading | >= 93% to ship |

**Auxiliary:** Bug Hunter Agent for hard-to-solve bugs.

All agents MUST use `append_entry` to log every significant action. The progress log is the source of truth.

**Source:** `.claude/agents/` files, `AGENTS.md`, `CLAUDE.md`

---

## 2. Complete Tool Reference

Every tool requires `agent: str` as the first parameter. This is used for session isolation and audit trail.

### 2.1 Project Management Tools

#### `set_project` (tools/set_project.py:190)

**Purpose:** Register a project and set it as current context. Must be called before any other tool.

```python
async def set_project(
    agent: str,           # REQUIRED - agent name for session identity
    name: str,            # REQUIRED - project name (auto-normalizes hyphens/spaces to underscores)
    root: str,            # REQUIRED - repository root path
    progress_log: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
    author: Optional[str] = None,
    overwrite_docs: bool = False,
    expected_version: Optional[int] = None,  # Optimistic concurrency control
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    template: Optional[str] = None,
    auto_create_dirs: bool = True,
    skip_validation: bool = False,
    reminder_settings: Optional[Dict[str, Any]] = None,
    notification_config: Optional[Dict[str, Any]] = None,
    reset_reminders: bool = False,
    emoji: Optional[str] = None,
    bridge_id: Optional[str] = None,
    bridge_managed: bool = False,
    format: str = "readable",
) -> Dict[str, Any]
```

**Key behaviors:**
- Auto-creates `.scribe/docs/dev_plans/<name>/` directory structure
- Auto-bootstraps PROGRESS_LOG.md, ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md
- Project names normalize: `"my-project"` becomes `"my_project"`
- Idempotent: calling on existing project activates it without overwriting (unless `overwrite_docs=True`)

**When to use:** Always first. Every session starts with `set_project`.

---

#### `get_project` (tools/get_project.py:353)

```python
async def get_project(
    agent: str,
    project: Optional[str] = None,  # None = active project
    format: str = "structured",
    verbose: bool = False,          # Include recent log entries
) -> Dict[str, Any]
```

**When to use:** Verify current project context, check project state, get document inventory.

---

#### `list_projects` (tools/list_projects.py:183)

```python
async def list_projects(
    agent: str,
    limit: Optional[int] = 5,
    filter: Optional[str] = None,       # Case-insensitive name substring
    root: Optional[str] = None,         # Filter by repo root
    global_mode: bool = False,          # True = all repos
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_test: bool = False,
    page: int = 1,
    page_size: Optional[int] = None,
    status: Optional[List[str]] = None, # e.g. ['planning', 'in_progress']
    tags: Optional[List[str]] = None,
    order_by: Optional[str] = None,     # created_at|last_entry_at|last_access_at|total_entries
    direction: str = "desc",
    format: str = "readable",
) -> Dict[str, Any]
```

**When to use:** Discover existing projects, find project names before `set_project`.

---

### 2.2 Logging Tools

#### `append_entry` (tools/append_entry.py:1072)

**Purpose:** The primary logging tool. Every agent action MUST be logged here.

```python
async def append_entry(
    agent: str,              # REQUIRED
    message: str = "",       # Log message
    status: Optional[str] = None,  # info|success|warn|error|bug|plan
    emoji: Optional[str] = None,
    meta: Optional[Any] = None,    # Metadata dict (reasoning, files_touched, etc.)
    timestamp_utc: Optional[str] = None,
    items: Optional[str] = None,         # JSON string for bulk mode
    items_list: Optional[List[Dict[str, Any]]] = None,  # Direct list for bulk mode
    auto_split: bool = True,
    split_delimiter: str = "\n",
    stagger_seconds: int = 1,
    agent_id: Optional[str] = None,
    log_type: Optional[str] = "progress",  # progress|doc_updates|global
    priority: Optional[str] = None,    # critical|high|medium|low
    category: Optional[str] = None,    # decision|investigation|bug|implementation|test|milestone
    tags: Optional[List[str]] = None,
    confidence: Optional[float] = None,  # 0.0-1.0
    config: Optional[AppendEntryConfig] = None,
    format: str = "readable",
) -> Union[Dict[str, Any], str]
```

**Modes:**
- **Single entry:** Just pass `message` and `status`
- **Bulk mode:** Pass `items` (JSON string) or `items_list` (direct list)
- **Auto-split:** Multiline messages automatically split into separate entries

**Required meta structure (COMMANDMENT #2 - Reasoning Traces):**
```python
meta={
    "reasoning": {
        "why": "decision point or research goal",
        "what": "constraints, alternatives considered",
        "how": "methodology, steps taken"
    },
    "confidence": 0.9,
    "files_touched": ["path/to/file.py"]
}
```

**When to use:** After every 2-3 significant actions. Minimum 10+ entries per research investigation.

---

#### `read_recent` (tools/read_recent.py:156)

```python
async def read_recent(
    agent: str,
    project: Optional[str] = None,
    n: Optional[Any] = None,        # Legacy max entries
    limit: Optional[Any] = None,    # Alias for n
    filter: Optional[Dict[str, Any]] = None,  # {agent, status, emoji}
    page: int = 1,
    page_size: int = 10,
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
    format: str = "readable",
    priority: Optional[List[str]] = None,
    category: Optional[List[str]] = None,
    min_confidence: Optional[float] = None,
    priority_sort: bool = False,
) -> Dict[str, Any]
```

**When to use:** Context rehydration at session start. Always read last 5-10 entries before starting work (COMMANDMENT #0).

---

#### `query_entries` (tools/query_entries.py:1002)

```python
async def query_entries(
    agent: str,
    project: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    message: Optional[str] = None,
    message_mode: str = "substring",  # substring|regex|exact
    case_sensitive: bool = False,
    emoji: Optional[List[str]] = None,
    status: Optional[List[str]] = None,
    agents: Optional[List[str]] = None,
    meta_filters: Optional[Dict[str, Any]] = None,
    limit: int = 50,
    page: int = 1,
    page_size: int = 10,
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
    search_scope: str = "project",    # project|global|all_projects|research|bugs|all
    document_types: Optional[List[str]] = None,  # ["progress","research","architecture","bugs","global"]
    include_outdated: bool = True,
    verify_code_references: bool = False,
    time_range: Optional[str] = None,  # last_30d|last_7d|today
    relevance_threshold: float = 0.0,
    max_results: Optional[int] = None,
    config: Optional[QueryEntriesConfig] = None,
    format: str = "readable",
    priority: Optional[List[str]] = None,
    category: Optional[List[str]] = None,
    min_confidence: Optional[float] = None,
    priority_sort: bool = False,
) -> Dict[str, Any]
```

**Key features:**
- `search_scope="all_projects"` searches across all projects in the repo
- `search_scope="global"` searches the global log
- `document_types` filters which log types to search
- `verify_code_references=True` checks if referenced files still exist

**When to use:** Targeted history search, cross-project research validation, finding architectural decisions.

---

### 2.3 Document Management

#### `manage_docs` (tools/manage_docs.py:1118) -- CRITICAL TOOL

```python
async def manage_docs(
    agent: str,
    action: str,
    doc_category: str = "",
    section: Optional[str] = None,
    content: Optional[str] = None,
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    edit: Optional[Dict[str, Any] | str] = None,
    patch_mode: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    doc_name: Optional[str] = None,
    target_dir: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]
```

##### Action Registry (from manage_docs.py:53-87)

**7 Primary Actions:**

| Action | Purpose | Key Params |
|--------|---------|------------|
| `create` | Create new doc (research/bug/custom/review/agent_card) | `doc_name`, `metadata.doc_type` |
| `replace_section` | Replace content by section anchor ID | `doc_name`, `section`, `content` |
| `apply_patch` | Apply unified diff patch | `doc_name`, `edit` or `patch` |
| `replace_range` | Replace explicit line range | `doc_name`, `start_line`, `end_line`, `content` |
| `replace_text` | Find/replace text pattern | `doc_name`, `metadata.find`, `metadata.replace` |
| `append` | Append content to doc or section | `doc_name`, `content` |
| `status_update` | Update checklist item status | `doc_name`, `section`, `metadata` |

**Deprecated Aliases (still work, route to `create`):**

| Old Action | Routes To |
|------------|----------|
| `create_doc` | `create` with `doc_type="custom"` |
| `create_research_doc` | `create` with `doc_type="research"` |
| `create_bug_report` | `create` with `doc_type="bug"` |
| `create_review_report` | `create` with `doc_type="review"` |
| `create_agent_report_card` | `create` with `doc_type="agent_card"` |

**Hidden Actions (advanced use):**
`list_sections`, `list_checklist_items`, `normalize_headers`, `generate_toc`, `validate_crosslinks`, `search`, `batch`

##### Create Action Examples

```python
# Research document
manage_docs(
    agent="ResearchAgent",
    action="create",
    doc_name="RESEARCH_AUTH_FLOW_20260129",
    metadata={"doc_type": "research", "research_goal": "Analyze auth flow"}
)

# Bug report (doc_name auto-generated from slug)
manage_docs(
    agent="BugHunterAgent",
    action="create",
    metadata={
        "doc_type": "bug",
        "category": "logic",
        "slug": "auth_leak",
        "severity": "high",
        "title": "Auth token not invalidated"
    }
)

# Custom document with body content
manage_docs(
    agent="ArchitectAgent",
    action="create",
    doc_name="COORDINATION_PROTOCOL",
    metadata={
        "doc_type": "custom",
        "body": "# Protocol\n\nContent here..."
    }
)
```

##### Edit Action Examples

```python
# Replace a section by anchor ID
manage_docs(
    agent="ArchitectAgent",
    action="replace_section",
    doc_name="architecture",
    section="problem_statement",
    content="## Problem Statement\nNew content..."
)

# Update checklist item
manage_docs(
    agent="CoderAgent",
    action="status_update",
    doc_name="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "PR #123 merged"}
)

# Find and replace text
manage_docs(
    agent="CoderAgent",
    action="replace_text",
    doc_name="architecture",
    metadata={"find": "old_term", "replace": "new_term", "replace_all": True}
)

# Replace line range
manage_docs(
    agent="ArchitectAgent",
    action="replace_range",
    doc_name="phase_plan",
    start_line=45,
    end_line=50,
    content="New content for these lines"
)

# Append to section
manage_docs(
    agent="ResearchAgent",
    action="append",
    doc_name="architecture",
    section="constraints",
    content="- New constraint added",
    metadata={"position": "inside"}
)
```

##### Why manage_docs Is Required

- **Atomic updates:** Section-level precision prevents accidental overwrites
- **Audit trail:** Every edit is logged with agent, timestamp, and diff
- **Frontmatter preservation:** Managed docs have metadata headers that hand-editing can corrupt
- **Index auto-update:** Research docs auto-register in INDEX.md
- **Parameter healing:** Malformed inputs are auto-corrected with warnings
- **Hand-editing risks:** Corrupted frontmatter, lost section IDs, broken cross-references

---

#### `generate_doc_templates` (tools/generate_doc_templates.py:46)

```python
async def generate_doc_templates(
    agent: str,
    project_name: str,
    author: str | None = None,
    overwrite: bool = False,
    force: bool = False,
    documents: Iterable[str] | None = None,  # Specific docs to regenerate
    base_dir: str | None = None,
    custom_context: Any = None,
    legacy_fallback: bool = False,
    include_template_metadata: bool = False,
    validate_only: bool = False,
) -> Dict[str, Any]
```

**When to use:** Scaffold initial project docs. Usually called automatically by `set_project`.

---

#### `rotate_log` (tools/rotate_log.py:1368)

```python
async def rotate_log(
    agent: str,
    project: Optional[str] = None,
    suffix: Optional[str] = None,
    custom_metadata: Optional[str] = None,
    confirm: Optional[bool] = None,     # Must be True to actually rotate
    dry_run: Optional[bool] = None,
    dry_run_mode: Optional[str] = None, # "estimate"|"precise"
    log_type: Optional[str] = None,     # "progress"|"doc_updates"
    log_types: Optional[List[str]] = None,
    rotate_all: Optional[bool] = None,
    auto_threshold: Optional[bool] = None,
    threshold_entries: Optional[int] = None,  # Default: 500
    config: Optional[RotateLogConfig] = None,
    format: str = "structured",
) -> Dict[str, Any]
```

**When to use:** When progress logs get large (500+ entries). Archives old entries.

---

### 2.4 File Operations (v2.2)

#### `read_file` (tools/read_file.py:1694)

**Purpose:** PRIMARY file access tool. All file reads for investigation MUST use this.

```python
async def read_file(
    agent: str,
    path: str,
    mode: str = "scan_only",  # scan_only|chunk|page|line_range|search
    chunk_index: Optional[List[int]] = None,
    start_chunk: Optional[int] = None,
    max_chunks: Optional[int] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    page_number: Optional[int] = None,
    page_size: Optional[int] = None,
    search: Optional[str] = None,
    query: Optional[str] = None,     # Alias for search
    search_mode: str = "regex",      # regex|literal|fuzzy
    case_insensitive: Optional[bool] = None,
    context_lines: int = 0,
    max_matches: Optional[int] = None,
    fuzzy_threshold: Optional[float] = None,
    format: str = "readable",
    include_dependencies: bool = False,
    include_impact: bool = False,          # Requires include_dependencies=True
    structure_filter: Optional[str] = None, # Regex filter for scan_only mode
    structure_page: int = 1,
    structure_page_size: int = 10,
    allow_outside_repo: bool = False,
) -> Union[Dict[str, Any], str]
```

**Modes:**

| Mode | Purpose | Key Params |
|------|---------|------------|
| `scan_only` | File metadata + AST structure (classes, functions, methods) | `structure_filter`, `structure_page` |
| `chunk` | Read file in ~200-line chunks | `chunk_index=[0]`, `chunk_index=[0,1,2]` |
| `page` | Read file page-by-page | `page_number=1`, `page_size=50` |
| `line_range` | Read specific line range | `start_line=10`, `end_line=50` |
| `search` | Regex search within file | `query="pattern"`, `context_lines=3` |

**Key behaviors:**
- Sandbox enforced: cannot read outside repo root (unless `allow_outside_repo=True`)
- Session tracking: records which files have been read (for `edit_file` enforcement)
- AST extraction: Python/JS/Markdown files get full structure with signatures, types, line ranges
- `include_dependencies=True` adds import analysis and dependency graph
- `include_impact=True` adds blast radius analysis (requires `include_dependencies=True`)
- `structure_filter` accepts regex to filter classes/functions in scan_only mode
- `structure_page`/`structure_page_size` paginate large structures (default 10 items/page)

**Why read_file over cat/grep:**
- Audit trail of every file read
- Sandbox enforcement (path policy)
- Structure extraction (AST)
- Session tracking for edit_file enforcement
- Context reminders (active project, mode hints)

---

#### `search` (tools/search.py:533)

**Purpose:** Multi-file codebase search. Replaces grep/rg.

```python
async def search(
    agent: str,
    pattern: str,           # REQUIRED - regex by default
    path: Optional[str] = None,
    glob: Optional[str] = None,        # e.g. "*.py", "src/**/*.ts"
    type: Optional[str] = None,        # py|js|ts|rust|go|java etc.
    output_mode: str = "content",      # content|files_with_matches|count
    format: str = "readable",
    context_lines: int = 0,
    before_context: Optional[int] = None,
    after_context: Optional[int] = None,
    case_insensitive: bool = False,
    regex: bool = True,
    multiline: bool = False,
    max_matches_per_file: int = 50,
    max_total_matches: int = 200,
    max_files: int = 100,
    line_numbers: bool = True,
    skip_binary: bool = True,
    max_file_size_mb: int = 10,
) -> Union[Dict[str, Any], str]
```

**Output modes:**
- `content` - matching lines with context (default)
- `files_with_matches` - just file paths
- `count` - match counts per file

**Why search over grep/rg:**
- Sandbox enforcement (stays within repo)
- Audit trail
- Structured output with metadata
- Denylist-aware (skips .git, node_modules, etc.)

---

#### `edit_file` (tools/edit_file.py:173)

**Purpose:** Safe file editing with exact string replacement.

```python
async def edit_file(
    agent: str,
    path: str,             # REQUIRED
    old_string: str,       # REQUIRED - exact match
    new_string: str,       # REQUIRED
    replace_all: bool = False,
    dry_run: bool = True,  # DEFAULT TRUE - must explicitly set False
    format: str = "readable",
) -> Union[Dict[str, Any], str]
```

**Error codes:**

| Error | Meaning |
|-------|--------|
| `SANDBOX_VIOLATION` | Path outside repository boundary |
| `READ_BEFORE_EDIT_REQUIRED` | `read_file` not called on this path in current session |
| `SESSION_REQUIRED` | No session ID available |
| `FILE_NOT_FOUND` | File does not exist |
| `NOT_A_FILE` | Path is a directory |
| `READ_ERROR` | Cannot read file contents |
| `STRING_NOT_FOUND` | `old_string` not found in file |
| `BACKUP_ERROR` | Failed to create backup |
| `WRITE_ERROR` | Failed to write file |

**Critical behaviors:**
- `dry_run=True` by default -- MUST set `False` to apply changes
- `read_file` MUST be called on the same file path first (tool-enforced, not just policy)
- Creates backup in `.scribe/backups/` before writing
- No regex -- exact string matching only
- Returns unified diff preview in dry_run mode

**Workflow: search -> read -> edit**

```python
# 1. Find files
search(agent="CoderAgent", pattern="def old_function")

# 2. Read file (REQUIRED before edit)
read_file(agent="CoderAgent", path="src/module.py", mode="search", query="old_function")

# 3. Preview edit (dry_run=True is default)
edit_file(agent="CoderAgent", path="src/module.py",
    old_string="def old_function():",
    new_string="def new_function():")

# 4. Apply edit
edit_file(agent="CoderAgent", path="src/module.py",
    old_string="def old_function():",
    new_string="def new_function():",
    dry_run=False)
```

---

### 2.5 Sentinel/Bug Tools

#### `append_event` (tools/sentinel_tools.py:157)

General sentinel event logger. In project mode, routes to `append_entry`.

```python
async def append_event(
    agent: str,
    message: Optional[str] = None,
    status: Optional[str] = None,
    emoji: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    timestamp_utc: Optional[str] = None,
    items: Optional[Any] = None,
    items_list: Optional[list[Dict[str, Any]]] = None,
    auto_split: bool = True,
    split_delimiter: str = "\n",
    stagger_seconds: int = 1,
    event_type: Optional[str] = None,  # Legacy
    data: Optional[Dict[str, Any]] = None,  # Legacy
) -> Dict[str, Any]
```

---

#### `open_bug` (tools/sentinel_tools.py:278)

```python
async def open_bug(
    agent: str,
    title: str,        # REQUIRED - short bug title
    symptoms: str,     # REQUIRED - description of symptoms
    category: str,     # REQUIRED - e.g. 'auth', 'api', 'ui'
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]
```

Creates a bug case with auto-generated ID (BUG-YYYY-MM-DD-N), logs via `append_entry`, and creates a bug report document via `manage_docs`.

---

#### `open_security` (tools/sentinel_tools.py:400)

Identical signature to `open_bug` but for security issues. Creates SEC-prefixed case IDs.

```python
async def open_security(
    agent: str,
    title: str,
    symptoms: str,
    category: str,     # e.g. 'auth', 'injection', 'xss'
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]
```

---

#### `link_fix` (tools/sentinel_tools.py:525)

```python
async def link_fix(
    agent: str,
    case_id: str,        # REQUIRED - must start with BUG- or SEC-
    execution_id: str,   # REQUIRED
    artifact_ref: str,   # REQUIRED - e.g. PR URL, commit SHA
    landing_status: str, # REQUIRED - merged|landed|done|proposed
) -> Dict[str, Any]
```

---

#### `scribe_doctor` (tools/doctor.py:32)

```python
async def scribe_doctor(agent: str) -> Dict[str, Any]
```

Returns runtime diagnostics: database status, config, project state, connection health.

---

## Technical Analysis
<!-- ID: technical_analysis -->

### File Reading Policy (NON-NEGOTIABLE)

These rules apply to ALL agents in ALL stages:

| Operation | MUST Use | NEVER Use |
|-----------|----------|----------|
| Read file contents | `scribe.read_file` | `cat`, `head`, `tail`, native `Read` |
| Multi-file search | `scribe.search` | `grep`, `rg`, `find`, Bash search |
| Edit files | `scribe.edit_file` | `sed`, `awk`, manual editing |

**Enforcement levels:**
- `edit_file` requires `read_file` first: **tool-enforced** (returns `READ_BEFORE_EDIT_REQUIRED` error)
- `edit_file` defaults to dry_run: **tool-enforced** (must explicitly set `dry_run=False`)
- `read_file`/`search` over shell commands: **policy-enforced** (agents must comply, review agent checks)

**Exception:** Native `Read` tool is acceptable ONLY for ephemeral previews when Scribe MCP is unavailable.

### Output Format Options

All tools support the `format` parameter:

| Format | Use Case |
|--------|----------|
| `readable` | Human-friendly output with line breaks, boxes (default for most tools) |
| `structured` | Raw dict/JSON for programmatic parsing |
| `compact` | Minimal dict for token conservation |

---

## Recommendations
<!-- ID: recommendations -->

### Drop-In Snippet for Agent Files

Copy-paste this into agent definitions in other projects (source: `.claude/skills/scribe-mcp-usage/references/files.md:176-187`):

```markdown
### File Operations Policy
- **Reading files:** Use `scribe.read_file` (NOT cat/head/tail)
- **Multi-file search:** MUST use `scribe.search` (NOT grep, rg, find, or Bash search)
- **File editing:** SHOULD use `scribe.edit_file` (NOT sed, awk, or Bash edits)
- **Enforcement:** `edit_file` requires `read_file` on the same file first (tool-enforced)
- **Safety:** `edit_file` defaults to `dry_run=True` -- must set `False` to apply changes
```

### Session Lifecycle Quick Reference

```
1. list_projects(agent="...")           # Discover existing projects
2. set_project(agent="...", name="...", root="...")  # Activate context
3. read_recent(agent="...", limit=10)   # Rehydrate context (COMMANDMENT #0)
4. append_entry(agent="...", ...)       # Log intent before work
5. read_file / search / edit_file       # Do work
6. append_entry(agent="...", ...)       # Log results after work
7. manage_docs(agent="...", ...)        # Create/update documents
8. append_entry(agent="...", status="success")  # Final completion log
```

### Handoff Notes

**For Architect Agent:** This document provides the complete tool API surface. Use it to design agent prompts that include correct tool signatures and behavioral constraints.

**For Coder Agent:** The `manage_docs` action registry and `edit_file` error codes are the most critical sections for implementation work.

**For Review Agent:** Validate that agents follow the file reading policy and logging requirements. Check for `READ_BEFORE_EDIT_REQUIRED` compliance and reasoning trace completeness.

---

## Appendix
<!-- ID: appendix -->

**Source Files Investigated:**
- `tools/set_project.py` (949 lines) - Project management
- `tools/get_project.py` (605 lines) - Project queries
- `tools/list_projects.py` (719 lines) - Project discovery
- `tools/append_entry.py` (2162 lines) - Primary logging
- `tools/read_recent.py` (591 lines) - Recent entry retrieval
- `tools/query_entries.py` (2038 lines) - Advanced log search
- `tools/manage_docs.py` (3404 lines) - Document management
- `tools/read_file.py` (2309 lines) - File reading
- `tools/search.py` (749 lines) - Codebase search
- `tools/edit_file.py` (359 lines) - File editing
- `tools/generate_doc_templates.py` (589 lines) - Template generation
- `tools/rotate_log.py` (2129 lines) - Log rotation
- `tools/sentinel_tools.py` (598 lines) - Bug/security case management
- `tools/doctor.py` (113 lines) - Diagnostics

**Governance Files Referenced:**
- `CLAUDE.md` (root + scribe_mcp)
- `AGENTS.md`
- `.claude/agents/*.md` (5 agent definitions)
- `.claude/skills/scribe-mcp-usage/references/files.md` (drop-in snippet)

---
