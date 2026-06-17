---
id: read_file_search_audit-search
title: Multi-File Search (search)
doc_name: search
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
# Multi-File Search (search)

## Contents
- `search`

### `search`
**Purpose**: Multi-file codebase search with grep/rg feature parity. Agents MUST use this instead of `grep`, `rg`, `find`, or any Bash search commands. Enforces the same repo sandbox as `read_file`.

**Required Parameters:**
- `agent` (string): Agent identifier (required for audit trail)
- `pattern` (string): Search pattern (regex by default, literal if `regex=False`)

**Optional Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | repo root | Directory or file to search |
| `glob` | string | None | Glob pattern to filter files (e.g. `"*.py"`, `"src/**/*.ts"`) |
| `type` | string | None | File type filter (`py`, `js`, `ts`, `rust`, `go`, `java`, etc.) |
| `output_mode` | string | `"content"` | `"content"` (matching lines), `"files_with_matches"` (paths only), `"count"` (match counts) |
| `format` | string | `"readable"` | Output format: `"readable"`, `"structured"`, `"compact"` |
| `context_lines` | int | `0` | Lines of context around matches (both before and after) |
| `before_context` | int | None | Lines before match (overrides `context_lines` for before) |
| `after_context` | int | None | Lines after match (overrides `context_lines` for after) |
| `case_insensitive` | bool | `False` | Case-insensitive matching |
| `regex` | bool | `True` | `True` for regex, `False` for literal string matching |
| `multiline` | bool | `False` | Enable multiline matching (pattern can span lines) |
| `max_matches_per_file` | int | `50` | Max matches per file |
| `max_total_matches` | int | `200` | Max total matches across all files |
| `max_files` | int | `100` | Max files to include in results |
| `line_numbers` | bool | `True` | Show line numbers in output |
| `skip_binary` | bool | `True` | Skip binary files |
| `max_file_size_mb` | int | `10` | Max file size in MB to search |

**Output Modes:**

| Mode | Returns | Use When |
|------|---------|----------|
| `content` | Matching lines with context | You need to see the actual code |
| `files_with_matches` | File paths only | You need to know which files match |
| `count` | Match count per file | You need frequency information |

**Security:**
- Search is sandboxed to the repository root. Paths outside the repo are rejected.
- Binary files and denied paths (`.git/`, secrets, etc.) are automatically skipped.

**Examples:**
```python
# Basic regex search
search(agent="CoderAgent", pattern="def handle_")

# Filter by file type
search(agent="CoderAgent", pattern="import", type="py")

# Glob pattern
search(agent="CoderAgent", pattern="TODO", glob="src/**/*.ts")

# Count matches per file
search(agent="CoderAgent", pattern="error", output_mode="count")

# List files only
search(agent="CoderAgent", pattern="class", output_mode="files_with_matches")

# With context lines
search(agent="CoderAgent", pattern="def main", context_lines=3)

# Case-insensitive literal search
search(agent="CoderAgent", pattern="error", case_insensitive=True, regex=False)

# Multiline search
search(agent="CoderAgent", pattern="class.*:\n.*def __init__", multiline=True)
```

**Notes:**
- Default mode is regex (`regex=True`). Set `regex=False` for literal matching.
- Results are truncated when limits are reached; check for `truncated: true` in structured output.
- Same denylist and sandbox rules as `read_file`.
