# Scribe MCP Onboarding Prompt

**Purpose:** Copy this prompt into any project's CLAUDE.md, agent files, or system prompt to onboard agents to the Scribe MCP toolset. It covers the protocol pipeline, every tool and when to use it, managed document workflows, file operations policy, and hook enforcement.

---

## The Prompt

Paste everything below this line into your project's agent configuration:

---

# Scribe MCP Protocol & Tool Contract

You are operating in a codebase that uses **Scribe MCP** for documentation governance, audit logging, and file operations. Every significant action must be logged, every document must be created through managed tools, and every file operation must use Scribe tools instead of shell commands.

---

## The Protocol Pipeline

All non-trivial work follows a 5-stage pipeline:

```
1. Research → 2. Architect → 3. Review → 4. Code → 5. Review
```

| Stage | Agent | Produces | Quality Gate |
|-------|-------|----------|-------------|
| 1 | Research Agent | `RESEARCH_*.md` documents | Confidence scores on findings |
| 2 | Architect Agent | `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md` | Review Agent >= 93% |
| 3 | Review Agent | Pre-implementation feasibility review | Pass/fail with grade |
| 4 | Coder Agent | Working code, tests | Tests pass, code matches specs |
| 5 | Review Agent | Post-implementation review, agent grading | >= 93% to ship |

**Auxiliary:** Bug Hunter Agent for hard-to-solve bugs.

---

## Commandments (Non-Negotiable)

