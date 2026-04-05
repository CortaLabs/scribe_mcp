---
id: scribe_release_audit_20260403-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_release_audit_20260403"
doc_type: PHASE_PLAN
doc_name: PHASE_PLAN
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-05 09:30:40 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners:
- ArchitectAgent
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — scribe_release_audit_20260403
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-04-03 04:07:06 UTC

> Execution roadmap for scribe_release_audit_20260403.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Primary Risk | Confidence |
|---|---|---|---|
| Phase 0 — Architecture synthesis | Publish the blocker-removal contract | Missing a real shipping surface in the plan | 0.96 |
| Phase 1 — Security and surface hardening | Remove public-surface trust-boundary failures | Unsafe network/tool behavior survives into release | 0.93 |
| Phase 2 — Slim core / vector removal | Remove all built-in vector runtime/tool/config/docs/test surfaces | False-complete removal while vector files or semantic entrypoints still ship | 0.88 |
| Phase 3 — Packaging and plugin distribution | Make installation and plugin distribution reproducible | Package/docs/plugins disagree with shipped artifacts | 0.90 |
| Phase 4 — Storage/config/test cleanup | Remove residual runtime/bootstrap/test release blockers | Postgres/runtime residue or import side effects survive | 0.87 |
| Phase 5 — Release candidate signoff | Rebuild and inspect the ship artifacts | Governed/runtime truth diverges after the artifact rerun | 0.92 |

### Shared-file ownership and merge order
- `src/scribe_mcp/config/settings.py`: **1.1 → 2.1 → 4.1 → 6.2-A**
- `src/scribe_mcp/plugins/registry.py`: **1.2 → 2.1**
- `README.md` and release-facing docs: **1.1 topology safety and outside-repo posture contract (`p1-topology-docs`) → 2.2 vector-claim removal → 3.1 canonical install truth → 3.2 plugin install addendum → 6.4-B final Phase 6 README/file-map pass only**
- `pyproject.toml` and install surfaces: **2.1 dependency/vector removal → 3.1 install profile cleanup → 5.1 rebuilt artifact verification → 6.1-A core/extension boundary rewrite → 6.4-A artifact verification only**
- Plugin install docs: **3.1 owns canonical install language; 3.2 appends bundle-specific install steps only after 3.1 merges**
- Package 1.2 consumes the Phase 1 posture wording owned by Package 1.1 but does not edit `README.md` / `deploy/README.md`.
- If an earlier owner has not merged, the later package must wait rather than editing the same shared file in parallel.

**Phase 6 collision map (must be followed exactly)**
- `pyproject.toml`: **6.1-A first write**; **6.4-A verification only**; no `6.2` / `6.3` / `6.4-B` edits unless the architect reopens the package boundary.
- `packages/scribe_council/pyproject.toml` and `packages/scribe_council/src/**`: **6.1-A first write + final ownership**; **6.4-A verification only**.
- `.gitignore`: **6.1-B first write** for overlay/runtime policy; **6.1-C final cleanup** for concrete `.scribe/cli/*.json`, `.scribe/state/`, and runtime ignores; frozen after `6.1-C`.
- Runtime path/config surfaces (`src/scribe_mcp/config/paths.py`, `src/scribe_mcp/cli/session_store.py`, `src/scribe_mcp/utils/rotation_state.py`, `src/scribe_mcp/utils/audit.py`, shared runtime-path helpers): **6.1-C first and final owner**.
- Remote auth settings/runtime surfaces (`src/scribe_mcp/config/settings.py`, `src/scribe_mcp/storage/__init__.py`, `src/scribe_mcp/storage/remote.py`, `src/scribe_mcp/config/mode_detection.py`): **6.2-A first and final owner**; `6.2-B` adds docs/tests only.
- Bridge boundary surfaces (`src/scribe_mcp/server.py`, `src/scribe_mcp/bridges/registry.py`, `src/scribe_mcp/bridges/policy.py`, `src/scribe_mcp/bridges/hooks.py`, `src/scribe_mcp/bridges/plugin.py`, bridge manifest loaders): **6.3-A first and final owner**; `6.3-B` / `6.3-C` / `6.3-D` consume the boundary only.
- Release docs written before the file-map freeze (`docs/RELEASE_SURFACE.md`, `docs/RUNTIME_LAYOUT.md`, package-local extension docs, `docs/REMOTE_CLIENT.md`, bridge-boundary docs/examples, `docs/COMPATIBILITY_MATRIX.md`): first write belongs to the owning package; **6.4-B may link them from README but may not rewrite their technical contracts**.
- Final `README.md`: **6.4-B first and only Phase 6 write**.
- Final `docs/RELEASE_FILE_MAP.md`: **6.4-B create + finalize**.
- Shared `council_mcp` package-boundary/config/export/deploy surfaces across `6.3-B` / `6.3-C` / `6.3-D`: **6.3-B auth/bootstrap first → 6.3-C export/import cleanup second → 6.3-D deploy/scaffold/docs/tests finalization third**.

### Post-review correction addendum (`5.6-A` / `5.6-B` / `5.6-C` / `5.6-D` / `5.6-E`)
- `5.1` through `5.5` stay locked as historical evidence.
- **`5.6-A` is complete**: the governed docs now close the three Phase 1 trust-policy checklist items from existing landed proof.
- **`5.6-B` is complete**: the live `manage_docs` edit success path no longer emits the removed vector reminder strings, and the focused reminder regression covers that behavior.
- **`5.6-C` is complete as blocker identification**: live source/runtime state is coherent, and the prior NO-SHIP block is preserved as historical stale-artifact-drift evidence after `5.6-B`.
- **`5.6-D` is complete**: fresh post-`5.6-B` bundle `/tmp/scribe_release_audit_20260403_dist/final_56d_20260404T231620Z` rebuilt the current tree and confirmed the packaged `edit.py` reminder path now matches the clean live source/runtime state.
- **`5.6-E` is complete**: the governed docs now reconcile the final signoff from that fresh bundle while preserving the historical `5.3` / `5.5` / `5.6-C` evidence.
- Current release decision = **SHIP**.
- No new broad phase is introduced, and no packaging/storage/plugin/test-layout package is reopened by this reconciliation pass.
### Task Package: 0.1 — Publish the stable-release contract

**Scope:** Convert the research wave into a bounded implementation contract for release blockers, supported topology, and plugin distribution.

**Files to Modify:**
- `.scribe/docs/dev_plans/scribe_release_audit_20260403/ARCHITECTURE_GUIDE.md` — release architecture and boundaries
- `.scribe/docs/dev_plans/scribe_release_audit_20260403/PHASE_PLAN.md` — ordered work packages
- `.scribe/docs/dev_plans/scribe_release_audit_20260403/CHECKLIST.md` — blocker checklist and defer list

**Dependencies:** None

**Specifications:**
1. Encode the 1.0 product boundary: local-first, SQLite default, Postgres extra, no built-in vector.
2. Classify security/vector/packaging issues into must-fix vs defer.
3. Define the plugin distribution model for Claude and Codex.
4. Call out topology work that is explicitly out of scope for this release.

**Verification:**
- [x] ARCHITECTURE_GUIDE cites the completed research wave.
- [x] PHASE_PLAN contains bounded task packages.
- [x] CHECKLIST separates must-fix-before-release from defer.

**Out of Scope:** Any code implementation.

## Phase 1 — Security and Surface Hardening

### APPROACH_SUMMARY — Phase 1 Forge Deployment

**Goal**
- Harden Scribe’s exposed transport and tool surfaces for release while keeping trusted local/stdio and loopback-authenticated SSE cross-repo workflows as first-class supported defaults.
- Deliver a safe default where non-loopback/network-exposed posture denies outside-repo reads unless an operator explicitly force-enables them, while allowing a global force-disable in every posture.

**Task packages to execute now**
1. **Package 1.1 — transport boundary and hosted-surface lockdown**
   - Owns network auth/bind posture and top-level hosted-surface documentation.
2. **Package 1.2 — tool sandbox, plugin policy, and search hardening**
   - Owns `read_file` trust-posture defaults, search safety, and plugin execution hardening after 1.1 establishes the transport/server policy posture.

**Files to touch now**
- **Package 1.1 only:** `src/scribe_mcp/server_sse.py`, `src/scribe_mcp/server.py`, `src/scribe_mcp/__main__.py`, `src/scribe_mcp/config/settings.py`, `README.md`, `deploy/README.md`, related deploy/topology docs.
- **Package 1.2 only:** `src/scribe_mcp/tools/read_file.py`, `src/scribe_mcp/tools/search.py`, `src/scribe_mcp/plugins/registry.py`, `src/scribe_mcp/config/repo_config.py`.

**Files forbidden / out of scope now**
- **Package 1.1 must not edit:** `tools/read_file.py`, `tools/search.py`, plugin registry policy code, or broad tool-sandbox logic owned by 1.2.
- **Package 1.2 must not edit:** transport/auth server boundary files owned by 1.1 (`server_sse.py`, `server.py`, `__main__.py`), `src/scribe_mcp/config/settings.py`, or release docs/config templates owned by 1.1; it must not reopen topology scope beyond consuming the outside-repo posture contract already owned by `p1-topology-docs`.

**Verification plan**
- **Package 1.1 / checklist `p1-topology-docs`:** prove unauthenticated HTTP/SSE calls are rejected, REST backend routes enforce the same protection model as SSE/MCP, default startup does not expose an unsafe listener, and the Package 1.1-owned release docs describe trusted local cross-repo work as first-class, document global force-disable, and reserve force-enable guidance for deliberate non-loopback exposure.
- **Package 1.2:** prove outside-repo read defaults derive from runtime trust posture; trusted local/stdio and loopback-authenticated SSE allow them by default; non-loopback/network-exposed posture denies them by default unless explicitly force-enabled; global force-disable overrides every allow path including deliberate force-enable; and implementation consumes one canonical Package 1.1-owned trust-policy surface without recreating repo/env posture sprawl. Also prove unsafe regex is bounded/rejected and plugin auto-exec is not silently enabled.

**Ownership boundaries / sequencing**
- Run **1.1 first**. It owns transport/server posture, `settings.py`, and top-level topology docs.
- Run **1.2 second**, after 1.1 merges. It owns tool hardening only and must not edit `settings.py` or release docs/config-template policy surfaces.
- Do not run 1.1 and 1.2 in parallel on shared files. If a file is not listed under a package above, it is out of scope for this Phase 1 deployment wave.
### Task Package: 1.1 — Transport boundary and hosted-surface lockdown

**Scope:** Package 1.1 owns the minimum release-safe transport boundary for SSE/REST, owns publication/proof of the single reusable transport/trust policy surface for downstream packages, and makes the topology contract explicit in code and docs.

**Files to Modify:**
- `src/scribe_mcp/server_sse.py` — auth/origin/bind enforcement and shared boundary for REST + SSE
- `src/scribe_mcp/server.py` — startup wiring and transport profile propagation
- `src/scribe_mcp/__main__.py` — CLI/server entrypoint defaults
- `src/scribe_mcp/config/settings.py` — transport settings surface and canonical posture inputs
- `README.md` — supported vs unsupported topology claims
- `deploy/README.md` and related deploy docs — trusted/internal SSE posture only

**Dependencies:**
- Requires Package 0.1 complete.

**Specifications:**
1. Introduce an application-level auth requirement for network transport.
2. Change default bind behavior to a safe local/trusted profile.
3. Ensure backend REST operations do not bypass the SSE/MCP transport boundary.
4. Package 1.1 owns, publishes, and proves the single reusable transport/trust policy surface that decides trusted-local, loopback-authenticated, and non-loopback/network-exposed posture for downstream consumers.
5. Ensure Package 1.2 can consume that canonical surface directly instead of reconstructing posture from repo/env heuristics.
6. Remove any release docs that imply public unauthenticated hosting is supported.
7. Release docs must explicitly describe loopback-authenticated SSE as a supported default-allow posture and non-loopback/network-exposed posture as default-deny unless force-enabled.

**Patterns to Follow:**
- Reuse the existing settings-driven startup path; do not create a parallel server bootstrap system.
- Keep `server_sse.py` as the network boundary, not a second transport stack.
- Make the canonical trust-policy surface the only posture authority that later packages consume.

**Verification:**
- [x] Unauthenticated HTTP/SSE calls are rejected. Proof: `tests/test_transport_sse.py::TestTransportAuthBoundary::test_unauthenticated_sse_and_rest_requests_are_rejected` exercises `/sse`, `/messages/`, and `/api/v1/batch` without auth and expects HTTP 401.
- [x] REST backend routes enforce the same protection model as SSE/MCP routes. Proof: the shared middleware in `src/scribe_mcp/server_sse.py` wraps `/sse`, `/messages/`, `/api/v1/backend/{operation}`, and `/api/v1/batch`, and the focused pytest suite passed on 2026-04-03.
- [x] Default startup no longer publishes an unsafe externally reachable listener by accident. Proof: `src/scribe_mcp/config/settings.py` and `src/scribe_mcp/__main__.py` now default `SCRIBE_TRANSPORT_HOST` / `--host` to `127.0.0.1`, covered by `tests/test_transport_sse.py::TestCLIArgumentParsing::test_default_host_is_loopback_safe`.
- [ ] Package 1.1 owns, publishes, and proves a single reusable transport/trust policy surface for downstream consumption, with evidence that Package 1.2 consumes it directly for outside-repo allow/deny decisions.
- [ ] Docs describe loopback-authenticated SSE as a supported default-allow posture and non-loopback/network-exposed posture as default-deny unless explicitly force-enabled.

**Out of Scope:** multi-tenant authz, grants, or `knowledge_mcp`-style request envelopes.

### Task Package: 1.2 — Tool sandbox, plugin policy, and search hardening

**Scope:** Remove the known local-execution footguns from public tool behavior while keeping trusted local cross-repo work first-class.

**Files to Modify:**
- `src/scribe_mcp/tools/read_file.py` — make outside-repo defaults derive from runtime trust posture instead of per-repo opt-in sprawl
- `src/scribe_mcp/tools/search.py` — regex safety controls
- `src/scribe_mcp/plugins/registry.py` — default plugin execution policy
- `src/scribe_mcp/config/repo_config.py` — global override contract only where needed, without re-deriving posture

