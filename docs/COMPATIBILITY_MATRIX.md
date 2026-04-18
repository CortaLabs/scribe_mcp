# Compatibility Matrix

Baseline date: **2026-04-18**  
Release framing: **v2.5 compatibility baseline**

## Baseline contract

This baseline keeps compatibility posture for the 2.5 documentation wave:

- **Core package version:** `scribe-mcp==2.2.5`
- **Optional template package:** `scribe-council==2.2.5`
- **Default runtime posture:** Postgres-backed runtime contract
- **Standalone SQLite posture:** explicit local-only opt-in (`SCRIBE_MODE=standalone` + `SCRIBE_STORAGE_BACKEND=sqlite`)
- **Remote/client posture:** internal compatibility only, excluded by `SCRIBE_RELEASE_PROFILE=public`

`v3` is out of scope for this baseline.

## Supported combinations

| Core (`scribe-mcp`) | Optional templates (`scribe-council`) | Status | Intended use |
| --- | --- | --- | --- |
| `2.2.5` | — | Supported | Standard install for local/core usage. |
| `2.2.5` | `2.2.5` | Supported | Add optional template bundle when template assets are needed. |

## Not supported by this baseline

| Combination / practice | Status | Why |
| --- | --- | --- |
| `scribe-council` without `scribe-mcp==2.2.5` | Unsupported | Optional package explicitly depends on `scribe-mcp==2.2.5`. |
| Public onboarding that treats remote/client as generally available | Unsupported | Public release profile fail-closes remote/client startup. |
| Standalone SQLite presented as default runtime posture | Unsupported | Runtime settings default storage backend to Postgres. |
| Guidance that depends on repo-local/operator files as public setup | Unsupported | Those files are local convenience, not release contract. |
| Unversioned or mixed versions outside the baseline above | Not signed off | This baseline only certifies the combinations listed in this document. |

## What is shipped

### `scribe-mcp 2.2.5`

- CLI entry points include: `scribe`, `scribe-mcp`, `scribe-server`, `scribe-server-sse`
- Core runtime and tool surface in `src/scribe_mcp/**`
- One compatibility shim remains in `src/scribe_mcp/council_templates/__init__.py`

### `scribe-council 2.2.5` (optional)

- Ships optional template assets from `packages/scribe_council/src/scribe_council/**`
- Provides `council.templates` entry point
- Depends on `scribe-mcp==2.2.5`

## Versioning contract

- `main` is release-bound for `scribe-mcp`: pushes that touch package/release surfaces trigger the PyPI publish workflow.
- Any release-bound change must bump `pyproject.toml` before merge/push to `main`.
- If the optional template package contract changes in lockstep, `packages/scribe_council/pyproject.toml` must be bumped too so the documented baseline stays truthful.

## Public boundary summary

- Public install/setup guidance must map to shipped package files and tracked docs.
- Local/operator overlays are never release truth.
- This baseline is intentionally conservative: compatibility first, breaking changes deferred.
