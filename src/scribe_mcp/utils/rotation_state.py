"""
Rotation state management for Scribe MCP log rotation system.

Provides persistent storage and retrieval of rotation state information,
including sequence numbers, hash chains, and rotation metadata.
"""

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Dict, Optional, Any, Tuple, List
from datetime import datetime, timezone
import threading
import time

from scribe_mcp.config.paths import runtime_state_dir


class RotationStateManager:
    """
    Manages rotation state persistence and tracking.

    Provides thread-safe operations for maintaining rotation sequences,
    hash chains, and state information across server restarts.
    """

    def __init__(self, state_dir: str = None, state_file: str = "rotation_state.json"):
        """
        Initialize rotation state manager.

        Args:
            state_dir: Directory for storing state files
            state_file: Name of the state file
        """
        if state_dir is None:
            state_dir = runtime_state_dir()

        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / state_file

        # Thread lock for atomic operations
        self._lock = threading.RLock()

        # Load or initialize state
        self._state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load rotation state from file or create new structure."""
        if not self.state_file.exists():
            return {
                "version": "1.0",
                "created_timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
                "last_updated": datetime.now(timezone.utc).isoformat() + " UTC",
                "projects": {},
                "global_settings": {
                    "max_rotations_per_project": 100,
                    "cleanup_threshold": 150,
                    "hash_chaining_enabled": True,
                    "integrity_verification_enabled": True
                }
            }

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Validate and ensure required structure
            if not isinstance(state, dict):
                raise ValueError("Invalid state format")

            state.setdefault("version", "1.0")
            state.setdefault("projects", {})
            state.setdefault("global_settings", {
                "max_rotations_per_project": 100,
                "cleanup_threshold": 150,
                "hash_chaining_enabled": True,
                "integrity_verification_enabled": True
            })

            return state

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Error loading rotation state: %s", e)
            # Return fresh state if file is corrupted
            return {
                "version": "1.0",
                "created_timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
                "last_updated": datetime.now(timezone.utc).isoformat() + " UTC",
                "projects": {},
                "global_settings": {
                    "max_rotations_per_project": 100,
                    "cleanup_threshold": 150,
                    "hash_chaining_enabled": True,
                    "integrity_verification_enabled": True
                },
                "corruption_note": f"State file corrupted at {datetime.now(timezone.utc).isoformat() + ' UTC'}"
            }

    def _save_state(self) -> bool:
        """Save state to file atomically."""
        try:
            with self._lock:
                self._state["last_updated"] = datetime.now(timezone.utc).isoformat() + " UTC"

                # Atomic write
                temp_file = self.state_file.with_suffix(".tmp")
                try:
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump(self._state, f, indent=2, ensure_ascii=False)

                    # Atomic rename with retry (Windows safe)
                    for attempt in range(5):
                        try:
                            temp_file.replace(self.state_file)
                            break
                        except PermissionError:
                            if attempt == 4:
                                raise
                            time.sleep(0.1)
                    return True

                except Exception as e:
                    # Cleanup temp file if write fails
                    if temp_file.exists():
                        temp_file.unlink()
                    raise e

        except Exception as e:
            logger.warning("Error saving rotation state: %s", e)
            return False

    def get_project_state(self, project_name: str) -> Dict[str, Any]:
        """
        Get rotation state for a specific project.

        Args:
            project_name: Name of the project

        Returns:
            Project rotation state dictionary
        """
        with self._lock:
            return self._state["projects"].setdefault(project_name, {
                "created_timestamp": datetime.now(timezone.utc).isoformat() + " UTC",
                "current_sequence": 0,
                "total_rotations": 0,
                "last_rotation_timestamp": None,
                "hash_chain": {
                    "root_hash": None,
                    "current_sequence": 0,
                    "last_hash": None
                },
                "rotation_ids": [],
                "log_stats": {},
                "settings": {
                    "auto_cleanup": True,
                    "max_rotations": 100
                }
            })

    def update_project_state(self, project_name: str, rotation_metadata: Dict[str, Any]) -> bool:
        """
        Update project state after a rotation.

        Args:
            project_name: Name of the project
            rotation_metadata: Metadata from the completed rotation

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self._lock:
                project_state = self.get_project_state(project_name)

                # Update sequence counters
                project_state["current_sequence"] = rotation_metadata.get("sequence_number", 0)
                project_state["total_rotations"] += 1
                project_state["last_rotation_timestamp"] = rotation_metadata.get("rotation_timestamp_utc")

                # Update hash chain
                file_hash = rotation_metadata.get("file_hash")
                if file_hash and self._state["global_settings"]["hash_chaining_enabled"]:
                    if project_state["hash_chain"]["root_hash"] is None:
                        project_state["hash_chain"]["root_hash"] = file_hash
                    project_state["hash_chain"]["current_sequence"] = rotation_metadata.get("sequence_number", 0)
                    project_state["hash_chain"]["last_hash"] = file_hash

                # Track rotation IDs
                rotation_id = rotation_metadata.get("rotation_uuid")
                if rotation_id:
                    project_state["rotation_ids"].append(rotation_id)

                # Auto-cleanup old rotation IDs if enabled
                if (project_state["settings"]["auto_cleanup"] and
                    len(project_state["rotation_ids"]) > project_state["settings"]["max_rotations"]):

                    max_rotations = project_state["settings"]["max_rotations"]
                    project_state["rotation_ids"] = project_state["rotation_ids"][-max_rotations:]

                # Save updated state
                return self._save_state()

        except Exception as e:
            logger.warning("Error updating project state for %s: %s", project_name, e)
            return False

    def get_log_stats(self, project_name: str, log_type: str) -> Dict[str, Any]:
        """
        Return cached statistics for a specific project/log combination.

        Args:
            project_name: Project identifier
            log_type: Log type identifier

        Returns:
            Dictionary of cached statistics (copy) or empty dict.
        """
        with self._lock:
            project_state = self.get_project_state(project_name)
            log_stats = project_state.setdefault("log_stats", {})
            return dict(log_stats.get(log_type, {}))

    def update_log_stats(
        self,
        project_name: str,
        log_type: str,
        *,
        size_bytes: Optional[int] = None,
        line_count: Optional[int] = None,
        ema_bytes_per_line: Optional[float] = None,
        mtime_ns: Optional[int] = None,
        inode: Optional[int] = None,
        source: Optional[str] = None,
        initialized: Optional[bool] = None,
    ) -> bool:
        """
        Update cached statistics for a project/log combination.

        Args:
            project_name: Project identifier
            log_type: Log type identifier
            size_bytes: Observed file size in bytes
            line_count: Observed line count
            ema_bytes_per_line: Updated EMA for bytes-per-line
            mtime_ns: Observed modification time in nanoseconds
            inode: Observed inode or file identifier
            source: Optional label describing source of update

        Returns:
            True if state persisted successfully, False otherwise.
        """
        with self._lock:
            project_state = self.get_project_state(project_name)
            log_stats = project_state.setdefault("log_stats", {})
            entry = dict(log_stats.get(log_type, {}))

            if size_bytes is not None:
                try:
                    entry["size_bytes"] = int(size_bytes)
                except (TypeError, ValueError):
                    pass

            if line_count is not None:
                try:
                    entry["line_count"] = int(line_count)
                except (TypeError, ValueError):
                    pass

            if ema_bytes_per_line is not None:
                try:
                    entry["ema_bytes_per_line"] = float(ema_bytes_per_line)
                except (TypeError, ValueError):
                    pass

            if mtime_ns is not None:
                try:
                    entry["mtime_ns"] = int(mtime_ns)
                except (TypeError, ValueError):
                    pass

            if inode is not None:
                try:
                    candidate = int(inode)
                    entry["inode"] = candidate if candidate != 0 else None
                except (TypeError, ValueError):
                    entry["inode"] = None

            if initialized is not None:
                entry["initialized"] = bool(initialized)

            if source:
                entry["source"] = source

            entry["updated_at"] = datetime.now(timezone.utc).isoformat() + " UTC"
            log_stats[log_type] = entry
            return self._save_state()

    def generate_rotation_id(self, project_name: str) -> str:
        """
        Generate a unique rotation ID for a project.

        Args:
            project_name: Name of the project

        Returns:
            Unique rotation ID (UUID)
        """
        return str(uuid.uuid4())

    def get_next_sequence_number(self, project_name: str) -> int:
        """
        Get the next sequence number for a project rotation.

        Args:
            project_name: Name of the project

        Returns:
            Next sequence number
        """
        with self._lock:
            project_state = self.get_project_state(project_name)
            return project_state["current_sequence"] + 1

    def get_hash_chain_info(self, project_name: str) -> Dict[str, Any]:
        """
        Get hash chain information for a project.

        Args:
            project_name: Name of the project

        Returns:
            Hash chain information dictionary
        """
        with self._lock:
            project_state = self.get_project_state(project_name)
            return project_state["hash_chain"].copy()

    def get_project_statistics(self, project_name: str) -> Dict[str, Any]:
        """
        Get comprehensive rotation statistics for a project.

        Args:
            project_name: Name of the project

        Returns:
            Project statistics dictionary
        """
        with self._lock:
            project_state = self.get_project_state(project_name)

            return {
                "project_name": project_name,
                "current_sequence": project_state["current_sequence"],
                "total_rotations": project_state["total_rotations"],
                "last_rotation_timestamp": project_state["last_rotation_timestamp"],
                "hash_chain_root": project_state["hash_chain"]["root_hash"],
                "hash_chain_sequence": project_state["hash_chain"]["current_sequence"],
                "hash_chain_last": project_state["hash_chain"]["last_hash"],
                "rotation_ids_count": len(project_state["rotation_ids"]),
                "created_timestamp": project_state["created_timestamp"],
                "settings": project_state["settings"].copy()
            }

    def cleanup_project_state(self, project_name: str, keep_count: int = 50) -> Tuple[int, bool]:
        """
        Clean up old rotation state for a project.

        Args:
            project_name: Name of the project
            keep_count: Number of recent rotations to keep in state

        Returns:
            Tuple of (rotations_removed: int, success: bool)
        """
        try:
            with self._lock:
                project_state = self.get_project_state(project_name)
                rotation_ids = project_state["rotation_ids"]

                if len(rotation_ids) <= keep_count:
                    return 0, True

                # Keep only the most recent rotation IDs
                kept_ids = rotation_ids[-keep_count:]
                removed_count = len(rotation_ids) - keep_count
                project_state["rotation_ids"] = kept_ids

                # Save updated state
                success = self._save_state()
                return removed_count, success

        except Exception as e:
            logger.warning("Error cleaning up project state for %s: %s", project_name, e)
            return 0, False

    def update_global_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Update global rotation settings.

        Args:
            settings: Settings to update

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self._lock:
                self._state["global_settings"].update(settings)
                return self._save_state()

        except Exception as e:
            logger.warning("Error updating global settings: %s", e)
            return False

    def get_global_settings(self) -> Dict[str, Any]:
        """
        Get global rotation settings.

        Returns:
            Global settings dictionary
        """
        with self._lock:
            return self._state["global_settings"].copy()

    def list_tracked_projects(self) -> List[str]:
        """
        List all projects with rotation state.

        Returns:
            List of project names
        """
        with self._lock:
            return list(self._state["projects"].keys())

    def reset_project_state(self, project_name: str) -> bool:
        """
        Reset rotation state for a project.

        Args:
            project_name: Name of the project to reset

        Returns:
            True if reset successful, False otherwise
        """
        try:
            with self._lock:
                if project_name in self._state["projects"]:
                    del self._state["projects"][project_name]
                    return self._save_state()
                return True  # Project didn't exist, success by default

        except Exception as e:
            logger.warning("Error resetting project state for %s: %s", project_name, e)
            return False


