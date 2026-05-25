---
id: scribe_document_topology_foundation_20260524-research-scribe-topology-security-boundary
title: "\U0001F52C Research Scribe Topology Security Boundary \u2014 scribe_document_topology_foundation_20260524"
doc_type: RESEARCH_SCRIBE_TOPOLOGY_SECURITY_BOUNDARY
doc_name: RESEARCH_SCRIBE_TOPOLOGY_SECURITY_BOUNDARY
category: engineering
status: ready
version: '0.1'
last_updated: 2026-05-25 03:45:12 UTC
maintained_by: agent-20260525-033354-b4269bd2
created_by: agent-20260525-033354-b4269bd2
owners: []
related_docs: []
tags: []
summary: Security and trust-boundary audit for Scribe topology indexes and Knowledge
  MCP ingestion manifests, including export controls, rejection rules, minimal visibility
  metadata, and implementation review requirements.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 03:45:12 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-05-25 03:45:12 UTC
  last_edited_by: agent-20260525-033354-b4269bd2
  last_action: frontmatter_update
---

# 🔬 Research Scribe Topology Security Boundary — scribe_document_topology_foundation_20260524
**Author:** Scribe
**Version:** v0.1
**Status:** ready
**Last Updated:** 2026-05-25 03:41:29 UTC

> Wave 2 security and trust-boundary audit for Scribe topology indexes and Knowledge MCP ingestion manifests.

---
## Executive Summary
<!-- ID: executive_summary -->
Scribe can safely act as the truth layer for downstream retrieval only if topology indexes and `knowledge_ingestion_manifest` are treated as publication artifacts rather than direct mirrors of local registry state. The live code already stores and transports normalized repo roots, raw document paths, case-report paths, progress-log locations, and syncable managed-doc content, so v1 must add an explicit sanitization boundary before any Knowledge-facing export is generated.

**Primary Objective:** Define the minimum safe trust boundary between Scribe-managed documents and any downstream Knowledge MCP ingestion artifact so topology exports remain deterministic without leaking workstation-local paths, archived/private corpus state, cross-project records, or user-authored unsafe references.

**Key Takeaways:**
- Scribe should remain the authority for document identity, status, quality, and typed topology, but Knowledge MCP should receive only sanitized export records, never raw `docs_json`, raw registry rows, or absolute `repo_root` values.
- Any document discovered from a configured dev-plans root outside the repo must be rejected from Knowledge export by default or marked `local_only`; current discovery helpers can resolve such roots today.
- Archived, stale, superseded, blocked, scaffolded, and quality-failing documents must be deny-listed for ingestion even if they are discoverable or synced elsewhere.
- User-authored `related_docs` and markdown links must not be followed, promoted into topology edges, or emitted as trusted references unless they resolve inside the active project and pass deterministic allowlist rules.
- Remote storage/object-store transport is an internal persistence boundary, not proof that an artifact is safe for Knowledge publication.
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** SecurityAgent

**Investigation Window:** 2026-05-24 to 2026-05-25 UTC

**Focus Areas:**
- Map the trust boundary between managed docs, project registry state, generated indexes, storage backends, remote/object-store sync, and downstream Knowledge MCP ingestion.
- Verify where absolute paths, repo roots, file hashes, timestamps, and project identifiers are persisted or transmitted today.
- Identify leakage risks from archived/stale/private docs, configured external dev-plan roots, cross-project discovery, and user-authored links.
- Define v1 eligibility and rejection rules for `knowledge_ingestion_manifest` without introducing semantic classification inside Scribe.
- Recommend the smallest metadata contract that expresses visibility and sensitivity decisions deterministically.

