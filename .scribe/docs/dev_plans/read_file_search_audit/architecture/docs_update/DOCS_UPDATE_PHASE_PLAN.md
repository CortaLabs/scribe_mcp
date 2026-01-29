---
id: read_file_search_audit-docs-update-phase-plan
title: 'Phase Plan: Documentation Update for search & edit_file Tools'
doc_name: DOCS_UPDATE_PHASE_PLAN
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
# Phase Plan: Documentation Update for search & edit_file Tools

**Project:** read_file_search_audit
**Sub-plan:** docs_update
**Author:** ArchitectAgent-DocsUpdate
**Date:** 2026-01-29

---

## Phase Overview

| Phase | Description | Files | Est. Lines |
|-------|-------------|-------|------------|
| Batch 1 | Skill source update (new + modified files) | 3 new, 5 modified | ~350 |
| Batch 2 | Skill sync (~/.claude -> .codex) | 8 file copies | 0 (copies) |
| Batch 3 | Governance docs (Scribe_Usage, CLAUDE.md, AGENTS.md, config) | 4 | ~250 |
| Batch 4 | Codex skill references (Operational_Contract, files.md, INDEX, quickstart, Scribe_Usage) | 5 | ~200 |
| Batch 5 | Agent files (5 in .claude/agents + 5 mirrors) | 10 | ~50 |
| Batch 6 | Minor updates (README, whitepaper) | 2 | ~70 |

**Total: 22 unique files, ~600 lines of new/modified content**

---

## Batch 0: Recreate `.claude/skills/` from `.codex/` (Recovery)
<!-- ID: batch_0 -->

**Dependency:** None (first step)
**Scope:** Restore accidentally deleted `.claude/skills/scribe-mcp-usage/` directory

### Task Package 0.1: Copy `.codex/skills/` to `.claude/skills/`

**Scope:** Recreate the repo-local source directory from the `.codex/` copy
**Dependencies:** None

**Specifications:**
1. Create directory `.claude/skills/scribe-mcp-usage/references/`
2. Copy ALL files from `.codex/skills/scribe-mcp-usage/` to `.claude/skills/scribe-mcp-usage/`
3. Verify SHA256 match for all copied files

**Verification:**
- [ ] `.claude/skills/scribe-mcp-usage/SKILL.md` exists and matches `.codex/` copy
- [ ] All reference files present in `.claude/skills/scribe-mcp-usage/references/`

**Out of Scope:** Do NOT modify any file contents yet (that is Batch 1)

---

## Batch 1: Skill Source Update (at `.claude/skills/`)
<!-- ID: batch_1 -->

**Dependency:** Batch 0 (`.claude/skills/` must exist)
**Scope:** Create 2 new reference files + update 1 existing file in `.claude/skills/scribe-mcp-usage/`

### Task Package 1.1: Create `references/search.md`

**Scope:** Create new file at `.claude/skills/scribe-mcp-usage/references/search.md`
**Files to Create:** 1 new file
**Dependencies:** None

**Specifications:**
1. Create `search.md` following the structure pattern of existing `read_file.md`
2. Include:
   - Title: `# Multi-File Search (search)`
   - `## Contents` with `### search` subsection
   - Full parameter table with all 17 parameters:
     - agent (str, required), pattern (str, required)
     - path (str, default: repo root), glob (str), type (str)
     - output_mode (str, default: "content"), format (str, default: "readable")
     - context_lines (int, 0), before_context (int, None), after_context (int, None)
     - case_insensitive (bool, False), regex (bool, True), multiline (bool, False)
     - max_matches_per_file (int, 50), max_total_matches (int, 200), max_files (int, 100)
     - line_numbers (bool, True), skip_binary (bool, True), max_file_size_mb (int, 10)
   - Output modes section: content, files_with_matches, count
   - Supported file types: py, js, ts, rust, go, java, etc.
   - `## Examples` section with 6+ examples:
     - Basic regex: `search(agent="...", pattern="def handle_")`
     - Type filter: `search(agent="...", pattern="import", type="py")`
     - Glob: `search(agent="...", pattern="TODO", glob="src/**/*.ts")`
     - Count mode: `search(agent="...", pattern="error", output_mode="count")`
     - Files only: `search(agent="...", pattern="class", output_mode="files_with_matches")`
     - Context: `search(agent="...", pattern="def main", context_lines=3)`
     - Case insensitive: `search(agent="...", pattern="error", case_insensitive=True)`
3. ~120 lines total

**Verification:**
- [ ] File exists at `.claude/skills/scribe-mcp-usage/references/search.md`
- [ ] All 17 parameters documented with types and defaults
- [ ] At least 6 examples included
- [ ] Follows read_file.md structural pattern

