# Release Surface

Baseline date: **2026-04-08**  
Applies to: **v2.5 compatibility baseline**

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