**Dependencies & Constraints:**
- Scope is read-only research; no source-code edits and no Knowledge MCP implementation.
- Scribe remains the truth layer for identity, status, quality, and topology; Knowledge MCP remains the retrieval layer.
- Security guidance must reuse existing lifecycle and quality surfaces instead of creating a parallel classification system.
- Findings are grounded in the SPEC, Wave 1 artifacts, and live code paths in `src/scribe_mcp/doc_management`, `src/scribe_mcp/storage`, and `src/scribe_mcp/object_store`.
## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** Absolute repo roots and raw document paths are already first-class storage and logging data, so a topology export that mirrors registry state would expose workstation-local filesystem topology by default.
- **Evidence:** `src/scribe_mcp/storage/models.py:12-28` normalizes and hashes absolute repo roots; `src/scribe_mcp/doc_management/runtime.py:1699-1744` writes raw document paths into project docs mappings and auto-registration logs; `src/scribe_mcp/storage/remote.py:383-412` transports `repo_root` and `doc_path` in remote case-registry payloads.
- **Confidence:** High

### Finding 2
- **Summary:** Scribe discovery can ingest managed-doc roots configured outside the active repo, which is acceptable for local truth workflows but unsafe for Knowledge-facing publication unless those roots are rejected or explicitly marked local-only.
- **Evidence:** `src/scribe_mcp/doc_management/utils.py:365-423` loads `dev_plans_dir` from config and accepts absolute paths; `src/scribe_mcp/doc_management/utils.py:311-362` then scans every project directory and research document under those candidate roots.
- **Confidence:** High

### Finding 3
- **Summary:** Current source discovery and custom-path resolution do not inherently exclude archived or superseded artifacts, so stale/private case reports can be rediscovered unless export policy adds lifecycle and path-family deny rules.
- **Evidence:** `src/scribe_mcp/doc_management/utils.py:347-360` scans case reports with `glob("*/*/report.md")`; `src/scribe_mcp/doc_management/utils.py:473-494` resolves bug/security docs with the same pattern; neither path includes an archive exclusion rule.
- **Confidence:** High

### Finding 4
- **Summary:** User-authored crosslinks are not a safe topology input today because `_validate_crosslinks` resolves arbitrary `related_docs` targets and returns absolute resolved paths without enforcing that the target remains inside the active project.
- **Evidence:** `src/scribe_mcp/doc_management/manager.py:3620-3639` resolves each `related_docs` entry relative to `docs_dir`, records `str(resolved)`, and does not reject targets outside `project_root`.
- **Confidence:** High

### Finding 5
- **Summary:** Managed-doc indexes already participate in remote/object-store sync, which means any sensitive metadata written into an index can cross an internal network boundary long before Knowledge MCP consumes it.
- **Evidence:** `src/scribe_mcp/object_store/keys.py:17-25,58-79` syncs `.scribe/docs/dev_plans/` and `.scribe/docs/agent_report_cards/` markdown by default; `src/scribe_mcp/doc_management/special_indexes.py:30-44` automatically syncs generated indexes to the object store.
- **Confidence:** High

### Finding 6
- **Summary:** There is a strong project-isolation primitive at the storage layer, but callers must preserve it. Case-registry records key by normalized repo root plus project name, while remote query helpers still allow optional filters that could widen the result set if export code is careless.
- **Evidence:** `src/scribe_mcp/storage/sqlite/cases.py:197-252` computes `project_key` from normalized repo root and project name and upserts on `(project_key, case_id)`; `src/scribe_mcp/storage/sqlite/cases.py:255-307` and `src/scribe_mcp/storage/remote.py:419-451` allow fetch/query operations with optional `repo_root` and `project_name` filters.
- **Confidence:** Medium

### Finding 7
- **Summary:** One positive control already exists: explicit markdown paths supplied to `quality_check` are resolved only if they stay inside the active project root. The export pipeline should copy this boundary check instead of inventing a weaker path resolver.
- **Evidence:** `src/scribe_mcp/doc_management/runtime.py:885-906` rejects explicit markdown paths that do not exist, are not `.md`, or resolve outside the active project root.
- **Confidence:** High