1. **Progress Log First (Commandment #0):** Before ANY work, call `read_recent(agent="YourName", limit=10)` to understand current state. Never work blind.

2. **Log Everything (Commandment #1):** Use `append_entry` after every 2-3 significant actions. If it's not logged, it didn't happen.

3. **Reasoning Traces (Commandment #2):** Every `append_entry` must include reasoning:
   ```python
   append_entry(
       agent="YourName",
       message="What you did",
       status="info",  # info|success|warn|error|bug|plan
       meta={
           "reasoning": {
               "why": "decision point or goal",
               "what": "constraints, alternatives considered",
               "how": "methodology, steps taken"
           }
       }
   )
   ```

4. **No Replacement Files (Commandment #3):** NEVER create `*_v2`, `*_new`, `enhanced_*` files. Modify existing files directly.

5. **No TaskOutput (Commandment #6):** NEVER read raw task output files for agent results. Use `read_recent` or `query_entries` — all agent work is logged to the progress log.

---

## File Operations Policy (NON-NEGOTIABLE)

| Operation | MUST Use | NEVER Use |
|-----------|----------|-----------|
| Read file contents | `scribe.read_file` | `cat`, `head`, `tail`, native `Read` |
| Multi-file search | `scribe.search` | `grep`, `rg`, `find`, Bash search |
| Edit files | `scribe.edit_file` | `sed`, `awk`, manual editing |
| Create/edit managed docs | `scribe.manage_docs` | `Write`, `Edit`, `echo` |

**Enforcement:**
- `edit_file` requires `read_file` on the same path first — **tool-enforced**, returns `READ_BEFORE_EDIT_REQUIRED` error
- `edit_file` defaults to `dry_run=True` — must explicitly set `False` to apply
- Direct `Write`/`Edit` on `.scribe/docs/dev_plans/` paths is **blocked by a Claude Code hook** (exit code 2, tool call rejected)
- `read_file`/`search` over shell commands is **policy-enforced** (review agent checks compliance)

**Exception:** Native `Read` is acceptable ONLY if Scribe MCP is unavailable or errors irrecoverably — must state exception explicitly.

---

## Tool Reference

Every tool requires `agent: str` as first parameter for session isolation and audit trail.

### Project Management

**`set_project(agent, name, root)`** — Register/activate a project. Always call first.
- Auto-creates `.scribe/docs/dev_plans/<name>/` with PROGRESS_LOG, ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST
- Names auto-normalize: `"my-project"` → `"my_project"`

**`get_project(agent)`** — Check current project context.

**`list_projects(agent)`** — Discover existing projects.

### Logging

**`append_entry(agent, message, status, meta)`** — Primary logging tool.
- **Single mode:** `append_entry(agent="X", message="Did thing", status="success")`
- **Bulk mode:** `append_entry(agent="X", items_list=[{"message": "A", "status": "info"}, {"message": "B", "status": "success"}])`
- Status values: `info`, `success`, `warn`, `error`, `bug`, `plan`
- Priority: `critical`, `high`, `medium`, `low`
- Category: `decision`, `investigation`, `bug`, `implementation`, `test`, `milestone`

**`read_recent(agent, limit=10)`** — Read last N log entries. Use at session start (Commandment #0).

**`query_entries(agent, message="search_term")`** — Search log history.
- `search_scope="project"` (default), `"global"`, `"all_projects"`
- `message_mode="substring"` (default), `"regex"`, `"exact"`

### File Operations

**`read_file(agent, path, mode="scan_only")`** — Read files with audit trail and structure extraction.

| Mode | Purpose | Key Params |
|------|---------|------------|
| `scan_only` | File metadata + AST structure (classes, functions, signatures) | `structure_filter` (regex), `structure_page`, `structure_page_size` |
| `chunk` | Read ~200-line chunks | `chunk_index=[0]` or `[0,1,2]` |
| `page` | Read page-by-page | `page_number=1`, `page_size=50` |
| `line_range` | Read specific lines | `start_line=10`, `end_line=50` |
| `search` | Regex search within file | `query="pattern"`, `context_lines=3` |

Advanced features:
- `include_dependencies=True` — import analysis and dependency graph
- `include_impact=True` — blast radius analysis (requires `include_dependencies`)
- `structure_filter="ClassName"` — regex filter for AST items in scan_only mode
- `structure_page`/`structure_page_size` — paginate large class/module structures

**`search(agent, pattern)`** — Multi-file codebase search (replaces grep/rg).
- `type="py"` — filter by file type (py, js, ts, rust, go, java, etc.)
- `glob="src/**/*.ts"` — filter by glob pattern
- `output_mode="content"` (default), `"files_with_matches"`, `"count"`
- `context_lines=3` — lines of context around matches
- `case_insensitive=True`, `multiline=True`, `regex=True` (default)
- Safety limits: `max_matches_per_file=50`, `max_total_matches=200`, `max_files=100`

**`edit_file(agent, path, old_string, new_string)`** — Safe file editing (replaces sed).
- `dry_run=True` (DEFAULT) — preview diff, must set `False` to apply
- `replace_all=False` (default) — set `True` to replace all occurrences
- Requires `read_file` on same path first (tool-enforced)
- Creates backup in `.scribe/backups/` before writing
- Error codes: `READ_BEFORE_EDIT_REQUIRED`, `STRING_NOT_FOUND`, `STRING_NOT_UNIQUE`, `SANDBOX_VIOLATION`, `SESSION_REQUIRED`, `WRITE_FAILED`

**Recommended workflow:**
```python
# 1. Find files
search(agent="CoderAgent", pattern="def old_function")

# 2. Read file (REQUIRED before edit)
read_file(agent="CoderAgent", path="src/module.py", mode="search", query="old_function")

# 3. Preview edit (dry_run=True is default)
edit_file(agent="CoderAgent", path="src/module.py",
    old_string="def old_function():", new_string="def new_function():")

# 4. Apply edit
edit_file(agent="CoderAgent", path="src/module.py",
    old_string="def old_function():", new_string="def new_function():",
    dry_run=False)
```

### Document Management (CRITICAL)

**`manage_docs(agent, action, ...)`** — The ONLY way to create/edit managed documents.

Managed documents live under `.scribe/docs/dev_plans/<project>/` and have YAML frontmatter, section IDs, and versioning metadata. Direct Write/Edit on these paths is **blocked by hook**. You MUST use `manage_docs`.

#### Creating Documents

```python
# Research document
manage_docs(agent="ResearchAgent", action="create",
    doc_name="RESEARCH_AUTH_FLOW_20260129",
    metadata={"doc_type": "research", "research_goal": "Analyze auth flow"})

# Bug report (doc_name auto-generated)
manage_docs(agent="BugHunter", action="create",
    metadata={"doc_type": "bug", "category": "logic", "slug": "null_ref",
              "severity": "high", "title": "Null reference in handler"})

# Custom document
manage_docs(agent="Architect", action="create",
    doc_name="COORDINATION_PROTOCOL",
    metadata={"doc_type": "custom", "body": "# Protocol\n\nContent here..."})

# Review report
manage_docs(agent="ReviewAgent", action="create",
    doc_name="REVIEW_PHASE1",
    metadata={"doc_type": "review", "stage": "post_implementation"})
```

Available `doc_type` values: `research`, `bug`, `custom`, `review`, `agent_card`

Doc-type/create routing contract:
- For `create`, pass `metadata.doc_type` as the only operator-facing selector.
- Config routing lives in `.scribe/config/scribe.yaml` under `doc_types.create_aliases` and `doc_types.create_templates`.
- Built-ins are reserved; invalid/missing template config fails closed.
- Create responses include: `requested_doc_type`, `resolved_doc_type`, `resolved_handler`, `config_source`.

#### Editing Documents

```python
# Replace a section by anchor ID (<!-- ID:section_id -->)
manage_docs(agent="Architect", action="replace_section",
    doc_name="architecture", section="problem_statement",
    content="## Problem Statement\nNew content...")

# Replace by line range
manage_docs(agent="Architect", action="replace_range",
    doc_name="phase_plan", start_line=45, end_line=50,
    content="New content for these lines")

# Find and replace text
manage_docs(agent="Coder", action="replace_text",
    doc_name="architecture",
    metadata={"find": "old_term", "replace": "new_term", "replace_all": True})

# Append content to a section
manage_docs(agent="Research", action="append",
    doc_name="architecture", section="constraints",
    content="- New constraint", metadata={"position": "inside"})

# Apply structured patch
manage_docs(agent="Coder", action="apply_patch",
    doc_name="architecture",
    edit={"find": "old text", "replace": "new text"},
    patch_mode="structured")

# Update checklist item
manage_docs(agent="Coder", action="status_update",
    doc_name="checklist", section="phase_1_task_1",
    metadata={"status": "done", "proof": "All tests passing"})

# Update narrative document frontmatter (NOT checklist)
manage_docs(agent="Coder", action="frontmatter_update",
    doc_name="RESEARCH_AUTH_FLOW_20260129",
    metadata={"frontmatter": {"status": "ready_for_review"}})

# Intent mismatch example:
# status_update on narrative docs returns DOC_STATUS_INTENT_MISMATCH
# and directs you to frontmatter_update / metadata.frontmatter.
```

#### Quality and readiness checks

- Scaffold residue means "not done"; readiness can be blocked with `DOC_NOT_DONE_SCAFFOLD_QUALITY`.
- Run `manage_docs(action="quality_check", ...)` before handoff for deterministic no-regex proof UX.
- Configured log surfaces, including custom `.scribe/config/scribe.yaml` `logs:` entries, are excluded from readiness-quality aggregation. Do not clean log timestamps as scaffold residue.
- Warning codes you must treat as authoritative:
  - `SCF_PLACEHOLDER_BRACKET`
  - `SCF_TEMPLATE_PROSE`
  - `SCF_EMPTY_FINDING`
  - `SCF_UNFILLED_APPENDIX`
  - `SCF_TODO_ONLY_SECTION`
  - `SCF_LOG_TEMPLATE_ONLY`
  - `SCF_FRONTMATTER_MISMATCH`
  - `SCF_INDEX_STALE`
  - `SCF_INDEX_MISSING`
  - `SCF_DOC_UNINDEXED`
  - `SCF_NONCANONICAL_LOCATION`

#### Canonical research path/index rules

- Keep research artifacts in canonical flat `.scribe/docs/dev_plans/<project>/research/`.
- `research/INDEX.md` is managed and refreshed by lifecycle paths.
- Noncanonical locations and stale/orphan/unindexed index states are warnings that block quality completion.

#### Tool friction reporting

If Scribe tools, search, manage_docs, or generation surfaces are awkward/unavailable, report that friction in Scribe logs (or your active audit trail) before handoff.

#### Querying Documents

```python
# List section IDs in a document
manage_docs(agent="X", action="list_sections", doc_name="architecture")

# List checklist items
manage_docs(agent="X", action="list_checklist_items", doc_name="checklist")

# Search across documents
manage_docs(agent="X", action="search",
    metadata={"query": "authentication", "search_mode": "exact"})

# Batch operations (sequential, fail-fast)
manage_docs(agent="X", action="batch", metadata={"operations": [
    {"agent": "X", "action": "replace_section", "doc_name": "architecture",
     "section": "overview", "content": "Updated overview"},
    {"agent": "X", "action": "status_update", "doc_name": "checklist",
     "section": "task_1", "metadata": {"status": "done"}}
]})
```

#### Why manage_docs Is Required

- **Atomic updates:** Section-level precision prevents accidental overwrites
- **Audit trail:** Every edit logged with agent, timestamp, and diff
- **Frontmatter preservation:** Managed docs have YAML headers that hand-editing corrupts
- **Index auto-update:** Research docs auto-register in INDEX.md
- **Hook enforcement:** Direct Write/Edit on `.scribe/docs/dev_plans/` is blocked at the tool level

### Bug & Security Tools

**`open_bug(agent, title, symptoms, category)`** — Open a bug case (BUG-YYYY-MM-DD-N ID).

**`open_security(agent, title, symptoms, category)`** — Open a security case (SEC-YYYY-MM-DD-N ID).

**`link_fix(agent, case_id, execution_id, artifact_ref, landing_status)`** — Link a fix to a bug/security case. `landing_status`: `merged`, `landed`, `done`, `proposed`.

Accepted `execution_id` reference forms (for `link_fix`):
- current execution id
- parent execution id
- authoritative session key
- in-scope Scribe entry id (32-hex) that exists in storage for the active project

Not accepted:
- transport or process session identifiers
- arbitrary 32-hex tokens that are not proven in-scope Scribe entry ids

Fast recovery when `execution_id` is rejected:
- retry with the current execution id
- or retry with the parent execution id
- or retry with the active authoritative session key
- or retry with a real in-scope Scribe entry id from the active project

### Frontmatter Mutation Contract

Preserve-first defaults:
- Empty/null/blank-style incoming values do not overwrite existing non-empty frontmatter values.
- Body-only edit actions do not create frontmatter unless you explicitly opt in.

Explicit deletion and replacement:
- Use `metadata.frontmatter_delete` only for non-reserved keys.
- Reserved/runtime-owned keys are protected and cannot be deleted by caller input.
- `frontmatter_mode=\"replace_explicit\"` is structural replacement for allowed fields; it is not a bypass for reserved/runtime-owned keys.

Runtime-owned attribution:
- `created_by`, `maintained_by`, and `edit_trace` are tool/runtime-authored.
- Caller-supplied values for runtime-owned attribution fields are ignored in favor of runtime resolution.

Frontmatter creation behavior:
- `create` writes governed frontmatter by default.
- `frontmatter_update` may create frontmatter when metadata intent is explicit.
- Body-only actions (`replace_section`, `append`, `replace_text`, `replace_range`, `apply_patch`) default to no frontmatter creation unless opted in.

### Focused Validation Bundle

Run this focused bundle for the ID/frontmatter/case workflow:

```bash
uv run pytest -q tests/test_frontmatter.py tests/test_manage_docs_frontmatter_contract.py
uv run pytest -q tests/test_sentinel_tools.py tests/test_case_registry_ownership.py
uv run pytest -q tests/test_case_registry_storage.py tests/storage/test_entry_lookup_scope.py
uv run pytest -q tests/shared/test_reference_resolution.py
git diff --check
```

### Diagnostics

**`scribe_doctor(agent)`** — Runtime diagnostics (DB status, config, project state).

---

## Session Lifecycle

Every agent session follows this pattern:

```
1. set_project(agent="...", name="...", root="...")    # Activate project
2. read_recent(agent="...", limit=10)                  # Rehydrate context
3. append_entry(agent="...", message="Starting...", status="info")  # Log intent
4. [Do work using read_file, search, edit_file, manage_docs]
5. append_entry(agent="...", message="Result...", status="success") # Log results
6. [Repeat 4-5 as needed, logging every 2-3 actions]
7. append_entry(agent="...", message="Complete", status="success")  # Final log
```

---

## Hook Enforcement Setup

To protect managed docs from direct Write/Edit, install the Scribe protection hook:

### 1. Install the hook script (once per machine)

```bash
mkdir -p ~/.claude/hooks
cat > ~/.claude/hooks/protect-managed-docs.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
hook_input=$(cat)
file_path=$(echo "$hook_input" | jq -r '.tool_input.file_path // .tool_input.filePath // ""')
tool_name=$(echo "$hook_input" | jq -r '.tool_name // ""')
if [[ -z "$file_path" ]]; then exit 0; fi
if [[ "$file_path" != /* ]]; then
    cwd=$(echo "$hook_input" | jq -r '.cwd // ""')
    if [[ -n "$cwd" ]]; then file_path="$cwd/$file_path"; fi
fi
if [[ "$file_path" == *".scribe/docs/dev_plans/"* ]]; then
    echo "BLOCKED: $tool_name on managed doc path: $file_path" >&2
    echo "Use manage_docs() instead. Direct Write/Edit is FORBIDDEN." >&2
    exit 2
fi
exit 0
SCRIPT
chmod +x ~/.claude/hooks/protect-managed-docs.sh
```

Requires `jq` (`sudo apt install jq` or `brew install jq`).

### 2. Add to each project's `.claude/settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/protect-managed-docs.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 3. Restart Claude Code

Hooks load on session start. Restart after adding the settings.

---

## Quick Reference Card

| I need to... | Use this tool |
|-------------|---------------|
| Start a session | `set_project` → `read_recent` → `append_entry` |
| Read a file | `read_file(mode="scan_only")` for structure, `"chunk"` for content |
| Find something across files | `search(pattern="...", type="py")` |
| Edit a file | `read_file` first, then `edit_file(dry_run=False)` |
| Create a research doc | `manage_docs(action="create", metadata={"doc_type": "research"})` |
| Update architecture | `manage_docs(action="replace_section", section="...")` |
| Check off a task | `manage_docs(action="status_update", metadata={"status": "done"})` |
| Log what I did | `append_entry(message="...", status="success")` |
| Search my logs | `query_entries(message="search term")` |
| File a bug | `open_bug(title="...", symptoms="...", category="...")` |
