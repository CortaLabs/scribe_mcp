---
id: scribe_tool_output_refinement-phase-plan
title: "📋 Phase Plan — SQL Tool Logging Fix"
doc_type: phase_plan
category: project_management
status: ready_for_implementation
version: '1.0'
last_updated: '2026-01-04'
maintained_by: ArchitectAgent
created_by: ArchitectAgent
owners: []
related_docs: [".scribe/docs/dev_plans/scribe_tool_output_refinement/ARCHITECTURE_GUIDE.md"]
tags: ["implementation", "asyncio", "sql-logging", "background-threads"]
summary: 'Detailed implementation roadmap for fixing SQL tool logging with asyncio.to_thread() pattern'
---

# 📋 Phase Plan — SQL Tool Logging Fix (Option 1)
**Author:** ArchitectAgent
**Version:** 1.0
**Status:** Ready for Implementation
**Last Updated:** 2026-01-04 12:43:00 UTC

> **Project Goal:** Fix SQL tool logging by replacing fire-and-forget `asyncio.create_task()` with background thread execution using `asyncio.to_thread()`, guaranteeing execution while maintaining non-blocking tool responses.

---

## Phase Overview

**Total Estimated Effort:** ~60 minutes
**Critical Path:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
**Deliverables:** Working SQL logging, comprehensive tests, performance validation

| Phase | Goal | Duration | Deliverables | Dependencies |
|-------|------|----------|--------------|--------------|
| Phase 1 | Create Synchronous SQL Method | 15 min | `record_tool_call_sync()` in storage/sqlite.py | None |
| Phase 2 | Update Response Utility | 10 min | Updated utils/response.py with background threads | Phase 1 |
| Phase 3 | Add Tests | 15 min | 3 new tests in test_tool_calls_schema.py | Phases 1 & 2 |
| Phase 4 | Integration Testing | 10 min | SQL writes verified, test suite passes | Phase 3 |
| Phase 5 | Performance Verification | 10 min | Benchmarks meet requirements | Phase 4 |
| Phase 6 | Final Review | 10 min (bonus) | Review report, implementation documentation | Phase 5 |

---

## Phase 1: Create Synchronous SQL Method
**Duration:** 15 minutes
**Owner:** Coder Agent
**Dependencies:** None
**Status:** Pending

### Objective
Create `record_tool_call_sync()` synchronous method in `storage/sqlite.py` for background thread execution.

### Tasks

#### Task 1.1: Locate Insertion Point
- **File:** `storage/sqlite.py`
- **Location:** After existing `record_tool_call()` async method (line ~2027)
- **Action:** Add new method immediately after async version for co-location
- **Acceptance:** Method is placed logically near related code

#### Task 1.2: Implement Synchronous Method
- **File:** `storage/sqlite.py`
- **Code Template:**
```python
def record_tool_call_sync(
    self,
    session_id: str,
    tool_name: str,
    duration_ms: Optional[float] = None,
    status: str = "success",
    format_requested: Optional[str] = None,
    project_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    error_message: Optional[str] = None,
    response_size_bytes: Optional[int] = None
) -> None:
    """Synchronous version of record_tool_call for background thread execution.

    This method is designed to be called via asyncio.to_thread() from
    finalize_tool_response(). It uses synchronous sqlite3 connection
    instead of aiosqlite for thread-safe execution.

    Args:
        session_id: Session identifier from scribe_sessions table
        tool_name: Name of the tool that was called
        duration_ms: Optional execution time in milliseconds
        status: Tool execution status (success, error, partial)
        format_requested: Format parameter from tool call
        project_name: Optional project context
        agent_id: Optional agent identifier
        error_message: Optional error details if status=error
        response_size_bytes: Optional response payload size

    Thread Safety:
        SQLite with WAL mode supports concurrent writes from multiple threads.
        This method acquires a lock via SQLite's internal locking mechanism.

    Error Handling:
        Exceptions are caught and logged to stderr. SQL logging failures
        must never propagate to the calling code or block tool execution.
    """
    try:
        # Use synchronous sqlite3 connection (not aiosqlite)
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for concurrency

        # Execute insert directly (no await needed)
        conn.execute(
            """
            INSERT INTO tool_calls (
                session_id, tool_name, timestamp, duration_ms, status,
                format_requested, project_name, agent_id, error_message, response_size_bytes
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, tool_name, duration_ms, status,
             format_requested, project_name, agent_id, error_message, response_size_bytes)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        # SQL logging is optional, never block or raise
        import sys
        print(f"Warning: SQL tool logging failed in background thread: {e}", file=sys.stderr)
```
- **Acceptance:** Method compiles without errors, follows existing code style

