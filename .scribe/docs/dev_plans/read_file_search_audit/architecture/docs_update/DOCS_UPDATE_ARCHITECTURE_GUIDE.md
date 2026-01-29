---
id: read_file_search_audit-docs-update-architecture-guide
title: 'Architecture Guide: Documentation Update for search & edit_file Tools'
doc_name: DOCS_UPDATE_ARCHITECTURE_GUIDE
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
# Architecture Guide: Documentation Update for search & edit_file Tools

**Project:** read_file_search_audit
**Sub-plan:** docs_update
**Author:** ArchitectAgent-DocsUpdate
**Date:** 2026-01-29

---

## 1. Problem Statement
<!-- ID: problem_statement -->

Two new MCP tools (`search` and `edit_file`) are fully implemented and registered but have ZERO documentation across 22 files. Agents cannot discover these tools through normal reference channels.

---

## 2. Skill Sync Chain Design
<!-- ID: skill_sync_chain -->

### Source of Truth

```
.claude/skills/scribe-mcp-usage/       (REPO-LOCAL - source of truth, ALWAYS WINS)
    |
    +---> .codex/skills/scribe-mcp-usage/   (REPO COPY - sync target)
    |
    +---> ~/.claude/skills/scribe-mcp-usage/ (GLOBAL COPY - sync target)
```

**The repo-local `.claude/skills/` directory is the canonical source.** It was accidentally deleted and must be RECREATED from `.codex/` (which has the most recent content) before any updates.

### Sync Rules
1. RECREATE `.claude/skills/scribe-mcp-usage/` by copying from `.codex/skills/scribe-mcp-usage/` (one-time recovery)
2. ALL edits start at `.claude/skills/scribe-mcp-usage/` (repo-local source)
3. Then copy changed files OUT to `.codex/skills/scribe-mcp-usage/` AND `~/.claude/skills/scribe-mcp-usage/`
4. Sync is file-level copy (not symlink)
5. Verify SHA256 match after sync

### Files to Create in Skill (at `.claude/skills/`)
- `.claude/skills/scribe-mcp-usage/references/search.md` (NEW)
- `.claude/skills/scribe-mcp-usage/references/edit_file.md` (NEW)

### Files to Update in Skill (at `.claude/skills/`)
- `.claude/skills/scribe-mcp-usage/SKILL.md` (add tool navigation entries)
- `.claude/skills/scribe-mcp-usage/references/INDEX.md` (add index entries)
- `.claude/skills/scribe-mcp-usage/references/Operational_Contract.md` (add tool schemas)
- `.claude/skills/scribe-mcp-usage/references/files.md` (rename to "File Operations" or add search/edit sections)
- `.claude/skills/scribe-mcp-usage/references/quickstart.md` (brief mention)
- `.claude/skills/scribe-mcp-usage/references/Scribe_Usage.md` (full tool docs)

---

## 3. Tool Signatures (Reference for All Docs)
<!-- ID: tool_signatures -->

### search() — Multi-file Codebase Search

```python
search(
    # REQUIRED
    agent: str,           # Agent identifier
    pattern: str,         # Search pattern (regex by default)
    # Scope
    path: str = None,     # Directory or file (default: repo root)
    glob: str = None,     # Glob filter (e.g. "*.py", "src/**/*.ts")
    type: str = None,     # File type (py, js, ts, rust, go, java, etc.)
    # Output
    output_mode: str = "content",  # "content" | "files_with_matches" | "count"
    format: str = "readable",
    # Context
    context_lines: int = 0,
    before_context: int = None,
    after_context: int = None,
    # Behavior
    case_insensitive: bool = False,
    regex: bool = True,
    multiline: bool = False,
    # Limits
    max_matches_per_file: int = 50,
    max_total_matches: int = 200,
    max_files: int = 100,
    # Display
    line_numbers: bool = True,
    # Performance
    skip_binary: bool = True,
    max_file_size_mb: int = 10,
)
```

**Purpose:** Replace `grep`, `rg`, and bash search commands. Searches across repository files with regex/literal patterns, file type filtering, glob patterns, context lines, and multiple output modes. Respects repo boundary sandbox.

### edit_file() — Safe File Editing

```python
edit_file(
    # REQUIRED
    agent: str,           # Agent identifier
    path: str,            # File to edit (repo-relative or absolute)
    old_string: str,      # Exact string to find
    new_string: str,      # Replacement string
    # Behavior
    replace_all: bool = False,  # Replace all occurrences (default: first only)
    # Safety
    dry_run: bool = True,       # Preview without writing (DEFAULT IS TRUE)
    # Output
    format: str = "readable",
)
```

