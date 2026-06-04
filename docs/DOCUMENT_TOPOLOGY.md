# Document topology and downstream export

Release line: `2.4.1`
Updated: `2026-06-04`

Scribe now treats managed documents as a deterministic corpus, not loose markdown. The goal is simple: Scribe owns document truth, lifecycle state, quality posture, typed relationships, and sanitized export records. Downstream systems can build retrieval, datasets, dashboards, or graph traversal from those records, but they do not define Scribe truth.

## Managed document contract

New and repaired managed documents prefer these frontmatter fields:

- `id`
- `title`
- `doc_type`
- `doc_name`
- `category`
- `status`
- `summary`
- `created_by`
- `maintained_by`
- `owners`
- `tags`
- `related_docs`

Human-facing attribution uses display names such as `Forge`, `Atlas`, `Witness`, `Crucible`, `Blueprint`, `Arbiter`, `Loom`, and `Quill`. Opaque runtime IDs may remain as secondary provenance, but they should not be the primary author or owner value.

Allowed lifecycle statuses are:

- `scaffolded`
- `in_progress`
- `ready`
- `complete`
- `stale`
- `superseded`
- `blocked`
- `archived`

`ready` and `complete` are quality-gated. A document with scaffold residue, failed-write residue, unresolved blockers, invalid topology, or missing required metadata is not clean handoff material.

## Typed topology

Scribe accepts deterministic typed edges under frontmatter `topology`:

- `depends_on`
- `supports`
- `validates`
- `supersedes`
- `blocked_by`
- `touches`
- `related_docs`

Edges can begin as string IDs and normalize into structured records with target reference, relation type, source path, resolution state, and proof metadata. Scribe validates what it can prove from registered documents, repo-relative paths, anchors, and markdown structure. It does not guess semantic relationships.

## Operator actions

The topology foundation extends `manage_docs` with these actions:

- `topology_scan`: read-only graph snapshot with nodes, edges, duplicate IDs, dangling targets, anomalies, and hard dependency cycles.
- `metadata_scan`: read-only metadata findings for missing IDs, missing summaries, invalid IDs, invalid edge shapes, duplicate IDs, and opaque agent-ID leaks.
- `metadata_repair`: `report_only`, `repair_safe`, and `repair_assisted` modes for deterministic repair without guessing.
- `stale_cleanup_scan`: non-destructive cleanup recommendations for empty, tiny, stale, and sentinel-log-like docs.
- `quality_handoff_check`: proof gate for clean handoff or clock-out attempts.
- `ingestion_manifest_inspect`: read-only preview of sanitized downstream ingestion eligibility.

## Export artifacts

Scribe writes derived local artifacts under `.scribe/indexes/`:

- `doc_topology.json`
- `work_topology.json`
- `downstream_ingestion_manifest.json`

These files are generated from managed-doc registration, frontmatter, quality posture, deterministic file state, and topology validation. They are not a second registry and not a semantic index.

The downstream manifest uses allowlisted, repo-relative publication fields. It rejects documents that are outside the repo, scaffolded, in progress, blocked, stale, superseded, archived, quality-failing, missing required metadata, or blocked by dangling topology edges.

## Boundary

Scribe does not ship embeddings, transformer classifiers, semantic matching, vector search, graph-RAG traversal, or retrieval ranking. Those are downstream responsibilities.

Scribe's contract is to publish a clean, deterministic corpus boundary:

- stable document IDs
- lifecycle status
- quality state
- sanitized repo-relative paths
- summaries
- typed edges
- rejection reasons
- deterministic JSON artifacts

That is enough for downstream consumers to ingest excellent source material without making Scribe pretend to be the retrieval layer.
