---
id: quality_check_infrastructure_20260524-synthesis-quality-check-infrastructure
title: Synthesis Quality Check Infrastructure
doc_type: SYNTHESIS_QUALITY_CHECK_INFRASTRUCTURE
doc_name: SYNTHESIS_QUALITY_CHECK_INFRASTRUCTURE
category: engineering
status: ready
version: v1.0
last_updated: 2026-05-24 03:49:05 UTC
maintained_by: agent-20260524-033158-52dee72d
created_by: agent-20260524-033158-52dee72d
owners:
- ArchitectAgent
related_docs: []
tags:
- quality-check
- architecture
- synthesis
summary: Architecture-stage synthesis for the quality_check infrastructure redesign.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-24 03:37:00 UTC
  created_via: create_doc
  last_edited_at: 2026-05-24 03:49:05 UTC
  last_edited_by: agent-20260524-033158-52dee72d
  last_action: frontmatter_update
---

# Synthesis: Quality Check Infrastructure

## Cross-Research Convergence
<!-- ID: cross_research_convergence -->
All four research lanes converged on the same direction.

- Keep `manage_docs(action="quality_check")` stable as the public entrypoint and extend it with additive metadata only when needed.
- Preserve reuse-first seams already confirmed in source: `runtime._handle_quality_check`, `collect_managed_doc_quality_warnings`, `summarize_quality_warnings`, `parse_frontmatter`, and the changelog/version helpers.
- Replace raw line-regex assumptions for markdown structure with a markdown-aware classification layer so prose rules stop firing inside fenced examples, quoted examples, list-contained fences, and tables.
- Move toward deterministic rule metadata and mode-aware evaluation instead of adding more ad hoc branching in `scaffold_quality.py`.
- Keep the default path lightweight and local. Release-grade and runtime-proof behavior must be explicit modes, not hidden cost in the everyday path.
- Treat missing current-version changelog coverage as advisory or omitted in `local_default` unless release intent is explicit or conservatively inferred from evidence such as explicit `mode=release_gate`, a changed `pyproject.toml` version, touched release docs, an active release checklist or package, invoked `preview_reconciliation` or `apply_global_changelog`, or an explicit release-closeout claim.
- Ambiguous context stays advisory-only. Inference must be explainable in output metadata; if the tool cannot point to a concrete trigger, it must not promote the finding to a blocking release gate.

## Verified Source Truths
<!-- ID: verified_source_truths -->
The architecture is grounded in current code, not only research summaries.

- `handle_manage_docs_request` routes both `quality_check` and `scaffold_quality_check` to `_handle_quality_check`, so the public action and alias already share one control plane.
- `_handle_quality_check` resolves canonical doc names, explicit markdown paths, and research-path rebinding before reading the target file and calling `collect_managed_doc_quality_warnings`.
- `scaffold_quality.py` currently owns warning policies, warning construction, heuristic markdown handling, changelog checks, research-index hygiene, and metadata-driven suppressions, which confirms it is the pressure point to decompose.
- Fenced-code detection is currently based on counting triple-backtick markers in the text prefix, so nested fences, outer quadruple fences, and tilde fences are real false-positive risk areas.
- `parse_frontmatter` is already a clean reusable seam: it separates YAML frontmatter from the markdown body before the quality scanner runs.
- `preview_current_release_coverage` already gives a reusable release-coverage contract, but it depends on version-context resolution and therefore belongs in a non-default gate.
- `pyproject.toml` currently has no markdown parser dependency, so any parser addition must pass a deliberate evaluation gate.

## Architecture Decisions
<!-- ID: architecture_decisions -->
1. Introduce a `DocumentContext` plus markdown-scope layer as the new foundation for quality rules.
2. Keep the existing public action stable and model mode selection as additive metadata, with `local_default` as the default, `release_gate` as the stronger optional lane, and `runtime_proof` as the explicit route/runtime contract lane.
3. Preserve the current top-level response keys and extend warning/result data additively with stable taxonomy fields such as `category`, `gate_scope`, `scope_kind`, `suppressible`, `source_owner`, and `rule_version`.
4. Replace monolithic collector branching with a deterministic registry of rule specs and collectors. Ordering is explicit and stable by registry order plus rule ID.
5. Keep `scaffold_quality.py` as the compatibility facade during migration. New modules may sit behind it, but runtime imports stay stable until the migration is complete.
6. Treat release coverage, version drift, and runtime proof as mode-gated checks so the default path does not pick up subprocess or runtime coupling by surprise. Missing current-version changelog coverage is blocking only in explicit `release_gate` mode or conservatively inferred release/version-bump context; ambiguous authoring contexts remain advisory-only.
7. Retain metadata-based suppressions for backward compatibility, but keep critical scaffold, source-authority, and release-integrity blockers unsuppressible.

## Open Questions And Evaluation Gates
<!-- ID: open_questions_evaluation_gates -->
No blocker remains that requires another research wave before implementation planning can proceed. The remaining questions are bounded evaluation gates for Forge.

- Parser gate: evaluate `markdown-it-py` first against the regression corpus because it best matches the CommonMark/GFM fence semantics from research. Evaluate Marko only if dependency policy, position fidelity, or package fit blocks the first candidate.
- Dependency gate: accept a new parser only if it adds no network or subprocess dependency, passes the fence and container regression corpus, preserves deterministic output ordering, and has acceptable package and lock impact.
- Fallback gate: if no candidate clears the gate, keep the same `DocumentContext` and registry contracts but ship a bounded heuristic scope provider as a temporary adapter. Do not create a parallel `quality_check_v2` path.
- Suppression scope: phase the redesign around existing `metadata.quality` suppressions first. Inline markdown suppressions are deferred until the rule contract is stable and a real downstream need exists.
- Cache gate: do not add caching in the first implementation slice. Profile first; only introduce content-hash caching if the new parser and rule pipeline prove slow enough to justify the complexity.

## Rejected Paths
<!-- ID: rejected_paths -->
The synthesis explicitly rejects the following paths.

- No heavyweight linter platform replacing Scribe managed-doc validation.
- No mandatory LLM review lane for deterministic document-shape defects.
- No mandatory external Vale invocation in the default path.
- No hidden network or subprocess dependencies in `local_default` mode.
- No source-authority confusion that tells operators to fix generated outputs instead of the owning templates, managed docs, or release surfaces.
- No big-bang rewrite and no replacement files such as `scaffold_quality_v2.py`.

## Handoff Summary
<!-- ID: handoff_summary -->
Architecture can proceed without reopening research. The implementation contract should center on a markdown-aware `DocumentContext`, deterministic registry-backed rules, additive output evolution, and an incremental migration that preserves the current `manage_docs(action="quality_check")` surface throughout the rollout while keeping missing current-version changelog coverage non-blocking in ordinary `local_default` authoring and blocking only in explicit or conservatively inferred `release_gate` contexts.
