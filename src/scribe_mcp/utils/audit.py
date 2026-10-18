"""
Audit trail management for Scribe MCP log rotation system.

Provides persistent storage and retrieval of rotation metadata,
maintaining complete audit trails for log integrity verification.
"""

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import threading

from scribe_mcp.config.paths import runtime_state_dir


class AuditTrailManager:
    """
    Manages audit trail storage and retrieval for log rotation events.

    Provides thread-safe operations for storing, retrieving, and verifying
    rotation metadata with JSON-based persistence.
    """

    def __init__(self, state_dir: str = None):
        """
        Initialize audit trail manager.

        Args:
            state_dir: Directory for storing audit trail files
                       (defaults to `.scribe/state/` under the repo root)
        """
        if state_dir is None:
            state_dir = runtime_state_dir()

        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Thread lock for atomic operations
        self._lock = threading.RLock()

    def _get_audit_file_path(self, project_name: str) -> Path:
        """Get the audit trail file path for a project."""
        # Sanitize project name for filesystem safety
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
        return self.state_dir / f"rotation_audit_{safe_name}.json"

    def store_rotation_metadata(self, project_name: str, metadata: Dict[str, Any]) -> bool:
        """
        Store rotation metadata in the audit trail.

        Args:
            project_name: Name of the project
            metadata: Rotation metadata to store

        Returns:
            True if storage successful, False otherwise
        """
        try:
            with self._lock:
                audit_file = self._get_audit_file_path(project_name)

                # Load existing audit trail or create new
                audit_trail = self._load_audit_trail(project_name)

                # Add timestamp if not present
                if "stored_timestamp" not in metadata:
                    metadata["stored_timestamp"] = datetime.now(timezone.utc).isoformat() + " UTC"

                # Add to audit trail
                audit_trail["rotations"].append(metadata)
                audit_trail["total_rotations"] = len(audit_trail["rotations"])
                audit_trail["last_updated"] = metadata["stored_timestamp"]

                # Atomic write to file
                temp_file = audit_file.with_suffix(".tmp")
                try:
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump(audit_trail, f, indent=2, ensure_ascii=False)

                    # Atomic rename
                    temp_file.rename(audit_file)

                except Exception as e:
                    # Cleanup temp file if write fails
                    if temp_file.exists():
                        temp_file.unlink()
                    raise e

                return True

        except Exception as e:
            # Log error but don't raise - rotation should continue
            logger.warning("Error storing rotation metadata for %s: %s", project_name, e)
            return False

    def _load_audit_trail(self, project_name: str) -> Dict[str, Any]:
        """
        Load audit trail from file or create new structure.

        Args:
            project_name: Name of the project

        Returns:
            Audit trail dictionary
        """
        audit_file = self._get_audit_file_path(project_name)

        if not audit_file.exists():
            # Create new audit trail structure
            return {
                "project_name": project_name,
                "created_timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
                "rotations": [],
                "total_rotations": 0,
                "last_updated": None,
                "version": "1.0"
            }

        try:
            with open(audit_file, 'r', encoding='utf-8') as f:
                audit_trail = json.load(f)

            # Validate structure
            if not isinstance(audit_trail, dict):
                raise ValueError("Invalid audit trail format")

            # Ensure required fields
            audit_trail.setdefault("project_name", project_name)
            audit_trail.setdefault("rotations", [])
            audit_trail.setdefault("total_rotations", len(audit_trail["rotations"]))
            audit_trail.setdefault("version", "1.0")

            return audit_trail

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Error loading audit trail for %s: %s", project_name, e)
            # Return fresh structure if file is corrupted
            return {
                "project_name": project_name,
                "created_timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
                "rotations": [],
                "total_rotations": 0,
                "last_updated": None,
                "version": "1.0",
                "corruption_note": f"File corrupted at {datetime.now(timezone.utc).isoformat() + ' UTC'}"
            }

    def get_rotation_history(self, project_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get rotation history for a project.

        Args:
            project_name: Name of the project
            limit: Maximum number of rotations to return (most recent first)

        Returns:
            List of rotation metadata dictionaries
        """
        try:
            audit_trail = self._load_audit_trail(project_name)
            rotations = audit_trail.get("rotations", [])

            # Sort by timestamp (most recent first)
            rotations.sort(key=lambda x: x.get("rotation_timestamp", ""), reverse=True)

            if limit:
                rotations = rotations[:limit]

            return rotations

        except Exception as e:
            logger.warning("Error getting rotation history for %s: %s", project_name, e)
            return []

    def get_rotation_by_uuid(self, project_name: str, rotation_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get specific rotation by UUID.

        Args:
            project_name: Name of the project
            rotation_uuid: UUID of the rotation to find

        Returns:
            Rotation metadata dictionary or None if not found
        """
        try:
            audit_trail = self._load_audit_trail(project_name)
            rotations = audit_trail.get("rotations", [])

            for rotation in rotations:
                if rotation.get("rotation_uuid") == rotation_uuid:
                    return rotation

            return None

        except Exception as e:
            logger.warning("Error getting rotation %s for %s: %s", rotation_uuid, project_name, e)
            return None

    def verify_rotation_integrity(self, project_name: str, rotation_uuid: str) -> Tuple[bool, str]:
        """
        Verify the integrity of a specific rotation.

        Args:
            project_name: Name of the project
            rotation_uuid: UUID of the rotation to verify

        Returns:
            Tuple of (is_valid: bool, verification_message: str)
        """
        try:
            rotation = self.get_rotation_by_uuid(project_name, rotation_uuid)
            if not rotation:
                return False, f"Rotation {rotation_uuid} not found"

            archived_file_path = rotation.get("archived_file_path")
            expected_hash = rotation.get("file_hash")

            if not archived_file_path or not expected_hash:
                return False, "Missing file path or hash in rotation metadata"

            # Check if file still exists
            if not Path(archived_file_path).exists():
                return False, f"Archived file not found: {archived_file_path}"

            # Import integrity utilities
            from .integrity import verify_file_integrity

            # Verify file integrity
            is_valid, actual_hash = verify_file_integrity(archived_file_path, expected_hash)

            if is_valid:
                return True, f"File integrity verified: {actual_hash[:16]}..."
            else:
                return False, f"File integrity compromised: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."

        except Exception as e:
            return False, f"Error verifying rotation integrity: {e}"

    def get_audit_summary(self, project_name: str) -> Dict[str, Any]:
        """
        Get audit trail summary for a project.

        Args:
            project_name: Name of the project

        Returns:
            Audit summary dictionary
        """
        try:
            audit_trail = self._load_audit_trail(project_name)
            rotations = audit_trail.get("rotations", [])

            if not rotations:
                return {
                    "project_name": project_name,
                    "total_rotations": 0,
                    "oldest_rotation": None,
                    "newest_rotation": None,
                    "total_entries_archived": 0,
                    "total_size_archived": 0,
                    "last_updated": audit_trail.get("last_updated")
                }

            # Calculate summary statistics
            total_entries = sum(r.get("entry_count", 0) for r in rotations if r.get("entry_count", 0) > 0)
            total_size = sum(r.get("file_size", 0) for r in rotations if r.get("file_size", 0) > 0)

            # Sort by timestamp for oldest/newest
            sorted_rotations = sorted(rotations, key=lambda x: x.get("rotation_timestamp", ""))

            return {
                "project_name": project_name,
                "total_rotations": len(rotations),
                "oldest_rotation": sorted_rotations[0].get("rotation_timestamp") if sorted_rotations else None,
                "newest_rotation": sorted_rotations[-1].get("rotation_timestamp") if sorted_rotations else None,
                "total_entries_archived": total_entries,
                "total_size_archived": total_size,
                "last_updated": audit_trail.get("last_updated"),
                "audit_file_path": str(self._get_audit_file_path(project_name))
            }

        except Exception as e:
            return {
                "project_name": project_name,
                "error": str(e),
                "total_rotations": 0
            }

    def cleanup_old_rotations(self, project_name: str, keep_count: int = 50) -> Tuple[int, bool]:
        """
        Clean up old rotation records, keeping only the most recent ones.

        Args:
            project_name: Name of the project
            keep_count: Number of recent rotations to keep

        Returns:
            Tuple of (rotations_removed: int, success: bool)
        """
        try:
            with self._lock:
                audit_trail = self._load_audit_trail(project_name)
                rotations = audit_trail.get("rotations", [])

                if len(rotations) <= keep_count:
                    return 0, True

                # Sort by timestamp (most recent first)
                rotations.sort(key=lambda x: x.get("rotation_timestamp", ""), reverse=True)

                # Keep only the most recent rotations
                kept_rotations = rotations[:keep_count]
                removed_count = len(rotations) - keep_count

                # Update audit trail
                audit_trail["rotations"] = kept_rotations
                audit_trail["total_rotations"] = len(kept_rotations)
                audit_trail["last_updated"] = datetime.now(timezone.utc).isoformat() + " UTC"
                audit_trail["cleanup_note"] = f"Removed {removed_count} old rotation records"

                # Save updated audit trail
                audit_file = self._get_audit_file_path(project_name)
                with open(audit_file, 'w', encoding='utf-8') as f:
                    json.dump(audit_trail, f, indent=2, ensure_ascii=False)

                return removed_count, True

        except Exception as e:
            logger.warning("Error cleaning up old rotations for %s: %s", project_name, e)
            return 0, False

    def list_audited_projects(self) -> List[str]:
        """
        List all projects that have audit trails.

        Returns:
            List of project names
        """
        try:
            projects = []
            for file_path in self.state_dir.glob("rotation_audit_*.json"):
                # Extract project name from filename
                filename = file_path.stem  # Remove .json extension
                if filename.startswith("rotation_audit_"):
                    project_name = filename[len("rotation_audit_"):]
                    # Reverse the sanitization
                    project_name = project_name.replace("_", " ")
                    projects.append(project_name)

            return sorted(projects)

        except Exception as e:
            logger.warning("Error listing audited projects: %s", e)
            return []


# Global audit manager instance
_audit_manager = None


def get_audit_manager(state_dir: str = None) -> AuditTrailManager:
    """
    Get global audit manager instance.

    Args:
        state_dir: Directory for storing audit trail files

    Returns:
        AuditTrailManager instance
    """
    global _audit_manager
    if _audit_manager is None:
        _audit_manager = AuditTrailManager(state_dir)
    return _audit_manager


# Convenience functions for direct usage
def store_rotation_metadata(project_name: str, metadata: Dict[str, Any]) -> bool:
    """Store rotation metadata for a project."""
    return get_audit_manager().store_rotation_metadata(project_name, metadata)


def get_rotation_history(project_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get rotation history for a project."""
    return get_audit_manager().get_rotation_history(project_name, limit)


def verify_rotation_integrity(project_name: str, rotation_uuid: str) -> Tuple[bool, str]:
    """Verify the integrity of a specific rotation."""
    return get_audit_manager().verify_rotation_integrity(project_name, rotation_uuid)


def get_audit_summary(project_name: str) -> Dict[str, Any]:
    """Get audit trail summary for a project."""
    return get_audit_manager().get_audit_summary(project_name)