#### Task 1.3: Add Docstring and Comments
- **Requirements:**
  - Comprehensive docstring explaining purpose and thread safety
  - Inline comments for WAL mode and error handling
  - Reference to `asyncio.to_thread()` usage pattern
- **Acceptance:** Documentation is clear and complete

#### Task 1.4: Verify Syntax and Imports
- **Actions:**
  - Run syntax check: `python -m py_compile storage/sqlite.py`
  - Verify `sqlite3` import is available (standard library)
  - Check that `self.db_path` attribute exists in SQLiteStorage
- **Acceptance:** No syntax errors, all imports resolve

### Deliverables
- [ ] `record_tool_call_sync()` method added to `storage/sqlite.py`
- [ ] Comprehensive docstring with thread safety notes
- [ ] Error handling with stderr logging
- [ ] Syntax validation passed

### Validation
- Code compiles without errors
- Method signature matches architecture specification
- Docstring explains usage with `asyncio.to_thread()`

---

## Phase 2: Update Response Utility Integration
**Duration:** 10 minutes
**Owner:** Coder Agent
**Dependencies:** Phase 1 complete
**Status:** Pending

### Objective
Update `utils/response.py:2218` to use background thread pattern with `asyncio.to_thread()`.

### Tasks

#### Task 2.1: Locate Target Code
- **File:** `utils/response.py`
- **Lines:** 2218 (fire-and-forget `create_task` call)
- **Current Code:**
```python
asyncio.create_task(storage.record_tool_call(
    session_id=session_id,
    tool_name=tool_name,
    status="success" if data.get('ok', True) else "error",
    format_requested=format,
    project_name=project_name,
    agent_id=agent_id,
    error_message=data.get('error') if not data.get('ok', True) else None,
    response_size_bytes=response_size
))
```
- **Acceptance:** Located exact line number and code block

#### Task 2.2: Replace with Background Thread Pattern
- **New Code:**
```python
# FIXED: Use asyncio.to_thread() to guarantee execution in background thread
asyncio.create_task(asyncio.to_thread(
    storage.record_tool_call_sync,  # Synchronous method for thread execution
    session_id=session_id,
    tool_name=tool_name,
    duration_ms=None,  # Will add timing in future enhancement
    status="success" if data.get('ok', True) else "error",
    format_requested=format,
    project_name=project_name,
    agent_id=agent_id,
    error_message=data.get('error') if not data.get('ok', True) else None,
    response_size_bytes=response_size
))
```
- **Key Changes:**
  1. Wrap with `asyncio.to_thread()`
  2. Call `record_tool_call_sync` instead of `record_tool_call`
  3. Add `duration_ms=None` parameter explicitly
  4. Update comment to explain background thread execution
- **Acceptance:** Code matches architecture specification exactly

#### Task 2.3: Update Comments
- **Before Comment:**
```python
# STEP 1.5: Write to SQL for cross-project analytics
```
- **After Comment:**
```python
# STEP 1.5: Write to SQL for cross-project analytics (background thread for guaranteed execution)
# Uses asyncio.to_thread() to execute synchronous SQL write in thread pool, preventing orphaned tasks
```
- **Acceptance:** Comment explains rationale for background thread pattern

#### Task 2.4: Verify Context and Imports
- **Actions:**
  - Verify `asyncio` is imported at top of file
  - Check that `storage` variable is available in scope
  - Ensure error handling try/except block still wraps the call
- **Acceptance:** All context is correct, no missing imports

