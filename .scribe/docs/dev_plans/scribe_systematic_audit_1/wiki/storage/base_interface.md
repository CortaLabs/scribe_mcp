# Storage Abstraction Layer - Base Interface

**File**: `storage/base.py`
**LOC**: 286
**Purpose**: Defines unified persistence interface for all storage backends
**Last Audited**: 2026-01-05

---

## 1. Overview

The `StorageBackend` abstract base class defines the contract that all persistence layers must implement. This abstraction enables the Scribe MCP system to support multiple database backends (SQLite, PostgreSQL) without changing application code.

### Key Design Principles

1. **Backend Agnostic**: Application code uses only the abstract interface
2. **Async-First**: All methods are async to support concurrent operations
3. **Optimistic Concurrency**: Version tracking prevents concurrent update conflicts
4. **Optional Features**: Some methods have default implementations for backward compatibility

---

## 2. Core Exception Types

### ConflictError

```python
class ConflictError(Exception):
    """Raised when an optimistic concurrency conflict occurs."""
```

**Purpose**: Signals version mismatch during concurrent project updates
**Used By**: `set_agent_project()` optimistic concurrency control
**File Location**: storage/base.py:12-14

---

## 3. Abstract Methods (Required Implementation)

All storage backends MUST implement these 17 methods:

### 3.1 Project Operations (4 methods)

#### upsert_project()

```python
@abstractmethod
async def upsert_project(
    self,
    *,
    name: str,
    repo_root: str,
    progress_log_path: str,
) -> ProjectRecord:
    """Insert or update a project row and return the record."""
```

**Contract**:
- Creates new project if `name` doesn't exist
- Updates existing project if `name` matches
- Returns full `ProjectRecord` with database ID
- Must be idempotent

**File Location**: storage/base.py:26-34

---

#### fetch_project()

```python
@abstractmethod
async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
    """Return the project by name when present."""
```

**Contract**:
- Returns `ProjectRecord` if found
- Returns `None` if project doesn't exist
- Should be fast (indexed lookup)

**File Location**: storage/base.py:36-38

---

#### list_projects()

```python
@abstractmethod
async def list_projects(self) -> List[ProjectRecord]:
    """Return all known projects."""
```

**Contract**:
- Returns ALL projects (no filtering)
- Returns empty list if no projects exist
- Order not guaranteed by abstraction

**File Location**: storage/base.py:40-42

---

#### delete_project()

```python
@abstractmethod
async def delete_project(self, name: str) -> bool:
    """Delete a project and all associated data. Returns True if project was deleted."""
```

**Contract**:
- Deletes project and CASCADE deletes all related entries
- Returns `True` if project was deleted
- Returns `False` if project didn't exist
- Must handle foreign key constraints

**File Location**: storage/base.py:44-46

**⚠️ CRITICAL GAP**: PostgreSQL backend raises `NotImplementedError` (postgres.py:81-84)

---

### 3.2 Entry Operations (3 methods)

#### insert_entry()

```python
@abstractmethod
async def insert_entry(
    self,
    *,
    entry_id: str,
    project: ProjectRecord,
    ts: datetime,
    emoji: str,
    agent: Optional[str],
    message: str,
    meta: Optional[Dict[str, Any]],
    raw_line: str,
    sha256: str,
) -> None:
    """Insert a progress log entry and update metrics."""
```

**Contract**:
- Inserts entry into `scribe_entries` table
- Updates `scribe_metrics` counters (total_entries, success_count, etc.)
- `entry_id` must be unique
- `project.id` must reference valid project
- Should be atomic (entry + metrics in same transaction)

**File Location**: storage/base.py:48-62

---

#### fetch_recent_entries()

```python
@abstractmethod
async def fetch_recent_entries(
    self,
    *,
    project: ProjectRecord,
    limit: int,
    filters: Optional[Dict[str, Any]] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Return recent entries for the given project."""
```

**Contract**:
- Returns entries ordered by timestamp DESC (newest first)
- Respects `limit` and `offset` for pagination
- `filters` supports: `agent`, `emoji`, `status` keys
- Returns list of dicts (not ProjectRecord objects)

