# Release Surface

Baseline date: **2026-04-18**  
Applies to: **v2.2.8 public release line**

## Public contract

Treat these as public release truth:

- Shipped package source and manifests:
  - `pyproject.toml`
  - `MANIFEST.in`
  - `src/scribe_mcp/**`
  - `packages/scribe_council/**` (optional package)
- Public docs and examples:
  - `README.md`
  - `docs/**`
  - `docs/examples/**`

## Runtime truth in public docs

Public docs must keep these runtime truths aligned with current source:

- Postgres is the default storage posture.
- Standalone SQLite is explicit local-only opt-in.
- Remote/client remains internal compatibility only for this release line and is excluded by public-release posture.
- `SCRIBE_REMOTE_URL` is documented as service root; `/health` and `/sse` are distinct paths with different roles.
- Codex projection is documented through `scribe plugins project-codex`.

## Local/operator boundary

Treat these as local/operator-only, not public contract:

- Repo overlays and agent/tooling configuration at repo root
- Local runtime state and logs under `.scribe/**`
- Build output and caches (`build/`, `dist/`, `*.egg-info/`, `__pycache__/`)

If a path is workstation-specific or runtime-generated, it is not public guidance.

## Plugin and bridge boundary

Public docs should describe only shipped plugin/bridge surfaces:

- Core runtime/plugin framework in `src/scribe_mcp/bridges/**`
- Optional shipped template/extension assets in `packages/scribe_council/src/scribe_council/**`

Do not present local manifests, local bridge config, or local operator adapters as shipped public surface.

## Practical release check

Before publishing guidance, confirm all referenced files are:

1. Tracked in the repo
2. Part of shipped package/manifests or public docs/examples
3. Not runtime-generated and not workstation-specific
