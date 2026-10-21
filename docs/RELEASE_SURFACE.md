# Release Surface

Updated: **2026-10-21**
Applies to: **v3.0.1 development candidate; integration and fleet acceptance pending**

## Development candidate

Version 3.0.1 holds a configured SQLite connection for schema bootstrap to reduce repeated last-connection teardown, and closes newly created connections when configuration fails. Existing schema checks, commits, durability settings and initialization ordering are retained.

Version 3.0.0 introduced the Doctor default change: ordinary calls retain diagnostics and skip physical/logical inventory collection. Callers requiring the existing full v1 report must pass `reconciliation="full"`. Deferred results expose a null report and explicit `not_collected` metadata; full results preserve existing availability limits. The compatibility matrix and usage guide document migration.

This checkpoint is not a completed release or fleet rollout. Broader binding/schema work, integrated validation and actual failing-peer acceptance remain open. Public stdio validation is required if it is the affected peer's effective path. The 2.15.x maintenance candidate remains separate.

## Earlier checkpoint repairs

Version 2.15.19 corrects doctor module-origin reporting and repairs the existing document-test setup through real SDK ingress,
persisted caller bindings, and canonical metadata readback. All 53 original cases
pass with their assertions retained. Invalid actions retain both consumer and RPC
rejection checks; dependency faults still exercise partial-registration outcomes.
This is correctness evidence, not a performance or fleet certification. Broader
integration, public stdio, and actual peer acceptance remain open.

Version 2.15.17 carries the reviewed nonselecting metadata correction into this
larger development branch. Document registration refreshes existing stored
metadata and cache without changing caller or sibling project selection.
Remaining integration failures, the planned binding/schema work, public stdio
and actual peer acceptance remain release blockers. No publication or live
checkout update is implied.

Version 2.15.13 removes project-selection writes from document metadata updates.
Creating, editing, registering, or rehoming a document preserves the caller's
default project and sibling session bindings. Existing authority checks remain.
This candidate has not been promoted to the fleet. Internal-profile SDK canaries
pass; public-profile stdio binding and actual fleet acceptance remain open.

Version 2.15.12 reuses the canonical export-policy digest during document creation.
Equivalent grant lists receive the same digest in either order, while emitted
metadata order, document text, default-private behavior, and authority checks
remain unchanged.

Version 2.15.11 preserves complete bug and security report narratives during
metadata healing. Long descriptions, Unicode, line breaks, and code fences retain
their text; ordinary metadata sanitization and length limits remain enforced.

Version 2.15.10 preserves SQLite project and session extensions during canonical
identity upgrades, including typed values, column definitions, indexes, views,
and triggers. Legacy projects receive repository identities before startup indexes
are created. Project deletion and document metadata updates retain sibling
project data when labels are ambiguous.

Version 2.15.9 verifies project reads against the current caller binding and canonical
repository identity. Advisory caches and compatibility labels cannot authorize a
project selection; warm reads recheck the stored binding.

Version 2.15.8 loads tool definitions before validating a first call that precedes
tool discovery. Unknown tools and invalid arguments remain refused.

Version 2.15.7 preserves literal whitespace inside fenced artifacts across section
and frontmatter updates while retaining prose whitespace cleanup.

Version 2.15.6 makes PostgreSQL project deletion atomic. Ambiguous names refuse
deletion, and concurrent same-name projects retain their data and session context.

Version 2.15.5 strengthens binding recovery across reconnects while retaining
verified caller and repository scope.

Version 2.15.4 removes the obsolete onboarding-directory packaging rule.
Canonical onboarding and integration skills remain included from `skills/`
and the shipped plugin bundles.

Version 2.15.3 replaces a workstation-specific checkout path in the isolated
validation runbook with a portable placeholder.

Version 2.15.2 reduces repository dependency-scan work. Excluded build and cache
directories are pruned before traversal, and import extraction visits AST
statement containers without walking unrelated expression subtrees. Dependency
graphs, breadth-first import order, scan limits, and symlink behavior are retained.