**File Location**: storage/base.py:92-101

---

#### query_entries()

```python
async def query_entries(
    self,
    *,
    project: ProjectRecord,
    limit: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    agents: Optional[List[str]] = None,
    emojis: Optional[List[str]] = None,
    message: Optional[str] = None,
    message_mode: str = "substring",
    case_sensitive: bool = False,
    meta_filters: Optional[Dict[str, str]] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Advanced log query for the given project."""
```

**Contract**:
- Filters by time range (`start`, `end` ISO timestamps)
- Filters by `agents` list (OR logic)
- Filters by `emojis` list (OR logic)
- Filters by `message` (substring/regex/exact modes)
- Filters by metadata key-value pairs
- Returns entries matching ALL filters (AND logic)
- Ordered by timestamp DESC

**File Location**: storage/base.py:157-171

---

### 3.3 Agent Session Management (5 methods)

#### upsert_agent_session()

```python
@abstractmethod
async def upsert_agent_session(
    self,
    agent_id: str,
    session_id: str,
    metadata: Optional[Dict[str, Any]]
) -> None:
    """Create or update an agent session."""
```

**Contract**:
- Creates session if doesn't exist
- Updates last_active_at if exists
- Stores session metadata

**File Location**: storage/base.py:268-270

---

#### heartbeat_session()

```python
@abstractmethod
async def heartbeat_session(self, session_id: str) -> None:
    """Update session last_active_at timestamp."""
```

**Contract**:
- Updates last_active_at to current time
- Used for session expiry tracking

**File Location**: storage/base.py:272-274

---

#### end_session()

```python
@abstractmethod
async def end_session(self, session_id: str) -> None:
    """Mark a session as expired."""
```

**Contract**:
- Sets session status to 'expired'
- Used for cleanup

**File Location**: storage/base.py:276-278

---

#### get_agent_project()

```python
@abstractmethod
async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
    """Get an agent's current project with version info."""
```

**Contract**:
- Returns dict with `project_name`, `version`, `updated_at`
- Returns `None` if agent has no project set

**File Location**: storage/base.py:280-282

---

#### set_agent_project()

```python
@abstractmethod
async def set_agent_project(
    self,
    agent_id: str,
    project_name: Optional[str],
    expected_version: Optional[int],
    updated_by: str,
    session_id: str
) -> Dict[str, Any]:
    """Set an agent's current project with optimistic concurrency control."""
```

**Contract**:
- Updates agent's current project
- Checks `expected_version` matches current version
- Raises `ConflictError` if version mismatch
- Increments version on success
- Returns updated record

**File Location**: storage/base.py:284-286

---

## 4. Optional Methods (Default Implementations)

### 4.1 Lifecycle Hooks

#### setup()

```python
async def setup(self) -> None:
    """Perform any startup work. Optional for some backends."""
```

**Default**: No-op (empty implementation)
**Override**: PostgreSQL creates connection pool
**File Location**: storage/base.py:20-21

---

#### close()

```python
async def close(self) -> None:
    """Release held resources."""
```

**Default**: No-op (empty implementation)
**Override**: PostgreSQL closes connection pool
**File Location**: storage/base.py:23-24

---

### 4.2 Recording Methods

#### record_doc_change()

```python
async def record_doc_change(
    self,
    project: ProjectRecord,
    *,
    doc: str,
    section: Optional[str],
    action: str,
    agent: Optional[str],
    metadata: Optional[Dict[str, Any]],
    sha_before: str,
    sha_after: str,
) -> None:
    """Record a documentation change (optional for storage backends)."""
```

**Default**: No-op (empty implementation)
**Override**: SQLite/PostgreSQL write to `doc_changes` table
**File Location**: storage/base.py:64-76

---

#### record_agent_report_card()

```python
async def record_agent_report_card(
    self,
    project: ProjectRecord,
    *,
    file_path: str,
    agent_name: str,
    stage: Optional[str],
    overall_grade: Optional[float],
    performance_level: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> None:
    """Persist agent report card metadata (optional for storage backends)."""
    raise NotImplementedError
```

