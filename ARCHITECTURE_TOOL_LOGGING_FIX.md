# Architecture: Tool Logging Recursion Fix

**Status:** Ready for Implementation
**Created:** 2026-01-04
**Author:** ArchitectAgent
**Project:** scribe_tool_output_refinement

---

## Executive Summary

This document specifies the architecture for eliminating the recursive `append_entry` pattern in `finalize_tool_response()` by implementing a direct JSONL+SQL dual-write system for tool call logging.

**Key Design Principles:**
- **Zero Recursion:** Direct file/SQL writes bypass `append_entry` entirely
- **Session-Aware:** All tool calls linked to stable `session_id` from `scribe_sessions` table
- **Crash-Safe:** Reuses existing WAL-based atomic write infrastructure
- **No Reminders:** Tool logs are audit trails, explicitly excluded from reminder system
- **Backward Compatible:** Maintains existing JSONL format for tool logs

---

## Problem Statement

### Current State (BROKEN - VERIFIED AT CODE LEVEL)

**File:** `utils/response.py:2164-2183`

```python
# Current implementation - RECURSIVE PATTERN
if tool_name != "append_entry":
    await append_entry(
        message=f"Tool call: {tool_name}",
        log_type="tool_logs",
        meta={...},
        format="structured"
    )
```

**Issues:**
1. **Recursion:** `finalize_tool_response()` → `append_entry()` → `finalize_tool_response()` → infinite loop
2. **Guard Insufficient:** Only prevents `append_entry` from logging itself, all other tools still recurse
3. **Token Bloat:** Creates massive JSON nesting in tool responses
4. **Performance:** Unnecessary overhead for every tool call
5. **No SQL Metrics:** Tool usage data only in per-project JSONL files, no cross-project analytics

### Root Cause Analysis

The recursion occurs because:
- `append_entry` is itself a tool that calls `finalize_tool_response()`
- `finalize_tool_response()` tries to log ALL tool calls via `append_entry(log_type="tool_logs")`
- Guard only prevents one level, doesn't stop other tools from recursing

---

## Solution Overview

### NEW Architecture: Direct JSONL+SQL Dual-Write

```
Tool Call → finalize_tool_response() → log_tool_call()
                                            ├─→ Direct JSONL write (utils/files.py::append_line)
                                            └─→ Direct SQL insert (storage/sqlite.py::record_tool_call)

NO CALLS TO append_entry() - RECURSION IMPOSSIBLE
```

**Key Components:**
1. **NEW:** `tool_calls` SQL table (session-linked metrics)
2. **NEW:** `utils/tool_logger.py` module (direct writer)
3. **EXISTING (VERIFIED):** `scribe_sessions` table at `storage/sqlite.py:746-768`
4. **EXISTING (VERIFIED):** `append_line()` with WAL at `utils/files.py:516-543`
5. **MODIFIED:** `finalize_tool_response()` to call new logger instead of `append_entry`

---

## Component Design

### 1. NEW: `tool_calls` SQL Table