**Purpose:** Replace `sed`, `awk`, and manual file editing bash commands. Safe exact-string replacement with mandatory read-before-edit enforcement, automatic backup, dry-run preview, and diff output.

**CRITICAL SAFETY:** `read_file` MUST be called on the file in the current session before `edit_file` will accept edits. This is enforced at the tool level — the tool rejects edits on unread files.

---

## 4. Drop-In Snippet for Other Projects
<!-- ID: drop_in_snippet -->

This is a self-contained block that can be copy-pasted into ANY agent file in ANY project to document the Scribe file toolkit:

```markdown
## Scribe File Toolkit (search, read_file, edit_file)

Three Scribe MCP tools handle all file operations. Use them INSTEAD of shell commands.

| Task | Use This | NOT This |
|------|----------|----------|
| Find patterns in files | `scribe.search(pattern, path, type)` | `grep`, `rg`, `find` |
| Read file contents | `scribe.read_file(path, mode)` | `cat`, `head`, `tail` |
| Edit file contents | `scribe.edit_file(path, old_string, new_string)` | `sed`, `awk`, manual editing |

### Workflow: Always Read Before Edit

1. **Search** to find what you need: `search(agent="...", pattern="def my_func", type="py")`
2. **Read** the file: `read_file(agent="...", path="path/to/file.py")`
3. **Edit** with exact replacement: `edit_file(agent="...", path="path/to/file.py", old_string="old code", new_string="new code", dry_run=False)`

**Enforcement:** `edit_file` will REJECT edits if `read_file` was not called first on that file in the current session. This is a tool-level safety mechanism, not just a policy.

### Quick Reference

**search** — multi-file regex/literal search:
- `pattern` (required): regex by default, literal with `regex=False`
- `type`: file type filter (`py`, `js`, `ts`, `rust`, `go`, `java`)
- `glob`: glob pattern (`"*.py"`, `"src/**/*.ts"`)
- `output_mode`: `"content"` (default), `"files_with_matches"`, `"count"`
- `context_lines`: lines of context around matches
- `case_insensitive`: case-insensitive matching

**edit_file** — safe exact-string replacement:
- `old_string` / `new_string` (required): exact match and replace
- `dry_run=True` (default): preview mode, set `False` to apply
- `replace_all=False` (default): first occurrence only
- Creates automatic backup before writing
```

---

## 5. File-by-File Update Specifications
<!-- ID: file_specs -->

### BATCH 0: Recreate `.claude/skills/` from `.codex/` (Recovery)

Copy `.codex/skills/scribe-mcp-usage/` to `.claude/skills/scribe-mcp-usage/` to restore the accidentally deleted source directory. This is a one-time recovery step.

### BATCH 1: Skill Source Update (at `.claude/skills/`)

#### 1a. NEW FILE: `.claude/skills/scribe-mcp-usage/references/search.md`
Create dedicated reference doc for search tool. Follow pattern of existing `read_file.md`.

Content structure:
```
# Multi-File Search (search)
## Contents
### `search`
- Full parameter table (all 17 params with types, defaults, descriptions)
- Output modes explained with examples
- File type filters list
- Context lines usage
- Multiline search
- Limits and performance
## Examples
- Basic regex search
- File type filtered search
- Glob pattern search
- Count mode
- Files-only mode
- Case insensitive
- Context lines
- Multiline pattern
```
Approximate length: ~120 lines

#### 1b. NEW FILE: `.claude/skills/scribe-mcp-usage/references/edit_file.md`
Create dedicated reference doc for edit_file tool.

Content structure:
```
# File Editing (edit_file)
## Contents
### `edit_file`
- Full parameter table (7 params)
- Read-before-edit enforcement explained
- Dry-run workflow (preview then apply)
- Backup mechanism
- Error handling (STRING_NOT_FOUND, SANDBOX_VIOLATION, etc.)
## Examples
- Dry-run preview
- Apply edit
- Replace all occurrences
- Full workflow (search -> read -> edit)
```
Approximate length: ~100 lines

#### 1c. UPDATE: `.claude/skills/scribe-mcp-usage/SKILL.md`
In the `### Tools` section (line 17-20), add:
```markdown
- `references/search.md` — multi-file codebase search (grep/rg replacement).
- `references/edit_file.md` — safe file editing with read-before-edit enforcement.
```

In `## Non-negotiables` (line 40-44), change:
```
- Use `read_file` for file contents; avoid shell reads.
```
To:
```
- Use `read_file` for file contents, `search` for multi-file grep, `edit_file` for file edits; avoid shell reads/edits.
```

### BATCH 2: Skill Sync

