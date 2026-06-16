# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>
## Runtime latency, telemetry, and binding reuse release
- `entry_id`: 20260616:runtime-latency-telemetry-binding-reuse-2-7-0
- `entry_status`: accepted
- `title`: Runtime latency, telemetry, and binding reuse release
- `summary`: Bumped the public release line to `2.7.0`. Scribe now records queryable tool runtimes with durations, correlation IDs, measurement scope, and repo root; `append_entry` returns phase timing; `set_project` has a strict same-agent/session/project/root no-write reuse path that skips redundant writes and mutation-time reminder refresh; successful timing logs stay out of warning output; local probes support JSON output, same-server root comparison, and background telemetry draining; diagnostics expose physical/logical reconciliation for fresh Postgres installs with existing file-backed Scribe artifacts.
- `evidence_refs`:
  - pyproject.toml
  - src/scribe_mcp/__main__.py
  - src/scribe_mcp/tools/set_project.py
  - src/scribe_mcp/tools/append_entry.py
  - src/scribe_mcp/state/agent_manager.py
  - src/scribe_mcp/scripts/scribe_probe.py
  - src/scribe_mcp/utils/formatters/dispatcher.py
  - src/scribe_mcp/physical_logical_reconciliation.py
  - docs/dev_plans/scribe_mcp/CHANGELOG.md
  - tests/test_set_project.py
  - tests/test_scribe_probe.py
  - tests/test_execution_context.py
  - tests/test_physical_logical_reconciliation.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 2.7.0
