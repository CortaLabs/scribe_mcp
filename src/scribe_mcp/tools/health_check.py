"""Health check tool for monitoring agent-scoped system status."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError


class _HealthCheckHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_HEALTH_CHECK_HELPER = _HealthCheckHelper()


@app.tool(**read_only_local_tool(title="Health Check", tags=("diagnostics", "read-only")))
async def health_check(agent: str) -> Dict[str, Any]:
    """
    Perform comprehensive health check of the agent-scoped system.

    Returns:
        Health status including sync status, active sessions, and system metrics.
    """
    state_snapshot = await server_module.state_manager.record_tool("health_check")
    agent_identity = server_module.get_agent_identity()
    agent_id = None
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    try:
        context: LoggingContext = await _HEALTH_CHECK_HELPER.prepare_context(
            tool_name="health_check",
            agent_id=agent_id,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _HEALTH_CHECK_HELPER.translate_project_error(exc)
        payload.setdefault("reminders", [])
        return payload

    health_status = {
        "status": "healthy",
        "timestamp": None,
        "components": {},
        "metrics": {},
        "issues": [],
        "recommendations": []
    }

    try:
        import asyncio
        from scribe_mcp.utils.time import utcnow

        health_status["timestamp"] = utcnow().isoformat()

        # Check 1: AgentContextManager availability
        agent_manager = server_module.get_agent_context_manager()
        if agent_manager:
            health_status["components"]["agent_context_manager"] = {
                "status": "available",
                "message": "AgentContextManager is initialized and ready"
            }
        else:
            health_status["components"]["agent_context_manager"] = {
                "status": "unavailable",
                "message": "AgentContextManager is not initialized"
            }
            health_status["status"] = "degraded"
            health_status["issues"].append("AgentContextManager not available")
            health_status["recommendations"].append("Restart server to initialize AgentContextManager")

        # Check 2: Storage backend health
        storage = server_module.storage_backend
        if storage:
            try:
                # Test database connection with a simple query
                await storage._fetchone("SELECT 1", ())
                health_status["components"]["storage_backend"] = {
                    "status": "healthy",
                    "message": f"Storage backend ({type(storage).__name__}) is responding"
                }
            except Exception as e:
                health_status["components"]["storage_backend"] = {
                    "status": "unhealthy",
                    "message": f"Storage backend error: {e}"
                }
                health_status["status"] = "unhealthy"
                health_status["issues"].append(f"Storage backend failure: {e}")
                health_status["recommendations"].append("Check database connectivity and configuration")
        else:
            health_status["components"]["storage_backend"] = {
                "status": "unavailable",
                "message": "Storage backend is not initialized"
            }
            health_status["status"] = "degraded"
            health_status["issues"].append("Storage backend not available")

        # Check 3: State manager health
        state_manager = server_module.state_manager
        if state_manager:
            try:
                state = await state_manager.load()
                health_status["components"]["state_manager"] = {
                    "status": "healthy",
                    "message": "State manager is accessible"
                }
                health_status["metrics"]["state_file_size"] = len(str(state.__dict__))
            except Exception as e:
                health_status["components"]["state_manager"] = {
                    "status": "unhealthy",
                    "message": f"State manager error: {e}"
                }
                health_status["status"] = "unhealthy"
                health_status["issues"].append(f"State manager failure: {e}")
        else:
            health_status["components"]["state_manager"] = {
                "status": "unavailable",
                "message": "State manager is not initialized"
            }
            health_status["status"] = "degraded"
            health_status["issues"].append("State manager not available")

        # Check 4: Sync status between JSON state and database
        if agent_manager and storage and state_manager:
            sync_status = await _check_sync_status(agent_manager, storage, state_manager)
            health_status["components"]["sync_status"] = sync_status
            if sync_status["status"] != "in_sync":
                health_status["status"] = "degraded"
                health_status["issues"].extend(sync_status["issues"])
                health_status["recommendations"].extend(sync_status["recommendations"])

        # Check 5: Active sessions
        if agent_manager:
            try:
                # Get count of active sessions (approximate)
                if hasattr(agent_manager, '_session_leases'):
                    active_sessions = len(agent_manager._session_leases)
                    health_status["metrics"]["active_sessions"] = active_sessions
                    health_status["components"]["sessions"] = {
                        "status": "healthy",
                        "message": f"{active_sessions} active sessions"
                    }
                else:
                    health_status["components"]["sessions"] = {
                        "status": "unknown",
                        "message": "Cannot determine session count"
                    }
            except Exception as e:
                health_status["components"]["sessions"] = {
                    "status": "error",
                    "message": f"Session check error: {e}"
                }

        # Check 6: Recent agent activity
        if agent_manager:
            try:
                recent_events = await agent_manager.get_agent_events(limit=10)
                health_status["metrics"]["recent_events_count"] = len(recent_events)
                if recent_events:
                    last_event_time = recent_events[0]["created_at"]
                    health_status["metrics"]["last_event_time"] = last_event_time
                    health_status["components"]["activity"] = {
                        "status": "active",
                        "message": f"Recent activity detected ({len(recent_events)} events in trail)"
                    }
                else:
                    health_status["components"]["activity"] = {
                        "status": "inactive",
                        "message": "No recent agent activity detected"
                    }
                    health_status["recommendations"].append("Check if agents are properly connecting to the system")
            except Exception as e:
                health_status["components"]["activity"] = {
                    "status": "error",
                    "message": f"Activity check error: {e}"
                }

        # Check 7: Background startup/service health
        try:
            background_services = server_module.get_background_service_status()
            failed_services = [
                name
                for name, details in background_services.items()
                if details.get("status") == "failed"
            ]
            running_services = [
                name
                for name, details in background_services.items()
                if details.get("status") == "running"
            ]

            health_status["components"]["background_services"] = {
                "status": "degraded" if failed_services else "healthy",
                "message": (
                    f"{len(background_services)} tracked "
                    f"({len(running_services)} running, {len(failed_services)} failed)"
                ),
                "services": background_services,
            }
            health_status["metrics"]["background_services_total"] = len(background_services)
            health_status["metrics"]["background_services_running"] = len(running_services)
            health_status["metrics"]["background_services_failed"] = len(failed_services)

            if failed_services:
                if health_status["status"] == "healthy":
                    health_status["status"] = "degraded"
                health_status["issues"].append(
                    f"Background service failures: {', '.join(failed_services)}"
                )
                health_status["recommendations"].append(
                    "Inspect health_check background_services details and server logs for failures."
                )
        except Exception as e:
            health_status["components"]["background_services"] = {
                "status": "error",
                "message": f"Background service check error: {e}",
            }

        # Overall assessment
        if not health_status["issues"]:
            health_status["summary"] = "All systems operational and in sync"
        else:
            health_status["summary"] = f"{len(health_status['issues'])} issue(s) detected"

    except Exception as e:
        health_status["status"] = "error"
        health_status["components"]["health_check"] = {
            "status": "error",
            "message": f"Health check failed: {e}"
        }
        health_status["issues"].append(f"Health check system failure: {e}")
        health_status["summary"] = "Health check system error"

    return _HEALTH_CHECK_HELPER.apply_context_payload(health_status, context)


async def _check_sync_status(agent_manager, storage, state_manager) -> Dict[str, Any]:
    """
    Check sync status between JSON state and database.

    Args:
        agent_manager: AgentContextManager instance
        storage: Storage backend
        state_manager: State manager

    Returns:
        Sync status information
    """
    sync_status = {
        "status": "in_sync",
        "message": "JSON state and database are synchronized",
        "issues": [],
        "recommendations": [],
        "details": {}
    }

    try:
        # Get current state from JSON
        json_state = await state_manager.load()

        # Compare current project if any
        if json_state.current_project:
            # Try to get the same project from database (via Scribe agent)
            try:
                db_project = await storage.get_agent_project("Scribe")
                if db_project and db_project.get("project_name"):
                    if db_project["project_name"] == json_state.current_project:
                        sync_status["details"]["current_project"] = {
                            "json": json_state.current_project,
                            "database": db_project["project_name"],
                            "status": "matched"
                        }
                    else:
                        sync_status["details"]["current_project"] = {
                            "json": json_state.current_project,
                            "database": db_project["project_name"],
                            "status": "mismatch"
                        }
                        sync_status["status"] = "out_of_sync"
                        sync_status["issues"].append("Current project mismatch between JSON and database")
                        sync_status["recommendations"].append("Run migration or set project to resync")
                else:
                    sync_status["details"]["current_project"] = {
                        "json": json_state.current_project,
                        "database": None,
                        "status": "missing_in_db"
                    }
                    sync_status["status"] = "out_of_sync"
                    sync_status["issues"].append("Current project exists in JSON but not in database")
                    sync_status["recommendations"].append("Use set_project to sync current project to database")
            except Exception as e:
                sync_status["details"]["current_project"] = {
                    "error": f"Database query failed: {e}"
                }
                sync_status["status"] = "sync_check_failed"
                sync_status["issues"].append(f"Failed to check project sync: {e}")

        # Check version consistency
        if hasattr(json_state, 'version'):
            sync_status["details"]["version"] = {
                "json_state": json_state.version
            }

    except Exception as e:
        sync_status["status"] = "error"
        sync_status["issues"].append(f"Sync check failed: {e}")
        sync_status["recommendations"].append("Check system logs for detailed error information")

    return sync_status
