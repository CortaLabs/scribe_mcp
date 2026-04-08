---
id: scribe_release_polish_20260408-architecture
title: "Release Polish Architecture Guide \u2014 `scribe_release_polish_20260408`"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:50:00 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Release Polish Architecture Guide — `scribe_release_polish_20260408`

Status: planning baseline complete on 2026-04-08.

## 1. Problem Statement

This project exists because the current release surface is internally inconsistent. The repo already contains a credible package-first public story, but it is split across partially modernized docs, a Codex-only plugin bootstrap command, ambiguous runtime terminology, incomplete downstream hygiene boundaries, an unclear shipped test contract, and one confirmed security blocker in tracked runtime residue.

The existing `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md` were scaffold placeholders. They did not provide a bounded issue inventory, an execution-safe package graph, or acceptance criteria strong enough for review and implementation. This document replaces that placeholder set with the contract implementation teams must follow.

## 2. Verified Scope And Constraints

### Scope In

- Public-doc truth across the tracked release-facing docs, with `README.md` acting as the high-level front door and docs index.
- Professional install UX for both human operators and automation, while keeping `install.sh` scriptable and non-interactive by default.
- First-class public bootstrap paths for both Codex and Claude plugin consumers.
- A shipped public-safe `scribe-integration` skill in both plugin bundles.
- Public-surface hygiene for tracked local, runtime, and generated residue.
- A clean shipped-vs-dev regression contract for tests and packaging.
- Runtime terminology cleanup so local/core, remote/client, and SSE postures are documented consistently.
- Remediation planning for the confirmed secret leak in `.scribe/backups/postgres/latest_backup_manifest.json`.
- Final review and signoff as a separate package.

### Scope Out

- New product features beyond release polish.
- Broad council or agent redesign outside the shipped public plugin bundles.
- Storage-layer redesign unrelated to release polish.
- Large refactors of test logic beyond what is needed to create a clean public/dev split and shipped regression contract.

### Non-Negotiables

- `README.md` stays high-level and professional; it must explain what Scribe is and act as a docs index.
- `docs/RELEASE_FILE_MAP.md` stays a dedicated file-map document and is linked from README rather than inlined.
- Public truth is anchored in tracked docs and tracked examples, not repo-local overlays.
- `install.sh` remains scriptable and automation-safe by default.
- Heavy dependencies remain optional; core install must not pick up Postgres or S3 extras by default.
- `scribe-integration` ships in both plugin bundles as a public-safe Scribe-focused skill and does not need templating work in this wave.
- `.scribe/**`, `docs/dev_plans/**`, repo-local overlays, and generated residue are not public release truth.
- The known credential leak is a release blocker and must be cleared before signoff.

## 3. Governing Design Decisions

1. Public truth is defined by tracked release docs plus tracked examples.
   Why: the repo already distinguishes public contract from local overlays in `README.md`, `docs/RELEASE_SURFACE.md`, and `docs/RELEASE_FILE_MAP.md`. The remaining work is alignment, not reinvention.

2. README and file-map finalization are late-phase work owned by Package 1.
   Why: `README.md` and `docs/RELEASE_FILE_MAP.md` should describe the final command surface, file boundaries, and shipped docs set after structural churn lands. Early edits from Phase 2 packages would immediately drift.

3. Installer and client bootstrap stay separate concerns.
   Why: `install.sh` is already a deterministic checkout installer. Plugin projection/bootstrap is a separate UX problem and belongs in dedicated CLI/plugin packages rather than inside the base installer.

4. Codex and Claude public bootstrap must be symmetric.
   Why: the current public CLI exposes only `plugins project-codex`, while the repo already ships a Claude bundle. The release story is not stable until both clients have first-class public paths.

5. Runtime-mode terminology must be normalized around four truths.
   The four truths are local/core stdio default, package entrypoints, optional authenticated SSE server, and optional authenticated remote/client posture.
   Why: the implementation is coherent, but the current docs use overlapping names (`scribe`, `scribe-server`, `scribe-server-sse`, `trusted-sse`, transport auth token names) that blur operator intent.

6. Public-surface cleanup is both policy and code.
   Why: `.gitignore`, packaging manifests, shipped plugin exceptions, and tracked runtime residue must all agree. Documentation alone is insufficient.

7. The test contract must become explicit.
   Why: `MANIFEST.in` currently contains a one-off test exclusion instead of a principled shipped-vs-dev boundary. The release surface should expose only intentional regression assets.

