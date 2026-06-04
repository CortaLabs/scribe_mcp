# RESEARCH: manage_docs target resolution and edit actions

## Summary
`manage_docs` has a solid safety model for normal managed docs and for the case-report flows created by `open_bug`/`open_security`, but the edit path is still optimized around registered document keys rather than generic case-registry lookup. That means the safe follow-up identifier is usually the registered `doc_name`/path that was written into `project["docs"]`, not an arbitrary `case_id` unless that `case_id` was also registered as the doc key.

## Findings

### 1. `manage_docs` resolves edits from registered doc keys first, then canonical project paths
Confidence: high.

Evidence:
- `manage_docs` accepts both `doc_name` and `doc`, with `doc` acting as a compatibility alias when `doc_name` is omitted. See [src/scribe_mcp/tools/manage_docs.py](../../../../src/scribe_mcp/tools/manage_docs.py#L74) and [src/scribe_mcp/tools/manage_docs.py](../../../../src/scribe_mcp/tools/manage_docs.py#L118).
- In the runtime dispatcher, `doc_name` is canonicalized through `resolve_registered_doc_key(active_project, doc_name)` before mutation routing. See [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L1949).
- `resolve_registered_doc_key` accepts:
  - exact registered keys
  - case-insensitive key matches
  - basename/stem matches
  - normalized relative-path suffix matches
  - absolute-path matches when the path equals a registered value
  See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L193).
- For non-`create_doc` actions, `apply_doc_change` resolves the file via `_resolve_doc_path(project, doc_name)` and then requires the document to be registered unless the file already exists and can be auto-registered. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L318).

Implication:
- Follow-up edits are only as flexible as the keys stored in `project["docs"]`. If a report was registered under a slug or case ID, that identifier works. If it was not registered, direct mutation is rejected or falls back to a less useful generic path.

### 2. Bug/security reports are created in a case-report layout, but their manage_docs identity is the registered key, not the on-disk folder name
Confidence: high.

