
# 🔬 Research Scribe Topology Index Implementation — scribe_document_topology_foundation_20260524
**Author:** Scribe
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-05-25 03:36:00 UTC

> Wave 2 storage/index strategy for deterministic topology and ingestion artifacts with cross-backend compatibility and migration risk assessment.

---
## Executive Summary
<!-- ID: executive_summary -->
This lane evaluated whether topology/index outputs should be stored as durable backend records or derived deterministically from existing managed-doc truth surfaces.

Primary decision: **v1 should be derived artifacts, not storage-backed topology tables**. Use current managed-doc registration, frontmatter metadata, quality results, and deterministic file-state hashing to generate:
- `.scribe/indexes/doc_topology.json`
- `.scribe/indexes/work_topology.json`
- `.scribe/indexes/knowledge_ingestion_manifest.json`

This satisfies no-second-registry constraints, avoids immediate multi-backend migration debt, and keeps parity risk low while still enabling deterministic downstream ingestion contracts.

## Research Scope
<!-- ID: research_scope -->
**Research Lead:** sia

**Investigation Window:** 2026-05-24 — 2026-05-25

**Focus Areas:**
- Existing registration/storage/index generation evidence.
- Deterministic content identity and mtime/path handling.
- Cross-backend behavior and migration risk.
- Safe regeneration triggers and repeat-run determinism.

**Dependencies & Constraints:**
- No source edits.
- No second document registry.
- Prefer managed-doc/frontmatter/registration derivation unless storage proof required.

## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** Existing architecture already supports single-registry document truth via project `docs_json`, with registration/autoregister/rehome behavior in doc management.
- **Evidence:** `src/scribe_mcp/storage/base.py`, `src/scribe_mcp/storage/postgres/__init__.py` (`update_project_docs`/project docs_json fields), `src/scribe_mcp/doc_management/manager.py` (registered-doc resolution + auto-register behavior).
- **Confidence:** High

### Finding 2
- **Summary:** Deterministic identity primitives already exist for hashing and stable IDs, so v1 index generation can be derived without schema change.
- **Evidence:** `src/scribe_mcp/doc_management/utils.py` (`hash_text`, `generate_doc_entry_id`, `classify_scribe_source_document`), plus Wave 1 ingestion boundary research.
- **Confidence:** High

### Finding 3
- **Summary:** Cross-backend storage divergence risk is materially higher if v1 introduces new topology tables/columns now, especially with PostgreSQL backend complexity and Remote API compatibility needs.
- **Evidence:** `src/scribe_mcp/storage/remote.py` (operation-proxy model), `src/scribe_mcp/storage/postgres/__init__.py` monolith status and project-doc update path, Wave 1 registration findings.
- **Confidence:** High

### Additional Notes
- Hybrid evolution remains valid later: keep v1 derived-on-read/materialized-files; add optional cached storage records only after perf or scale evidence justifies migration cost.

## Technical Analysis
<!-- ID: technical_analysis -->
**Current index/storage generation evidence:**
- Project registry persists docs mapping (`docs_json`) and is already backend-portable.
- Managed-doc flows provide canonical source signals: doc path, frontmatter fields, section anchors, related edges, and quality status outputs.
- Existing hash and classification utilities can anchor deterministic artifact rows.

**Recommended schemas (v1):**
1) `doc_topology.json`
- `schema_version`, `generated_at_utc`, `project_name`, `source_hash`
- `documents[]` with: `doc_id`, `doc_name`, `doc_type`, `path`, `status`, `content_hash`, `frontmatter_hash`, `mtime_utc`, `quality_status`, `quality_blockers`, `tags[]`
- `edges[]` with: `edge_id`, `kind` (`depends_on|supports|validates|supersedes|blocked_by|touches|related_docs`), `source_doc_id`, `target_ref`, `target_doc_id`, `target_anchor`, `resolved`, `resolution_error`

2) `work_topology.json`
- `schema_version`, `generated_at_utc`, `project_name`
- `workstreams[]` with: `workstream_id`, `docs[]`, `statuses{}`, `blocker_counts{}`
- `phases[]` with: `phase_id`, `doc_refs[]`, `dependency_edges[]`

3) `knowledge_ingestion_manifest.json`
- `contract_version`, `generated_at_utc`, `project_name`, `hash_algorithm`
- `documents_total`, `eligible_total`, `rejected_total`, `rejection_summary{}`
- `records[]` with: `doc_id`, `path`, `status`, `quality_status`, `content_hash`, `eligibility`, `rejection_reasons[]`, `source_family`, `chunk_count_estimate`, `edge_count`

**Derivation sources and regeneration flow:**
1. Load project registry/doc map from managed-doc registration source.
2. For each registered doc: parse frontmatter + compute `content_hash` and `frontmatter_hash`; capture file `mtime` from filesystem.
3. Normalize typed edges from frontmatter + compatibility `related_docs` references.
4. Resolve targets against registered docs and anchors; annotate unresolved edges deterministically.
5. Pull quality-check output/state for blocker/eligibility mapping.
6. Emit three JSON artifacts with stable key ordering, sorted arrays (path/doc_id/edge_id), and explicit schema versions.

**Storage schema change needs / migration risk:**
- **v1: none required** (derived artifacts only).
- Optional future hybrid cache (if needed) should be additive and idempotent, with defaults, and implemented across SQLite/Postgres/Remote operation contracts before enabling by default.
- Immediate storage migrations now would add medium-high risk without proof of necessity.

**Cross-backend compatibility plan:**
- SQLite/PostgreSQL: identical derivation behavior because source-of-truth fields already exist at project/docs/frontmatter/file layer.
- Remote backend: run derivation where file access and managed docs exist; avoid requiring remote-only new storage methods in v1.
- Keep manifest/index contract backend-agnostic so downstream ingestion never depends on backend-specific columns.

**Determinism and repeated-run test strategy:**
- Fixed ordering tests: run generation twice with unchanged inputs and assert byte-identical JSON output.
- Mutation tests: single-doc content/frontmatter/path/mtime changes produce localized diff only.
- Edge resolution tests: unresolved target and cycle scenarios produce stable error codes/ordering.
- Cross-backend parity tests: same fixture corpus under SQLite and PostgreSQL yields identical logical rows (ignoring timestamp of generation).
- Remote compatibility test: absence of optional fields does not break artifact generation.

## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Adopt **derived-only v1** and codify schema versions for the three JSON artifacts.
- Define canonical sort rules and hashing rules in one generation contract.
- Wire regeneration trigger points to managed-doc mutations + explicit regenerate command.

### Long-Term Opportunities
- Introduce optional hybrid cache only if performance evidence shows repeated full derivation cost is unacceptable.
- When cache is introduced, keep derived artifacts as canonical external contract and treat storage cache as internal acceleration only.

## Appendix
<!-- ID: appendix -->
- **References:**
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/SPEC.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_DOC_REGISTRATION.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_STRUCTURAL_TOPOLOGY.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md`
  - `src/scribe_mcp/storage/base.py`
  - `src/scribe_mcp/storage/postgres/__init__.py`
  - `src/scribe_mcp/storage/remote.py`
  - `src/scribe_mcp/doc_management/manager.py`
  - `src/scribe_mcp/doc_management/runtime.py`
  - `src/scribe_mcp/doc_management/utils.py`
- **Attachments:** Managed research artifact only; no code changes.
