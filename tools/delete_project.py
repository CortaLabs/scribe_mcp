"""Tool for deleting or archiving projects."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.agent_project_utils import (
    ensure_agent_session,
    validate_agent_session,
)
from scribe_mcp.tools.project_utils import (
    list_project_configs,
    slugify_project_name,
)


@app.tool()
async def delete_project(
    name: str,
    root: str,  # Required: repo root for safety (like set_project)
    mode: str = "archive",  # "archive" or "permanent"
    confirm: bool = False,  # Must explicitly confirm
    force: bool = False,    # Override safety checks
    archive_path: Optional[str] = None,  # Custom archive location
    agent_id: Optional[str] = None,  # Agent identification
) -> Dict[str, Any]:
    """Delete or archive a project and all associated data.

    Args:
        name: Project name to delete
        root: Repository root path (required for safety, must match project's root)
        mode: "archive" (default) moves files to archive, "permanent" deletes everything
        confirm: Must be True to proceed with deletion
        force: Override safety checks (not recommended)
        archive_path: Custom archive directory (default: docs/archived_projects/)
        agent_id: Agent identification (auto-detected if not provided)

    Returns:
        Dict with deletion status, details, and any warnings
    """
    state_snapshot = await server_module.state_manager.record_tool("delete_project")

    # Auto-detect agent ID if not provided
    if agent_id is None:
        agent_identity = server_module.get_agent_identity()
        if agent_identity:
            agent_id = await agent_identity.get_or_create_agent_id()
        else:
            agent_id = "Scribe"  # Fallback

    # Update agent activity tracking
    agent_identity = server_module.get_agent_identity()
    if agent_identity:
        await agent_identity.update_agent_activity(
            agent_id, "delete_project", {"project_name": name, "mode": mode}
        )

    # Initialize response
    response = {
        "success": False,
        "project_name": name,
        "mode": mode,
        "message": "",
        "details": {},
        "warnings": [],
        "errors": [],
    }

    # Validate mode
    if mode not in ["archive", "permanent"]:
        response["errors"].append(f"Invalid mode: {mode}. Must be 'archive' or 'permanent'.")
        return response

    # Safety check: require confirmation unless force=True
    if not confirm and not force:
        response["errors"].append(
            "Deletion requires explicit confirmation. Set confirm=True to proceed."
        )
        response["message"] = "Safety check failed: confirmation required"
        return response

    try:
        # Get storage backend
        storage = server_module.storage_backend

        # Verify project exists in storage (primary lookup method)
        project_record = await storage.fetch_project(name)
        if not project_record:
            response["warnings"].append(f"Project '{name}' not found in storage, checking state cache only.")

        # Safety check: verify root matches project's repo_root
        resolved_root = Path(root).resolve()
        if project_record and project_record.repo_root:
            project_root = Path(project_record.repo_root).resolve()
            if resolved_root != project_root:
                response["errors"].append(
                    f"Root mismatch: provided '{resolved_root}' does not match project root '{project_root}'"
                )
                response["message"] = "Safety check failed: root parameter must match project's repository root"
                return response

        # Try to get project configuration for file system operations
        # But don't require it - we can derive paths from the project record
        project_config = None
        project_configs = list_project_configs()
        if name in project_configs:
            project_config = project_configs[name]

        # Check for active agent sessions (unless force=True)
        if not force:
            # TODO: Implement active session checking
            # For now, we'll just warn about this
            response["warnings"].append(
                "Cannot check for active agent sessions in current implementation"
            )

        # Initialize details tracking
        deleted_items = []
        archived_items = []

        # Handle file system operations only if we have a project record
        if project_record:
            if project_config and "docs_dir" in project_config:
                project_docs_path = Path(project_config["docs_dir"])
            else:
                # Use the project record's progress_log_path to derive docs directory
                progress_log_path = Path(project_record.progress_log_path)
                project_docs_path = progress_log_path.parent

            if mode == "archive":
                # Archive mode: move files to archive directory
                if archive_path is None:
                    archive_path = "docs/archived_projects"

                archive_dir = Path(archive_path)
                archive_dir.mkdir(parents=True, exist_ok=True)

                # Create timestamped archive subdirectory
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                project_archive_dir = archive_dir / f"{name}_{timestamp}"

                if project_docs_path.exists():
                    shutil.move(str(project_docs_path), str(project_archive_dir))
                    archived_items.append(str(project_docs_path))
                    response["details"]["archive_location"] = str(project_archive_dir)

                response["message"] = f"Project '{name}' archived to {project_archive_dir}"

            elif mode == "permanent":
                # Permanent mode: delete files
                if project_docs_path.exists():
                    shutil.rmtree(str(project_docs_path))
                    deleted_items.append(str(project_docs_path))

                response["message"] = f"Project '{name}' permanently deleted"

        # Delete from database (this will cascade delete all related data)
        db_deleted = False
        if project_record:
            db_deleted = await storage.delete_project(name)
        else:
            response["warnings"].append("No database record found to delete")

        if db_deleted:
            deleted_items.append("database_records")
        elif project_record:
            response["warnings"].append("Database deletion may have been incomplete")

        # Clear any cached state for this project
        state_manager = server_module.state_manager
        current_state = await state_manager.load()

        if name in current_state.projects:
            # Remove project from state - need to manually handle removal since with_project doesn't support deletion
            updated_projects = dict(current_state.projects)
            del updated_projects[name]

            # Also remove from recent projects list
            updated_recent = [p for p in current_state.recent_projects if p != name]

            # Clear current_project if it matches the deleted project
            updated_current = None if current_state.current_project == name else current_state.current_project

            # Create updated state
            from scribe_mcp.state.manager import State
            updated_state = State(
                current_project=updated_current,
                projects=updated_projects,
                recent_projects=updated_recent,
                recent_tools=list(current_state.recent_tools),
                last_activity_at=current_state.last_activity_at,
                session_started_at=current_state.session_started_at,
                version=current_state.version,
                last_updated_by=current_state.last_updated_by,
                operation_timestamp=current_state.operation_timestamp,
                agent_state=current_state.agent_state,
            )

            await state_manager.persist(updated_state)
            deleted_items.append("state_cache")
        else:
            response["warnings"].append(
                f"Project '{name}' not found in state cache"
            )

        # Update response with success
        response["success"] = True
        response["details"]["deleted_files"] = deleted_items
        response["details"]["archived_files"] = archived_items
        response["details"]["database_cleanup"] = db_deleted

        # Add final confirmation
        if not project_record:
            response["message"] = f"Project '{name}' removed from state cache only"
        elif mode == "archive":
            response["message"] += f" (database records cleaned up)"
        else:
            response["message"] += " (all data permanently removed)"

    except Exception as e:
        response["success"] = False
        response["errors"].append(f"Unexpected error during deletion: {str(e)}")
        response["message"] = f"Failed to delete project '{name}'"

    return response