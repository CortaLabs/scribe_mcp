# Global Changelog

## Harden reference provenance, case scope, and frontmatter preservation
- `source_project`: scribe_id_frontmatter_case_workflow_20260515
- `source_entry_id`: 20260515:reference-frontmatter-case-workflow
- `summary`: Added shared reference resolution, scoped entry lookup, project-scoped BUG/security case registry ownership, hardened `link_fix` provenance validation, preserve-first managed-doc frontmatter behavior, and agent recovery documentation for the ID/frontmatter/case workflow. Follow-up release truth bumps the package line to `2.2.21`.

## Enforce managed changelog version governance
- `source_project`: scribe_release_changelog_governance_20260515
- `source_entry_id`: 20260515:release-changelog-governance
- `summary`: Added current-version managed changelog coverage detection, blocking `SCF_CHANGELOG_CURRENT_VERSION_MISSING` quality warnings, readiness/reminder/project_health surfacing, release-governance public docs, and generic SemVer commit-hygiene template guidance. This closes the governance gap where package version bumps could land without accepted managed changelog proof.

## Provenance-safe global changelog reconciliation guard
- `source_project`: scribe_release_changelog_governance_20260515
- `source_entry_id`: 20260515:provenance-safe-global-changelog-guard
- `summary`: Release 2.2.22 fails closed when accepted managed changelog entries lack safe observed provenance, preventing retroactive/backfilled entries from being promoted into the global changelog without a real version source and value.

## No-dotenv-safe settings import
- `source_project`: scribe_mcp
- `source_entry_id`: 20260518:no-dotenv-settings-import
- `summary`: Added the generic `SCRIBE_DISABLE_DOTENV` settings-load guard so import/readiness proof can avoid repo and global dotenv reads, preserved storage backend fail-closed behavior, and bumped the public release line to `2.2.24`.

## Emergency Scribe UX repair wave
- `source_project`: link_fix_emergency_repair_20260521
- `source_entry_id`: 20260521:link-fix-quality-read-recent-ux
- `summary`: Release 2.2.27 makes `link_fix` usable without `scribe_doctor`, adds typed fix artifact metadata, repairs report update targeting, lets `quality_check` inspect repo markdown paths and reports outside the active registry, reports trailing markdown whitespace via `SCF_TRAILING_WHITESPACE`, allows same-repo cross-project `read_recent` inspection without rebinding, and restores stable-session authority for document registration.

## Quality check infrastructure research and architecture package
- `source_project`: quality_check_infrastructure_20260524
- `source_entry_id`: 20260524:quality-check-infrastructure-planning
- `summary`: Created a governed research and architecture package for turning `manage_docs quality_check` into a markdown-aware, lightweight infrastructure gate while preserving the existing public action contract.

## Quality check infrastructure release
- `source_project`: quality_check_infrastructure_20260524
- `source_entry_id`: 20260524:quality-check-infrastructure-release
- `summary`: Release 2.3.0 turns `manage_docs quality_check` into a markdown-aware, lightweight infrastructure gate with nested codeblock protection, structured context parsing, registry-backed scaffold/research/changelog/release-gate rule families, additive result metadata, explicit and inferred `release_gate` checks for current-version changelog coverage and research-context drift, unsuppressible integrity blockers, alias-route proof, explicit markdown-path proof, and a measured no-cache decision.

## Quality check infrastructure hardening release
- `source_project`: quality_check_infrastructure_20260524
- `source_entry_id`: 20260524:quality-check-infrastructure-hardening-2-3-1
- `summary`: Release 2.3.1 closes the post-2.3.0 quality_check hardening gaps by adding the declared `markdown-it-py` runtime dependency, making `MarkdownItScopeProvider` parser-backed for fenced, indented, and inline code scopes with deterministic fallback, enforcing explicit warning severity ordering, proving release-gate trigger metadata in the runtime payload, adding mixed-markdown torture coverage, and fixing repeated identical inline-code localization so duplicate literals map to distinct occurrences.

