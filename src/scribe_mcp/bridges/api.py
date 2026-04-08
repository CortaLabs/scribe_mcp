"""API for bridges to call Scribe operations."""

from typing import Dict, List, Any, Optional
import logging
from datetime import datetime, timezone
import uuid
import hashlib

logger = logging.getLogger(__name__)


class BridgeToScribeAPI:
    """
    API interface for bridge→Scribe calls.

    All operations enforce permissions via BridgePolicyPlugin
    and inject bridge metadata automatically.
    """

    def __init__(self, bridge_id: str, manifest, storage_backend, policy):
        self.bridge_id = bridge_id
        self.manifest = manifest
        self._storage = storage_backend
        self._policy = policy

    async def append_entry(
        self,
        project_name: str,
        message: str,
        status: str = "info",
        agent: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        log_type: str = "progress"
    ) -> Dict[str, Any]:
        """
        Append entry to Scribe log on behalf of bridge.

        Enforces permissions and injects bridge metadata.

        Args:
            project_name: Target project
            message: Log message
            status: Entry status (info, success, warn, error, bug, plan)
            agent: Agent name (defaults to bridge:<bridge_id>)
            meta: Additional metadata
            log_type: Log type (progress, doc_updates, bugs, etc.)

        Returns:
            Dict with ok=True, entry_id, timestamp

        Raises:
            PermissionError: If bridge lacks permission
        """
        # Check permission
        if not await self._policy.can_append_to_project(project_name, log_type):
            raise PermissionError(
                f"Bridge {self.bridge_id} cannot append to {project_name}/{log_type}"
            )

        # Inject bridge metadata
        meta = meta or {}
        meta["source_bridge_id"] = self.bridge_id
        meta["bridge_version"] = self.manifest.version

        # Map status to emoji
        emoji_map = {
            "info": "ℹ️",
            "success": "✅",
            "warn": "⚠️",
            "error": "❌",
            "bug": "🐞",
            "plan": "📋"
        }
        emoji = emoji_map.get(status, "ℹ️")

        # Fetch project record
        project = await self._storage.fetch_project(project_name)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")

        # Generate entry ID and timestamp
        entry_id = str(uuid.uuid4())[:8]
        ts = datetime.now(timezone.utc)
        timestamp_str = ts.isoformat()
        agent_name = agent or f"bridge:{self.bridge_id}"

        # Create raw line and compute hash
        raw_line = f"{timestamp_str} | {agent_name} | {message}"
        sha256_hash = hashlib.sha256(raw_line.encode()).hexdigest()

        # Insert entry via storage backend
        await self._storage.insert_entry(
            entry_id=entry_id,
            project=project,
            ts=ts,
            emoji=emoji,
            agent=agent_name,
            message=message,
            meta=meta,
            raw_line=raw_line,
            sha256=sha256_hash
        )

        logger.info(f"Bridge {self.bridge_id} appended entry to {project_name}: {message[:50]}")

        return {
            "ok": True,
            "entry_id": entry_id,
            "timestamp": timestamp_str
        }

    async def query_entries(
        self,
        project_name: str,
        limit: int = 50,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Query entries from Scribe log.

        Args:
            project_name: Target project
            limit: Maximum entries to return
            **filters: Additional query filters

        Returns:
            List of log entries

        Raises:
            PermissionError: If bridge lacks permission
        """
        if not await self._policy.can_read_project(project_name):
            raise PermissionError(
                f"Bridge {self.bridge_id} cannot read from {project_name}"
            )

        entries = await self._storage.fetch_recent_entries(project_name, limit, filters)
        logger.info(f"Bridge {self.bridge_id} queried {len(entries)} entries from {project_name}")

        return entries

    async def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new Scribe project on behalf of bridge.

        Args:
            name: Project name
            description: Project description
            tags: Project tags
            meta: Additional metadata

        Returns:
            Dict with ok=True, project_name, tags

        Raises:
            PermissionError: If bridge lacks permission
        """
        if not self._policy.can_create_projects():
            raise PermissionError(
                f"Bridge {self.bridge_id} cannot create projects"
            )

        # Apply prefix if configured
        prefix = self.manifest.project_config.project_prefix
        original_name = name
        full_name = f"{prefix}{name}" if prefix else name

        # Add auto-tags
        all_tags = list(tags or [])
        all_tags.extend(self.manifest.project_config.auto_tag)
        all_tags.append(f"bridge:{self.bridge_id}")

        # Inject bridge metadata
        project_meta = dict(meta or {})
        project_meta.update(self.manifest.project_config.default_metadata)
        project_meta["managed_by_bridge"] = self.bridge_id
        project_meta["bridge_version"] = self.manifest.version

        # Create via storage with bridge ownership
        await self._storage.upsert_project(
            name=full_name,
            repo_root=".",
            progress_log_path=f".scribe/docs/dev_plans/{full_name}/PROGRESS_LOG.md",
            docs_json=None,
            bridge_id=self.bridge_id,
            bridge_managed=True
        )

        logger.info(f"Bridge {self.bridge_id} created project: {full_name}")

        return {
            "ok": True,
            "project_name": full_name,
            "original_name": original_name,
            "tags": all_tags,
            "bridge_managed": True,
            "bridge_id": self.bridge_id
        }
