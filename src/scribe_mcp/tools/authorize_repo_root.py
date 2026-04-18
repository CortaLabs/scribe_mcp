"""Tool for issuing short-lived repo-root authorization grants."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scribe_mcp.server import app
from scribe_mcp.tool_contracts import stateful_local_tool
from scribe_mcp import server as server_module
from scribe_mcp.shared.tool_runtime import (
    issue_repo_root_grant,
    resolve_context_authoritative_session_key,
)


@app.tool(**stateful_local_tool(title="Authorize Repo Root", tags=("projects", "context", "write")))
async def authorize_repo_root(
    root: str,
    reason: str,
    ttl_minutes: int = 30,
) -> Dict[str, Any]:
    """Issue a session-bound grant authorizing an external repository root bind."""
    authoritative_session_key = resolve_context_authoritative_session_key(
        server_module.get_execution_context()
    )
    if not authoritative_session_key:
        return {
            "ok": False,
            "error": "authority_error",
            "reason_code": "missing_authoritative_session_key",
            "message": "No authoritative runtime session is active for grant issuance.",
        }

    repo_root = str(Path(root).expanduser().resolve())
    try:
        grant = await issue_repo_root_grant(
            storage_backend=server_module.storage_backend,
            repo_root=repo_root,
            reason=reason,
            ttl_minutes=ttl_minutes,
            authoritative_session_key=authoritative_session_key,
        )
    except ValueError:
        return {
            "ok": False,
            "error": "authority_error",
            "reason_code": "repo_scope_grant_storage_unavailable",
            "message": "Repo-scope grant storage backend is unavailable for issuance.",
        }
    return {
        "ok": True,
        "grant_id": grant["grant_id"],
        "repo_root": grant["repo_root"],
        "repo_id": grant["repo_id"],
        "expires_at": grant["expires_at"],
        "next_step": "Call set_project(..., root=<repo_root>, grant_id=<grant_id>).",
    }
