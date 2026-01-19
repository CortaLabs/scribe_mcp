"""Bidirectional sync manager for coordinating file system and database synchronization."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.utils.time import utcnow
from scribe_mcp.doc_management.file_watcher import FileChangeEvent, FileSystemWatcher


class ConflictResolution(Enum):
    """Strategies for resolving sync conflicts."""
    FILE_WINS = "file_wins"          # File system is authoritative
    DATABASE_WINS = "database_wins"  # Database is authoritative
    LATEST_WINS = "latest_wins"      # Most recent timestamp wins
    MANUAL = "manual"                # Require manual resolution


@dataclass
class SyncConflict:
    """Represents a synchronization conflict."""
    file_path: Path
    conflict_type: str  # 'content', 'timestamp', 'deleted'
    file_timestamp: float
    database_timestamp: float
    file_content: Optional[str] = None
    database_content: Optional[str] = None
    resolution: Optional[ConflictResolution] = None
    resolved_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncOperation:
    """Represents a synchronization operation."""
    operation_type: str  # 'sync_to_db', 'sync_to_file', 'resolve_conflict'
    file_path: Path
    timestamp: float = field(default_factory=time.time)
    success: bool = False
    error_message: Optional[str] = None
    checksum_before: Optional[str] = None
    checksum_after: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SyncManager:
    """Manages bidirectional synchronization between file system and database."""

    def __init__(
        self,
        storage: StorageBackend,
        project_root: Path,
        conflict_resolution: ConflictResolution = ConflictResolution.LATEST_WINS,
        sync_interval: float = 5.0,
        enable_watcher: bool = True
    ):
        self.storage = storage
        self.project_root = Path(project_root)
        self.conflict_resolution = conflict_resolution
        self.sync_interval = sync_interval
        self.enable_watcher = enable_watcher

        self._logger = logging.getLogger(__name__)
        self._is_running = False
        self._watcher: Optional[FileSystemWatcher] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._pending_syncs: Dict[str, asyncio.Event] = {}
        self._sync_lock = asyncio.Lock()

        # Performance tracking
        self._sync_stats = {
            'operations_total': 0,
            'operations_successful': 0,
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'average_sync_time': 0.0,
            'last_sync_time': None
        }

    async def start(self) -> bool:
        """Start the sync manager."""
        if self._is_running:
            self._logger.warning("Sync manager is already running")
            return True

        try:
            # Start file watcher if enabled
            if self.enable_watcher:
                success = await self._start_file_watcher()
                if not success:
                    self._logger.warning("Failed to start file watcher, continuing without it")

            # Start periodic sync task
            self._sync_task = asyncio.create_task(self._sync_loop())

            self._is_running = True
            self._logger.info(f"Sync manager started for {self.project_root}")
            self._logger.info(f"Conflict resolution strategy: {self.conflict_resolution.value}")

            return True

        except Exception as e:
            self._logger.error(f"Failed to start sync manager: {e}")
            return False

    async def stop(self):
        """Stop the sync manager."""
        if not self._is_running:
            return

        self._is_running = False

        # Stop file watcher
        if self._watcher:
            await self._watcher.stop()
            self._watcher = None

        # Stop sync task
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        self._logger.info("Sync manager stopped")

    async def _start_file_watcher(self) -> bool:
        """Start the file system watcher."""
        try:
            self._watcher = FileSystemWatcher(
                project_root=self.project_root,
                change_callback=self._handle_file_change,
                debounce_seconds=1.0
            )

            return await self._watcher.start()

        except Exception as e:
            self._logger.error(f"Failed to start file watcher: {e}")
            return False

    def _handle_file_change(self, change_event: FileChangeEvent):
        """Handle file system change events."""
        try:
            self._logger.debug(f"File change detected: {change_event.file_path} ({change_event.event_type})")

            # Trigger sync for the changed file
            file_path_str = str(change_event.file_path)
            if file_path_str not in self._pending_syncs:
                self._pending_syncs[file_path_str] = asyncio.Event()

            # Signal that sync is needed
            self._pending_syncs[file_path_str].set()

        except Exception as e:
            self._logger.error(f"Error handling file change: {e}")

    async def _sync_loop(self):
        """Main sync loop."""
        while self._is_running:
            try:
                await self._process_pending_syncs()
                await asyncio.sleep(self.sync_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in sync loop: {e}")
                await asyncio.sleep(self.sync_interval)

    async def _process_pending_syncs(self):
        """Process all pending sync operations."""
        if not self._pending_syncs:
            return

        async with self._sync_lock:
            # Snapshot keys to avoid mutating while iterating
            for file_path_str, event in list(self._pending_syncs.items()):
                if not event.is_set():
                    continue
                event.clear()
                self._pending_syncs.pop(file_path_str, None)
                await self._sync_file(Path(file_path_str))

    async def _sync_file(self, file_path: Path) -> SyncOperation:
        """Sync a specific file between file system and database."""
        start_time = time.time()

        operation = SyncOperation(
            operation_type='sync_to_db',
            file_path=file_path,
            metadata={'start_time': start_time}
        )

        try:
            # Check if file exists and is a document we should track
            if not file_path.exists() or not file_path.is_file():
                self._logger.debug(f"Skipping non-existent or non-file: {file_path}")
                operation.success = True
                return operation

            # Check file extension
            if file_path.suffix.lower() not in ['.md', '.txt', '.json']:
                self._logger.debug(f"Skipping non-document file: {file_path}")
                operation.success = True
                return operation

            # Read current file content off the loop
            file_content = await asyncio.to_thread(file_path.read_text, encoding='utf-8')

            # Calculate checksum off the loop
            file_checksum = await asyncio.to_thread(self._calculate_checksum, file_content)
            operation.checksum_before = file_checksum

            # Get database state for this file
            db_state = await self._get_database_state(file_path)

            # Check for conflicts
            conflict = await self._detect_conflict(file_path, file_content, db_state)

            if conflict:
                operation.operation_type = 'resolve_conflict'
                self._sync_stats['conflicts_detected'] += 1

                resolved_content = await self._resolve_conflict(conflict)
                if resolved_content is not None:
                    # Update database with resolved content
                    await self._update_database_record(file_path, resolved_content)
                    operation.success = True
                    operation.checksum_after = self._calculate_checksum(resolved_content)
                    self._sync_stats['conflicts_resolved'] += 1
                else:
                    operation.success = False
                    operation.error_message = "Failed to resolve conflict"
            else:
                # No conflict, sync to database
                await self._update_database_record(file_path, file_content)
                operation.success = True
                operation.checksum_after = file_checksum

        except Exception as e:
            self._logger.error(f"Error syncing file {file_path}: {e}")
            operation.success = False
            operation.error_message = str(e)

        # Update statistics
        self._update_sync_stats(operation, time.time() - start_time)

        return operation

    async def _get_database_state(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get the current database state for a file."""
        try:
            # Try to get from sync_status table first
            query = """
                SELECT last_file_hash, last_db_hash, last_sync_at, sync_status
                FROM sync_status
                WHERE file_path = ? AND project_root = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """

            # Use the existing query method from storage backend
            results = await self.storage._fetchall(query, (str(file_path), str(self.project_root)))

            if results:
                row = results[0]
                return {
                    'file_hash': row['last_file_hash'],
                    'db_hash': row['last_db_hash'],
                    'last_sync': row['last_sync_at'],
                    'sync_status': row['sync_status']
                }

            # If no sync status, try document_sections
            query = """
                SELECT content, updated_at, file_hash
                FROM document_sections
                WHERE file_path = ? AND project_root = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """

            results = await self.storage._fetchall(query, (str(file_path), str(self.project_root)))

            if results:
                row = results[0]
                return {
                    'content': row['content'],
                    'timestamp': row['updated_at'],
                    'checksum': row['file_hash']
                }

        except Exception as e:
            self._logger.debug(f"Error getting database state for {file_path}: {e}")

        return None

    async def _detect_conflict(
        self,
        file_path: Path,
        file_content: str,
        db_state: Optional[Dict[str, Any]]
    ) -> Optional[SyncConflict]:
        """Detect if there's a conflict between file and database."""

        if not db_state:
            # No database record, no conflict
            return None

        file_timestamp = file_path.stat().st_mtime
        db_timestamp_raw = db_state.get('timestamp', db_state.get('last_sync', 0))
        db_timestamp = self._to_epoch(db_timestamp_raw)

        # Calculate checksums
        file_checksum = self._calculate_checksum(file_content)
        db_checksum = db_state.get('checksum', db_state.get('file_hash', ''))

        # Check for conflict
        content_differs = file_content != db_state.get('content', '')
        timestamp_differs = abs(file_timestamp - db_timestamp) > 1.0  # 1 second tolerance
        checksum_differs = file_checksum != db_checksum

        if content_differs and timestamp_differs:
            # We have a conflict
            return SyncConflict(
                file_path=file_path,
                conflict_type='content',
                file_timestamp=file_timestamp,
                database_timestamp=db_timestamp,
                file_content=file_content,
                database_content=db_state.get('content'),
                metadata={
                    'file_checksum': file_checksum,
                    'database_checksum': db_checksum,
                    'time_difference': file_timestamp - db_timestamp
                }
            )

        return None

    def _to_epoch(self, ts: Any) -> float:
        """Convert iso/datetime/float int to epoch seconds."""
        if ts is None:
            return 0.0
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, datetime):
            return ts.timestamp()
        # assume ISO string
        try:
            return datetime.fromisoformat(str(ts)).timestamp()
        except Exception:
            return 0.0

    async def _resolve_conflict(self, conflict: SyncConflict) -> Optional[str]:
        """Resolve a sync conflict based on the configured strategy."""

        self._logger.warning(f"Resolving conflict for {conflict.file_path}: {conflict.conflict_type}")

        if self.conflict_resolution == ConflictResolution.FILE_WINS:
            conflict.resolution = ConflictResolution.FILE_WINS
            return conflict.file_content

        elif self.conflict_resolution == ConflictResolution.DATABASE_WINS:
            conflict.resolution = ConflictResolution.DATABASE_WINS
            return conflict.database_content

        elif self.conflict_resolution == ConflictResolution.LATEST_WINS:
            if conflict.file_timestamp > conflict.database_timestamp:
                conflict.resolution = ConflictResolution.FILE_WINS
                return conflict.file_content
            else:
                conflict.resolution = ConflictResolution.DATABASE_WINS
                return conflict.database_content

        elif self.conflict_resolution == ConflictResolution.MANUAL:
            # For manual resolution, we'll log the conflict and require external intervention
            self._logger.error(
                f"Manual conflict resolution required for {conflict.file_path}. "
                f"File timestamp: {conflict.file_timestamp}, "
                f"Database timestamp: {conflict.database_timestamp}"
            )
            # For now, prefer the file content but mark for manual review
            conflict.resolution = ConflictResolution.FILE_WINS
            conflict.metadata['manual_review_required'] = True
            return conflict.file_content

        return None

    async def _update_database_record(self, file_path: Path, content: str):
        """Update the database record for a file."""
        try:
            now = utcnow()
            checksum = self._calculate_checksum(content)
            relative_path = str(file_path.relative_to(self.project_root))

            # Update document_sections table
            await self.storage._execute(
                """
                INSERT OR REPLACE INTO document_sections
                (project_root, file_path, relative_path, content, file_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [str(self.project_root), str(file_path), relative_path, content, checksum, now, now]
            )

            # Update sync_status table
            await self.storage._execute(
                """
                INSERT OR REPLACE INTO sync_status
                (project_root, file_path, last_sync_at, last_file_hash, last_db_hash, sync_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [str(self.project_root), str(file_path), now, checksum, checksum, 'synced', now]
            )

        except Exception as e:
            self._logger.error(f"Error updating database record for {file_path}: {e}")
            raise

    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA-256 checksum of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _update_sync_stats(self, operation: SyncOperation, duration: float):
        """Update synchronization statistics."""
        self._sync_stats['operations_total'] += 1

        if operation.success:
            self._sync_stats['operations_successful'] += 1

        # Update average sync time
        total_time = self._sync_stats['average_sync_time'] * (self._sync_stats['operations_total'] - 1) + duration
        self._sync_stats['average_sync_time'] = total_time / self._sync_stats['operations_total']
        self._sync_stats['last_sync_time'] = time.time()

    async def sync_all_files(self) -> List[SyncOperation]:
        """Manually trigger sync for all tracked files."""
        operations = []

        # Find all document files
        for pattern in ['**/*.md', '**/*.txt', '**/*.json']:
            for file_path in await asyncio.to_thread(lambda: list(self.project_root.glob(pattern))):
                if file_path.is_file():
                    operation = await self._sync_file(file_path)
                    operations.append(operation)

        self._logger.info(f"Synced {len(operations)} files")
        return operations

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics."""
        return {
            'is_running': self._is_running,
            'watcher_method': self._watcher.get_method() if self._watcher else 'disabled',
            'sync_interval': self.sync_interval,
            'conflict_resolution': self.conflict_resolution.value,
            'pending_syncs': len(self._pending_syncs),
            'statistics': self._sync_stats.copy(),
            'last_sync': self._sync_stats.get('last_sync_time')
        }

    async def force_conflict_resolution(
        self,
        file_path: Path,
        resolution: ConflictResolution,
        preferred_content: Optional[str] = None
    ) -> bool:
        """Manually resolve a conflict for a specific file."""
        try:
            # Get current states
            file_content = None
            if file_path.exists():
                file_content = await asyncio.to_thread(file_path.read_text, encoding='utf-8')

            db_state = await self._get_database_state(file_path)

            # Create and resolve conflict
            conflict = SyncConflict(
                file_path=file_path,
                conflict_type='manual',
                file_timestamp=(file_path.stat().st_mtime if file_path.exists() else 0),
                database_timestamp=(self._to_epoch(db_state.get('timestamp', 0)) if db_state else 0),
                file_content=file_content,
                database_content=db_state.get('content') if db_state else None
            )

            # Apply resolution
            if resolution == ConflictResolution.FILE_WINS:
                resolved_content = file_content
            elif resolution == ConflictResolution.DATABASE_WINS:
                resolved_content = db_state.get('content') if db_state else None
            elif resolution == ConflictResolution.MANUAL and preferred_content:
                resolved_content = preferred_content
            else:
                resolved_content = file_content  # Default fallback

            if resolved_content is not None:
                await self._update_database_record(file_path, resolved_content)

                # Update file if database content was chosen
                if resolution == ConflictResolution.DATABASE_WINS and db_state:
                    await asyncio.to_thread(file_path.write_text, db_state.get('content', ''), 'utf-8')

                self._logger.info(f"Manually resolved conflict for {file_path} using {resolution.value}")
                return True

        except Exception as e:
            self._logger.error(f"Error manually resolving conflict for {file_path}: {e}")

        return False