Version 2.15.1 replaces the PostgreSQL session-binding classifier trigger in one
atomic batch. Concurrent binding writers retain canonical project classification
through startup, including databases upgraded from the legacy binding schema.
Release checks also handle normal TCP cleanup after a legacy SSE server stops
and use explicit synthetic credential fixtures.

## Public contract

Treat these as public release truth:

- Shipped package source and manifests:
  - `pyproject.toml`
  - `MANIFEST.in`
  - `src/scribe_mcp/**`
- Public docs and examples:
  - `README.md`
  - `docs/**`
  - `docs/examples/**`
  - `skills/**`

## Runtime truth in public docs

Public docs must keep these runtime truths aligned with current source:

- Postgres is the default storage posture.
- Standalone SQLite is explicit local-only opt-in.
- Remote/client remains internal compatibility only for this release line and is excluded by public-release posture.
- `SCRIBE_REMOTE_URL` is documented as service root; `/health` and `/sse` are distinct paths with different roles.
- Codex projection is documented through `scribe plugins project-codex`.
- Managed-doc hygiene behavior is public release truth: scaffold-aware `quality_check`, grouped `project_health` signals, project-local managed-doc preflight archives, centralized `edit_file` backups, canonical research artifact naming, and stale index-backup cleanup.
- Changelog/version memory behavior is public release truth: project `CHANGELOG.md` is curated source, `.scribe/docs/GLOBAL_CHANGELOG.md` is derived by preview/apply reconciliation, version context is advisory observed evidence, and malformed changelog escaped-newline content is a blocking quality failure.
- Missing current-version changelog coverage is a blocking warning (`SCF_CHANGELOG_CURRENT_VERSION_MISSING`) surfaced by `quality_check`, reminders, and `project_health` quality digests.
- The public release line retains the fail-closed provenance guard for changelog/global reconciliation, deterministic document topology, metadata scan/repair, quality handoff gates, agent-ready quality-check summaries/actions, bulk managed-doc checks, sanitized downstream export manifests, and governed case-registry closeout for resolved fixes.
- Fast same-binding `set_project` reuse, queryable runtime telemetry, append-entry phase timing, physical/logical reconciliation diagnostics, JSON probe output, same-server root comparison, clean success-path timing logs, and background telemetry drain behavior are public runtime truth for this release line.
- Bug/security case reports are governed repo-root documents; `open_bug`/`open_security` expose follow-up handles and `manage_docs` resolves those reports without dev-plan name guessing.
- Scribe-owned write barriers, owner-only Postgres backup/restore custody, sparse `read_recent` progress-log supplementation, and remote blocking for local operator-only tools are public runtime safety behavior.
- Downstream topology exports are generic publication artifacts. Public Scribe must not hard-code a private retrieval product as the consumer or source of truth.

## Local/operator boundary

Treat these as local/operator-only, not public contract:

- Repo overlays and agent/tooling configuration at repo root
- Local runtime state and logs under `.scribe/**`
- Build output and caches (`build/`, `dist/`, `*.egg-info/`, `__pycache__/`)
- Generated authoring/runtime overlays unless a future exported copy is intentionally tracked as public support material

If a path is workstation-specific or runtime-generated, it is not public guidance.

## Plugin and bridge boundary

Public docs should describe only shipped plugin/bridge surfaces:

- Core runtime/plugin framework in `src/scribe_mcp/bridges/**`
- Tracked onboarding and integration guides in `skills/**`
- Generic Claude and Codex plugin bundles in `.claude-plugin/` and `.codex-plugin/`

Do not present local manifests, local bridge config, unpromoted generated outputs, or local operator adapters as shipped public surface.

## Practical release check

Before publishing guidance, confirm all referenced files are:

1. Tracked in the repo
2. Part of shipped package/manifests or public docs/examples
3. Not runtime-generated and not workstation-specific

Reconnect hardening recovers scope from the persisted binding, rejects caller-supplied session identity as authority, and preserves legitimate reconstructed sessions. Public path validation and credential-shaped test fixtures remain intact.
