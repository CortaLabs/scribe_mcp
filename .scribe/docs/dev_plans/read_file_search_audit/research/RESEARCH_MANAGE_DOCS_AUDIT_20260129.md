# manage_docs Tool Audit

**Date:** 2026-01-29
**Researcher:** ResearchAgent-ManageDocs
**Source:** `tools/manage_docs.py` (3,404 lines, 129KB)
**Confidence:** 1.0 (all findings verified from source code)

---

## Executive Summary

The `manage_docs` tool is the primary interface for creating and editing managed documents in Scribe MCP projects. It exposes 19 total actions across 3 tiers: 7 primary, 5 deprecated aliases, and 7 hidden actions. All actions route through a single async function (`manage_docs` at line 1118) with parameter healing, deprecation routing, and auto-registration.

---

## 1. Function Signature (line 1118-1136)

```python
async def manage_docs(
    agent: str,                              # Agent identifier (REQUIRED)
    action: str,                             # Action to perform (REQUIRED)
    doc_category: str = "",                  # Document category hint
    section: Optional[str] = None,           # Section anchor ID
    content: Optional[str] = None,           # Content to write/replace
    patch: Optional[str] = None,             # Unified diff patch text
    patch_source_hash: Optional[str] = None, # SHA256 of source used for patch
    edit: Optional[Dict | str] = None,       # Structured edit payload (or JSON string)
    patch_mode: Optional[str] = None,        # "structured" or "unified"
    start_line: Optional[int] = None,        # Start line (1-based) for replace_range
    end_line: Optional[int] = None,          # End line (1-based) for replace_range
    template: Optional[str] = None,          # Template fragment name
    metadata: Optional[Dict] = None,         # Action-specific metadata
    dry_run: bool = False,                   # Preview without writing
    doc_name: Optional[str] = None,          # Document identifier/key
    target_dir: Optional[str] = None,        # Custom output directory
    project: Optional[str] = None,           # Cross-project override
) -> Dict[str, Any]
```

### Global Optional Parameters (apply to all actions)

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `agent` | str | REQUIRED | Agent identity for audit trail |
| `action` | str | REQUIRED | Which action to execute |
| `project` | str | None | Cross-project override (auto-normalized) |
| `dry_run` | bool | False | Preview changes without applying |
| `doc_name` | str | None | Document identifier (required for most actions) |
| `metadata` | dict | None | Action-specific options |

---

## 2. Action Registry (lines 53-87)

### 2.1 PRIMARY ACTIONS (7)

#### `create`
**Purpose:** Unified document creation with doc_type routing.
**Required:** `doc_name` (except bug), `metadata.doc_type`
**Optional:** `content` (overrides template), `target_dir`, `metadata.*`
**Routing (line 1377-1448):** Dispatches based on `metadata.doc_type`:

| doc_type | Handler | Required metadata | Output path |
|----------|---------|-------------------|-------------|
| `custom` (default) | create_doc handler | `body` (content) | Resolved via `_resolve_create_doc_path` |
| `research` | `_handle_special_document_creation` | (none extra) | `{docs_dir}/research/{doc_name}.md` |
| `bug` | `_handle_special_document_creation` | `category` (required), `slug` (optional) | `{root}/docs/bugs/{category}/{date}_{slug}/report.md` |
| `review` | `_handle_special_document_creation` | `stage` (optional, default "unknown") | `{docs_dir}/REVIEW_REPORT_{stage}_{date}_{time}.md` |
| `agent_card` | `_handle_special_document_creation` | `agent_name`, `stage` (optional) | `{docs_dir}/AGENT_REPORT_CARD_{agent}_{stage}_{datetime}.md` |

**Example calls:**
```python
# Research doc
manage_docs(agent="R", action="create", doc_name="RESEARCH_AUTH_20260129",
            metadata={"doc_type": "research", "research_goal": "Analyze auth"})

# Bug report (doc_name auto-generated from slug)
manage_docs(agent="R", action="create",
            metadata={"doc_type": "bug", "category": "logic", "slug": "null_ref",
                       "severity": "high", "title": "Null reference in handler"})

# Custom doc (body required)
manage_docs(agent="R", action="create", doc_name="COORDINATION_PROTOCOL",
            metadata={"doc_type": "custom", "body": "# Protocol\n\nContent..."})

# Review report
manage_docs(agent="R", action="create", doc_name="REVIEW_PHASE1",
            metadata={"doc_type": "review", "stage": "post_implementation"})

# Agent report card
manage_docs(agent="R", action="create", doc_name="CARD_CODER",
            metadata={"doc_type": "agent_card", "agent_name": "CoderAgent", "stage": "phase_1"})
```

