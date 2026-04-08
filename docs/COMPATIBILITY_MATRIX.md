# Compatibility Matrix

Frozen on **2026-04-05** from fresh git-archived release artifacts built for
the synchronized compatibility review.

## Release decision

**Recommendation:** the next public release should remain a **compatibility
release**, **not `v3`**.

Why:

1. The built `scribe-mcp` wheel now cleanly ships the public core runtime and
   console scripts without publishing a `council.templates` entry point.
2. The optional council/template provider is now isolated in the separate
   `scribe-council` wheel, which depends on `scribe-mcp==2.2` and owns the
   `council.templates` entry point.
3. The only remaining compatibility residue is the explicit
   `scribe_mcp.council_templates` import shim, and that shim already marks
   itself for removal in the next breaking release and no later than `v3`.
4. The remote/client and `council_mcp` changes are additive and optional:
   local/core remains the default posture, while authenticated remote/client
   remains opt-in.

`v3` becomes justified when the deprecated shim is removed and the project is
ready to intentionally break the legacy import path. This frozen artifact set
does **not** require that break yet.

## Release truth rules

For this synchronized wave, release truth comes from the built wheels/sdists
plus tracked docs/manifests that explain them.

Not release truth:

- repo-root overlays such as `.mcp.json`, `opencode.json`, `AGENTS.md`,
  `CLAUDE.md`, `.claude/`, `.codex/`, and `.council/`
- local runtime state such as `.scribe/cli/*.json`, `.scribe/state/*.json`,
  and `.scribe/logs/*`
- stale generated trees such as `build/`, `dist/`, and `*.egg-info/`

The fresh artifacts inspected for this decision contain none of those repo-root
overlay/runtime paths.

## Supported combinations

| `scribe-mcp` | `scribe-council` | `council_mcp` | Status | Intended use | Artifact-backed evidence |
| --- | --- | --- | --- | --- | --- |
| `2.2` | — | — | **Supported** | Default local/core Scribe install. Use `scribe-server` / `scribe` and keep local/core as the default posture. Optional authenticated remote/client remains available via docs and env config. | `scribe_mcp-2.2-py3-none-any.whl` publishes only console scripts; no `council.templates` entry point is present. |
| `2.2` | `2.2` | — | **Supported** | Add the optional council/template provider when you also need Scribe's council extension assets. | `scribe_council-2.2-py3-none-any.whl` owns `[council.templates] scribe-council = ...` and depends on `scribe-mcp==2.2`. |
| `2.2` | — | `2.0.0` | **Supported / recommended synchronized pair** | `council_mcp` consuming installed `scribe-server` for local/core stdio, with optional authenticated SSE remote/client via `SCRIBE_SSE_ENDPOINT` + `SCRIBE_REMOTE_AUTH_TOKEN`. | `council_mcp-2.0.0-py3-none-any.whl` publishes `council`; docs and artifacts align on installed-package `scribe-server` instead of sibling-repo launch commands or repo-root overlays. |
| `2.2` | `2.2` | `2.0.0` | **Supported when optional Scribe extension assets are also needed** | Same as the synchronized pair above, plus optional Scribe council/template assets in the same environment. | `scribe-council` remains additive; `council_mcp` does not require it for the transport/runtime contract. |

## Explicitly unsupported or not signed off here

| Combination / practice | Status | Why |
| --- | --- | --- |
| `scribe-council` without `scribe-mcp==2.2` | **Unsupported** | The built package depends on `scribe-mcp==2.2`. |
| Public guidance that depends on repo-root `.mcp.json`, `opencode.json`, `AGENTS.md`, `.claude/`, `.codex/`, or `.council/` | **Unsupported** | Fresh wheels/sdists do not define release truth from those overlays. |
| Public downstream guidance that tells users to run `cd ../scribe_mcp && python -m server` | **Unsupported** | The frozen contract is the installed `scribe-server` command. |
| Unversioned or mismatched combinations outside the frozen `scribe-mcp 2.2` / `scribe-council 2.2` / `council_mcp 2.0.0` wave | **Not signed off by 6.4-A** | This package only freezes the synchronized Phase 6 release set. |

## What the artifacts actually ship

### `scribe-mcp 2.2`

- Ships console scripts including `scribe-server`.
- Does **not** publish a `council.templates` entry point.
- Still ships one deprecated import shim at
  `scribe_mcp/council_templates/__init__.py`.

### `scribe-council 2.2`

- Ships the optional `council.templates` provider.
- Depends on `scribe-mcp==2.2`.
- Exists only to carry optional council/template assets; it is not required for
  standard local/core Scribe usage.

### `council_mcp 2.0.0`

- Ships the `council` console script and its own `council.templates` entry
  point.
- Aligns with the installed-package `scribe-server` contract for Scribe
  integration.
- Treats remote/client as optional and authenticated rather than as the default
  posture.

## Cross-repo public contract frozen by this matrix

- **Default:** local/core remains the public default.
- **Optional:** remote/client remains optional and authenticated.
- **Optional extension only:** `scribe-council` is not the core runtime; it is
  additive when council/template assets are needed.
- **Breaking removal deferred:** the legacy `scribe_mcp.council_templates`
  import path remains only as a documented compatibility shim for this wave.