**Dependencies:**
- Requires Package 0.1 complete.
- Requires Package 1.1 merged first.

**Specifications:**
1. Default outside-repo read behavior derives from runtime transport/trust posture, not per-repo env sprawl.
2. Trusted local/stdio profiles allow `read_file(... allow_outside_repo=True)` by default.
3. Trusted loopback-only authenticated SSE profiles allow `read_file(... allow_outside_repo=True)` by default.
4. Non-loopback/network-exposed posture disables outside-repo reads by default unless an operator explicitly force-enables them.
5. A global force-disable path is available in every posture for constrained environments and overrides any allow path, including deliberate non-loopback/network force-enable.
6. The caller flag requests outside-repo access but does not override runtime posture.
7. Package 1.2 must consume a single canonical Package 1.1-owned transport/trust-policy surface for the final allow/deny decision.
8. Package 1.2 must not recreate posture detection or widen access by independently combining repo config/env heuristics.
9. Bound or replace untrusted regex execution.
10. Disable repo-local arbitrary Python auto-load by default.
11. Require explicit trusted enablement for any retained external plugin loading path.

**Patterns to Follow:**
- Keep repo-root enforcement inside the existing read-path policy logic.
- Make outside-repo behavior depend on the canonical runtime/server trust posture from Package 1.1, not repo-local opt-in sprawl.
- `repo_config.py` may carry only global override inputs consumed by that canonical surface; it must not become a second trust-policy engine.
- Preserve the plugin registry as the single loading authority.

**Verification:**
- [ ] `read_file(... allow_outside_repo=True)` is enabled by default for trusted local/stdio profiles. Evidence required: focused tests covering stdio/local default behavior without a force-enable flag.
- [ ] `read_file(... allow_outside_repo=True)` is enabled by default for loopback-only authenticated SSE profiles. Evidence required: focused tests covering loopback-authenticated SSE without a force-enable flag.
- [ ] A global force-disable turns off outside-repo reads even in trusted local/stdio and loopback-authenticated SSE profiles. Evidence required: focused tests covering the override in both trusted profiles.
- [ ] A global force-disable also overrides deliberate non-loopback/network force-enable. Evidence required: focused tests covering network-exposed posture with both force-enable and force-disable present and verifying deny wins.
- [ ] In non-loopback/network-exposed posture, `read_file(... allow_outside_repo=True)` is disabled by default unless operator policy explicitly force-enables it. Evidence required: focused tests covering default deny and deliberate force-enable.
- [ ] Package 1.2 consumes the single canonical Package 1.1-owned transport/trust-policy surface and does not reintroduce repo-config/env widening logic. Evidence required: focused reread/tests of the read-path decision flow against the Package 1.1-owned surface.
- [x] Unsafe regex inputs are bounded or rejected. Proof: `src/scribe_mcp/tools/search.py` now defaults to literal mode and rejects multiline/advanced/backreference/nested-quantifier regex; `tests/test_phase1_package12_hardening.py::test_search_rejects_unsafe_nested_regex` passed on 2026-04-03.
- [x] Repo config alone cannot silently execute arbitrary plugin code in the public package. Proof: `src/scribe_mcp/plugins/registry.py` now requires `plugin_config.enabled` plus trusted runtime env opt-in and manifest/file-hash validation before import; `tests/test_phase1_package12_hardening.py::test_plugin_registry_requires_trusted_runtime_opt_in` and `::test_plugin_registry_loads_manifest_pinned_plugin_with_trusted_runtime` passed on 2026-04-03.

Release-doc alignment remains owned by Package 1.1 checklist item `p1-topology-docs`; Package 1.2 must not claim `README.md` / `deploy/README.md` edits as part of this package.

**Out of Scope:** long-term signature PKI or a new plugin framework.

## Phase 2 — Slim Core / Remove Built-In Vector Stack

### APPROACH_SUMMARY — Phase 2 Forge Deployment

**Goal**
- Remove built-in vector behavior from the shipped core package without breaking the public `manage_docs(... action="search")` contract.
- Deliver a slim core where semantic/vector requests explicitly fall back to text search, and all vector-only docs/scripts/tests/runtime residues are removed.

**Task packages to execute now**
1. **Package 2.1 — runtime/tooling contract cleanup**
   - Owns vector runtime removal, tool exports/metadata/probe cleanup, `manage_docs.py` helper cleanup, fallback contract, and retained extension seam.
2. **Package 2.2 — blast-radius cleanup**
   - Owns vector-bearing docs, scripts, templates, and tests after 2.1 lands.

**Files to touch now**
- **Package 2.1 only:** `pyproject.toml`, retained install metadata surfaces, `deploy/Dockerfile`, `src/scribe_mcp/plugins/registry.py`, `src/scribe_mcp/plugins/vector_indexer.py`, `src/scribe_mcp/plugins/vector_indexer.json`, `src/scribe_mcp/config/settings.py`, `src/scribe_mcp/config/vector_config.py`, `src/scribe_mcp/config/repo_config.py`, `src/scribe_mcp/doc_management/indexing.py`, `src/scribe_mcp/doc_management/actions/search.py`, `src/scribe_mcp/tools/manage_docs.py`, `src/scribe_mcp/tools/append_entry.py`, `src/scribe_mcp/tools/doctor.py`, `src/scribe_mcp/tools/vector_search.py`, `src/scribe_mcp/tools/__init__.py`, `src/scribe_mcp/tools/base/tool_metadata.py`, `src/scribe_mcp/scripts/scribe_probe.py`, regenerated `src/scribe_mcp.egg-info/*`.
- **Package 2.2 only:** `README.md`, `docs/Scribe_Usage.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, `docs/guides/manage_docs_troubleshooting.md`, `src/scribe_mcp/config/scribe_config_template.yaml`, `src/scribe_mcp/scripts/reindex_vector.py`, `src/scribe_mcp/scripts/reindex_docs.py`, `src/scribe_mcp/scripts/check_vector_index.py`, vector-focused tests, `tests/test_vector_entry_ids.py` rename/re-home.

**Files forbidden / out of scope now**
- **Package 2.1 must not edit:** release-facing docs owned by 2.2 (`README.md`, docs whitepaper/usage/troubleshooting files), broad test cleanup outside vector-bearing suites, Phase 4 Postgres/runtime cleanup files.
- **Package 2.2 must not edit:** core runtime/search contract files owned by 2.1 (`plugins/registry.py`, `doc_management/indexing.py`, `doc_management/actions/search.py`, `tools/manage_docs.py`, tool registry/metadata exports, package dependency metadata except regenerated artifact proof if needed).

**Verification plan**
- **Package 2.1:** prove no built-in vector plugin loads; no shipped vector tool exports/metadata/probe hooks remain; `_chunk_text_for_vector` and `_resolve_semantic_limits` no longer ship as core compatibility helpers; semantic/vector requests fall back to text with structured disclosure; regenerated egg-info no longer lists vector deps/sources.
- **Package 2.2:** prove named docs/templates/scripts no longer advertise vector behavior; true vector tests are gone; misnamed non-vector coverage is preserved under a correct name/location.

**Ownership boundaries for Forge deployment**
- Run **2.1 first**. It owns the runtime/search/package contract and is the only package allowed to change `manage_docs.py`, `doc_management/actions/search.py`, registry/tool metadata, and dependency metadata.
- Run **2.2 second**, after 2.1 merges. It owns release-surface cleanup only: docs, templates, scripts, and vector-focused tests.
- No parallel edits across those ownership lines. If a file is not listed under a package above, it is out of scope for this Phase 2 deployment wave.

### Task Package: 2.1 — Remove vector runtime, tool exports, and metadata wiring

**Scope:** Delete built-in vector behavior from the package/runtime path so the public artifact is genuinely slim, including all shipped MCP tool surfaces and generated source listings that would otherwise keep vector code shipping.

**Files to Modify:**
- `pyproject.toml`
- `requirements.txt` and/or `install.sh` (if retained)
- `deploy/Dockerfile`
- `src/scribe_mcp/plugins/registry.py`
- `src/scribe_mcp/plugins/vector_indexer.py`
- `src/scribe_mcp/plugins/vector_indexer.json`
- `src/scribe_mcp/config/settings.py`
- `src/scribe_mcp/config/vector_config.py`
- `src/scribe_mcp/config/repo_config.py`
- `src/scribe_mcp/config/scribe_config_template.yaml`
- `src/scribe_mcp/doc_management/indexing.py`
- `src/scribe_mcp/doc_management/actions/search.py`
- `src/scribe_mcp/tools/manage_docs.py`
- `src/scribe_mcp/tools/append_entry.py`
- `src/scribe_mcp/tools/doctor.py`
- `src/scribe_mcp/tools/vector_search.py`
- `src/scribe_mcp/tools/__init__.py`
- `src/scribe_mcp/tools/base/tool_metadata.py`
- `src/scribe_mcp/scripts/scribe_probe.py`
- regenerated metadata surfaces: `src/scribe_mcp.egg-info/PKG-INFO`, `src/scribe_mcp.egg-info/requires.txt`, `src/scribe_mcp.egg-info/SOURCES.txt`

**Dependencies:**
- Requires Phase 1 decisions merged where they overlap with `settings.py` or `registry.py`.
- Owns `settings.py` after Package 1.1 and owns `registry.py` after Package 1.2.

**Specifications:**
1. Remove vector/heavy dependencies from base package metadata.
2. Remove built-in vector plugin import/initialization.
3. Remove shipped vector MCP exports, aliases, metadata, and probe hooks from `vector_search.py`, `tools/__init__.py`, `tool_metadata.py`, and `scribe_probe.py`.
4. Remove or rename/rework `src/scribe_mcp/tools/manage_docs.py` semantic/vector compatibility helpers such as `_chunk_text_for_vector` and `_resolve_semantic_limits` so they do not survive as core vector/semantic surfaces.
5. Make core `manage_docs(action="search")` text-only and explicitly fall back to the supported text/literal path when `search_mode="semantic"` or `"vector"` is requested.
6. Surface that fallback in a structured, user-visible way with `fallback_applied`, `requested_search_mode`, `effective_search_mode`, and a fallback warning/reason while still returning text-search results.
7. Retain the downstream extension seam via `src/scribe_mcp/plugins/registry.py` (`ScribePlugin`, `PluginRegistry`, `get_plugin_registry`) plus the `manage_docs` tool entrypoint in `src/scribe_mcp/tools/manage_docs.py` and the search boundary in `src/scribe_mcp/doc_management/actions/search.py`, while removing repo config vector flags and semantic-limit helpers from the core contract.
8. Regenerate package metadata/source listings so those files no longer advertise vector deps or vector sources.

**Patterns to Follow:**
- Use the existing plugin and config seams; do not add a dormant built-in replacement layer.
- Keep the public `manage_docs` search contract stable while removing legacy semantic/vector compatibility helpers and private vector-only imports.

**Verification:**
- [x] Base install metadata no longer includes vector/heavy deps. Evidence: `pyproject.toml`, `requirements.txt`, `deploy/Dockerfile`, `src/scribe_mcp.egg-info/PKG-INFO`, and `src/scribe_mcp.egg-info/requires.txt` were updated on 2026-04-03.
- [x] Startup no longer loads a built-in vector plugin. Evidence: `src/scribe_mcp/plugins/registry.py` no longer imports `vector_indexer`, and `pytest tests/test_plugin_registry_runtime.py -q` confirmed the registry stays empty for the legacy built-in path.
- [x] `src/scribe_mcp/tools/manage_docs.py` no longer ships semantic/vector compatibility helpers such as `_chunk_text_for_vector` or `_resolve_semantic_limits`. Evidence: both wrappers were removed from the core entrypoint.
- [x] No shipped vector tool exports, aliases, metadata, or probe hooks remain in core. Evidence: deleted `src/scribe_mcp/tools/vector_search.py` and `src/scribe_mcp/plugins/vector_indexer.{py,json}` plus pruned `tools/__init__.py`, `tool_metadata.py`, and `scripts/scribe_probe.py`.
- [x] Core `manage_docs(... action="search")` is text-only and semantic/vector requests fall back to text results with structured fallback disclosure rather than hard-failing or silently downgrading. Evidence: `pytest tests/test_phase2_vector_core_removal.py -q` asserted `fallback_applied`, requested/effective modes, and returned text matches for both `semantic` and `vector` requests.
- [x] The retained downstream seam is still the `manage_docs` tool entrypoint plus `doc_management.actions.search`, backed by the plugin boundary in `plugins/registry.py`, with no dependency on removed vector helpers, aliases, or private imports. Evidence: the registry boundary types remain exported while search fallback logic now lives solely in `tools/manage_docs.py` + `doc_management/actions/search.py`.
- [x] Regenerated egg-info source listings no longer contain vector plugin/tool files. Evidence: regenerated `src/scribe_mcp.egg-info/SOURCES.txt` no longer lists `src/scribe_mcp/plugins/vector_indexer.*` or `src/scribe_mcp/tools/vector_search.py`.

**Out of Scope:** building a replacement downstream vector plugin inside this repo.

### Task Package: 2.2 — Remove vector blast-radius docs, scripts, and tests from core

**Scope:** Clean the release surface so docs/tests/scripts no longer advertise or depend on the removed built-in feature.

**Files to Modify:**
- `README.md` vector/semantic release claims
- `docs/Scribe_Usage.md`
- `docs/whitepapers/scribe_mcp_whitepaper.md`
- `docs/guides/manage_docs_troubleshooting.md`
- `src/scribe_mcp/config/scribe_config_template.yaml`
- `src/scribe_mcp/scripts/reindex_vector.py`
- `src/scribe_mcp/scripts/reindex_docs.py`
- `src/scribe_mcp/scripts/check_vector_index.py`
- vector-focused tests under `tests/`
- `tests/test_vector_entry_ids.py` (rename/re-home, not delete)
- any config templates still mentioning vector flags

**Dependencies:**
- Requires Package 2.1 complete.
- Owns `README.md` only after Package 1.1 safety edits are merged.

**Specifications:**
1. Delete or move vector-only operational scripts out of the core release path.
2. Remove vector release docs and semantic-search marketing claims from the named blast-radius files.
3. Delete true vector suites from the core regression namespace.
4. Preserve and relocate misnamed non-vector coverage such as `tests/test_vector_entry_ids.py`.

**Patterns to Follow:**
- Align docs/tests/scripts to the actual shipped runtime.
- Prefer deletion to temporary placeholders for removed core features.

**Verification:**
- [x] The named vector blast-radius docs, templates, and scripts no longer advertise or implement built-in semantic/vector behavior. Evidence: `README.md`, `docs/Scribe_Usage.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, and `docs/guides/manage_docs_troubleshooting.md` now document text search and generic diagnostics only; `src/scribe_mcp/config/scribe_config_template.yaml` no longer ships vector flags; and targeted searches on 2026-04-03 found no `reindex_vector`, `vector_indexer`, `vector_search`, or vector-config references in the touched release-surface files.
- [x] No true vector suites remain in the public core test surface. Evidence: deleted `tests/debug_vector_processing.py`, `tests/test_manage_docs_chunking.py`, `tests/test_vector_complete_integration.py`, `tests/test_vector_indexer.py`, `tests/test_vector_indexer_torchvision_guard.py`, `tests/test_vector_integration.py`, and `tests/test_vector_search_tools.py`; `find tests -maxdepth 1 -type f -name '*vector*'` now returns only `tests/test_phase2_vector_core_removal.py`, which is the removal regression rather than a retained vector feature suite.
- [x] The append-entry helper coverage formerly named `test_vector_entry_ids.py` is preserved under a correct name/location. Evidence: the file now lives at `tests/test_append_entry_ids.py`, its wording no longer refers to vector stability, and `pytest tests/test_append_entry_ids.py -q` passed with 12 tests on 2026-04-03.

