---
id: read_file_search_audit-edit-file
title: File Editing (edit_file)
doc_name: edit_file
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
# File Editing (edit_file)

## Contents
- `edit_file`

### `edit_file`
**Purpose**: Safe file editing with exact string replacement. Agents SHOULD use this instead of `sed`, `awk`, or manual Bash editing. Enforces read-before-edit at the tool level.

**Required Parameters:**
- `agent` (string): Agent identifier (required for audit trail)
- `path` (string): File to edit (repo-relative or absolute)
- `old_string` (string): Exact string to find in the file
- `new_string` (string): Replacement string

**Optional Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `replace_all` | bool | `False` | Replace all occurrences (default: first only) |
| `dry_run` | bool | `True` | Preview without writing. **MUST set `False` to apply changes.** |
| `format` | string | `"readable"` | Output format: `"readable"`, `"structured"`, `"compact"` |

**CRITICAL: Read-Before-Edit Enforcement**

`read_file` MUST be called on the target file in the current session before `edit_file` will accept edits. This is enforced at the tool level -- not just policy. If you skip `read_file`, the tool returns:

```json
{
  "ok": false,
  "error": "READ_BEFORE_EDIT_REQUIRED",
  "message": "Cannot edit <path> - file not read in this session",
  "required_action": "Call read_file(path='<path>') before editing"
}
```

**CRITICAL: Dry-Run Default**

`dry_run=True` is the default. Calling `edit_file` without `dry_run=False` only previews the change (diff, occurrence count, lines affected). You MUST explicitly set `dry_run=False` to write changes.

**Workflow:**
1. `read_file(path="target.py")` -- read the file first (required)
2. `edit_file(path="target.py", old_string="...", new_string="...")` -- preview (dry run)
3. Review the diff output
4. `edit_file(path="target.py", old_string="...", new_string="...", dry_run=False)` -- apply

**Backup:** When `dry_run=False`, a `.bak` backup is automatically created before writing.

**Error Codes:**

| Error | Cause |
|-------|-------|
| `READ_BEFORE_EDIT_REQUIRED` | `read_file` not called on this file in current session |
| `SESSION_REQUIRED` | No session ID available |
| `SANDBOX_VIOLATION` | File is outside the repository boundary |
| `FILE_NOT_FOUND` | File does not exist |
| `STRING_NOT_FOUND` | `old_string` not found in the file |
| `WRITE_ERROR` | Failed to write (backup preserved) |

**Security:**
- Sandboxed to repository root (same as `read_file` and `search`).
- Automatic backup before every write.
- Exact string matching only (no regex) -- prevents accidental mass edits.

**Examples:**
```python
# Preview a change (dry run, default)
edit_file(
    agent="CoderAgent",
    path="config/settings.py",
    old_string="DEBUG = True",
    new_string="DEBUG = False"
)

# Apply the change
edit_file(
    agent="CoderAgent",
    path="config/settings.py",
    old_string="DEBUG = True",
    new_string="DEBUG = False",
    dry_run=False
)

# Replace all occurrences
edit_file(
    agent="CoderAgent",
    path="utils/helpers.py",
    old_string="old_function_name",
    new_string="new_function_name",
    replace_all=True,
    dry_run=False
)

# Full workflow: search -> read -> edit
search(agent="CoderAgent", pattern="deprecated_api", type="py")
read_file(agent="CoderAgent", path="api/handler.py")
edit_file(agent="CoderAgent", path="api/handler.py",
          old_string="deprecated_api()", new_string="new_api()",
          dry_run=False)
```

**Notes:**
- Only exact string matching (no regex). Use `search` to find patterns first.
- `old_string` must be unique in the file unless using `replace_all=True`.
- The diff output in dry-run mode shows a unified diff for review.
