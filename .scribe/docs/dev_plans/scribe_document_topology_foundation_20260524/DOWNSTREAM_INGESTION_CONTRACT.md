---
id: downstream-ingestion-contract
doc_type: architecture
doc_name: DOWNSTREAM_INGESTION_CONTRACT
summary: Generic downstream ingestion contract for sanitized deterministic topology exports.
status: ready
quality_status: pass
---

# Downstream Ingestion Contract

## Scope
Scribe publishes deterministic sanitized export truth for downstream consumers.

## Producer Fields
Required document fields: `id`, `doc_name`, `doc_type` or `intended_doc_type`, `summary`, `status`.
Eligible statuses: `ready`, `complete`.
Quality requirement: export eligibility requires explicit quality status and non-blocking quality result.

## Artifact Schemas
`doc_topology.json`: stable node/edge projection from managed docs and normalized topology links.
`work_topology.json`: aggregate counts and cycle projection over hard dependency edges.
`downstream_ingestion_manifest.json`: per-doc eligibility decisions with rejection codes.

## Rejection Codes
- `REJECTED_OUTSIDE_REPO`
- `REJECTED_UNSAFE_EXTERNAL_LINK`
- `REJECTED_ARCHIVED`
- `REJECTED_STALE`
- `REJECTED_SUPERSEDED`
- `REJECTED_BLOCKED`
- `REJECTED_SCAFFOLDED_OR_IN_PROGRESS`
- `REJECTED_QUALITY_FAIL`
- `REJECTED_MISSING_QUALITY`
- `REJECTED_MISSING_REQUIRED_METADATA`
- `REJECTED_DANGLING_EDGE`

## Sanitized Path Rules
Only repo-relative paths are emitted. Absolute paths, repo-root leakage, and arbitrary frontmatter dumps are forbidden.

## Responsibilities
Scribe public core owns deterministic truth generation and sanitized exports only.
Downstream systems own ingestion strategy, embeddings, retrieval/ranking, Graph RAG traversal, and model classification.
Knowledge MCP is an optional private adapter example outside Scribe public core.

## Runbook
1. Generate exports via `manage_docs(action="regenerate_intelligence_exports")`.
2. Inspect eligibility preview via `manage_docs(action="ingestion_manifest_inspect")`.
3. Repair metadata/topology/quality blockers via existing scan+repair workflows.
4. Regenerate and confirm deterministic output.

## Future Expectations
Future Graph RAG consumers should treat Scribe exports as canonical sanitized source and apply downstream policies independently.
