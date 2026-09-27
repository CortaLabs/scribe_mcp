---
visibility: "internal"
owner_principal_id: "seshat"
council_id: ""
project_id: "scribe_binding_reliability_repair_20260927"
required_grants: []
revoked_at: null
policy_digest: "a259769ff3ce41868cc2b9197150e77f432f089221dbd230074f683f7450e107"
---


# 🐞 Execution-context test leaves state that hangs subsequent actor binding resolution — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** INVESTIGATING
**Last Updated:** 2026-09-27 21:21:02 UTC

> Summarise why this document exists and what decisions it captures.

---
## Bug Overview
<!-- ID: bug_overview -->
**Bug ID:** BUG-2026-09-27-0010

**Reported By:** seshat

**Date Reported:** 2026-09-27 21:21:01 UTC

**Severity:** HIGH

**Status:** INVESTIGATING

**Component:** execution context, state manager, and actor-scoped binding tests

**Environment:** local pytest asyncio strict mode

**Customer Impact:** The release gate can hang indefinitely and report misleading split-suite green status, obscuring binding regressions and consuming worker capacity.


---
## Description
<!-- ID: description -->
### Summary
A minimal ordered two-test run passes test_get_execution_context_prefers_runtime_context_over_bootstrap_state, then hangs indefinitely in test_explicit_project_override_in_verified_repo_root_is_honored while awaiting resolve_logging_context. The actor test passes alone. A 25-second timeout with faulthandler reproduced the hang; the main thread remained in the asyncio loop and a ThreadPoolExecutor worker was idle.

### Expected Behaviour
Execution-context tests must fully restore server/global/contextvar and event-loop state. Actor-scoped binding resolution must complete independently of earlier test order.

### Actual Behaviour
A minimal ordered two-test run passes test_get_execution_context_prefers_runtime_context_over_bootstrap_state, then hangs indefinitely in test_explicit_project_override_in_verified_repo_root_is_honored while awaiting resolve_logging_context. The actor test passes alone. A 25-second timeout with faulthandler reproduced the hang; the main thread remained in the asyncio loop and a ThreadPoolExecutor worker was idle.

### Steps to Reproduce
- [ ] Run timeout 25s ./.venv/bin/pytest -vv -o faulthandler_timeout=8 tests/test_execution_context.py::test_get_execution_context_prefers_runtime_context_over_bootstrap_state tests/shared/test_actor_scoped_session_binding.py::test_explicit_project_override_in_verified_repo_root_is_honored
- [ ] Observe the first node pass and the second node hang until timeout.
- [ ] Run the actor-scoped node alone and observe it pass.



---
## Investigation
<!-- ID: investigation -->
**Root Cause Analysis:**
Unproven. The minimal predecessor imports and temporarily mutates scribe_mcp.server execution context; the following actor-resolution path then waits indefinitely. Mantis must prove whether a global ContextVar, app-state, StateManager, background task, or loop-bound resource is retained.

**Affected Areas:**
- src/scribe_mcp/shared/execution_context.py
- src/scribe_mcp/shared/logging_utils.py
- src/scribe_mcp/state/manager.py
- tests/test_execution_context.py
- tests/shared/test_actor_scoped_session_binding.py


**Related Issues:**
- Link to related bugs, tickets, or documentation.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Actions
- [ ] Route through Mantis after Council exact-seat recovery. Require a reproduction test, proven causal state path, surgical cleanup/fix, and a combined-order regression before accepting split-suite results.


### Long-Term Fixes
- [ ] Outline long-term remedial work or refactors.

### Testing Strategy
- [ ] Define validation steps for the fix (unit, integration, regression).


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
- **Logs & Evidence:** [Link to relevant logs, traces, screenshots]
- **Fix References:** [Git commits, PRs, or documentation]
- **Open Questions:** [List unresolved unknowns or next investigations]


---