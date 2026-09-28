---
visibility: "internal"
owner_principal_id: "seshat"
council_id: ""
project_id: "scribe_binding_reliability_repair_20260927"
required_grants: []
revoked_at: null
policy_digest: "a259769ff3ce41868cc2b9197150e77f432f089221dbd230074f683f7450e107"
---


# 🐞 scribe_probe import mutates SCRIBE_ROOT and breaks fail-closed validation — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** INVESTIGATING
**Last Updated:** 2026-09-27 21:20:42 UTC

> Summarise why this document exists and what decisions it captures.

---
## Bug Overview
<!-- ID: bug_overview -->
**Bug ID:** BUG-2026-09-27-0009

**Reported By:** seshat

**Date Reported:** 2026-09-27 21:20:42 UTC

**Severity:** HIGH

**Status:** INVESTIGATING

**Component:** startup probe and execution-context validation

**Environment:** local test suite

**Customer Impact:** Release validation can report false failures or silently weaken repository-root validation depending on import order.


---
## Description
<!-- ID: description -->
### Summary
Collecting tests/test_release_startup_probe.py imports scribe_mcp.scripts.scribe_probe, whose module top level sets SCRIBE_ROOT. A relative ProjectTargetV1 repo_root that must raise ValueError is then remapped to an absolute workspace and accepted. The standalone execution-context suite passes, while the combined changed-surface suite fails deterministically.

### Expected Behaviour
Importing any Scribe module must not mutate process-wide repository identity. Relative repository roots must fail closed regardless of test collection order.

### Actual Behaviour
Collecting tests/test_release_startup_probe.py imports scribe_mcp.scripts.scribe_probe, whose module top level sets SCRIBE_ROOT. A relative ProjectTargetV1 repo_root that must raise ValueError is then remapped to an absolute workspace and accepted. The standalone execution-context suite passes, while the combined changed-surface suite fails deterministically.

### Steps to Reproduce
- [ ] Run ./.venv/bin/pytest -x -vv tests/test_execution_context.py tests/test_release_startup_probe.py
- [ ] Observe test_project_target_v1_rejects_invalid_selectors[kwargs3-ValueError] does not raise.
- [ ] Run tests/test_execution_context.py alone and observe 94/94 pass.



---
## Investigation
<!-- ID: investigation -->
**Root Cause Analysis:**
src/scribe_mcp/scripts/scribe_probe.py executes os.environ.setdefault('SCRIBE_ROOT', str(REPO_ROOT)) at module import. pytest imports all selected modules during collection, so the release-startup module changes later path mapping before execution-context assertions run.

**Affected Areas:**
- src/scribe_mcp/scripts/scribe_probe.py
- src/scribe_mcp/shared/execution_context.py
- tests/test_release_startup_probe.py
- tests/test_execution_context.py


**Related Issues:**
- Link to related bugs, tickets, or documentation.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Actions
- [ ] Route through Mantis after Council exact-seat recovery. Remove import-time environment mutation and add a collection-order regression that preserves fail-closed relative-root validation.


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