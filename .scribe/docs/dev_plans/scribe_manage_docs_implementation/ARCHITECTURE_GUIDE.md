---
id: scribe_manage_docs_implementation-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_manage_docs_implementation"
doc_type: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-06'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# 🏗️ Architecture Guide — scribe_manage_docs_implementation
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-06 01:52:50 UTC

> Comprehensive architecture for fixing BUG-MANAGE-DOCS-001 and implementing auto-registration for manage_docs tool.

---

## Problem Statement
<!-- ID: problem_statement -->

**Bug ID:** BUG-MANAGE-DOCS-001
**Severity:** CRITICAL - Blocking 10+ of 17 manage_docs actions
**Root Cause:** Missing `docs_json` column in `scribe_projects` database table

### Current Broken State

**Infrastructure Bug:**
- The `scribe_projects` table contains only 6 columns (id, name, repo_root, progress_log_path, created_at, updated_at)
- Query at `shared/logging_utils.py:111-119` returns incomplete project data without `docs` field
- manage_docs validation check `project.get("docs")` returns `None` for all projects
- **Impact:** 10+ editing actions fail with "DOC_NOT_FOUND" errors

**User Experience Gap:**
- Agents attempting to edit documents receive cryptic errors
- Manual workaround requires calling `generate_doc_templates` before every edit operation
- No automatic document registration workflow
- Significant friction in agent workflows

**Working Actions (Only 2/17):**
- ✅ `create_research_doc` - Creates new research documents (explicit registration)
- ✅ `create_bug_report` - Creates new bug reports (explicit registration)
- ❌ All other 15 actions blocked by missing database field

### Why This Matters

**Project Context:**
This fix is blocking Phase 5.5 of the scribe_systematic_audit_1 project, which requires a fully functional manage_docs tool for wiki maintenance. Future agents depend on manage_docs for maintaining `/docs/wiki/` documentation.

**Technical Debt:**
The database schema and query logic have diverged from the expected interface. The `state.json` file contains complete project data (including docs mappings), but the database query resolves first and returns incomplete data, preventing fallback to state.json.

**Cascading Failures:**
- Agents cannot update architecture documents
- Agents cannot maintain checklists
- Agents cannot edit wiki content
- Development velocity severely impacted

### Desired End State

**Infrastructure Fixed:**
- `docs_json` column added to `scribe_projects` table (TEXT, nullable, JSON-encoded)
- Query updated to SELECT and parse `docs_json` field
- All 17 manage_docs actions functional and tested
- Existing projects backfilled with document metadata from state.json

**Auto-Registration Implemented:**
- **EDIT operations** (9 actions) auto-register unregistered files on first use
- **CREATE operations** (2 actions) remain opt-in and explicit
- Automatic detection: "Is this file registered? No → register it silently, then proceed"
- Registration events logged to progress log for auditability

**Developer Experience:**
- Agents can edit ANY file without pre-registration ceremony
- Clear, actionable error messages for genuine failures
- Comprehensive usage documentation with examples
- <100ms performance overhead for auto-registration

**Confidence:** 0.95 (high - root cause verified, solution well-understood)

---

## System Overview
<!-- ID: system_overview -->

### Current State (BROKEN)

**Database Schema:**
```sql
-- storage/sqlite.py:652-659
CREATE TABLE IF NOT EXISTS scribe_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL,
    progress_log_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    -- MISSING: docs_json TEXT
);
```

**Query Logic:**
```python
# shared/logging_utils.py:111-119
row = conn.execute(
    "SELECT name, repo_root, progress_log_path FROM scribe_projects WHERE name = ?",
    (project_name,)
).fetchone()
if row:
    session_project = {
        "name": row["name"],
        "root": row["repo_root"],
        "progress_log": row["progress_log_path"],
        # NO DOCS FIELD!
    }
```

**Fallback Never Triggers:**
```python
# shared/logging_utils.py:134-138
if not session_project:  # This is FALSE - we have a dict (even though incomplete)
    state = await server_module.state_manager.load()
    session_project = state.get_session_project(session_key_fallback)
```

### Desired State (FIXED)

**Database Schema:**
```sql
CREATE TABLE IF NOT EXISTS scribe_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL,
    progress_log_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    docs_json TEXT  -- NEW: JSON-encoded document mappings
);
```

**Query Logic:**
```python
# shared/logging_utils.py:111-119 (FIXED)
import json

row = conn.execute(
    "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
    (project_name,)
).fetchone()
if row:
    session_project = {
        "name": row["name"],
        "root": row["repo_root"],
        "progress_log": row["progress_log_path"],
    }

    # Parse and add docs field
    if row["docs_json"]:
        try:
            session_project["docs"] = json.loads(row["docs_json"])
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse docs_json for {row['name']}: {e}")
```

**Data Flow:**
```
User calls manage_docs
    ↓
Action dispatcher checks action type
    ↓
EDIT action? → Auto-registration check
    ├─ Registered? → Proceed with edit
    └─ Not registered? → Call _auto_register_document() → Proceed
    ↓
CREATE action? → Proceed without auto-registration
    ↓
Execute operation (list_sections, replace_section, etc.)
    ↓
Update docs_json in database if files changed
    ↓
Log operation to doc_updates log
```