8. Security-blocker closure requires credential disposition, not just artifact cleanup.
   Why: removing the tracked manifest and hardening generation stop repeat exposure, but the already exposed credential remains a live risk until Package 7 records completed rotation or explicit proof that the leaked secret is already invalidated and replaced.

9. Runtime terminology work must cite the canonical runtime research conclusions.
   Why: the governed baseline relies on `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408.md`, specifically the `# Summary`, `# Supported Modes and Intended Audience`, `# Export vs Runtime Contract`, and `# Naming and Contract Drift` sections. The accidental `.md.md` creation path is historical noise, not a planning input.

## 4. Verified Issue Inventory

| Package | Area | Current gap | Verified evidence | Change class |
| --- | --- | --- | --- | --- |
| 1 | Public docs truth | README is directionally good but does not yet serve as the complete front door; older public docs still teach repo-checkout flows | `README.md`; `docs/GLOBAL_DEPLOYMENT_GUIDE.md`; `docs/mcp_server_guide.md`; `docs/whitepapers/scribe_mcp_whitepaper.md`; `RESEARCH_PUBLIC_DOCS_TRUTH_20260408.md` | Docs only |
| 2 | Install UX | `install.sh` is deterministic today but not presented as the professional public installer story; package-vs-automation guidance is split | `install.sh`; `pyproject.toml`; `requirements.txt`; `RESEARCH_INSTALL_PLUGIN_UX_20260408.md` | Code plus docs |
| 3 | Plugin bootstrap parity | Only `plugins project-codex` exists publicly; no Claude parity; shipped skill name is `scribe-mcp-usage`, not `scribe-integration` | `src/scribe_mcp/cli/main.py`; `src/scribe_mcp/scripts/project_codex_plugin.py`; `plugins/codex/**`; `plugins/claude/**`; `.agents/plugins/marketplace.json`; `.gitignore` skill-pack exceptions | Code plus docs |
| 4 | Public-surface hygiene | Runtime-local and generated clutter policy is only partially enforced in ignore rules and tracked surfaces | `.gitignore`; `docs/RELEASE_SURFACE.md`; `docs/RELEASE_FILE_MAP.md`; `RESEARCH_PUBLIC_SURFACE_HYGIENE_20260408.md` | Code plus docs |
| 5 | Test/public split | The shipped regression boundary is implicit and weak; `MANIFEST.in` excludes one test file instead of defining a clean public/dev test policy | `MANIFEST.in`; `tests/**`; `RESEARCH_PUBLIC_SURFACE_HYGIENE_20260408.md` | Code plus docs |
| 6 | Runtime terminology | The public story still mixes CLI dispatcher, stdio runtime, SSE runtime, and remote/client posture language, and the canonical runtime research conclusions must stay the single baseline for fixing that drift | `docs/REMOTE_CLIENT.md`; `docs/RELEASE_SURFACE.md`; `pyproject.toml`; `src/scribe_mcp/__main__.py`; `src/scribe_mcp/server_sse.py`; `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408.md` (`# Summary`, `# Supported Modes and Intended Audience`, `# Export vs Runtime Contract`, `# Naming and Contract Drift`) | Code plus docs |
| 7 | Security blocker | A tracked backup manifest still contains a raw Postgres password in `pg_dump_command`, and the exposed credential is not fully remediated until rotation or explicit invalidation proof is recorded | `.scribe/backups/postgres/latest_backup_manifest.json`; `.gitignore`; `docs/RELEASE_FILE_MAP.md`; `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_RELEASE_SECURITY_SANITY_20260408.md`; `SEC-2026-04-08-0001` | Code plus ops/docs |
| 8 | Final review/signoff | No explicit release-gate package exists to verify the final public surface after the above work lands | This architecture package plus operator requirements | Review only |

## 5. Domain Split And Execution Model

This wave decomposes into four domains so implementation can stay bounded:

- Domain A: security and surface boundary enforcement.
  Packages: 7 and 4. Package 7 is not complete until artifact removal, generator hardening, and credential rotation or explicit invalidated-secret proof are all recorded.
- Domain B: installer and plugin bootstrap surfaces.
  Packages: 2 and 3.
- Domain C: runtime contract and public terminology.
  Package: 6.
- Domain D: shipped docs and regression surface.
  Packages: 5, 1, and 8.

### Dependency Rules

