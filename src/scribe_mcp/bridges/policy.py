"""Permission enforcement for bridge operations."""

from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class BridgePolicyPlugin:
    """
    Enforces permissions for bridge operations.

    Checks manifest.permissions list and validates operations
    against allowed_log_types and forbidden_projects.

    Phase 3: Enhanced with project ownership checking for access control.
    """

    def __init__(self, manifest, storage_backend=None):
        self.manifest = manifest
        self.bridge_id = manifest.bridge_id
        self.permissions = set(manifest.permissions)
        self._storage = storage_backend

    def can_append_entry(self, project_name: str, log_type: str = "progress") -> bool:
        """Static append permission check used before async ownership checks."""
        if "write:all_projects" in self.permissions:
            return self._can_use_log_type(log_type)
        if "write:own_projects" in self.permissions:
            return self._can_use_log_type(log_type)

        return False

    def can_read_entries(self, project_name: str) -> bool:
        """Static read permission check used before async ownership checks."""
        if "read:all_projects" in self.permissions:
            return True
        if "read:own_projects" in self.permissions:
            return True

        return False

    def can_create_projects(self) -> bool:
        """Check if bridge can create projects."""
        return (
            "create:projects" in self.permissions and
            self.manifest.project_config.can_create_projects
        )

    def _can_use_log_type(self, log_type: str) -> bool:
        """Check if bridge can use this log type."""
        # Bridge's own log types are always allowed
        if log_type in self.manifest.log_config:
            return True

        # Standard log types allowed if bridge has write permission
        standard_types = {"progress", "doc_updates", "security", "bugs", "global"}
        if log_type in standard_types:
            return True

        return False

    async def can_modify_project(self, project_name: str) -> bool:
        """
        Check if bridge can modify a project (Phase 3 access control).

        Rules:
        - Bridge can always modify its own projects
        - Bridge needs 'write:all_projects' for other projects
        - Non-bridge-managed projects are accessible to all with write permission
        """
        if "write:all_projects" in self.permissions:
            return True

        if self._storage is None:
            # No storage = can't check ownership, allow by default if has write permission
            return "write:own_projects" in self.permissions

        # Fetch project to check ownership
        try:
            project = await self._storage.fetch_project(project_name)
        except Exception as e:
            logger.warning(f"Failed to fetch project {project_name} for ownership check: {e}")
            return False

        if project is None:
            # New project - allow if has create permission
            return self.can_create_projects()

        # Check if bridge-managed
        bridge_managed = getattr(project, "bridge_managed", False)
        owner_bridge = getattr(project, "bridge_id", None)

        if not bridge_managed:
            # Not bridge-managed - anyone with write permission can modify
            return "write:own_projects" in self.permissions or "write:all_projects" in self.permissions

        if owner_bridge == self.bridge_id:
            # This bridge owns it
            return True

        # Owned by different bridge - need write:all_projects
        return "write:all_projects" in self.permissions

    async def can_read_project(self, project_name: str) -> bool:
        """
        Check if bridge can read a project with ownership awareness.

        Rules:
        - read:all_projects can read anything
        - read:own_projects can read its own bridge-managed projects
        - non-bridge-managed projects are readable to bridges with read permission
        """
        if "read:all_projects" in self.permissions:
            return True

        if "read:own_projects" not in self.permissions:
            return False

        if self._storage is None:
            return True

        try:
            project = await self._storage.fetch_project(project_name)
        except Exception as e:
            logger.warning(f"Failed to fetch project {project_name} for read ownership check: {e}")
            return False

        if project is None:
            return False

        bridge_managed = getattr(project, "bridge_managed", False)
        owner_bridge = getattr(project, "bridge_id", None)

        if not bridge_managed:
            return True

        return owner_bridge == self.bridge_id

    async def can_append_to_project(self, project_name: str, log_type: str = "progress") -> bool:
        """Check if bridge can append entries to project (Phase 3 access control)."""
        # First check log type permission
        if not self._can_use_log_type(log_type):
            return False

        # Then check project access
        return await self.can_modify_project(project_name)
