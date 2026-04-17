# Live MCP Impact Report

This note captures the direct impact of the `session_resolution_tool_audit_20260417` repair work using actual MCP tool calls against a fresh stdio server on April 17, 2026.

## Summary

The targeted regressions are fixed in live MCP use.

- `set_project` now fails closed for out-of-scope roots instead of trusting an external root.
- Project-bound tools now carry session-bound resolution correctly after `set_project`.
- `manage_docs(create, register_doc=True)` now uses the authoritative session binding and no longer emits the old unknown-session registry warning.
- `manage_docs` out-of-project writes now return a structured boundary payload instead of a generic wrapped error.
- `get_project`, `read_recent`, and `scribe_doctor` now surface truthful planning-registry unavailability instead of silently returning empty advisory fields.

The remaining issues observed during verification are runtime noise, not failures of the targeted fix:

- bridge bootstrap warns that `council_mcp` does not define a runtime plugin
- some Postgres reminder cooldown queries are slow
- pytest teardown still emits occasional asyncpg cleanup warnings

## What Changed

### `set_project` trust boundary

Before:
- `set_project(root="/tmp")` could succeed and seed project state outside trusted repo scope.

Now:
- the same call fails closed with an explicit trusted-scope error
- a valid in-repo call returns the authoritative session id used for persistence

Representative live payload:

```json
{
  "ok": false,
  "error": "Project root is outside trusted workspace scope. Set skip_validation=true only for explicit compatibility workflows."
}
```

Representative successful payload excerpt:

```json
{
  "ok": true,
  "project": {
    "name": "live_manage_docs_agentux_a8c1a4c6"
  },
  "scope_resolution": {
    "source": "runtime_context",
    "authoritative_session_id": "78b99e26-5759-42b0-98fe-1f26067b702b"
  }
}
```

Impact:
- prevents accidental project creation outside the trusted repo root
- makes the persisted session identity explicit instead of implied

### Session carryover into consumer tools

Before:
- `get_project`, `read_recent`, and `query_entries` could lose or under-report the active project resolution path after `set_project`.

Now:
- these tools report session-bound project resolution directly
- the live path shows that the active project is being consumed from `session_binding`

Representative `read_recent` payload excerpt:

```json
{
  "ok": true,
  "project": "live_manage_docs_agentux_a8c1a4c6",
  "project_resolution": {
    "resolution_source": "session_binding",
    "fallback_used": false,
    "fallback_chain": [],
    "resolution_summary": "Resolved via 'session_binding'"
  }
}
```

### `manage_docs` session binding during document registration

Before:
- `manage_docs(action="create", register_doc=True)` could create the doc but warn:

```text
Registry update failed: Cannot bind project for unknown session_id=...
```

Now:
- doc creation succeeds without that warning
- the created document is registered in project docs state

Representative live payload excerpt:

```json
{
  "ok": true,
  "path": "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/live_manage_docs_agentux_a8c1a4c6/custom_doc.md",
  "warning": null,
  "warnings": null,
  "next_step_guidance": "create scaffolds a governed document..."
}
```

Representative `get_project` doc registration proof:

```json
{
  "doc_keys": [
    "_hashes",
    "architecture",
    "checklist",
    "live_session_note",
    "phase_plan",
    "progress_log"
  ],
  "created_doc_registered": true
}
```

### Boundary contract for out-of-project doc writes

Before:
- out-of-project create attempts were rejected, but the operator-facing payload could be degraded into:

```text
Unexpected error: Target directory /tmp is outside project root ...
```

Now:
- the same failure is surfaced as a first-class boundary contract with guidance

Representative live payload:

```json
{
  "ok": false,
  "error": "Target directory /tmp is outside project root /home/austin/projects/MCP_SPINE/scribe_mcp",
  "suggestion": "Choose a target_dir inside the active project root, or omit target_dir to use the project docs_dir.",
  "boundary_guidance": {
    "rule": "target_dir must resolve inside the active project root",
    "project_root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
    "rejected_target_dir": "/tmp",
    "supported_alternative": {
      "example": "Use an in-project target_dir (or omit it to use project docs_dir).",
      "target_dir": ""
    }
  }
}
```

### Advisory surfacing for planning registry truth

Before:
- `get_project` and `read_recent` could return empty advisory fields even when runtime conditions made drift analysis unavailable.
- `scribe_doctor` did not clearly expose planning-registry context.

Now:
- live payloads explicitly say advisories are unavailable in this runtime
- the classification is surfaced as `environment_mismatch`
- `scribe_doctor` includes `runtime.planning_registry`

Representative `get_project` payload excerpt:

```json
{
  "meta": {
    "planning_advisories": {
      "available": false,
      "reason_code": "runtime_mode_non_standalone",
      "classification": "environment_mismatch",
      "mode": "server",
      "storage_backend": "postgres",
      "advisories": [
        {
          "code": "planning_registry_unavailable",
          "severity": "info",
          "classification": "environment_mismatch",
          "message": "Planning-doc drift advisories require standalone runtime mode."
        }
      ]
    },
    "docs_status": {
      "available": false,
      "classification": "environment_mismatch",
      "reason_code": "runtime_mode_non_standalone",
      "message": "Planning-doc drift advisories require standalone runtime mode.",
      "mode": "server",
      "storage_backend": "postgres"
    }
  }
}
```

Representative `scribe_doctor` payload excerpt:

```json
{
  "runtime": {
    "execution_context": {
      "mode": "project",
      "repo_root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
      "session_id": "78b99e26-5759-42b0-98fe-1f26067b702b",
      "stable_session_id": "95f80b3f-1ade-4981-9e69-314b0c19b719"
    },
    "planning_registry": {
      "available": false,
      "classification": "environment_mismatch",
      "reason_code": "runtime_mode_non_standalone",
      "message": "Planning-doc drift advisories require standalone runtime mode.",
      "mode": "server",
      "storage_backend": "postgres"
    }
  }
}
```

## Verification

### Live MCP gauntlet

Fresh stdio server runs verified:

- invalid-root `set_project` rejection
- valid `set_project` authoritative session binding
- `manage_docs` create with registration
- `manage_docs` out-of-project boundary rejection
- `get_project` advisory surfacing
- `read_recent` project-resolution and advisory surfacing
- `scribe_doctor` planning-registry surfacing
- `read_file` success on a freshly created managed doc

### Repo-local regression suite

Final targeted suite result:

```text
79 passed in 76.13s
```

Covered lanes:

- `tests/test_set_project_runtime_scope_contract.py`
- `tests/test_set_project_integration.py`
- `tests/test_execution_context.py`
- `tests/test_consumer_resolution_contract.py`
- `tests/test_query_entries_explicit_project_resolution.py`
- `tests/test_get_project_integration.py`
- `tests/test_manage_docs_session_binding.py`
- `tests/test_manage_docs_create_doc.py`
- `tests/test_manage_docs_boundary_contract.py`
- `tests/test_session_resolution_advisories.py`
- `tests/test_planning_truth_advisories.py`

## Bottom Line

The session carryover, managed-doc registration, boundary contract, and advisory-truth problems that motivated this audit are fixed in actual MCP tool use.

The biggest improvement is that the tools now tell the truth about:

- which session is authoritative
- where project resolution came from
- whether a write is outside scope
- whether planning advisory truth is available in the current runtime
