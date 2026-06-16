
# 🐞 Probe exits with unobserved asyncpg telemetry task exceptions — integrate-system-scribe-latency-20260616T050042Z
**Author:** Scribe
**Version:** v0.1
**Status:** RESOLVED
**Last Updated:** 2026-06-16 09:55:00 UTC

This report tracks the asyncpg/asyncio shutdown warning path that made successful local probes look dirty.

---
## Bug Overview
<!-- ID: bug_overview -->
Local direct/probe runs return successful tool results but emit shutdown telemetry warnings on stderr. This makes the latency/probe proof surface noisy and untrustworthy: operators cannot distinguish a clean probe from a run that leaked background SQL telemetry work or lost asyncpg connection-close errors.

Customer impact: local operators and CI-style probes see successful JSON output alongside asyncio/asyncpg errors, blocking reliable validation and release closeout for the latency workstream.


---
## Description
<!-- ID: description -->
### Summary
Local scribe_probe direct runs complete with ok=true JSON but emit asyncio Future exception was never retrieved and asyncpg.exceptions.ConnectionDoesNotExistError during shutdown after SQL telemetry background tasks are scheduled.

### Expected Behaviour
Background telemetry tasks are drained or observed before local/probe process exit, so stderr contains no unhandled asyncio future/asyncpg shutdown warnings and JSON output remains valid.

### Actual Behaviour
Local scribe_probe direct runs complete with ok=true JSON but emit asyncio Future exception was never retrieved and asyncpg.exceptions.ConnectionDoesNotExistError during shutdown after SQL telemetry background tasks are scheduled.

### Steps to Reproduce
- [ ] Run uv run python -m scribe_mcp.scripts.scribe_probe --tools set_project,append_entry,read_recent --project integrate-system-scribe-latency-20260616T050042Z --agent GaussProbe --root /home/austin/projects/MCP_SPINE/scribe_mcp --message probe-before-background-drain --status info --json-output
- [ ] Observe ok=true JSON on stdout plus asyncio Future exception was never retrieved / asyncpg ConnectionDoesNotExistError on stderr.



---
## Investigation
<!-- ID: investigation -->
Root cause:

Anonymous background telemetry tasks were originally a lifecycle problem: unnamed scheduled tasks could finish after tool output, and direct probe cleanup did not always drain server background tasks before closing runtime resources. That created a release-blocking stderr surface where otherwise successful local scripts emitted `Future exception was never retrieved` with asyncpg `ConnectionDoesNotExistError`.

The follow-up coordinator failure exposed a second related direct-runtime gap: `set_project` fast reuse was only proven for requests with an execution context. Direct local Python calls import the tool without running server startup, so `agent_context_manager`/`agent_identity` stayed uninitialized and the fast path had no session/binding proof. Lazily initializing the existing agent context services and keeping agent-session ids out of router-only session tables lets direct scripts reuse the same agent/project/root binding without duplicate persistent writes.

Current proof:

A direct no-handler Python double-bind probe against the edited runtime returned second-call `side_effects.binding_reused=true`, `binding_reuse_reason=same_agent_session_project_root`, skipped writes including `ensure_documents`, `upsert_project`, `agent_context_manager`, `state_set_current_project`, and `upsert_agent_recent`, and emitted no `Future exception was never retrieved` / no asyncpg `ConnectionDoesNotExistError` stderr text.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Actions
Fix landed with status: **resolved**

### Fix Details
- Artifact: src/scribe_mcp/server.py; src/scribe_mcp/tools/set_project.py; src/scribe_mcp/state/agent_manager.py; tests/test_set_project.py; docs/bugs/runtime/2026-06-16_BUG-2026-06-16-0004/report.md
- Execution ID: 18eabb5e-4710-45c2-86ea-16c12dfbb618
- Verification: Direct structured double-bind probes and focused probe/background tests emitted no `Future exception was never retrieved` or asyncpg `ConnectionDoesNotExistError` warning text.


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
- **Fix Reference:** src/scribe_mcp/server.py; src/scribe_mcp/tools/set_project.py; src/scribe_mcp/state/agent_manager.py; tests/test_set_project.py; tests/test_scribe_probe.py (execution: 18eabb5e-4710-45c2-86ea-16c12dfbb618)
- **Landing Status:** resolved
- **Fix Linked By:** seshat


---