---

## Component Design
<!-- ID: component_design -->

### 1. Database Migration (storage/sqlite.py)

**Location:** `storage/sqlite.py:652-659` (CREATE TABLE statement)

**Changes Required:**

**1a. Add docs_json Column**
```python
# Add after line 659 in CREATE TABLE statement
    docs_json TEXT,  -- JSON-encoded document metadata
```

**1b. Create Migration Function**
```python
# Add new method to SQLiteStorage class
async def migrate_add_docs_json_column(self):
    """Add docs_json column if it doesn't exist (idempotent)."""
    await self._initialise()
    async with self._write_lock:
        try:
            # Check if column exists
            cursor = await self._execute(
                "PRAGMA table_info(scribe_projects)"
            )
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'docs_json' not in column_names:
                # Add column
                await self._execute(
                    "ALTER TABLE scribe_projects ADD COLUMN docs_json TEXT"
                )
                logger.info("Added docs_json column to scribe_projects table")
                return True
            else:
                logger.info("docs_json column already exists")
                return False
        except Exception as e:
            logger.error(f"Failed to add docs_json column: {e}")
            raise
```

**1c. Backfill Function**
```python
async def backfill_docs_json_from_state(self, state_path: Path):
    """Backfill docs_json from state.json for existing projects."""
    import json

    # Load state.json
    with open(state_path, 'r') as f:
        state = json.load(f)

    projects = state.get("projects", {})
    backfilled_count = 0

    await self._initialise()
    async with self._write_lock:
        for project_name, project_data in projects.items():
            docs = project_data.get("docs")
            if not docs:
                continue

            docs_json = json.dumps(docs)
            await self._execute(
                "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
                (docs_json, project_name)
            )
            backfilled_count += 1

    logger.info(f"Backfilled {backfilled_count} projects with docs_json")
    return backfilled_count
```

**1d. Update upsert_project Method**
```python
# storage/sqlite.py:48-80 (extend signature)
async def upsert_project(
    self,
    *,
    name: str,
    repo_root: str,
    progress_log_path: str,
    docs_json: Optional[str] = None,  # NEW PARAMETER
) -> ProjectRecord:
    await self._initialise()
    async with self._write_lock:
        await self._execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name)
            DO UPDATE SET
                repo_root = excluded.repo_root,
                progress_log_path = excluded.progress_log_path,
                docs_json = excluded.docs_json,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (name, repo_root, progress_log_path, docs_json),
        )

        # Return updated record
        row = await self._fetchone(
            "SELECT * FROM scribe_projects WHERE name = ?",
            (name,)
        )
        return ProjectRecord(**row)
```

**Verification:**
```python
# Verify column exists
async def verify_migration(self):
    cursor = await self._execute("PRAGMA table_info(scribe_projects)")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]
    assert 'docs_json' in column_names, "docs_json column not found!"
    logger.info("Migration verified: docs_json column exists")
```

### 2. Query Integration (shared/logging_utils.py)

**Location:** `shared/logging_utils.py:111-119`

**Current Code (BROKEN):**
```python
row = conn.execute(
    "SELECT name, repo_root, progress_log_path FROM scribe_projects WHERE name = ?",
    (project_name,)
).fetchone()
if row:
    session_project = {
        "name": row["name"],
        "root": row["repo_root"],
        "progress_log": row["progress_log_path"],
    }
```

**Fixed Code:**
```python
import json

row = conn.execute(
    "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
    (project_name,)
).fetchone()
if row:
    session_project = {
        "name": row["name"],
        "root": row["repo_root"],
        "progress_log": row["progress_log_path"],
    }

    # Parse and add docs field
    if row["docs_json"]:
        try:
            session_project["docs"] = json.loads(row["docs_json"])
        except (json.JSONDecodeError, TypeError) as e:
            # Log error but don't fail - fallback will still work
            logger.warning(f"Failed to parse docs_json for {row['name']}: {e}")
```

**Error Handling Strategy:**
- NULL docs_json: Skip parsing, session_project has no docs field (fallback to state.json works)
- Invalid JSON: Log warning, session_project has no docs field (fallback to state.json works)
- Missing row: session_project is None (fallback to state.json works)

**Verification:**
```python
# Test query returns docs field
session_project = get_active_project(project_name="test_project")
assert "docs" in session_project, "docs field missing from query result"
assert isinstance(session_project["docs"], dict), "docs field must be dict"
logger.info("Query integration verified")
```

### 3. Auto-Registration (tools/manage_docs.py)

**Location:** `tools/manage_docs.py` (action dispatcher)

**Action Categorization:**

**EDIT Actions (9 total) - Auto-registration enabled:**
1. `list_sections` - Lists section anchors from existing files
2. `replace_section` - Updates specific sections via anchors
3. `apply_patch` - Structured edits with compiler
4. `replace_range` - Line-targeted edits
5. `append` - Add content to document end
6. `status_update` - Toggle checklist items
7. `normalize_headers` - ATX canonicalization
8. `generate_toc` - Table of contents generation
9. `search` - Semantic search across documents

