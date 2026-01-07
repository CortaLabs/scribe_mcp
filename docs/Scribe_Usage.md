# Scribe MCP Tool Usage Guide

This document provides comprehensive usage instructions for all available Scribe MCP tools, including required parameters, optional parameters, and practical examples.

## Update v2.1.1

- `apply_patch` now supports **structured mode** with compiler-generated unified diffs.
- Unified diffs are **compiler output only** (do not hand-craft).
- Optional `patch_source_hash` enforces stale-source protection for patches.
- Reminders teach: scaffold with `replace_section`, then prefer structured/line edits.
- New lifecycle actions: `normalize_headers`, `generate_toc`, `create_doc`, `validate_crosslinks`.
- Structural actions validate `doc` against the project registry; unknown docs fail with `DOC_NOT_FOUND`.
- `normalize_headers` now supports ATX headers with or without a space plus Setext (`====` / `----`), skipping fenced code blocks.
- `generate_toc` uses GitHub-style anchors (NFKD normalization, ASCII folding, emoji removal, punctuation collapse, de-dup suffixes).
- `create_doc` preserves multiline body content in metadata (`body`, `snippet`, `content`).
- `read_file` adds repo-scoped scan/chunk/page/search modes with provenance logging for every read.
- `read_file` **Phase 5 enhancements**: Full signature extraction (types, defaults, return types), line ranges for all functions/classes/methods, method display under classes, structure filtering (`structure_filter` for regex-based class/function search), and structure pagination (`structure_page`, `structure_page_size`) for browsing large classes with 50+ methods.
- `scribe_doctor` provides environment readiness diagnostics (repo root, config, plugin status, vector readiness).
- `manage_docs` adds semantic search via `action="search"` with `search_mode="semantic"` and doc/log separation.
- Semantic search supports `project_slug`, `project_slugs`, `project_slug_prefix`, `doc_type`, `file_path`, `time_start/time_end`.
- Per-type defaults: `vector_search_doc_k` / `vector_search_log_k` (overrides via `doc_k` / `log_k`).
- Vector indexing uses registry-managed docs only; log/rotated-log files are excluded from doc indexing.
- `scripts/reindex_vector.py` supports `--rebuild` for clean index rebuilds, `--safe` for low-thread fallback, and `--wait-for-drain` to block until embeddings are written.

## Readable Output Formatting (v2.1.1+)

Scribe MCP tools support a `format` parameter that controls output rendering for agent readability.

### Format Options

| Format | Returns | Use Case |
|--------|---------|----------|
| `readable` (default) | `CallToolResult` with `TextContent` | Clean display in Claude Code with actual newlines |
| `structured` | Raw dict/JSON | Programmatic parsing, backward compatibility |
| `compact` | Minimal dict | Token conservation |
| `both` | `CallToolResult` + `structuredContent` | Future use when Issue #9962 is resolved |

### ANSI Color Policy

**Critical design decision for token conservation and agent experience:**

| Tool Type | ANSI Colors | Rationale |
|-----------|-------------|-----------|
| **High-frequency tools** (`append_entry`, `set_project`, confirmations) | **OFF (hardcoded)** | Called 10-30x/session; ANSI codes are visual clutter for agents |
| **Display-heavy tools** (`read_file`, `read_recent`, `query_entries`) | **Config-driven** | Called 1-5x/session; colors aid human scanning of large outputs |

**Config setting** (`.scribe/config/scribe.yaml`):
```yaml
use_ansi_colors: true  # Enable ANSI colors for display-heavy tools
```

### Implementation Pattern for Tool Authors

When adding readable format support to a new tool:

```python
# 1. Add format parameter to tool signature
async def my_tool(
    ...,
    format: str = "readable",  # readable (default), structured, compact
) -> Union[Dict[str, Any], str]:

# 2. Build response data as usual
response = {"ok": True, "data": ...}

# 3. Route through formatter at the end
return await default_formatter.finalize_tool_response(
    data=response,
    format=format,
    tool_name="my_tool"
)
```

**For high-frequency tools** (confirmations, logging):
```python
# In format_readable_my_tool():
USE_COLORS = False  # Hardcode OFF - no config check needed
```

**For display-heavy tools** (file content, log queries):
```python
# Uses self.USE_COLORS property which reads from config
if self.USE_COLORS:
    # Apply ANSI formatting
```

### Reasoning Block Display

The `append_entry` readable format parses `meta.reasoning` JSON and displays it as a tree:

```
Reasoning:
├─ Why: <decision context>
├─ What: <constraints and alternatives>
└─ How: <methodology and steps>
```

This makes the audit trail immediately scannable without parsing JSON.

### Conditional Sections

Readable formats only display sections when they contain data:
- **Reminders**: Only shown if `len(reminders) > 0`
- **Metadata**: Only shown if explicitly set and non-empty
- **Errors**: Formatted prominently with suggestions

---

## Quick Start (High Level)

Scribe tools follow a simple flow:

1. **Pick or create a project** with `set_project(...)` so the tool knows where to read/write.
2. **Use the tool for the job**:
   - `append_entry` for logging actions/results.
   - `manage_docs` for structured doc edits (sections, patches, ranges).
   - `read_recent` and `query_entries` for log retrieval/search.
3. **Check outputs** for `ok`, `error`, and any `parameter_healing` notes.

If you skip step 1, most tools will error because no active project context exists.

## Document Editing (manage_docs)

Scribe supports three document edit modes, in increasing precision order:

### 1. apply_patch (recommended; structured by default)
Describe intent and let Python compile a valid unified diff. This avoids manual diff errors.

- Intent-based edits (range, block, or section)
- `patch_mode` enum: `structured` (default) or `unified` (advanced)
- Compiler emits a valid diff; no hand-written hunks
- Idempotent behavior is easier to guarantee
- `replace_block` ignores fenced code blocks and fails on ambiguous anchors with a line list.

Example:
```json
{
  "action": "apply_patch",
  "doc": "architecture",
  "edit": {
    "type": "replace_range",
    "start_line": 1,
    "end_line": 1,
    "content": "# Architecture (Updated)\n"
  }
}
```

Block replacement example:
```json
{
  "action": "apply_patch",
  "doc": "architecture",
  "edit": {
    "type": "replace_block",
    "anchor": "**Solution Summary:**",
    "new_content": "**Solution Summary:** Updated summary here."
  }
}
```

Structured edit types:
- `replace_range`: swap explicit line ranges (body-relative).
- `replace_block`: replace from an anchor line to the next blank line; fails on ambiguous anchors.
- `replace_section`: legacy anchor-by-ID (scaffolding only).

Common structured errors:
- `DOC_NOT_FOUND`: doc key is not registered for the project.
- `STRUCTURED_EDIT_ANCHOR_NOT_FOUND`: anchor not found in body.
- `STRUCTURED_EDIT_ANCHOR_AMBIGUOUS`: anchor matched multiple lines; includes line list.
- `PATCH_MODE_CONFLICT`: `patch_mode` argument conflicts with metadata.

### YAML frontmatter (automatic)
All managed docs are expected to use YAML frontmatter. When a document is edited via `manage_docs`,
Scribe will automatically add frontmatter if missing and update `last_updated` on each edit.

Manual overrides are supported via `metadata.frontmatter` (merged into the frontmatter map).

Line numbers for `apply_patch` (structured mode) and `replace_range` are **body-relative** (frontmatter lines are excluded).
If a `doc` key is not registered for the project, structural actions fail with `DOC_NOT_FOUND` instead of redirecting to another file.

Example:
```json
{
  "action": "apply_patch",
  "doc": "architecture",
  "edit": { "type": "replace_range", "start_line": 12, "end_line": 12, "content": "..." },
  "metadata": {
    "frontmatter": {
      "status": "authoritative",
      "tags": ["scribe", "documentation"]
    }
  }
}
```

### 2. replace_range
Replace an explicit 1-based line range (inclusive).

```json
{
  "action": "replace_range",
  "doc": "architecture",
  "start_line": 12,
  "end_line": 15,
  "content": "replacement text\n"
}
```

### Checklist helper: list_checklist_items
Return checklist items with line numbers so you can feed replace_range without guessing.

```json
{
  "action": "list_checklist_items",
  "doc": "checklist",
  "metadata": { "text": "Phase 0 item", "case_sensitive": true }
}
```
The response includes `body_line_offset` and `file_line` for mapping body-relative lines back to the file.

### 3. apply_patch (unified diff mode, advanced)
Apply a unified diff generated by the diff compiler. Avoid hand-written diffs.

```json
{
  "action": "apply_patch",
  "doc": "architecture",
  "patch": "<compiler output>",
  "patch_mode": "unified"
}
```

### 4. replace_section (legacy)
Replace content using HTML section markers (`<!-- ID: ... -->`). This is best suited for templates and scaffolding.

Note: New agents should prefer `apply_patch` (structured mode) or `replace_range` whenever possible.

### 5. normalize_headers (structure)
Normalizes markdown headers into canonical ATX form with numbering. This action is **body-only** and skips fenced code blocks.

Current support: ATX headers with or without a space after `#`, plus Setext headers (`====` for H1, `----` for H2). Output is canonical ATX and idempotent.

```json
{
  "action": "normalize_headers",
  "doc": "architecture"
}
```

### 6. generate_toc (derived)
Generates or replaces a table of contents between `<!-- TOC:start -->` / `<!-- TOC:end -->`. Inserted at top of body if missing.

Anchors match GitHub-style behavior (NFKD normalization, ASCII folding, emoji removal, punctuation collapse, whitespace to `-`, de-dup with `-1`).

```json
{
  "action": "generate_toc",
  "doc": "architecture"
}
```

### 7. create_doc (custom docs)
Creates a new document from plain content. Users do **not** supply Jinja; pass content/body/snippets/sections and optional frontmatter.
Multiline content in `metadata.body`/`metadata.snippet` is preserved as-is.