**Out of Scope:** designing the future downstream vector companion package.

## Phase 3 — Packaging and Plugin Distribution
<!-- ID: phase_3 -->

### APPROACH_SUMMARY — Phase 3 Forge Deployment

**Goal**
- Convert the post-Phase-2 slim core into a coherent install/distribution package with one canonical install story and first-party Claude/Codex plugin bundles.

**Task packages to execute now**
1. **Package 3.1 — canonical package/install profile cleanup**
   - Execute now as the entry package for this wave.
2. **Package 3.2 — Claude and Codex plugin bundle implementation**
   - Still intended for this immediate wave, but only **after 3.1 merges** because bundle docs and install surfaces must align to the canonical package/install contract.

**Files to touch now**
- **Package 3.1 only:** `pyproject.toml`, `README.md`, `install.sh`, `requirements.txt`, `src/scribe_mcp/config/mcp_config.json`, related install/setup docs.
- **Package 3.2 only:** `plugins/claude/.claude-plugin/plugin.json`, `plugins/claude/hooks/hooks.json`, Claude plugin-root bundle assets (`skills/`, `.mcp.json`, and optional `commands/`, `hooks/`, `.lsp.json`, `bin/`, `settings.json` when shipped), public-safe Claude `agents/*.md` when intentionally shipped, `plugins/codex/.codex-plugin/plugin.json`, Codex plugin-root assets (`skills/`, `.mcp.json`, `.app.json`, `assets/`, any distribution-only `plugins/codex/agents/*.toml`, and `plugins/codex/assets/agents.json` + `plugins/codex/assets/agents/*.md`), `.agents/plugins/marketplace.json`, build/install helper(s) under `src/scribe_mcp/scripts/`, `src/scribe_mcp/cli/main.py` if needed for supported installer flow, plugin install docs/tests.

**Files forbidden / out of scope now**
- **Package 3.1 must not edit:** plugin bundle roots, Codex projection helpers, or plugin smoke tests owned by 3.2.
- **Package 3.2 must not edit:** package dependency truth surfaces owned by 3.1 (`pyproject.toml`, `install.sh`, `requirements.txt`) except where 3.1 has already merged final install contract changes; 3.2 also must not reopen Phase 2 runtime/vector-removal files.

**Verification plan**
- **Package 3.1:** prove slim SQLite install works from package metadata, Postgres installs only via requested extra/profile, and packaged MCP config contains no developer-machine paths.
- **Package 3.2:** prove the official Claude and Codex root layouts, the exact public-safe allowlist/exclusion rule, valid Claude hook schema, Codex marketplace `source.path` resolution, non-destructive/idempotent Codex projection, clean CLI error handling, and packaged entry-point usage.

**Ownership boundaries / sequencing**
- Run **3.1 first**. It owns the canonical install truth and all shared install-language surfaces.
- Run **3.2 second**, after 3.1 merges. It owns plugin bundle roots, projection helpers, marketplace metadata, projected agent catalogs/assets, and plugin-specific docs/tests.
- Do not run 3.1 and 3.2 in parallel on shared docs or install surfaces. If a file is not listed under a package above, it is out of scope for this Phase 3 deployment wave.

### Task Package: 3.1 — Canonical package/install profile cleanup

**Scope:** Make package installation and configuration coherent for SQLite, Postgres, and trusted SSE users.

**Files to Modify:**
- `pyproject.toml`
- `README.md`
- `install.sh`
- `requirements.txt`
- `src/scribe_mcp/config/mcp_config.json`
- related install/setup docs

**Dependencies:**
- Requires Package 2.1 complete.
- Must complete before Package 3.2 begins so bundle docs inherit the final install contract.

**Specifications:**
1. Make `pyproject.toml` the sole release truth.
2. Remove or generate any legacy install surfaces that disagree with the package metadata.
3. Publish clear install profiles for SQLite default, Postgres extra, and trusted SSE.
4. Replace absolute-path/repo-root config examples with install-safe examples.

**Patterns to Follow:**
- Reuse packaged entry points already declared in `pyproject.toml`.
- Do not perpetuate repo-root compatibility shims in public examples.

**Verification:**
- [x] Slim SQLite install path works from package metadata alone.
- [x] Postgres installs only when the extra/profile is requested.
- [x] Packaged MCP config contains no developer-machine paths.

**Evidence (2026-04-03):** `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/scribe_phase31_wheels .` produced `scribe_mcp-2.2-py3-none-any.whl`; inspecting its `METADATA` showed the SQLite/base install depends only on the slim core set while `asyncpg~=0.29` appears only as `extra == "postgres"`; the same wheel ships `scribe_mcp/config/mcp_config.json` with `"command": "scribe-server"` and no developer-machine paths; `bash -n install.sh` passed after the helper was rewritten to install `sqlite`, `postgres`, `trusted-sse`, `dev`, and `dev-postgres` profiles directly from `pyproject.toml`.

**Out of Scope:** PyPI publication automation or release marketing copy.

### Task Package: 3.2 — Claude and Codex plugin bundle implementation

**Scope:** Correct the official Claude/Codex plugin bundles so they remain host-valid and public-safe without reopening broader packaging or runtime architecture.

**Files to Modify/Create:**
- `plugins/claude/.claude-plugin/plugin.json`
- `plugins/claude/hooks/hooks.json`
- public-safe Claude agent assets when intentionally shipped: `plugins/claude/agents/*.md`
- Claude plugin-root assets when shipped: `plugins/claude/skills/`, `plugins/claude/.mcp.json`, and optional `plugins/claude/commands/`, `plugins/claude/.lsp.json`, `plugins/claude/bin/`, `plugins/claude/settings.json`
- `plugins/codex/.codex-plugin/plugin.json`
- `plugins/codex/agents/*.toml`
- `plugins/codex/assets/agents.json`
- `plugins/codex/assets/agents/*.md`
- Codex plugin-root assets: `plugins/codex/skills/`, `plugins/codex/.mcp.json`, `plugins/codex/.app.json`, `plugins/codex/assets/`
- `.agents/plugins/marketplace.json`
- build/install helper(s) under `src/scribe_mcp/scripts/` including `project_codex_plugin.py`
- `src/scribe_mcp/cli/main.py` for the supported public installer flow
- plugin install docs/tests

**Dependencies:**
- Requires Package 0.1 complete.
- Requires Package 3.1 for final docs alignment.

**Specifications:**
1. Keep separate Claude and Codex plugin roots so `.claude-plugin/` and `.codex-plugin/` remain manifest-only directories.
2. The public-bundle allowlist is exactly `scribe-architect`, `scribe-bug-hunter`, `scribe-coder`, `scribe-doc-writer`, `scribe-research-analyst`, `scribe-review-agent`, and `scribe-security-agent`. `seshat`, `maat`, `ptah`, and `sia` are always excluded from public Claude/Codex bundle assets, `plugins/codex/assets/agents.json`, projection outputs, and release docs.
3. Public bundle assets must not contain Council/private-agent logic, Council-only tools/workflows, or internal orchestration instructions. Explicitly forbid `open_session`, `end_session`, `store_memory`, `ask_self`, `ask_agent`, `ask_council`, operator/team escalation paths, coordinator wait-loop behavior, and similar Council-only instructions. If a public-safe rewrite is not ready for an allowlisted agent, omit it rather than ship internal text.
4. Ship the Claude bundle with only `.claude-plugin/plugin.json` inside `.claude-plugin/`; any shipped `commands/`, `agents/`, `skills/`, `hooks/`, `.mcp.json`, `.lsp.json`, `bin/`, and `settings.json` live at the Claude plugin root. `plugins/claude/hooks/hooks.json` must match the plugin-host schema with a top-level `hooks` object copied from Claude settings JSON rather than top-level event maps.
5. Ship the Codex bundle with only `.codex-plugin/plugin.json` inside `.codex-plugin/`; `skills/`, `.mcp.json`, `.app.json`, and `assets/` live at the Codex plugin root. Treat any `agents/*.toml` as distribution/projection assets only, and allow `plugins/codex/assets/agents.json` to enumerate only the approved public-safe slugs.
6. Register the Codex bundle through `.agents/plugins/marketplace.json` with `source.path` pointing at the Codex plugin root, then project any shipped `agents/*.toml` into Codex-native config/agent surfaces during install/build without destructively replacing existing user config or user-edited agent files. Re-running projection must be idempotent.
7. The public `scribe plugins project-codex` CLI wrapper must catch projection/config/filesystem errors and return clean actionable failures instead of raw tracebacks.
8. Add validation/smoke tests for host layout, hook schema, allowlist/excluded-agent enforcement, no-private-logic scans, non-destructive merge/idempotence, and CLI error handling.

**Patterns to Follow:**
- Claude bundle follows the documented native root layout directly.
- Codex bundle follows the official plugin-root layout and marketplace path rules; `agents/*.toml` remain installer-owned projection assets rather than native plugin components.
- Public plugin assets may expose only public Scribe workflows; omit assets rather than ship Council-specific text.

**Verification:**
- [ ] Claude bundle proves the official root layout and a host-valid `plugins/claude/hooks/hooks.json` with a top-level `hooks` object.
- [ ] Only the approved public-safe slugs appear in public bundle assets, `plugins/codex/assets/agents.json`, and projection outputs; `seshat`, `maat`, `ptah`, and `sia` are absent everywhere.
- [ ] Shipped agent/skill/doc assets contain no Council-only tool/workflow keywords or internal orchestration instructions.
- [ ] Codex bundle proves the official root layout, marketplace `source.path`, and projection catalog rules.
- [ ] Projection preserves existing `config.toml` keys plus existing user agent files by default and is idempotent on repeat runs.
- [ ] The public CLI surfaces clean actionable errors on malformed config, bad plugin roots, or filesystem failures.
- [ ] Both bundles use packaged entry points rather than repo-only shims.

**Out of Scope:** extra plugin marketplace features beyond the official release bundles.
## Phase 4 — Storage, Config, and Test Release Cleanup

**Phase 4 execution map**
- `4.1-A` must land first.
- `4.1-B`, `4.1-C`, and `4.1-D` may proceed in parallel after `4.1-A`.
- `4.2-A` and `4.2-B` may proceed in parallel.
- `4.2-C` requires both `4.2-A` and `4.2-B`.
- `4.2-D` requires `4.2-C`.
- No Phase 4 package may commit operator-specific direct paths; any direct-path behavior must be config/env/public-settings driven.

### Task Package: 4.1-A — Remove live Postgres vector residue

**Owner lane:** Storage/Postgres

**Scope:** Remove the remaining runtime/bootstrap vector extension behavior so the shipped storage stack matches the slim-core release claim.

**Files to Modify:**
- `src/scribe_mcp/storage/postgres/schema.py`
- `src/scribe_mcp/scripts/bootstrap_postgres.py`
- focused storage/bootstrap tests and release docs that mention the bootstrap steps

**Dependencies:**
- Requires Package 2.1 complete.
- Must complete before `4.1-B`, `4.1-C`, and final Phase 4 signoff.

**Specifications:**
1. Remove `CREATE EXTENSION vector` and any vector-extension bootstrap/runtime wording.
2. Preserve legitimate non-vector bootstrap behavior such as `pg_trgm` setup.
3. Keep the change bounded to runtime/bootstrap residue; do not redesign the Postgres backend.

**Verification:**
- [x] No runtime/bootstrap path attempts vector extension enablement. Proof: `src/scribe_mcp/storage/postgres/schema.py` now executes only `PG_TRGM_EXTENSION_SQL`, `src/scribe_mcp/scripts/bootstrap_postgres.py` no longer issues `CREATE EXTENSION IF NOT EXISTS vector;`, and Scribe search for `vector|pgvector` across those two files returned 0 matches on 2026-04-04.
- [x] Storage/bootstrap docs no longer claim vector setup. Proof: `_print_bootstrap_intro()` in `src/scribe_mcp/scripts/bootstrap_postgres.py` now says `Enable pg_trgm`, and `tests/test_bootstrap_postgres_script.py::test_print_bootstrap_intro_omits_vector` covers the wording.
- [x] Focused bootstrap/storage tests cover the revised non-vector behavior. Proof: `pytest -q tests/test_bootstrap_postgres_script.py` passed 14/14 on 2026-04-04, including `test_ensure_schema_and_privileges_enables_pg_trgm_only` and `test_ensure_schema_applies_pg_trgm_without_vector`.

**Out of Scope:** backend/mode resolution, `settings.py` public surface redesign, full Postgres decomposition.
### Task Package: 4.1-B — Publish the public storage/settings contract

**Owner lane:** Config/docs
**Scope:** Publish the supported 1.0 storage contract without hiding public settings.

