---
id: hello_world_scribe_20260418-research-demo-isolation-and-publication
title: "\U0001F52C Research Demo Isolation And Publication \u2014 hello_world_scribe_20260418"
doc_type: RESEARCH_DEMO_ISOLATION_AND_PUBLICATION
doc_name: RESEARCH_DEMO_ISOLATION_AND_PUBLICATION
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-18 13:22:02 UTC
maintained_by: agent-20260418-131702-3ff37e0a
created_by: agent-20260418-131702-3ff37e0a
owners: []
related_docs: []
tags: []
summary: ''
edit_trace:
  tool: manage_docs
  created_at: 2026-04-18 13:20:55 UTC
  created_via: replace_section
  last_edited_at: 2026-04-18 13:22:02 UTC
  last_edited_by: agent-20260418-131702-3ff37e0a
  last_action: replace_section
---

# 🔬 Research Demo Isolation And Publication — hello_world_scribe_20260418
**Author:** Scribe
**Version:** 0.1
**Status:** draft
**Last Updated:** 2026-04-18 13:20:24 UTC

> Research on isolating a local Hello World Scribe demo while keeping a future GitHub-published example viable

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Resolve how a Hello World Scribe demo can stay safely local and gitignored during active development while still yielding a coherent GitHub-published example later.

**Key Takeaways:**
- The repo already draws a strong boundary between runtime/operator state and public release assets: `.scribe/` is ignored and pruned, while `docs/**` and `docs/examples/**` are explicitly part of the public release surface.
- The current `demo/` top-level path is ignored, and `src/scribe_mcp/config/projects/manual_demo.json` is also ignored, which indicates the repo already treats demo workspaces as local-only rather than publication artifacts.
- The best long-term shape is to keep the live demo workspace local and export or mirror a sanitized, tracked example artifact into a public-facing path later, rather than committing the live `.scribe/` workspace directly.
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** scribe-research-analyst

**Investigation Window:** 2026-04-18

**Focus Areas:**
- Local demo isolation rules in `.gitignore`
- Public release and packaging surfaces in `pyproject.toml`, `MANIFEST.in`, and release docs
- Existing example/demo layout patterns in `README.md`, `docs/examples/**`, and source example/config files
- Risks around `.scribe/`, generated docs, runtime state, and publication confusion

**Dependencies & Constraints:**
- No code changes in this investigation.
- Only this research document may be written.
- The live demo workspace must remain local-only unless intentionally exported into a tracked/public artifact.
- Publication guidance must not imply that `.scribe/**` or runtime-generated state is safe to ship as public example content.
## Findings
<!-- ID: findings -->
### Finding 1: Local demo state is intentionally non-public
- **Summary:** `.scribe/`, `.scribe_vectors/`, `/state/`, `demo/`, and the manual demo project config are treated as local/operator-only or generated surfaces, not public release artifacts.
- **Evidence:** `.gitignore:45-52`, `.gitignore:156-166`, `.gitignore:93-99`, and `MANIFEST.in:19-31` all exclude runtime or demo-local state; `README.md:184-208` describes `.scribe/` as the working surface.
- **Confidence:** High

### Finding 2: The release pipeline already defines a public example lane
- **Summary:** Public release truth already includes `docs/**` and `docs/examples/**`, and the package manifest explicitly ships those docs/examples while pruning `.scribe` and other runtime-generated directories.
- **Evidence:** `docs/RELEASE_SURFACE.md:6-18`, `pyproject.toml:73-92`, and `MANIFEST.in:1-31`.
- **Confidence:** High

### Finding 3: The repo already uses two different example patterns
- **Summary:** There is a tracked source-level example bridge under `src/scribe_mcp/bridges/examples/`, while `src/scribe_mcp/config/projects/manual_demo.json` is an ignored local project config that points to `docs/dev_plans/manual_demo/`.
- **Evidence:** `src/scribe_mcp/bridges/examples/__init__.py:1-10`, `src/scribe_mcp/bridges/examples/hello_world_plugin.py:1-19`, and `src/scribe_mcp/config/projects/manual_demo.json:1-10`.
- **Confidence:** Medium-High

