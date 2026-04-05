# Release Surface Policy

This document defines the public release surface for `scribe-mcp` and the boundary between **tracked repo truth** and **repo-local runtime/operator overlays**.

## 1. Repo truth vs. local overlays

Treat the following as **repo truth** for public release work:

- tracked package source and manifests such as `src/scribe_mcp/**`, `packages/scribe_council/**`, `pyproject.toml`, and `MANIFEST.in`
- tracked release docs and tracked examples under `docs/**` and `docs/examples/**`
- shipped bridge/plugin assets that live in tracked package paths

Treat the following as **local overlays or runtime state**, not public release truth:

- `.council/`
- `.mcp.json`
- `opencode.json`
- `.scribe/cli/*.json`
- `.scribe/state/*.json`
- `.scribe/logs/*`
- operator-specific `AGENTS.md`, `.claude/**`, and `.codex/**` material

If a local overlay exists in the repo root, it may be useful for one operator's workstation, but it is **not** the public contract for downstream users.

## 2. Public guidance must point to tracked docs/examples

Do not tell users to copy the repo-root `.mcp.json`, `opencode.json`, `AGENTS.md`, `.claude/`, or `.codex/` overlays.

Use these tracked examples instead:

- `docs/examples/mcp.json.example`
- `docs/examples/opencode.json.example`

Those files are the release-safe examples for client bootstrap guidance in this repo.

## 3. Runtime state is mutable and local-only

These paths are runtime/operator surfaces and should be treated as mutable local state:

- `.scribe/cli/*.json` for per-operator CLI/session state
- `.scribe/state/*.json` for local runtime state such as rotation/audit bookkeeping
- `.scribe/logs/*` for local log output

Runtime files may exist during development, but they do not define what ships. They also stay out of object-store sync and packaging decisions.

## 4. Build artifacts are never release truth

The following are stale or generated artifact surfaces and must not be used to define package scope:

- `build/`
- `dist/`
- `*.egg-info/`
- `__pycache__/`

Release decisions must come from tracked source/manifests/docs, not from generated trees left behind by earlier builds.

## 5. Bridge package boundary

For bridge/runtime work, the release contract is:

- **Core (`scribe-mcp`)** ships the generic bridge runtime contract only: manifest loading, plugin/runtime binding, policy enforcement, hook execution, and server wiring.
- **Optional extension (`scribe-council`)** owns any council/federation-specific shipped bridge manifests, bridge plugins, hook adapters, scaffold/export assets, and docs/examples that require council semantics.
- **Local-only overlays** stay local: repo/operator manifests and adapters under `.scribe/config/bridges/`, `.council/`, or other workstation-specific paths are not public release truth.

One additional release rule is mandatory: a bridge manifest must resolve to a real runtime plugin in the same owning package or local overlay. Manifest-only inactive placeholders are not a supported shipped surface.

## 6. Practical release rule

When deciding whether a file belongs in public guidance or packaging:

1. Prefer tracked package source, tracked docs, and tracked examples.
2. Reject repo-root operator overlays and mutable runtime outputs as release truth.
3. Reject generated build artifacts as release truth.
4. If a public example is needed, add it under `docs/examples/` instead of pointing to a repo-root overlay file.