**Files to Modify:**
- `README.md`
- public install/runtime docs
- `src/scribe_mcp/config/settings.py` (documentation/schema/help text/tests only as needed)
- release config examples/assets

**Dependencies:**
- Requires `4.1-A` complete so docs describe the actual shipped bootstrap/runtime behavior.
- Can run in parallel with `4.1-C` and `4.1-D` after `4.1-A`.

**Specifications:**
1. Document SQLite, Postgres, and remote/client mode as the three public 1.0 storage modes.
2. Separate canonical runtime envs from bootstrap-only convenience envs.
3. Keep `settings.py` public by labeling settings as canonical, compatibility, or advanced/public — not by hiding them.
4. Treat `SCRIBE_DB_SCHEMA` and `SCRIBE_SQLITE_PATH` as compatibility aliases unless removal is proven safe.
5. Ensure examples/docs use portable defaults and never hardcode operator-machine paths.

**Verification:**
- [x] Public docs accurately describe SQLite, Postgres, and remote/client mode.
- [x] Runtime envs vs bootstrap-only envs are clearly separated.
- [x] Canonical names lead the docs, while compatibility/advanced settings remain visible.
- [x] No checked-in config/example uses an operator-specific path.

**Evidence (2026-04-04):** `README.md`, `docs/Scribe_Usage.md`, and `docs/GLOBAL_DEPLOYMENT_GUIDE.md` now publish the three public 1.0 storage modes and separate runtime envs from bootstrap-only Postgres bootstrap conveniences; `src/scribe_mcp/config/settings.py` exports `PUBLIC_STORAGE_MODES` / `PUBLIC_STORAGE_SETTINGS_CONTRACT` so canonical, compatibility, and advanced/public settings stay visible; `tests/test_settings_schema_alias.py` now covers `SCRIBE_SQLITE_PATH` plus `SCRIBE_DB_SCHEMA`, `tests/test_settings_public_contract.py` verifies the public contract metadata, `pytest -q tests/test_settings_schema_alias.py tests/test_settings_public_contract.py` passed 6/6, and targeted Scribe searches for `/home/austin|/Users/|C:\\Users\\` across the touched public docs returned 0 matches.
**Out of Scope:** changing mode-resolution code or deleting advanced public settings merely because they are lightly used.

### Task Package: 4.1-C — Align backend selection with the remote/client contract

**Owner lane:** Runtime/mode

**Scope:** Make backend startup deterministic for the supported remote/client public contract.

**Files to Modify:**
- `src/scribe_mcp/storage/__init__.py`
- `src/scribe_mcp/config/mode_detection.py`
- `src/scribe_mcp/server.py`
- focused mode-resolution/runtime tests

**Dependencies:**
- Requires `4.1-A` complete.
- Consumes the contract published by `4.1-B`.

**Specifications:**
1. Use one coherent storage-mode decision path for SQLite, Postgres, and remote/client startup.
2. Ensure remote/client mode is deterministic when `SCRIBE_REMOTE_URL` is present and/or `SCRIBE_MODE=client` is explicit.
3. Preserve the operator’s constraint that remote/client is supported publicly, but do not expand it into thin-client/shared-host execution semantics.

**Verification:**
- [x] Startup behavior matches the documented three-mode contract.
- [x] Remote/client mode tests prove deterministic selection.
- [x] No new shared-host/thin-client claims are introduced.

**Evidence (2026-04-04):** `resolve_configured_mode()` now gives `mode_detection.py`, `storage/__init__.py`, and `server.py` one shared startup contract; import-time backend creation selects remote when `SCRIBE_REMOTE_URL` is configured, async startup rebinds the concrete backend for the final resolved `OperatingMode`, and `pytest -q tests/test_mode_detection.py tests/test_runtime_mode_resolution.py` passed 13/13 with focused assertions for remote selection, SQLite/Postgres/standalone resolution, and runtime singleton rebinding. The code changes are limited to remote storage/backend access and do not add any shared-host or thin-client execution path.
**Out of Scope:** hosted-runtime redesign, remote tool dispatch, full server decomposition.

### Task Package: 4.1-D — Resolve storage-model compatibility residue

**Owner lane:** Storage/models

**Scope:** Remove or quarantine dead vector dataclasses without breaking a documented public import surface.

**Files to Modify:**
- `src/scribe_mcp/storage/models.py`
- any focused storage-model tests/docs

**Dependencies:**
- Requires `4.1-A` complete.
- Can run in parallel with `4.1-B` and `4.1-C`.

**Specifications:**
1. Remove dead vector dataclasses if they are internal-only.
2. If implementation discovers a documented public import surface, replace removal with explicit compatibility/deprecation shims and document that decision.
3. Keep the package bounded to `storage/models.py` and directly affected tests/docs.

**Verification:**
- [x] `storage/models.py` no longer implies active built-in vector-table/runtime behavior. Proof: `src/scribe_mcp/storage/models.py` no longer defines `VectorIndexRecord`, `VectorShardMetadata`, or any other `Vector*` symbol, and a direct `VectorIndexRecord|VectorShardMetadata` search across live `src/` returned 0 matches on 2026-04-04.
- [x] Any retained compatibility symbol is explicitly documented as compatibility-only. Proof: no compatibility symbols were retained because direct Scribe searches of live `src/`, `tests/`, and `README.md` found no documented/public import surface beyond `src/scribe_mcp/storage/models.py`; the only remaining import-pattern hits are in `.scribe/backups/*` artifacts.
- [x] No unrelated storage-layer refactor is mixed into the package. Proof: the package changed only `src/scribe_mcp/storage/models.py` and the dedicated regression file `tests/test_storage_models_compatibility.py`, and `pytest -q tests/test_storage_models_compatibility.py` passed 1/1 on 2026-04-04.

**Out of Scope:** broader settings cleanup, mode selection, Postgres schema work.
### Task Package: 4.2-A — Repair clean collection and remove import side effects

**Owner lane:** Test gate / doc-management

**Scope:** Restore a trustworthy collect path before broader test reorganization begins.

**Files to Modify:**
- `tests/core/test_manage_docs_semantic_limits.py` *(moved under `tests/core/` by `4.2-C`; still the owned focused regression shard)*
- `src/scribe_mcp/tools/manage_docs_validation.py`
- directly affected focused tests

**Dependencies:**
- Requires Package 2.2 complete.
- Can run in parallel with `4.2-B`.
- Must complete before `4.2-C`.

**Specifications:**
1. Fix or quarantine the broken collect import in the owned `test_manage_docs_semantic_limits.py` shard.
2. Remove the `builtins` mutation from `manage_docs_validation` production import behavior.
3. Keep the package tightly bounded to collection hygiene and import side effects.

**Verification:**
- [x] `pytest --collect-only tests -q` runs cleanly. Proof: 2026-04-04 — the command completed with `2152/2155 tests collected (3 deselected)` and no collection errors.
- [x] Importing `manage_docs_validation` no longer mutates `builtins`. Proof: 2026-04-04 — `tests/core/test_manage_docs_semantic_limits.py` now re-imports `scribe_mcp.tools.manage_docs_validation`, verifies the helper API remains on the module, and confirms `builtins` never gains `ParameterValidationError`, `_validate_inputs`, `_validate_comparison_symbols`, or `create_manage_docs_validator`.
- [x] Any replacement tests cover the supported contract instead of removed helpers. Proof: 2026-04-04 — the owned test file removed the stale `_resolve_semantic_limits` import and now covers the retained `_should_skip_doc_index` wrapper plus the import-side-effect regression.

**Out of Scope:** marker/layout migration, artifact relocation, broad file renames.

### Task Package: 4.2-B — Remove non-regression material from `tests/`

**Owner lane:** Release-suite hygiene

**Scope:** Clear benchmark/demo/generated artifacts out of the shipped regression namespace.

**Files to Modify:**
- `tests/benchmark_connection_pool.py`
- `tests/demo_spec_token_003.py`
- `tests/performance_results_*.json`
- any new destination files under `benchmarks/`, `scripts/benchmarks/`, `examples/`, or another portable non-test path
- docs/config for artifact output destination if needed

**Dependencies:**
- Can run in parallel with `4.2-A`.
- Must complete before `4.2-C`.

**Specifications:**
1. Move demo/benchmark helpers out of `tests/`.
2. Remove committed generated performance artifacts from `tests/`.
3. Route future generated performance output to a gitignored path outside `tests/` using config/env/public settings, never a machine-specific committed path.

**Verification:**
- [x] `tests/` no longer contains the benchmark/demo/generated-artifact files identified by research.
- [x] A portable artifact-output location is documented or configured.
- [x] No operator-specific direct path is committed.

**Evidence:** 2026-04-04 — `tests/benchmark_connection_pool.py` moved to `benchmarks/benchmark_connection_pool.py`, `tests/demo_spec_token_003.py` moved to `examples/demo_spec_token_003.py`, the eight committed `tests/performance_results_*.json` files were removed, `tests/test_performance.py` now defaults generated JSON output to `benchmarks/artifacts/` with `SCRIBE_PERFORMANCE_OUTPUT_DIR` as an env override, `.gitignore` ignores `benchmarks/artifacts/`, `pytest -q tests/test_performance.py -m performance -k 'results_output_dir_defaults_to_gitignored_benchmarks_artifacts or save_results_honors_env_output_dir_override'` passed 2/2 (1 deselected), `find tests -maxdepth 1 -type f \( -name 'performance_results_*.json' -o -name 'benchmark_connection_pool.py' -o -name 'demo_spec_token_003.py' \) | sort` returned no files, and targeted searches across `benchmarks/benchmark_connection_pool.py`, `examples/demo_spec_token_003.py`, `tests/test_performance.py`, and `.gitignore` found 0 `/home/austin`, `/Users/`, or `C:\\Users\\` paths.

**Out of Scope:** marker/layout migration, fixture consolidation, unrelated benchmark redesign.
### Task Package: 4.2-C — Establish the shipped core/integration test contract

**Owner lane:** Test infrastructure

**Scope:** Define the release-grade default test lane and the explicit non-default lanes.

**Files to Modify:**
- `pytest.ini`
- `tests/core/`
- `tests/integration/`
- `tests/integration/storage/`
- any directly affected collection helpers/docs

**Dependencies:**
- Requires `4.2-A` and `4.2-B` complete.

**Specifications:**
1. Introduce the bounded directory contract: `tests/core/`, `tests/integration/`, `tests/integration/storage/`, `tests/fixtures/`, `tests/data/`.
2. Register `core`, `integration`, `postgres`, `performance`, `slow`, and `manual` markers.
3. Curate the default fast lane as `pytest -q tests/core -m "not slow and not performance"`.
4. Add strict marker/testpath policy only after the migration is coherent enough to enforce it safely.

**Verification:**
- [x] The default fast lane is explicit and hermetic. Proof: 2026-04-04 — `pytest.ini` now documents the shipped fast lane as `pytest -q tests/core -m "not slow and not performance"`, and that exact command passed 3/3 against `tests/core/test_manage_docs_semantic_limits.py` with no integration/performance leakage.
- [x] Integration/postgres/performance work is outside the default lane. Proof: 2026-04-04 — `pytest --collect-only -q tests/integration -m "not performance"` collected 48 non-default integration tests, `pytest --collect-only -q tests/integration/storage -m postgres` isolated 5/11 Postgres-only parametrizations with 6 deselections, and `pytest --collect-only -q tests/test_performance.py -m performance` collected 3 dedicated performance tests separate from `tests/core/`.
- [x] Marker names and directory layout are documented and enforced. Proof: 2026-04-04 — `pytest.ini` registers `core`, `integration`, `postgres`, `performance`, `slow`, and `manual` under `--strict-markers`; `tests/conftest.py` applies the path-based `core`/`integration` layout markers for `tests/core/` and `tests/integration/`; and `tests/README.md` plus `tests/data/README.md` document the shipped layout while explicitly deferring strict `testpaths` until `4.2-D` finishes the broader migration safely.

**Out of Scope:** broad behavior renames and deep fixture refactors.

### Task Package: 4.2-D — Rename tests by behavior and consolidate fixtures

**Owner lane:** Test maintainability

**Scope:** Finish the bounded release-suite cleanup by making names and fixtures match the new contract.

**Files to Modify:**
- behavior-renamed test files now under `tests/core/` or `tests/integration/`
- `tests/fixtures/`
- area-local `conftest.py` files where truly needed

**Dependencies:**
- Requires `4.2-C` complete.

**Specifications:**
1. Rename phase/spec/package/ticket-styled test filenames to `test_<feature>_<behavior>.py` names.
2. Move recurring fixtures into `tests/fixtures/` or area-local `conftest.py` files.
3. Keep the global harness from regrowing while preserving only the shared setup that is truly global.

**Verification:**
- [x] Release-facing test filenames are behavior-based rather than phase/spec based. Proof: 2026-04-04 — `tests/integration/test_integration_phase5.py` was renamed to `tests/integration/test_toolkit_workflows.py`, `tests/integration/storage/test_storage_backend_conformance.py` was renamed to `tests/integration/storage/test_storage_backend_shared_contract.py`, and `pytest --collect-only -q tests/integration -m "not performance"` now enumerates only the behavior-named release-slice files under `tests/integration/`.
- [x] Recurring fixtures are centralized or localized intentionally. Proof: 2026-04-04 — the shared `project_tree` / `router` fixtures moved into `tests/integration/conftest.py`, the storage backend lifecycle fixture moved into `tests/integration/storage/conftest.py`, and the top-level `tests/conftest.py` remained limited to global bootstrap/cleanup/marker policy.
- [x] The resulting suite remains aligned with the `4.2-C` marker/layout contract. Proof: 2026-04-04 — `pytest -q tests/integration/test_toolkit_workflows.py::TestSessionTracking::test_record_and_check_file_read` passed 1/1, `pytest -q tests/integration/storage/test_storage_backend_shared_contract.py -m "not postgres" -k project_entry_roundtrip` passed 1/1 with 10 deselections, `pytest -q tests/core -m "not slow and not performance"` still passed 3/3, `pytest --collect-only -q tests/integration -m "not performance"` still collected 48 tests, and `pytest --collect-only -q tests/integration/storage -m postgres` still collected 5/11 tests with 6 deselections.
**Out of Scope:** new benchmark systems, unrelated performance tuning, full repo-wide taxonomy beyond the Phase 4 release slice.
## Phase 5 — Release Remediation and Signoff
### Task Package: 5.1 — Stable-release verification matrix (historical evidence)