**CREATE Actions (2 total) - Explicit registration only:**
1. `create_research_doc` - Creates new research documents
2. `create_bug_report` - Creates new bug reports

**Other Actions (6 total) - Context-dependent:**
3. `read_doc` - Read-only, no registration needed
4. `validate_frontmatter` - Read-only, no registration needed
5. `preview_changes` - Read-only, no registration needed
6. `list_documents` - Read-only, no registration needed
7. `get_doc_info` - Read-only, no registration needed
8. `refresh_index` - Updates existing indexes, no registration needed

**Auto-Registration Logic:**

```python
# tools/manage_docs.py (add near top of manage_docs function)

EDIT_ACTIONS = {
    "list_sections", "replace_section", "apply_patch", "replace_range",
    "append", "status_update", "normalize_headers", "generate_toc", "search"
}

async def manage_docs(action: str, doc: str = None, **kwargs):
    """Main entry point for document management operations."""

    # Auto-registration for EDIT operations
    if action in EDIT_ACTIONS and doc:
        project = await get_active_project()
        docs = project.get("docs", {})

        # Check if document is registered
        if doc not in docs:
            logger.info(f"Auto-registering unregistered document: {doc}")
            try:
                await _auto_register_document(project, doc)
                # Re-fetch project data with updated docs
                project = await get_active_project()
            except Exception as e:
                logger.error(f"Auto-registration failed for {doc}: {e}")
                raise ValueError(
                    f"Failed to auto-register document '{doc}'. "
                    f"Ensure the file exists and is readable. Error: {e}"
                )

    # Proceed with normal action dispatch
    # ... existing code ...
```

**Auto-Registration Helper Function:**

```python
async def _auto_register_document(project: dict, doc_key: str):
    """Auto-register document with project registry.

    Args:
        project: Project dict with name, root, docs
        doc_key: Document key (e.g., 'architecture', 'phase_plan')

    Raises:
        ValueError: If document file doesn't exist or can't be read
    """
    import hashlib
    import json
    from pathlib import Path

    # Infer document path from doc_key
    doc_path = _resolve_doc_path(project, doc_key)

    if not Path(doc_path).exists():
        raise ValueError(
            f"Cannot auto-register: {doc_path} does not exist. "
            f"Use 'generate_doc_templates' to create it first."
        )

    # Compute SHA256 hash
    with open(doc_path, 'rb') as f:
        doc_hash = hashlib.sha256(f.read()).hexdigest()

    # Update database with new document registration
    backend = getattr(server_module, "storage_backend", None)
    if backend and hasattr(backend, "upsert_project"):
        # Get current docs_json
        current_docs = project.get("docs", {})
        current_docs[doc_key] = str(doc_path)
        docs_json = json.dumps(current_docs)

        # Update database
        await backend.upsert_project(
            name=project["name"],
            repo_root=project["root"],
            progress_log_path=project["progress_log"],
            docs_json=docs_json,
        )

    # Also update ProjectRegistry for in-memory tracking
    registry = ProjectRegistry()
    await registry.record_doc_update(
        project_name=project["name"],
        doc_key=doc_key,
        file_path=doc_path,
        baseline_hash=doc_hash,
        current_hash=doc_hash,
    )

    # Log registration event
    await append_entry(
        message=f"Auto-registered document: {doc_key} ({doc_path})",
        status="info",
        agent="manage_docs",
        meta={
            "action": "auto_register",
            "doc": doc_key,
            "path": str(doc_path),
            "hash": doc_hash[:8],
        }
    )

    logger.info(f"Successfully registered {doc_key}: {doc_path}")


def _resolve_doc_path(project: dict, doc_key: str) -> str:
    """Resolve document path from doc_key.

    Standard mappings:
    - architecture → ARCHITECTURE_GUIDE.md
    - phase_plan → PHASE_PLAN.md
    - checklist → CHECKLIST.md
    - progress_log → PROGRESS_LOG.md
    - bug_log → BUG_LOG.md
    - doc_log → DOC_LOG.md
    - security_log → SECURITY_LOG.md
    """
    from pathlib import Path

    # Get docs directory from project root
    docs_dir = Path(project["root"]) / ".scribe" / "docs" / "dev_plans" / project["name"]

    # Standard document mappings
    DOC_FILENAMES = {
        "architecture": "ARCHITECTURE_GUIDE.md",
        "phase_plan": "PHASE_PLAN.md",
        "checklist": "CHECKLIST.md",
        "progress_log": "PROGRESS_LOG.md",
        "bug_log": "BUG_LOG.md",
        "doc_log": "DOC_LOG.md",
        "security_log": "SECURITY_LOG.md",
    }

    filename = DOC_FILENAMES.get(doc_key)
    if not filename:
        raise ValueError(f"Unknown doc_key: {doc_key}")

    return str(docs_dir / filename)
```

**Performance Considerations:**
- Auto-registration adds ~50-100ms overhead (file read + SHA256 + DB write)
- Only happens once per document per project
- Subsequent calls skip registration check (doc already in docs dict)
- Async operation doesn't block other requests