- Package 7 must land before Package 4 finalizes overlapping ignore/runtime-local policy, before any structural package is treated as release-clean, and before Package 8 can sign off. Its exit criteria are artifact removal, generator hardening, and credential rotation or explicit invalidated-secret proof.
- Package 4 must establish the cleanup boundary before packages 2, 3, 5, and 6 finalize their surfaces.
- Packages 2, 3, 5, and 6 may run in parallel once Package 4 lands, provided file ownership is respected.
- Package 6 may update supporting runtime docs and help text, but it does not own `README.md` or `docs/RELEASE_FILE_MAP.md`.
- Package 1 must run after Packages 2, 3, 4, 5, and 6 because README and file-map finalization must describe the landed structure.
- Package 8 is last and is blocked on all prior packages.

## 6. File Ownership Matrix

| Package | Primary ownership |
| --- | --- |
| 1 | `README.md`, `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/mcp_server_guide.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, `docs/RELEASE_FILE_MAP.md`, `docs/BRIDGE_DEVELOPMENT.md` if index links need adjustment |
| 2 | `install.sh`, `pyproject.toml`, `requirements.txt`, installer-facing docs/examples only when needed |
| 3 | `src/scribe_mcp/cli/main.py`, `src/scribe_mcp/scripts/project_codex_plugin.py` or successor bootstrap modules, `plugins/codex/**`, `plugins/claude/**`, `.agents/plugins/marketplace.json` |
| 4 | `.gitignore`, runtime-residue policy docs, generated-artifact cleanup paths, release-boundary docs except final file-map polish |
| 5 | `MANIFEST.in`, `tests/**`, any new public regression subset docs or metadata, package-level test-selection guidance |
| 6 | `docs/REMOTE_CLIENT.md`, `docs/RELEASE_SURFACE.md`, CLI/help text or entrypoint descriptions touched by naming cleanup, and supporting runtime docs outside `README.md` / `docs/RELEASE_FILE_MAP.md` |
| 7 | `.scribe/backups/postgres/latest_backup_manifest.json`, the backup/manifest generation path, `.gitignore`, related runbook or release docs, security-case evidence, and operator rotation or invalidated-secret proof tied to `SEC-2026-04-08-0001` |
| 8 | No new product surface by default; review bundle, release notes, final checklist proof, and any last-mile doc fixes required to resolve review findings |

## 7. Governed Inputs Before Implementation Begins

The following artifacts should be committed as the planning baseline before any coder package starts:

- `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_PUBLIC_DOCS_TRUTH_20260408.md`
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_INSTALL_PLUGIN_UX_20260408.md`
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_PUBLIC_SURFACE_HYGIENE_20260408.md`
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408.md` as the canonical runtime terminology baseline; implementation should rely on its `# Summary`, `# Supported Modes and Intended Audience`, `# Export vs Runtime Contract`, and `# Naming and Contract Drift` sections.
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_RELEASE_SECURITY_SANITY_20260408.md`
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/ARCHITECTURE_GUIDE.md`
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/PHASE_PLAN.md`
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/CHECKLIST.md`
- Security case `SEC-2026-04-08-0001`

The accidental `RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408.md.md` creation path is not part of the governed baseline.

## 8. Review Expectations

Review should reject implementation packages that:

- rewrite `README.md` or `docs/RELEASE_FILE_MAP.md` before the structural packages land,
- let Package 6 or any other Phase 2 package preempt Package 1's front-door/file-map ownership,
- merge plugin bootstrap changes without Codex and Claude parity,
- make optional dependencies part of the base install,
- leave runtime-local artifacts or generated metadata ambiguously tracked,
- cite the stale `.md.md` runtime research creation path instead of the canonical runtime research conclusions,
- or treat the secret leak as anything less than a hard blocker with credential-disposition proof.

## 9. Evidence Base

Primary research inputs:

- `RESEARCH_PUBLIC_DOCS_TRUTH_20260408.md`
- `RESEARCH_INSTALL_PLUGIN_UX_20260408.md`
- `RESEARCH_PUBLIC_SURFACE_HYGIENE_20260408.md`
- `RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408.md` (`# Summary`, `# Supported Modes and Intended Audience`, `# Export vs Runtime Contract`, `# Naming and Contract Drift`)
- `RESEARCH_RELEASE_SECURITY_SANITY_20260408.md`

The accidental `.md.md` runtime-research creation path is excluded from this baseline.

Primary source checks performed in this session:

- `README.md`
- `install.sh`
- `pyproject.toml`
- `MANIFEST.in`
- `src/scribe_mcp/cli/main.py`
- `src/scribe_mcp/scripts/project_codex_plugin.py`
- `plugins/codex/.codex-plugin/plugin.json`
- `plugins/claude/.claude-plugin/plugin.json`
- `.agents/plugins/marketplace.json`
- `.gitignore`
- `docs/RELEASE_FILE_MAP.md`
- `.scribe/backups/postgres/latest_backup_manifest.json`
