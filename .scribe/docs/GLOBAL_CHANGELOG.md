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