### 4. set_project Integration (tools/set_project.py)

**Location:** `tools/set_project.py` (after document generation)

**Current Behavior:**
- Creates project documents
- Registers project in state.json
- Does NOT write to database (relies on storage backend)

**Required Changes:**

```python
# tools/set_project.py (after generating docs mapping)

# Build docs mapping
docs = {
    "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
    "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
    "checklist": str(docs_dir / "CHECKLIST.md"),
    "progress_log": str(progress_log),
    "bug_log": str(docs_dir / "BUG_LOG.md"),
    "doc_log": str(docs_dir / "DOC_LOG.md"),
    "security_log": str(docs_dir / "SECURITY_LOG.md"),
}

# Serialize to JSON
docs_json = json.dumps(docs)

# Call upsert_project with docs_json
backend = getattr(server_module, "storage_backend", None)
if backend and hasattr(backend, "upsert_project"):
    await backend.upsert_project(
        name=name,
        repo_root=str(repo_root),
        progress_log_path=str(progress_log),
        docs_json=docs_json,  # NEW
    )
```

**Verification:**
```python
# After set_project completes, verify docs field exists
project = await get_active_project(project_name=name)
assert "docs" in project, "set_project failed to populate docs field"
assert project["docs"]["architecture"].endswith("ARCHITECTURE_GUIDE.md")
logger.info("set_project integration verified")
```

---

## Data Flow
<!-- ID: data_flow -->

### Flow 1: Project Creation (set_project)

```
User calls set_project(name="my_project")
    ↓
1. Generate document files (ARCHITECTURE_GUIDE.md, etc.)
    ↓
2. Build docs mapping dict
    {
        "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
        "phase_plan": "/path/to/PHASE_PLAN.md",
        ...
    }
    ↓
3. Serialize to JSON
    docs_json = '{"architecture": "/path/...", ...}'
    ↓
4. Write to database
    upsert_project(..., docs_json=docs_json)
    ↓
5. Write to state.json (existing behavior)
    ↓
6. Return success
```

### Flow 2: Document Editing (EDIT actions)

```
User calls manage_docs(action="replace_section", doc="architecture", ...)
    ↓
1. Check if action is EDIT type
    ↓
2. Get active project from database
    session_project = get_active_project()
    session_project["docs"] = json.loads(docs_json)
    ↓
3. Check if doc is registered
    if "architecture" not in session_project["docs"]:
    ↓
4. Auto-register document
    _auto_register_document(session_project, "architecture")
        - Verify file exists
        - Compute SHA256 hash
        - UPDATE scribe_projects SET docs_json = ...
        - Log registration event
    ↓
5. Re-fetch project data (now includes docs field)
    session_project = get_active_project()
    ↓
6. Proceed with edit operation
    replace_section(...) or apply_patch(...) or ...
    ↓
7. Update ProjectRegistry tracking
    record_doc_update(doc_key, baseline_hash, current_hash)
    ↓
8. Log to doc_updates log
    append_entry(log_type="doc_updates", ...)
    ↓
9. Return success
```

### Flow 3: Document Creation (CREATE actions)

```
User calls manage_docs(action="create_research_doc", doc_name="RESEARCH_TOPIC", ...)
    ↓
1. Action is CREATE type (not EDIT)
    ↓
2. Skip auto-registration check
    ↓
3. Create new file with template
    ↓
4. Explicitly register with ProjectRegistry
    record_doc_update(doc_key, baseline_hash, current_hash)
    ↓
5. Update INDEX.md if applicable
    ↓
6. Log to doc_updates log
    ↓
7. Return file path
```

### Flow 4: Database Migration (One-Time)

```
Server startup or migration script runs
    ↓
1. Check if docs_json column exists
    PRAGMA table_info(scribe_projects)
    ↓
2. If missing, add column
    ALTER TABLE scribe_projects ADD COLUMN docs_json TEXT
    ↓
3. Load state.json
    ↓
4. For each project in state.json:
    - Extract docs dict
    - Serialize to JSON
    - UPDATE scribe_projects SET docs_json = ? WHERE name = ?
    ↓
5. Verify backfill
    SELECT COUNT(*) FROM scribe_projects WHERE docs_json IS NOT NULL
    ↓
6. Log success
```

---

## API Design
<!-- ID: api_design -->

### No External API Changes

**Critical Design Principle:**
This implementation is **internal infrastructure only**. No external API changes are required. All manage_docs actions retain their existing signatures and behavior from the caller's perspective.

**What Changes:**
- Internal database schema (adds docs_json column)
- Internal query logic (adds docs field to return value)
- Internal auto-registration (silent, transparent to caller)

**What Stays the Same:**
- manage_docs function signature
- All 17 action signatures
- Return value formats
- Error types and messages
- Logging behavior

**Backward Compatibility:**
- Old projects without docs_json: Fallback to state.json still works
- Old callers: No changes required
- Old tests: All existing tests should still pass

### Internal Contract Updates

