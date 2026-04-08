"""Database change logging and rollback system for document management."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.utils.time import utcnow


@dataclass
class ChangeLogEntry:
    """Represents a change log entry for rollback."""
    id: str
    timestamp: datetime
    operation_type: str  # 'insert', 'update', 'delete'
    table_name: str
    record_id: Optional[str]
    old_data: Optional[Dict[str, Any]]
    new_data: Optional[Dict[str, Any]]
    change_summary: str
    author: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackPlan:
    """Plan for rolling back changes."""
    rollback_id: str
    target_timestamp: datetime
    affected_tables: List[str]
    total_records: int
    estimated_duration: float
    risk_level: str  # 'low', 'medium', 'high'
    changes_to_rollback: List[ChangeLogEntry]
    warnings: List[str] = field(default_factory=list)


class ChangeRollbackManager:
    """Manages database change logging and rollback capabilities."""

    def __init__(
        self,
        storage: StorageBackend,
        project_root: Path,
        enable_auto_logging: bool = True,
        retention_days: int = 30
    ):
        self.storage = storage
        self.project_root = Path(project_root)
        self.enable_auto_logging = enable_auto_logging
        self.retention_days = retention_days

        self._logger = logging.getLogger(__name__)
        self._change_log_cache: List[ChangeLogEntry] = []
        self._rollback_lock = asyncio.Lock()

    async def log_change(
        self,
        operation_type: str,
        table_name: str,
        record_id: Optional[str],
        old_data: Optional[Dict[str, Any]],
        new_data: Optional[Dict[str, Any]],
        change_summary: str,
        author: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a database change for potential rollback."""
        try:
            change_id = self._generate_change_id()
            timestamp = utcnow()

            entry = ChangeLogEntry(
                id=change_id,
                timestamp=timestamp,
                operation_type=operation_type,
                table_name=table_name,
                record_id=record_id,
                old_data=old_data,
                new_data=new_data,
                change_summary=change_summary,
                author=author,
                metadata=metadata or {}
            )

            # Store in database
            await self._store_change_log_entry(entry)

            # Add to cache
            self._change_log_cache.append(entry)

            # Cleanup old entries if cache is too large
            if len(self._change_log_cache) > 1000:
                self._change_log_cache = self._change_log_cache[-500:]

            self._logger.debug(f"Logged change: {operation_type} on {table_name}")
            return change_id

        except Exception as e:
            self._logger.error(f"Failed to log change: {e}")
            return ""

    async def _store_change_log_entry(self, entry: ChangeLogEntry):
        """Store a change log entry in the database."""
        try:
            # Create a change log table if it doesn't exist
            await self._ensure_change_log_table()

            # Store the entry
            await self.storage._execute(
                """
                INSERT INTO change_log
                (id, timestamp, operation_type, table_name, record_id, old_data, new_data,
                 change_summary, author, metadata, project_root)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    entry.id,
                    entry.timestamp.isoformat(),
                    entry.operation_type,
                    entry.table_name,
                    entry.record_id,
                    json.dumps(entry.old_data) if entry.old_data else None,
                    json.dumps(entry.new_data) if entry.new_data else None,
                    entry.change_summary,
                    entry.author,
                    json.dumps(entry.metadata),
                    str(self.project_root)
                ]
            )

        except Exception as e:
            self._logger.error(f"Failed to store change log entry: {e}")

    async def _ensure_change_log_table(self):
        """Ensure the change log table exists."""
        try:
            await self.storage._execute(
                """
                CREATE TABLE IF NOT EXISTS change_log (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    record_id TEXT,
                    old_data TEXT,
                    new_data TEXT,
                    change_summary TEXT NOT NULL,
                    author TEXT NOT NULL,
                    metadata TEXT,
                    project_root TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create indexes for performance
            await self.storage._execute(
                "CREATE INDEX IF NOT EXISTS idx_change_log_timestamp ON change_log(timestamp DESC)"
            )
            await self.storage._execute(
                "CREATE INDEX IF NOT EXISTS idx_change_log_table ON change_log(table_name, timestamp DESC)"
            )
            await self.storage._execute(
                "CREATE INDEX IF NOT EXISTS idx_change_log_project ON change_log(project_root, timestamp DESC)"
            )

        except Exception as e:
            self._logger.error(f"Failed to create change log table: {e}")

    async def create_rollback_plan(
        self,
        target_timestamp: datetime,
        table_filter: Optional[List[str]] = None,
        author_filter: Optional[str] = None
    ) -> Optional[RollbackPlan]:
        """Create a plan for rolling back changes to a specific timestamp."""
        try:
            # Get changes to rollback
            changes = await self._get_changes_for_rollback(
                target_timestamp, table_filter, author_filter
            )

            if not changes:
                self._logger.info("No changes found to rollback")
                return None

            # Analyze the rollback
            affected_tables = list(set(change.table_name for change in changes))
            total_records = len(changes)

            # Estimate duration (rough estimate)
            estimated_duration = total_records * 0.1  # 100ms per record

            # Assess risk level
            risk_level = await self._assess_rollback_risk(changes)

            # Generate warnings
            warnings = await self._generate_rollback_warnings(changes)

            rollback_id = self._generate_change_id()

            plan = RollbackPlan(
                rollback_id=rollback_id,
                target_timestamp=target_timestamp,
                affected_tables=affected_tables,
                total_records=total_records,
                estimated_duration=estimated_duration,
                risk_level=risk_level,
                changes_to_rollback=changes,
                warnings=warnings
            )

            self._logger.info(f"Created rollback plan: {rollback_id} with {total_records} changes")
            return plan

        except Exception as e:
            self._logger.error(f"Failed to create rollback plan: {e}")
            return None

    async def _get_changes_for_rollback(
        self,
        target_timestamp: datetime,
        table_filter: Optional[List[str]],
        author_filter: Optional[str]
    ) -> List[ChangeLogEntry]:
        """Get changes that need to be rolled back."""
        try:
            query = """
                SELECT id, timestamp, operation_type, table_name, record_id, old_data, new_data,
                       change_summary, author, metadata
                FROM change_log
                WHERE project_root = ? AND timestamp > ?
            """
            params = [str(self.project_root), target_timestamp.isoformat()]

            if table_filter:
                placeholders = ", ".join("?" for _ in table_filter)
                query += f" AND table_name IN ({placeholders})"
                params.extend(table_filter)

            if author_filter:
                query += " AND author = ?"
                params.append(author_filter)

            query += " ORDER BY timestamp DESC"  # Reverse order for proper rollback

            rows = await self.storage._fetchall(query, tuple(params))

            changes = []
            for row in rows:
                entry = ChangeLogEntry(
                    id=row['id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    operation_type=row['operation_type'],
                    table_name=row['table_name'],
                    record_id=row['record_id'],
                    old_data=json.loads(row['old_data']) if row['old_data'] else None,
                    new_data=json.loads(row['new_data']) if row['new_data'] else None,
                    change_summary=row['change_summary'],
                    author=row['author'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                )
                changes.append(entry)

            return changes

        except Exception as e:
            self._logger.error(f"Failed to get changes for rollback: {e}")
            return []

    async def _assess_rollback_risk(self, changes: List[ChangeLogEntry]) -> str:
        """Assess the risk level of a rollback operation."""
        try:
            # Count different operation types
            operations = [change.operation_type for change in changes]
            delete_count = operations.count('delete')
            update_count = operations.count('update')

            # Check for critical tables
            critical_tables = ['scribe_projects', 'scribe_entries']
            critical_changes = sum(1 for change in changes if change.table_name in critical_tables)

            # Calculate risk score
            risk_score = 0
            risk_score += delete_count * 2  # Deletes are riskier
            risk_score += update_count * 1  # Updates are moderately risky
            risk_score += critical_changes * 3  # Critical table changes are very risky

            # Determine risk level
            if risk_score >= 10 or critical_changes > 0:
                return "high"
            elif risk_score >= 5:
                return "medium"
            else:
                return "low"

        except Exception as e:
            self._logger.error(f"Failed to assess rollback risk: {e}")
            return "medium"  # Default to medium risk

    async def _generate_rollback_warnings(self, changes: List[ChangeLogEntry]) -> List[str]:
        """Generate warnings for the rollback operation."""
        warnings = []

        try:
            # Check for irreversible operations
            delete_count = sum(1 for change in changes if change.operation_type == 'delete')
            if delete_count > 0:
                warnings.append(f"Will delete {delete_count} records that were added")

            # Check for conflicts
            record_changes = {}
            for change in changes:
                key = f"{change.table_name}:{change.record_id}"
                if key not in record_changes:
                    record_changes[key] = []
                record_changes[key].append(change)

            conflicts = [key for key, changes in record_changes.items() if len(changes) > 1]
            if conflicts:
                warnings.append(f"Found {len(conflicts)} records with multiple changes that may conflict")

            # Check for data loss
            for change in changes:
                if change.operation_type == 'update' and change.new_data and not change.old_data:
                    warnings.append(f"Update on {change.table_name} may result in data loss")

        except Exception as e:
            self._logger.error(f"Failed to generate rollback warnings: {e}")
            warnings.append("Unable to fully analyze rollback risks")

        return warnings

    async def execute_rollback(
        self,
        rollback_plan: RollbackPlan,
        confirm: bool = False,
        author: str = "rollback_system"
    ) -> Tuple[bool, str]:
        """Execute a rollback plan."""
        if not confirm:
            return False, "Rollback not confirmed"

        async with self._rollback_lock:
            try:
                self._logger.info(f"Executing rollback {rollback_plan.rollback_id}")

                # Create a backup point before rollback
                backup_id = await self.create_backup_point("pre_rollback")

                success_count = 0
                error_count = 0
                errors = []

                # Execute changes in reverse chronological order
                for change in rollback_plan.changes_to_rollback:
                    try:
                        success = await self._execute_rollback_change(change, author)
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                            errors.append(f"Failed to rollback change {change.id}")
                    except Exception as e:
                        error_count += 1
                        errors.append(f"Error rolling back change {change.id}: {e}")

                # Log the rollback operation
                result_summary = f"Rollback completed: {success_count} successful, {error_count} failed"
                if errors:
                    result_summary += f". Errors: {'; '.join(errors[:3])}"  # Limit error details

                await self.log_change(
                    operation_type="rollback",
                    table_name="change_log",
                    record_id=rollback_plan.rollback_id,
                    old_data=None,
                    new_data={
                        'rollback_id': rollback_plan.rollback_id,
                        'target_timestamp': rollback_plan.target_timestamp.isoformat(),
                        'total_changes': rollback_plan.total_records,
                        'success_count': success_count,
                        'error_count': error_count,
                        'backup_id': backup_id
                    },
                    change_summary=result_summary,
                    author=author
                )

                if error_count == 0:
                    self._logger.info(f"Rollback {rollback_plan.rollback_id} completed successfully")
                    return True, result_summary
                else:
                    self._logger.warning(f"Rollback {rollback_plan.rollback_id} completed with errors")
                    return False, result_summary

            except Exception as e:
                self._logger.error(f"Rollback {rollback_plan.rollback_id} failed: {e}")
                return False, f"Rollback failed: {e}"

    async def _execute_rollback_change(self, change: ChangeLogEntry, author: str) -> bool:
        """Execute a single rollback change."""
        try:
            if change.operation_type == 'insert':
                # Rollback insert by deleting the record
                if change.record_id:
                    await self.storage._execute(
                        f"DELETE FROM {change.table_name} WHERE id = ?",
                        (change.record_id,)
                    )

            elif change.operation_type == 'update':
                # Rollback update by restoring old data
                if change.old_data and change.record_id:
                    set_clause = ", ".join(f"{key} = ?" for key in change.old_data.keys())
                    values = list(change.old_data.values()) + [change.record_id]

                    await self.storage._execute(
                        f"UPDATE {change.table_name} SET {set_clause} WHERE id = ?",
                        values
                    )

            elif change.operation_type == 'delete':
                # Rollback delete by restoring the record
                if change.old_data:
                    columns = list(change.old_data.keys())
                    placeholders = ", ".join("?" for _ in columns)
                    values = list(change.old_data.values())

                    await self.storage._execute(
                        f"INSERT INTO {change.table_name} ({', '.join(columns)}) VALUES ({placeholders})",
                        values
                    )

            return True

        except Exception as e:
            self._logger.error(f"Failed to execute rollback change {change.id}: {e}")
            return False

    async def create_backup_point(self, name: str) -> str:
        """Create a backup point for the current state."""
        try:
            backup_id = self._generate_change_id()
            timestamp = utcnow()

            # Store backup point metadata
            await self.storage._execute(
                """
                INSERT INTO backup_points
                (id, name, timestamp, project_root, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    backup_id,
                    name,
                    timestamp.isoformat(),
                    str(self.project_root),
                    json.dumps({'created_by': 'backup_system'})
                ]
            )

            self._logger.info(f"Created backup point: {backup_id} ({name})")
            return backup_id

        except Exception as e:
            self._logger.error(f"Failed to create backup point: {e}")
            return ""

    async def restore_from_backup(self, backup_id: str, confirm: bool = False) -> Tuple[bool, str]:
        """Restore database state from a backup point."""
        # This is a complex operation that would require full database backups
        # For now, we'll implement a basic version using the change log
        if not confirm:
            return False, "Restore not confirmed"

        try:
            # Get backup point info
            result = await self.storage._fetchone(
                """
                SELECT timestamp FROM backup_points
                WHERE id = ? AND project_root = ?
                """,
                (backup_id, str(self.project_root))
            )

            if not result:
                return False, "Backup point not found"

            backup_timestamp = datetime.fromisoformat(result['timestamp'])

            # Create rollback plan to restore to backup timestamp
            rollback_plan = await self.create_rollback_plan(backup_timestamp)
            if not rollback_plan:
                return False, "Failed to create rollback plan for backup restore"

            # Execute the rollback
            return await self.execute_rollback(rollback_plan, confirm=True, author="backup_restore")

        except Exception as e:
            self._logger.error(f"Failed to restore from backup {backup_id}: {e}")
            return False, f"Backup restore failed: {e}"

    async def get_change_history(
        self,
        limit: int = 100,
        table_filter: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[ChangeLogEntry]:
        """Get change history with optional filters."""
        try:
            query = """
                SELECT id, timestamp, operation_type, table_name, record_id, old_data, new_data,
                       change_summary, author, metadata
                FROM change_log
                WHERE project_root = ?
            """
            params = [str(self.project_root)]

            if table_filter:
                query += " AND table_name = ?"
                params.append(table_filter)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time.isoformat())

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time.isoformat())

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = await self.storage._fetchall(query, tuple(params))

            changes = []
            for row in rows:
                entry = ChangeLogEntry(
                    id=row['id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    operation_type=row['operation_type'],
                    table_name=row['table_name'],
                    record_id=row['record_id'],
                    old_data=json.loads(row['old_data']) if row['old_data'] else None,
                    new_data=json.loads(row['new_data']) if row['new_data'] else None,
                    change_summary=row['change_summary'],
                    author=row['author'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                )
                changes.append(entry)

            return changes

        except Exception as e:
            self._logger.error(f"Failed to get change history: {e}")
            return []

    async def cleanup_old_changes(self):
        """Clean up old change log entries based on retention policy."""
        try:
            cutoff_date = utcnow() - timedelta(days=self.retention_days)

            # Delete old change log entries
            result = await self.storage._execute(
                "DELETE FROM change_log WHERE timestamp < ? AND project_root = ?",
                (cutoff_date.isoformat(), str(self.project_root))
            )

            # Delete old backup points
            await self.storage._execute(
                "DELETE FROM backup_points WHERE timestamp < ? AND project_root = ?",
                (cutoff_date.isoformat(), str(self.project_root))
            )

            self._logger.info(f"Cleaned up changes older than {cutoff_date.isoformat()}")

        except Exception as e:
            self._logger.error(f"Failed to cleanup old changes: {e}")

    def _generate_change_id(self) -> str:
        """Generate a unique change ID."""
        import hashlib
        import time
        content = f"change_{time.time()}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]

    async def get_backup_points(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get available backup points."""
        try:
            # Ensure backup_points table exists
            await self.storage._execute(
                """
                CREATE TABLE IF NOT EXISTS backup_points (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            rows = await self.storage._fetchall(
                """
                SELECT id, name, timestamp, metadata, created_at
                FROM backup_points
                WHERE project_root = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (str(self.project_root), limit)
            )

            backups = []
            for row in rows:
                backups.append({
                    'id': row['id'],
                    'name': row['name'],
                    'timestamp': row['timestamp'],
                    'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                    'created_at': row['created_at']
                })

            return backups

        except Exception as e:
            self._logger.error(f"Failed to get backup points: {e}")
            return []