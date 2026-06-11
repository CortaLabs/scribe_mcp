# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>

## doc_updates auto-log contract repair
- `entry_id`: 20260611:doc-updates-autolog-contract-2-4-2
- `entry_status`: accepted
- `title`: doc_updates auto-log contract repair
- `summary`: Bumped the public release line to `2.4.2` and repaired the manage_docs edit auto-logger so internal doc_updates entries satisfy their own metadata_requirements (`doc`, `section`, `action`) and use a valid `warn` status, eliminating the ~37k "Log requirements not met: Missing metadata for log entry: doc" silent error stream (BUG-2026-06-11-0003).
- `evidence_refs`:
  - pyproject.toml
  - docs/COMPATIBILITY_MATRIX.md
  - src/scribe_mcp/doc_management/actions/edit.py
  - tests/test_doc_updates_autolog_contract.py
  - docs/bugs/logic/2026-06-11_BUG-2026-06-11-0003/report.md
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.2

## Bug and security report follow-up editing
- `entry_id`: 20260604:case-report-manage-docs-followup-2-4-1
- `entry_status`: accepted
- `title`: Bug and security report follow-up editing
- `summary`: Bumped the public release line to `2.4.1`, added obvious `open_bug` and `open_security` follow-up handles, and taught `manage_docs` to resolve governed bug/security reports by case id, governed path, or canonical category metadata before applying edits.
- `evidence_refs`:
  - pyproject.toml
  - README.md
  - docs/COMPATIBILITY_MATRIX.md
  - docs/RELEASE_SURFACE.md
  - src/scribe_mcp/doc_management/runtime.py
  - src/scribe_mcp/doc_management/utils.py
  - src/scribe_mcp/tools/sentinel_tools.py
  - tests/test_manage_docs_target_resolution.py
  - tests/test_sentinel_tools.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.1

## No-dotenv-safe settings import
- `entry_id`: 20260518:no-dotenv-settings-import
- `entry_status`: accepted
- `title`: No-dotenv-safe settings import
- `summary`: Added the generic `SCRIBE_DISABLE_DOTENV` settings-load guard so import/readiness proof can avoid repo and global dotenv reads, preserved storage backend fail-closed behavior, and bumped the public release line to `2.2.24`.
- `evidence_refs`:
  - src/scribe_mcp/config/settings.py
  - tests/test_settings_schema_alias.py
  - tests/test_storage_factory_backends.py
  - tests/test_runtime_backend_repo_overrides.py
  - pyproject.toml
  - README.md
  - docs/COMPATIBILITY_MATRIX.md
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.2.24
