# Compatibility Matrix

Baseline date: **2026-05-12**
Release framing: **v2.2.22 compatibility baseline**

## Baseline contract

This baseline keeps compatibility posture for the 2.2.22 documentation wave:

- **Core package version:** `scribe-mcp==2.2.22`
- **Default runtime posture:** Postgres-backed runtime contract
- **Standalone SQLite posture:** explicit local-only opt-in (`SCRIBE_MODE=standalone` + `SCRIBE_STORAGE_BACKEND=sqlite`)
- **Remote/client posture:** internal compatibility only, excluded by `SCRIBE_RELEASE_PROFILE=public`
- **Governed-memory posture:** project `CHANGELOG.md` is curated source; `.scribe/docs/GLOBAL_CHANGELOG.md` is derived output

`v3` is out of scope for this baseline.

## Supported combinations

| Core (`scribe-mcp`) | Status | Intended use |
| --- | --- | --- |
| `2.2.22` | Supported | Public Scribe install for local/core usage. |

## Not supported by this baseline

| Combination / practice | Status | Why |
| --- | --- | --- |
| Public onboarding that treats remote/client as generally available | Unsupported | Public release profile fail-closes remote/client startup. |
| Standalone SQLite presented as default runtime posture | Unsupported | Runtime settings default storage backend to Postgres. |
| Guidance that depends on repo-local/operator files as public setup | Unsupported | Those files are local convenience, not release contract. |
| Unversioned or mixed versions outside the baseline above | Not signed off | This baseline only certifies the combinations listed in this document. |

## What is shipped

### `scribe-mcp 2.2.22`

- CLI entry points include: `scribe`, `scribe-mcp`, `scribe-server`, `scribe-server-sse`
- Core runtime and tool surface in `src/scribe_mcp/**`
- Managed-doc hygiene includes scaffold-aware quality checks, project-local preflight archive routing, canonical research artifact naming, stale index-backup cleanup, and quality-check recovery for registered or discoverable package/research docs.
- Managed-doc project memory includes project `CHANGELOG.md`, derived global changelog reconciliation, advisory version context, research-context drift warnings, lifecycle/body-status mismatch warnings, and malformed changelog escaped-newline blocking checks.
- Managed-doc release governance also blocks missing accepted coverage for the active `pyproject.toml` version via `SCF_CHANGELOG_CURRENT_VERSION_MISSING` in `quality_check`, reminders, and `project_health`.

## Versioning contract

- `main` is release-bound for `scribe-mcp`: pushes that touch package/release surfaces trigger the PyPI publish workflow.
- Any release-bound change must bump `pyproject.toml` before merge/push to `main`.

## Public boundary summary

- Public install/setup guidance must map to shipped package files and tracked docs.
- Local/operator overlays are never release truth.
- This baseline is intentionally conservative: compatibility first, breaking changes deferred.