**storage.SQLiteStorage.upsert_project:**
```python
# BEFORE
async def upsert_project(
    self,
    *,
    name: str,
    repo_root: str,
    progress_log_path: str,
) -> ProjectRecord:
    ...

# AFTER (backward compatible - docs_json is optional)
async def upsert_project(
    self,
    *,
    name: str,
    repo_root: str,
    progress_log_path: str,
    docs_json: Optional[str] = None,  # NEW
) -> ProjectRecord:
    ...
```

**shared.logging_utils.get_active_project:**
```python
# BEFORE - Returns dict with 3 keys
{
    "name": "project_name",
    "root": "/path/to/repo",
    "progress_log": "/path/to/PROGRESS_LOG.md"
}

# AFTER - Returns dict with 4 keys
{
    "name": "project_name",
    "root": "/path/to/repo",
    "progress_log": "/path/to/PROGRESS_LOG.md",
    "docs": {  # NEW
        "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
        "phase_plan": "/path/to/PHASE_PLAN.md",
        ...
    }
}
```

**New Internal Functions:**
```python
# tools/manage_docs.py
async def _auto_register_document(project: dict, doc_key: str) -> None:
    """Auto-register document with project registry.

    Internal helper - not exposed to external callers.
    """
    ...

def _resolve_doc_path(project: dict, doc_key: str) -> str:
    """Resolve document path from doc_key.

    Internal helper - not exposed to external callers.
    """
    ...

# storage/sqlite.py
async def migrate_add_docs_json_column(self) -> bool:
    """Add docs_json column if it doesn't exist (idempotent).

    Internal migration - called once during deployment.
    """
    ...

async def backfill_docs_json_from_state(self, state_path: Path) -> int:
    """Backfill docs_json from state.json for existing projects.

    Internal migration - called once during deployment.
    """
    ...
```

---

## Security Considerations
<!-- ID: security_considerations -->

### 1. SQL Injection Prevention

**Risk:** Adding docs_json column and UPDATE queries could introduce SQL injection vulnerabilities

**Mitigation:**
- Use parameterized queries exclusively (never string concatenation)
- SQLite driver handles escaping automatically
- All user input (project_name, doc_key) passed as parameters

**Example (SAFE):**
```python
await self._execute(
    "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
    (docs_json, project_name)  # Parameters - safe
)
```

**Example (UNSAFE - DO NOT USE):**
```python
# NEVER DO THIS
query = f"UPDATE scribe_projects SET docs_json = '{docs_json}' WHERE name = '{project_name}'"
await self._execute(query)  # SQL injection vulnerability!
```

### 2. JSON Injection Prevention

**Risk:** Malicious JSON in docs_json could break parsing or cause unexpected behavior

**Mitigation:**
- Use json.dumps() for serialization (escapes special characters)
- Use json.loads() for deserialization (validates JSON structure)
- Wrap JSON parsing in try/except to catch malformed data
- Log errors but don't crash - fallback to state.json gracefully

**Example (SAFE):**
```python
try:
    docs = json.loads(row["docs_json"])
except (json.JSONDecodeError, TypeError) as e:
    logger.warning(f"Invalid docs_json: {e}")
    docs = {}  # Safe default
```

### 3. Path Traversal Prevention

**Risk:** Malicious doc_key or file paths could access files outside project directory

**Mitigation:**
- Validate doc_key against whitelist (DOC_FILENAMES dict)
- Resolve paths using Path().resolve() to normalize
- Check resolved path starts with project root
- Never accept arbitrary file paths from user input

**Example (SAFE):**
```python
def _resolve_doc_path(project: dict, doc_key: str) -> str:
    # Validate doc_key against whitelist
    if doc_key not in DOC_FILENAMES:
        raise ValueError(f"Invalid doc_key: {doc_key}")

    # Build path safely
    docs_dir = Path(project["root"]) / ".scribe" / "docs" / "dev_plans" / project["name"]
    filename = DOC_FILENAMES[doc_key]
    doc_path = (docs_dir / filename).resolve()

    # Verify path is within project root
    if not str(doc_path).startswith(str(docs_dir.resolve())):
        raise ValueError(f"Path traversal detected: {doc_path}")

    return str(doc_path)
```

### 4. Atomic Operations

**Risk:** Concurrent updates could corrupt docs_json or create race conditions

**Mitigation:**
- Use database transactions for all writes
- SQLiteStorage already has _write_lock for serialization
- Auto-registration + edit operation happens atomically
- If registration fails, edit operation doesn't proceed

**Example:**
```python
async with self._write_lock:
    # Auto-registration
    await _auto_register_document(project, doc_key)
    # Edit operation
    await _perform_edit(...)
    # Both succeed or both fail - no partial state
```

### 5. Migration Safety

**Risk:** Migration could corrupt existing data or fail mid-operation

**Mitigation:**
- ALTER TABLE is atomic in SQLite
- Idempotent migration (checks if column exists first)
- Backfill wrapped in transaction with rollback on error
- Migration logged with before/after verification
- Recommend database backup before migration

**Rollback Procedure:**
```sql
-- If migration fails, rollback is automatic (transaction aborts)
-- Manual rollback (if needed):
BEGIN TRANSACTION;
ALTER TABLE scribe_projects DROP COLUMN docs_json;
COMMIT;
```