### Deliverables
- [ ] `utils/response.py:2218` updated with `asyncio.to_thread()` pattern
- [ ] Comments updated to explain background thread execution
- [ ] All parameters preserved from original call
- [ ] Error handling intact

### Validation
- Code compiles without errors
- All parameters match original call (except `duration_ms`)
- Comment explains fix rationale

---

## Phase 3: Add Comprehensive Tests
**Duration:** 15 minutes
**Owner:** Coder Agent
**Dependencies:** Phases 1 & 2 complete
**Status:** Pending

### Objective
Add three new tests to `tests/test_tool_calls_schema.py` to verify synchronous method, background thread execution, and thread safety.

### Tasks

#### Task 3.1: Add Test for Synchronous Method
- **Test Name:** `test_record_tool_call_sync()`
- **Purpose:** Verify synchronous SQL method works correctly
- **Implementation:**
  - Create test database and session
  - Call `storage.record_tool_call_sync()` directly (not awaited)
  - Verify row was written to `tool_calls` table
  - Assert row contains correct `tool_name`
- **Acceptance:** Test passes, SQL row verified

#### Task 3.2: Add Test for Background Thread Execution
- **Test Name:** `test_background_thread_execution()`
- **Purpose:** Verify `asyncio.to_thread()` actually executes SQL writes
- **Implementation:**
  - Create test database and session
  - Use exact pattern from `finalize_tool_response()`:
    ```python
    asyncio.create_task(asyncio.to_thread(
        storage.record_tool_call_sync, ...
    ))
    ```
  - Wait 0.1 seconds for thread to complete
  - Verify row was written to `tool_calls` table
- **Acceptance:** Test passes, proves background execution works

#### Task 3.3: Add Test for Concurrent Writes (Thread Safety)
- **Test Name:** `test_concurrent_tool_calls()`
- **Purpose:** Verify thread-safe concurrent SQL writes
- **Implementation:**
  - Create test database and session
  - Launch 10 concurrent `asyncio.to_thread()` tasks
  - Wait for all tasks to complete with `asyncio.gather()`
  - Verify all 10 rows were written (no race conditions)
- **Acceptance:** Test passes, all 10 rows written correctly

#### Task 3.4: Update Test File Structure
- **Actions:**
  - Add new tests at end of `tests/test_tool_calls_schema.py`
  - Update main test runner to include new tests
  - Add imports: `import asyncio`, `import sqlite3`
- **Acceptance:** Test file structure is clean and organized

### Deliverables
- [ ] `test_record_tool_call_sync()` test added
- [ ] `test_background_thread_execution()` test added
- [ ] `test_concurrent_tool_calls()` test added
- [ ] All tests pass independently

### Validation
- Run new tests: `pytest tests/test_tool_calls_schema.py::test_record_tool_call_sync -v`
- Run new tests: `pytest tests/test_tool_calls_schema.py::test_background_thread_execution -v`
- Run new tests: `pytest tests/test_tool_calls_schema.py::test_concurrent_tool_calls -v`
- All three tests pass with ✅ status

---

## Phase 4: Integration Testing and Validation
**Duration:** 10 minutes
**Owner:** Coder Agent
**Dependencies:** Phases 1, 2, 3 complete
**Status:** Pending

### Objective
Run full test suite and verify SQL writes occur in real tool execution scenarios.

### Tasks

#### Task 4.1: Run Full Test Suite
- **Command:** `pytest`
- **Expected:** All 69 functional tests pass (no regression)
- **Validation:**
  - No new test failures
  - No deprecation warnings
  - No event loop warnings
- **Acceptance:** Full test suite passes

#### Task 4.2: Verify SQL Writes in Integration Test
- **Actions:**
  1. Delete existing test database (fresh start)
  2. Run test suite with SQL logging enabled
  3. Inspect `tool_calls` table after tests complete
  4. Count rows in `tool_calls` table
- **Command:**
```bash
rm -f /tmp/test_tool_calls.db
pytest tests/test_tool_calls_schema.py -v
sqlite3 /tmp/test_tool_calls.db "SELECT COUNT(*) FROM tool_calls;"
```
- **Expected:** Multiple rows in `tool_calls` table (≥5)
- **Acceptance:** SQL writes are verified

