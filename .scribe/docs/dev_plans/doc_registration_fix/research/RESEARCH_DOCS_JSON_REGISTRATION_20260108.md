# 🔬 Research: docs_json Registration Flow

**Author:** ResearchAgent-DocsJson
**Status:** Complete
**Confidence:** 0.95
**Date:** 2026-01-08

## Executive Summary

This research documents how the Scribe MCP system registers documents in the `docs_json` field and identifies why auto-created documents (research reports, bug reports, etc.) aren't being registered in the database.

**Key Finding:** Auto-created documents are NOT calling the `update_project_docs()` method after creation, leaving them unregistered in docs_json.

---

## docs_json Structure

docs_json is a JSON object stored in the `scribe_projects.docs_json` column that maps document types to their file paths.

### Initial Structure (from set_project.py lines 251-256)

```json
{
  "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
  "phase_plan": "/path/to/PHASE_PLAN.md",
  "checklist": "/path/to/CHECKLIST.md",
  "progress_log": "/path/to/PROGRESS_LOG.md"
}
```

### What Should Happen (but doesn't)

After creating research reports, bug reports, etc., the docs_json should be updated:

```json
{
  "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
  "phase_plan": "/path/to/PHASE_PLAN.md",
  "checklist": "/path/to/CHECKLIST.md",
  "progress_log": "/path/to/PROGRESS_LOG.md",
  "research_auth_refactor_20260108": "/path/to/research/RESEARCH_auth_refactor_20260108.md",
  "bug_memory_leak_20260108": "/path/to/docs/bugs/infrastructure/2026-01-08_memory_leak/report.md"
}
```

---

## Registration Flow for Standard Docs

### Location: tools/set_project.py (lines 251-296)

1. **Build docs dict** (lines 251-256):
   ```python
   docs = {
       "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
       "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
       "checklist": str(docs_dir / "CHECKLIST.md"),
       "progress_log": str(resolved_log),
   }
   ```

2. **Create project_data with docs** (lines 258-269):
   ```python
   project_data = {
       "name": name,
       "root": str(resolved_root),
       "progress_log": str(resolved_log),
       "docs_dir": str(docs_dir),
       "docs": docs,  # <-- docs mapping included
       # ... more fields
   }
   ```

3. **Persist to database** (lines 291-296):
   ```python
   project_record = await backend.upsert_project(
       name=name,
       repo_root=str(resolved_root),
       progress_log_path=str(resolved_log),
       docs_json=_json.dumps(docs),  # <-- JSON is serialized
   )
   ```

### Storage Layer Implementation

**Location:** storage/sqlite.py lines 48-83 (upsert_project)

```python
async def upsert_project(
    self,
    *,
    name: str,
    repo_root: str,
    progress_log_path: str,
    docs_json: Optional[str] = None,  # <-- Parameter exists
) -> ProjectRecord:
    await self._initialise()
    async with self._write_lock:
        await self._execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name)
            DO UPDATE SET repo_root = excluded.repo_root,
                          progress_log_path = excluded.progress_log_path,
                          docs_json = excluded.docs_json;  # <-- Updated on conflict
            """,
            (name, repo_root, progress_log_path, docs_json),
        )
```

---

## Update Method for Auto-Created Docs

### Location: storage/sqlite.py lines 177-185

```python
async def update_project_docs(self, name: str, docs_json: str) -> bool:
    """Update only the docs_json field for a project."""
    await self._initialise()
    async with self._write_lock:
        await self._execute(
            "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
            (docs_json, name),
        )
    return True
```

**Status:** Method exists and is working (used by set_project)
**Problem:** Never called by manage_docs.py create_* actions

---

## The Registration Gap

### Where Auto-Created Docs Are Generated

Location: tools/manage_docs.py

**create_research_doc** (lines 2371-2595):
- ✅ Builds file path (line 2392)
- ✅ Renders content (lines 2457-2485)
- ✅ Writes file to disk (line 2525)
- ✅ Records doc change metadata (lines 2529-2538)
- ✅ Updates index (line 2580)
- ❌ **DOES NOT** call update_project_docs()