**Status:** Completed on 2026-04-04 — **NO-SHIP**.

**Scope:** Preserve the failed signoff evidence as the bounded reason this phase was reopened.

**Evidence summary:**
1. The rebuilt wheel still shipped forbidden vector package files: `scribe_mcp/tools/vector_search.py`, `scribe_mcp/plugins/vector_indexer.py`, `scribe_mcp/plugins/vector_indexer.json`, `scribe_mcp/scripts/check_vector_index.py`, `scribe_mcp/scripts/reindex_docs.py`, and `scribe_mcp/scripts/reindex_vector.py`.
2. The rebuilt sdist and regenerated `src/scribe_mcp.egg-info/SOURCES.txt` still carried vector residue, including `src/scribe_mcp/config/vector_config.py` and the Phase 2 vector-removal regression test.
3. Rebuilt `PKG-INFO` / wheel `METADATA` still carried stale vector/torch and multi-tenant text derived from `README.md`.
4. `README.md` / `deploy/README.md` still omitted the full approved loopback-authenticated default-allow plus global-force-disable wording.

**Out of Scope:** implementing the fix. `5.1` is the locked historical gate that justified `5.2-A` through `5.5`.

### Task Package: 5.2-A — Wheel/package-namespace residue cleanup

**Status:** Completed on 2026-04-04.

**Scope:** Remove vector-only runtime/plugin/script files from the shipped wheel surface without reopening already-cleared runtime behavior.

**Files to Modify:**
- `src/scribe_mcp/tools/__init__.py` — remove any remaining exports/aliases that keep vector-only tool files on the public package surface.
- `src/scribe_mcp/tools/base/tool_metadata.py` — remove any vector-only metadata/examples that still belong to deleted shipped files.
- `src/scribe_mcp/scripts/scribe_probe.py` — remove any probe hook that still expects vector-only shipped files.

**Files to Remove or Relocate Out of Shipped Package Scope:**
- `src/scribe_mcp/tools/vector_search.py`
- `src/scribe_mcp/plugins/vector_indexer.py`
- `src/scribe_mcp/plugins/vector_indexer.json`
- `src/scribe_mcp/scripts/check_vector_index.py`
- `src/scribe_mcp/scripts/reindex_docs.py`
- `src/scribe_mcp/scripts/reindex_vector.py`

**Dependencies:** none; this package started first.

**Specifications:**
1. Make the real `src/scribe_mcp/` package namespace match the already-accepted slim-core contract.
2. Prefer source removal or relocation out of the shipped package namespace over trying to patch generated wheel metadata after the build.
3. Keep changes limited to the files that currently leak into the wheel; do not revisit storage, security, plugin-bundle, or test-layout packages.

**Implementation note:** The live `src/scribe_mcp/` namespace and owned helper files were already clean when this package started. The actual wheel leak came from stale generated package-surface copies under `build/lib/scribe_mcp/{tools,plugins,scripts}/...`, so `5.2-A` deleted only those generated residue files and rebuilt the wheel to prove the slim-core contract now holds at the artifact layer.

**Patterns to Follow:**
- Match the slim-core contract documented in `ARCHITECTURE_GUIDE.md` §4.3–4.6.
- Treat generated wheel contents as proof only; fix the source package surface instead.

**Verification:**
- [x] `python -m zipfile -l /tmp/scribe_release_audit_20260403_52a_clean/scribe_mcp-2.2-py3-none-any.whl | grep -Eic 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector'` returned `0` on 2026-04-04 after the cleanup.
- [x] Direct Scribe searches against `src/scribe_mcp/tools/__init__.py`, `src/scribe_mcp/tools/base/tool_metadata.py`, and `src/scribe_mcp/scripts/scribe_probe.py` returned 0 matches for `vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector`.

**Out of Scope:** README copy changes, `SOURCES.txt`/sdist rules, final ship decision.

### Task Package: 5.2-B — sdist and `SOURCES.txt` hygiene

**Status:** Completed on 2026-04-04.

**Scope:** Make the rebuilt source distribution and regenerated `SOURCES.txt` tell the truth about the cleaned package surface.

**Files to Modify:**
- `pyproject.toml` — adjust the real build/include surface if required.
- the repo's explicit sdist include/exclude control surface, if needed (for example `MANIFEST.in` if that is the least-invasive fix).

**Generated Proof Artifacts (never hand-edit):**
- `src/scribe_mcp.egg-info/SOURCES.txt`
- rebuilt `/tmp/.../scribe_mcp-2.2.tar.gz`

**Dependencies:** required `5.2-A` complete so the manifest pass described the real post-cleanup package surface.

**Specifications:**
1. Remove `src/scribe_mcp/config/vector_config.py` from regenerated `SOURCES.txt` and the rebuilt sdist.
2. Remove the Phase 2 vector-removal regression test from the shipped source-distribution surface if it is still being swept into the tarball.
3. Regenerate build outputs from the real manifest/include inputs; do not patch `SOURCES.txt` directly.

**Patterns to Follow:**
- Generated `egg-info` is evidence, not the fix surface.
- Keep the change bounded to packaging-manifest truth, not broader runtime behavior.

**Verification:**
- [x] `grep -Eic 'vector|test_phase2_vector_core_removal' src/scribe_mcp.egg-info/SOURCES.txt` returned `0` on 2026-04-04 after adding root `MANIFEST.in` excludes for `src/scribe_mcp/config/vector_config.py` and `tests/test_phase2_vector_core_removal.py` and rebuilding with `python -m build --sdist --outdir /tmp/scribe_release_audit_20260403_52b .`.
- [x] `tar -tzf /tmp/scribe_release_audit_20260403_52b/scribe_mcp-2.2.tar.gz | grep -Eic 'vector|test_phase2_vector_core_removal'` returned `0` on 2026-04-04, confirming the rebuilt sdist no longer ships vector-only config/test residue.

**Historical note:** `5.2-B` fixed the sdist/manifest surface only. It is not the correct template for the remaining wheel blocker.

**Out of Scope:** wheel-only residue already owned by `5.2-A`, README/deploy copy cleanup, smoke-test reruns beyond the build needed to regenerate proof.

### Task Package: 5.2-C — README/deploy/METADATA truth cleanup

**Status:** Completed on 2026-04-04.

**Scope:** Clean the public release narrative so README-derived metadata and deployment docs match the approved 1.0 contract.

**Files to Modify:**
- `README.md`
- `deploy/README.md`

**Generated Proof Artifacts (never hand-edit):**
- regenerated `src/scribe_mcp.egg-info/PKG-INFO`
- rebuilt wheel `METADATA`

**Dependencies:** may run in parallel with `5.2-A` / `5.2-B`; `5.3` waited for all three packages.

**Specifications:**
1. Remove stale vector/torch warning prose and the deferred `Multi-tenant` marketing claim from `README.md`.
2. Publish the exact approved posture split in both README and deploy docs:
   - loopback-authenticated trusted SSE = supported default-allow posture
   - global force-disable is available in every posture and overrides every allow path
   - non-loopback/network-exposed = default-deny unless explicitly force-enabled
3. Ensure the regenerated long-description artifacts (`PKG-INFO` / wheel `METADATA`) inherit only the cleaned release narrative.

**Patterns to Follow:**
- `pyproject.toml` already points package metadata at `README.md`; README is therefore the metadata source of truth.
- Keep docs narrow: no new hosted/shared-host roadmap promises.

**Verification:**
- [x] Rebuilt `PKG-INFO` / wheel `METADATA` contain no `vector`, `torchvision mismatch`, or `Multi-tenant` marketing residue. Proof: 2026-04-04 — `python -m build --wheel --outdir /tmp/scribe_release_audit_20260403_dist .` regenerated `src/scribe_mcp.egg-info/PKG-INFO` plus `/tmp/scribe_release_audit_20260403_dist/scribe_mcp-2.2-py3-none-any.whl`, and the follow-up residue scans reported `PKG-INFO_RESIDUE=NONE` and `WHEEL_METADATA_RESIDUE=NONE` for `grep -nEi 'vector|BertModel|torchvision|Multi-tenant|multi-tenant' src/scribe_mcp.egg-info/PKG-INFO` plus `unzip -p /tmp/scribe_release_audit_20260403_dist/scribe_mcp-2.2-py3-none-any.whl '*/METADATA' | grep -nEi 'vector|BertModel|torchvision|Multi-tenant|multi-tenant'`.
- [x] `README.md` and `deploy/README.md` both publish the approved posture wording exactly. Proof: 2026-04-04 — `README.md:377-379` and `deploy/README.md:65-67` now match the approved three-line split verbatim: `loopback-authenticated trusted SSE = supported default-allow posture`, `global force-disable is available in every posture and overrides every allow path`, and `non-loopback/network-exposed = default-deny unless explicitly force-enabled`.

**Out of Scope:** wheel file deletion, sdist manifest rules, changing runtime trust semantics.

### Task Package: 5.3 — Final rebuilt-artifact verification rerun (historical NO-SHIP gate)

**Status:** Completed on 2026-04-04 — **NO-SHIP**.

**Scope:** Preserve the coherent rerun bundle that proved only one blocker remained after `5.2-A` / `5.2-B` / `5.2-C`.

**Files Modified:**
- `CHECKLIST.md`
- `PHASE_PLAN.md`

**Files Rebuilt / Inspected:**
- rebuilt sdist/wheel under `/tmp/scribe_release_audit_20260403_dist/final_53/`
- regenerated `src/scribe_mcp.egg-info/{PKG-INFO,requires.txt,SOURCES.txt}`

**Dependencies:** required `5.2-A`, `5.2-B`, and `5.2-C` complete.

**Rerun evidence summary:**
1. `python -m build --sdist --wheel --outdir /tmp/scribe_release_audit_20260403_dist/final_53 .` produced one coherent final bundle: `/tmp/scribe_release_audit_20260403_dist/final_53/scribe_mcp-2.2.tar.gz` plus `/tmp/scribe_release_audit_20260403_dist/final_53/scribe_mcp-2.2-py3-none-any.whl`.
2. Artifact scans from that same bundle found one remaining blocker: `python -m zipfile -l /tmp/scribe_release_audit_20260403_dist/final_53/scribe_mcp-2.2-py3-none-any.whl | grep -En 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector|vector_config'` returned `43:scribe_mcp/config/vector_config.py`. The paired sdist / `SOURCES.txt` / `PKG-INFO` / wheel `METADATA` scans were empty.
3. Doc truth remained correct in the same rerun window: `README.md:377-379` and `deploy/README.md:65-67` still matched the approved release posture wording, while regenerated `PKG-INFO` and wheel `METADATA` stayed free of vector / torch-warning / multi-tenant residue.
4. Retained smoke lanes all passed from the same rerun window: `pytest -q tests/test_transport_sse.py` (32 passed), `pytest -q tests/test_phase1_package12_hardening.py` (7 passed), `pytest -q tests/test_plugin_bundles.py` (8 passed), `pytest -q tests/core -m "not slow and not performance"` (3 passed), and a clean-target wheel-install smoke that installed the rebuilt wheel into `/tmp/scribe_release_audit_20260403_dist/final_53_install_smoke` and imported `scribe_mcp` successfully as version `2.2`.
5. Because the rebuilt wheel still ships `scribe_mcp/config/vector_config.py`, `5.3` stops here with a bounded release-surface escalation and no new implementation work.

**Out of Scope:** any new implementation work after the rerun; `5.3` is locked historical proof and must not be rewritten as a pass.

### Task Package: 5.4 — Generated-tree cleanup for the wheel-only `vector_config.py` residue

**Status:** Complete (2026-04-04).

**Scope:** Remove the final wheel-only leak by cleaning stale generated packaging residue before rebuilding the probe wheel.

**Files Modified / Removed:**
- `build/lib/scribe_mcp/config/vector_config.py` — deleted the stale generated copy that was still being swept into the wheel.

**Already-landed source truth preserved:**
- `src/scribe_mcp/config/vector_config.py` stayed deleted.
- `MANIFEST.in` stayed free of the stale exclude for that deleted source file.

**Execution summary:**
1. Re-verified the bounded `5.4` contract and the three open checklist items before changing anything.
2. Deleted only `build/lib/scribe_mcp/config/vector_config.py`; no broader `build/lib/scribe_mcp/config/` or `build/lib/scribe_mcp/` subtree cleanup was needed.
3. Re-ran `rg -n "vector_config" src/scribe_mcp pyproject.toml MANIFEST.in build/lib/scribe_mcp/config`, which returned no matches after the deletion.
4. Rebuilt the probe wheel with `python -m build --wheel --outdir /tmp/scribe_release_audit_20260403_dist/phase54_probe .`.
5. Re-ran `python -m zipfile -l /tmp/scribe_release_audit_20260403_dist/phase54_probe/scribe_mcp-2.2-py3-none-any.whl | grep -En 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector|vector_config'`, which returned no matches.

**Patterns Followed:**
- Stayed inside `ARCHITECTURE_GUIDE.md` §4.3–4.6 by treating this as generated-tree wheel hygiene only.
- Preserved the already-landed source deletion and avoided `pyproject.toml`, README, runtime config, plugin, storage, and test scope.

**Verification:**
- [x] `rg -n "vector_config" src/scribe_mcp pyproject.toml MANIFEST.in build/lib/scribe_mcp/config` returned no matches after deleting the stale generated file on 2026-04-04.
- [x] `python -m build --wheel --outdir /tmp/scribe_release_audit_20260403_dist/phase54_probe .`
- [x] `python -m zipfile -l /tmp/scribe_release_audit_20260403_dist/phase54_probe/scribe_mcp-2.2-py3-none-any.whl | grep -En 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector|vector_config'` returned no matches on 2026-04-04.
- [x] No wider generated subtree cleanup or escalation was required; `5.5` is now unblocked for the final rerun/signoff bundle.

**Out of Scope:** final ship/no-ship determination, sdist/`SOURCES.txt`/metadata revalidation, or any new source changes beyond preserving the already-landed deletion.

### Task Package: 5.5 — Final rebuilt-artifact rerun and signoff

**Status:** Complete (2026-04-04).