## Document topology foundation release
- `source_project`: scribe_document_topology_foundation_20260524
- `source_entry_id`: 20260525:document-topology-foundation-release
- `summary`: Release 2.4.0 makes Scribe a deterministic document topology and lifecycle authority with canonical managed-doc metadata, typed topology edges, topology and metadata scan actions, safe and assisted repair modes, hard quality handoff gates, sanitized downstream ingestion manifests, and a generic downstream export boundary that keeps retrieval and semantic ranking outside Scribe.

## Bug and security report follow-up editing
- `source_project`: scribe_mcp_bug_log_tooling_20260604
- `source_entry_id`: 20260604:case-report-manage-docs-followup-2-4-1
- `summary`: Bumped the public release line to `2.4.1`, added obvious `open_bug` and `open_security` follow-up handles, and taught `manage_docs` to resolve governed bug/security reports by case id, governed path, or canonical category metadata before applying edits.

## Quality-check agent actions, bulk validation, and write-barrier safety
- `source_project`: scribe_mcp
- `source_entry_id`: 20260616:quality-check-agent-actions-bulk-write-barrier-2-6-0
- `summary`: Release 2.6.0 makes `manage_docs quality_check` agent-actionable with grouped warning families, ranked `agent_actions`, file/section context, repair hints, and provenance; adds Atlas bulk quality checks for project or bounded doc-list validation; adds concrete quality handoff actions; protects mutation surfaces with write barriers and Postgres backup/restore custody; blocks local operator-only tools over exported remote transport; and supplements sparse Postgres `read_recent` responses from canonical progress logs.

## Runtime latency, telemetry, and binding reuse release
- `source_project`: integrate_system_scribe_latency_20260616t050042z
- `source_entry_id`: 20260616:runtime-latency-telemetry-binding-reuse-2-7-0
- `summary`: Bumped the public release line to `2.7.0`. Scribe now records queryable tool runtimes with durations, correlation IDs, measurement scope, and repo root; `append_entry` returns phase timing; `set_project` has a strict same-agent/session/project/root no-write reuse path that skips redundant writes and mutation-time reminder refresh; successful timing logs stay out of warning output; local probes support JSON output, same-server root comparison, and background telemetry draining; diagnostics expose physical/logical reconciliation for fresh Postgres installs with existing file-backed Scribe artifacts.

## Case registry and Council closeout patch
- `source_project`: integrate_system_scribe_latency_20260616t050042z
- `source_entry_id`: 20260616:case-registry-council-closeout-2-7-1
- `summary`: Release 2.7.1 repairs governed bug/security report path targeting so explicit report paths do not collapse onto unrelated `report.md` basenames, closes shared case-registry rows for resolved/validated/implemented fix statuses, and completes the Council hook/guidance readback for bind-once `set_project` behavior.

## Furnace-project quality-check O(N^2) elimination + read_recent fixes
- `source_project`: scribe_scale_cache_arch
- `source_entry_id`: 20260616:furnace-quality-check-perf-2-7-2
- `summary`: Release 2.7.2 eliminates two O(N^2) defects in managed-doc quality analysis that made set_project/prepare_context ~20s on large ("furnace") projects: (1) per-inline-span line-number computation via str.count("\n", 0, offset) replaced with a precomputed line-offset index + bisect in quality/scopes.py; (2) offset_in_scope linear any()-over-scopes replaced with a per-kind sorted interval index + bisect in quality/context.py. Measured: an 18,867-line PHASE_PLAN quality check dropped 18.0s -> 1.15s; furnace set_project ~20.3s -> ~2.1s; warm rebind stays ~70ms. Also in this line: read_recent limit/n now returns exactly the requested row count; progress-log supplementation gated for DB-authoritative projects; readiness doc-quality cache key is O(1) via directory-stat sentinel; count_entries() uses the scribe_metrics counter as an O(1) fast path; session-binding lookups cached; research-index rglob hoisted out of per-doc loop. No public API/CLI/schema contract changes (PATCH).
