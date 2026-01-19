"""Utilities for agent-scoped project operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp import server as server_module
from scribe_mcp.tools.project_utils import (
    load_active_project,
    load_project_config,
)


async def get_agent_project_data(agent_id: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Get project data for an agent using AgentContextManager as primary source.

    Args:
        agent_id: Agent identifier

    Returns:
        Tuple of (project_data, recent_projects)
    """
    agent_manager = server_module.get_agent_context_manager()

    if not agent_manager:
        # Fallback to legacy behavior
        project, _, recent = await load_active_project(server_module.state_manager)
        return project, list(recent)

    try:
        # Get agent's current project from AgentContextManager
        agent_project = await agent_manager.get_current_project(agent_id)

        if agent_project and agent_project.get("project_name"):
            project_name = agent_project["project_name"]

            # Try to get project data from storage backend
            storage = server_module.storage_backend
            if storage:
                try:
                    # Get project from database
                    db_project = await storage.get_project(project_name)
                    if db_project:
                        # Convert database project to project data format
                        project_data = {
                            "name": db_project.get("name", project_name),
                            "root": db_project.get("repo_root", ""),
                            "progress_log": db_project.get("progress_log_path", ""),
                            "version": agent_project.get("version", 1),
                            "updated_by": agent_project.get("updated_by", agent_id),
                            "session_id": agent_project.get("session_id"),
                        }

                        # Get recent projects from agent's history
                        recent_projects = [project_name]

                        # Add other projects from recent_projects list
                        try:
                            state = await server_module.state_manager.load()
                            for proj_name in state.recent_projects:
                                if proj_name != project_name and proj_name not in recent_projects:
                                    recent_projects.append(proj_name)
                        except Exception:
                            pass

                        return project_data, recent_projects
                except Exception:
                    pass

            # Fallback: attempt to load from state or config instead of /tmp defaults
            fallback_project = await _project_from_state_or_config(project_name)
            if fallback_project:
                project_data = dict(fallback_project)
                project_data.setdefault("version", agent_project.get("version", 1))
                project_data.setdefault("updated_by", agent_project.get("updated_by", agent_id))
                project_data.setdefault("session_id", agent_project.get("session_id"))
                recent_projects = await _recent_projects_snapshot(project_name)
                return project_data, recent_projects

            # No trusted project info available
            return None, []

        else:
            # Agent has no project set
            return None, []

    except Exception:
        # Fallback to legacy behavior on any error
        project, _, recent = await load_active_project(server_module.state_manager)
        return project, list(recent)


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

async def _project_from_state_or_config(project_name: str) -> Optional[Dict[str, Any]]:
    """Load project definition from JSON state or config files."""
    try:
        state = await server_module.state_manager.load()
        state_project = state.projects.get(project_name)
        if state_project:
            return dict(state_project)
    except Exception:
        pass

    config_project = load_project_config(project_name)
    if config_project:
        return dict(config_project)
    return None


async def _recent_projects_snapshot(current_name: str) -> List[str]:
    """Return ordered list of recent projects with current name first."""
    snapshot = [current_name]
    try:
        state = await server_module.state_manager.load()
        for proj_name in state.recent_projects:
            if proj_name not in snapshot:
                snapshot.append(proj_name)
    except Exception:
        pass
    return snapshot
