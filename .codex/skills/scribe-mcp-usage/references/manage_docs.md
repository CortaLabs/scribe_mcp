# Manage Docs

### `manage_docs`
**Purpose**: Structured documentation system for projects.

**Required Parameters:**
- `action` (string): Action type (see all 17 actions below)
- `doc_name` (string): Document identifier/filename key (e.g., `architecture`, `phase_plan`, `checklist`, `implementation`)

**Important:** `doc_name` is the unique document identifier (and drives filename resolution). `doc_category` is a semantic label only and must not be used as a filename or registry key.

**All Available Actions (17 total):**

**EDIT Operations** (11 actions - auto-register documents by `doc_name` if needed):
- `list_sections` - List all section anchors in a document
- `list_checklist_items` - List all checklist items
- `replace_section` - Replace content using section anchors
- `append` - Append content to document or section
- `status_update` - Update checklist item status
- `apply_patch` - Apply structured or unified diff patches
- `replace_range` - Replace explicit line ranges
- `normalize_headers` - Normalize markdown headers to ATX format
- `generate_toc` - Generate table of contents
- `search` - Semantic search across documents
- `validate_crosslinks` - Validate cross-document references

**CREATE Operations** (6 actions - create the file and register it by default):
- `create_research_doc` - Create structured research documents
- `create_bug_report` - Create structured bug reports
- `create_review_report` - Create review reports
- `create_agent_report_card` - Create agent performance reports
- `create_doc` - Create custom documents
- `batch` - Execute multiple operations sequentially

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

#### `apply_patch`
- `edit` (dict, required): Patch specification with `type` field
  - Format: `{"type": "structured"|"unified", ...}` for structured patches
  - Or: Full patch dict for unified diffs
- `patch` (string, optional): Unified diff patch string
- `patch_source_hash` (string, optional): Source content hash for verification
- `patch_mode` (string, optional): Patch application mode

#### `replace_range`
- `start_line` (int, required): Starting line number (1-indexed)
- `end_line` (int, required): Ending line number (inclusive)
- `content` (string, required): Replacement content

#### `replace_text`
- `content` (string, required): Text pattern to replace
- `metadata` (dict, optional): Replacement configuration

#### `list_sections`
- No additional parameters required
- Returns the discovered section anchors for the requested document, including line numbers.

#### `list_checklist_items`
- No additional parameters required
- Returns all checklist items with their IDs and status

#### `batch`
- `metadata.operations` (list, required): Sequence of manage_docs payloads executed in order. Nested batches are rejected for safety.

#### `create_research_doc`
- `doc_name` (string, required): Document name (e.g., "RESEARCH_AUTH_SYSTEM_20251102")
- `metadata` (dict, required): Must include `research_goal` field
  - Example: `{"research_goal": "Analyze authentication flow", "confidence_areas": ["security", "performance"]}`

#### `create_bug_report`
- `metadata` (dict, required): Must include:
  - `category` (string): One of `infrastructure|logic|database|api|ui|misc`
  - `slug` (string): Descriptive identifier
  - `severity` (string): One of `low|medium|high|critical`
  - `title` (string): Brief bug description
  - `component` (string, optional): Affected component

#### `create_review_report`
- `metadata` (dict, required): Review report metadata

#### `create_agent_report_card`
- `metadata` (dict, required): Agent performance metadata

#### `create_doc`
- `doc_name` (string, required): Document identifier used for naming/registration
- `content` (string, required unless `metadata.body`/`metadata.snippet`/`metadata.sections` provided): Document content
- `template` (string, optional): Template name
- `metadata` (dict, optional): Document metadata (supports `register_doc` and `register_as` overrides)

#### `normalize_headers`
- No additional parameters required
- Normalizes all markdown headers to ATX format (# style)

#### `generate_toc`
- `metadata` (dict, optional): TOC generation options

#### `validate_crosslinks`
- No additional parameters required
- Validates all cross-document references

**Global Optional Parameters:**
- `metadata` (dict): Additional metadata for the operation
- `dry_run` (bool): Preview changes without applying
- `target_dir` (string): Custom target directory for CREATE operations
- Metadata payloads are auto-normalized; dicts, JSON strings, and legacy key/value sequences are all accepted.

**MCP Schema Fix (v2.2.0+):**
All parameters now properly exposed via MCP with correct JSON Schema types. Previously, parameters like `doc_name`, `edit`, `section`, and `metadata` appeared as empty schemas `{}` due to string annotations from `from __future__ import annotations`. Fixed by using `typing.get_type_hints()` to resolve annotations at runtime.

**Example Usage:**
```python
# Replace architecture section
await manage_docs(
    action="replace_section",
    doc_name="architecture",  # REQUIRED: unique doc identifier
    section="problem_statement",
    content="## Problem Statement\n**Context:** ..."
)

# Append within a section
await manage_docs(
    action="append",
    doc_name="architecture",
    section="problem_statement",
    content="Updated scope paragraph",
    metadata={"position": "inside"}
)

# Update checklist status
await manage_docs(
    action="status_update",
    doc_name="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "code_review_completed"}
)

# Create research document
await manage_docs(
    action="create_research_doc",
    doc_name="RESEARCH_AUTH_SYSTEM_20251102",  # REQUIRED for custom docs
    metadata={"research_goal": "Analyze authentication flow", "confidence_areas": ["security"]}
)

# Create bug report
await manage_docs(
    action="create_bug_report",
    metadata={
        "category": "database",
        "slug": "connection_leak",
        "severity": "high",
        "title": "Database connection pool exhaustion",
        "component": "storage/sqlite.py"
    }
)

# Apply unified patch (patch_mode defaults to "unified" when patch is provided)
await manage_docs(
    action="apply_patch",
    doc_name="architecture",
    patch="--- a/file.md\n+++ b/file.md\n@@ -10,3 +10,4 @@\n existing line\n+new line",
    dry_run=True  # Always dry_run first!
)

# Batch multiple updates (executed sequentially)
await manage_docs(
    action="batch",
    doc_name="architecture",
    metadata={
        "operations": [
            {
                "action": "append",
                "doc_name": "architecture",
                "section": "requirements_constraints",
                "content": "Documented latency targets",
                "metadata": {"position": "after"}
            },
            {
                "action": "status_update",
                "doc_name": "checklist",
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
  "doc_name": "architecture",
  "action": "replace_section",
  "path": "/path/to/document.md",
  "verification_passed": true,
  "dry_run": false
}
```