**Scope:** Run one final coherent release bundle after `5.4` and record the final ship/no-ship decision.

**Files Modified:**
- `CHECKLIST.md` — closed the Phase 5 rerun/signoff items from the final evidence bundle.
- `PHASE_PLAN.md` — recorded the `5.5` outcome and updated milestone tracking.

**Files Rebuilt / Inspected:**
- `/tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2.tar.gz`
- `/tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2-py3-none-any.whl`
- regenerated `src/scribe_mcp.egg-info/{PKG-INFO,requires.txt,SOURCES.txt}`

**Dependencies:** `5.4` completed with a clean `phase54_probe` wheel.

**Execution summary:**
1. Rebuilt once with `python -m build --sdist --wheel --outdir /tmp/scribe_release_audit_20260403_dist/final_55 .`, producing the final sdist/wheel bundle and regenerated egg-info metadata.
2. Re-ran the exact historical artifact scans from the same bundle, and all five returned no matches: the wheel blocker scan, sdist blocker scan, `SOURCES.txt` blocker scan, `PKG-INFO` residue scan, and wheel `METADATA` residue scan.
3. Re-read `README.md:377-379` and `deploy/README.md:65-67`; both still matched the approved loopback-authenticated default-allow / global-force-disable / non-loopback default-deny-unless-force-enabled wording.
4. Re-ran only the retained smoke lanes and kept them green in the same rerun window: `pytest -q tests/test_transport_sse.py` (32 passed), `pytest -q tests/test_phase1_package12_hardening.py` (7 passed), `pytest -q tests/test_plugin_bundles.py` (8 passed), and `pytest -q tests/core -m "not slow and not performance"` (3 passed).
5. Re-ran the local wheel-install smoke against `/tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2-py3-none-any.whl` by installing into `/tmp/scribe_release_audit_20260403_dist/final_55_install_smoke_20260404T2226Z`, importing `scribe_mcp` successfully, and confirming `importlib.metadata.version('scribe-mcp')` resolved to `2.2`.
6. Because the rebuilt artifact surfaces and retained smoke lanes were all clean in that single bundle, the post-`5.4` release decision moves from the preserved historical `5.3` NO-SHIP record to **SHIP**.

**Patterns Followed:**
- Matched the exact `5.3` / `5.5` scan commands and did not widen verification scope beyond the retained smoke lanes plus the local wheel-install smoke.
- Recorded one build bundle and one decision; no source/runtime/package/discovery changes were made.
- Preserved the historical `5.3` NO-SHIP evidence while superseding only the final decision state with the coherent `final_55` bundle.

**Verification:**
- [x] `python -m zipfile -l /tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2-py3-none-any.whl | grep -En 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector|vector_config'` returned no matches on 2026-04-04.
- [x] `tar -tzf /tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2.tar.gz | grep -En 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector|vector_config|test_phase2_vector_core_removal'` returned no matches on 2026-04-04.
- [x] `grep -En 'vector_search|vector_indexer|check_vector_index|reindex_docs|reindex_vector|vector_config|test_phase2_vector_core_removal' src/scribe_mcp.egg-info/SOURCES.txt` returned no matches on 2026-04-04.
- [x] `grep -Eni 'vector|BertModel|torchvision|Multi-tenant|multi-tenant' src/scribe_mcp.egg-info/PKG-INFO` returned no matches on 2026-04-04.
- [x] `unzip -p /tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2-py3-none-any.whl '*/METADATA' | grep -Eni 'vector|BertModel|torchvision|Multi-tenant|multi-tenant'` returned no matches on 2026-04-04.
- [x] `pytest -q tests/test_transport_sse.py` → 32 passed.
- [x] `pytest -q tests/test_phase1_package12_hardening.py` → 7 passed.
- [x] `pytest -q tests/test_plugin_bundles.py` → 8 passed.
- [x] `pytest -q tests/core -m "not slow and not performance"` → 3 passed.
- [x] Local wheel-install smoke against `/tmp/scribe_release_audit_20260403_dist/final_55/scribe_mcp-2.2-py3-none-any.whl` passed in `/tmp/scribe_release_audit_20260403_dist/final_55_install_smoke_20260404T2226Z`, with `importlib.metadata.version('scribe-mcp')` = `2.2`.

**Out of Scope:** any new fix implementation discovered during the rerun. No such implementation was attempted because the final bundle stayed clean.

## Milestone Tracking
<!-- ID: milestone_tracking -->
### Historical 2.2 closure summary
- Packages `5.6-A` through `5.6-E` remain the authoritative record for the 2026-04-04 `SHIP` decision from `/tmp/scribe_release_audit_20260403_dist/final_56d_20260404T231620Z`.
- Phase 6 is a new bounded release-wave extension, not a reopening of the historical 2.2 signoff.

### Next-wave sequencing rules (2026-04-05 synchronized split/auth release; extended runtime/bridge/doc ordering)
- `6.0` is docs-only architecture publication and is complete.
- `6.1-A` (core/extension boundary) and `6.2-A` (optional public remote auth plumbing) may still run in parallel because they touch separate Scribe file groups.
- `6.1-B` depends on `6.1-A` because repo-truth vs overlay classification must follow the final package boundary.
- `6.1-C` depends on `6.1-B` because runtime JSON/state/log path moves and `.gitignore` truth must implement the published overlay policy, not invent a second one.
- `6.2-B` depends on `6.2-A` because it freezes auth tests/docs from the landed client contract.
- `6.3-A` depends on `6.1-A` and `6.1-C` because bridge/plugin/runtime ownership cannot be frozen before the extension boundary and runtime directories are settled.
- `6.3-B` depends on `6.2-A` and `6.3-A` because `council_mcp` runtime clients need both the final auth contract and the final bridge/extension boundary.
- `6.3-C` depends on `6.1-A` and `6.3-A` because export/import cleanup needs the final public/core vs extension split plus the final bridge ownership story.
- `6.3-D` depends on `6.3-B` and `6.3-C` because deploy/scaffold/docs/tests must reflect the final auth names and the final bridge/package boundary at the same time.
- `6.4-A` depends on `6.1` through `6.3` landing because it freezes release truth, compatibility, and the future `v3` decision gate from built artifacts rather than assumptions.
- `6.4-B` depends on `6.4-A` and is the **only** package allowed to update README tree/file-map artifacts; no earlier package may publish interim tree snapshots in README while structure is still moving.

### Task Package: 6.0 — Publish the synchronized cross-repo release-wave contract
**Status:** Complete (2026-04-05, docs-only architecture package; extended 2026-04-05).

**Scope:** Update the governed docs in `scribe_release_audit_20260403` with the bounded wave for the public/core split, local/standard core default posture, optional remote-client auth completion, runtime JSON/path hygiene, bridge/extension/package-boundary unification, `council_mcp` lockstep compatibility, and final documentation sequencing.

**Files Modified:**
- `.scribe/docs/dev_plans/scribe_release_audit_20260403/ARCHITECTURE_GUIDE.md`
- `.scribe/docs/dev_plans/scribe_release_audit_20260403/PHASE_PLAN.md`
- `.scribe/docs/dev_plans/scribe_release_audit_20260403/CHECKLIST.md`

**Dependencies:** upstream research report complete plus bounded live-source verification.

**Verification:**
- [x] The design cites upstream research plus bounded live-source verification for runtime paths and bridge seams.
- [x] The docs distinguish historical 2.2 closure from the new synchronized release wave.
- [x] The package plan now states that README/file-map work is last, not an early churn package.

**Out of Scope:** any code, test, packaging, or deploy edits.

### Task Package: 6.1-A — Extract council template provider into an optional `scribe-council` package boundary
**Owner:** `scribe_mcp` core/package lane.

**Scope:** Remove council-only template/federation surface from the public `scribe-mcp` wheel by moving it into a separate optional distribution in the same repository while keeping `scribe-mcp` as the public core package name.

**Files to Modify:**
- `pyproject.toml` — remove the `project.entry-points."council.templates"` registration and stop shipping `council_templates/**/*` from the public core wheel.
- `src/scribe_mcp/council_templates/__init__.py` — reduce to the one-wave deprecation shim defined by the architecture contract.
- core release/build docs that describe the public package surface (dedicated docs only; no README tree updates yet).

**Files to Create:**
- `packages/scribe_council/pyproject.toml` — required same-repo optional distribution boundary for this wave.
- `packages/scribe_council/src/scribe_council/__init__.py`
- `packages/scribe_council/src/scribe_council/council_templates/__init__.py`
- package-local extension docs/release notes.

**Dependencies:** requires `6.0` complete.

**Specifications:**
1. Keep `scribe-mcp` as the public runtime package and create the optional council extension as a same-repo multi-package boundary under `packages/scribe_council/`; no sibling-repository or alternate layout decision is part of this wave.
2. Publish the `council.templates` entry point from the extension package, not from the core wheel.
3. Keep `src/scribe_mcp/council_templates/__init__.py` only as a one-wave deprecation shim that forwards to `scribe_council.council_templates`, emits a deprecation warning, and is removed by the next breaking release / no later than the `v3` boundary.
4. Ensure the split is visible from built artifacts (`entry_points.txt`, package data, install metadata), not just source layout.

**Verification:**
- [ ] Built `scribe-mcp` wheel no longer contains the `council.templates` entry point or `council_templates/**/*`.
- [ ] Built `scribe-council` package provides the template provider successfully.
- [ ] Any temporary shim emits a clear deprecation warning and is documented with a removal target.

**Out of Scope:** runtime path hygiene, bridge activation cleanup, and `council_mcp` consumer updates.

### Task Package: 6.1-B — Publish repo-truth vs local-runtime overlay policy
**Status:** Complete (2026-04-05).
**Owner:** `scribe_mcp` release-surface lane.

**Scope:** Freeze the policy that distinguishes tracked repo truth from gitignored local runtime/operator overlays without yet touching README tree/file-map artifacts.

**Files to Modify:**
- `.gitignore`
- package-manifest/include rules that currently risk shipping local overlays or stale build artifacts
- dedicated release-surface docs only (no README changes)

**Files to Create:**
- `docs/RELEASE_SURFACE.md` — authoritative tracked-vs-runtime policy.
- `docs/examples/mcp.json.example`
- `docs/examples/opencode.json.example`
- optional `docs/RUNTIME_LAYOUT.md` if a focused runtime policy doc is cleaner than embedding all detail in `RELEASE_SURFACE.md`.

**Dependencies:** requires `6.1-A` complete so the package boundary is already explicit.

**Specifications:**
1. Reclassify repo-local `.council/`, `.mcp.json`, `opencode.json`, `.scribe/cli/*.json`, `.scribe/state/*.json`, `.scribe/logs/*`, and operator-specific `AGENTS.md` / `.claude/` / `.codex/` material as local overlays/runtime state, not public release truth.
2. State clearly that tracked source/manifests, shipped bridge assets, tracked examples, and release docs are repo truth.
3. Publish the policy in dedicated docs/examples only; do **not** touch README/file-map artifacts in this package.
4. Ensure `build/`, `dist/`, and other stale artifact directories cannot define ship surface or be mistaken for source-of-truth package content.

**Verification:**
- [x] Dedicated docs/examples describe the tracked-vs-runtime boundary without relying on README tree snapshots.
- [x] `.gitignore` and package-manifest rules reflect the policy.
- [x] Public guidance now points to tracked examples/docs rather than repo-root overlay files.

**Evidence (2026-04-05):**
1. Added `docs/RELEASE_SURFACE.md`, `docs/examples/mcp.json.example`, and `docs/examples/opencode.json.example`; the new policy explicitly classifies `.council/`, `.mcp.json`, `opencode.json`, `AGENTS.md`, `.claude/**`, and `.codex/**` as local overlays and points downstream guidance at tracked docs/examples instead.
2. `.gitignore` now ignores `opencode.json`, `.scribe/cli/*.json`, `.scribe/state/`, `build/`, `dist/`, and `pip-wheel-metadata/`; `6.1-C` has now finished the runtime-writer cleanup that makes `.scribe/state/` the sole mutable runtime-state namespace.
3. `MANIFEST.in` now prunes `build`, `dist`, `.council`, `.claude`, `.codex`, `.scribe`, `logs`, and `state`, and excludes `.mcp.json`, `opencode.json`, `AGENTS.md`, `CLAUDE.md`, and `tool_calls.jsonl` so local overlays/build residue cannot define the sdist surface.
4. Narrow verification passed with `git check-ignore -v --stdin`, `rg -n` over `MANIFEST.in` and `docs/RELEASE_SURFACE.md`, and `python -m json.tool` on both tracked example JSON files.

**Out of Scope:** moving runtime writers or editing README/file-map artifacts.

### Task Package: 6.1-C — Runtime JSON/state/log path hygiene and gitignore truth
**Status:** Complete (2026-04-05).
**Owner:** `scribe_mcp` runtime-hygiene lane.

**Scope:** Align mutable runtime files with the `.scribe/*` runtime model by keeping CLI session JSON in `.scribe/cli/`, moving repo-root `state/*.json` writers into `.scribe/state/`, and making gitignore/object-store behavior match the actual runtime path policy.

**Files to Modify:**
- `.gitignore`
- `src/scribe_mcp/config/paths.py`
- `src/scribe_mcp/cli/session_store.py`
- `src/scribe_mcp/utils/rotation_state.py`
- `src/scribe_mcp/utils/audit.py`
- any shared runtime-path helper touched by those writers

**Files to Create:**
- `src/scribe_mcp/config/runtime_paths.py` if a single helper is needed to stop new path drift.

**Dependencies:** requires `6.1-B` complete.

**Specifications:**
1. Keep `.scribe/cli/*.json` as repo-local runtime output for per-user CLI session/profile state, but ignore the whole mutable surface rather than just `default.json`.
2. Move repo-root `state/*.json` outputs to `.scribe/state/`; no mutable JSON writer may keep using repo-root `state/` after this package lands.
3. Keep `.scribe/logs/` as the runtime log namespace and ensure no package/build/doc artifact treats it as shipped truth.
4. If runtime path helpers are duplicated, centralize them so CLI, rotation/audit, and future runtime writers cannot drift again.
5. Update dedicated runtime/release-surface docs, but leave README/file-map untouched.

