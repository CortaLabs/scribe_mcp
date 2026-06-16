
# 🐞 P1 telemetry persistence under-reports tool runtime and fails validation proof — integrate-system-scribe-latency-20260616T050042Z
**Author:** Scribe
**Version:** v0.1
**Status:** INVESTIGATING
**Last Updated:** 2026-06-16 06:09:29 UTC

> Summarise why this document exists and what decisions it captures.

---
## Bug Overview
<!-- ID: bug_overview -->
Customer impact: Scribe telemetry would appear durable but materially under-report real tool runtime for key calls such as `set_project`, `append_entry`, and `read_recent`. That would make latency audits misleading, hide slow tool phases, and allow downstream optimization decisions to be based on formatter-time rather than actual tool execution time. The validation failure also blocks this workstream's dependent packages until fixed and revalidated.


---
## Description
<!-- ID: description -->
### Summary
P1 Crucible validation blocked at 68/100. Persisted duration_ms is measured from formatter/finalization boundary instead of full tool execution start for key tools. Plan-named test command fails, and fresh SQLite readback probe fails with sqlite3.OperationalError no such column: status.

### Expected Behaviour
Generic tool telemetry should persist real full tool execution duration and correlation metadata, focused and plan-named tests should reproduce passing, and fresh readback probe should verify TOOL_LOG and tool_calls rows with matching correlation IDs.

### Actual Behaviour
P1 Crucible validation blocked at 68/100. Persisted duration_ms is measured from formatter/finalization boundary instead of full tool execution start for key tools. Plan-named test command fails, and fresh SQLite readback probe fails with sqlite3.OperationalError no such column: status.

### Steps to Reproduce
- [ ] Run uv run pytest tests/test_doctor_telemetry.py tests/test_log_intelligence.py tests/test_tools.py and observe tests/test_tools.py::test_set_and_get_project_roundtrip failure.
- [ ] Inspect dispatcher duration source and key tool call sites; set_project, append_entry, and read_recent do not pass execution-start telemetry into finalize_tool_response.
- [ ] Run a fresh SQLite-backed set_project/append_entry/read_recent probe and observe sqlite3.OperationalError no such column: status during storage setup.



---
## Investigation
<!-- ID: investigation -->
**Root Cause Analysis:**
P1 implementation measured formatter/finalization elapsed time rather than threading actual tool execution start or full duration from call sites; validation also exposed stale or incomplete local SQLite schema setup and set_project doc-generation failure.

**Affected Areas:**
- src/scribe_mcp/utils/formatters/dispatcher.py
- src/scribe_mcp/tools/set_project.py
- src/scribe_mcp/tools/append_entry.py
- src/scribe_mcp/tools/read_recent.py
- tests/test_tools.py


**Related Issues:**
- Link to related bugs, tickets, or documentation.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Actions
Fix landed with status: **validated**

### Fix Details
- Artifact: .scribe/docs/dev_plans/integrate_system_scribe_latency_20260616t050042z/REVIEW_REPORT_post_implementation_review_2026-06-16_0621.md
- Execution ID: 80903aa5-d7ae-40b4-b90f-d4e2700b2ace


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
- **Fix Reference:** .scribe/docs/dev_plans/integrate_system_scribe_latency_20260616t050042z/REVIEW_REPORT_post_implementation_review_2026-06-16_0621.md (execution: 80903aa5-d7ae-40b4-b90f-d4e2700b2ace)
- **Landing Status:** validated
- **Fix Linked By:** seshat


---