```json
{
  "action": "create_doc",
  "doc": "custom_doc",
  "metadata": {
    "doc_name": "release_brief_003",
    "doc_type": "release_brief",
    "body": "# Release Brief\nSummary details here.",
    "target_dir": ".scribe/docs/dev_plans/my_project/custom",
    "frontmatter": { "category": "release" },
    "register_doc": false
  }
}
```

### 8. validate_crosslinks (read-only)
Validates `related_docs` without writing. Optional anchor checks are controlled by `metadata.check_anchors=true`.

```json
{
  "action": "validate_crosslinks",
  "doc": "architecture",
  "metadata": { "check_anchors": true }
}
```

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Core Project Management](#core-project-management)
3. [Logging Operations](#logging-operations)
4. [Query and Analysis](#query-and-analysis)
5. [Documentation Management](#documentation-management)
6. [Log Maintenance](#log-maintenance)
7. [Project Cleanup](#project-cleanup)

---

## Prerequisites

### **IMPORTANT: Project Context Required**

Most Scribe tools require an active project context. Before using any tool, you MUST set a project:

```python
await set_project(name="your-project-name")
```

**Failure to set a project first will result in errors like:**
- `"No project configured. Invoke set_project before using this tool."`
- `"No project configured. Invoke set_project before reading logs"`

---

## Core Project Management

### `set_project`
**Purpose**: Create/select a project and bootstrap documentation structure.

**Required Parameters:**
- `name` (string): Project name

**Optional Parameters:**
- `root` (string): Project root directory (defaults to current directory)
- `progress_log` (string): Path to progress log file
- `defaults` (dict): Default settings for the project

**Example Usage:**
```python
# Basic usage
await set_project(name="my-project")

# With custom defaults
await set_project(
    name="my-project",
    defaults={"emoji": "🧪", "agent": "MyAgent"}
)
```

**Returns:**
```json
{
  "ok": true,
  "project": {
    "name": "my-project",
    "root": "/path/to/project",
    "progress_log": "/path/to/progress/log.md",
    "docs_dir": "/path/to/docs",
    "docs": {
      "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
      "phase_plan": "/path/to/PHASE_PLAN.md",
      "checklist": "/path/to/CHECKLIST.md",
      "progress_log": "/path/to/PROGRESS_LOG.md"
    },
    "defaults": {"agent": "Scribe"},
    "author": "Scribe"
  }
}
```

### `get_project`
**Purpose**: Retrieve current active project context and configuration.

**Parameters:** None

**Example Usage:**
```python
await get_project()
```

**Returns:**
```json
{
  "ok": true,
  "project": {
    "name": "current-project",
    "root": "/path/to/project",
    "progress_log": "/path/to/log.md",
    "docs_dir": "/path/to/docs",
    "defaults": {"agent": "Scribe"},
    "author": "Scribe"
  }
}
```

### `list_projects`
**Purpose**: Discover available projects and their configurations.

**Optional Parameters:**
- `limit` (int, default: 5): Maximum number of projects to return
- `filter` (string): Filter projects by name (case-insensitive)
- `compact` (bool): Use compact response format
- `fields` (list): Specific fields to include in response
- `include_test` (bool, default: false): Include test/temp projects
- `page` (int, default: 1): Page number for pagination
- `page_size` (int): Number of items per page

**Example Usage:**
```python
# Basic usage
await list_projects()

# With pagination
await list_projects(limit=10, page=1)

# Filtered search
await list_projects(filter="my-project", limit=3)
```

**Returns:**
```json
{
  "ok": true,
  "projects": [
    {
      "name": "project-name",
      "root": "/path/to/project",
      "progress_log": "/path/to/log.md"
    }
  ],
  "count": 1,
  "pagination": {
    "page": 1,
    "page_size": 5,
    "total_count": 10,
    "has_next": true,
    "has_prev": false
  }
}
```

---

## Logging Operations

### `append_entry`
**Purpose**: **PRIMARY TOOL** - Add structured log entries with metadata.

#### Single Entry Mode

**Required Parameters:**
- `message` (string): Log message content

**Optional Parameters:**
- `status` (string): Status type - "info", "success", "warn", "error", "bug", "plan"
- `emoji` (string): Custom emoji override
- `agent` (string): Agent identifier
- `meta` (dict): Metadata dictionary for context
- `timestamp_utc` (string): Custom UTC timestamp
- `log_type` (string): Target log identifier (defaults to "progress")

**Example Usage:**
```python
# Basic entry
await append_entry(message="Fixed authentication bug")

# With full context
await append_entry(
    message="Fixed authentication bug",
    status="success",
    agent="DebugBot",
    meta={"component": "auth", "tests_fixed": 5}
)

# Planning entry
await append_entry(
    message="Beginning database migration phase",
    status="plan",
    emoji="🗄️",
    meta={"phase": "migration", "priority": "high"}
)
```

#### Bulk Entry Mode

**Required Parameters:**
- `items` (string or list): JSON string array or direct list of entry dictionaries

**Each Entry Requires:**
- `message` (string): Log message content

**Each Entry Optional:**
- `status`, `emoji`, `agent`, `meta`, `timestamp_utc`, `log_type`

**Example Usage:**
```python
# As JSON string
await append_entry(items=json.dumps([
  {"message": "First task completed", "status": "success"},
  {"message": "Bug found in auth module", "status": "bug", "agent": "DebugBot"},
  {"message": "Database migration finished", "status": "info",
   "meta": {"component": "database", "phase": "deployment"}}
]))

# As direct list
await append_entry(items=[
  {"message": "Code review completed", "status": "success"},
  {"message": "Tests passing", "status": "success", "meta": {"tests_run": 25}}
])
```

**Returns:**
```json
{
  "ok": true,
  "written_line": "[ℹ️] [2025-11-02 07:39:07 UTC] [Agent: AgentName] [Project: project] [ID: hash] Your message",
  "path": "/path/to/progress/log.md",
  "meta": {"log_type": "progress"}
}
```

---

## Query and Analysis

### `read_recent`
**Purpose**: Retrieve recent log entries with pagination.

**Optional Parameters:**
- `n` (int, default: 50): Number of recent entries to return
- `filter` (dict): Optional filters for agent, status, emoji
- `page` (int, default: 1): Page number for pagination
- `page_size` (int): Number of entries per page
- `compact` (bool): Use compact response format
- `fields` (list): Specific fields to include
- `include_metadata` (bool): Include metadata field in entries

**Example Usage:**
```python
# Basic usage
await read_recent()

# Limited entries
await read_recent(n=10)

# With filters
await read_recent(n=5, filter={"agent": "DebugBot", "status": "success"})
```

**Returns:**
```json
{
  "ok": true,
  "entries": [
    {
      "id": "entry_id",
      "ts": "2025-11-02 07:39:07 UTC",
      "emoji": "ℹ️",
      "agent": "AgentName",
      "message": "Log message",
      "meta": {"log_type": "progress"},
      "raw_line": "Full log line"
    }
  ],
  "count": 1,
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_count": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

### `query_entries`
**Purpose**: Advanced log searching and filtering.

**Optional Parameters:**
- `project` (string): Project name (uses active project if None)
- `start` (string): Start timestamp filter
- `end` (string): End timestamp filter
- `message` (string): Message text filter
- `message_mode` (string): How to match message - "substring", "regex", "exact"
- `case_sensitive` (bool): Case sensitive message matching
- `emoji` (string or list): Filter by emoji(s)
- `status` (string or list): Filter by status(es)
- `agents` (string or list): Filter by agent name(s)
- `meta_filters` (dict): Filter by metadata key/value pairs
- `limit` (int): Maximum results to return
- `page` (int): Page number for pagination
- `page_size` (int): Number of results per page

**Enhanced Search Parameters:**
- `search_scope`: "project", "global", "all_projects", "research", "bugs", "all"
- `document_types`: ["progress", "research", "architecture", "bugs", "global"]
- `relevance_threshold`: Minimum relevance score (0.0-1.0)
- `verify_code_references`: Check if mentioned code exists
- `time_range`: Temporal filtering ("last_30d", "last_7d", "today")

**Example Usage:**
```python
# Basic message search
await query_entries(message="bug", message_mode="substring")

# Date range search
await query_entries(start="2025-10-23", end="2025-10-24")

# Enhanced cross-project search
await query_entries(
    message="authentication",
    search_scope="all_projects",
    document_types=["progress", "bugs"],
    relevance_threshold=0.8
)

# Metadata filtering
await query_entries(
    meta_filters={"component": "auth", "severity": "high"}
)
```

**Returns:**
```json
{
  "ok": true,
  "entries": [/* matching entries */],
  "count": 5,
  "pagination": {/* pagination info */}
}
```

---

### `read_file`
**Purpose**: Repo-scoped file access with deterministic scan/chunk/page/search modes, dependency analysis, and read provenance logging.

**Required Parameters:**
- `path` (string): File path (absolute or repo-relative)

**Optional Parameters:**
- `mode`: `scan_only` (default), `chunk`, `line_range`, `page`, `full_stream`, `search`
- `chunk_index`: Chunk index or list of indices (for `chunk` mode)
- `start_line` / `end_line`: Explicit line range (for `line_range`)
- `page_number` / `page_size`: Pagination controls (for `page`)
- `start_chunk` / `max_chunks`: Streaming controls (for `full_stream`)
- `search`: Search term (for `search` mode)
- `query`: Alias for `search` (for `search` mode, defaults to smart inference)
- `search_mode`: `regex` (default) or `literal` - **Note: Default changed from literal to regex**
- `context_lines`: Lines of context around matches (search mode)
- `max_matches`: Max matches to return (search mode)
- `include_dependencies`: `False` (default) or `True` - Enable dependency analysis (Python files only)
- `format`: `readable` (default), `structured`, or `compact` - Output format

**Scan Mode Enhancements:**
When `mode="scan_only"`, the tool automatically detects file type and extracts structure:

- **Python files**: AST analysis showing functions, classes, methods with line numbers and signatures
- **Markdown files**: Heading hierarchy with line numbers (max 100 headings)
- **JavaScript/TypeScript**: Basic structure detection
- **SKILL.md detection**: Special urgent warning when reading SKILL.md files
- **Navigation hints**: Suggested chunk sizes and example calls for large files

**Dependency Analysis (`include_dependencies=True`):**
Provides static analysis of Python imports with governance features:

1. **Import Categorization**:
   - **Standard Library**: Python stdlib imports (detected via sys.stdlib_module_names)
   - **Third-Party Packages**: External dependencies from pip/conda
   - **Local Modules**: Project-internal imports with path resolution and existence checks

2. **Path Resolution**:
   - Resolves relative imports (e.g., `from ..utils import helper`)
   - Resolves absolute imports (e.g., `from scribe_mcp.tools import append_entry`)
   - Shows resolved file paths with ✓ checkmarks when files exist
   - Detects workspace root automatically (.git, pyproject.toml markers)

3. **Impact Radius (Blast Radius)**:
   - Shows how many files import the current file
   - Categorized by impact level:
     - **Low**: 0-4 importers
     - **Medium**: 5-15 importers (⚠️ warning)
     - **High**: 16+ importers (🚨 high impact)
   - Lists up to 20 files that import this module
   - Helps assess change risk before modifications

4. **Boundary Enforcement**:
   - Checks imports against `.scribe/config/boundary_rules.yaml` rules
   - Detects forbidden import patterns (e.g., "sentinel layer must not import tools")
   - Shows violations with severity levels: ERROR, WARNING, INFO
   - Supports glob patterns with `**` for recursive matching
   - Respects `allowed_exceptions` for legitimate edge cases

5. **Static Analysis Disclaimer**:
   - Automatically included when dependencies or impact radius shown
   - Clarifies that only import-time relationships are detected
   - Honest about limitations: no runtime dependencies, dynamic imports, or reflection patterns

**Example Usage:**
```python
# Basic scan (metadata + structure)
await read_file(path="tools/read_file.py", mode="scan_only")

# Scan with dependency analysis
await read_file(path="tools/read_file.py", mode="scan_only", include_dependencies=True)

# Read specific chunk
await read_file(path="docs/Scribe_Usage.md", mode="chunk", chunk_index=[0])

# Regex search (default mode)
await read_file(path="tools/read_file.py", mode="search", query=r"async\s+def\s+\w+")

# Literal search (explicit)
await read_file(path="docs/Scribe_Usage.md", mode="search", search="semantic", search_mode="literal")

# Search with context lines
await read_file(path="server.py", mode="search", query="async def", context_lines=2)
```

**Configuration:**
Boundary rules are defined in `.scribe/config/boundary_rules.yaml`:
```yaml
version: 1.0
enabled: true
rules:
  - name: "Sentinel Layer Isolation"
    severity: "error"
    pattern:
      source: "sentinel/**/*.py"
      forbidden_imports:
        - "tools/**"
        - "scribe_mcp.tools.*"
```

**Performance:**
- Dependency analysis: ~20% overhead when enabled (opt-in)
- Impact radius: <3s for typical repositories (<500 Python files)
- Boundary checking: <20ms overhead per file
- Zero overhead when `include_dependencies=False` (default)

**Notes:**
- Every read is logged with provenance (absolute path, hash, byte size, encoding, read mode)
- Enforces repo scope by default; out-of-scope paths are denied
- Dependency analysis is static only - does not execute code or resolve runtime imports
- Impact radius requires workspace root detection (looks for .git, pyproject.toml markers)

### `scribe_doctor`
**Purpose**: Diagnostics for repo root, config resolution, plugin status, and vector readiness.

**Example Usage:**
```python
await scribe_doctor()
```

**Returns:**
- Repo root, cwd, config paths
- Plugin status (including vector indexer availability)
- Vector index metadata and queue depth (if enabled)

---

## Documentation Management

### `manage_docs`
**Purpose**: Structured documentation system for projects.

**Required Parameters:**
- `action` (string): Action type - `replace_section`, `append`, `status_update`, `list_sections`, `batch`, `create_research_doc`, `create_bug_report`, `create_review_report`, `create_agent_report_card`
- `doc` (string): Document key (e.g., `architecture`, `phase_plan`, `checklist`, `implementation`)

**Action-Specific Parameters:**

#### `replace_section`
- `section` (string, required): Section anchor ID (e.g., "problem_statement")
- `content` (string, required): New section content

#### `append`
- `content` (string, required): Content to append
- `section` (string, optional): Section anchor to append near. When omitted the content is appended to the end of the file.
- `metadata.position` (string, optional): Insert placement relative to the section. Supported values: `before`, `inside` (immediately after the anchor), and `after` (default).

#### `status_update`
- `section` (string, required): Checklist item ID
- `metadata` (dict, optional): Status info such as `{"status": "done", "proof": "evidence"}`. When omitted the existing status is preserved and proofs can still be updated.

#### `list_sections`
- Returns the discovered section anchors for the requested document, including line numbers.

#### `batch`
- `metadata.operations` (list, required): Sequence of manage_docs payloads executed in order. Nested batches are rejected for safety.

#### `create_research_doc`
- `doc_name` (string, required): Document name
- `metadata` (dict, optional): Research metadata

#### `create_bug_report`
- `metadata` (dict, required): Bug report metadata

**Optional Parameters:**
- `metadata` (dict): Additional metadata for the operation
- `dry_run` (bool): Preview changes without applying
- Metadata payloads are auto-normalized; dicts, JSON strings, and legacy key/value sequences are all accepted.

**Example Usage:**
```python
# Replace architecture section
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",
    content="## Problem Statement\n**Context:** ..."
)

# Append within a section
await manage_docs(
    action="append",
    doc="architecture",
    section="problem_statement",
    content="Updated scope paragraph",
    metadata={"position": "inside"}
)

# Update checklist status
await manage_docs(
    action="status_update",
    doc="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "code_review_completed"}
)

# Create research document
await manage_docs(
    action="create_research_doc",
    doc_name="RESEARCH_AUTH_SYSTEM_20251102",
    metadata={"research_goal": "Analyze authentication flow"}
)

# Batch multiple updates (executed sequentially)
await manage_docs(
    action="batch",
    doc="architecture",
    metadata={
        "operations": [
            {
                "action": "append",
                "doc": "architecture",
                "section": "requirements_constraints",
                "content": "Documented latency targets",
                "metadata": {"position": "after"}
            },
            {
                "action": "status_update",
                "doc": "checklist",
                "section": "documentation_hygiene",
                "metadata": {"status": "done", "proof": "PROGRESS_LOG#2025-11-02"}
            }
        ]
    }
)
```

**Returns:**
```json
{
  "ok": true,
  "doc": "architecture",
  "action": "replace_section",
  "path": "/path/to/document.md",
  "verification_passed": true,
  "dry_run": false
}
```

### `manage_docs` semantic search
**Purpose**: Semantic retrieval across registry-managed docs and logs (doc-first results by default).

**Required Parameters:**
- `action`: `"search"`
- `doc`: `"*"` (search all) or specific doc key
- `metadata.query`: search string
- `metadata.search_mode`: `"semantic"`

**Optional Filters:**
- `content_type`: `"doc"` or `"log"` (default is both)
- `project_slug` / `project_slugs` / `project_slug_prefix`
- `doc_type`, `file_path`
- `time_start` / `time_end`
- `k` (total results), `doc_k` / `log_k` overrides
- `min_similarity` (float)

**Example Usage:**
```python
# Semantic search across docs + logs
await manage_docs(
    action="search",
    doc="*",
    metadata={"query": "ExecutionContext", "search_mode": "semantic", "k": 8}
)

# Doc-only semantic search scoped to a project
await manage_docs(
    action="search",
    doc="*",
    metadata={
        "query": "ExecutionContext",
        "search_mode": "semantic",
        "content_type": "doc",
        "project_slug": "scribe_sentinel_concurrency_v1",
        "doc_k": 5
    }
)
```

### `generate_doc_templates`
**Purpose**: Create/update documentation templates for a project.

**Required Parameters:**
- `project_name` (string): Name of the project

**Optional Parameters:**
- `author` (string): Document author
- `overwrite` (bool, default: false): Overwrite existing templates
- `documents` (list): Specific documents to generate
- `base_dir` (string): Base directory for templates

**Example Usage:**
```python
# Basic usage
await generate_doc_templates(project_name="my-project")

# With author and specific documents
await generate_doc_templates(
    project_name="my-project",
    author="MyAgent",
    documents=["architecture", "phase_plan"]
)
```

**Returns:**
```json
{
  "ok": true,
  "files": ["/paths/to/generated/files.md"],
  "skipped": ["/paths/to/existing/files.md"],
  "directory": "/path/to/docs/dir",
  "validation": {/* template validation results */}
}
```

### Auto-Registration for EDIT Operations (v2.2.0+)

Starting in v2.2.0, `manage_docs` automatically registers unregistered documents when you perform EDIT operations. This eliminates "DOC_NOT_FOUND" errors and streamlines workflows for both AI agents and human users.

#### How It Works

When you call `manage_docs` with an EDIT action, the system automatically:
1. Checks if the document is registered in the project's `docs` metadata
2. If unregistered, resolves the document path based on the document key
3. Verifies the file exists on disk
4. Computes the SHA256 hash for integrity tracking
5. Updates the project's `docs_json` database field
6. Logs the registration to the progress log
7. Proceeds with your requested edit operation

**EDIT operations (auto-register if needed):**
- `list_sections` - List all section anchors in a document
- `replace_section` - Replace content using section anchors
- `apply_patch` - Apply structured or unified diff patches
- `replace_range` - Replace explicit line ranges
- `append` - Append content to document or section
- `status_update` - Update checklist item status
- `normalize_headers` - Normalize markdown headers to ATX format
- `generate_toc` - Generate table of contents
- `search` - Semantic search across documents
- `replace_text` - Replace text patterns
- `validate_crosslinks` - Validate cross-document references

**CREATE operations (explicit registration):**
These actions handle document creation and registration internally, so auto-registration is not needed:
- `create_research_doc` - Create structured research documents
- `create_bug_report` - Create structured bug reports
- `create_review_report` - Create review reports
- `create_agent_report_card` - Create agent performance reports
- `create_doc` - Create custom documents

#### Example Workflow

**Before v2.2.0 (manual registration required):**
```python
# Step 1: Explicitly register documents first
await generate_doc_templates(project_name="my_project")

# Step 2: Then perform edits
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",
    content="Updated content..."
)
```

**v2.2.0+ (auto-registration):**
```python
# Just call manage_docs directly - auto-registration handles the rest
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",
    content="Updated content..."
)
# Auto-registers 'architecture' if needed, then performs the edit
```

#### What Gets Registered

When auto-registration triggers, the following happens:

1. **Document Path Resolution**: The document key (e.g., "architecture") is mapped to its canonical filename (e.g., `ARCHITECTURE_GUIDE.md`)

2. **File Verification**: The system checks that the file exists at the expected path within the project's documentation directory

3. **Hash Computation**: A SHA256 hash is computed for the file contents to enable integrity tracking and change detection

4. **Database Update**: The project's `docs_json` field in the database is updated with the new registration

5. **Progress Log Entry**: A log entry is created documenting the auto-registration event:
   ```
   [ℹ️] [timestamp] Auto-registered 'architecture' → ARCHITECTURE_GUIDE.md
   ```

#### Requirements for Auto-Registration

Auto-registration requires all of the following conditions:

- **Database Backend**: SQLite or PostgreSQL storage must be active (auto-registration uses database-backed project metadata)
- **File Must Exist**: The document file must exist on disk at the expected path
- **Valid Document Key**: The document key must be one of the recognized types (architecture, phase_plan, checklist, etc.)
- **Active Project Context**: A project must be set via `set_project()` before calling `manage_docs`

#### Troubleshooting

**Error: "DOC_NOT_FOUND: Document 'X' not registered"**

This error occurs when:
- Auto-registration is disabled (should not happen in v2.2.0+)
- The action is not an EDIT operation (use CREATE operations for new docs)
- Something prevented auto-registration from completing

*Solution:*
1. Verify you're using an EDIT action (see list above)
2. Check that the file exists: `ls .scribe/docs/dev_plans/<project>/<DOC_FILE>.md`
3. Review progress log for auto-registration errors
4. Try manual registration: `await generate_doc_templates(project_name="<project>")`

**Error: "Cannot auto-register: file does not exist at path X"**

The document file doesn't exist at the expected location.

*Solution:*
1. Create the file first: `await generate_doc_templates(project_name="<project>")`
2. Or use a CREATE action to generate a new document
3. Verify the project name matches the directory structure

**Auto-registration logs but edit fails**

Registration succeeded, but the edit operation encountered an issue.

*Solution:*
1. For `replace_section`: Verify section anchors exist using `list_sections`
2. For `replace_range`: Check that line numbers are valid and within bounds
3. For `apply_patch`: Ensure YAML frontmatter is valid and not corrupted
4. Review the error message for specific guidance

**Database connectivity issues**

Auto-registration requires database write access.

*Solution:*
1. Verify database backend is configured: Check `SCRIBE_STORAGE_BACKEND` environment variable
2. For SQLite: Ensure write permissions on the database file
3. For PostgreSQL: Verify connection string and credentials
4. Run diagnostics: `await scribe_doctor()` to check system health

#### Best Practices

**For AI Agents:**
- Don't worry about pre-registering documents - just call `manage_docs` with EDIT actions directly
- Use CREATE actions (`create_research_doc`, `create_bug_report`) for new documents
- Check error messages for actionable guidance if auto-registration fails

**For Human Users:**
- Auto-registration works transparently - no workflow changes needed
- Use `generate_doc_templates()` to create initial project scaffolding
- Monitor progress logs to see when auto-registration occurs

**For Tool Developers:**
- Auto-registration is handled in the `manage_docs` tool entry point
- No changes needed to individual action handlers
- All EDIT actions benefit automatically

---

## Log Maintenance

### `rotate_log`
**Purpose**: Archive current progress log and start fresh file.

**Optional Parameters:**
- `confirm` (bool): When True, perform actual rotation
- `dry_run` (bool, default: true): Preview rotation without changes
- `log_type` (string): Specific log type to rotate
- `log_types` (list): Multiple log types to rotate
- `rotate_all` (bool): Rotate every configured log type
- `auto_threshold` (bool): Only rotate if entry count exceeds threshold
- `threshold_entries` (int): Override entry threshold
- `suffix` (string): Optional suffix for archive filenames
- `custom_metadata` (string): JSON metadata for rotation record

**Example Usage:**
```python
# Preview rotation
await rotate_log(dry_run=True)

# Actually rotate progress log
await rotate_log(confirm=True)

# Rotate multiple log types
await rotate_log(
    confirm=True,
    log_types=["progress", "doc_updates"]
)

# Auto-threshold rotation
await rotate_log(
    confirm=True,
    auto_threshold=True,
    threshold_entries=1000
)
```

**Returns:**
```json
{
  "ok": true,
  "rotations": [
    {
      "log_type": "progress",
      "dry_run": false,
      "rotation_id": "unique-id",
      "project": "project-name",
      "current_file_path": "/path/to/current.md",
      "archived_to": "/path/to/archive.md",
      "entry_count": 150,
      "requires_confirmation": false,
      "auto_threshold_triggered": false
    }
  ]
}
```

### `verify_rotation_integrity`
**Purpose**: Verify the integrity of a specific rotation archive.

**Required Parameters:**
- `archive_path` (string): Path to rotation archive to verify

**Example Usage:**
```python
await verify_rotation_integrity(
    archive_path="/path/to/archive.md"
)
```

### `get_rotation_history`
**Purpose**: Return recent rotation history entries for the active project.

**Parameters:** None (requires active project)

**Example Usage:**
```python
await get_rotation_history()
```

**Returns:**
```json
{
  "ok": true,
  "project": "project-name",
  "rotation_count": 3,
  "rotations": [
    {
      "rotation_id": "id",
      "timestamp": "2025-11-02 07:40:21 UTC",
      "log_type": "progress",
      "entry_count": 150
    }
  ]
}
```

---

## Project Cleanup

### `delete_project`
**Purpose**: Delete or archive a project and all associated data.

**Required Parameters:**
- `name` (string): Project name to delete
- `confirm` (bool): Must be True to proceed with deletion

**Optional Parameters:**
- `mode` (string, default: "archive"): "archive" or "permanent"
- `force` (bool): Override safety checks (not recommended)
- `archive_path` (string): Custom archive directory
- `agent_id` (string): Agent identification

**Example Usage:**
```python
# Archive project (safe default)
await delete_project(
    name="old-project",
    confirm=True
)

# Permanent deletion (dangerous)
await delete_project(
    name="temp-project",
    confirm=True,
    mode="permanent"
)
```

**Returns:**
```json
{
  "success": true,
  "project_name": "project-name",
  "mode": "archive",
  "message": "Project 'project-name' archived to path",
  "archive_location": "/path/to/archive",
  "database_cleanup": true
}
```

---

## Best Practices

### 1. **Always Set Project First**
```python
await set_project(name="your-project")
# Now use other tools
```

### 2. **Use Structured Metadata**
```python
await append_entry(
    message="Fixed critical bug",
    status="success",
    meta={
        "component": "auth",
        "bug_id": "BUG-123",
        "tests_fixed": 5,
        "phase": "bugfix"
    }
)
```

### 3. **Log Meaningful Events**
- Code changes and why they were made
- Test results and failures
- Decisions and reasoning
- Bug discoveries and fixes
- Milestone completions

### 4. **Use Bulk Mode for Backfilling**
```python
# If you forget to log, use bulk mode immediately
await append_entry(items=[
    {"message": "Step 1 completed", "status": "success"},
    {"message": "Step 2 completed", "status": "success"},
    {"message": "Bug discovered", "status": "bug", "agent": "DebugBot"}
])
```

### 5. **Leverage Enhanced Search**
```python
# Cross-project learning
await query_entries(
    message="authentication pattern",
    search_scope="all_projects",
    document_types=["architecture", "progress"],
    relevance_threshold=0.9
)
```

---

## Error Handling

Common errors and solutions:

1. **"No project configured"** → Call `set_project()` first
2. **"Invalid arguments for tool"** → Check parameter names and types
3. **"dictionary update sequence element #0 has length 1; 2 is required"** → `meta` parameter format issue

---

## Tool Summary Quick Reference

| Tool | Purpose | Required Params | Project Context |
|------|---------|----------------|-----------------|
| `set_project` | Initialize project | `name` | No |
| `get_project` | Get current context | None | Yes |
| `list_projects` | Browse projects | None | No |
| `append_entry` | **PRIMARY** logging | `message` or `items` | Yes |
| `read_recent` | Recent entries | None | Yes |
| `query_entries` | Search logs | None | Yes |
| `manage_docs` | Documentation | `action`, `doc` | Yes |
| `generate_doc_templates` | Create templates | `project_name` | No |
| `rotate_log` | Archive logs | None | Yes |
| `verify_rotation_integrity` | Verify archive | `archive_path` | No |
| `get_rotation_history` | Rotation history | None | Yes |
| `delete_project` | Remove project | `name`, `confirm` | No |