**Verification:**
- [x] No live runtime JSON writer defaults to repo-root `state/`.
- [x] `.gitignore` covers the real `.scribe/cli/*.json` and `.scribe/state/` runtime surfaces.
- [x] Runtime path helpers resolve the same local namespaces used by code, docs, and object-store exclusions.

**Evidence (2026-04-05):**
1. `src/scribe_mcp/config/paths.py` now centralizes the shared `.scribe/{cli,state,logs}` runtime namespace constants/helpers; `src/scribe_mcp/cli/session_store.py` remains pinned to `.scribe/cli/`; `src/scribe_mcp/utils/rotation_state.py` and `src/scribe_mcp/utils/audit.py` now default to `.scribe/state/` via `runtime_state_dir()` instead of repo-root `state/`.
2. `src/scribe_mcp/object_store/keys.py` now denies `.scribe/state/` alongside `.scribe/cli/` and `.scribe/logs/`; `docs/RELEASE_SURFACE.md` now treats those three namespaces as local runtime-only surfaces; and `.gitignore` now ignores `.scribe/cli/*.json`, `.scribe/state/`, and `.scribe/logs/` without preserving repo-root `state/*.json` as an active runtime path.
3. Narrow verification passed with `python -m compileall -q src/scribe_mcp/config/paths.py src/scribe_mcp/cli/session_store.py src/scribe_mcp/utils/rotation_state.py src/scribe_mcp/utils/audit.py src/scribe_mcp/object_store/keys.py tests/test_runtime_path_policy.py`, `pytest -q tests/test_runtime_path_policy.py` (`4 passed in 0.07s`), `git check-ignore -v .scribe/cli/runtime-policy.json .scribe/state/rotation_state.json`, and targeted `rg -n` checks confirming no remaining `repo_root() / "state"` default in the touched code/docs plus aligned `.scribe/{cli,state,logs}` namespace references across `.gitignore`, `docs/RELEASE_SURFACE.md`, and the shared helper surfaces.

**Out of Scope:** remote auth or bridge activation work.

### Task Package: 6.2-A — Finish optional public remote/client auth plumbing in `scribe_mcp`
**Status:** Complete (2026-04-05).
**Owner:** `scribe_mcp` storage/runtime lane.

**Scope:** Complete the optional supported public remote/client auth contract by loading a client token from settings, passing it into `RemoteStorageBackend`, and sending it on every remote backend request using the existing SSE/REST auth model, while keeping local/standard core usage as the shipped default posture.

**Files to Modify:**
- `src/scribe_mcp/config/settings.py`
- `src/scribe_mcp/storage/__init__.py`
- `src/scribe_mcp/storage/remote.py`
- `src/scribe_mcp/config/mode_detection.py`

**Dependencies:** requires `6.0` complete.

**Specifications:**
1. Add a client-side remote token setting (recommended canonical name: `SCRIBE_REMOTE_AUTH_TOKEN`) with fallback aliases to the existing server-side token names for single-env deployments.
2. Pass the resolved token through `create_storage_backend()` into `RemoteStorageBackend`.
3. Extend `RemoteStorageBackend` so `setup()`, `_call()`, and `execute_batch()` emit auth on every request; prefer `Authorization: Bearer <token>` and keep compatibility with the server’s accepted `x-scribe-auth` path if an explicit fallback header is needed.
4. Return clear auth failures for `401`/`403` instead of surfacing them only as generic remote unavailability.
5. Keep remote health probing and `SCRIBE_REMOTE_FALLBACK` behavior coherent with the new auth contract.

**Verification:**
- [ ] `RemoteStorageBackend` sends the configured token on backend and batch requests.
- [ ] Unauthorized remote responses surface as explicit auth errors.
- [ ] Client mode still probes/falls back coherently when the remote is unavailable.

**Out of Scope:** server-side auth redesign or any `council_mcp` changes.

### Task Package: 6.2-B — Publish optional remote/client auth regressions and transition docs
**Status:** Complete (2026-04-05).
**Owner:** `scribe_mcp` test/docs lane.

**Scope:** Freeze the optional supported remote/client auth contract with focused tests and dedicated docs once `6.2-A` lands, while keeping local/standard core usage as the documented default posture and deferring README updates until the final documentation package.

**Files to Modify:**
- focused remote/client test files under `tests/`
- dedicated docs only; no README tree/file-map edits

**Files to Create:**
- `docs/REMOTE_CLIENT.md` — public remote/client auth and posture contract.

**Dependencies:** requires `6.2-A` complete.

**Specifications:**
1. Add regressions for client token loading, header emission, and explicit unauthorized failure handling.
2. Document that local/standard core usage remains the shipped default public posture and that remote/client is an optional authenticated capability.
3. Document the three release postures: loopback-local, managed private-mesh/Tailscale, and unsupported casual public exposure.
4. State clearly that `0.0.0.0` is allowed only for managed/private-mesh deployment guidance and must be paired with auth.
5. Keep README/file-map untouched; this package writes only the dedicated auth/posture doc.

**Verification:**
- [x] Focused remote/client auth tests pass via `pytest -q tests/test_remote_backend.py tests/test_runtime_mode_resolution.py` (`54 passed in 0.26s`).
- [x] Dedicated docs publish the exact default-vs-optional posture split plus the bind/auth posture split via `docs/REMOTE_CLIENT.md` sections 1-5.
- [x] The docs no longer imply unauthenticated or default-by-posture remote/client mode is a supported deployment recipe; `docs/REMOTE_CLIENT.md` explicitly marks remote/client as optional/authenticated, marks casual public exposure as unsupported, and restricts `0.0.0.0` guidance to managed/private-mesh deployments with auth.

**Out of Scope:** `council_mcp` adoption work or README edits.

### Task Package: 6.3-A — Unify bridge / extension / plugin seams before downstream adoption
**Owner:** `scribe_mcp` extension-runtime lane.

**Scope:** Make the bridge surface coherent before any downstream package consumes it by keeping the generic bridge runtime contract in core, moving council-specific shipped bridge assets to the optional extension package, and aligning manifest discovery, plugin instantiation, policy checks, hook/runtime activation, and package ownership under one release contract.

**Files to Modify:**
- `src/scribe_mcp/server.py`
- `src/scribe_mcp/bridges/registry.py`
- `src/scribe_mcp/bridges/policy.py`
- `src/scribe_mcp/bridges/hooks.py`
- `src/scribe_mcp/bridges/plugin.py`
- any bridge-manifest loader or extension registration module that defines package ownership for shipped bridges

**Files to Create:**
- a shared bridge-runtime boundary/helper module only if needed to avoid duplicate ownership logic between registry, hooks, and plugin loading.

**Dependencies:** requires `6.1-A` and `6.1-C` complete.

**Specifications:**
1. Freeze the bridge classification exactly as defined in the architecture docs: core owns the generic bridge runtime contract only — manifest discovery, registry, policy enforcement, plugin base/instantiation, hook/runtime activation, and server wiring needed to load installed extension bridges or local operator bridges.
2. Move any council-specific shipped bridge manifests, plugin implementations, hook adapters, scaffold/export assets, and council/federation-specific bridge docs/examples into the optional `scribe-council` package; they do not remain in the public core wheel.
3. Keep repo-local `.council/` bridge manifests/adapters as local-only overlays; they are not promoted into public release truth by this package.
4. A shipped bridge surface must include a real plugin/runtime activation path in the same owning package; manifest-only inactive registration is not a supported release contract.
5. Close the current partial seams between plugin instantiation, API injection, policy ownership, and hook registration/execution.
6. Document the final package boundary in dedicated docs/examples so downstream consumers know whether to install core only, core + extension, or treat a bridge as local-only.

**Patterns to Follow:**
- One package boundary, one activation story, one policy surface.
- Prefer finishing a bounded shipped bridge surface or explicitly demoting it; do not ship an ambiguous half-wired middle state.
- Do not add a temporary bridge-compatibility shim; land the final ownership boundary directly in this package.

**Verification:**
- [x] The release docs can name which bridge surfaces are core, extension, or local-only without ambiguity.
- [x] Bridge activation no longer depends on manifest-only placeholders or TODO-owned policy/API seams in the shipped path.
- [x] Hook/runtime execution follows the same ownership boundary as manifest and plugin loading.

**Evidence (2026-04-05):** Added `src/scribe_mcp/bridges/runtime.py` so core bridge registration now binds a real runtime plugin, `BridgeToScribeAPI`, and `BridgePolicyPlugin` together before hook registration; `src/scribe_mcp/bridges/registry.py` now rejects manifest-only registration, records the runtime owner package, and registers/unregisters against the configured hook manager; `src/scribe_mcp/bridges/api.py` now enforces async ownership-aware read/append checks; `src/scribe_mcp/server.py` no longer keeps manifest-only inactive placeholders in the startup path; and `docs/RELEASE_SURFACE.md` plus `docs/BRIDGE_DEVELOPMENT.md` now publish the core-vs-extension-vs-local bridge boundary plus the `plugin_factory` activation rule. Verification passed via `python -m compileall -q src/scribe_mcp/bridges/manifest.py src/scribe_mcp/bridges/plugin.py src/scribe_mcp/bridges/policy.py src/scribe_mcp/bridges/api.py src/scribe_mcp/bridges/runtime.py src/scribe_mcp/bridges/registry.py src/scribe_mcp/bridges/examples/hello_world_plugin.py src/scribe_mcp/server.py tests/test_bridge_registry.py tests/test_bridge_system.py`, `pytest -q tests/test_bridge_registry.py tests/test_bridge_system.py` (`85 passed in 25.95s`), and `rg -n 'optional extension|local-only overlays|Manifest-only inactive placeholders|plugin_factory|runtime plugin' docs/RELEASE_SURFACE.md docs/BRIDGE_DEVELOPMENT.md src/scribe_mcp/server.py src/scribe_mcp/bridges/runtime.py src/scribe_mcp/bridges/registry.py`.

**Out of Scope:** `council_mcp` consumer updates and README/file-map edits.

### Task Package: 6.3-B — Update `council_mcp` runtime clients to consume the Scribe auth + extension contract
**Owner:** `council_mcp` runtime/auth lane.

**Scope:** Make `council_mcp` capable of connecting to authenticated Scribe transport and the final bridge/extension package boundary without breaking stdio fallback.

**Files to Modify:**
- `council_mcp/src/council_mcp/web/mcp_client.py`
- `council_mcp/src/council_mcp/server.py`
- `council_mcp/src/council_mcp/config/__init__.py`
- `council_mcp/src/council_mcp/config/env_schema.py`
- `council_mcp/src/council_mcp/cli/connect_cmd.py`

**Files to Create:**
- a shared Scribe transport/auth helper in `council_mcp` if needed so web and daemon bootstrap do not drift again.

**Dependencies:** requires `6.2-A` and `6.3-A` complete.

**Specifications:**
1. Add config/env loading for the Scribe remote auth token using the final Scribe public names.
2. Extend the SSE client/bootstrap path so it can attach the token on authenticated Scribe connections.
3. Preserve stdio fallback when SSE is unset or intentionally unavailable.
4. Respect the final bridge/extension install boundary so downstream bootstrap knows whether it needs `scribe-mcp` alone or `scribe-mcp` + `scribe-council`.

**Verification:**
- [x] Auth-configured SSE connects successfully from both runtime call sites.
- [x] Missing/invalid token fails clearly instead of silently downgrading to a confusing transport error.
- [x] Stdio fallback remains intact when SSE is not selected.

**Evidence (2026-04-05):** Added `src/council_mcp/config/scribe_transport.py` so `src/council_mcp/web/mcp_client.py`, `src/council_mcp/server.py`, and `src/council_mcp/cli/connect_cmd.py` all resolve the same authenticated Scribe transport contract: canonical `SCRIBE_REMOTE_AUTH_TOKEN` with fallback aliases to `SCRIBE_TRANSPORT_AUTH_TOKEN` / `SCRIBE_AUTH_TOKEN`, shared SSE endpoint selection, and the final install-boundary guidance that core transport comes from `scribe-mcp` while `scribe-council` remains optional extension-only surface area. `MCPSSEClient` now sends `Authorization: Bearer <token>` plus compatibility `x-scribe-auth` headers, both runtime call sites now raise explicit auth/configuration errors instead of silently dropping to stdio when SSE is selected, and stdio fallback remains the path when no SSE endpoint is selected. Verification passed via `python -m compileall -q src/council_mcp/web/mcp_client.py src/council_mcp/server.py src/council_mcp/config/__init__.py src/council_mcp/config/env_schema.py src/council_mcp/config/scribe_transport.py src/council_mcp/cli/connect_cmd.py` plus `PYTHONPATH=src python - <<'PY' ...` with explicit assertions for `verified: pool_sse_success`, `verified: pool_missing_token_failure`, `verified: pool_auth_rejection_failure`, `verified: pool_stdio_fallback`, and `verified: server_sse_success`.

**Out of Scope:** export/config docs and direct-import cleanup.

### Task Package: 6.3-C — Replace Scribe-internal imports and repo-coupled export assumptions in `council_mcp`
**Owner:** `council_mcp` integration/export lane.

**Scope:** Remove direct imports/path injection against `scribe_mcp` internals and stop publishing sibling-repo launch assumptions as the public export truth.

**Files to Modify:**
- `council_mcp/src/council_mcp/services/mcp_servers.py`
- `council_mcp/src/council_mcp/web/routes/hooks.py`
- `council_mcp/src/council_mcp/bridges/scribe_storage_api.py`
- `council_mcp/.mcp.json`
- `council_mcp/opencode.json`
- `council_mcp/docs/MCP_SERVERS.md`
- `council_mcp/tests/test_codex_export.py`
- `council_mcp/tests/test_mcp_codex_export.py`

**Dependencies:** requires `6.1-A` and `6.3-A` complete; should coordinate with `6.3-B` for final auth/env names.

**Specifications:**
1. Replace sibling-repo `cd .../scribe_mcp && exec python -m server` assumptions with the final public install/runtime contract or clearly marked local-development override behavior.
2. Remove `sys.path` injection and direct imports such as `scribe_mcp.storage.sqlite` and `scribe_mcp.utils.tool_logger`.
3. Make exported downstream configs describe installed-package/public-contract truth, not repo-root operator overlays or transitional runtime directories.
4. Keep any local-development override path clearly marked as non-public operator guidance.

