
# 🏗️ Architecture Guide — scribe_mcp_bug_log_tooling_20260604
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-06-04 01:38:18 UTC

> Architecture guide for scribe_mcp_bug_log_tooling_20260604.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
### Context
`open_bug` and `open_security` already create governed case reports under repo-root `docs/bugs/.../report.md` or `docs/security/.../report.md`, register those artifacts in the active project docs mapping, and upsert shared case-registry rows. The friction is not document creation or template shape. It is that follow-up `manage_docs` mutations are still optimized around already-registered document keys and a limited custom-category resolver, while BUG/SEC users naturally think in `case_id`, returned report path, or bug/security category terms.

### Goals
- Make follow-up `manage_docs` edits source-backed and obvious after `open_bug` and `open_security`.
- Preserve the current combination authority model: project log for case allocation, governed repo-root report for narrative content, and shared case registry for operational authority.
- Keep `list_open_cases` and `link_fix` coherent by preserving registry `doc_name`/`doc_path` truth.
- Add bug/security parity regressions for the exact friction, not broad unrelated coverage.

### Non-Goals
- No shell-edited bug/security docs.
- No report mirroring into `.scribe/docs/dev_plans/...`.
- No generated `AGENTS.md`, `CLAUDE.md`, `.claude/`, or `.codex/` edits.
- No template source edits unless source proof shows missing anchors or missing special-create behavior.

### Success Metrics
- A caller can take the success payload from `open_bug` or `open_security` and perform `manage_docs(action='replace_section', ...)` using an explicit returned handle.
- `manage_docs` can resolve scoped BUG/SEC case-report identifiers without weakening path safety.
- `link_fix` and `list_open_cases` continue to use the same registry-backed case identity and do not need compensating mirror logic.
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->
### Functional Requirements
- `manage_docs` must accept case-report follow-up handles that are already emitted or implied by source truth: registered `doc_name`, BUG/SEC `case_id`, and governed report path aliases that can be mapped back to a registered key.
- `open_bug` and `open_security` must return explicit follow-up identifiers without removing existing fields such as `case_id`, `artifacts`, `bug_report`/`security_report`, `completeness`, and `action_required`.
- Bug and security flows must stay behaviorally symmetric.
- `list_open_cases` and `link_fix` must continue to rely on shared registry `doc_name` and `doc_path` values.

### Non-Functional Requirements
- Keep the change bounded to existing runtime/tooling surfaces; no parallel document system and no mirroring job.
- Preserve the current project-root sandbox and section-anchor enforcement.
- Keep the implementation small enough for one coder pass with focused regression coverage.

### Assumptions
- Active project mode is already bound via `set_project`, so runtime/project resolution is authoritative for writes.
- Shared case-registry queries remain available in the same backend already used by `list_open_cases` and `link_fix`.
- The bug/security templates remain sufficient because their required anchors already exist.

### Risks And Mitigations
- Registry drift or missing rows: prefer registry-backed resolution for case IDs, but fall back to governed report discovery only inside the active repo root and only after re-binding to a registered doc key.
- Category alias ambiguity: normalize aliases such as `bug`, `bugs`, `bug_report`, `security`, and `security_report` to a canonical case-report resolver before mutation.
- Safety regression from path-based edits: never mutate a resolved path directly; every successful resolution must end as a canonical registered doc key routed back through existing `apply_doc_change` safeguards.
## 3. Architecture Overview
<!-- ID: architecture_overview -->
### APPROACH_SUMMARY
Use first-class case-report resolution inside `manage_docs`; do not mirror case reports and do not change templates. The resolver should treat the shared case registry and the governed repo-root report tree as the two source-backed lookup surfaces for BUG/SEC follow-up edits, then map every successful lookup back to the already-registered project doc key before mutation.

### Source-Backed Authority Model
- The project progress log remains the allocation and immediate-queryability source for new BUG/SEC case IDs.
- The governed repo-root report under `docs/bugs/.../report.md` or `docs/security/.../report.md` remains the narrative artifact edited by `manage_docs`.
- The shared case registry remains the operational authority for `list_open_cases`, ownership checks, `link_fix`, and canonical `doc_name`/`doc_path` metadata.

### Chosen Solution
1. Preserve registered doc keys as the write authority that `apply_doc_change` ultimately mutates.
2. Add a case-report resolver in the `manage_docs` runtime path that:
   - accepts `doc_name`/`doc` aliases as today,
   - recognizes BUG/SEC case IDs and case-report category aliases,
   - consults the active repo/project case registry when a case ID is supplied,
   - falls back to governed case-report discovery only within the active project root,
   - maps any resolved path back to a registered doc key, auto-registering only the safe discovered report path when needed.
3. Extend `open_bug` and `open_security` success payloads so callers receive the exact follow-up handle set required by that resolver.

