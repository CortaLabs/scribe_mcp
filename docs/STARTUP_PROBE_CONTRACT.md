# Startup Probe Contract (Repo Boundary)

This document defines what `scribe_probe.py` owns for release bootstrap proofing and what remains external orchestration responsibility.

## Fresh-Environment Proof Lane

Use the probe-only lane:

```bash
python -m scribe_mcp.scripts.scribe_probe \
  --tools release_bootstrap_proof \
  --project <project_name> \
  --bootstrap-observations-json '{"persona_registered":true,"open_session_ok":true,"discovered_tools":["set_project"],"lazy_exposure":false}'
```

The release proof checks:
1. Persona/profile precondition input (`persona_registered`).
2. External `open_session` status input (`open_session_ok`).
3. Tool discovery contract input (`discovered_tools`, `lazy_exposure`, `discovery_error`).
4. Repo-owned project flow (`set_project` then scoped `query_entries`).
5. Lightweight runtime budget artifact (`runtime_budget` and `release_artifact`).

## Delegated-Agent Discovery Contract

- Discovery is expected when the delegated agent/runtime has loaded the tool catalog for the active surface.
- Lazy exposure means tool discovery can be incomplete at first; `set_project` may be absent initially and still be valid.
- Non-lazy discovery with missing `set_project` is treated as an external mismatch.

## Classification Rules

- `environment_orchestration_mismatch`:
  - persona/profile missing
  - `open_session` failure
  - discovery failure before repo tools run
  - non-lazy discovery missing `set_project`
- `repo_startup_defect`:
  - repo-owned `set_project` or scoped `query_entries` path throws or returns failure
- `repo_flow_verified`:
  - repo-owned project-bound flow succeeds (budget may pass or fail independently)

## Runtime-Weight Budget

`release_bootstrap_proof` records:
- elapsed milliseconds
- configured budget milliseconds
- within-budget boolean
- loaded probe tool count

This is a bounded startup-weight artifact only, not a broad performance program.