**Verification:**
- [x] No direct `scribe_mcp.storage.*` / `scribe_mcp.utils.*` imports remain in the bounded files.
- [x] Export tests pass against the new public/core + extension contract.
- [x] Repo-root `.mcp.json`/`opencode.json` no longer define the public Scribe contract.

**Evidence (2026-04-05):** `src/council_mcp/services/mcp_servers.py` now publishes the installed-package Scribe stdio contract (`scribe-server` plus `SCRIBE_ROOT` and default sqlite `.scribe/state/scribe.db`) for both local system metadata and downstream exports instead of sibling-checkout `cd .../scribe_mcp && python -m server`; `src/council_mcp/web/routes/hooks.py` now writes its local hook audit overlay directly without `sys.path` injection or `scribe_mcp.utils.tool_logger`; and `src/council_mcp/bridges/scribe_storage_api.py` now routes the deprecated compatibility shim through `ScribeMCPClient` instead of `scribe_mcp.storage.sqlite`. Repo-root `.mcp.json` and `opencode.json` now use local overlay `scribe-server` entries rooted at the `council_mcp` workspace, while `docs/MCP_SERVERS.md` explicitly demotes repo-root overlays to operator-local guidance and names the installed `scribe-server` contract as the public export truth. Verification passed via `python -m compileall -q src/council_mcp/services/mcp_servers.py src/council_mcp/web/routes/hooks.py src/council_mcp/bridges/scribe_storage_api.py tests/test_codex_export.py tests/test_mcp_codex_export.py`, `pytest -q tests/test_codex_export.py tests/test_mcp_codex_export.py::TestGatherMcpServers::test_downstream_includes_knowledge_managed_server tests/test_mcp_codex_export.py::test_audit_export_drift_uses_shared_post_policy_surface tests/test_mcp_codex_export.py::TestTomlRoundTrip::test_downstream_scribe_config_uses_public_install_contract` (`10 passed in 0.93s`), `python -m json.tool .mcp.json`, `python -m json.tool opencode.json`, and `rg -n "scribe_mcp\.(storage|utils)|sys\.path|cd .*scribe_mcp && exec python -m server" src/council_mcp/services/mcp_servers.py src/council_mcp/web/routes/hooks.py src/council_mcp/bridges/scribe_storage_api.py .mcp.json opencode.json docs/MCP_SERVERS.md tests/test_codex_export.py tests/test_mcp_codex_export.py` (`no matches`).

**Out of Scope:** Docker/deploy secret rollout.

### Task Package: 6.3-D — Update `council_mcp` deploy/scaffold/docs/tests in lockstep
**Owner:** `council_mcp` deploy/config lane.

**Scope:** Roll the new package/auth/bridge contract through scaffolds, Docker/dev-serve deployment, dedicated docs, and the bounded regression suite so `council_mcp` can ship alongside the Scribe release without using README tree snapshots as interim truth.

**Files to Modify:**
- `council_mcp/src/council_mcp/templates/defaults/council.yaml`
- `council_mcp/src/council_mcp/templates/scaffold/.env.example.j2`
- `council_mcp/src/council_mcp/cli/init_cmd.py`
- `council_mcp/deploy/docker-compose.yaml`
- `council_mcp/deploy/docker-compose.dev.yaml`
- `council_mcp/deploy/docker-entrypoint.sh`
- `council_mcp/deploy/scripts/deploy.sh`
- `council_mcp/deploy/scripts/setup-hetzner.sh`
- `council_mcp/docs/*` dedicated deployment/runtime docs
- `council_mcp/tests/test_multi_repo_scribe.py`
- `council_mcp/tests/bridges/test_scribe_mcp_client.py`
- `council_mcp/tests/test_connect_serve.py`
- `council_mcp/tests/test_connect_serve_config.py`

**Dependencies:** requires `6.3-B` and `6.3-C` complete.

**Specifications:**
1. Thread the final Scribe auth env/secret names through scaffolds, deploy manifests, and dev-serve/bootstrap flows.
2. Update dedicated docs to distinguish managed private-mesh/Tailscale deployment from casual public exposure.
3. Keep `0.0.0.0` allowed only in the private-mesh/operator-managed posture guidance.
4. Update the bounded tests named in the upstream research report in the same PR wave.
5. Defer any README tree/file-map refresh to `6.4-B`.

**Verification:**
- [x] Generated config/schema/scaffolds expose the correct Scribe endpoint + auth variables.
- [x] Docker/dev-serve/deploy surfaces wire the token and extension boundary consistently.
- [x] The bounded `council_mcp` regression lane passes on the synchronized release branch.

**Evidence (2026-04-05):** `council_mcp` scaffolds and deploy surfaces now thread the final public Scribe contract end to end: `src/council_mcp/templates/defaults/council.yaml` defaults transport/web hosts to loopback and adds `council.scribe.remote_auth_token`; `src/council_mcp/templates/scaffold/.env.example.j2` and `src/council_mcp/cli/init_cmd.py` now advertise canonical `SCRIBE_REMOTE_AUTH_TOKEN`, installed-package `scribe-server`, and `scribe-council` as optional-only; `deploy/docker-compose.yaml`, `deploy/docker-compose.dev.yaml`, `deploy/docker-entrypoint.sh`, `deploy/scripts/deploy.sh`, and `deploy/scripts/setup-hetzner.sh` now distinguish remote-client auth (`SCRIBE_REMOTE_AUTH_TOKEN`) from transport/server auth (`SCRIBE_TRANSPORT_AUTH_TOKEN`) while keeping 0.0.0.0 guidance confined to managed private-mesh posture; and `docs/MCP_SERVERS.md` plus `docs/CLI_REFERENCE.md` now document loopback-local default vs authenticated private-mesh exposure without promoting repo-root overlays as public truth. The bounded verification lane passed with `python -m compileall -q /home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/cli/init_cmd.py /home/austin/projects/MCP_SPINE/council_mcp/tests/test_multi_repo_scribe.py /home/austin/projects/MCP_SPINE/council_mcp/tests/bridges/test_scribe_mcp_client.py /home/austin/projects/MCP_SPINE/council_mcp/tests/test_connect_serve.py /home/austin/projects/MCP_SPINE/council_mcp/tests/test_connect_serve_config.py` and `pytest -q tests/test_multi_repo_scribe.py tests/bridges/test_scribe_mcp_client.py tests/test_connect_serve.py tests/test_connect_serve_config.py` (`147 passed in 24.93s`); the synchronized test updates in `tests/test_multi_repo_scribe.py`, `tests/test_connect_serve.py`, and `tests/test_connect_serve_config.py` now freeze the canonical Scribe identity and authenticated dev-serve expectations.

**Out of Scope:** broader council runtime redesign unrelated to Scribe.

### Task Package: 6.4-A — Freeze release truth and publish the compatibility / `v3` decision matrix
**Owner:** cross-repo release lane.

**Scope:** After the split/auth/runtime-hygiene/bridge/compatibility work lands, freeze built-artifact truth across both repos and publish the compatibility matrix that determines whether the next public release remains a compatibility wave or becomes the explicit `v3` boundary.

**Files to Modify:**
- dedicated release docs/notes in both repos that describe install/export/runtime compatibility
- built-artifact inspection/signoff material

**Files to Create:**
- `docs/COMPATIBILITY_MATRIX.md` in `scribe_mcp` (and linked dedicated docs from `council_mcp` if needed)
- one synchronized signoff bundle/checklist artifact path for the release manager

**Dependencies:** requires `6.1-A` through `6.3-D` complete.

**Specifications:**
1. Record the supported combinations of `scribe-mcp`, `scribe-council`, and `council_mcp`.
2. State whether the release remains a compatibility release or whether the remaining shim/removal surface now justifies `v3`.
3. Verify that built wheels/sdists, not repo-root overlays, runtime JSON dirs, `.council/`, or stale `build/` / `dist/` trees, define the release truth.
4. Keep README/file-map work deferred until the compatibility matrix is final.

**Verification:**
- [ ] Compatibility matrix published in dedicated docs.
- [ ] One signoff bundle inspects built artifacts and docs from both repos.
- [ ] The `v3` decision is explicit, evidence-backed, and no longer blocked on packaging/doc ambiguity.

**Out of Scope:** final README/file-map publication.

### Task Package: 6.4-B — Final README + release file-map pass (last package)
**Owner:** cross-repo documentation lane.

**Scope:** Publish the final top-level README/doc-tree updates only after the package boundary, runtime dirs, bridge surface, and compatibility matrix are frozen.

**Files to Modify:**
- `README.md`
- `deploy/README.md`
- any repo-top navigation doc that links the final release-surface docs
- corresponding top-level README/navigation files in `council_mcp` if they must reference the same frozen contract

**Files to Create:**
- `docs/RELEASE_FILE_MAP.md` — final authoritative file-map artifact linked from README.

**Dependencies:** requires `6.4-A` complete.

**Specifications:**
1. Update README only once the actual directory/package layout is frozen; do not publish interim tree snapshots before this package.
2. Make `docs/RELEASE_FILE_MAP.md` the detailed tree/file-map artifact and keep README itself concise, linking to that dedicated doc.
3. Ensure the file map reflects the final runtime policy: `.scribe/cli/`, `.scribe/state/`, and `.scribe/logs/` are runtime-only/local, while tracked package/docs/examples are repo truth.
4. Link the compatibility matrix, release-surface doc, remote-client doc, and final file map from the final README pass.

**Verification:**
- [ ] README/file-map updates happen only after structural packages are complete.
- [ ] `docs/RELEASE_FILE_MAP.md` matches the final shipped/repo/runtime boundary.
- [ ] README no longer acts as a stale interim tree during the restructure.
**Out of Scope:** further structural/package/runtime changes after the file map is published.
| Milestone | Status | Evidence |
|---|---|---|
| Historical 2.2 ship decision preserved | Complete | Packages `5.6-A` through `5.6-E` remain the governing record for the 2026-04-04 `SHIP` outcome from `/tmp/scribe_release_audit_20260403_dist/final_56d_20260404T231620Z`. |
| Next-wave architecture published | Complete | `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md` now freeze the same-repo `packages/scribe_council/` extension layout, the core-vs-extension-vs-local bridge classification, the one-wave `src/scribe_mcp/council_templates/__init__.py` shim policy, remote/client as optional-not-default, README/file-map-last sequencing, and the explicit Phase 6 shared-file ownership/merge-order map. |
| `6.1` public/core vs extension split + runtime path policy | Complete | `6.1-A`, `6.1-B`, and `6.1-C` are complete: fresh clean wheels show `scribe-mcp` no longer publishes `council.templates` and now carries only the deprecated `src/scribe_mcp/council_templates/__init__.py` shim under `council_templates/`, while `scribe-council` owns the provider entry point and template payload; `6.1-B` published `docs/RELEASE_SURFACE.md` plus tracked `docs/examples/mcp.json.example` and `docs/examples/opencode.json.example`, demoted repo-root overlay files in `.gitignore`, and pruned overlay/build/runtime trees from `MANIFEST.in`; and `6.1-C` centralized the `.scribe/{cli,state,logs}` runtime namespace in `src/scribe_mcp/config/paths.py`, moved the last repo-root `state/*.json` writers under `.scribe/state/`, aligned object-store deny prefixes with that runtime policy, and verified the boundary with the focused runtime-path test shard. |
| `6.2` optional public remote/client auth completion | Complete | `6.2-A` and `6.2-B` are complete: the public settings contract now resolves canonical `SCRIBE_REMOTE_AUTH_TOKEN` plus single-env alias fallbacks, `create_storage_backend()` passes the token into `RemoteStorageBackend`, remote backend/batch calls emit `Authorization` + compatibility `x-scribe-auth` headers and surface explicit `401`/`403` auth failures, and `detect_operating_mode()` now distinguishes remote auth rejection from true unavailability so `SCRIBE_REMOTE_FALLBACK` only applies to unavailable remotes. The follow-up freeze package added focused regressions in `tests/test_runtime_mode_resolution.py` and `tests/test_remote_backend.py` for token loading, auth header emission, and explicit unauthorized guidance, and published `docs/REMOTE_CLIENT.md` so local/standard remains the default public posture, remote/client is explicitly optional/authenticated, loopback-local and managed private-mesh/Tailscale are the only supported release postures, casual public exposure is unsupported, and any `0.0.0.0` guidance is limited to managed/private-mesh deployments with auth. Verification passed via `python -m compileall -q src/scribe_mcp/config/settings.py src/scribe_mcp/storage/__init__.py src/scribe_mcp/storage/remote.py src/scribe_mcp/config/mode_detection.py`, `pytest -q tests/test_remote_backend.py tests/test_runtime_mode_resolution.py` (`54 passed in 0.26s`), and targeted `rg -n` proof over `docs/REMOTE_CLIENT.md`. |
| `6.3` bridge/runtime unification + lockstep `council_mcp` compatibility/deploy/export update | Complete | `6.3-A` through `6.3-D` are complete: core bridge registration now requires a real runtime path, downstream runtime clients now consume the final authenticated Scribe transport contract, `council_mcp` no longer publishes sibling-checkout `scribe_mcp` assumptions or direct `scribe_mcp` internal imports as export truth, and deploy/scaffold/docs/tests now carry the same installed-package `scribe-server` plus authenticated private-mesh/Tailscale contract end to end. Verification includes the bounded `council_mcp` regression lane `pytest -q tests/test_multi_repo_scribe.py tests/bridges/test_scribe_mcp_client.py tests/test_connect_serve.py tests/test_connect_serve_config.py` (`147 passed in 24.95s`). |
| `6.4` release-truth freeze + final README/file-map publication | Pending | Owned by Packages `6.4-A` and `6.4-B`. |
<!-- ID: retro_notes -->
### Explicit defer list (not part of the 2.2 ship history or the next synchronized release wave)
- Repo-scoped lease/shared-host coordinator patterned after `knowledge_mcp`
- Full remote tool execution / thin-client runtime redesign
- Full decomposition of `server.py`, `doc_management/manager.py`, `read_file.py`, `append_entry.py`, `rotate_log.py`, and Postgres storage
- Large-scale test taxonomy cleanup beyond the release-surface issues listed above
If any implementation package starts requiring those items, stop and escalate rather than silently expanding the synchronized release scope.