**Out of Scope:** Do NOT modify any .codex files (that's Batch 2)

### Task Package 1.2: Create `references/edit_file.md`

**Scope:** Create new file at `.claude/skills/scribe-mcp-usage/references/edit_file.md`
**Files to Create:** 1 new file
**Dependencies:** None

**Specifications:**
1. Create `edit_file.md` following the structure pattern of existing `read_file.md`
2. Include:
   - Title: `# File Editing (edit_file)`
   - `## Contents` with `### edit_file` subsection
   - Full parameter table with all 7 parameters:
     - agent (str, required), path (str, required)
     - old_string (str, required), new_string (str, required)
     - replace_all (bool, False), dry_run (bool, True), format (str, "readable")
   - Read-before-edit enforcement section:
     - `read_file` MUST be called on the target file in the current session
     - Tool returns `READ_BEFORE_EDIT_REQUIRED` error if not
     - This is tool-level enforcement, not just policy
   - Dry-run workflow:
     - Default is `dry_run=True` (preview only)
     - Shows diff, occurrence count, lines affected
     - Must explicitly set `dry_run=False` to apply
   - Backup mechanism: automatic `.bak` file created before write
   - Error codes: STRING_NOT_FOUND, SANDBOX_VIOLATION, READ_BEFORE_EDIT_REQUIRED, SESSION_REQUIRED
   - `## Examples` section with 4+ examples:
     - Dry-run preview: `edit_file(agent="...", path="file.py", old_string="old", new_string="new")`
     - Apply: `edit_file(agent="...", path="file.py", old_string="old", new_string="new", dry_run=False)`
     - Replace all: `edit_file(..., replace_all=True, dry_run=False)`
     - Full workflow: search -> read_file -> edit_file
3. ~100 lines total

**Verification:**
- [ ] File exists at `.claude/skills/scribe-mcp-usage/references/edit_file.md`
- [ ] All 7 parameters documented
- [ ] Read-before-edit enforcement clearly explained
- [ ] dry_run=True default prominently documented
- [ ] At least 4 examples including full workflow

**Out of Scope:** Do NOT modify any .codex files (that's Batch 2)

### Task Package 1.3: Update SKILL.md

**Scope:** Update `.claude/skills/scribe-mcp-usage/SKILL.md`
**Files to Modify:** 1
**Dependencies:** Task 1.1, 1.2 (new files must exist for nav links)

**Specifications:**
1. In `### Tools` section (after line 20, after `references/logging.md` entry), add:
   ```
   - `references/search.md` -- multi-file codebase search (grep/rg replacement).
   - `references/edit_file.md` -- safe file editing with read-before-edit enforcement.
   ```
2. In `## Non-negotiables` section (line 43), change:
   - FROM: `- Use `read_file` for file contents; avoid shell reads.`
   - TO: `- Use `read_file` for file contents, `search` for multi-file grep, `edit_file` for file edits; avoid shell reads/edits.`

**Verification:**
- [ ] SKILL.md Tools section lists search.md and edit_file.md
- [ ] Non-negotiables updated to include all three tools

**Out of Scope:** Do NOT modify .codex copy yet

---

## Batch 2: Skill Sync
<!-- ID: batch_2 -->

**Dependency:** Batch 1 + Batch 4 complete
**Scope:** Sync all changed/new files from `.claude/skills/` (source) OUT to `.codex/skills/` AND `~/.claude/skills/`

### Task Package 2.1: Sync Skill Files

**Scope:** Copy files from repo-local source to both sync targets
**Dependencies:** ALL of Batch 1 + Batch 4 (see note)

**IMPORTANT NOTE:** Batch 4 also modifies files in `.claude/skills/` (Operational_Contract.md, files.md, INDEX.md, quickstart.md, Scribe_Usage.md). Therefore Batch 2 sync should happen AFTER Batch 4, not after Batch 1. The ordering in this plan is logical grouping; execution order is: **Batch 0 -> Batch 1 -> Batch 4 -> Batch 2 -> Batch 3 -> Batch 5 -> Batch 6**.

**Specifications:**
1. Copy these files from `.claude/skills/scribe-mcp-usage/` to BOTH `.codex/skills/scribe-mcp-usage/` AND `~/.claude/skills/scribe-mcp-usage/`:
   - `SKILL.md`
   - `references/search.md` (new)
   - `references/edit_file.md` (new)
   - `references/INDEX.md`
   - `references/Operational_Contract.md`
   - `references/files.md`
   - `references/quickstart.md`
   - `references/Scribe_Usage.md`
2. For each file, verify content matches (SHA256 or diff)

**Verification:**
- [ ] All 8 files copied
- [ ] `diff .claude/skills/scribe-mcp-usage/SKILL.md .codex/skills/scribe-mcp-usage/SKILL.md` shows no differences
- [ ] `diff .claude/skills/scribe-mcp-usage/SKILL.md ~/.claude/skills/scribe-mcp-usage/SKILL.md` shows no differences
- [ ] New reference files exist in both .codex/skills/ and ~/.claude/skills/

**Out of Scope:** Do NOT modify source files (already done in Batch 1+4)

---

## Batch 3: Governance Docs
<!-- ID: batch_3 -->

**Dependency:** Batch 1 (tool signatures defined)
**Scope:** Update 4 governance documents in the repo

### Task Package 3.1: Update `docs/Scribe_Usage.md`

**Scope:** Add full tool reference sections for search and edit_file
**Files to Modify:** `docs/Scribe_Usage.md`
**Dependencies:** None (uses signatures from Architecture Guide Section 3)

**Specifications:**
1. Find the `read_file` tool section (around line 869+)
2. After it, add `## search` section containing:
   - Description paragraph
   - Full parameter table (17 params, matching Architecture Guide Section 3)
   - Output modes explanation
   - 4+ usage examples
   - ~100 lines
3. After search section, add `## edit_file` section containing:
   - Description paragraph emphasizing read-before-edit enforcement
   - Full parameter table (7 params)
   - Dry-run workflow explanation
   - Error codes table
   - 4+ usage examples
   - ~80 lines

**Verification:**
- [ ] `search` section exists with all parameters
- [ ] `edit_file` section exists with all parameters
- [ ] Read-before-edit enforcement documented
- [ ] Examples are runnable

### Task Package 3.2: Update `CLAUDE.md` (scribe_mcp root)

**Scope:** Add tools to Essential Tools table and update File Policy
**Files to Modify:** `CLAUDE.md` (in scribe_mcp root)
**Dependencies:** None

**Specifications:**
1. In "Essential Tools Quick Reference" table, add rows for search and edit_file
2. In "File Reading Policy" section, expand to cover search and edit_file:
   - Add: `- ALL multi-file searches MUST use `scribe.search` (NOT grep, rg, or find)`
   - Add: `- ALL file edits SHOULD use `scribe.edit_file` (NOT sed, awk, or manual editing)`
   - Add: `- `edit_file` requires `read_file` first (enforced at tool level)`
3. In v2.2 tools section if present, add search and edit_file

**Verification:**
- [ ] Essential Tools table has search and edit_file rows
- [ ] File Policy mentions search and edit_file

### Task Package 3.3: Update `AGENTS.md`

**Scope:** Add tools to tool listing and update file policy
**Files to Modify:** `AGENTS.md`
**Dependencies:** None

**Specifications:**
1. In tool listing section, add search and edit_file entries
2. In file reading/access policy, add search and edit_file references

**Verification:**
- [ ] Tool listing includes search and edit_file
- [ ] File policy updated

### Task Package 3.4: Update `config/CLAUDE.md`

**Scope:** Add 2 lines to Tools Architecture listing
**Files to Modify:** `config/CLAUDE.md`
**Dependencies:** None

**Specifications:**
1. In Tools Architecture listing (lines 280-297), add:
   - `- search.py - Multi-file codebase search (grep/rg replacement)`
   - `- edit_file.py - Safe file editing with exact string replacement`

**Verification:**
- [ ] Both tool files listed in Tools Architecture

---

## Batch 4: Codex Skill References
<!-- ID: batch_4 -->

**Dependency:** Batch 1 (skill source updated)
**Scope:** Update 5 reference files in `.claude/skills/scribe-mcp-usage/references/`

**NOTE:** These edits happen at `.claude/skills/` (repo-local source). Sync to `.codex/` and `~/.claude/` happens in Batch 2.

### Task Package 4.1: Update `references/Operational_Contract.md`

**Scope:** Add tool schemas for search and edit_file
**Files to Modify:** `.claude/skills/scribe-mcp-usage/references/Operational_Contract.md`
**Dependencies:** None

**Specifications:**
1. Find existing tool schema section
2. Add search tool schema (params, description, output modes)
3. Add edit_file tool schema (params, description, safety features)
4. Update file reading rules to include search and edit_file

**Verification:**
- [ ] search schema present with all params
- [ ] edit_file schema present with all params

### Task Package 4.2: Update `references/files.md`

**Scope:** Expand from read_file-only to full file operations
**Files to Modify:** `.claude/skills/scribe-mcp-usage/references/files.md`
**Dependencies:** None

**Specifications:**
1. Change title from `# File Reading (read_file)` to `# File Operations (read_file, search, edit_file)`
2. After existing read_file content, add:
   - `### search` section with param table and examples
   - `### edit_file` section with param table, enforcement rules, examples
3. Add "Workflow" section showing search -> read -> edit pipeline

**Verification:**
- [ ] Title updated to "File Operations"
- [ ] search section with params and examples
- [ ] edit_file section with read-before-edit enforcement
- [ ] Workflow section

### Task Package 4.3: Update `references/INDEX.md`

**Scope:** Add 2 index entries
**Files to Modify:** `.claude/skills/scribe-mcp-usage/references/INDEX.md`

**Specifications:**
Add entries:
```
- `search.md` -- multi-file codebase search
- `edit_file.md` -- safe file editing
```

### Task Package 4.4: Update `references/quickstart.md`

**Scope:** Add brief tool mention
**Files to Modify:** `.claude/skills/scribe-mcp-usage/references/quickstart.md`

**Specifications:**
Add brief mention of search and edit_file in any tool overview section (~3 lines).

### Task Package 4.5: Update `references/Scribe_Usage.md`

**Scope:** Mirror docs/Scribe_Usage.md additions
**Files to Modify:** `.claude/skills/scribe-mcp-usage/references/Scribe_Usage.md`

**Specifications:**
Add the same search and edit_file sections as Task 3.1 (mirror content).

---

## Batch 5: Agent Files
<!-- ID: batch_5 -->

**Dependency:** Batch 3 (governance patterns established)
**Scope:** Update 10 agent definition files (5 source + 5 mirrors)

### Task Package 5.1: Update `.claude/agents/` files

**Scope:** Update 5 agent files
**Files to Modify:**
- `.claude/agents/scribe-research-analyst.md`
- `.claude/agents/scribe-coder.md`
- `.claude/agents/scribe-architect.md`
- `.claude/agents/scribe-review-agent.md`
- `.claude/agents/scribe-bug-hunter.md`

**Specifications:**
For EACH file:
1. Find "File Reading Policy" section
2. After existing read_file line, add:
   ```
   - **For multi-file search:** MUST use `scribe.search` (NOT grep, rg, find, or bash search commands)
   - **For file editing:** SHOULD use `scribe.edit_file` (NOT sed, awk, or manual editing). Requires `read_file` first (tool-enforced).
   ```
3. Find tool usage table (if present), add:
   ```
   | `search` | Multi-file codebase search | grep/rg replacement |
   | `edit_file` | Safe file editing | Requires read_file first |
   ```

**Verification:**
- [ ] All 5 files updated with search/edit_file in File Reading Policy
- [ ] Tool tables updated where they exist

### Task Package 5.2: Mirror to `docs/claude_code_subagents/`

**Scope:** Copy updated agent files to mirror location
**Files to Modify:**
- `docs/claude_code_subagents/scribe-research-analyst.md`
- `docs/claude_code_subagents/scribe-coder.md`
- `docs/claude_code_subagents/scribe-architect.md`
- `docs/claude_code_subagents/scribe-review-agent.md`
- `docs/claude_code_subagents/scribe-bug-hunter.md`

**Specifications:**
Apply identical changes as Task 5.1 to each mirror file.

**Verification:**
- [ ] All 5 mirror files match their .claude/agents/ counterparts for the updated sections

---

## Batch 6: Minor Updates
<!-- ID: batch_6 -->

**Dependency:** Batch 3 (content patterns established)
**Scope:** 2 minor files

### Task Package 6.1: Update `README.md`

**Scope:** Add feature sections for search and edit_file
**Files to Modify:** `README.md`

**Specifications:**
1. Find existing read_file features section
2. Add search tool feature section (~30 lines): description, key features, example
3. Add edit_file tool feature section (~30 lines): description, safety features, example

### Task Package 6.2: Update `docs/whitepapers/scribe_mcp_whitepaper.md`

**Scope:** Add edit_file to directory tree and tool suite
**Files to Modify:** `docs/whitepapers/scribe_mcp_whitepaper.md`

**Specifications:**
1. Add `edit_file.py` to directory tree listing (line ~135)
2. Add edit_file description to tool suite section (after search.py entry at line ~607)

---

## Execution Order (CRITICAL)
<!-- ID: execution_order -->

Due to the sync chain dependency, the correct execution order is:

```
Batch 0 (RECOVERY: copy .codex/skills/ -> .claude/skills/ to recreate deleted source)
  |
  v
Batch 1 (skill source: new files + SKILL.md update at .claude/skills/)
  |
  v
Batch 4 (skill references: Operational_Contract, files.md, INDEX, quickstart, Scribe_Usage at .claude/skills/)
  |
  v
Batch 2 (sync: copy .claude/skills/ -> .codex/skills/ AND ~/.claude/skills/)
  |
  v
Batch 3 (governance: docs/Scribe_Usage.md, CLAUDE.md, AGENTS.md, config/CLAUDE.md)
  |
  v
Batch 5 (agents: .claude/agents/ + docs/claude_code_subagents/)
  |
  v
Batch 6 (minor: README, whitepaper)
```

Batches 3, 5, 6 could run in parallel after Batch 2 completes. The critical path is: 0 -> 1 -> 4 -> 2.