#### `replace_section`
**Purpose:** Replace content at a section anchor (`<!-- ID:section_id -->`).
**Required:** `doc_name`, `section` (anchor ID), `content` or `template`
**Optional:** `metadata.scaffold` (bool, enables scaffolding mode)
**Delegates to:** `apply_doc_change()` in `doc_management/manager.py`

```python
manage_docs(agent="R", action="replace_section", doc_name="architecture",
            section="problem_statement", content="## Problem\nNew content...")
```

#### `apply_patch`
**Purpose:** Apply unified diff or structured edit to a document.
**Required:** `doc_name`, plus one of:
  - `edit` (dict or JSON string) with `patch_mode="structured"`
  - `patch` (unified diff text) with `patch_mode="unified"`
  - `content` (diff content) with `patch_mode`
**Optional:** `patch_source_hash` (SHA256 for conflict detection)

```python
# Structured patch
manage_docs(agent="R", action="apply_patch", doc_name="architecture",
            edit={"find": "old text", "replace": "new text"}, patch_mode="structured")

# Unified diff
manage_docs(agent="R", action="apply_patch", doc_name="phase_plan",
            patch="--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new",
            patch_mode="unified")
```

#### `replace_range`
**Purpose:** Replace content at specific line numbers.
**Required:** `doc_name`, `start_line` (1-based), `end_line` (1-based), `content`

```python
manage_docs(agent="R", action="replace_range", doc_name="phase_plan",
            start_line=45, end_line=50, content="New content for these lines")
```

#### `replace_text`
**Purpose:** Find and replace text patterns in a document.
**Required:** `doc_name`, `metadata.find`, `metadata.replace`
**Optional:** `metadata.replace_all` (bool, default False)

```python
manage_docs(agent="R", action="replace_text", doc_name="architecture",
            metadata={"find": "old_term", "replace": "new_term", "replace_all": True})
```

#### `append`
**Purpose:** Append content to a document or section.
**Required:** `doc_name`, `content`
**Optional:** `section` (append within section), `metadata.position` ("inside" to append within section)

```python
manage_docs(agent="R", action="append", doc_name="architecture",
            section="constraints", content="- New constraint",
            metadata={"position": "inside"})
```

#### `status_update`
**Purpose:** Update checklist item status.
**Required:** `doc_name`, `section` (section anchor ID), `metadata`
**Metadata fields:** `status` ("done"/"pending"/etc.), `proof` (evidence string)

```python
manage_docs(agent="R", action="status_update", doc_name="checklist",
            section="phase_1_task_1",
            metadata={"status": "done", "proof": "PR #123 merged"})
```

### 2.2 DEPRECATED ALIASES (5) - lines 67-73

These still work but emit deprecation warnings and route to `create`:

| Old Action | Routes To | Default metadata |
|------------|-----------|------------------|
| `create_doc` | `create` | `{"doc_type": "custom"}` |
| `create_research_doc` | `create` | `{"doc_type": "research"}` |
| `create_bug_report` | `create` | `{"doc_type": "bug"}` |
| `create_review_report` | `create` | `{"doc_type": "review"}` |
| `create_agent_report_card` | `create` | `{"doc_type": "agent_card"}` |

### 2.3 HIDDEN ACTIONS (7) - lines 76-84

#### `list_sections` (line 2222)
**Purpose:** Return all section anchors (`<!-- ID:xxx -->`) in a document.
**Required:** `doc_name`
**Optional:** `metadata.page` (default 1), `metadata.page_size` (default 50)
**Returns:** Array of `{id, line, file_line}` objects, detects duplicate anchors.

#### `list_checklist_items` (line 2337)
**Purpose:** Parse and return checklist items from a checklist document.
**Required:** `doc_name` (must be "checklist")
**Optional:** `metadata.text` (filter), `metadata.case_sensitive` (default True), `metadata.require_match` (default False), `metadata.page`/`page_size` (default 20)
**Returns:** Array of `{line, start_line, end_line, file_line, status, text, raw, section}`.

#### `search` (line 1501)
**Purpose:** Search within managed documents.
**Required:** `metadata.query` (or `metadata.search`)
**Optional:** `doc_name` (use `*` or `all` for all docs), `metadata.search_mode` ("semantic", "exact", "fuzzy")

