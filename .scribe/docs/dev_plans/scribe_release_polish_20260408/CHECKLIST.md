---
id: scribe_release_polish_20260408-checklist
title: "Release Polish Acceptance Checklist \u2014 `scribe_release_polish_20260408`"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:49:00 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Release Polish Acceptance Checklist — `scribe_release_polish_20260408`

## Phase 0: Planning Baseline
<!-- phase: 0 -->

- [x] <!-- id: p0-architecture-guide --> Replaced `ARCHITECTURE_GUIDE.md` with a real release-polish contract covering all remaining polish areas. Proof: the architecture guide now makes Package 7 blocking on artifact removal, generator hardening, and credential rotation or invalidated-secret proof; keeps `README.md` / `docs/RELEASE_FILE_MAP.md` finalization in Package 1; and binds runtime terminology work to the canonical runtime research conclusions.
- [x] <!-- id: p0-phase-plan --> Replaced `PHASE_PLAN.md` with bounded packages, explicit dependencies, and safe parallel lanes. Proof: the phase plan now keeps Package 7 fully owning the blocker outcome, reserves README/file-map work for Package 1, and points Package 6 at the canonical runtime research sections instead of ad hoc interpretation.
- [x] <!-- id: p0-checklist --> Replaced `CHECKLIST.md` with package-level acceptance criteria and architecture proof items. Proof: this checklist now tracks Package 7 credential disposition, Package 6 doc-boundary discipline, and the final signoff package in addition to the rest of the release-polish graph.

## Phase 1: Blocker And Boundary Lock
<!-- phase: 1 -->

- [ ] <!-- id: p1-p7-secret-removal --> Package 7 removes the tracked credential-bearing backup artifact from the public surface and records fix evidence against `SEC-2026-04-08-0001`.
- [ ] <!-- id: p1-p7-generator-hardening --> Package 7 hardens backup-manifest generation so raw DSNs or credential-bearing command strings are never serialized into tracked output.
- [ ] <!-- id: p1-p7-credential-disposition --> Package 7 completes credential rotation or records explicit invalidated-secret proof before the blocker can close.
- [ ] <!-- id: p1-p4-runtime-boundary --> Package 4 aligns ignore and policy files so `.scribe/**`, `docs/dev_plans/**`, repo-local overlays, and generated residue are classified consistently.
- [ ] <!-- id: p1-p4-generated-cleanup --> Package 4 removes or quarantines generated metadata and other downstream-hostile residue from the tracked source surface.

## Phase 2: Structural Public-Surface Work
<!-- phase: 2 -->

- [ ] <!-- id: p2-p2-installer-story --> Package 2 leaves `install.sh` non-interactive by default and clarifies the professional installer story for checkout, deploy, and automation users.
- [ ] <!-- id: p2-p2-optional-deps --> Package 2 preserves a light core install and keeps heavy dependencies behind optional extras.
- [ ] <!-- id: p2-p3-plugin-parity --> Package 3 ships first-class public bootstrap paths for both Codex and Claude.
- [ ] <!-- id: p2-p3-scribe-integration --> Package 3 ships `scribe-integration` in both plugin bundles and updates shipped agent references to use it.
- [ ] <!-- id: p2-p5-test-boundary --> Package 5 defines a principled shipped-vs-dev regression boundary instead of one-off test exclusions.
- [ ] <!-- id: p2-p5-public-regression-subset --> Package 5 leaves an intentional public regression subset that review can inspect and verify.
- [ ] <!-- id: p2-p6-runtime-truth --> Package 6 normalizes docs/help text around local/core stdio, installed-package entrypoints, optional authenticated SSE, and optional authenticated remote/client posture using the canonical runtime research conclusions as the baseline.
- [ ] <!-- id: p2-p6-token-clarity --> Package 6 separates server-side and client-side auth token naming clearly in the docs.
- [ ] <!-- id: p2-p6-doc-boundary --> Package 6 updates supporting runtime docs/help text without editing `README.md` or `docs/RELEASE_FILE_MAP.md`, leaving final front-door/file-map ownership to Package 1.

## Phase 3: Public Docs Finalization
<!-- phase: 3 -->

- [ ] <!-- id: p3-p1-readme-front-door --> Package 1 makes `README.md` a professional high-level explanation of Scribe and a reliable docs index.
- [ ] <!-- id: p3-p1-file-map-dedicated --> Package 1 keeps `docs/RELEASE_FILE_MAP.md` dedicated and updates it only after structural packages land.
- [ ] <!-- id: p3-p1-doc-drift-cleared --> Package 1 rewrites `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/mcp_server_guide.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, and any drifting public docs so they match the landed release truth.

## Phase 4: Final Review And Signoff
<!-- phase: 4 -->

- [ ] <!-- id: p4-p8-review-pass --> Package 8 re-runs the bounded release truth and security sanity checks after implementation.
- [ ] <!-- id: p4-p8-no-blockers --> Package 8 confirms there are no unresolved blockers and that every landed change maps back to a package and checklist item.
- [ ] <!-- id: p4-p8-signoff --> Package 8 records explicit signoff or produces blocking findings with file-level proof.