### Additional Notes
- The current Knowledge-boundary research proposes fields like `repo_root` and raw `path`; those are useful for local diagnostics but should not be part of the default downstream publication payload.
- The current research recommendation of statuses like `ready_for_review`, `approved`, and `published` does not match the SPEC's canonical status set, so ingestion eligibility should be defined against the SPEC statuses rather than a second vocabulary.
## Technical Analysis
<!-- ID: technical_analysis -->
### Trust-Boundary Map
- **Managed document authoring boundary:** Files under project-local managed-doc roots are Scribe truth inputs. They may contain drafts, private notes, unsafe links, and local-only provenance, so they are not Knowledge-ready merely because they exist.
- **Registration boundary:** Project docs mappings, project registry state, case registry state, content hashes, mtimes, and progress-log locations are internal control-plane data. They support reconciliation and audit, but default export must treat them as sensitive metadata.
- **Generated index boundary:** Research indexes and future topology indexes are derived artifacts. Because generated indexes can sync to the object store automatically, they must carry only publication-safe fields.
- **Storage backend boundary:** SQLite and Postgres are trusted persistence layers inside the Scribe authority boundary. Remote storage is a second trust zone reached over authenticated HTTP and must be treated as internal infrastructure, not a public publication layer.
- **Knowledge ingestion boundary:** Knowledge MCP should receive a sanitized manifest, sanitized topology/work indexes, and chunk payloads. It must not receive raw session state, raw registry rows, raw path inventories, or unrestricted related-doc diagnostics.

### Risks And Required Controls
- **Path exposure:** Never emit absolute `repo_root`, `progress_log_path`, absolute `doc_path`, or resolved `related_docs` targets in Knowledge-facing artifacts. Publish only a repo-relative canonical path when the document lives inside the active repo; otherwise publish no path and record a rejection reason.
- **Configured external roots:** If `dev_plans_dir` resolves outside the active repo, treat all discovered docs from that root as `local_only` and reject them from `knowledge_ingestion_manifest` by default.
- **Archived, stale, or superseded docs:** Deny ingest for documents whose path family is archived/preflight/backup or whose lifecycle status is `archived`, `superseded`, `stale`, `blocked`, `scaffolded`, or `in_progress`.
- **Quality-failing docs:** Deny ingest when `quality_check` reports any blocking warning, including scaffold residue, missing required frontmatter, index drift, or ownership drift.
- **Secrets and private metadata:** Do not export frontmatter wholesale. Restrict exported metadata to an allowlist so arbitrary user-authored keys, tokens, URLs, or notes do not leak through pass-through serialization.
- **User-authored unsafe links:** Treat `related_docs` and markdown links as untrusted content. Only convert them into topology edges when they resolve to repo-internal managed docs under deterministic path rules; never dereference external URLs for ingestion.
- **Cross-project bleed:** Every export query must bind to both normalized repo root and project name or equivalent project key. No aggregate manifest should be built from unscoped registry queries.
- **Remote/backend proxy implications:** Remote storage auth and object-store sync prove transport reachability, not publication safety. Generated exports must be sanitized before they enter any syncable path, because internal remote/object-store replicas may have broader readership than the originating agent session.

### Eligibility And Rejection Rules For `knowledge_ingestion_manifest`
**Eligible only when all conditions are true:**
- Document is classified as a Scribe-managed source document under the active repo and active project.
- Document path is repo-internal and canonical for its source family.
- Lifecycle status is one of `ready` or `complete`.
- Blocking `quality_check` warning count is zero.
- Document is not archived, superseded, stale, scaffolded, blocked, or preflight/backup material.
- Export metadata passes the allowlist and contains no unresolved sanitization requirement.

**Required rejection codes:**
- `REJECT_OUTSIDE_ACTIVE_REPO`
- `REJECT_LOCAL_ONLY_SOURCE`
- `REJECT_NONCANONICAL_PATH`
- `REJECT_ARCHIVED_OR_BACKUP_PATH`
- `REJECT_STATUS_INELIGIBLE`
- `REJECT_QUALITY_BLOCKER`
- `REJECT_SCAFFOLD_RESIDUE`
- `REJECT_MISSING_REQUIRED_METADATA`
- `REJECT_UNSAFE_LINK_TARGET`
- `REJECT_CROSS_PROJECT_SCOPE`
- `REJECT_SANITIZATION_REQUIRED`

