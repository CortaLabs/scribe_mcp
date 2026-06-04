
# ✅ Acceptance Checklist — scribe_mcp_bug_log_tooling_20260604
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-06-04 01:38:18 UTC

> Acceptance checklist for scribe_mcp_bug_log_tooling_20260604.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] <!-- id: docs-architecture-ready --> `ARCHITECTURE_GUIDE` documents the combination authority model, the chosen resolver-first solution, rejected mirroring, file boundaries, payload contract, and safety invariants with source-backed references. | proof=ARCHITECTURE_GUIDE sections architecture_overview, detailed_design, data_storage, testing_strategy, and references_appendix now define the combination authority model, resolver-first solution, rejected mirroring, payload contract, file boundaries, and safety invariants.
- [x] <!-- id: docs-phase-ready --> `PHASE_PLAN` and `CHECKLIST` describe one bounded implementation package with explicit files, out-of-scope boundaries, and exact verification commands. | proof=PHASE_PLAN sections phase_overview, phase_0, and milestone_tracking plus CHECKLIST sections phase_0, phase_1, phase_2, and final_verification now define one bounded implementation package, explicit owned/forbidden files, and exact pytest verification commands.
## Phase 0
<!-- ID: phase_0 -->
- [x] <!-- id: p0-runtime-resolution --> Implement first-class case-report resolution in `manage_docs` so BUG/SEC follow-up mutations can start from `doc_name`, BUG/SEC `case_id`, or returned governed report path, while still ending on a canonical registered key. Proof: `src/scribe_mcp/doc_management/runtime.py` resolves case-report references after the initial `resolve_registered_doc_key` step and before mutation dispatch; `tests/test_manage_docs_target_resolution.py::test_bug_report_resolution_accepts_case_id_governed_path_and_canonical_alias` and `::test_security_report_resolution_accepts_case_id_governed_path_and_canonical_alias` passed inside `pytest -q tests/test_manage_docs_target_resolution.py tests/test_case_registry_registration.py`.
- [x] <!-- id: p0-open-payload --> Extend `open_bug` and `open_security` success payloads additively with `doc_name`, `doc_path`, `doc_category`, and `case_registry`, while preserving current fields and `doc_name == case_id` for Sentinel-opened cases. Proof: `tests/test_sentinel_tools.py` opener happy-path assertions passed in `pytest -q tests/test_sentinel_tools.py -k "open_bug or open_security or link_fix"`.
- [x] <!-- id: p0-coherence --> Preserve shared-registry coherence: `list_open_cases` and `link_fix` still rely on the same `doc_name` and `doc_path` identity with active repo/project scope enforcement. Proof: `pytest -q tests/test_case_registry_ownership.py tests/test_list_open_cases.py` passed.
- [x] <!-- id: p0-tests --> Add focused bug/security parity regressions for opener payloads and `manage_docs replace_section` follow-up behavior, including canonical `bugs` / `security` alias resolution. Proof: new assertions in `tests/test_manage_docs_target_resolution.py`, `tests/test_case_registry_ownership.py`, and `tests/test_sentinel_tools.py`; all required pytest commands passed after the post-review coverage fix.
## Phase 1
<!-- ID: phase_1 -->
- [x] <!-- id: p1-owned-files --> Restrict implementation edits to the bounded package files: `src/scribe_mcp/doc_management/runtime.py`, `src/scribe_mcp/doc_management/utils.py`, `src/scribe_mcp/tools/sentinel_tools.py`, `tests/test_manage_docs_target_resolution.py`, `tests/test_case_registry_ownership.py`, and `tests/test_sentinel_tools.py`. Proof: `git status --short` shows only those six package files modified.
- [x] <!-- id: p1-forbidden-files --> Do not edit generated instruction surfaces, repo-root bug/security docs by hand, or template sources under `src/scribe_mcp/templates/documents/` unless a new Blueprint revision explicitly authorizes them. Proof: no generated instruction surfaces, repo-root case docs, or template sources appear in `git status --short`.
- [x] <!-- id: p1-out-of-scope --> Do not add report mirroring, new tool names, schema changes, or unrelated `list_open_cases` / `link_fix` feature work while implementing Package 0.1. Proof: implementation changed only resolver/payload surfaces and focused tests; no schema/tool/template/list_open_cases edits were made.
## Phase 2
<!-- ID: phase_2 -->
- [x] <!-- id: p2-verify-resolution --> `pytest -q tests/test_manage_docs_target_resolution.py tests/test_case_registry_registration.py` passes after the resolver coverage fix. Proof: 10 passed in 11.33s.
- [x] <!-- id: p2-verify-coherence --> `pytest -q tests/test_case_registry_ownership.py tests/test_list_open_cases.py` passes, proving ownership and list-open coherence were preserved. Proof: 11 passed in 0.47s.
- [x] <!-- id: p2-verify-openers --> `pytest -q tests/test_sentinel_tools.py -k "open_bug or open_security or link_fix"` passes, proving bug/security opener parity and follow-up guidance. Proof: 28 passed, 1 deselected in 0.55s.
## Final Verification
<!-- ID: final_verification -->
- [x] <!-- id: final-package-pass --> Package 0.1 lands with all targeted pytest commands passing and no forbidden files modified. Proof: all three required pytest commands passed after the post-review test coverage fix; `git diff --check` passed; `git status --short` shows the existing six package files plus managed docs updated for proof.
- [x] <!-- id: final-runtime-contract --> `open_bug` and `open_security` return explicit follow-up handles, and `manage_docs replace_section` can consume them without shell/path guesswork. Proof: opener tests assert `doc_name`, `doc_path`, `doc_category`, and `case_registry`; target-resolution tests replace BUG and SEC report sections by case ID using canonical `bugs` / `security` aliases and by governed report path.
- [x] <!-- id: final-coherence --> `list_open_cases` and `link_fix` remain coherent with the shared registry authority model after implementation. Proof: `pytest -q tests/test_case_registry_ownership.py tests/test_list_open_cases.py` passed.
- [x] <!-- id: final-review-ready --> Crucible or equivalent validation can review one clean implementation package without mirror docs, template churn, or hidden scope expansion. Proof: the post-review fix modified only `tests/test_manage_docs_target_resolution.py` and managed proof docs; no report mirroring, template edits, schema changes, generated-surface edits, or `list_open_cases` semantic edits were made.