### Rejected Alternatives
- **Mirroring reports into dev-plan docs:** rejected because it duplicates authority, introduces synchronization risk, and would drift from registry `doc_name`/`doc_path` values already used by `list_open_cases` and `link_fix`.
- **Template changes:** rejected because the bug/security templates already expose the needed section anchors and special-create behavior already lands reports in the governed tree.
- **Arbitrary path-based mutation:** rejected because it weakens the current sandbox and bypasses the registration model that protects `manage_docs` writes.
- **Payload-only fix with no resolver change:** rejected because it improves instructions but still leaves `manage_docs` unable to reconcile case-report identifiers consistently when callers supply a case ID, returned path, or case-report category hint.
## 4. Detailed Design
<!-- ID: detailed_design -->
### Resolver Contract
1. `manage_docs` keeps its current first step: canonicalize incoming `doc_name`/`doc` through `resolve_registered_doc_key`.
2. If the caller already supplied a registered key or a path alias that maps to one, continue unchanged.
3. If the incoming identifier still looks like a BUG/SEC case-report reference, run a dedicated case-report resolution helper before mutation:
   - normalize case-report aliases (`bug`, `bugs`, `bug_report`, `security`, `security_report`),
   - prefer active repo/project registry lookup for BUG/SEC case IDs,
   - validate the resolved registry `doc_path` stays inside the active project root,
   - map the resolved path back to a registered key with `resolve_registered_doc_key`,
   - only auto-register the resolved report path when it is a governed case-report file under the active repo root.
4. If no registry row is available, fall back to governed report discovery using existing case-report classification/path helpers.
5. The resolver returns a canonical registered key; `apply_doc_change` remains the only mutation path.

### Open-Tool Return Payload Contract
Keep all current success fields. Add the following explicit follow-up fields to both `open_bug` and `open_security` success envelopes:
- `doc_name`: canonical registered manage_docs key. For Sentinel-opened cases this remains equal to `case_id`.
- `doc_path`: absolute path to the governed report file. This should match the existing `bug_report` or `security_report` value.
- `doc_category`: canonical manage_docs case-report category alias. Use `bugs` for bug reports and `security` for security reports so the runtime resolver can recognize both flows consistently.
- `case_registry`: compact summary containing at least `case_id`, `case_type`, `doc_name`, `doc_path`, and `project_name`.

The existing `bug_report` / `security_report`, `artifacts`, `next_step`, `completeness`, and `action_required` fields stay intact. Guidance strings should reference `doc_name` as the primary handle and may mention `doc_path` as an equivalent safe alias.

### Files Likely To Change And Why
- `src/scribe_mcp/doc_management/runtime.py`
  Add the case-report resolution hook in the mutation/read path, normalize case-report category aliases, and route resolved identifiers back into the existing registration-gated mutation flow.
- `src/scribe_mcp/doc_management/utils.py`
  Add the shared case-report normalization/resolution helpers that combine registry-backed case lookup with governed report discovery and safety validation.
- `src/scribe_mcp/tools/sentinel_tools.py`
  Extend `open_bug` and `open_security` success payloads and guidance strings so callers receive explicit follow-up handles without altering the case-opening lifecycle.
- `tests/test_manage_docs_target_resolution.py`
  Add regressions proving case-report identifiers resolve through `manage_docs` using case ID, returned path, and canonical category aliases.
- `tests/test_case_registry_ownership.py`
  Preserve ownership and `link_fix` coherence while the resolver begins honoring registry-backed case identities.
- `tests/test_sentinel_tools.py`
  Add focused parity assertions for opener payload fields and bug/security follow-up edit guidance.

### Safety Invariants
- No arbitrary path editing. Every resolved report path must stay under the active project root and must be re-bound to a registered key before mutation.
- No report mirroring. Repo-root governed reports remain the only report artifact; `.scribe/docs/dev_plans/...` is not a second source of truth.
- Preserve registry coherence. Do not rename or reinterpret registry `doc_name`/`doc_path` fields in a way that breaks `list_open_cases` or `link_fix`.
- Preserve Sentinel open behavior. New BUG/SEC cases still register `doc_name == case_id` unless a deliberate multi-surface migration is planned later.
- No template or schema churn unless implementation uncovers a verified missing anchor or missing storage method, which current source evidence does not indicate.
## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```text
src/scribe_mcp/
  doc_management/
    runtime.py          # manage_docs runtime dispatch and case-report resolution hook
    utils.py            # shared case-report lookup, category normalization, and safety helpers
  tools/
    sentinel_tools.py   # open_bug/open_security payload contract updates

tests/
  test_manage_docs_target_resolution.py  # resolver regressions for case IDs, paths, and category aliases
  test_case_registry_ownership.py        # registry ownership and link_fix coherence
  test_sentinel_tools.py                 # opener payload parity and follow-up guidance regressions
