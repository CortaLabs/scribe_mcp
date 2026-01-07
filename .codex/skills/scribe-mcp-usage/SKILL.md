---
name: scribe-mcp-usage
description: Operate the local Scribe MCP for any /home/carlos/projects/* repo; use when registering the server, setting projects, drafting ARCH/PHASE/CHECKLIST via manage_docs, or logging work with append_entry/get_project safeguards.
---
## Required Reading

- Codex: read and follow `AGENTS.md`.
- Claude Code: read and follow `CLAUDE.md`.

- If confused on how to use any Scribe tools, do targeted searches of `scribe_usage.md` using the `scribe.read_file` tool

This skill is the minimal, enforceable tool-and-logging contract. Deeper rationale belongs in wiki or code.

## Core Rules (Brief, Enforced)

- MCP tools are mandatory: if a tool exists, call it directly via MCP; do not script substitutes.
- Log intent only after the tool succeeds or fails.
- Confirmation flags (e.g., `confirm`, `dry_run`) must be passed as actual tool parameters.
- All file reads must use `read_file` (scan/search/chunk/page/line_range). Do not read file contents with `cat`/`rg`; use `rg --files` only for filename discovery.
- For parameter discovery, use `read_file` with `mode="search"` and `query="search term"` against tool docs or sources.  This mode allows regex.  Most notably: `/docs/scribe_usage.md`.  **Always keep this document updated with changes to tools or usage**
- If a tool call fails, fix the payload and retry; never fall back to shell reads for content.
- Always rehydrate context when required:
  - Project mode: `read_recent` or `query_entries` (last 5 entries minimum).
  - Cross-project/global: `query_entries` with `search_scope="global"` or `"all_projects"`.
  - You only need to rehydrate when unsure of next steps, on a fresh context window, or we need previous architectural decisions brought back.
- Logging discipline:
  - Project mode: use `append_entry` after every meaningful action (every 2-3 edits or 5 minutes). You MUST log during investigation as well.
  - Sentinel mode (only if preconfigured): use `append_event`.
- Reasoning block is mandatory in every `append_entry`:
  - `why` (goal/decision point)
  - `what` (constraints/alternatives)
  - `how` (method/uncertainty)
- New project workflow (Codex): call `set_project` (with repo root) then `manage_docs` to draft ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST before any feature code.
- Codex agent name must be `Codex`.


**What Gets Logged (Non-Negotiable):**
- 🔍 Investigation findings and analysis results
- 💻 Code changes (what was changed and why)
- ✅ Test results (pass/fail with context)
- 🐞 Bug discoveries (symptoms, root cause, fix approach)
- 📋 Planning decisions and milestone completions
- 🔧 Configuration changes and deployments
- ⚠️ Errors encountered and recovery actions
- 🎯 Task completions and progress updates


## Readable vs Structured Modes
- Readable mode is the preferred way to use Scribe Tools, however, if you need to debug or require additional information, structured mode will output the entire payload.   This can be token heavy!

## Sentinel vs Project Mode

- Project mode: call `set_project` and use `append_entry`, `manage_docs`, `read_recent`, `query_entries`.
- If you are unsure which project is active, call `list_projects` first, then `set_project` to create/switch.
- Sentinel mode is not switchable once a project is set in this session. If sentinel is preconfigured, use `append_event`, `open_bug`, `open_security`, `link_fix` for repo-wide issues.



## Tool Signatures (Authoritative)

All MCP tool calls and parameters must match these signatures.

### Core Project Tools

```
append_entry(
  message="",
  status=None,
  emoji=None,
  agent=None,
  meta=None,
  timestamp_utc=None,
  items=None,
  items_list=None,
  auto_split=True,
  split_delimiter="\n",
  stagger_seconds=1,
  agent_id=None,
  log_type="progress",
  priority=None,
  category=None,
  tags=None,
  confidence=None,
  config=None,
  format="readable"
)

set_project(
  name,
  root=None,
  progress_log=None,
  defaults=None,
  author=None,
  overwrite_docs=False,
  agent_id=None,
  expected_version=None,
  description=None,
  tags=None,
  template=None,
  auto_create_dirs=True,
  skip_validation=False,
  reminder_settings=None,
  notification_config=None,
  reset_reminders=False,
  emoji=None,
  project_agent=None,
  format="readable"
)

get_project(project=None, format="structured")

manage_docs(
  action,
  doc,
  section=None,
  content=None,
  patch=None,
  patch_source_hash=None,
  edit=None,
  patch_mode=None,
  start_line=None,
  end_line=None,
  template=None,
  metadata=None,
  dry_run=False,
  doc_name=None,
  target_dir=None
)

generate_doc_templates(
  project_name,
  author=None,
  overwrite=False,
  force=False,
  documents=None,
  base_dir=None,
  custom_context=None,
  legacy_fallback=False,
  include_template_metadata=False,
  validate_only=False
)

read_recent(
  project=None,
  n=None,
  limit=None,
  filter=None,
  page=1,
  page_size=10,
  compact=False,
  fields=None,
  include_metadata=True,
  format="readable",
  priority=None,
  category=None,
  min_confidence=None,
  priority_sort=False
)

query_entries(
  project=None,
  start=None,
  end=None,
  message=None,
  message_mode="substring",
  case_sensitive=False,
  emoji=None,
  status=None,
  agent=None,
  agents=None,
  meta_filters=None,
  limit=50,
  page=1,
  page_size=10,
  compact=False,
  fields=None,
  include_metadata=True,
  search_scope="project",
  document_types=None,
  include_outdated=True,
  verify_code_references=False,
  time_range=None,
  relevance_threshold=0.0,
  max_results=None,
  config=None,
  format="readable",
  priority=None,
  category=None,
  min_confidence=None,
  priority_sort=False
)

read_file(
  path,
  mode="scan_only",
  chunk_index=None,
  start_chunk=None,
  max_chunks=None,
  start_line=None,
  end_line=None,
  page_number=None,
  page_size=None,
  search=None,
  query=None,
  search_mode="regex",
  case_insensitive=None,
  context_lines=0,
  max_matches=None,
  fuzzy_threshold=None,
  include_dependencies=False,
  structure_filter=None,
  structure_page=1,
  structure_page_size=10,
  format="readable"
)

list_projects(
  limit=5,
  filter=None,
  compact=False,
  fields=None,
  include_test=False,
  page=1,
  page_size=None,
  status=None,
  tags=None,
  order_by=None,
  direction="desc",
  format="structured"
)

rotate_log(
  project=None,
  suffix=None,
  custom_metadata=None,
  confirm=None,
  dry_run=None,
  dry_run_mode=None,
  log_type=None,
  log_types=None,
  rotate_all=None,
  auto_threshold=None,
  threshold_entries=None,
  config=None
)

delete_project(
  name,
  mode="archive",
  confirm=False,
  force=False,
  archive_path=None,
  agent_id=None
)

health_check()

scribe_doctor()
```

### Sentinel Tools (Sentinel Mode Only)

```
append_event(
  message=None,
  status=None,
  emoji=None,
  agent=None,
  meta=None,
  timestamp_utc=None,
  items=None,
  items_list=None,
  auto_split=True,
  split_delimiter="\n",
  stagger_seconds=1,
  event_type=None,
  data=None
)

open_bug(title, symptoms, affected_paths=None)

open_security(title, symptoms, affected_paths=None)

link_fix(case_id, execution_id, artifact_ref, landing_status)
```

### Vector Tools (Registered Only When Vector Indexer Plugin Is Active)

```
vector_search(
  query,
  k=10,
  project_slug=None,
  project_slugs=None,
  project_slug_prefix=None,
  agent_name=None,
  content_type=None,
  doc_type=None,
  file_path=None,
  time_start=None,
  time_end=None,
  min_similarity=None
)

semantic_search(
  query,
  k=10,
  project_slug=None,
  project_slugs=None,
  project_slug_prefix=None,
  agent_name=None,
  time_start=None,
  time_end=None,
  min_similarity=None
)

retrieve_by_uuid(entry_id)

vector_index_status()

rebuild_vector_index()
```
---

## `manage_docs` — How to Use It (Project Mode Only)

`manage_docs` is the **only approved way** to create or change **managed project documentation** inside `.scribe/docs/dev_plans/<project>/`. Use it for dev-plan artifacts (architecture/phase/checklist) and structured reports (research/bug/review/agent card). **Do not hand-edit managed docs** unless the plan explicitly says to. If you’re in **Sentinel Mode (no active project)**, `manage_docs` is **not available**—create a project with `set_project()` first.

### What you use `manage_docs` for

* Keeping the **doc suite** consistent:

  * `ARCHITECTURE_GUIDE.md` (source of truth for design)
  * `PHASE_PLAN.md` (execution plan)
  * `CHECKLIST.md` (status + proof)
* Producing **structured artifacts**:

  * research reports
  * bug reports
  * review reports
  * agent report cards
* Performing **safe, auditable edits**:

  * section replacement, patches, line-range edits, checklists updates
  * formatting helpers (TOC, header normalization)
  * crosslink validation

### Core editing actions (your daily bread)

These actions all share the same edit backend and should be treated as “**edit this doc safely**” variants:


**Use `apply_patch` when** you need precision edits and you can produce a clean patch.

* Best for surgical changes when section markers aren’t available.
* Prefer patch over “rewrite the whole file.”
* This is the most preferred method of updating managed_docs

**Use `replace_range` when** you know the exact line span you must replace.

* Only do this after inspecting structure (see introspection below).
* Fragile if the doc changes; use sparingly.

**Use `replace_text` for** simple find/replace transforms.

* Good for consistent renames or small substitutions.
* Dangerous if your “old text” matches too broadly—be explicit.


**Use `replace_section` when** you’re updating a named section that has a stable marker like:
`<!-- ID: section_name -->`

* Example pattern: “Update the ‘Constraints’ section in ARCHITECTURE_GUIDE.”
* Preferred for maintaining long-lived docs because it avoids line drift.
* Always prefer `apply_patch` over replace_section, this tool is meant to be used only during the templating/bootstrapping of initial plan documents.  It will overwrite/duplicate content.

**Use `append` when** you’re adding a new block at the end (notes, findings, new subsection).

* Example pattern: “Append a new decision record / findings block.”
* Do *not* use append for checklist state changes (use `status_update`).

**Use `status_update` when** the change is “mark checklist items done” and attach proof.

* Example pattern: “Mark CHECKLIST item X as complete with test output reference.”
* Always include proof metadata (what verified it, where, and when).

**Use `normalize_headers` / `generate_toc` when** you want doc formatting to be standardized.

* Use after major structural edits, not constantly.

**Use `validate_crosslinks` when** the doc has internal links you might have broken.

* Run after reorganizing sections or renaming docs.

### Special document creation (templated “create_*” actions)

These are for creating structured docs that have a defined lifecycle and indexing:

* `create_research_doc` → creates a research report + updates `research/INDEX.md`
* `create_bug_report` → creates a bug report + updates `docs/bugs/INDEX.md`
* `create_review_report` → creates a review report + updates review index
* `create_agent_report_card` → creates evaluation + updates its index

**When to use these:** whenever you’re generating a **new report artifact** that should be discoverable later.
**When NOT to use these:** for routine progress logging (that’s `append_entry`) or repo-wide cases (that’s Sentinel mode case tools).

### Introspection actions (to avoid guessing)

Use these to locate structure before doing precise edits:

**Use `list_sections` when** you need to know what section IDs exist and where they live.

* Pair with `replace_section` or to find anchors.

**Use `list_checklist_items` when** you want the checklist items + line numbers + status.

* Pair with `status_update` to avoid mismatches.

### Lifecycle action

**Use `create_doc` when** you need a brand new managed document registered in project state.

* This is for “new managed doc types” within a project, not random repo files.

---

## Safe usage patterns (what agents should actually do)

### Pattern A: Update an architecture section safely

1. Rehydrate: `read_recent` / `query_entries` for relevant context
2. Inspect: `manage_docs(list_sections, doc="ARCHITECTURE_GUIDE")` if unsure
3. Edit: `manage_docs(replace_section, doc="ARCHITECTURE_GUIDE", section="constraints", content=...)`
4. Verify: tests or reasoning consistency check
5. Log: `append_entry` with what changed and why

### Pattern B: Close a checklist item with proof

1. Find item: `manage_docs(list_checklist_items, doc="CHECKLIST")`
2. Run tests / verification
3. Update item: `manage_docs(status_update, doc="CHECKLIST", section=..., metadata.status="done", metadata.proof=...)`
4. Log: `append_entry` summarizing proof + link to outputs

### Pattern C: Create a bug report artifact

1. Confirm Project Mode is active
2. Create report: `manage_docs(create_bug_report, metadata.category=..., metadata.slug=..., metadata.severity=..., content=...)`
3. Log: `append_entry` with bug summary + link to report path

---

## Hard rules (to prevent freestyle)

* `manage_docs` is **Project Mode only**. No project → no doc management.
* Don’t invent action names or parameters. If an action isn’t supported: **stop and request a tool update**.  Be sure to check `Scribe_Usage.md` first.
* Prefer `replace_range` / `apply_patch` over whole-file rewrites.  `Read_File` can provide exact line numbers.
* `append_entry` is for progress logging; `manage_docs` is for managed doc artifacts. Use both when appropriate.

---

## Notes

- If a tool is unavailable (e.g., vector tools without plugin), stop and note the blocker; do not invent behaviors.
- Keep this skill minimal; link to wiki/code for extended rationale.