**Default**: Raises `NotImplementedError`
**Override**: SQLite writes to `agent_report_cards` table
**File Location**: storage/base.py:78-90

---

### 4.3 Pagination Helpers (Default Implementations)

#### fetch_recent_entries_paginated()

```python
async def fetch_recent_entries_paginated(
    self,
    *,
    project: ProjectRecord,
    page: int = 1,
    page_size: int = 50,
    filters: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return recent entries with pagination metadata."""
```

**Default**: Calls `fetch_recent_entries()` + `count_entries()`
**Returns**: `(entries, total_count)` tuple
**File Location**: storage/base.py:103-137

---

#### count_entries()

```python
async def count_entries(
    self,
    project: ProjectRecord,
    filters: Optional[Dict[str, Any]] = None,
) -> int:
    """Count total entries matching filters."""
```

**Default**: Fetches 10,000 entries and returns `len()`
**⚠️ Performance**: Inefficient - backends should override with COUNT query
**File Location**: storage/base.py:139-155

---

#### query_entries_paginated()

```python
async def query_entries_paginated(
    self,
    *,
    project: ProjectRecord,
    page: int = 1,
    page_size: int = 50,
    # ... same filters as query_entries
) -> Tuple[List[Dict[str, Any]], int]:
    """Advanced log query with pagination."""
```

**Default**: Calls `query_entries()` + `count_query_entries()`
**Returns**: `(entries, total_count)` tuple
**File Location**: storage/base.py:174-232

---

#### count_query_entries()

```python
async def count_query_entries(
    self,
    *,
    project: ProjectRecord,
    # ... same filters as query_entries
) -> int:
    """Count total entries matching query criteria."""
```

**Default**: Queries 10,000 entries and returns `len()`
**⚠️ Performance**: Inefficient - backends should override with COUNT query
**File Location**: storage/base.py:234-265

---

## 5. Architecture Patterns

### 5.1 Abstraction Benefits

1. **Backend Swapping**: Switch SQLite ↔ PostgreSQL without code changes
2. **Testing**: Mock storage backend for unit tests
3. **Future Expansion**: Add Redis, DynamoDB, etc. by implementing interface
4. **Type Safety**: Type hints enforce contract compliance

### 5.2 Known Limitations

1. **No Transactions**: Abstraction doesn't expose transaction control
2. **No Bulk Operations**: No `insert_many()` or `update_many()`
3. **Limited Query**: No JOIN operations across tables
4. **Sync Methods**: No synchronous API (async-only)

---

## 6. Implementation Status

| Backend | Status | Completeness | Notes |
|---------|--------|--------------|-------|
| SQLite | ✅ Complete | 100% | All methods implemented |
| PostgreSQL | ⚠️ Incomplete | ~85% | Missing: delete_project, record_agent_report_card |

---

## 7. Critical Issues

### 7.1 PostgreSQL delete_project() Gap

**File**: `storage/postgres.py:69-84`
**Severity**: HIGH
**Impact**: Cannot delete projects in PostgreSQL mode

```python
async def delete_project(self, name: str) -> bool:
    # ...
    raise NotImplementedError(
        "delete_project not yet implemented for PostgreSQL backend. "
        "Add implementation to scribe_mcp.db.ops module."
    )
```

**Fix Required**: Implement in `db/ops.py` module

---

## 8. Related Files

- **Implementations**: `storage/sqlite.py`, `storage/postgres.py`
- **Models**: `storage/models.py` (ProjectRecord definition)
- **Database Ops**: `db/ops.py` (PostgreSQL operations)
- **Usage**: All tools in `tools/` directory use StorageBackend

---

## 9. Testing Recommendations

1. **Contract Tests**: Verify all backends implement same behavior
2. **Concurrency Tests**: Test ConflictError handling
3. **Pagination Tests**: Verify offset/limit correctness
4. **Performance Tests**: Benchmark count_entries() implementations

---

**Next**: See `sqlite_backend.md` for SQLite-specific implementation details