Evidence:
- `create_bug_report` writes to `docs/bugs/<category>/<date>_<slug>/report.md` and sets `primary_doc_key = slug`. It also registers `slug`, `doc_name` alias, and a legacy key, but not `case_id` by itself. See [src/scribe_mcp/doc_management/special_create.py](../../../../src/scribe_mcp/doc_management/special_create.py#L446).
- The bug template defines `Bug ID` from `metadata.get("slug", ...)`, not from a canonical `case_id` field. See [src/scribe_mcp/templates/documents/BUG_REPORT_TEMPLATE.md](../../../../src/scribe_mcp/templates/documents/BUG_REPORT_TEMPLATE.md#L10).
- `create_bug_report` returns `doc_name` as the slug-derived primary key. See [src/scribe_mcp/doc_management/special_create.py](../../../../src/scribe_mcp/doc_management/special_create.py#L789).
- `open_bug` and `open_security` deliberately pass `slug=case_id` and `doc_name=case_id` into `manage_docs(action="create")`, then register the case record with `doc_name=case_id`. See [src/scribe_mcp/tools/sentinel_tools.py](../../../../src/scribe_mcp/tools/sentinel_tools.py#L907) and [src/scribe_mcp/tools/sentinel_tools.py](../../../../src/scribe_mcp/tools/sentinel_tools.py#L953), plus the security flow at [src/scribe_mcp/tools/sentinel_tools.py](../../../../src/scribe_mcp/tools/sentinel_tools.py#L1202) and [src/scribe_mcp/tools/sentinel_tools.py](../../../../src/scribe_mcp/tools/sentinel_tools.py#L1248).

Implication:
- A bug/security report created by the Sentinel flow is easy to update if the caller keeps the returned `case_id`, because that value is also the registered doc key.
- A bug report created through bare `manage_docs(action="create", metadata={"doc_type": "bug", ...})` is more awkward because the file path and the visible Bug ID are slug-based, and the tool does not use the case registry as a reverse-lookup service for later edits.

### 3. There are extension points for non-dev-plan docs, explicit paths, and metadata-driven target discovery, but they are uneven across actions
Confidence: high.

Evidence:
- `resolve_custom_doc_path` already knows how to find research docs, bug reports, security reports, review reports, and agent cards by category and name, including case-id matches for bug/security reports. See [src/scribe_mcp/doc_management/utils.py](../../../../src/scribe_mcp/doc_management/utils.py#L445).
- `quality_check`/`scaffold_quality_check` can accept an explicit markdown path in `doc_name` when it is absolute or repo-relative, but only if it stays inside the project root and ends with `.md`. See [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L906).
- `rehome_doc` accepts `doc`/`doc_name`, `metadata.target_project`, `metadata.target_dir`, and `metadata.source_path`, and it enforces docs-relative/project-root boundaries. See [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L1132) and [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L1245).
- `create_doc` also has a `register_existing` flow that can resolve an on-disk file and register it safely when metadata supplies `register_as`/`doc_name`. See [src/scribe_mcp/doc_management/actions/edit.py](../../../../src/scribe_mcp/doc_management/actions/edit.py#L166).

Implication:
- The repo already has enough primitives to support cleaner follow-up workflows for case reports. The missing piece is not path safety; it is making the edit router consistently recognize the same identifiers that creation and case registration already emit.

### 4. The current safe identifiers for bug/security follow-up edits are registered doc keys, returned paths, or doc names that are already bound into `project["docs"]`
Confidence: medium-high.

Evidence:
- `apply_doc_change` only edits a target after `_resolve_doc_path` resolves it under the project root, and it refuses unregistered doc names unless the file already exists and can be auto-registered. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L318).
- `resolve_registered_doc_key` can map a returned absolute path or relative path to the registered key if the project docs mapping already contains that path. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L193).
- `link_fix` assumes the case-report doc is already registered and uses `case_record.doc_name` or `case_id` as the document key for follow-up edits. See [src/scribe_mcp/tools/sentinel_tools.py](../../../../src/scribe_mcp/tools/sentinel_tools.py#L1503).

Implication:
- For source-backed bug/security follow-up edits, the safest accepted identifiers are:
  - the registered `doc_name`/case ID written by the opener flow
  - the returned path when it is already registered in `project["docs"]`
  - a path alias that `resolve_registered_doc_key` can map back to the registered key
- `doc_type`/`doc_category` are routing hints, not reliable primary identifiers.

### 5. Unsafe arbitrary file editing is blocked by path sandboxing, registration checks, and anchor-level edit guards
Confidence: high.

Evidence:
- `_resolve_doc_path` ensures the resolved document path stays within `project_root`, including fallback paths and legacy subdirectory searches. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L1101).
- `_resolve_create_doc_path` validates `target_dir` and final output paths against `project_root`. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L1195).
- `ensure_parent` uses a sandboxed path helper before creating directories. See [src/scribe_mcp/utils/files.py](../../../../src/scribe_mcp/utils/files.py#L598).
- `replace_section` fails when the section anchor is missing or duplicated unless the caller explicitly enables append/scaffold behavior. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L1362).
- `apply_patch` requires an explicit patch/edit payload and has its own mode validation and conflict checks. See [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L406).
- `rehome_doc` rejects target paths outside the target docs tree and forbids nested `.scribe` paths. See [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L1245).

Implication:
- The safe boundary is already strong enough to prevent arbitrary file editing. The real risk is identifier drift: if the caller uses the wrong key for a case report, the mutation fails even though the target file exists on disk.

## Why bug reports under `docs/bugs/runtime` can become awkward to update

1. The creation path is slug-first, not case-registry-first, unless the caller is the Sentinel opener flow. `create_bug_report` keys the artifact by slug and returns that slug as `doc_name`. See [src/scribe_mcp/doc_management/special_create.py](../../../../src/scribe_mcp/doc_management/special_create.py#L458) and [src/scribe_mcp/doc_management/special_create.py](../../../../src/scribe_mcp/doc_management/special_create.py#L789).
2. The runtime edit router does not perform a generic case-registry lookup. It depends on `project["docs"]` registration and `resolve_registered_doc_key`. See [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L1950) and [src/scribe_mcp/doc_management/manager.py](../../../../src/scribe_mcp/doc_management/manager.py#L193).
3. Category-based custom resolution is uneven. `resolve_custom_doc_path` can discover bug/security reports, but the runtime branch only invokes it for `_CUSTOM_DOC_TYPES`, and that set does not include plain `security` and uses `bugs` rather than `bug`. See [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L144) and [src/scribe_mcp/doc_management/runtime.py](../../../../src/scribe_mcp/doc_management/runtime.py#L2067).

## Recommended constraints for Blueprint

1. Treat the registered doc key as the authoritative follow-up identifier for bug/security reports.
2. Preserve the current safe path sandboxing; do not weaken it to accept arbitrary filesystem paths.
3. If the UX needs improvement, add a source-backed lookup layer that can resolve `case_id` to the registered doc key before mutation, rather than bypassing registration.
4. Keep `doc_category` as a hint, not a required primary key, and avoid broadening the edit router into unconstrained file editing.
5. If direct path support is added for edits, require that the path be normalized, project-root bounded, and mapped back to a registered doc key before mutation.

## Targeted test evidence

- Target resolution and alias handling are covered by [tests/test_manage_docs_target_resolution.py](../../../../tests/test_manage_docs_target_resolution.py).
- Bug/security case registry metadata and backfill logic are covered by [tests/test_case_registry_registration.py](../../../../tests/test_case_registry_registration.py).
- Bug/security index routing is covered by [tests/test_manage_docs_index_updates.py](../../../../tests/test_manage_docs_index_updates.py).

## Verification

Focused tests passed in this workspace:

```text
pytest -q tests/test_manage_docs_target_resolution.py tests/test_case_registry_registration.py tests/test_manage_docs_index_updates.py
```

