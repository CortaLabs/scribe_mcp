# RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY

## Executive Summary

This research defines the ingestion contract boundary between Scribe (source authority) and Knowledge MCP (downstream retrieval/index consumer) for the Document Topology Foundation initiative. The core finding is that Scribe must emit deterministic, quality-gated, topology-aware export artifacts and ingestion manifests, while Knowledge MCP must remain responsible for embeddings, semantic retrieval, ranking, Graph RAG traversal logic, and model-driven classification.

Key conclusions:
- Scribe already has primitives needed for deterministic export metadata: content hashing (`hash_text`), stable chunk IDs (`generate_doc_entry_id`), semantic chunking (`chunk_text_for_vector`), and source-family classification (`classify_scribe_source_document`).
- Scribe quality lifecycle must gate ingestion eligibility using existing scaffold-quality and lifecycle mismatch signals, rather than allowing any managed document to ingest.
- Publication boundary requirements confirm that live `.scribe/**` runtime state is not public export material; ingestion payloads must be curated, sanitized contract outputs.
- Knowledge MCP contract surfaces define producer-versus-consumer separation that should be mirrored in Scribe’s own export contract.

## Evidence Inventory

Primary sources reviewed:
- `skills/scribe-integration/SKILL.md`
- `docs/examples/hello_world_scribe/publication_boundary.md`
- `.codex/skills/scribe-rag-workflow/SKILL.md`
- `.codex/skills/knowledge-dataset-contract/SKILL.md`
- `.codex/skills/knowledge-mcp-usage/SKILL.md`
- `src/scribe_mcp/doc_management/utils.py`

## Boundary Contract: Scribe-Owned Responsibilities

### Eligibility and Lifecycle Gate

Required eligibility conditions per document:
- Managed doc is in canonical managed location for its source family.
- Frontmatter lifecycle status is eligible for ingestion (recommended allowlist: `ready_for_review`, `approved`, `published`; configurable by policy).
- `quality_check` blocking warning count is zero for ingestion-critical warnings.
- Document passes canonical indexing hygiene (indexed or indexable in expected project/doc hierarchy).

Recommended rejection reason codes:
- `REJECT_NONCANONICAL_PATH`
- `REJECT_STATUS_INELIGIBLE`
- `REJECT_QUALITY_BLOCKER`
- `REJECT_SCAFFOLD_RESIDUE`
- `REJECT_MISSING_REQUIRED_FRONTMATTER`
- `REJECT_INDEX_DRIFT`
- `REJECT_SANITIZATION_REQUIRED`

### Ingestion Manifest (Run + Document Records)

Run-level fields:
- `contract_version`, `export_run_id`, `project_name`, `project_slug`, `repo_root`, `generated_at_utc`
- `source_dataset`, `documents_total`, `documents_eligible`, `documents_rejected`
- `rejection_summary`, `index_schema_version`, `hash_algorithm`

Per-document fields:
- `doc_id`, `doc_name`, `doc_type`, `source_family`, `path`, `status`
- `content_hash`, `frontmatter_hash`, `last_updated_utc`
- `eligibility`, `rejection_reasons[]`, `chunk_count`, `edge_count`

### Topology Index Schema

Node fields:
- `node_id`, `node_type`, `doc_id`, `title`, `path`, `doc_type`, `status`, `content_hash`, `updated_at_utc`, `tags[]`

Edge fields:
- `edge_id`, `src_node_id`, `dst_node_id`, `edge_type`, `evidence`, `confidence`

### Chunk Export Contract

Producer chunk payload should include:
- `chunk_id`, `title`, `domain`, `content`
- `source_refs`, `entity_refs` (rule-derived only)
- `metadata.doc_id`, `metadata.doc_type`, `metadata.project`, `metadata.status`, `metadata.content_hash`, `metadata.source_type`

## Boundary Contract: Knowledge MCP-Owned Responsibilities

Must remain downstream in Knowledge MCP:
- Embedding generation and vector indexing/storage orchestration
- Semantic retrieval ranking and score blending
- Graph RAG traversal and retrieval-time graph scoring
- Model-based classification/synthesis/abstention behavior
- Query-time relevance tuning and cross-dataset arbitration

## Operator and Agent Workflow Recommendations

Recommended low-friction flow:
1. Run `manage_docs` `quality_check` for candidate docs/projects.
2. Run Scribe export/index generation on eligible docs.
3. Emit ingestion manifest, topology index, and chunk export artifacts.
4. Return rejection-coded repair guidance mapped to owning docs.
5. Re-export only affected project/doc subsets after repair.

Usability requirements:
- Human-readable summary counts by doc type/status/rejection code.
- Deterministic JSON artifacts for automation.
- Stable IDs/hashes for incremental updates and audit diffs.

## Risks and Mitigations

- Contract drift between producer and consumer schemas.
  - Mitigation: versioned contract + compatibility checks.
- Scaffold/ineligible docs polluting retrieval corpus.
  - Mitigation: hard eligibility gate tied to quality warnings/status allowlist.
- Noisy/non-deterministic graph edges.
  - Mitigation: rule-based edge derivation only in Scribe.
- Confusion between live local runtime state and publishable/exportable artifacts.
  - Mitigation: enforce publication boundary and sanitize exports.

## Draft Inputs for Future Contract Doc

Future `KNOWLEDGE_MCP_INGESTION_CONTRACT.md` should codify:
- Field-level schemas for manifest, topology index, and chunk exports.
- Eligibility/rejection rules and reason-code catalog.
- Hash/content identity and incremental update semantics.
- Scribe-vs-Knowledge responsibility table and explicit non-goals.
- Operator runbook for generate-inspect-repair-reingest.

This research artifact intentionally does not author the final contract doc.

## Next-Gate Impact

This artifact unblocks contract drafting by providing evidence-backed boundary decisions, required fields, eligibility/rejection model, topology/index recommendations, and operator workflow guidance.
---