# Global state manager instance
_state_manager = None


def get_state_manager(state_dir: str = None) -> RotationStateManager:
    """
    Get global rotation state manager instance.

    Args:
        state_dir: Directory for storing state files

    Returns:
        RotationStateManager instance
    """
    global _state_manager
    if _state_manager is None:
        _state_manager = RotationStateManager(state_dir)
    return _state_manager


# Convenience functions for direct usage
def get_project_state(project_name: str) -> Dict[str, Any]:
    """Get rotation state for a project."""
    return get_state_manager().get_project_state(project_name)


def update_project_state(project_name: str, rotation_metadata: Dict[str, Any]) -> bool:
    """Update project state after rotation."""
    return get_state_manager().update_project_state(project_name, rotation_metadata)


def get_next_sequence_number(project_name: str) -> int:
    """Get next sequence number for project rotation."""
    return get_state_manager().get_next_sequence_number(project_name)


def generate_rotation_id(project_name: str) -> str:
    """Generate unique rotation ID for project."""
    return get_state_manager().generate_rotation_id(project_name)


def get_log_stats(project_name: str, log_type: str) -> Dict[str, Any]:
    """Retrieve cached statistics for a project/log combination."""
    return get_state_manager().get_log_stats(project_name, log_type)


def update_log_stats(
    project_name: str,
    log_type: str,
    *,
    size_bytes: Optional[int] = None,
    line_count: Optional[int] = None,
    ema_bytes_per_line: Optional[float] = None,
    mtime_ns: Optional[int] = None,
    inode: Optional[int] = None,
    source: Optional[str] = None,
    initialized: Optional[bool] = None,
) -> bool:
    """Update cached statistics for a project/log combination."""
    return get_state_manager().update_log_stats(
        project_name,
        log_type,
        size_bytes=size_bytes,
        line_count=line_count,
        ema_bytes_per_line=ema_bytes_per_line,
        mtime_ns=mtime_ns,
        inode=inode,
        source=source,
        initialized=initialized,
    )