### Minimal Metadata Contract For Visibility And Sensitivity
Recommended v1 fields:
- `visibility`: `knowledge_publishable`, `local_only`, or `internal_only`
- `sensitivity`: `normal` or `restricted`
- `path_policy`: `repo_relative`, `hidden`, or `not_applicable`
- `ingestion_eligibility`: `eligible` or `rejected`
- `rejection_reasons`: deterministic list of rejection codes
- `active_project_key`: stable project-scoping identifier used for export filtering
- `source_scope`: `active_repo`, `configured_external_root`, or `unknown`

Guidance:
- `visibility` and `source_scope` are enough for v1 to express whether a document may cross into Knowledge artifacts without inventing semantic labels.
- `sensitivity` should be operator- or template-authored only when necessary; do not add an LLM classifier or freeform sensitivity taxonomy inside Scribe.
- `path_policy` lets export code hide paths without losing determinism about why a path is absent.
- Do not export arbitrary frontmatter maps; project the allowlisted fields into manifest records explicitly.
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Add an export-only sanitization layer that projects internal registry state into publication-safe manifest/index records instead of serializing internal models directly.
- Make repo-internal path verification mandatory for every export candidate, reusing the `quality_check`-style boundary that rejects markdown paths outside the active project root.
- Add deterministic deny rules for archive/preflight/backup families and for lifecycle states outside `ready` and `complete`.
- Require export queries to bind on active repo root plus project name or active project key; reject manifest generation when scope is ambiguous.
- Add an allowlisted metadata projector for Knowledge export fields so arbitrary frontmatter keys and raw link diagnostics cannot leak.
- Treat configured external dev-plan roots as local truth only until an operator explicitly blesses a future cross-repo export contract.

### Long-Term Opportunities
- Add a dedicated publication-readiness check inside existing `quality_check` output so export tooling can consume one authoritative eligibility verdict.
- Add deterministic redaction summaries to manifests, for example counts of hidden paths or restricted docs, so operators can audit why records were withheld without revealing the hidden data.
- Extend project-health/index-health output to flag docs that are syncable internally but not publishable downstream, reducing confusion between persistence and publication.

### Test And Review Requirements For Implementation
- Unit tests for repo-relative path projection, outside-repo rejection, and hidden-path behavior.
- Unit tests proving archived/preflight/backup documents and ineligible lifecycle states are rejected with stable reason codes.
- Unit tests proving user-authored `related_docs` that resolve outside the repo become `REJECT_UNSAFE_LINK_TARGET` and do not surface absolute paths.
- Backend-parity tests across SQLite, Postgres, and Remote storage proving project-scoped export queries cannot bleed documents across repo roots or project names.
- Regression tests for configured absolute `dev_plans_dir` outside the repo showing local discovery may still work while Knowledge export is rejected or downgraded to `local_only`.
- Review checklist requirement: every new manifest/index field must be labeled as `publication_safe`, `internal_only`, or `local_only` during design review before it can ship.
## Appendix
<!-- ID: appendix -->
- **References:**
  - `SPEC.md`
  - `SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md`
  - `research/RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md`
  - `research/RESEARCH_SCRIBE_DOC_REGISTRATION.md`
  - `src/scribe_mcp/doc_management/runtime.py`
  - `src/scribe_mcp/doc_management/utils.py`
  - `src/scribe_mcp/doc_management/manager.py`
  - `src/scribe_mcp/doc_management/special_indexes.py`
  - `src/scribe_mcp/storage/models.py`
  - `src/scribe_mcp/storage/remote.py`
  - `src/scribe_mcp/storage/sqlite/cases.py`
  - `src/scribe_mcp/object_store/keys.py`
- **Attachments:** No separate datasets or diagrams were created for this lane.
