---
id: integrate_system_scribe_latency_20260616t050042z-measurement-table-scribe-latency-20260616
title: Measurement Table
doc_type: custom
doc_name: MEASUREMENT_TABLE_SCRIBE_LATENCY_20260616
category: engineering
status: complete
version: '0.1'
last_updated: 2026-06-16 07:54:12 UTC
maintained_by: Scribe
created_by: Scribe
owners:
- Seshat
related_docs: []
tags:
- latency
- measurement
- p7-deferred
summary: Final measurement table and P7 deferral proof for the Scribe latency optimization
  workstream.
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-06-16 07:26:35 UTC
  created_via: create_doc
  last_edited_at: 2026-06-16 07:54:12 UTC
  last_edited_by: Scribe
  last_action: replace_section
---
<!-- ID: measurement_table -->
## Measurement Table

| Tool / Scenario | Host Wall Time | Scribe / Tool Timing | Hook Label | Repo Binding | Notes |
|---|---:|---:|---|---|---|
| `set_project` local verified runtime | `387.614 ms` | `385.992 ms` total | `hook_excluded` | `/home/austin/projects/MCP_SPINE/scribe_mcp` | Dominant phases: `targeted_refresh_after=200.661 ms`, `resolve_paths=59.289 ms`, `record_tool=45.868 ms`. |
| `append_entry` local verified runtime | `276.436 ms` | `88.776 ms` append timing | `hook_excluded` | `/home/austin/projects/MCP_SPINE/scribe_mcp` | Phase timing: file WAL append `30.059 ms`, DB project fetch `30.517 ms`, DB upsert `17.196 ms`, DB insert `7.343 ms`; response wall includes wrapper/state overhead. |
| `read_recent` local verified runtime | `174.198 ms` | `173.905 ms` generic tool-call duration | `hook_excluded` | `/home/austin/projects/MCP_SPINE/scribe_mcp` | Returned structured entries and persisted queryable `tool_calls` duration/correlation metadata. |
| `manage_docs quality_check CHECKLIST` | `321.917 ms` | host-wall measured | `hook_excluded` | `/home/austin/projects/MCP_SPINE/scribe_mcp` | Quality status `pass`, zero warnings, zero readiness blockers, correct Scribe project path. |
| Same-server `set_project`, Scribe root | `428.524 ms` | `427.864 ms` total | `hook_excluded` | `/home/austin/projects/MCP_SPINE/scribe_mcp` | Probe row 1; `config_mutation=false`. |
| Same-server `set_project`, Council root | `248.895 ms` | `248.318 ms` total | `hook_excluded` | `/home/austin/projects/MCP_SPINE/council_mcp` | Probe row 2; same server/process, varied only root. |

Attribution result: `classification=inside_scribe_phases`; host delta `-179.629 ms`, Scribe delta `-179.546 ms`, outside-Scribe delta `-0.083 ms`.

<!-- ID: p7_defer_decision -->
## P7 Defer Decision

P7 is explicitly deferred. The data does not show Council-root `set_project` being slower in the same-server probe, and the outside-Scribe delta is effectively zero. Current evidence points to Scribe-internal phase cost, especially `targeted_refresh_after` and generic telemetry recording on some calls, but not to a proven duplicate-write optimization opportunity that should ship in this lane.

A later P7 package should require fresh before/after phase timing and call-count tests before changing write behavior.

<!-- ID: telemetry_readback -->
## Telemetry Readback

Live `tool_calls` readback after the repair showed recent rows for `set_project`, `append_entry`, and `read_recent` with non-null correlation IDs, `measurement_scope=tool_only`, normalized `repo_root=/home/austin/projects/MCP_SPINE/scribe_mcp`, and positive `duration_ms` values including `428.147 ms`, `387.298 ms`, `276.077 ms`, and `173.905 ms`.

Live project identity readback showed two rows for `integrate-system-scribe-latency-20260616T050042Z`: one for `/home/austin/projects/MCP_SPINE/scribe_mcp` and one for `/home/austin/projects/MCP_SPINE/council_mcp`, with distinct repo IDs and project keys.

<!-- ID: final_repeat_probe -->
## Final Repeat Probe

A final repeat of the same-server root comparison after the docs-json/progress-log drift repair returned `ok=true`, `config_mutation=false`, and `classification=inside_scribe_phases`. The repeat measured Scribe root `414.846 ms` host / `414.321 ms` Scribe total and Council root `259.682 ms` host / `259.159 ms` Scribe total, with outside-Scribe delta `-0.002 ms`.

One immediately prior final probe produced a transient Scribe-root outlier of `1319.582 ms`, fully attributed to Scribe phase timing (`record_tool=967.629 ms`) rather than hooks (`outside_scribe_delta=-0.025 ms`). An isolated record-tool profile then measured backend setup `18.265 ms`, state load `25.297 ms`, and repeated `record_tool` calls around `2.2 ms`, so the outlier is recorded as transient backend/cold contention, not a stable Council hook cost.

<!-- ID: final_speed_improvement -->
## Final Speed Improvement

A final optimization package landed after the earlier P7 defer decision because the active goal requires real measured speed improvement, not only attribution. The patch caches managed-doc readiness quality state by file signatures in `src/scribe_mcp/readiness.py`, preserving invalidation on managed doc edits, current phase changes, configured log exclusions, `pyproject.toml` changes, and research-directory Markdown changes. This removes repeated expensive readiness scans from reminder/context generation across Scribe tools.

Before/after measurements were taken in the same local direct-runtime style used by the earlier final table, with hooks excluded. Baseline before this final patch measured warm structured `set_project` mean `293.310 ms`, `append_entry` `179.728 ms`, and `read_recent` mean `144.900 ms`. After the cache patch, warm structured `set_project` mean was `195.229 ms`, readable `set_project` warm mean was `243.243 ms`, `append_entry` was `132.714 ms`, and `read_recent` mean was `96.095 ms`.

| Tool / Scenario | Before | After | Improvement | Notes |
|---|---:|---:|---:|---|
| `set_project` structured warm mean | `293.310 ms` | `195.229 ms` | `98.081 ms` faster (`33.4%`) | Repeated same-process direct runtime; targeted reminder phase dropped from roughly `77-79 ms` to roughly `30-33 ms`. |
| `append_entry` structured | `179.728 ms` | `132.714 ms` | `47.014 ms` faster (`26.2%`) | Benefits from shared readiness/reminder cache during context preparation. |
| `read_recent` structured mean | `144.900 ms` | `96.095 ms` | `48.805 ms` faster (`33.7%`) | Benefits from shared readiness/reminder cache during context preparation. |
| `set_project` readable warm mean | not previously isolated | `243.243 ms` | measured current default path | Readable path still includes SITREP/inventory formatting; it is now below the earlier structured baseline. |

Probe surface repair also landed in `src/scribe_mcp/scripts/scribe_probe.py`: multi-tool probe results now serialize MCP `CallToolResult` objects safely and `--json-output` emits aggregate machine-readable results. The repaired probe completed `set_project`, `append_entry`, `read_recent`, and `manage_docs quality_check` with `ok=true`; `manage_docs` returned `quality_status=pass`.