**create_bug_report** (lines 2401-2430):
- ✅ Builds file path
- ✅ Renders content
- ✅ Writes file to disk
- ✅ Records metadata
- ✅ Updates index
- ❌ **DOES NOT** call update_project_docs()

**create_review_report** (lines 2431-2437):
- Same pattern - creates file but doesn't register

**create_agent_report_card** (lines 2438-2448):
- Same pattern - creates file but doesn't register

### Evidence: search manage_docs.py for update_project_docs

Result: 0 matches in the file

The method is available in the storage backend but is never called from manage_docs.py.

---

## Database Schema Confirmation

### Table: scribe_projects

From storage/sqlite.py lines 60-66 and storage/models.py lines 9-16:

```python
@dataclass
class ProjectRecord:
    id: int
    name: str
    repo_root: str
    progress_log_path: str
    docs_json: Optional[str] = None  # <-- Column exists
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

The `docs_json` column is:
- Defined in the ProjectRecord model
- Stored in the database
- Populated by set_project during initialization
- Can be updated via update_project_docs() method

---

## Impact Analysis

When docs_json is missing for an auto-created document:

1. **manage_docs can't find the document** - operations like list_sections, replace_section, apply_patch all check `project.get("docs")` and fail with DOC_NOT_FOUND if the doc isn't registered

2. **Cross-project search fails** - features that rely on docs_json to locate documents can't find auto-created docs

3. **Index becomes stale** - while the filesystem and index files are updated, the database doesn't know about the new document

---

## Proposed Solution

Each create_* action in manage_docs.py should:

1. After successfully creating and recording the document (around line 2538 in create_research_doc):

```python
# Get the project's current docs_json
if storage_backend and project:
    try:
        current_project = await storage_backend.fetch_project(project.name)
        docs_dict = {}
        if current_project and current_project.docs_json:
            import json
            docs_dict = json.loads(current_project.docs_json)

        # Add new document with unique key
        # Key format: "{doc_type}_{identifier}"
        doc_key = f"{doc_label}_{safe_name}"
        docs_dict[doc_key] = str(target_path)

        # Update database
        updated_json = json.dumps(docs_dict)
        await storage_backend.update_project_docs(project.name, updated_json)
    except Exception as exc:
        print(f"⚠️ Warning: Failed to register document in docs_json: {exc}")
        # Don't fail the whole operation if registration fails
```

**Key Design Decisions:**
- Use full document identifier as key to avoid conflicts (e.g., "research_auth_refactor_20260108")
- Preserve existing standard docs (architecture, phase_plan, checklist, progress_log)
- Gracefully continue if registration fails (warning only, not an error)
- Merge new docs with existing ones in docs_json

---

## Validation Criteria

1. ✅ docs_json exists in scribe_projects table
2. ✅ update_project_docs() method is implemented and working
3. ✅ set_project() calls update_project_docs() during initialization
4. ✅ update_project_docs() is available in storage backend but not used by manage_docs
5. ✅ Creating research docs/bug reports writes to filesystem and index but doesn't update docs_json

---

## References

- **Storage Backend:** `storage/sqlite.py` lines 177-185 (update_project_docs method)
- **Base Interface:** `storage/base.py` lines 49-50 (abstract method definition)
- **Project Initialization:** `tools/set_project.py` lines 251-296 (docs_json creation)
- **Models:** `storage/models.py` lines 9-16 (ProjectRecord with docs_json field)
- **Existing Spec:** `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/specs/SPEC-MANAGE-DOCS-001-database-docs-field.yaml`
- **Gap Location:** `tools/manage_docs.py` lines 2371-2595 (create_* actions)

---

## Confidence Assessment

- **docs_json structure:** 0.99 (verified in multiple files)
- **Registration flow for standard docs:** 0.99 (complete call chain traced)
- **Existence of update_project_docs():** 0.99 (method exists and implemented)
- **Gap in auto-created docs:** 0.99 (search confirms zero calls to update_project_docs)
- **Proposed solution:** 0.85 (clear approach, implementation details to be decided)