### 6. Audit Trail

**Requirement:** All document registrations must be logged for security audits

**Implementation:**
- Every auto-registration logs to progress log
- Log includes: doc_key, file_path, hash, timestamp, agent
- Tamper-evident (append-only log with cryptographic verification)
- Integration with existing append_entry infrastructure

**Example Log Entry:**
```
[ℹ️] [2026-01-06 02:00:00 UTC] [Agent: manage_docs] Auto-registered document: architecture (/path/to/ARCHITECTURE_GUIDE.md) | action=auto_register; doc=architecture; path=/path/to/ARCHITECTURE_GUIDE.md; hash=a1b2c3d4
```

---

## Deployment Strategy
<!-- ID: deployment_strategy -->

### Migration Approach

**Phase 1: Pre-Deployment (Manual)**
1. **Backup database**
   ```bash
   cp .scribe/scribe.db .scribe/scribe.db.backup
   ```

2. **Verify state.json exists**
   ```bash
   test -f .scribe/state.json || echo "WARNING: state.json missing"
   ```

3. **Run migration script**
   ```python
   # scripts/migrate_add_docs_json.py
   from storage.sqlite import SQLiteStorage
   from pathlib import Path

   async def main():
       storage = SQLiteStorage(db_path=Path(".scribe/scribe.db"))

       # Add column
       await storage.migrate_add_docs_json_column()

       # Backfill from state.json
       count = await storage.backfill_docs_json_from_state(
           state_path=Path(".scribe/state.json")
       )
       print(f"Backfilled {count} projects")

       # Verify
       await storage.verify_migration()

   asyncio.run(main())
   ```

4. **Verify migration**
   ```sql
   sqlite3 .scribe/scribe.db "PRAGMA table_info(scribe_projects);"
   # Should show docs_json as column #7

   sqlite3 .scribe/scribe.db "SELECT name, LENGTH(docs_json) FROM scribe_projects;"
   # Should show non-zero length for existing projects
   ```

**Phase 2: Code Deployment**
1. Deploy updated storage/sqlite.py (with docs_json column)
2. Deploy updated shared/logging_utils.py (query includes docs_json)
3. Deploy updated tools/manage_docs.py (auto-registration logic)
4. Deploy updated tools/set_project.py (writes docs_json)

**Phase 3: Verification**
1. Test manage_docs actions on existing projects
   ```python
   # Should work without generate_doc_templates
   await manage_docs(action="list_sections", doc="architecture")
   ```

2. Create new project and verify docs_json populated
   ```python
   await set_project(name="test_project")
   project = await get_active_project(project_name="test_project")
   assert "docs" in project
   ```

3. Monitor logs for auto-registration events
   ```bash
   grep "Auto-registered" .scribe/docs/dev_plans/*/PROGRESS_LOG.md
   ```

### Rollback Plan

**If migration fails:**
```bash
# Restore backup
cp .scribe/scribe.db.backup .scribe/scribe.db

# Revert code changes
git revert <commit_sha>

# Server continues working with state.json fallback
```

**If auto-registration has issues:**
```python
# Disable auto-registration temporarily
EDIT_ACTIONS = set()  # Empty set = no auto-registration

# Agents must use generate_doc_templates as before
```

### PostgreSQL Compatibility (OUT OF SCOPE for v1.0)

**Note:** This implementation targets SQLite only. PostgreSQL support requires:
- Different migration SQL (ALTER TABLE syntax differs)
- JSON operators (json_set → jsonb_set)
- Testing with asyncpg backend

**Future Work:**
- Create separate migration for PostgreSQL
- Abstract JSON operations in storage layer
- Add integration tests for both backends

---

## Testing & Validation Strategy
<!-- ID: testing_strategy -->

### Unit Tests

**Test 1: Database Migration**
```python
async def test_migrate_add_docs_json_column():
    """Test docs_json column is added idempotently."""
    storage = SQLiteStorage(db_path=":memory:")

    # First migration should add column
    result = await storage.migrate_add_docs_json_column()
    assert result is True, "First migration should add column"

    # Second migration should detect existing column
    result = await storage.migrate_add_docs_json_column()
    assert result is False, "Second migration should skip (idempotent)"

    # Verify column exists
    await storage.verify_migration()
```

**Test 2: Backfill from state.json**
```python
async def test_backfill_docs_json_from_state():
    """Test backfill populates docs_json from state.json."""
    # Create test state.json
    state_data = {
        "projects": {
            "test_project": {
                "docs": {
                    "architecture": "/path/to/ARCHITECTURE_GUIDE.md"
                }
            }
        }
    }

    # Run backfill
    count = await storage.backfill_docs_json_from_state(state_path)
    assert count == 1, "Should backfill 1 project"

    # Verify database has docs_json
    row = await storage._fetchone(
        "SELECT docs_json FROM scribe_projects WHERE name = ?",
        ("test_project",)
    )
    docs = json.loads(row["docs_json"])
    assert "architecture" in docs
```

