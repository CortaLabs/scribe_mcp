#!/usr/bin/env python3
"""
Council MCP Bridge Example

This example demonstrates how to integrate Council MCP (a multi-agent
orchestration system) with Scribe MCP for comprehensive logging and
project management.

Features demonstrated:
- Bridge lifecycle (activate/deactivate)
- Health monitoring
- Entry enrichment via pre_append hook
- External notifications via post_append hook
- Project creation with ownership
- Custom tool registration

Usage:
    # From scribe_mcp directory:
    python examples/council_bridge.py

    # Or import for integration:
    from examples.council_bridge import CouncilBridgePlugin
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

# Import bridge components
from scribe_mcp.bridges import (
    BridgePlugin,
    BridgeManifest,
    BridgeRegistry,
    BridgeState,
    BridgeToScribeAPI,
    get_tool_registry,
    create_health_monitor,
)
from scribe_mcp.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


class CouncilBridgePlugin(BridgePlugin):
    """
    Council MCP Bridge Implementation.

    This bridge connects Council MCP's multi-agent orchestration
    to Scribe's documentation and logging infrastructure.

    Features:
    - Automatic session tracking
    - Agent activity logging
    - Council decision documentation
    - Health monitoring integration
    """

    def __init__(self, manifest: BridgeManifest):
        super().__init__(manifest)

        # Session tracking
        self._session_id: Optional[str] = None
        self._active_agents: Dict[str, Dict[str, Any]] = {}
        self._started_at: Optional[datetime] = None

        # Metrics
        self._entries_processed: int = 0
        self._decisions_logged: int = 0

        # Background task for periodic sync
        self._sync_task: Optional[asyncio.Task] = None

    # =========================================================================
    # REQUIRED: Lifecycle Methods
    # =========================================================================

    async def on_activate(self) -> None:
        """
        Initialize Council bridge connection.

        Called when bridge transitions to ACTIVE state.
        """
        logger.info(f"Activating Council bridge: {self.bridge_id}")

        # Generate session ID
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._started_at = datetime.now(timezone.utc)

        # Register custom tools
        await self._register_custom_tools()

        # Start background sync (optional)
        self._sync_task = asyncio.create_task(self._background_sync())

        logger.info(f"Council bridge activated (session: {self._session_id})")

    async def on_deactivate(self) -> None:
        """
        Clean up Council bridge connection.

        Called when bridge transitions to INACTIVE state.
        Must be idempotent (safe to call multiple times).
        """
        logger.info(f"Deactivating Council bridge: {self.bridge_id}")

        # Stop background task
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        # Unregister custom tools
        registry = get_tool_registry()
        registry.unregister_bridge_tools(self.bridge_id)

        # Clear session
        self._session_id = None
        self._active_agents.clear()

        logger.info("Council bridge deactivated")

    async def health_check(self) -> Dict[str, Any]:
        """
        Return Council bridge health status.

        Returns:
            Dict with at least {healthy: bool}
        """
        uptime = None
        if self._started_at:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        return {
            "healthy": self._session_id is not None,
            "message": "Council session active" if self._session_id else "No active session",
            "session_id": self._session_id,
            "active_agents": len(self._active_agents),
            "entries_processed": self._entries_processed,
            "decisions_logged": self._decisions_logged,
            "uptime_seconds": uptime,
        }

    # =========================================================================
    # OPTIONAL: Hook Implementations
    # =========================================================================

    async def pre_append(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich entries with Council metadata before logging.

        Args:
            entry_data: Entry about to be logged

        Returns:
            Modified entry data
        """
        self._entries_processed += 1

        # Add Council session metadata
        meta = entry_data.get("meta", {})
        meta["council_session"] = self._session_id
        meta["bridge_version"] = self.manifest.version

        # Track decision entries
        if entry_data.get("status") == "plan" or "decision" in entry_data.get("message", "").lower():
            self._decisions_logged += 1
            meta["is_decision"] = True

        # Track agent activity
        agent = entry_data.get("agent")
        if agent and agent not in ["Orchestrator", "Council"]:
            self._active_agents[agent] = {
                "last_activity": datetime.now(timezone.utc).isoformat(),
                "entry_count": self._active_agents.get(agent, {}).get("entry_count", 0) + 1
            }

        entry_data["meta"] = meta
        return entry_data

    async def post_append(self, entry_data: Dict[str, Any]) -> None:
        """
        React to logged entries.

        Fire-and-forget - exceptions are logged but don't affect append.
        """
        # Example: Log high-priority decisions
        if entry_data.get("meta", {}).get("is_decision"):
            logger.debug(f"Council decision logged: {entry_data.get('message', '')[:50]}")

        # Example: Could send webhooks, update external systems, etc.

    async def pre_project_create(
        self,
        project_name: str,
        project_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enrich project configuration before creation.
        """
        # Add Council-specific defaults
        project_config.setdefault("defaults", {})
        project_config["defaults"]["agent"] = "Council"

        # Add session tracking
        project_config.setdefault("meta", {})
        project_config["meta"]["created_by_session"] = self._session_id

        return project_config

    async def post_project_create(
        self,
        project_name: str,
        project_data: Dict[str, Any]
    ) -> None:
        """
        React to project creation.
        """
        logger.info(f"Council project created: {project_name}")

    # =========================================================================
    # CUSTOM: Bridge-Specific Methods
    # =========================================================================

    async def _register_custom_tools(self) -> None:
        """Register Council-specific custom tools."""
        registry = get_tool_registry()

        # Custom tool: Log a council decision
        async def log_decision(
            decision: str,
            agents: List[str],
            confidence: float = 0.8,
            rationale: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Log a council decision with structured metadata.

            Args:
                decision: The decision made
                agents: Agents involved in the decision
                confidence: Decision confidence (0-1)
                rationale: Optional reasoning

            Returns:
                Result dict with entry details
            """
            entry = {
                "message": f"Council Decision: {decision}",
                "status": "plan",
                "agent": "Council",
                "meta": {
                    "decision_type": "council",
                    "participating_agents": agents,
                    "confidence": confidence,
                    "rationale": rationale,
                    "session_id": self._session_id,
                }
            }
            self._decisions_logged += 1
            return {"logged": True, "entry": entry}

        registry.register_custom_tool(
            self.bridge_id,
            "log_decision",
            log_decision,
            description="Log a council decision with structured metadata"
        )

        # Custom tool: Get session status
        async def session_status() -> Dict[str, Any]:
            """Get current Council session status."""
            return {
                "session_id": self._session_id,
                "active_agents": self._active_agents,
                "entries_processed": self._entries_processed,
                "decisions_logged": self._decisions_logged,
            }

        registry.register_custom_tool(
            self.bridge_id,
            "session_status",
            session_status,
            description="Get current Council session status"
        )

    async def _background_sync(self) -> None:
        """Background task for periodic sync operations."""
        while True:
            try:
                await asyncio.sleep(60)  # Sync every minute

                # Example: Clean up stale agents
                now = datetime.now(timezone.utc)
                stale = []
                for agent, data in self._active_agents.items():
                    last = datetime.fromisoformat(data["last_activity"].replace("Z", "+00:00"))
                    if (now - last).total_seconds() > 300:  # 5 min timeout
                        stale.append(agent)

                for agent in stale:
                    del self._active_agents[agent]
                    logger.debug(f"Removed stale agent: {agent}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background sync: {e}")


# =============================================================================
# EXAMPLE: Registration and Usage
# =============================================================================

async def demo():
    """Demonstrate Council bridge registration and usage."""
    print("=== Council Bridge Demo ===\n")

    # Initialize storage
    db_path = Path(__file__).parent.parent / "data" / "scribe_projects.db"
    storage = SQLiteStorage(str(db_path))
    await storage._initialise()

    # Initialize registry
    config_dir = Path(__file__).parent.parent / ".scribe" / "config" / "bridges"
    registry = BridgeRegistry(storage, config_dir)

    # Create manifest programmatically (or load from YAML)
    manifest = BridgeManifest(
        bridge_id="council_mcp",
        name="Council MCP Bridge",
        version="1.0.0",
        description="Multi-agent orchestration bridge for Council MCP",
        author="Scribe Team",
        permissions=["read:all_projects", "write:own_projects", "create:projects"],
        project_config={
            "can_create_projects": True,
            "project_prefix": "council_",
            "auto_tag": ["council", "multi-agent"]
        },
        hooks={
            "pre_append": {"callback_type": "async", "timeout_ms": 5000, "critical": False},
            "post_append": {"callback_type": "async", "timeout_ms": 5000, "critical": False},
        },
        min_scribe_version="2.1.0"
    )

    # Check if already registered
    existing = await storage.list_bridges()
    is_registered = any(b["bridge_id"] == manifest.bridge_id for b in existing)

    if is_registered:
        print(f"Bridge {manifest.bridge_id} already registered")
        # Re-register to update
        await storage.update_bridge_state(manifest.bridge_id, BridgeState.UNREGISTERED.value)
        registry._manifests.pop(manifest.bridge_id, None)
        registry._bridges.pop(manifest.bridge_id, None)

    # Register
    bridge_id = await registry.register_bridge(manifest, CouncilBridgePlugin)
    print(f"Registered: {bridge_id}")

    # Activate
    await registry.activate_bridge(bridge_id)
    print(f"Activated: {bridge_id}")

    # Get bridge instance
    bridge = registry.get_bridge(bridge_id)
    if not bridge:
        print("Error: Bridge not found")
        return

    # Run health check
    health = await bridge.health_check()
    print(f"Health: {health}")

    # Test pre_append hook
    entry = {
        "message": "Test entry from Council",
        "status": "info",
        "agent": "TestAgent"
    }
    modified = await bridge.pre_append(entry)
    print(f"Modified entry: {modified}")

    # Test custom tool
    tool_registry = get_tool_registry()
    log_decision = tool_registry.get_custom_tool(bridge_id, "log_decision")
    if log_decision:
        result = await log_decision(
            decision="Use research-first approach",
            agents=["Researcher", "Architect"],
            confidence=0.9,
            rationale="Better alignment with PROTOCOL"
        )
        print(f"Decision logged: {result}")

    # Get session status
    session_status = tool_registry.get_custom_tool(bridge_id, "session_status")
    if session_status:
        status = await session_status()
        print(f"Session status: {status}")

    # Deactivate
    await registry.deactivate_bridge(bridge_id)
    print(f"Deactivated: {bridge_id}")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    asyncio.run(demo())