```

No new directories are required. No template tree, generated instruction surfaces, or docs-mirroring folders should be introduced.
## 6. Data & Storage
<!-- ID: data_storage -->
### Authority Records
- Filesystem markdown remains the report body source: governed bug/security reports live only under repo-root `docs/bugs/.../report.md` and `docs/security/.../report.md`.
- Shared case-registry rows remain the operational source for case scope, ownership, `doc_name`, and `doc_path`.
- Project docs mapping remains the immediate mutation gate used by `manage_docs` and `apply_doc_change`.

### Data Rules
- Preserve `doc_name == case_id` for BUG/SEC cases opened through `open_bug` and `open_security`.
- Preserve registry `doc_path` as the exact governed report path.
- Do not introduce schema changes or alternate storage records for mirrored reports.
- If the resolver must auto-register a discovered case-report path, it should only update the active project's docs mapping for the canonical key and safe aliases; it should not fabricate a second report location.

### Performance And Safety
- Registry lookup should be scoped to active `repo_root` and `project_name`, matching current `list_open_cases` and `link_fix` ownership behavior.
- Governed-path fallback should remain bounded to project-local case-report directories and use existing classification helpers rather than recursive arbitrary path search.
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
### Focused Regression Strategy
- Add `manage_docs` target-resolution tests that prove a BUG/SEC case report can be addressed by returned `doc_name`, returned `doc_path`, and canonical case-report `doc_category` aliases.
- Add opener payload tests that assert both `open_bug` and `open_security` return the same follow-up contract shape, with only case-type-specific field names differing.
- Preserve existing ownership and list-open tests so registry scope and `link_fix` behavior remain stable while the resolver changes.

### Required Verification Commands
```text
pytest -q tests/test_manage_docs_target_resolution.py tests/test_case_registry_registration.py
pytest -q tests/test_case_registry_ownership.py tests/test_list_open_cases.py
pytest -q tests/test_sentinel_tools.py -k "open_bug or open_security or link_fix"
```

### Review Focus
- Confirm the resolver never mutates a raw filesystem path without re-binding it to a registered key.
- Confirm bug/security parity: both cases return explicit follow-up handles and both can complete a `replace_section` follow-up.
- Confirm no generated docs, templates, or unrelated case-registry consumers changed.
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
### Rollout Notes
- This is a runtime/tooling-only slice. No migrations, no generated-surface regeneration, and no operator workflow change outside the existing Scribe tools are planned.
- The implementation should ship behind the existing project-mode `manage_docs`, `open_bug`, and `open_security` flows; no new tool names are required.

### Implementation Gate
Implementation can proceed once the coder keeps the change inside the named files, preserves the current registry/list/link behavior, and passes the targeted regression commands listed above.

### Ownership
- `manage_docs` runtime remains the resolver owner.
- `sentinel_tools` remains the case-opening owner.
- The shared case registry remains the authority for cross-tool case identity.
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| Second implementation phase needed | Blueprint + Coder | Closed for now | Current evidence supports one bounded coder package; split only if implementation uncovers unexpected coupling beyond `runtime.py`, `utils.py`, and `sentinel_tools.py`. |
| Template changes required | Blueprint | Closed | Current source shows the required bug/security anchors already exist; no template edits are authorized in this plan. |
| Mirroring required for follow-up edits | Blueprint | Closed | Rejected by source evidence because registry plus governed report resolution is sufficient and keeps `list_open_cases` / `link_fix` coherent. |

No blocking questions remain for implementation.
## 10. References & Appendix
<!-- ID: references_appendix -->
### Required Inputs
- `SPEC_OPEN_BUG_MANAGE_DOCS.md`
- `research/RESEARCH_SENTINEL_CASE_AUTHORITY.md`
- `research/RESEARCH_MANAGE_DOCS_RESOLUTION.md`
- `research/RESEARCH_REPORT_TEMPLATES_TESTS.md`

### Primary Source Files
- `src/scribe_mcp/tools/sentinel_tools.py`
- `src/scribe_mcp/tools/list_open_cases.py`
- `src/scribe_mcp/tools/manage_docs.py`
- `src/scribe_mcp/doc_management/runtime.py`
- `src/scribe_mcp/doc_management/manager.py`
- `src/scribe_mcp/doc_management/utils.py`
- `src/scribe_mcp/doc_management/special_create.py`
- `src/scribe_mcp/templates/documents/base_document.md`
- `src/scribe_mcp/templates/documents/BUG_REPORT_TEMPLATE.md`
- `src/scribe_mcp/templates/documents/SECURITY_REPORT_TEMPLATE.md`

### Verification Targets
- `tests/test_manage_docs_target_resolution.py`
- `tests/test_case_registry_registration.py`
- `tests/test_case_registry_ownership.py`
- `tests/test_list_open_cases.py`
- `tests/test_sentinel_tools.py`

Architecture conclusion: implement first-class case-report resolution plus opener payload clarity; do not mirror reports and do not change templates.