**Semantic mode** (requires vector indexing enabled):
- `metadata.content_type`: "doc", "log", or "all" (default)
- `metadata.project_slugs`: list of project slugs to filter
- `metadata.project_slug_prefix`: prefix filter
- `metadata.doc_type`: filter by doc type
- `metadata.file_path`: filter by file path
- `metadata.time_start`/`time_end`: time range filter
- `metadata.min_similarity`: minimum similarity threshold
- `metadata.k`: total results limit

**Exact/fuzzy mode:**
- `metadata.fuzzy_threshold`: similarity threshold (default 0.8)

#### `batch` (line 2462)
**Purpose:** Execute multiple manage_docs operations sequentially.
**Required:** `metadata.operations` (list of operation dicts)
**Behavior:** Fails fast on first error. No nested batches allowed. Each operation dict is passed as kwargs to `manage_docs()`.

```python
manage_docs(agent="R", action="batch", metadata={"operations": [
    {"agent": "R", "action": "replace_section", "doc_name": "architecture",
     "section": "overview", "content": "New overview"},
    {"agent": "R", "action": "status_update", "doc_name": "checklist",
     "section": "task_1", "metadata": {"status": "done"}}
]})
```

#### `normalize_headers` (hidden)
**Purpose:** Normalize markdown headers in a document.
**Required:** `doc_name`
**Delegates to:** `apply_doc_change()`

#### `generate_toc` (hidden)
**Purpose:** Generate table of contents for a document.
**Required:** `doc_name`
**Delegates to:** `apply_doc_change()`

#### `validate_crosslinks` (hidden)
**Purpose:** Validate cross-references between documents.
**Required:** `doc_name`
**Delegates to:** `apply_doc_change()`

---

## 3. Parameter Healing (lines 117-311)

The `_heal_manage_docs_parameters` function auto-corrects common mistakes:
- **action:** Validates against VALID_ACTIONS set (no auto-correction to prevent accidental edits)
- **doc_category:** String normalization (strip whitespace)
- **section:** String normalization
- **content:** Coerced to string
- **edit:** Auto-parses JSON string to dict
- **patch_mode:** Normalized to lowercase, validated against {"structured", "unified"}
- **start_line/end_line:** Coerced to int via `_coerce_line_number`
- **metadata:** Parsed from JSON string if needed via `_normalize_metadata_with_healing`
- **dry_run:** Coerced to bool

---

## 4. Document Resolution and Registration

### Auto-registration (lines 1336-1374)
When `doc_name` is not registered in project docs for EDIT actions, the system attempts auto-registration by calling `_auto_register_document()`.

### Custom doc path resolution (lines 1272-1334)
For edit actions on custom doc types (research, bugs, reviews, agent_cards), `_resolve_custom_doc_path()` finds the document without requiring prior registration.

### create_doc with register_existing (lines 1715-1763)
Special flow: `action="create_doc"` with `metadata.register_existing=True` registers an existing file in project docs without writing content. Uses `metadata.register_as` or `doc_name` as the registry key.

---

## 5. Post-Edit Side Effects

After every successful non-dry-run edit (lines 1796-1920):
1. Records doc change in storage backend (SHA before/after)
2. Updates Project Registry metrics
3. Logs to `doc_updates` log type via `append_entry`
4. Vector-indexes the document (if enabled)
5. Updates INDEX.md files for special doc types (research, bugs, reviews, agent_cards)

---

## 6. Risks and Open Questions

1. **Direct SQL in list_sections** (line 2254): `_handle_list_sections` uses `storage._execute()` directly for auto-registration, violating the StorageBackend API rule. This is a known code quality issue.
2. **normalize_headers, generate_toc, validate_crosslinks**: These hidden actions are not documented in any agent file. Their exact behavior is delegated to `apply_doc_change()` in `doc_management/manager.py` -- not audited in this research.
3. **Semantic search** requires vector indexing to be enabled (`vector.json` config). Most deployments may not have this active.

---

## 7. Handoff Notes

- **For Architect:** The create action's 5 doc_type values and their distinct path patterns are critical for understanding where documents land in the filesystem.
- **For Coder:** The auto-registration and custom doc path resolution logic (lines 1272-1374) is complex and may need attention if new doc types are added.
- **For Review:** Verify that the direct SQL usage in `_handle_list_sections` (line 2254) is tracked as technical debt.
