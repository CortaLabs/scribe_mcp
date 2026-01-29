---
id: read_file_search_audit-files
title: File Operations (read_file, search, edit_file)
doc_name: files
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-29'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# File Operations (read_file, search, edit_file)

## Contents
- `read_file` -- repo-scoped file reading
- `search` -- multi-file codebase search
- `edit_file` -- safe file editing

---

### `read_file`
**Purpose**: Repo-scoped file access (by default) with deterministic scan/chunk/page/search modes, dependency analysis, and read provenance logging. Optional out-of-repo reads are allowed when explicitly enabled.

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
- `include_impact`: `False` (default) or `True` - Include impact radius (requires `include_dependencies=True`)
- `allow_outside_repo`: `False` (default) or `True` - Allow reads outside repo_root (denylist still enforced). Paths under `/.claude/skills/` or `/.codex/skills/` are always allowed.
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
   - Shows resolved file paths with checkmarks when files exist
   - Detects workspace root automatically (.git, pyproject.toml markers)

3. **Impact Radius (Blast Radius)**:
   - Shows how many files import the current file
   - Categorized by impact level: Low (0-4), Medium (5-15), High (16+)
   - Lists up to 20 files that import this module
   - Helps assess change risk before modifications

4. **Boundary Enforcement**:
   - Checks imports against `.scribe/config/boundary_rules.yaml` rules
   - Detects forbidden import patterns
   - Shows violations with severity levels: ERROR, WARNING, INFO

**Example Usage:**
```python
# Basic scan (metadata + structure)
await read_file(path="tools/read_file.py", mode="scan_only")

# Scan with dependency analysis
await read_file(path="tools/read_file.py", mode="scan_only", include_dependencies=True)

# Read specific chunk
await read_file(path="references/Scribe_Usage.md", mode="chunk", chunk_index=[0])

# Regex search (default mode)
await read_file(path="tools/read_file.py", mode="search", query=r"async\s+def\s+\w+")

# Search with context lines
await read_file(path="server.py", mode="search", query="async def", context_lines=2)
```

**Notes:**
- Every read is logged with provenance (absolute path, hash, byte size, encoding, read mode)
- Enforces repo scope by default; out-of-scope paths are denied
- Dependency analysis is static only - does not execute code or resolve runtime imports

---

### `search`
**Purpose**: Multi-file codebase search with grep/rg feature parity. Agents MUST use this instead of `grep`, `rg`, `find`, or Bash search commands.

**Required Parameters:**
- `agent` (string): Agent identifier
- `pattern` (string): Search pattern (regex by default)

**Key Optional Parameters:**
- `path` (string): Directory or file to search (default: repo root)
- `glob` (string): Glob filter (e.g. `"*.py"`, `"src/**/*.ts"`)
- `type` (string): File type filter (`py`, `js`, `ts`, `rust`, `go`, `java`)
- `output_mode` (string): `"content"` (default), `"files_with_matches"`, `"count"`
- `context_lines` (int): Context lines around matches (default: 0)
- `case_insensitive` (bool): Case-insensitive matching (default: False)
- `regex` (bool): Regex mode (default: True). Set False for literal.
- `multiline` (bool): Multiline matching (default: False)
- `max_matches_per_file` (int): Per-file limit (default: 50)
- `max_total_matches` (int): Total limit (default: 200)

See `references/search.md` for full parameter reference and examples.

---

### `edit_file`
**Purpose**: Safe file editing with exact string replacement. Agents SHOULD use this instead of `sed` or Bash editing.

**Required Parameters:**
- `agent` (string): Agent identifier
- `path` (string): File to edit (repo-relative or absolute)
- `old_string` (string): Exact string to find
- `new_string` (string): Replacement string

**Optional Parameters:**
- `replace_all` (bool): Replace all occurrences (default: False)
- `dry_run` (bool): Preview only (default: **True** -- must set False to apply)
- `format` (string): Output format (default: "readable")

**Enforcement:**
- `read_file` MUST be called on the file first (tool-level enforcement, not policy)
- `dry_run=True` by default -- changes are NOT written unless you set `dry_run=False`
- Automatic `.bak` backup before every write
- Sandboxed to repo root

See `references/edit_file.md` for full reference, error codes, and examples.

---

## Workflow: search -> read -> edit

The three file tools form a pipeline:

```python
# 1. Find files containing the pattern
search(agent="CoderAgent", pattern="deprecated_api", type="py")

# 2. Read the file (REQUIRED before edit)
read_file(agent="CoderAgent", path="api/handler.py")

# 3. Preview the edit (dry run)
edit_file(agent="CoderAgent", path="api/handler.py",
          old_string="deprecated_api()", new_string="new_api()")

# 4. Apply the edit
edit_file(agent="CoderAgent", path="api/handler.py",
          old_string="deprecated_api()", new_string="new_api()",
          dry_run=False)
```

---

## Drop-In Snippet for Agent Files

Copy-paste this into agent definitions in other projects:

```markdown
### File Operations Policy
- **Reading files:** Use `scribe.read_file` (NOT cat/head/tail)
- **Multi-file search:** MUST use `scribe.search` (NOT grep, rg, find, or Bash search)
- **File editing:** SHOULD use `scribe.edit_file` (NOT sed, awk, or Bash edits)
- **Enforcement:** `edit_file` requires `read_file` on the same file first (tool-enforced)
- **Safety:** `edit_file` defaults to `dry_run=True` -- must set `False` to apply changes
```