### Additional Notes
- The current docs and packaging surfaces already separate "what is shipped" from "what is merely used by the operator." The demo should follow that same pattern rather than inventing a new one.
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- The repo already treats example code and example config differently. `src/scribe_mcp/bridges/examples/**` is a tracked source tree meant to demonstrate a bridge lifecycle, while `src/scribe_mcp/config/projects/manual_demo.json` is a local sample project config that is ignored.
- The release build includes docs/examples as packaged artifacts (`pyproject.toml:73-92`, `MANIFEST.in:1-18`), but explicitly prunes `.scribe` and related runtime/operator state (`MANIFEST.in:19-31`).
- The README documents `.scribe/` as the working surface and explains that it contains state, backups, docs, and logs tied to runtime usage (`README.md:184-208`).

**System Interactions:**
- Public publication flows should consume tracked docs/examples, not live project state.
- Local demo execution will naturally create `.scribe/docs/dev_plans/<project>/...` and runtime state under `.scribe/state/` or sibling runtime directories; those are intended to be excluded from publication.
- The public example lane already exists in the release docs and manifest, so the demo should align with that lane instead of creating a parallel ad hoc publication story.

**Risk Assessment:**
- Publishing raw `.scribe/` content would leak runtime state, logs, backups, and possibly internal task trails into a public repo.
- Publishing only `demo/` or only `.scribe/` would be ambiguous because the repo already uses `demo/` as ignored local output and `.scribe/` as both runtime memory and generated docs.
- A future GitHub example that reuses the same name as the local workspace without an export boundary would create confusion about whether the source of truth is live state or public documentation.
## Recommendations
<!-- ID: recommendations -->
### Strategy 1: Dual-track, in-repo publication lane
- Keep the live demo workspace local and ignored under `.scribe/` or another ignored scratch location.
- Publish a sanitized, tracked example subtree inside the repo, most naturally under `docs/examples/hello_world_scribe/`, with a README, launch notes, and any non-sensitive example assets.
- If executable sample code is needed, place it in a tracked source example area such as `src/scribe_mcp/bridges/examples/` rather than inside the live workspace.
- **Pros:** Fits the repo’s existing release surface, keeps one source of truth for published example docs, and avoids shipping runtime state.
- **Cons:** Requires an explicit export/sanitization step to keep the public example from drifting away from the live demo.

### Strategy 2: Separate exported publication repo
- Keep the live demo workspace local and ignored in this repo.
- Generate a separate GitHub repository or companion export tree for publication, populated only from sanitized demo artifacts.
- **Pros:** Strongest boundary between operator memory and public example content.
- **Cons:** Adds repo duplication, a heavier release process, and more drift risk between the local demo and the published example.

### Preferred Strategy
**Prefer Strategy 1.** It matches the repo’s current contract: `docs/**` and `docs/examples/**` are public, `.scribe/**` is local/operator state, and the manifest already ships docs/examples while pruning `.scribe`. That makes an in-repo public example lane the least surprising, easiest to review, and easiest to keep aligned with current release docs.

### Layout Implications
- Keep local-only runtime data under `.scribe/**` and other ignored scratch paths.
- Keep the demo workspace name distinct from the published example path so readers can tell live state from curated artifact.
- Track only sanitized example docs, launch instructions, and minimal public assets in the published lane.
- Treat generated docs, backups, logs, vectors, and state under `.scribe/` as non-public unless a human explicitly curates a copy into the published example tree.

### Safe To Export Later
- Curated narrative README or walkthrough material
- Sanitized config examples with placeholder paths and no local secrets
- Minimal public bridge/example source if it is intentionally generic
- Screenshots, diagrams, and docs that explain the demo without exposing live state

### Keep Local Only
- `.scribe/**` runtime memory, docs, logs, backups, vectors, and state
- Local demo database files and operator-specific state
- Temp/demo output under ignored scratch directories such as `demo/`
- Any project config file that is meant to bind the operator’s live demo workspace rather than document the public example
## Appendix
<!-- ID: appendix -->
- **References:** `.gitignore:38-52`, `.gitignore:93-99`, `.gitignore:150-166`, `pyproject.toml:73-92`, `MANIFEST.in:1-31`, `README.md:184-208`, `docs/RELEASE_SURFACE.md:6-18`, `src/scribe_mcp/bridges/examples/__init__.py:1-10`, `src/scribe_mcp/bridges/examples/hello_world_plugin.py:1-19`, `src/scribe_mcp/config/projects/manual_demo.json:1-10`
- **Attachments:** None; evidence is sourced from repository files only.