**Test 3: Query Returns docs Field**
```python
async def test_query_returns_docs_field():
    """Test query includes docs field after migration."""
    # Set up project with docs_json
    await storage.upsert_project(
        name="test_project",
        repo_root="/path/to/repo",
        progress_log_path="/path/to/PROGRESS_LOG.md",
        docs_json='{"architecture": "/path/to/ARCHITECTURE_GUIDE.md"}'
    )

    # Query should return docs field
    project = await get_active_project(project_name="test_project")
    assert "docs" in project, "docs field missing"
    assert project["docs"]["architecture"] == "/path/to/ARCHITECTURE_GUIDE.md"
```

**Test 4: Auto-Registration Triggers**
```python
async def test_auto_registration_on_edit():
    """Test auto-registration triggers for EDIT actions."""
    # Create project WITHOUT registering architecture doc
    await set_project(name="test_project")

    # Create file manually (simulate unregistered file)
    doc_path = Path(".scribe/docs/dev_plans/test_project/CUSTOM_DOC.md")
    doc_path.write_text("# Custom Doc")

    # Edit action should auto-register
    await manage_docs(action="list_sections", doc="custom_doc")

    # Verify registration occurred
    project = await get_active_project(project_name="test_project")
    assert "custom_doc" in project["docs"]
```

**Test 5: CREATE Actions Don't Auto-Register**
```python
async def test_create_actions_no_auto_registration():
    """Test CREATE actions remain explicit."""
    await set_project(name="test_project")

    # CREATE action should NOT auto-register
    await manage_docs(action="create_research_doc", doc_name="RESEARCH_TOPIC")

    # Verify explicit registration happened via create logic
    project = await get_active_project(project_name="test_project")
    # Research docs are registered explicitly by create_research_doc
```

### Integration Tests

**Test 6: All 17 Actions Post-Fix**
```python
async def test_all_actions_functional():
    """Test all 17 manage_docs actions work after fix."""
    await set_project(name="test_project")

    # Generate docs
    await generate_doc_templates(project_name="test_project")

    # Test EDIT actions (should work with auto-registration)
    actions_to_test = [
        ("list_sections", {"doc": "architecture"}),
        ("replace_section", {"doc": "architecture", "section": "problem_statement", "content": "New content"}),
        ("apply_patch", {"doc": "architecture", "edit": {...}}),
        ("replace_range", {"doc": "architecture", "start_line": 1, "end_line": 2, "content": "New"}),
        ("append", {"doc": "architecture", "content": "Appended content"}),
        ("status_update", {"doc": "checklist", "section": "task1", "metadata": {"status": "done"}}),
        ("normalize_headers", {"doc": "architecture"}),
        ("generate_toc", {"doc": "architecture"}),
        ("search", {"doc": "*", "metadata": {"query": "test"}}),
    ]

    for action, kwargs in actions_to_test:
        result = await manage_docs(action=action, **kwargs)
        assert result["ok"] is True, f"{action} failed: {result.get('error')}"
```

**Test 7: Edge Cases**
```python
async def test_edge_cases():
    """Test edge cases and error handling."""

    # Test 1: Missing file (should fail gracefully)
    with pytest.raises(ValueError, match="does not exist"):
        await _auto_register_document(project, "nonexistent_doc")

    # Test 2: Malformed JSON in docs_json
    await storage._execute(
        "UPDATE scribe_projects SET docs_json = 'INVALID_JSON' WHERE name = ?",
        ("test_project",)
    )
    project = await get_active_project(project_name="test_project")
    assert "docs" not in project, "Should skip malformed JSON gracefully"

    # Test 3: NULL docs_json
    await storage._execute(
        "UPDATE scribe_projects SET docs_json = NULL WHERE name = ?",
        ("test_project",)
    )
    project = await get_active_project(project_name="test_project")
    # Should work - fallback to state.json

    # Test 4: Unicode filenames
    await _auto_register_document(project, "unicode_文档")
    # Should handle without errors
```

**Test 8: Performance (Auto-Registration Overhead)**
```python
async def test_auto_registration_performance():
    """Test auto-registration overhead is <100ms."""
    import time

    await set_project(name="test_project")
    await generate_doc_templates(project_name="test_project")

    # First call (with auto-registration)
    start = time.time()
    await manage_docs(action="list_sections", doc="architecture")
    first_call_duration = time.time() - start

    # Second call (already registered, no auto-registration)
    start = time.time()
    await manage_docs(action="list_sections", doc="architecture")
    second_call_duration = time.time() - start

    # First call should be <100ms (with registration)
    assert first_call_duration < 0.1, f"Auto-registration too slow: {first_call_duration}s"

    # Second call should be faster (no registration)
    assert second_call_duration < first_call_duration
```

### Manual QA Checklist

**Before Deployment:**
- [ ] Run all unit tests (pytest tests/test_manage_docs_migration.py)
- [ ] Run all integration tests (pytest tests/test_manage_docs_integration.py)
- [ ] Manually test on development project
- [ ] Verify migration idempotency (run twice, no errors)
- [ ] Verify backfill accuracy (compare state.json vs docs_json)

**After Deployment:**
- [ ] Verify all existing projects still work
- [ ] Create new project and verify docs_json populated
- [ ] Test auto-registration on unregistered file
- [ ] Monitor logs for errors or unexpected behavior
- [ ] Performance check (auto-registration <100ms)

