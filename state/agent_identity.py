"""Agent identification and session management utilities."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from scribe_mcp.utils.time import utcnow


class AgentIdentity:
    """
    Manages agent identification and session state for multi-agent environments.

    Features:
    - Automatic agent ID generation from context
    - Persistent agent identity across sessions
    - Project resumption capability
    - Activity tracking and state updates
    """

    def __init__(self, state_manager):
        self.state_manager = state_manager

    async def get_or_create_agent_id(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Get existing agent ID or create a new one based on context.

        Args:
            context: Optional context information (MCP request, environment, etc.)

        Returns:
            Agent ID string
        """
        # Try to get agent ID from various sources
        agent_id = (
            self._get_agent_id_from_mcp_context(context) or
            self._get_agent_id_from_environment() or
            await self._get_agent_id_from_persistent_state() or
            self._create_new_agent_id()
        )

        # Store the agent ID for future use
        await self._store_agent_id(agent_id)

        return agent_id

    def _get_agent_id_from_mcp_context(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract agent ID from MCP request context."""
        if not context:
            return None

        # Try various MCP context fields
        mcp_context_keys = [
            "client_id", "session_id", "request_id", "user_id",
            "agent_id", "client_name", "tool_call_id"
        ]

        for key in mcp_context_keys:
            if key in context:
                return f"mcp-{context[key]}"

        # Try to extract from request metadata
        if "request" in context:
            request = context["request"]
            if isinstance(request, dict):
                if "method" in request:
                    method = request["method"]
                    if "params" in request:
                        params = request["params"]
                        if isinstance(params, dict) and "session_id" in params:
                            return f"mcp-session-{params['session_id']}"

        return None

    def _get_agent_id_from_environment(self) -> Optional[str]:
        """Extract agent ID from environment variables."""
        env_keys = [
            "MCP_AGENT_ID", "SCRIBE_AGENT_ID", "CLIENT_ID",
            "SESSION_ID", "USER_AGENT", "HOSTNAME", "USERNAME"
        ]

        for key in env_keys:
            value = os.getenv(key)
            if value:
                # Sanitize and normalize
                safe_value = value.replace(" ", "-").lower()[:50]
                return f"env-{safe_value}"

        return None

    async def _get_agent_id_from_persistent_state(self) -> Optional[str]:
        """Get agent ID from persistent state storage."""
        try:
            state = await self.state_manager.load()
            agent_state = getattr(state, "agent_state", {})
            if "last_agent_id" in agent_state:
                return agent_state["last_agent_id"]
        except Exception:
            pass
        return None

    def _create_new_agent_id(self) -> str:
        """Create a new unique agent ID."""
        # Generate unique ID with timestamp and random component
        timestamp = utcnow().strftime("%Y%m%d-%H%M%S")
        random_part = str(uuid.uuid4())[:8]
        return f"agent-{timestamp}-{random_part}"

    async def _store_agent_id(self, agent_id: str) -> None:
        """Store agent ID in persistent state for future use."""
        try:
            state = await self.state_manager.load()
            if not hasattr(state, "agent_state"):
                state.agent_state = {}

            state.agent_state.update({
                "last_agent_id": agent_id,
                "last_seen": utcnow().isoformat(),
                "agent_metadata": {
                    "created_at": utcnow().isoformat(),
                    "id_type": "auto-generated"
                }
            })

            await self.state_manager.persist(state)
        except Exception:
            # Don't fail if we can't store the agent ID
            pass

    async def resume_agent_session(
        self,
        agent_id: str,
        agent_context_manager,
        stable_session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Resume an agent's previous session and project context.

        Args:
            agent_id: Agent identifier
            agent_context_manager: AgentContextManager instance
            stable_session_id: Optional stable session ID from ExecutionContext
            metadata: Optional session metadata

        Returns:
            Session ID if resumption successful, None otherwise
        """
        try:
            # Check if agent has an existing project
            agent_project = await agent_context_manager.get_current_project(agent_id)
            if agent_project and agent_project.get("project_name"):
                # Create new session for the agent with stable session if provided
                session_metadata = {
                    "resumed": True,
                    "resumed_at": utcnow().isoformat(),
                    "previous_project": agent_project["project_name"],
                }
                if metadata:
                    session_metadata.update(metadata)
                session_id = await agent_context_manager.start_session(
                    agent_id,
                    session_id=stable_session_id,  # Pass through stable session
                    metadata=session_metadata
                )

                print(f"🔄 Resumed agent '{agent_id}' session")
                print(f"   📋 Previous project: {agent_project['project_name']}")
                print(f"   🆔 Session ID: {session_id}")

                return session_id
            else:
                # No previous project, create fresh session
                session_metadata = {
                    "fresh_session": True,
                    "created_at": utcnow().isoformat(),
                }
                if metadata:
                    session_metadata.update(metadata)
                session_id = await agent_context_manager.start_session(
                    agent_id,
                    session_id=stable_session_id,  # Pass through stable session
                    metadata=session_metadata
                )

                print(f"🆕 Created fresh session for agent '{agent_id}'")
                print(f"   🆔 Session ID: {session_id}")

                return session_id

        except Exception as e:
            print(f"⚠️  Failed to resume session for agent '{agent_id}': {e}")
            return None

    async def update_agent_activity(self, agent_id: str, activity_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Update agent activity tracking.

        Args:
            agent_id: Agent identifier
            activity_type: Type of activity (tool_call, project_switch, etc.)
            metadata: Additional activity metadata
        """
        try:
            state = await self.state_manager.load()
            if not hasattr(state, "agent_state"):
                state.agent_state = {}

            activity = {
                "agent_id": agent_id,
                "activity_type": activity_type,
                "timestamp": utcnow().isoformat(),
                "metadata": metadata or {}
            }

            # Add to activity log
            if "activity_log" not in state.agent_state:
                state.agent_state["activity_log"] = []

            state.agent_state["activity_log"].append(activity)

            # Keep only recent activities (last 100)
            if len(state.agent_state["activity_log"]) > 100:
                state.agent_state["activity_log"] = state.agent_state["activity_log"][-100:]

            # Update last seen info
            state.agent_state.update({
                "last_agent_id": agent_id,
                "last_seen": utcnow().isoformat(),
                "last_activity": activity_type
            })

            await self.state_manager.persist(state)

        except Exception:
            # Don't fail if we can't update activity
            pass


# Global instance for server integration
_agent_identity: Optional[AgentIdentity] = None


def get_agent_identity() -> AgentIdentity:
    """Get the global agent identity instance."""
    global _agent_identity
    if _agent_identity is None:
        raise RuntimeError("AgentIdentity not initialized. Call init_agent_identity first.")
    return _agent_identity


def init_agent_identity(state_manager) -> AgentIdentity:
    """Initialize the global agent identity instance."""
    global _agent_identity
    _agent_identity = AgentIdentity(state_manager)
    return _agent_identity
