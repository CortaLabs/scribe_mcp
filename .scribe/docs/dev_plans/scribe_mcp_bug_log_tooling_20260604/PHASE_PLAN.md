
# ⚙️ Phase Plan — scribe_mcp_bug_log_tooling_20260604
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-06-04 01:38:18 UTC

> Execution roadmap for scribe_mcp_bug_log_tooling_20260604.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence |
| --- | --- | --- | --- |
| Phase 0 | Add first-class case-report follow-up resolution without changing authority surfaces | `manage_docs` case-report resolver, explicit opener follow-up payload handles, focused bug/security regressions | 0.93 |

This plan intentionally authorizes one implementation phase. Split only if the coder proves the runtime resolver and opener payload work cannot land safely in one bounded pass.
## Phase 0 — Define First Implementation Slice
<!-- ID: phase_0 -->
**Objective:** Make BUG/SEC follow-up edits source-backed and obvious by resolving case-report identifiers through existing registry/report authority instead of introducing mirrored docs or path workarounds.

### Task Package: 0.1 — Case-Report Resolution And Payload Clarity
**Scope:** Add first-class `manage_docs` case-report resolution and normalize `open_bug` / `open_security` success payloads so one coder can complete the full slice safely.

**Files to Modify:**
- `src/scribe_mcp/doc_management/runtime.py` — insert the case-report resolution hook before mutation dispatch, normalize accepted case-report category aliases, and re-bind resolved case docs to canonical registered keys.
- `src/scribe_mcp/doc_management/utils.py` — add shared helper logic for scoped case-registry lookup, governed report discovery fallback, and report-path safety validation.
- `src/scribe_mcp/tools/sentinel_tools.py` — add explicit follow-up fields (`doc_name`, `doc_path`, `doc_category`, `case_registry`) to opener success payloads and update guidance text to point at the canonical handle.
- `tests/test_manage_docs_target_resolution.py` — cover case ID, returned path, and category-alias resolution, including BUG `bugs` and SEC `security` aliases.
- `tests/test_case_registry_ownership.py` — confirm registry ownership and `link_fix` coherence survive the resolver changes.
- `tests/test_sentinel_tools.py` — cover bug/security opener payload parity and follow-up guidance.

**Dependencies:**
- Requires the verified research artifacts already present in `research/`.
- Requires no template or schema work; if implementation suggests either, stop and escalate instead of widening the slice.

**Specifications:**
1. Keep `resolve_registered_doc_key` as the first resolution step; do not bypass the existing registration-gated mutation path.
2. When a caller supplies a BUG/SEC case reference that is not already canonicalized, resolve it through active repo/project registry data first, then governed report discovery, then map the answer back to a registered doc key.
3. Preserve `doc_name == case_id` for newly opened Sentinel cases and keep registry `doc_path` aligned with the governed report file.
4. Extend `open_bug` and `open_security` success payloads additively. Existing keys remain valid; new keys provide the preferred follow-up contract.
5. Do not modify `list_open_cases` semantics or `link_fix` ownership rules; only adjust shared resolution/payload surfaces needed for coherence.

**Patterns to Follow:**
- Match project-scoped registry behavior in `src/scribe_mcp/tools/list_open_cases.py` and `src/scribe_mcp/tools/sentinel_tools.py`.
- Reuse governed report classification/resolution patterns already present in `src/scribe_mcp/doc_management/utils.py`.
- Keep writes inside the existing `manage_docs` -> runtime -> `apply_doc_change` flow.

**Verification:**
- [x] `pytest -q tests/test_manage_docs_target_resolution.py tests/test_case_registry_registration.py` -> 10 passed in 11.33s.
- [x] `pytest -q tests/test_case_registry_ownership.py tests/test_list_open_cases.py` -> 11 passed in 0.47s.
- [x] `pytest -q tests/test_sentinel_tools.py -k "open_bug or open_security or link_fix"` -> 28 passed, 1 deselected in 0.55s.
- [x] `git diff --check` -> passed.

**Out of Scope:**
- No report mirroring.
- No template edits under `src/scribe_mcp/templates/documents/`.
- No generated instruction-surface edits.
- No new tool names, schema changes, or unrelated case-registry refactors.
## Phase 1 — Next Bounded Slice
<!-- ID: phase_1 -->
No second implementation phase is approved in this blueprint. If the coder discovers that the runtime resolver and opener payload work cannot land safely together, stop, log the coupling evidence, and return to Blueprint rather than improvising a second package.
## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
| --- | --- | --- | --- | --- |
| Research gate verified | 2026-06-04 | Research + Orchestrator | Done | Verified research artifacts in `research/` plus recent Scribe gate entries |
| Blueprint contract ready | 2026-06-04 | ArchitectAgent | Done | `ARCHITECTURE_GUIDE` sections `architecture_overview`, `detailed_design`, `testing_strategy`; `PHASE_PLAN` section `phase_0`; `CHECKLIST` phase items |
| Package 0.1 implemented and validated | 2026-06-04 | Scribe Coder | Done | Implemented resolver/payload changes in the six allowed files, then resolved the post-review blocking test gap by adding BUG `bugs` alias and SEC `security` alias follow-up mutation coverage in `tests/test_manage_docs_target_resolution.py`. Verification: `pytest -q tests/test_manage_docs_target_resolution.py tests/test_case_registry_registration.py` -> 10 passed in 11.33s; `pytest -q tests/test_case_registry_ownership.py tests/test_list_open_cases.py` -> 11 passed in 0.47s; `pytest -q tests/test_sentinel_tools.py -k "open_bug or open_security or link_fix"` -> 28 passed, 1 deselected in 0.55s; `git diff --check` -> passed. |

Architecture milestone and Package 0.1 implementation are complete. The post-review blocking test-sufficiency finding is resolved for the coder handoff; the next legal step is package-specific validation/review before any dependent package is routed.
## Retro Notes & Adjustments
<!-- ID: retro_notes -->
- Blueprint confirmed that the right fix is resolver and payload alignment, not report mirroring.
- Research and source verification both showed the templates are already sufficient, so template churn is intentionally excluded.
- Any implementation attempt that requires schema work, template edits, or mirrored docs should be treated as a new planning event rather than absorbed into Package 0.1.