#### Task 4.3: Check for Event Loop Warnings
- **Actions:**
  - Run tests with asyncio debug mode:
    ```bash
    PYTHONASYNCIODEBUG=1 pytest tests/test_tool_calls_schema.py -v
    ```
  - Check for warnings about unawaited coroutines or orphaned tasks
- **Expected:** No asyncio warnings or errors
- **Acceptance:** Clean asyncio execution

#### Task 4.4: Verify Non-Blocking Behavior
- **Actions:**
  - Add timing instrumentation to test (optional)
  - Verify tool response returns immediately (< 1ms overhead)
  - Confirm SQL writes happen in background
- **Expected:** Tool responses are immediate, SQL writes complete asynchronously
- **Acceptance:** Non-blocking behavior confirmed

### Deliverables
- [ ] Full test suite passes (no regression)
- [ ] SQL `tool_calls` table contains rows after tests
- [ ] No event loop warnings in debug mode
- [ ] Non-blocking behavior verified

### Validation
- `pytest` returns 0 exit code (all tests pass)
- `tool_calls` table has ≥5 rows
- No asyncio debug warnings
- Tool response latency unchanged

---

## Phase 5: Performance Verification
**Duration:** 10 minutes
**Owner:** Coder Agent
**Dependencies:** Phase 4 complete
**Status:** Pending

### Objective
Measure performance impact and verify implementation meets performance requirements.

### Tasks

#### Task 5.1: Measure Tool Response Latency
- **Actions:**
  - Create simple benchmark script
  - Measure 100 tool calls with background thread logging
  - Record average overhead per call
- **Expected:** < 1ms overhead per tool call
- **Acceptance:** Performance requirement met

#### Task 5.2: Verify SQL Write Latency
- **Actions:**
  - Measure time for background thread to complete SQL write
  - Record latency
- **Expected:** 1-5ms for SQL write to complete in background
- **Acceptance:** Within expected range

#### Task 5.3: Test Concurrent Write Throughput
- **Actions:**
  - Launch 100 concurrent tool calls
  - Measure total time and verify all SQL rows written
  - Calculate writes/second throughput
- **Expected:** 100+ writes/second
- **Acceptance:** Throughput exceeds expected tool call volume

#### Task 5.4: Check for Resource Leaks
- **Actions:**
  - Run tests with memory profiling (if available)
  - Check for memory leaks or resource exhaustion
  - Verify thread pool doesn't grow unbounded
- **Expected:** No memory leaks, stable resource usage
- **Acceptance:** No resource leaks detected

### Deliverables
- [ ] Tool response latency < 1ms overhead
- [ ] SQL write latency 1-5ms (background)
- [ ] Throughput ≥100 writes/second
- [ ] No memory leaks or resource exhaustion

### Validation
- Performance benchmarks meet requirements
- No resource leaks detected
- Thread pool operates within expected bounds

---

## Critical Path and Dependencies

```
Phase 1 (Create Sync Method)
    ↓
Phase 2 (Update Response Utility)
    ↓
Phase 3 (Add Tests)
    ↓
Phase 4 (Integration Testing)
    ↓
Phase 5 (Performance Verification)
    ↓
Phase 6 (Final Review - bonus)
```

**Critical Path Duration:** ~60 minutes (Phases 1-5)
**Total Duration (with review):** ~70 minutes

---

## Success Criteria

**Implementation Successful If:**
- [ ] All tests pass (no regression)
- [ ] SQL `tool_calls` table receives rows for every tool execution
- [ ] Tool response latency < 1ms overhead (non-blocking)
- [ ] No event loop warnings or orphaned task errors
- [ ] Performance benchmarks meet requirements
- [ ] Code review passes (≥93% grade)
- [ ] Clean shutdown with all pending writes completed

**Ready for Deployment When:**
- All phases complete
- All success criteria met
- Review Agent approval (≥93% grade)
- Implementation report complete

---

**Phase Plan Complete**
**Status:** Ready for Implementation
**Confidence:** 98%
**Next Step:** Coder Agent executes Phases 1-5

---
