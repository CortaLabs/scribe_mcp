
# 🔬 Research Scribe Structural Topology — scribe_document_topology_foundation_20260524
**Author:** Scribe
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-05-25 03:25 UTC

> Audit markdown/frontmatter parsing, link validation, checklist extraction, TOC generation, and deterministic edge resolution for managed docs.

---
## Executive Summary
<!-- ID: executive_summary -->
This audit found that Scribe already has deterministic, reusable building blocks for document topology: YAML frontmatter parsing, anchor-first section discovery, checklist extraction, GitHub-style TOC anchors, and read-only crosslink diagnostics.

The current gap is topology semantics. `related_docs` can express adjacency, but it cannot yet represent typed edges, direction, resolution state, or cycles in a way that is ready for managed-doc quality gating.

The best implementation path is to extend the existing managed-doc pipeline, not add a second topology registry.

## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent
**Investigation Window:** 2026-05-24 to 2026-05-25

**Focus Areas:**
Frontmatter extraction, section listing, checklist extraction, header normalization, TOC generation, markdown link parsing, local-anchor resolution, typed edge fields, deterministic target resolution, and cycle detection.

**Dependencies & Constraints:**
No source edits, no transformer or embedding parsing, no parallel topology registry, and any new topology semantics must integrate with managed docs, registration, and `manage_docs quality_check`.

## Findings
<!-- ID: findings -->
### Finding 1
**Summary:** Frontmatter parsing is already deterministic and YAML-based. The helper preserves the body, strips the top-of-file frontmatter block, and rejects malformed or non-mapping frontmatter.

**Evidence:** `src/scribe_mcp/utils/frontmatter.py:24-62`

**Confidence:** High

### Finding 2
**Summary:** Section discovery is already stable and anchor-aware. `inspect_document_sections_from_text` prefers explicit `<!-- ID: ... -->` anchors, falls back to heading-derived IDs only when no explicit anchors exist, and reports duplicate IDs as warnings.

**Evidence:** `src/scribe_mcp/doc_management/actions/query.py:76-160`

**Confidence:** High

### Finding 3
**Summary:** Markdown-It is already installed and used for fence-aware scope extraction, so it is the best lightweight parser to extend for deterministic Markdown tokenization.

**Evidence:** `pyproject.toml:19-28`, `src/scribe_mcp/doc_management/quality/scopes.py:149-257`

**Confidence:** High

### Additional Notes
`validate_crosslinks` is read-only diagnostics over `related_docs`; it does not yet model typed edges or cycles.

---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
`parse_frontmatter` is the canonical frontmatter entrypoint. It uses `yaml.safe_load`, preserves the original body, and keeps managed-doc updates isolated from parsing concerns.

`inspect_document_sections_from_text` is the current structural primitive for stable section targeting. It is anchor-first, heading-fallback, and fence-aware, which is exactly the right shape for deterministic doc topology.

`list_sections` and `list_checklist_items` both depend on project registration and file-backed document lookup. That means topology semantics should remain attached to managed-doc registration rather than a separate registry.

`generate_toc` and `normalize_headers` already share a deterministic anchor model. The TOC builder uses GitHub-style anchors with duplicate suffixing, and normalization explicitly skips fenced code blocks before rewriting numbered ATX headers.

`validate_crosslinks` currently validates `related_docs` only. It resolves local paths relative to the docs base directory, optionally checks anchors, and returns a diagnostic list rather than mutating content.

**System Interactions:**
`manage_docs` already exposes the structural actions needed for a topology gate: `list_sections`, `list_checklist_items`, `normalize_headers`, `generate_toc`, `validate_crosslinks`, and `quality_check`. The right design is to extend that same surface, not introduce a parallel topology service.

`markdown-it-py` is already installed in `pyproject.toml` and already used in the Markdown scope provider for fence-aware and inline-code-aware tokenization. That makes it appropriate for any future deterministic link-token extraction that outgrows regex.

**Typed Edge Schema Recommendation:**
Use the existing `related_docs` field as the compatibility bridge, but add typed edge fields to managed-doc frontmatter so the graph can be validated deterministically.

```yaml
related_docs:
  - architecture#research_scope
  - checklist#p1-document-topology

depends_on:
  - architecture#research_scope
  - doc: checklist
    target: checklist#p1-document-topology
    anchor: p1-document-topology
    relation: hard
    status: resolved
supports:
  - doc: architecture
    target: architecture#technical_analysis
    relation: soft
validates:
  - checklist#p1-document-topology
supersedes:
  - legacy-topology-note
blocked_by:
  - checklist#p1-release-readiness
touches:
  - architecture
  - checklist
```

Recommended canonical edge fields: `depends_on`, `supports`, `validates`, `supersedes`, `blocked_by`, and `touches`.

Recommended normalized internal shape: `kind`, `source_doc`, `target_doc`, `target_path`, `target_anchor`, `target_resolved`, `relation_strength`, `status`, and `note`.

**Validation Algorithm Sketch:**
1. Parse frontmatter with the canonical YAML helper.
2. Normalize each edge entry into a canonical record, accepting both string and structured forms.
3. Resolve targets in deterministic order: registered doc name, then relative path within the project docs base directory, then anchor within the target document.
4. Validate existence first, then anchor existence if anchor checks are enabled.
5. Build a project-wide adjacency map from the normalized edges.
6. Run deterministic cycle detection with DFS or Kahn and return the concrete cycle path.
7. Surface broken targets and cycles as blocking findings; never auto-repair or silently drop them.
8. Feed the same normalized results into `manage_docs quality_check` so topology readiness and document readiness share one gate.

**Risk Notes:**
Explicit heading anchors are more stable than derived heading IDs. If authors rename headings without preserving anchors, section targets will shift and downstream operations will become ambiguous.

The current regex-based markdown-link extractor is intentionally simple. It should be replaced or supplemented if the topology layer needs to resolve more complex CommonMark link forms deterministically.

Without a typed edge schema, the project cannot detect dependency cycles meaningfully. `related_docs` alone is sufficient for adjacency, but not enough for dependency direction or blocking semantics.

---
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
Add a managed-doc topology normalizer that converts string and structured edge entries into the canonical schema above.

Extend `validate_crosslinks` to operate on all typed edge fields, not just `related_docs`, and return a stable diagnostic payload that includes broken targets, missing anchors, and cycle paths.

Wire the same normalized topology view into `quality_check` so scaffold residue, broken references, and topology cycles can block readiness together.

### Long-Term Opportunities
Make explicit anchors the preferred target form for stable cross-document references, and treat heading-derived IDs as a fallback for listing and TOC generation only.

Keep the Markdown parser surface lightweight and deterministic. `markdown-it-py` is already the right dependency for tokenization; do not introduce a second parser unless a concrete edge case proves it necessary.

---
## Appendix
<!-- ID: appendix -->
**References:**
`src/scribe_mcp/utils/frontmatter.py:24-62`
`src/scribe_mcp/doc_management/actions/query.py:76-160`
`src/scribe_mcp/doc_management/actions/query.py:160-291`
`src/scribe_mcp/doc_management/actions/query.py:298-460`
`src/scribe_mcp/doc_management/manager.py:2579-2665`
`src/scribe_mcp/doc_management/manager.py:2675-2845`
`src/scribe_mcp/doc_management/manager.py:3019-3065`
`src/scribe_mcp/doc_management/manager.py:3575-3692`
`src/scribe_mcp/tools/manage_docs_validation.py:241-343`
`src/scribe_mcp/doc_management/quality/scopes.py:149-257`
`pyproject.toml:19-28`

**Attachments:**
Managed research artifact only; no external attachments were needed for this audit.