Copy ALL changed files from `.claude/skills/scribe-mcp-usage/` (repo-local source) to BOTH `.codex/skills/scribe-mcp-usage/` AND `~/.claude/skills/scribe-mcp-usage/`:
- `SKILL.md`
- `references/search.md` (new)
- `references/edit_file.md` (new)
- `references/INDEX.md`
- `references/Operational_Contract.md`
- `references/files.md`
- `references/quickstart.md`
- `references/Scribe_Usage.md`

Verify SHA256 match for each copied file.

### BATCH 3: Governance Docs

#### 3a. `docs/Scribe_Usage.md` — Add full tool reference sections
Add after the existing `read_file` section (approx line 869+):
- `## search` section (~100 lines): full params, examples, output modes
- `## edit_file` section (~80 lines): full params, read-before-edit, dry-run, examples

#### 3b. `CLAUDE.md` (scribe_mcp root)
In "Essential Tools Quick Reference" table (line 611+), add:
```
| `search(agent, pattern, path, type, glob)` | Multi-file codebase search | grep/rg replacement |
| `edit_file(agent, path, old_string, new_string)` | Safe file editing | read_file required first |
```

In "File Reading Policy" (line 148 area), update to:
```
- ALL file content reads MUST use `scribe.read_file`
- ALL multi-file searches MUST use `scribe.search` (NOT grep, rg, or find)
- ALL file edits SHOULD use `scribe.edit_file` (NOT sed, awk, or manual editing)
- `edit_file` requires `read_file` first (enforced at tool level)
```

#### 3c. `AGENTS.md`
In tool listing section (line 254+), add search and edit_file entries.
In file reading policy (line 37+), add search/edit_file references.

#### 3d. `config/CLAUDE.md`
In Tools Architecture listing (lines 280-297), add:
```
- search.py - Multi-file codebase search (grep/rg replacement)
- edit_file.py - Safe file editing with exact string replacement
```

### BATCH 4: Codex Skill References

#### 4a. `.claude/skills/.../references/Operational_Contract.md` (then sync to .codex + ~/.claude)
Add tool schema sections for search and edit_file. Follow existing tool schema pattern.

#### 4b. `.claude/skills/.../references/files.md` (then sync to .codex + ~/.claude)
Rename heading from "File Reading (read_file)" to "File Operations (read_file, search, edit_file)".
Add `### search` and `### edit_file` sections with param tables and examples.

#### 4c. `.claude/skills/.../references/INDEX.md` (then sync to .codex + ~/.claude)
Add entries:
```
- `search.md` — multi-file codebase search
- `edit_file.md` — safe file editing
```

#### 4d. `.claude/skills/.../references/quickstart.md` (then sync to .codex + ~/.claude)
Add brief mention of search and edit_file in tool overview.

#### 4e. `.claude/skills/.../references/Scribe_Usage.md` (then sync to .codex + ~/.claude)
Mirror the same additions made to `docs/Scribe_Usage.md` in Batch 3a.

### BATCH 5: Agent Files

For ALL 5 agent files in `.claude/agents/` AND their mirrors in `docs/claude_code_subagents/` (10 files total):

Files:
- `scribe-research-analyst.md`
- `scribe-coder.md`
- `scribe-architect.md`
- `scribe-review-agent.md`
- `scribe-bug-hunter.md`

In each file's "File Reading Policy" section, add after the existing read_file line:
```markdown
- **For multi-file search:** MUST use `scribe.search` (NOT grep, rg, find, or bash search commands)
- **For file editing:** SHOULD use `scribe.edit_file` (NOT sed, awk, or manual editing). Requires `read_file` first (tool-enforced).
```

In each file's tool usage table (if present), add:
```
| `search` | Multi-file codebase search | grep/rg replacement |
| `edit_file` | Safe file editing | Requires read_file first |
```

### BATCH 6: Minor Updates

#### 6a. `README.md`
Add new feature sections for search and edit_file near the existing read_file features section (~30 lines each).

#### 6b. `docs/whitepapers/scribe_mcp_whitepaper.md`
Add `edit_file.py` to directory tree listing. Add edit_file description to tool suite section.

---

## 6. Design Decisions
<!-- ID: design_decisions -->

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Create separate reference files (search.md, edit_file.md) | Yes | Follows existing pattern (read_file.md exists separately). Progressive disclosure. |
| Update files.md heading | Rename to "File Operations" | Groups the trilogy of file tools logically |
| Drop-in snippet location | In architecture guide AND in SKILL.md | Maximizes discoverability |
| Batch ordering | Skill source first | Ensures source of truth is correct before syncing copies |
| Agent file updates | Both .claude/agents/ and docs/claude_code_subagents/ | Research confirmed these must stay in sync |
| dry_run=True default | Document prominently | Most common agent mistake will be forgetting to set dry_run=False |