---

## Open Questions & Decisions
<!-- ID: open_questions -->

| Item | Owner | Status | Resolution |
|------|-------|--------|------------|
| Should we also migrate `docs_dir` field to database? | ArchitectAgent | DECIDED | NO - out of scope for v1.0, state.json sufficient |
| Should migration run automatically on server startup? | ArchitectAgent | DECIDED | NO - manual migration script safer, prevents production issues |
| Should we add schema version tracking to prevent future drift? | ArchitectAgent | DEFERRED | Future enhancement, not critical for v1.0 |
| What if docs_json is NULL but state.json also has no data? | ArchitectAgent | DECIDED | Fail gracefully with clear error message directing to generate_doc_templates |
| Should auto-registration compute hash on every call or cache? | ArchitectAgent | DECIDED | Compute on registration only, ProjectRegistry tracks changes thereafter |
| Do we need auto-registration for READ-ONLY actions? | ArchitectAgent | DECIDED | NO - read-only actions don't require registration, reduces overhead |
| Should we support PostgreSQL in v1.0? | ArchitectAgent | DECIDED | NO - SQLite only for v1.0, PostgreSQL is future work |

---

## References & Appendix
<!-- ID: references_appendix -->

### Source Files Referenced

**Database Layer:**
- `storage/sqlite.py:652-659` - CREATE TABLE scribe_projects
- `storage/sqlite.py:48-80` - upsert_project method

**Query Layer:**
- `shared/logging_utils.py:111-119` - get_active_project query
- `shared/logging_utils.py:134-138` - state.json fallback logic

**Tools Layer:**
- `tools/manage_docs.py` - Main entry point for document operations
- `tools/set_project.py` - Project creation and initialization
- `tools/generate_doc_templates.py` - Template generation

**State Management:**
- `.scribe/state.json` - Contains complete project data including docs mappings
- `state/manager.py` - State persistence logic

### Related Documents

**From scribe_systematic_audit_1 (READ-ONLY):**
- `architecture/PIVOT_MANAGE_DOCS_FIXES.md` - Original pivot plan
- `wiki/analysis/manage_docs_comprehensive_audit.md` - Detailed audit findings
- `wiki/specs/SPEC-MANAGE-DOCS-001-database-docs-field.yaml` - Technical specification

**From scribe_manage_docs_implementation (THIS PROJECT):**
- `research/RESEARCH_DATABASE_SCHEMA_20260106.md` - Database schema research
- `PHASE_PLAN.md` - Implementation phases and timeline
- `CHECKLIST.md` - Verification ledger

### Action Reference Table

| # | Action | Type | Auto-Register? | Description |
|---|--------|------|----------------|-------------|
| 1 | list_sections | EDIT | ✅ YES | Lists section anchors from file |
| 2 | replace_section | EDIT | ✅ YES | Updates specific section via anchor |
| 3 | apply_patch | EDIT | ✅ YES | Structured edits with compiler |
| 4 | replace_range | EDIT | ✅ YES | Line-targeted edits |
| 5 | append | EDIT | ✅ YES | Add content to document end |
| 6 | status_update | EDIT | ✅ YES | Toggle checklist items |
| 7 | normalize_headers | EDIT | ✅ YES | ATX canonicalization |
| 8 | generate_toc | EDIT | ✅ YES | Table of contents generation |
| 9 | search | EDIT | ✅ YES | Semantic search |
| 10 | create_research_doc | CREATE | ❌ NO | Create research document (explicit) |
| 11 | create_bug_report | CREATE | ❌ NO | Create bug report (explicit) |
| 12 | read_doc | READ | ❌ N/A | Read document content |
| 13 | validate_frontmatter | READ | ❌ N/A | Validate YAML frontmatter |
| 14 | preview_changes | READ | ❌ N/A | Preview edits without applying |
| 15 | list_documents | READ | ❌ N/A | List registered documents |
| 16 | get_doc_info | READ | ❌ N/A | Get document metadata |
| 17 | refresh_index | WRITE | ❌ N/A | Update INDEX.md files |

### Confidence Scores

- **Problem Statement:** 0.95 (verified from source code)
- **Database Migration:** 0.95 (straightforward ALTER TABLE)
- **Query Integration:** 0.95 (simple query change + JSON parsing)
- **Auto-Registration Logic:** 0.90 (new code, needs testing)
- **Testing Strategy:** 0.90 (comprehensive but needs execution)
- **Overall Architecture:** 0.93 (high confidence, well-researched)

---

**Architecture Status:** COMPLETE
**Ready for Review:** YES
**Next Phase:** Review Agent validation (≥93% required to proceed)
## Production Test Section - Added by ReviewAgent

This section was added during Final Review (Phase 5) to test that manage_docs edit operations work correctly with Bug Fix #3's connection isolation resolution.

**Test Details:**
- Date: 2026-01-06
- Agent: ReviewAgent
- Purpose: Validate backend connection reuse works in production
- Expected: No DOC_NOT_FOUND errors
- Result: SUCCESS
