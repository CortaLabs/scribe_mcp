
# 🐞 Scribe tool runtime telemetry is not queryable after tool completion — integrate-system-scribe-latency-20260616T050042Z
**Author:** Scribe
**Version:** v0.1
**Status:** RESOLVED
**Last Updated:** 2026-06-16 09:55:00 UTC

This report tracks the telemetry persistence gap that made Scribe tool runtimes unavailable after the immediate MCP response completed.

---
## Bug Overview
<!-- ID: bug_overview -->
**Bug ID:** BUG-2026-06-16-0001

**Reported By:** BugHunterAgent

**Date Reported:** 2026-06-16 05:08:30 UTC

**Severity:** MEDIUM

**Status:** RESOLVED

**Component:** runtime telemetry

**Environment:** local scribe_mcp Postgres-backed MCP server on 2026-06-16

**Customer Impact:** Operators cannot reliably answer which Scribe tools were slow after the immediate MCP response is gone. That blocks latency RCA, makes regressions hard to compare across sessions/repos, and forces ad hoc transcript or shell timing instead of durable telemetry.


---
## Description
<!-- ID: description -->
### Summary
Current runtime evidence shows Scribe tool calls can be observed in immediate MCP host wall-time output and repo-level TOOL_LOG.jsonl, but after-the-fact analytics do not provide usable runtime durations. The project-level TOOL_LOG.jsonl is absent for the active workstream, repo-level TOOL_LOG entries omit duration_ms, and read-only Postgres queries against the configured scribe.tool_calls table returned zero recent rows. Source inspection also shows finalize_tool_response passes duration_ms=...

### Expected Behaviour
Tool runtime telemetry should persist a correlation key, tool name, status, response size, and measured duration so recent tool runtimes can be queried after the immediate MCP response is gone.

### Actual Behaviour
Current runtime evidence shows Scribe tool calls can be observed in immediate MCP host wall-time output and repo-level TOOL_LOG.jsonl, but after-the-fact analytics do not provide usable runtime durations. The project-level TOOL_LOG.jsonl is absent for the active workstream, repo-level TOOL_LOG entries omit duration_ms, and read-only Postgres queries against the configured scribe.tool_calls table returned zero recent rows. Source inspection also shows finalize_tool_response passes duration_ms=...

### Steps to Reproduce
- [ ] Call Scribe tools in the active project, such as append_entry, read_recent, and manage_docs quality_check.
- [ ] Inspect .scribe/logs/TOOL_LOG.jsonl for recent entries; entries contain tool_name/status/response_size but no duration_ms.
- [ ] Run scribe logs analyze on the active PROGRESS_LOG.md; timing_envelope reports unknown timing fields.
- [ ] Query the configured Postgres scribe.tool_calls table for recent rows/duration_ms; the read-only query returned zero rows for the last two hours in this environment.
- [ ] Inspect src/scribe_mcp/utils/formatters/dispatcher.py lines 233-245; record_tool_call_sync is scheduled with duration_ms=None.



---
## Investigation
<!-- ID: investigation -->
**Root Cause Analysis:**
The generic finalize_tool_response path does not measure elapsed tool duration and explicitly sends duration_ms=None to storage.record_tool_call_sync. In this observed runtime, the configured Postgres tool_calls table also did not receive recent rows, so there may be an additional target mismatch or background write path gap.

**Affected Areas:**
- src/scribe_mcp/utils/formatters/dispatcher.py
- src/scribe_mcp/utils/tool_logger.py
- src/scribe_mcp/storage/postgres/__init__.py
- src/scribe_mcp/log_intelligence.py


**Related Issues:**
- Link to related bugs, tickets, or documentation.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Actions
Fix landed with status: **resolved**

### Fix Details
- Artifact: src/scribe_mcp/utils/formatters/dispatcher.py:214; src/scribe_mcp/utils/tool_logger.py; src/scribe_mcp/storage/postgres/__init__.py; tests/test_dispatcher.py; tests/test_tool_calls_schema.py
- Execution ID: 18eabb5e-4710-45c2-86ea-16c12dfbb618
- Verification: Popper bug-hunter audit plus focused telemetry suites confirmed durable duration, correlation_id, measurement_scope, TOOL_LOG, and SQL scheduling are populated.


---
## Timeline & Ownership
<!-- ID: timeline -->
| Phase | Owner | Target Date | Notes |
| --- | --- | --- | --- |
| Investigation | [Name] | [Date] | [Details] |
| Fix Development | [Name] | [Date] | [Details] |
| Testing | [Name] | [Date] | [Details] |
| Deployment | [Name] | [Date] | [Details] |


---
## Appendix
<!-- ID: appendix -->
- **Fix Reference:** src/scribe_mcp/utils/formatters/dispatcher.py:214; src/scribe_mcp/utils/tool_logger.py; src/scribe_mcp/storage/postgres/__init__.py; tests/test_dispatcher.py; tests/test_tool_calls_schema.py (execution: 18eabb5e-4710-45c2-86ea-16c12dfbb618)
- **Landing Status:** resolved
- **Fix Linked By:** seshat


---
