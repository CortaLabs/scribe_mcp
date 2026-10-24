# Release Surface

Updated: **2026-10-24**
Applies to: **2.15.24 maintenance candidate; publication and fleet validation pending**

## Maintenance scope

This candidate carries verified-binding recovery after runtime reconstruction, first-call tool-definition loading, nonselecting document metadata updates, atomic PostgreSQL classifier-trigger replacement, and canonical export-policy digest generation. Public arguments and existing storage APIs are unchanged. The planned key-only binding API, migration 008, new receipt guarantees and broader document engine are outside this cut.

Version 2.15.20 corrects doctor module-origin reporting and removes the obsolete onboarding-directory packaging include. The loaded package directory is distinct from the configured project root; canonical skills remain included from `skills/` and the plugin bundles.

Version 2.15.24 stops treating valid JSON metadata strings as expression syntax. Comparisons such as `payload <=2048 bytes` and `1 > 2` retain their operators without invented backslashes or quotes. Request healing no longer labels these unchanged values as corrections. Log-delimiter handling, existing size bounds and non-JSON fallback rules remain.

Version 2.15.23 preserves literal trailing spaces and tabs inside fenced code across section replacements and frontmatter updates. Prose cleanup and final-newline behavior are retained. Persisted regression checks cover backtick and tilde fences, shorter inner fences, Unicode and actual metadata writes.

Version 2.15.22 corrects the build-backend minimum to setuptools 77.0.3 for its SPDX license metadata.

Version 2.15.21 replaces destructive build-directory cleanup with an isolated tracked-source snapshot. Existing outputs, metadata and source bytes are preserved; same-version output collisions are rejected before effects. Both distributions must pass Twine and the existing private-artifact checks before exclusive publication. The source distribution includes nested Python regression tests and tracked Markdown fixtures, retaining the existing manifest exclusions.

Source and isolated checks do not establish deployment acceptance. The actual failing client path must pass against the pinned candidate before fleet rollout, including public stdio first binding if it uses that path. A successful probe under another profile is insufficient; public stdio compatibility remains an open release boundary. No private orchestration configuration, generated agents, templates or runtime state belongs in the public package.

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
- v2.7.1 keeps the fail-closed provenance guard for changelog/global reconciliation, deterministic document topology, metadata scan/repair, quality handoff gates, agent-ready quality-check summaries/actions, bulk managed-doc checks, sanitized downstream export manifests, and governed case-registry closeout for resolved fixes.
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

Do not present local manifests, local bridge config, unpromoted generated outputs, or local operator adapters as shipped public surface.

## Practical release check

Before publishing guidance, confirm all referenced files are:

1. Tracked in the repo
2. Part of shipped package/manifests or public docs/examples
3. Not runtime-generated and not workstation-specific
