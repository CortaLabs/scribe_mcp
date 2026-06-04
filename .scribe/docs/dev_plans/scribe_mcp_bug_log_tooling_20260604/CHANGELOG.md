# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>
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
  - REVIEW_POST_IMPLEMENTATION_PACKAGE_0_1_RERUN
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.1