**Location:** Add to `storage/sqlite.py` schema initialization

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    duration_ms REAL,
    status TEXT CHECK (status IN ('success', 'error', 'partial')) NOT NULL DEFAULT 'success',
    format_requested TEXT,
    project_name TEXT,
    agent_id TEXT,
    error_message TEXT,
    response_size_bytes INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_timestamp ON tool_calls(timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_calls_project ON tool_calls(project_name);
```

**Design Rationale:**
- `session_id` links to EXISTING `scribe_sessions` table (VERIFIED at `storage/sqlite.py:746-768`)
- Cascade delete ensures orphan cleanup when sessions expire
- Indexes support common queries: session history, tool performance, project activity
- `response_size_bytes` enables token/cost tracking
- `duration_ms` enables performance monitoring

### 2. NEW: `utils/tool_logger.py` Module

**Purpose:** Direct JSONL+SQL writer that bypasses `append_entry` completely

**Specification:**

```python
"""
Direct tool call logger - bypasses append_entry to prevent recursion.

CRITICAL: This module must NEVER call append_entry or finalize_tool_response.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# EXISTING infrastructure imports (VERIFIED)
from utils.files import append_line  # VERIFIED at utils/files.py:516-543
from storage.sqlite import SQLiteStorage  # Will add record_tool_call() method


async def log_tool_call(
    session_id: str,
    tool_name: str,
    format_requested: str,
    project_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    response_size_bytes: Optional[int] = None,
    repo_root: Optional[Path] = None,
    storage: Optional[SQLiteStorage] = None
) -> None:
    """
    Log a tool call to JSONL and SQL without triggering recursion.

    Args:
        session_id: Session identifier from scribe_sessions table
        tool_name: Name of the tool that was called
        format_requested: Format parameter from tool call (readable/structured/compact)
        project_name: Optional project context
        agent_id: Optional agent identifier
        duration_ms: Optional execution time in milliseconds
        status: success|error|partial (default: success)
        error_message: Optional error details if status=error
        response_size_bytes: Optional response payload size for cost tracking
        repo_root: Repository root for file operations
        storage: SQLiteStorage instance for database writes

    GUARANTEES:
    - NO calls to append_entry (prevents recursion)
    - NO calls to finalize_tool_response (prevents recursion)
    - NO reminder generation (tool logs are audit trails, not work logs)
    - Atomic JSONL write with WAL crash safety
    - Parallel SQL insert for metrics
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Construct JSONL entry (backward compatible format)
    jsonl_entry = {
        "timestamp": timestamp,
        "session_id": session_id,
        "tool": tool_name,
        "format_requested": format_requested,
        "project": project_name,
        "agent": agent_id,
        "duration_ms": duration_ms,
        "status": status,
        "error": error_message
    }

    # STEP 1: Write to JSONL (uses EXISTING append_line with WAL)
    if project_name and repo_root:
        tool_log_path = repo_root / ".scribe" / "docs" / "dev_plans" / project_name / "TOOL_LOG.jsonl"
    else:
        # Global tool log for sentinel mode
        tool_log_path = repo_root / ".scribe" / "logs" / "GLOBAL_TOOL_LOG.jsonl"

    try:
        await append_line(
            path=tool_log_path,
            line=json.dumps(jsonl_entry),
            use_wal=True,  # Crash-safe atomic write
            repo_root=repo_root,
            context={"component": "tool_logger", "tool": tool_name}
        )
    except Exception as e:
        # Log failure but don't block tool execution
        print(f"Warning: Failed to write tool log to JSONL: {e}")

    # STEP 2: Write to SQL (parallel metrics storage)
    if storage:
        try:
            await storage.record_tool_call(
                session_id=session_id,
                tool_name=tool_name,
                timestamp=timestamp,
                duration_ms=duration_ms,
                status=status,
                format_requested=format_requested,
                project_name=project_name,
                agent_id=agent_id,
                error_message=error_message,
                response_size_bytes=response_size_bytes
            )
        except Exception as e:
            # Log failure but don't block tool execution
            print(f"Warning: Failed to write tool log to SQL: {e}")


async def get_session_tool_calls(
    storage: SQLiteStorage,
    session_id: str
) -> list[Dict[str, Any]]:
    """
    Retrieve all tool calls for a session.

    Args:
        storage: SQLiteStorage instance
        session_id: Session identifier

    Returns:
        List of tool call records ordered by timestamp
    """
    return await storage.get_session_tool_calls(session_id)


async def get_tool_metrics(
    storage: SQLiteStorage,
    tool_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get performance metrics for a specific tool.

    Args:
        storage: SQLiteStorage instance
        tool_name: Name of the tool to analyze
        start_time: Optional start timestamp filter
        end_time: Optional end timestamp filter

    Returns:
        Dictionary with metrics: total_calls, avg_duration_ms, error_rate, etc.
    """
    return await storage.get_tool_metrics(tool_name, start_time, end_time)
```

**Critical Design Constraints:**
- ❌ MUST NOT import or call `tools.append_entry`
- ❌ MUST NOT import or call `utils.response.finalize_tool_response`
- ❌ MUST NOT trigger reminder system
- ✅ MUST use EXISTING `utils.files.append_line()` for JSONL (VERIFIED)
- ✅ MUST link to EXISTING `scribe_sessions` table via session_id (VERIFIED)

### 3. EXISTING: Integration Points (VERIFIED)

#### A. `scribe_sessions` Table
**Location:** `storage/sqlite.py:746-768` (VERIFIED)

**Existing Schema:**
```sql
CREATE TABLE IF NOT EXISTS scribe_sessions (
    session_id TEXT PRIMARY KEY,          -- SHA-256 hash (stable across tool calls)
    transport_session_id TEXT,            -- Initial connection ID
    agent_id TEXT,                        -- Agent identifier
    repo_root TEXT,                       -- Repository root path
    mode TEXT NOT NULL CHECK (mode IN ('sentinel','project')) DEFAULT 'sentinel',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Usage:** Tool logger receives `session_id` from execution context, links tool calls to this table.

#### B. `append_line()` Function
**Location:** `utils/files.py:516-543` (VERIFIED)

**Existing Signature:**
```python
async def append_line(
    path: Path,
    line: str,
    use_wal: bool = True,  # Write-Ahead Log for crash safety
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None
```

**Usage:** Tool logger calls this directly for JSONL writes, bypassing `append_entry`.

#### C. Session Derivation
**Location:** `server.py:162-199`

**How Session ID is Generated:**
```python
session_id = SHA-256(repo_root:mode:scope_key:agent_key)
```

- **Sentinel mode:** scope_key = current day (YYYY-MM-DD)
- **Project mode:** scope_key = execution_id UUID
- **Stability:** Same session_id for entire agent execution

**Usage:** `finalize_tool_response()` extracts `session_id` from execution context, passes to tool logger.

### 4. MODIFIED: `utils/response.py::finalize_tool_response()`

**Current Code:** Lines 2164-2183 (VERIFIED - RECURSIVE)

**New Code:**
```python
# STEP 1: Log to tool_logs (audit trail) - Direct write to prevent recursion
try:
    from utils.tool_logger import log_tool_call
    from execution_context import get_current_session_id, get_storage_instance

    # Extract session context (NEW integration point)
    session_id = await get_current_session_id()  # From execution context
    storage = await get_storage_instance()       # From execution context
    project_name = data.get("project_name")      # From tool response
    agent_id = data.get("agent_id")              # From tool response

    # Direct JSONL+SQL write (NO recursion possible)
    await log_tool_call(
        session_id=session_id,
        tool_name=tool_name,
        format_requested=format,
        project_name=project_name,
        agent_id=agent_id,
        status="success",
        repo_root=Path.cwd(),  # Or from execution context
        storage=storage
    )
except Exception as e:
    # Log failure but don't block response
    print(f"Warning: Failed to log tool call: {e}")
```

**Key Changes:**
1. **Remove:** `await append_entry(log_type="tool_logs", ...)` (recursive call)
2. **Add:** `await log_tool_call(...)` (direct write, no recursion)
3. **Add:** Session context extraction from execution environment
4. **Guarantee:** No code path can trigger recursion

### 5. NEW: SQL Methods in `storage/sqlite.py`

**Add to SQLiteStorage class:**

```python
async def record_tool_call(
    self,
    session_id: str,
    tool_name: str,
    timestamp: str,
    duration_ms: Optional[float] = None,
    status: str = "success",
    format_requested: Optional[str] = None,
    project_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    error_message: Optional[str] = None,
    response_size_bytes: Optional[int] = None
) -> None:
    """Insert tool call record into tool_calls table."""
    async with self._conn_lock:
        await self._conn.execute(
            """
            INSERT INTO tool_calls (
                session_id, tool_name, timestamp, duration_ms, status,
                format_requested, project_name, agent_id, error_message, response_size_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, tool_name, timestamp, duration_ms, status,
             format_requested, project_name, agent_id, error_message, response_size_bytes)
        )
        await self._conn.commit()


async def get_session_tool_calls(self, session_id: str) -> list[Dict[str, Any]]:
    """Retrieve all tool calls for a session."""
    async with self._conn_lock:
        cursor = await self._conn.execute(
            """
            SELECT id, tool_name, timestamp, duration_ms, status,
                   format_requested, project_name, agent_id, error_message
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY timestamp ASC
            """,
            (session_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_tool_metrics(
    self,
    tool_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    """Get performance metrics for a specific tool."""
    where_clauses = ["tool_name = ?"]
    params = [tool_name]

    if start_time:
        where_clauses.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("timestamp <= ?")
        params.append(end_time)

    where_sql = " AND ".join(where_clauses)

    async with self._conn_lock:
        cursor = await self._conn.execute(
            f"""
            SELECT
                COUNT(*) as total_calls,
                AVG(duration_ms) as avg_duration_ms,
                MIN(duration_ms) as min_duration_ms,
                MAX(duration_ms) as max_duration_ms,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                SUM(response_size_bytes) as total_bytes
            FROM tool_calls
            WHERE {where_sql}
            """,
            tuple(params)
        )
        row = await cursor.fetchone()
        return dict(row) if row else {}
```

---

## Data Flow

### Tool Call Lifecycle

```
1. MCP Client calls tool (e.g., append_entry)
   ↓
2. Tool executes and returns result
   ↓
3. finalize_tool_response() called with tool_name, result, format
   ↓
4. Extract session context:
   - session_id from execution_context (linked to scribe_sessions table)
   - project_name from tool result
   - agent_id from execution_context
   ↓
5. Call log_tool_call() with session context
   ↓
6. Parallel dual-write:
   ├─→ JSONL: append_line(TOOL_LOG.jsonl, json_entry, use_wal=True)
   └─→ SQL: storage.record_tool_call(session_id, tool_name, ...)
   ↓
7. Return formatted response to MCP client

NO RECURSION: log_tool_call() never calls append_entry or finalize_tool_response
```

### Session Integration

```
Session Creation (server.py):
1. MCP client connects with transport_session_id
2. derive_session_identity() generates stable session_id = SHA-256(repo:mode:scope:agent)
3. Insert into scribe_sessions table
4. Store session_id in execution context

Tool Logging (utils/tool_logger.py):
1. Extract session_id from execution context
2. Write tool call with session_id to JSONL
3. Insert tool call with session_id to tool_calls table (FOREIGN KEY to scribe_sessions)
4. Cascade delete ensures cleanup when session expires
```

---

## No Recursion Guarantee

### Design Proof

**Recursion Prevention Mechanisms:**

1. **Module Isolation:**
   - `utils/tool_logger.py` NEVER imports `tools.append_entry`
   - `utils/tool_logger.py` NEVER imports `utils.response`
   - Static analysis can verify no circular dependencies

2. **Direct Infrastructure Use:**
   - JSONL writes use `utils.files.append_line()` directly
   - SQL writes use `storage.sqlite.record_tool_call()` directly
   - Both are low-level primitives that don't call higher-level tools

3. **Code Review Checkpoint:**
   - Before merging, verify `utils/tool_logger.py` has zero imports of:
     - `tools.append_entry`
     - `utils.response.finalize_tool_response`
   - Grep verification: `grep -r "from tools.append_entry" utils/tool_logger.py` → no matches
   - Grep verification: `grep -r "finalize_tool_response" utils/tool_logger.py` → no matches

4. **Type System Guard (Future):**
   - Could add static type checking to prevent importing append_entry in tool_logger.py
   - Mypy or Pyright rules to enforce module boundaries

### Testing Strategy

**Unit Tests:**
```python
async def test_log_tool_call_no_recursion():
    """Verify log_tool_call never triggers append_entry."""
    # Mock append_entry to fail if called
    with patch('tools.append_entry.append_entry', side_effect=AssertionError("RECURSION DETECTED")):
        await log_tool_call(
            session_id="test-session",
            tool_name="test_tool",
            format_requested="readable",
            repo_root=Path("/tmp/test"),
            storage=mock_storage
        )
        # Test passes if no AssertionError raised
```

**Integration Tests:**
```python
async def test_finalize_tool_response_integration():
    """Verify complete tool call flow without recursion."""
    call_count = 0

    # Track how many times finalize_tool_response is called
    original_finalize = finalize_tool_response

    async def tracked_finalize(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise AssertionError(f"RECURSION: finalize called {call_count} times")
        return await original_finalize(*args, **kwargs)

    with patch('utils.response.finalize_tool_response', side_effect=tracked_finalize):
        result = await some_tool.execute()
        assert call_count == 1, "Should only call finalize_tool_response once"
```

---

## Reminder System Exclusion

### Why Tool Logs Don't Need Reminders

**Tool logs are audit trails, not work logs:**
- Purpose: Track MCP tool execution for debugging, analytics, cost tracking
- Not user-facing work that needs reminder prompts
- High frequency (potentially hundreds per session)
- Reminder prompts would create massive token bloat

### Implementation

**Reminder System Context:**
The reminder system (implemented in `utils/reminder_engine.py`) monitors `append_entry` calls to detect stale work and prompt users to log progress.

**Exclusion Mechanism:**
Tool logs bypass the reminder system entirely because they:
1. **Don't use append_entry:** Direct writes via `log_tool_call()` never trigger reminder checks
2. **Separate JSONL files:** `TOOL_LOG.jsonl` is distinct from `PROGRESS_LOG.md` that reminder system monitors
3. **Separate SQL table:** `tool_calls` table is separate from `progress_entries` table that reminder system queries

**Verification:**
```python
# Reminder system only monitors these log types (from config/log_config.json):
REMINDER_ENABLED_LOGS = ["progress", "doc_updates", "bugs"]

# tool_logs is explicitly excluded
assert "tool_logs" not in REMINDER_ENABLED_LOGS
```

---

## Implementation Phases

### Phase 1: Database Schema (1 hour)

**Task:** Add `tool_calls` table to SQLite schema

**Files Modified:**
- `storage/sqlite.py` - Add table creation in `_setup_schema()`

**Verification:**
```bash
# Check table exists
sqlite3 .scribe/state.db "SELECT sql FROM sqlite_master WHERE name='tool_calls';"

# Verify foreign key constraint
sqlite3 .scribe/state.db "PRAGMA foreign_key_list(tool_calls);"
```

**Success Criteria:**
- [ ] Table `tool_calls` created with all specified columns
- [ ] Indexes created on session_id, tool_name, timestamp, project_name
- [ ] Foreign key constraint to scribe_sessions verified
- [ ] Cascade delete tested (delete session → tool_calls deleted)

### Phase 2: Tool Logger Module (2-3 hours)

**Task:** Create `utils/tool_logger.py` with direct JSONL+SQL writer

**Files Created:**
- `utils/tool_logger.py` - New module

**Files Modified:**
- `storage/sqlite.py` - Add `record_tool_call()`, `get_session_tool_calls()`, `get_tool_metrics()` methods

**Verification:**
```python
# Unit test: Direct JSONL write
async def test_log_tool_call_jsonl():
    await log_tool_call(
        session_id="test-session",
        tool_name="test_tool",
        format_requested="readable",
        repo_root=Path("/tmp/test")
    )
    # Verify JSONL entry written
    assert Path("/tmp/test/.scribe/logs/GLOBAL_TOOL_LOG.jsonl").exists()

# Unit test: SQL insert
async def test_log_tool_call_sql():
    await log_tool_call(
        session_id="test-session",
        tool_name="test_tool",
        format_requested="readable",
        storage=test_storage
    )
    # Verify SQL record
    rows = await test_storage.get_session_tool_calls("test-session")
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "test_tool"

# Critical: No recursion test
async def test_no_recursion():
    with patch('tools.append_entry.append_entry', side_effect=AssertionError("RECURSION")):
        await log_tool_call(...)  # Should not raise
```

**Success Criteria:**
- [ ] `log_tool_call()` writes to JSONL using `append_line()` with WAL
- [ ] `log_tool_call()` inserts into SQL using `record_tool_call()`
- [ ] Zero imports of `tools.append_entry` or `utils.response`
- [ ] Unit tests verify JSONL and SQL writes work
- [ ] Unit test verifies no recursion (mock append_entry to fail)

### Phase 3: Integrate with finalize_tool_response() (1 hour)

**Task:** Replace recursive `append_entry` call with direct `log_tool_call()`

**Files Modified:**
- `utils/response.py` - Replace lines 2164-2183
- `server.py` (potentially) - Expose session_id in execution context if not already available

**Verification:**
```python
# Integration test: End-to-end tool call
async def test_tool_call_logging():
    # Call any tool (e.g., list_projects)
    result = await list_projects()

    # Verify TOOL_LOG.jsonl has entry
    tool_log = Path(".scribe/logs/GLOBAL_TOOL_LOG.jsonl")
    assert tool_log.exists()

    # Verify tool_calls table has entry
    session_id = await get_current_session_id()
    calls = await storage.get_session_tool_calls(session_id)
    assert any(call["tool_name"] == "list_projects" for call in calls)

# Critical: No recursion in production
async def test_no_recursion_production():
    recursion_detector = RecursionDetector()

    with recursion_detector.track("finalize_tool_response"):
        await some_tool.execute()

    assert recursion_detector.max_depth == 1, "Should only call finalize once"
```

**Success Criteria:**
- [ ] `finalize_tool_response()` calls `log_tool_call()` instead of `append_entry()`
- [ ] Session context properly extracted and passed to tool logger
- [ ] Integration test verifies tool calls are logged to JSONL and SQL
- [ ] No recursion detected in integration tests
- [ ] All existing tests still pass

### Phase 4: Testing & Validation (2-3 hours)

**Task:** Comprehensive testing and documentation

**Tests to Create:**
- `tests/test_tool_logger.py` - Unit tests for tool_logger module
- `tests/test_tool_logging_integration.py` - End-to-end integration tests
- `tests/test_no_recursion.py` - Recursion detection tests

**Documentation:**
- Update `docs/Scribe_Usage.md` with tool logging architecture
- Add code comments explaining recursion prevention

**Verification:**
```bash
# Run all tests
pytest tests/test_tool_logger.py -v
pytest tests/test_tool_logging_integration.py -v
pytest tests/test_no_recursion.py -v

# Verify no recursion with real MCP session
python -m scripts.test_mcp_server  # Should show tool logs without recursion

# Check JSONL format preserved
cat .scribe/logs/GLOBAL_TOOL_LOG.jsonl | jq .  # Should parse correctly

# Check SQL data
sqlite3 .scribe/state.db "SELECT * FROM tool_calls LIMIT 10;"
```

**Success Criteria:**
- [ ] All unit tests pass (JSONL write, SQL insert, no recursion)
- [ ] All integration tests pass (end-to-end tool call flow)
- [ ] Manual testing confirms no recursion in MCP client sessions
- [ ] JSONL format verified backward compatible
- [ ] SQL queries work correctly
- [ ] Documentation updated

---

## Verification Checklist

### Pre-Implementation Verification
- [x] Research report read and verified against actual code
- [x] Existing code paths verified (response.py, files.py, sqlite.py)
- [x] Architecture distinguishes EXISTING vs NEW components clearly

### Phase 1 Verification (SQL Schema)
- [ ] `tool_calls` table created with correct schema
- [ ] Indexes created on session_id, tool_name, timestamp, project_name
- [ ] Foreign key constraint to `scribe_sessions` verified
- [ ] Cascade delete tested (session deletion removes tool_calls)

### Phase 2 Verification (Tool Logger Module)
- [ ] `utils/tool_logger.py` created with `log_tool_call()` function
- [ ] Zero imports of `tools.append_entry` (grep verified)
- [ ] Zero imports of `utils.response` (grep verified)
- [ ] Direct JSONL writing using `append_line()` works
- [ ] Direct SQL writing using `record_tool_call()` works
- [ ] Unit test confirms no recursion (mock append_entry to fail)

### Phase 3 Verification (Integration)
- [ ] `finalize_tool_response()` updated to call `log_tool_call()`
- [ ] Recursive `append_entry` call removed
- [ ] Session context extraction working
- [ ] Integration test verifies tool calls logged to JSONL
- [ ] Integration test verifies tool calls logged to SQL
- [ ] Zero recursion in integration tests (recursion detector passes)

### Phase 4 Verification (Testing)
- [ ] Unit tests pass for tool_logger module
- [ ] Integration tests pass for end-to-end flow
- [ ] Recursion detection tests pass
- [ ] Manual MCP session testing confirms no recursion
- [ ] JSONL format backward compatible
- [ ] SQL queries work correctly
- [ ] Documentation updated

### Final Verification (Production Ready)
- [ ] No reminders triggered for tool logs (verified by monitoring)
- [ ] Existing TOOL_LOG.jsonl format maintained
- [ ] Session-based queries work (`get_session_tool_calls()`)
- [ ] Tool metrics work (`get_tool_metrics()`)
- [ ] All existing tests still pass
- [ ] Code review confirms zero recursion possibility

---

## Success Metrics

**Functional Requirements:**
- ✅ Zero recursion in `finalize_tool_response()` (tested with recursion detector)
- ✅ Tool calls logged to JSONL with backward-compatible format
- ✅ Tool calls logged to SQL with session linkage
- ✅ No reminders generated for tool logs
- ✅ Crash-safe writes using WAL pattern

**Performance Requirements:**
- Tool logging adds < 10ms overhead per tool call
- JSONL writes are atomic and non-blocking
- SQL inserts don't block tool execution (async)

**Quality Requirements:**
- Zero imports of `append_entry` in `utils/tool_logger.py` (enforced by code review)
- 100% test coverage for recursion prevention
- All existing tests pass after integration

---

## Open Questions & Future Work

**Potential Enhancements:**
1. **Backfill Historical Data:** Migrate existing TOOL_LOG.jsonl files into SQL for analytics
2. **Real-Time Analytics:** Dashboard for tool usage, performance, errors
3. **Cost Tracking:** Link tool calls to token usage for API cost estimation
4. **Anomaly Detection:** Alert on unusual tool usage patterns
5. **Session Replay:** Reconstruct entire agent sessions from tool call history

**Migration Strategy (if needed):**
- Existing TOOL_LOG.jsonl files continue working (backward compatible)
- New tool calls write to both JSONL and SQL
- Optional: Background job to backfill old JSONL into SQL

---

## Architecture Approval

**Confidence Score:** 0.95

**Reasoning:**
- **Why:** Research confirmed recursion is root cause, direct write is solution
- **What:** Verified existing infrastructure (append_line WAL, scribe_sessions), designed new components (tool_calls table, tool_logger module) with zero recursion guarantee
- **How:** Code paths verified at line numbers, integration points identified, recursion prevention mechanisms specified with test strategy

**Ready for Review:** ✅
**Ready for Implementation:** ✅ (pending Review Agent approval)

---

**End of Architecture Document**
