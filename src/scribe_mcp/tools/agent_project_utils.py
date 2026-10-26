"""Utilities for agent-scoped project operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp import server as server_module
from scribe_mcp.shared.session_scope import ResolvedScope


async def get_agent_project_data(agent_id: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Get the current verified session project and advisory recent labels.

    Args:
        agent_id: Agent identifier

    Returns:
        Tuple of (project_data, recent_projects)
    """
    try:
        project = await server_module.state_manager._get_verified_project()
        try:
            state = await server_module.state_manager.load()
            recent = list(state.recent_projects)
        except Exception:
            recent = []
        if not project:
            return None, recent
        try:
            agent_manager = server_module.get_agent_context_manager()
            selection = await agent_manager.get_current_project(agent_id) if agent_manager else None
        except Exception:
            selection = None
        if isinstance(selection, dict) and selection.get("project_name") == project["name"]:
            # The label row contributes CAS metadata only, never its stored session.
            project["version"] = selection.get("version", 1)
            project["updated_by"] = selection.get("updated_by", agent_id)
        return project, [project["name"], *[name for name in recent if name != project["name"]]]
    except Exception:
        return None, []


async def ensure_agent_session(
    agent_id: str,
    stable_session_id: Optional[str] = None
) -> Optional[str]:
    """
    Ensure agent has an active session, creating one if needed.

    Args:
        agent_id: Agent identifier
        stable_session_id: Optional stable session ID from ExecutionContext

    Returns:
        Session ID if successful, None otherwise
    """
    agent_manager = server_module.get_agent_context_manager()
    agent_identity = server_module.get_agent_identity()

    if not agent_manager or not agent_identity:
        return None

    try:
        context = None
        if hasattr(server_module, "get_execution_context"):
            try:
                context = server_module.get_execution_context()
            except Exception:
                context = None

        session_metadata: Dict[str, Any] = {}
        if context and getattr(context, "agent_identity", None):
            agent_identity_payload = context.agent_identity
            if agent_identity_payload.display_name:
                session_metadata["agent_display_name"] = agent_identity_payload.display_name
            session_metadata["agent_instance_id"] = agent_identity_payload.instance_id

        # Try to resume existing session or create new one with stable session
        session_id = await agent_identity.resume_agent_session(
            agent_id,
            agent_manager,
            stable_session_id=stable_session_id,  # Pass through stable session
            metadata=session_metadata or None,
        )
        return session_id
    except Exception:
        return None


async def validate_agent_session(agent_id: str, session_id: str) -> bool:
    """
    Validate that a session is still active for an agent.

    Args:
        agent_id: Agent identifier
        session_id: Session ID to validate

    Returns:
        True if session is valid, False otherwise
    """
    agent_manager = server_module.get_agent_context_manager()

    if not agent_manager:
        return True  # No session management = always valid

    try:
        # Check if agent still has this session
        current_project = await agent_manager.get_current_project(agent_id)
        if current_project and current_project.get("session_id") == session_id:
            return True
        return False
    except Exception:
        return False


def resolve_authoritative_write_scope(
    *,
    context: Any,
    agent_session_id: Optional[str],
) -> Dict[str, Any]:
    """Resolve authoritative write-path session inputs from request-local scope."""
    resolved_scope: Optional[ResolvedScope] = getattr(context, "resolved_scope", None) if context else None

    # Trust-ordered: server-derived scope keys first (verified provenance),
    # then the request's own session_id, then raw stable_session_id LAST among
    # context fields — a bare context.stable_session_id without resolved_scope
    # is an unverified carried-over claim, and preferring it over the request's
    # session_id is how stale-session write capture happens (BUG-2026-06-11-0004;
    # contract pinned in 08d4d22, regressed by e320b3d).
    authoritative_candidates = (
        getattr(resolved_scope, "authoritative_session_key", None),
        getattr(context, "authoritative_session_key", None),
        getattr(resolved_scope, "stable_session_id", None),
        getattr(context, "session_id", None) if context else None,
        getattr(context, "stable_session_id", None) if context else None,
        getattr(resolved_scope, "agent_session_id", None),
        agent_session_id,
    )
    authoritative_session_id = None
    for candidate in authoritative_candidates:
        if isinstance(candidate, str) and candidate.strip():
            authoritative_session_id = candidate.strip()
            break

    return {
        "resolved_scope": resolved_scope,
        "authoritative_session_key": authoritative_session_id,
        "authoritative_session_id": authoritative_session_id,
        "scope_resolution_source": getattr(resolved_scope, "resolution_source", None)
        or ("execution_context" if context else "none"),
    }
