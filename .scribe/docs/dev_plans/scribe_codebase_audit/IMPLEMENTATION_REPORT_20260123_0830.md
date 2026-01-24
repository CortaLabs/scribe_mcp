---
id: scribe_codebase_audit-implementation-report-20260123-0830
title: 'Implementation Report: Phase 6 Task 6.1 - Lazy Journal Replay'
doc_name: IMPLEMENTATION_REPORT_20260123_0830
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-23'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Implementation Report: Phase 6 Task 6.1 - Lazy Journal Replay

**Date:** 2026-01-23 08:30 UTC
**Agent:** CoderAgent-Phase6-LazyJournal
**Project:** scribe_codebase_audit

## Summary

Moved journal replay from blocking server startup to a non-blocking background task. The server now starts immediately and can respond to tool calls while journals are replayed in the background.

## Problem Statement

Previously, journal replay happened synchronously during `_startup()`, which could delay server readiness when there were many projects or journals to scan. Users had to wait for journal recovery to complete before tools became available.

## Solution

1. **Created `_replay_journals_background()` async function** (lines 667-749)
   - Contains all journal replay logic from original `_startup()`
   - Handles both project-based recovery (Method 1) and orphaned journal scan (Method 2)
   - Sets `_journal_replay_complete` flag when done (even on failure)
   - Graceful error handling - server continues even if replay fails

2. **Added `_journal_replay_complete` tracking flag** (line 114)
   - Boolean flag to track background replay status
   - Can be queried to check if replay is complete

3. **Updated `_startup()` to use background task** (lines 878-881)
   - Replaced 72 lines of inline journal replay code
   - Now uses `schedule_background_task(_replay_journals_background())`
   - Server reports ready immediately after scheduling

4. **Fixed missing agent parameter** (line 692)
   - Added `agent='__scribe_internal__'` to `list_projects()` call
   - Required for session isolation compliance

## Files Changed

| File | Changes |
|------|--------|
| `server.py` | Added `_journal_replay_complete` flag, created `_replay_journals_background()` function, replaced inline replay code with background task call, fixed agent parameter |

## Code Metrics

- Lines added: ~85 (new function + flag)
- Lines removed: ~72 (inline replay code in _startup)
- Net: Cleaner separation of concerns

## Tests

- [x] Module import test passed
- [x] Background function executes without error
- [x] `_journal_replay_complete` flag set correctly
- [x] All 28 dispatcher tests pass (no regression)

## Verification

```bash
# Import test
python -c "from server import _replay_journals_background, _journal_replay_complete; print('OK')"

# Background function test
python -c "import asyncio; from server import _replay_journals_background; asyncio.run(_replay_journals_background())"

# Regression tests
python -m pytest tests/test_dispatcher.py -v  # 28 passed
```

## Notes

- Uses existing `schedule_background_task()` infrastructure for proper task lifecycle management
- Background task cleanup is handled automatically via `add_done_callback`
- Error handling ensures server operates normally even if replay fails
- The `__scribe_internal__` agent name is used for internal server operations

## Confidence Score

**0.95** - High confidence. Change is minimal and focused. Uses existing patterns. All tests pass. No architectural changes.

## Follow-up Considerations

- Consider adding a health endpoint to check `_journal_replay_complete` status
- Could add metrics for replay duration/entry count to monitor performance
