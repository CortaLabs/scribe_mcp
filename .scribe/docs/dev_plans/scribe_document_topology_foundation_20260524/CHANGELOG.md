# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>

## 2026-05-25: document-topology-foundation-release
- `entry_id`: 20260525:document-topology-foundation-release
- `entry_status`: accepted
- `title`: Document topology foundation release
- `summary`: Release 2.4.0 makes Scribe a deterministic document topology and lifecycle authority with canonical managed-doc metadata, typed topology edges, topology and metadata scan actions, safe and assisted repair modes, hard quality handoff gates, sanitized downstream ingestion manifests, and a generic downstream export boundary that keeps retrieval and semantic ranking outside Scribe.
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.4.0
- `evidence_refs`:
  - pyproject.toml
  - src/scribe_mcp/doc_management/lifecycle.py
  - src/scribe_mcp/doc_management/topology.py
  - src/scribe_mcp/doc_management/intelligence_workflows.py
  - src/scribe_mcp/doc_management/intelligence_exports.py
  - src/scribe_mcp/doc_management/boundary_guidance.py
  - src/scribe_mcp/doc_management/runtime.py
  - src/scribe_mcp/doc_management/scaffold_quality.py
  - src/scribe_mcp/state/agent_manager.py
  - tests/test_document_topology_metadata.py
  - tests/test_document_topology_parsing.py
  - tests/test_document_intelligence_workflows.py
  - tests/test_document_topology_exports.py
  - tests/test_manage_docs_quality_check.py
  - tests/test_manage_docs_scaffold_quality.py
  - docs/DOCUMENT_TOPOLOGY.md
  - .scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/CHECKLIST.md
