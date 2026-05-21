# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>

## Emergency Scribe UX repair wave
- `entry_id`: 20260521:link-fix-quality-read-recent-ux
- `entry_status`: accepted
- `title`: Emergency Scribe UX repair wave
- `summary`: Release 2.2.27 makes `link_fix` usable without `scribe_doctor`, adds typed fix artifact metadata, repairs report update targeting, lets `quality_check` inspect repo markdown paths and reports outside the active registry, reports trailing markdown whitespace via `SCF_TRAILING_WHITESPACE`, allows same-repo cross-project `read_recent` inspection without rebinding, and restores stable-session authority for document registration.
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.2.27
- `evidence_refs`:
  - pyproject.toml
  - src/scribe_mcp/tools/sentinel_tools.py
  - src/scribe_mcp/doc_management/runtime.py
  - src/scribe_mcp/doc_management/scaffold_quality.py
  - src/scribe_mcp/shared/logging_utils.py
  - src/scribe_mcp/tools/agent_project_utils.py
  - tests/test_sentinel_tools.py
  - tests/test_manage_docs_quality_check.py
  - tests/test_manage_docs_scaffold_quality.py
  - tests/security/test_project_binding_policy.py
