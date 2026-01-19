"""SQLite storage backend (default)."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.models import (
    ProjectRecord, DevPlanRecord, PhaseRecord, MilestoneRecord,
    BenchmarkRecord, ChecklistRecord, PerformanceMetricsRecord,
    DocumentSectionRecord, CustomTemplateRecord, DocumentChangeRecord, SyncStatusRecord
)
from scribe_mcp.utils.time import format_utc, utcnow
from scribe_mcp.utils.search import message_matches
from scribe_mcp.utils.slug import normalize_project_input

SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 5000

# Performance monitoring configuration (Stage 6)
SLOW_QUERY_THRESHOLD_MS = 5.0  # Log warnings for queries slower than 5ms
logger = logging.getLogger(__name__)


class SQLiteStorage(StorageBackend):
    """SQLite-backed persistence with lazy connections."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path).expanduser()
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._initialised = False

    async def setup(self) -> None:
        await self._initialise()

    async def close(self) -> None:  # pragma: no cover - nothing persistent to close
        # Connections are short-lived; nothing to do.
        return None

    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
        docs_json: Optional[str] = None,
        bridge_id: Optional[str] = None,
        bridge_managed: bool = False,
    ) -> ProjectRecord:
        await self._initialise()
        async with self._write_lock:
            await self._execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name)
            DO UPDATE SET repo_root = excluded.repo_root,
                          progress_log_path = excluded.progress_log_path,
                          docs_json = excluded.docs_json,
                          bridge_id = excluded.bridge_id,
                          bridge_managed = excluded.bridge_managed;
            """,
            (name, repo_root, progress_log_path, docs_json, bridge_id, 1 if bridge_managed else 0),
        )
        row = await self._fetchone(
            """
            SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE name = ?;
            """,
            (name,),
        )
        return ProjectRecord(
            id=row["id"],
            name=row["name"],
            repo_root=row["repo_root"],
            progress_log_path=row["progress_log_path"],
            docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
            bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
            bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
        )

    async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
        await self._initialise()
        # Try exact match first
        row = await self._fetchone(
            """
            SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE name = ?;
            """,
            (name,),
        )

        # If not found, try canonical match (flexible lookup for existing projects)
        if not row:
            canonical = normalize_project_input(name)
            if canonical and canonical != name:
                row = await self._fetchone(
                    """
                    SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = ?;
                    """,
                    (canonical,),
                )

        if not row:
            return None
        return ProjectRecord(
            id=row["id"],
            name=row["name"],
            repo_root=row["repo_root"],
            progress_log_path=row["progress_log_path"],
            docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
            bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
            bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
        )

    def fetch_project_sync(self, name: str) -> Optional[ProjectRecord]:
        """Synchronous version of fetch_project for use in finalize_tool_response.

        This method is designed for tool logging where we need to resolve the
        project's repo_root but can't use async/await. Uses synchronous sqlite3.

        Args:
            name: Project name to fetch

        Returns:
            ProjectRecord if found, None otherwise

        Thread Safety:
            Uses synchronous sqlite3 connection with WAL mode for safe concurrent access.
        """
        try:
            import sqlite3
            conn = sqlite3.connect(str(self._path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")

            # Try exact match first
            cursor = conn.execute(
                """
                SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE name = ?;
                """,
                (name,),
            )
            row = cursor.fetchone()

            # If not found, try canonical match (flexible lookup for existing projects)
            if not row:
                canonical = normalize_project_input(name)
                if canonical and canonical != name:
                    cursor = conn.execute(
                        """
                        SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                        FROM scribe_projects
                        WHERE name = ?;
                        """,
                        (canonical,),
                    )
                    row = cursor.fetchone()

            conn.close()

            if not row:
                return None
            return ProjectRecord(
                id=row["id"],
                name=row["name"],
                repo_root=row["repo_root"],
                progress_log_path=row["progress_log_path"],
                docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
                bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
                bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
            )
        except Exception:
            return None

    async def list_projects(self) -> List[ProjectRecord]:
        await self._initialise()
        rows = await self._fetchall(
            """
            SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            ORDER BY name;
            """
        )
        records: List[ProjectRecord] = []
        for row in rows:
            records.append(
                ProjectRecord(
                    id=row["id"],
                    name=row["name"],
                    repo_root=row["repo_root"],
                    progress_log_path=row["progress_log_path"],
                    docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
                    bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
                    bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
                )
            )
        return records

    async def list_projects_by_repo(self, repo_root: str) -> List[ProjectRecord]:
        """Return projects scoped to a specific repository root.

        Args:
            repo_root: Absolute path to repository root (will be normalized)

        Returns:
            List of projects whose repo_root matches the given path.
        """
        await self._initialise()
        # Normalize the path for consistent matching
        from pathlib import Path
        normalized_root = str(Path(repo_root).resolve())

        rows = await self._fetchall(
            """
            SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE repo_root = ?
            ORDER BY name;
            """,
            (normalized_root,),
        )
        records: List[ProjectRecord] = []
        for row in rows:
            records.append(
                ProjectRecord(
                    id=row["id"],
                    name=row["name"],
                    repo_root=row["repo_root"],
                    progress_log_path=row["progress_log_path"],
                    docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
                    bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
                    bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
                )
            )
        return records

    async def delete_project(self, name: str) -> bool:
        """Delete a project and all associated data with proper cascade handling."""
        await self._initialise()

        # First check if project exists
        project = await self.fetch_project(name)
        if not project:
            return False

        async with self._write_lock:
            # Delete project and all related data using proper cascade order
            # SQLite foreign key constraints should handle most of this automatically,
            # but we'll be explicit for safety and clarity

            # Delete agent project associations
            await self._execute(
                "DELETE FROM agent_projects WHERE project_name = ?;",
                (name,),
            )

            # Delete global log entries for this project (if they exist)
            # Note: global_log_entries uses project_id, but table is currently empty
            # await self._execute(
            #     "DELETE FROM global_log_entries WHERE project_id = ?;",
            #     (name,),
            # )

            # Due to foreign key constraints with ON DELETE CASCADE,
            # deleting the project should automatically clean up:
            # - scribe_entries
            # - dev_plans -> phases -> milestones
            # - benchmarks, checklists, performance_metrics
            # - documents -> document_sections, document_changes
            # - custom_templates, sync_status
            # - scribe_metrics

            # Delete the main project record (this will cascade to related tables)
            await self._execute(
                "DELETE FROM scribe_projects WHERE name = ?;",
                (name,),
            )

            # Verify deletion
            remaining = await self._fetchone(
                "SELECT COUNT(*) as count FROM scribe_projects WHERE name = ?;",
                (name,),
            )

            return remaining["count"] == 0

    async def update_project_docs(self, name: str, docs_json: str) -> bool:
        """Update only the docs_json field for a project."""
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
                (docs_json, name),
            )
        return True

    async def insert_entry(
        self,
        *,
        entry_id: str,
        project: ProjectRecord,
        ts: datetime,
        emoji: str,
        agent: Optional[str],
        message: str,
        meta: Optional[Dict[str, Any]],
        raw_line: str,
        sha256: str,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        confidence: Optional[float] = None,
        log_type: Optional[str] = None,
    ) -> None:
        await self._initialise()
        ts_iso = ts.isoformat()
        meta_json = json.dumps(meta or {}, sort_keys=True)
        # Extract new fields from meta if not explicitly provided
        if priority is None and meta:
            priority = meta.get("priority", "medium")
        elif priority is None:
            priority = "medium"
        if category is None and meta:
            category = meta.get("category")
        if tags is None and meta:
            tags = meta.get("tags")
        if confidence is None and meta:
            confidence = meta.get("confidence", 1.0)
        elif confidence is None:
            confidence = 1.0
        if log_type is None and meta:
            log_type = meta.get("log_type", "progress")
        elif log_type is None:
            log_type = "progress"
        async with self._write_lock:
            await self._execute(
                """
                INSERT OR IGNORE INTO scribe_entries
                    (id, project_id, ts, emoji, agent, message, meta, raw_line, sha256, ts_iso, priority, category, tags, confidence, log_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry_id,
                    project.id,
                    format_utc(ts),
                    emoji,
                    agent,
                    message,
                    meta_json,
                    raw_line,
                    sha256,
                    ts_iso,
                    priority,
                    category,
                    tags,
                    confidence,
                    log_type,
                ),
            )
            await self._execute(
                """
                INSERT INTO scribe_metrics (project_id, total_entries, success_count, warn_count, error_count, last_update)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(project_id)
                DO UPDATE SET total_entries = scribe_metrics.total_entries + 1,
                              success_count = scribe_metrics.success_count + excluded.success_count,
                              warn_count = scribe_metrics.warn_count + excluded.warn_count,
                              error_count = scribe_metrics.error_count + excluded.error_count,
                              last_update = excluded.last_update;
                """,
                (
                    project.id,
                    1 if emoji == "✅" else 0,
                    1 if emoji == "⚠️" else 0,
                    1 if emoji == "❌" else 0,
                    utcnow().isoformat(),
                ),
            )

    async def record_doc_change(
        self,
        project: ProjectRecord,
        *,
        doc: str,
        section: Optional[str],
        action: str,
        agent: Optional[str],
        metadata: Optional[Dict[str, Any]],
        sha_before: str,
        sha_after: str,
    ) -> None:
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO doc_changes
                    (project_id, doc_name, section, action, agent, metadata, sha_before, sha_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    project.id,
                    doc,
                    section,
                    action,
                    agent,
                    meta_json,
                    sha_before,
                    sha_after,
                ),
            )
            await self._execute(
                """
                DELETE FROM doc_changes
                WHERE id IN (
                    SELECT id FROM doc_changes
                    WHERE project_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET 500
                );
                """,
                (project.id,),
            )

    async def record_agent_report_card(
        self,
        project: ProjectRecord,
        *,
        file_path: str,
        agent_name: str,
        stage: Optional[str],
        overall_grade: Optional[float],
        performance_level: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO agent_report_cards
                    (project_id, file_path, agent_name, stage, overall_grade, performance_level, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, file_path)
                DO UPDATE SET agent_name = excluded.agent_name,
                              stage = excluded.stage,
                              overall_grade = excluded.overall_grade,
                              performance_level = excluded.performance_level,
                              metadata = excluded.metadata,
                              updated_at = excluded.updated_at;
                """,
                (
                    project.id,
                    file_path,
                    agent_name,
                    stage,
                    overall_grade,
                    performance_level,
                    meta_json,
                    utcnow().isoformat(),
                ),
            )

    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        await self._initialise()
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        agent = filters.get("agent")
        if agent:
            clauses.append("agent = ?")
            params.append(agent)

        emoji = filters.get("emoji")
        if emoji:
            clauses.append("emoji = ?")
            params.append(emoji)

        # Add priority filter
        priority = filters.get("priority")
        if priority:
            placeholders = ",".join("?" * len(priority))
            clauses.append(f"priority IN ({placeholders})")
            params.extend(priority)

        # Add category filter
        category = filters.get("category")
        if category:
            placeholders = ",".join("?" * len(category))
            clauses.append(f"category IN ({placeholders})")
            params.extend(category)

        # Add confidence filter
        min_confidence = filters.get("min_confidence")
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(min_confidence)

        # Add log_type filter (can be single string or list)
        log_type = filters.get("log_type")
        if log_type:
            if isinstance(log_type, str):
                clauses.append("log_type = ?")
                params.append(log_type)
            elif isinstance(log_type, (list, tuple)):
                placeholders = ",".join("?" * len(log_type))
                clauses.append(f"log_type IN ({placeholders})")
                params.extend(log_type)

        where_clause = " AND ".join(clauses)

        # Build ORDER BY clause
        priority_sort = filters.get("priority_sort", False)
        if priority_sort:
            order_by = """
                ORDER BY
                    CASE priority
                        WHEN 'critical' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                    END ASC,
                    ts_iso DESC
            """
        else:
            order_by = "ORDER BY ts_iso DESC"

        rows = await self._fetchall(
            f"""
            SELECT id, ts, emoji, agent, message, meta, raw_line, priority, category, confidence
            FROM scribe_entries
            WHERE {where_clause}
            {order_by}
            LIMIT ? OFFSET ?;
            """,
            (*params, limit, offset),
        )
        results: List[Dict[str, Any]] = []
        for row in rows:
            meta_value = json.loads(row["meta"]) if row["meta"] else {}
            results.append(
                {
                    "id": row["id"],
                    "ts": row["ts"],
                    "emoji": row["emoji"],
                    "agent": row["agent"],
                    "message": row["message"],
                    "meta": meta_value,
                    "raw_line": row["raw_line"],
                    "priority": row["priority"] if "priority" in row.keys() else "medium",
                    "category": row["category"] if "category" in row.keys() else None,
                    "confidence": row["confidence"] if "confidence" in row.keys() else 1.0,
                }
            )
        return results

    async def query_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        await self._initialise()
        limit = max(1, min(limit, 500))
        fetch_limit = min(max(limit * 3, limit), 1000)

        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        if start:
            clauses.append("ts_iso >= ?")
            params.append(start)
        if end:
            clauses.append("ts_iso <= ?")
            params.append(end)

        if agents:
            agent_placeholders = ", ".join("?" for _ in agents)
            clauses.append(f"agent IN ({agent_placeholders})")
            params.extend(agents)

        if emojis:
            emoji_placeholders = ", ".join("?" for _ in emojis)
            clauses.append(f"emoji IN ({emoji_placeholders})")
            params.extend(emojis)

        if meta_filters:
            for key, value in sorted(meta_filters.items()):
                clauses.append("json_extract(meta, ?) = ?")
                params.append(f"$.{key}")
                params.append(value)

        where_clause = " AND ".join(clauses)
        rows = await self._fetchall(
            f"""
            SELECT id, ts, ts_iso, emoji, agent, message, meta, raw_line
            FROM scribe_entries
            WHERE {where_clause}
            ORDER BY ts_iso DESC
            LIMIT ? OFFSET ?;
            """,
            (*params, fetch_limit, offset),
        )

        results: List[Dict[str, Any]] = []
        for row in rows:
            meta_value = json.loads(row["meta"]) if row["meta"] else {}
            entry = {
                "id": row["id"],
                "ts": row["ts"],
                "emoji": row["emoji"],
                "agent": row["agent"],
                "message": row["message"],
                "meta": meta_value,
                "raw_line": row["raw_line"],
            }
            if not message_matches(
                entry["message"],
                message,
                mode=message_mode,
                case_sensitive=case_sensitive,
            ):
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    async def count_entries(
        self,
        project: ProjectRecord,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Efficient count implementation using COUNT query."""
        await self._initialise()
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        agent = filters.get("agent")
        if agent:
            clauses.append("agent = ?")
            params.append(agent)

        emoji = filters.get("emoji")
        if emoji:
            clauses.append("emoji = ?")
            params.append(emoji)

        # Add priority filter
        priority = filters.get("priority")
        if priority:
            placeholders = ",".join("?" * len(priority))
            clauses.append(f"priority IN ({placeholders})")
            params.extend(priority)

        # Add category filter
        category = filters.get("category")
        if category:
            placeholders = ",".join("?" * len(category))
            clauses.append(f"category IN ({placeholders})")
            params.extend(category)

        # Add confidence filter
        min_confidence = filters.get("min_confidence")
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(min_confidence)

        # Add log_type filter (can be single string or list)
        log_type = filters.get("log_type")
        if log_type:
            if isinstance(log_type, str):
                clauses.append("log_type = ?")
                params.append(log_type)
            elif isinstance(log_type, (list, tuple)):
                placeholders = ",".join("?" * len(log_type))
                clauses.append(f"log_type IN ({placeholders})")
                params.extend(log_type)

        where_clause = " AND ".join(clauses)
        row = await self._fetchone(
            f"""
            SELECT COUNT(*) as count
            FROM scribe_entries
            WHERE {where_clause};
            """,
            tuple(params),
        )
        return row["count"] if row else 0

    async def count_query_entries(
        self,
        *,
        project: ProjectRecord,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
    ) -> int:
        """Efficient count for query_entries."""
        await self._initialise()

        clauses = ["project_id = ?"]
        params: List[Any] = [project.id]

        if start:
            clauses.append("ts_iso >= ?")
            params.append(start)
        if end:
            clauses.append("ts_iso <= ?")
            params.append(end)

        if agents:
            agent_placeholders = ", ".join("?" for _ in agents)
            clauses.append(f"agent IN ({agent_placeholders})")
            params.extend(agents)

        if emojis:
            emoji_placeholders = ", ".join("?" for _ in emojis)
            clauses.append(f"emoji IN ({emoji_placeholders})")
            params.extend(emojis)

        if meta_filters:
            for key, value in sorted(meta_filters.items()):
                clauses.append("json_extract(meta, ?) = ?")
                params.append(f"$.{key}")
                params.append(value)

        where_clause = " AND ".join(clauses)
        row = await self._fetchone(
            f"""
            SELECT COUNT(*) as count
            FROM scribe_entries
            WHERE {where_clause};
            """,
            tuple(params),
        )

        count = row["count"] if row else 0

        # Apply message filtering if needed (can't do this efficiently in SQL for complex patterns)
        if message:
            # Need to fetch and filter messages for counting
            # This is less efficient but necessary for message pattern matching
            fetch_limit = min(count, 10000)  # Limit to prevent excessive memory usage
            rows = await self._fetchall(
                f"""
                SELECT message
                FROM scribe_entries
                WHERE {where_clause}
                LIMIT ?;
                """,
                (*params, fetch_limit),
            )

            matching_count = 0
            for row in rows:
                if message_matches(
                    row["message"],
                    message,
                    mode=message_mode,
                    case_sensitive=case_sensitive,
                ):
                    matching_count += 1

            return matching_count

        return count

    async def _initialise(self) -> None:
        async with self._init_lock:
            if self._initialised:
                return
            await asyncio.to_thread(self._path.parent.mkdir, parents=True, exist_ok=True)
            # Migration: Drop old agent_sessions table if it has legacy schema
            # (old schema had 'id' column, new schema has 'session_id')
            await self._migrate_agent_sessions_schema()

            await self._execute_many(
                [
                    """
                    CREATE TABLE IF NOT EXISTS scribe_projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        repo_root TEXT NOT NULL,
                        progress_log_path TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        docs_json TEXT
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS scribe_entries (
                        id TEXT PRIMARY KEY,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        ts TEXT NOT NULL,
                        ts_iso TEXT NOT NULL,
                        emoji TEXT NOT NULL,
                        agent TEXT,
                        message TEXT NOT NULL,
                        meta TEXT,
                        raw_line TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        log_type TEXT DEFAULT 'progress'
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS scribe_metrics (
                        project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        total_entries INTEGER NOT NULL DEFAULT 0,
                        success_count INTEGER NOT NULL DEFAULT 0,
                        warn_count INTEGER NOT NULL DEFAULT 0,
                        error_count INTEGER NOT NULL DEFAULT 0,
                        last_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        session_id TEXT PRIMARY KEY,
                        identity_key TEXT UNIQUE NOT NULL,
                        agent_name TEXT NOT NULL,
                        agent_key TEXT NOT NULL,
                        repo_root TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        scope_key TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_sessions_identity ON agent_sessions(identity_key);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_active ON agent_sessions(last_active_at);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_sessions_expires ON agent_sessions(expires_at);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_projects (
                        agent_id TEXT PRIMARY KEY,
                        project_name TEXT,
                        version INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_by TEXT,
                        session_id TEXT,
                        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_projects_updated_at ON agent_projects(updated_at DESC);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_project_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK (event_type IN ('project_set', 'project_switched', 'session_started', 'session_ended', 'conflict_detected')),
                        from_project TEXT,
                        to_project TEXT NOT NULL,
                        expected_version INTEGER,
                        actual_version INTEGER,
                        success BOOLEAN NOT NULL DEFAULT 1,
                        error_message TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_project_events_agent_id ON agent_project_events(agent_id);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_project_events_created_at ON agent_project_events(created_at);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS scribe_sessions (
                        session_id TEXT PRIMARY KEY,
                        transport_session_id TEXT,
                        agent_id TEXT,
                        repo_root TEXT,
                        mode TEXT NOT NULL CHECK (mode IN ('sentinel','project')) DEFAULT 'sentinel',
                        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_scribe_sessions_transport ON scribe_sessions(transport_session_id);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_scribe_sessions_agent ON scribe_sessions(agent_id);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS session_projects (
                        session_id TEXT PRIMARY KEY,
                        project_name TEXT,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_recent_projects (
                        agent_id TEXT NOT NULL,
                        project_name TEXT NOT NULL,
                        last_access_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY(agent_id, project_name),
                        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE CASCADE
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS doc_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        doc_name TEXT NOT NULL,
                        section TEXT,
                        action TEXT NOT NULL,
                        agent TEXT,
                        metadata TEXT,
                        sha_before TEXT,
                        sha_after TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_doc_changes_project ON doc_changes(project_id, created_at DESC);
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS dev_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        project_name TEXT NOT NULL,
                        plan_type TEXT NOT NULL CHECK (plan_type IN ('architecture', 'phase_plan', 'checklist', 'progress_log')),
                        file_path TEXT NOT NULL,
                        version TEXT NOT NULL DEFAULT '1.0',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT,
                        UNIQUE(project_id, plan_type)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS phases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        dev_plan_id INTEGER NOT NULL REFERENCES dev_plans(id) ON DELETE CASCADE,
                        phase_number INTEGER NOT NULL,
                        phase_name TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('planned', 'in_progress', 'completed', 'blocked')) DEFAULT 'planned',
                        start_date TEXT,
                        end_date TEXT,
                        deliverables_count INTEGER NOT NULL DEFAULT 0,
                        deliverables_completed INTEGER NOT NULL DEFAULT 0,
                        confidence_score REAL NOT NULL DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
                        metadata TEXT,
                        UNIQUE(project_id, phase_number)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS milestones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
                        milestone_name TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'overdue')) DEFAULT 'pending',
                        target_date TEXT,
                        completed_date TEXT,
                        evidence_url TEXT,
                        metadata TEXT
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS benchmarks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        benchmark_type TEXT NOT NULL CHECK (benchmark_type IN ('hash_performance', 'throughput', 'latency', 'stress_test', 'integrity', 'concurrency')),
                        test_name TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        metric_unit TEXT NOT NULL,
                        test_parameters TEXT,
                        environment_info TEXT,
                        test_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        requirement_target REAL,
                        requirement_met BOOLEAN NOT NULL DEFAULT FALSE
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS checklists (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
                        checklist_item TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked')) DEFAULT 'pending',
                        acceptance_criteria TEXT NOT NULL,
                        proof_required BOOLEAN NOT NULL DEFAULT TRUE,
                        proof_url TEXT,
                        assignee TEXT,
                        priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TEXT,
                        metadata TEXT
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        metric_category TEXT NOT NULL CHECK (metric_category IN ('development', 'testing', 'deployment', 'operations')),
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        metric_unit TEXT NOT NULL,
                        baseline_value REAL,
                        improvement_percentage REAL,
                        collection_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT
                    );
                    """,
                    # Indexes for performance
                    "CREATE INDEX IF NOT EXISTS idx_entries_project_ts ON scribe_entries(project_id, ts_iso DESC);",
                    "CREATE INDEX IF NOT EXISTS idx_dev_plans_project_type ON dev_plans(project_id, plan_type);",
                    "CREATE INDEX IF NOT EXISTS idx_phases_project_status ON phases(project_id, status);",
                    "CREATE INDEX IF NOT EXISTS idx_milestones_project_status ON milestones(project_id, status);",
                    "CREATE INDEX IF NOT EXISTS idx_benchmarks_project_type ON benchmarks(project_id, benchmark_type);",
                    "CREATE INDEX IF NOT EXISTS idx_benchmarks_timestamp ON benchmarks(test_timestamp DESC);",
                    "CREATE INDEX IF NOT EXISTS idx_checklists_project_status ON checklists(project_id, status);",
                    "CREATE INDEX IF NOT EXISTS idx_checklists_phase ON checklists(phase_id);",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_project_category ON performance_metrics(project_id, metric_category);",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(collection_timestamp DESC);",
                    # Document Management 2.0 Tables
                    """
                    CREATE TABLE IF NOT EXISTS document_sections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        project_root TEXT,
                        document_type TEXT,
                        section_id TEXT,
                        file_path TEXT,
                        relative_path TEXT,
                        content TEXT NOT NULL,
                        file_hash TEXT NOT NULL,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, document_type, section_id),
                        UNIQUE(project_root, file_path)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS custom_templates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        template_name TEXT NOT NULL,
                        template_content TEXT NOT NULL,
                        variables TEXT,
                        is_global BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, template_name)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS document_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        project_root TEXT,
                        file_path TEXT,
                        change_type TEXT NOT NULL,
                        old_content_hash TEXT,
                        new_content_hash TEXT,
                        change_summary TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS sync_status (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        project_root TEXT,
                        file_path TEXT NOT NULL,
                        relative_path TEXT,
                        last_sync_at TEXT,
                        last_file_hash TEXT,
                        last_db_hash TEXT,
                        sync_status TEXT NOT NULL DEFAULT 'synced',
                        conflict_details TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, file_path)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS agent_report_cards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
                        file_path TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        stage TEXT,
                        overall_grade REAL,
                        performance_level TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_id, file_path)
                    );
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS reminder_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        reminder_hash TEXT NOT NULL,
                        project_root TEXT,
                        agent_id TEXT,
                        tool_name TEXT,
                        reminder_key TEXT,
                        shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        operation_status TEXT NOT NULL DEFAULT 'neutral' CHECK (operation_status IN ('success', 'failure', 'neutral')),
                        context_metadata TEXT,
                        FOREIGN KEY (session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_reminder_history_session_hash
                        ON reminder_history(session_id, reminder_hash);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_reminder_history_shown_at
                        ON reminder_history(shown_at);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_reminder_history_session_tool
                        ON reminder_history(session_id, tool_name);
                    """,
                    # Tool Calls Tracking Table (for direct logging without recursion)
                    """
                    CREATE TABLE IF NOT EXISTS tool_calls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        duration_ms REAL,
                        status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'error', 'partial')),
                        format_requested TEXT,
                        project_name TEXT,
                        agent_id TEXT,
                        error_message TEXT,
                        response_size_bytes INTEGER,
                        FOREIGN KEY (session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_name ON tool_calls(tool_name);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_tool_calls_timestamp ON tool_calls(timestamp);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_tool_calls_project ON tool_calls(project_name);
                    """,
                    # Document Management 2.0 Indexes
                    "CREATE INDEX IF NOT EXISTS idx_document_sections_project ON document_sections(project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_document_sections_updated ON document_sections(updated_at);",
                    "CREATE INDEX IF NOT EXISTS idx_document_changes_project ON document_changes(project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_document_changes_created ON document_changes(created_at);",
                    "CREATE INDEX IF NOT EXISTS idx_sync_status_project ON sync_status(project_id);",
                    "CREATE INDEX IF NOT EXISTS idx_sync_status_status ON sync_status(sync_status);",
                    # Full-text search for document content
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_sections_fts
                    USING fts5(document_type, section_id, content, content=document_sections, content_rowid=id)
                    """,
                    """
                    CREATE TRIGGER IF NOT EXISTS document_sections_fts_insert
                    AFTER INSERT ON document_sections BEGIN
                        INSERT INTO document_sections_fts(rowid, document_type, section_id, content)
                        VALUES (new.id, new.document_type, new.section_id, new.content);
                    END
                    """,
                    """
                    CREATE TRIGGER IF NOT EXISTS document_sections_fts_delete
                    AFTER DELETE ON document_sections BEGIN
                        INSERT INTO document_sections_fts(document_sections_fts, rowid, document_type, section_id, content)
                        VALUES ('delete', old.id, old.document_type, old.section_id, old.content);
                    END
                    """,
                    """
                    CREATE TRIGGER IF NOT EXISTS document_sections_fts_update
                    AFTER UPDATE ON document_sections BEGIN
                        INSERT INTO document_sections_fts(document_sections_fts, rowid, document_type, section_id, content)
                        VALUES ('delete', old.id, old.document_type, old.section_id, old.content);
                        INSERT INTO document_sections_fts(rowid, document_type, section_id, content)
                        VALUES (new.id, new.document_type, new.section_id, new.content);
                    END
                    """,
                    # Bridge Registry Tables
                    """
                    CREATE TABLE IF NOT EXISTS scribe_bridges (
                        bridge_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        version TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ('registered', 'active', 'inactive', 'error', 'unregistered')) DEFAULT 'registered',
                        health_json TEXT,
                        registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_health_check TEXT,
                        last_error TEXT
                    );
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_bridges_state ON scribe_bridges(state);
                    """,
                    """
                    CREATE INDEX IF NOT EXISTS idx_bridges_registered_at ON scribe_bridges(registered_at);
                    """,
                ]
            )
            # Ensure legacy databases have the newer scribe_projects columns
            await self._ensure_column("scribe_projects", "repo_root", "TEXT")
            await self._ensure_column("scribe_projects", "progress_log_path", "TEXT")
            await self._ensure_column("scribe_projects", "status", "TEXT")
            await self._ensure_column("scribe_projects", "phase", "TEXT")
            await self._ensure_column("scribe_projects", "confidence", "REAL DEFAULT 0.0")
            await self._ensure_column("scribe_projects", "completed_at", "TIMESTAMP")
            await self._ensure_column("scribe_projects", "last_activity", "TIMESTAMP")
            await self._ensure_column("scribe_projects", "description", "TEXT")
            await self._ensure_column("scribe_projects", "last_entry_at", "TEXT")
            await self._ensure_column("scribe_projects", "last_access_at", "TEXT")
            await self._ensure_column("scribe_projects", "last_status_change", "TEXT")
            await self._ensure_column("scribe_projects", "tags", "TEXT")
            await self._ensure_column("scribe_projects", "meta", "TEXT")
            # Bridge ownership columns for Phase 3
            await self._ensure_column("scribe_projects", "bridge_id", "TEXT")
            await self._ensure_column("scribe_projects", "bridge_managed", "INTEGER DEFAULT 0")
            await self._execute("CREATE INDEX IF NOT EXISTS idx_projects_bridge ON scribe_projects(bridge_id)", ())
            # Ensure scribe_entries has metadata columns for categorization and prioritization
            await self._ensure_column("scribe_entries", "priority", "TEXT")
            await self._ensure_column("scribe_entries", "category", "TEXT")
            await self._ensure_column("scribe_entries", "tags", "TEXT")
            await self._ensure_column("scribe_entries", "confidence", "REAL DEFAULT 1.0")
            await self._ensure_column("scribe_entries", "log_type", "TEXT DEFAULT 'progress'")
            # Note: Run scripts/backfill_log_type.py manually to populate log_type from meta
            await self._migrate_document_sections()
            await self._ensure_column("document_changes", "project_root", "TEXT")
            await self._ensure_column("document_changes", "file_path", "TEXT")
            await self._ensure_column("sync_status", "project_root", "TEXT")
            await self._ensure_column("sync_status", "relative_path", "TEXT")
            await self._ensure_column("document_sections", "project_root", "TEXT")
            await self._ensure_column("document_sections", "file_path", "TEXT")
            await self._ensure_column("document_sections", "relative_path", "TEXT")
            await self._ensure_index("CREATE UNIQUE INDEX IF NOT EXISTS idx_document_sections_file_path ON document_sections(project_root, file_path);")
            await self._ensure_index("CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_status_file_path ON sync_status(project_root, file_path);")
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_agent_report_cards_project_agent ON agent_report_cards(project_id, agent_name);")
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_agent_report_cards_stage ON agent_report_cards(stage);")
            # Performance indexes for scribe_entries metadata columns
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_entries_priority_ts ON scribe_entries(priority, ts_iso DESC);")
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_entries_category_ts ON scribe_entries(category, ts_iso DESC);")
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_entries_project_priority_category ON scribe_entries(project_id, priority, category, ts_iso DESC);")
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_entries_log_type ON scribe_entries(project_id, log_type, ts_iso DESC);")

            # Migration: Add repo_root column to tool_calls for per-project/repo tool logging
            await self._ensure_column("tool_calls", "repo_root", "TEXT")
            await self._ensure_index("CREATE INDEX IF NOT EXISTS idx_tool_calls_repo_root ON tool_calls(repo_root);")

            # Migration: Add docs_json column for manage_docs functionality (BUG-MANAGE-DOCS-001)
            await self.migrate_add_docs_json_column()

            # Backfill docs_json from state.json for existing projects
            from pathlib import Path
            state_path = Path(self._path).parent / "state.json"
            if state_path.exists():
                await self.backfill_docs_json_from_state(state_path)

            self._initialised = True

    async def _backfill_log_type_from_meta(self) -> None:
        """Backfill log_type column from meta JSON field for existing entries."""
        await asyncio.to_thread(self._backfill_log_type_from_meta_sync)

    def _backfill_log_type_from_meta_sync(self) -> None:
        """Sync version of log_type backfill migration."""
        conn = self._connect()
        try:
            # Update log_type from meta.log_type where it exists and log_type is still default
            # This is idempotent - only updates entries where log_type hasn't been set properly
            conn.execute("""
                UPDATE scribe_entries
                SET log_type = json_extract(meta, '$.log_type')
                WHERE json_extract(meta, '$.log_type') IS NOT NULL
                  AND (log_type IS NULL OR log_type = 'progress')
                  AND json_extract(meta, '$.log_type') != 'progress';
            """)
            conn.commit()
        except Exception:
            # Silently ignore if migration fails (e.g., no entries, column doesn't exist yet)
            pass
        finally:
            conn.close()

    async def _migrate_document_sections(self) -> None:
        await asyncio.to_thread(self._migrate_document_sections_sync)

    def _migrate_document_sections_sync(self) -> None:
        conn = self._connect()
        try:
            cursor = conn.execute("PRAGMA table_info(document_sections);")
            columns = cursor.fetchall()
            if not columns:
                return
            column_map = {row["name"]: row for row in columns}
            needs_rebuild = False
            document_type_info = column_map.get("document_type")
            if "project_root" not in column_map or "file_path" not in column_map or (document_type_info and document_type_info["notnull"]):
                needs_rebuild = True
            if not needs_rebuild:
                return

            conn.execute("ALTER TABLE document_sections RENAME TO document_sections_legacy;")
            conn.execute(
                """
                CREATE TABLE document_sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                    project_root TEXT,
                    document_type TEXT,
                    section_id TEXT,
                    file_path TEXT,
                    relative_path TEXT,
                    content TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, document_type, section_id),
                    UNIQUE(project_root, file_path)
                );
                """
            )
            conn.execute(
                """
                INSERT INTO document_sections (project_id, document_type, section_id, content, file_hash, metadata, created_at, updated_at)
                SELECT project_id, document_type, section_id, content, file_hash, metadata, created_at, updated_at
                FROM document_sections_legacy;
                """
            )
            conn.execute("DROP TABLE document_sections_legacy;")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def _ensure_column(self, table: str, column: str, definition: str) -> None:
        await asyncio.to_thread(self._ensure_column_sync, table, column, definition)

    def _ensure_column_sync(self, table: str, column: str, definition: str) -> None:
        conn = self._connect()
        try:
            cursor = conn.execute(f"PRAGMA table_info({table});")
            # PRAGMA table_info returns tuples: (cid, name, type, notnull, dflt_value, pk)
            # Column name is at index 1
            existing = {row[1] for row in cursor.fetchall()}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")
                conn.commit()
        finally:
            conn.close()

    async def _migrate_agent_sessions_schema(self) -> None:
        """Migrate agent_sessions from legacy schema to new stable identity schema."""
        await asyncio.to_thread(self._migrate_agent_sessions_schema_sync)

    def _migrate_agent_sessions_schema_sync(self) -> None:
        """Drop old agent_sessions table if it has legacy schema (id column instead of session_id)."""
        conn = self._connect()
        try:
            # Check if table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_sessions';"
            )
            if not cursor.fetchone():
                return  # Table doesn't exist, nothing to migrate

            # Check columns - old schema has 'id', new schema has 'session_id'
            cursor = conn.execute("PRAGMA table_info(agent_sessions);")
            columns = {row["name"] for row in cursor.fetchall()}

            if "id" in columns and "session_id" not in columns:
                # Old schema detected - drop table so it can be recreated with new schema
                conn.execute("DROP TABLE agent_sessions;")
                conn.commit()
        finally:
            conn.close()

    async def migrate_add_docs_json_column(self) -> bool:
        """
        Idempotent migration: Add docs_json column to scribe_projects table.

        This migration adds the docs_json TEXT column needed for manage_docs
        document registration functionality (BUG-MANAGE-DOCS-001 fix).

        Returns:
            True if column was added or already exists

        Raises:
            Exception if migration fails
        """
        return await asyncio.to_thread(self._migrate_add_docs_json_column_sync)

    def _migrate_add_docs_json_column_sync(self) -> bool:
        """Synchronous implementation of docs_json column migration."""
        conn = self._connect()
        try:
            # Check if column already exists
            cursor = conn.execute("PRAGMA table_info(scribe_projects);")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'docs_json' in column_names:
                logger.info("docs_json column already exists - migration already applied")
                return True

            # Add the column
            conn.execute("ALTER TABLE scribe_projects ADD COLUMN docs_json TEXT;")
            conn.commit()
            logger.info("Successfully added docs_json column to scribe_projects table")
            return True

        except Exception as e:
            logger.error(f"Failed to add docs_json column: {e}")
            raise
        finally:
            conn.close()

    async def backfill_docs_json_from_state(self, state_path: Path) -> int:
        """
        Backfill docs_json from state.json for existing projects.

        This function reads document metadata from state.json and populates
        the docs_json column for projects that have document mappings but
        haven't been updated in the database yet.

        Args:
            state_path: Path to state.json file

        Returns:
            Number of projects successfully backfilled

        Raises:
            FileNotFoundError if state.json doesn't exist
            json.JSONDecodeError if state.json is malformed
        """
        return await asyncio.to_thread(self._backfill_docs_json_from_state_sync, state_path)

    def _backfill_docs_json_from_state_sync(self, state_path: Path) -> int:
        """Synchronous implementation of docs_json backfill."""
        import json

        # Load state.json
        if not state_path.exists():
            logger.warning(f"State file not found: {state_path}")
            return 0

        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse state.json: {e}")
            raise

        projects = state.get("projects", {})
        backfilled_count = 0

        conn = self._connect()
        try:
            for project_name, project_data in projects.items():
                docs = project_data.get("docs")
                if not docs:
                    continue  # Skip projects without docs

                # Serialize docs to JSON
                docs_json = json.dumps(docs)

                # Update the project
                cursor = conn.execute(
                    "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
                    (docs_json, project_name)
                )

                if cursor.rowcount > 0:
                    backfilled_count += 1

            conn.commit()
            logger.info(f"Backfilled {backfilled_count} projects with docs_json from state.json")
            return backfilled_count

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to backfill docs_json: {e}")
            raise
        finally:
            conn.close()

    async def _ensure_index(self, statement: str) -> None:
        await asyncio.to_thread(self._ensure_index_sync, statement)

    def _ensure_index_sync(self, statement: str) -> None:
        conn = self._connect()
        try:
            conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    async def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        await asyncio.to_thread(self._execute_sync, query, params)

    def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        conn = self._connect()
        try:
            conn.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    async def _execute_many(self, statements: List[str]) -> None:
        await asyncio.to_thread(self._execute_many_sync, statements)

    def _execute_many_sync(self, statements: List[str]) -> None:
        conn = self._connect()
        try:
            for statement in statements:
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    async def _fetchone(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        return await asyncio.to_thread(self._fetchone_sync, query, params)

    def _fetchone_sync(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row
        finally:
            conn.close()

    async def _fetchall(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        return await asyncio.to_thread(self._fetchall_sync, query, params)

    def _fetchall_sync(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return rows
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=SQLITE_TIMEOUT_SECONDS,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        return conn

    # Development Plan Tracking Methods

    async def upsert_dev_plan(
        self,
        *,
        project_id: int,
        project_name: str,
        plan_type: str,
        file_path: str,
        version: str = "1.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DevPlanRecord:
        """Insert or update a development plan record."""
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO dev_plans (project_id, project_name, plan_type, file_path, version, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, plan_type)
                DO UPDATE SET file_path = excluded.file_path,
                              version = excluded.version,
                              metadata = excluded.metadata,
                              updated_at = excluded.updated_at;
                """,
                (project_id, project_name, plan_type, file_path, version, meta_json, utcnow().isoformat()),
            )
        row = await self._fetchone(
            """
            SELECT id, project_id, project_name, plan_type, file_path, version, created_at, updated_at, metadata
            FROM dev_plans
            WHERE project_id = ? AND plan_type = ?;
            """,
            (project_id, plan_type),
        )
        return DevPlanRecord(
            id=row["id"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            plan_type=row["plan_type"],
            file_path=row["file_path"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    async def upsert_phase(
        self,
        *,
        project_id: int,
        dev_plan_id: int,
        phase_number: int,
        phase_name: str,
        status: str = "planned",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        deliverables_count: int = 0,
        deliverables_completed: int = 0,
        confidence_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PhaseRecord:
        """Insert or update a phase record."""
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO phases (project_id, dev_plan_id, phase_number, phase_name, status,
                                 start_date, end_date, deliverables_count, deliverables_completed,
                                 confidence_score, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, phase_number)
                DO UPDATE SET phase_name = excluded.phase_name,
                              status = excluded.status,
                              start_date = excluded.start_date,
                              end_date = excluded.end_date,
                              deliverables_count = excluded.deliverables_count,
                              deliverables_completed = excluded.deliverables_completed,
                              confidence_score = excluded.confidence_score,
                              metadata = excluded.metadata;
                """,
                (project_id, dev_plan_id, phase_number, phase_name, status,
                 start_date, end_date, deliverables_count, deliverables_completed,
                 confidence_score, meta_json),
            )
        row = await self._fetchone(
            """
            SELECT id, project_id, dev_plan_id, phase_number, phase_name, status,
                   start_date, end_date, deliverables_count, deliverables_completed,
                   confidence_score, metadata
            FROM phases
            WHERE project_id = ? AND phase_number = ?;
            """,
            (project_id, phase_number),
        )
        return PhaseRecord(
            id=row["id"],
            project_id=row["project_id"],
            dev_plan_id=row["dev_plan_id"],
            phase_number=row["phase_number"],
            phase_name=row["phase_name"],
            status=row["status"],
            start_date=datetime.fromisoformat(row["start_date"]) if row["start_date"] else None,
            end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
            deliverables_count=row["deliverables_count"],
            deliverables_completed=row["deliverables_completed"],
            confidence_score=row["confidence_score"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    async def store_benchmark(
        self,
        *,
        project_id: int,
        benchmark_type: str,
        test_name: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        test_parameters: Optional[Dict[str, Any]] = None,
        environment_info: Optional[Dict[str, Any]] = None,
        requirement_target: Optional[float] = None,
    ) -> BenchmarkRecord:
        """Store a benchmark result."""
        await self._initialise()
        test_params_json = json.dumps(test_parameters or {}, sort_keys=True)
        env_info_json = json.dumps(environment_info or {}, sort_keys=True)
        requirement_met = (requirement_target is not None and
                          ((benchmark_type in ['throughput', 'hash_performance'] and metric_value >= requirement_target) or
                           (benchmark_type in ['latency', 'time'] and metric_value <= requirement_target) or
                           (requirement_target > 0 and metric_value <= requirement_target) or
                           (requirement_target < 0 and metric_value >= requirement_target)))

        row = await self._fetchone(
            """
            INSERT INTO benchmarks (project_id, benchmark_type, test_name, metric_name,
                                   metric_value, metric_unit, test_parameters, environment_info,
                                   requirement_target, requirement_met)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, project_id, benchmark_type, test_name, metric_name, metric_value,
                    metric_unit, test_parameters, environment_info, test_timestamp,
                    requirement_target, requirement_met;
            """,
            (project_id, benchmark_type, test_name, metric_name, metric_value,
             metric_unit, test_params_json, env_info_json, requirement_target, requirement_met),
        )
        return BenchmarkRecord(
            id=row["id"],
            project_id=row["project_id"],
            benchmark_type=row["benchmark_type"],
            test_name=row["test_name"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            test_parameters=json.loads(row["test_parameters"]) if row["test_parameters"] else None,
            environment_info=json.loads(row["environment_info"]) if row["environment_info"] else None,
            test_timestamp=datetime.fromisoformat(row["test_timestamp"]),
            requirement_target=row["requirement_target"],
            requirement_met=bool(row["requirement_met"]),
        )

    async def get_project_benchmarks(
        self,
        *,
        project_id: int,
        benchmark_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[BenchmarkRecord]:
        """Get benchmark results for a project."""
        await self._initialise()
        params = [project_id]
        query = """
            SELECT id, project_id, benchmark_type, test_name, metric_name, metric_value,
                   metric_unit, test_parameters, environment_info, test_timestamp,
                   requirement_target, requirement_met
            FROM benchmarks
            WHERE project_id = ?
        """

        if benchmark_type:
            query += " AND benchmark_type = ?"
            params.append(benchmark_type)

        query += " ORDER BY test_timestamp DESC LIMIT ?"
        params.append(limit)

        rows = await self._fetchall(query, tuple(params))
        results = []
        for row in rows:
            results.append(BenchmarkRecord(
                id=row["id"],
                project_id=row["project_id"],
                benchmark_type=row["benchmark_type"],
                test_name=row["test_name"],
                metric_name=row["metric_name"],
                metric_value=row["metric_value"],
                metric_unit=row["metric_unit"],
                test_parameters=json.loads(row["test_parameters"]) if row["test_parameters"] else None,
                environment_info=json.loads(row["environment_info"]) if row["environment_info"] else None,
                test_timestamp=datetime.fromisoformat(row["test_timestamp"]),
                requirement_target=row["requirement_target"],
                requirement_met=bool(row["requirement_met"]),
            ))
        return results

    async def store_performance_metric(
        self,
        *,
        project_id: int,
        metric_category: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        baseline_value: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PerformanceMetricsRecord:
        """Store a performance metric."""
        await self._initialise()
        meta_json = json.dumps(metadata or {}, sort_keys=True)

        # Calculate improvement percentage if baseline provided
        improvement_percentage = None
        if baseline_value is not None and baseline_value != 0:
            improvement_percentage = ((metric_value - baseline_value) / abs(baseline_value)) * 100

        row = await self._fetchone(
            """
            INSERT INTO performance_metrics (project_id, metric_category, metric_name,
                                           metric_value, metric_unit, baseline_value,
                                           improvement_percentage, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, project_id, metric_category, metric_name, metric_value, metric_unit,
                    baseline_value, improvement_percentage, collection_timestamp, metadata;
            """,
            (project_id, metric_category, metric_name, metric_value,
             metric_unit, baseline_value, improvement_percentage, meta_json),
        )
        return PerformanceMetricsRecord(
            id=row["id"],
            project_id=row["project_id"],
            metric_category=row["metric_category"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            baseline_value=row["baseline_value"],
            improvement_percentage=row["improvement_percentage"],
            collection_timestamp=datetime.fromisoformat(row["collection_timestamp"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    # Agent session and project context management methods
    async def upsert_agent_session(self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None:
        """Create or update an agent session (legacy compatibility shim).

        Maps old parameters to new stable session schema:
        - session_id → session_id
        - agent_id → agent_name, agent_key
        - identity_key = sha256(agent_id:session_id:legacy)
        """
        await self._initialise()
        import hashlib
        # Generate identity_key for legacy sessions
        identity_string = f"{agent_id}:{session_id}:legacy"
        identity_key = hashlib.sha256(identity_string.encode()).hexdigest()

        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO agent_sessions (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key)
                VALUES (?, ?, ?, ?, 'legacy', 'project', 'legacy')
                ON CONFLICT(session_id) DO UPDATE SET
                    last_active_at = CURRENT_TIMESTAMP;
                """,
                (session_id, identity_key, agent_id, agent_id)
            )

    async def upsert_session(
        self,
        *,
        session_id: str,
        transport_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        repo_root: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        """Create or update a router session record."""
        await self._initialise()
        mode_value = mode if mode in ("sentinel", "project") else "sentinel"
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO scribe_sessions (
                    session_id,
                    transport_session_id,
                    agent_id,
                    repo_root,
                    mode,
                    started_at,
                    last_active_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    transport_session_id = COALESCE(excluded.transport_session_id, scribe_sessions.transport_session_id),
                    agent_id = COALESCE(excluded.agent_id, scribe_sessions.agent_id),
                    repo_root = COALESCE(excluded.repo_root, scribe_sessions.repo_root),
                    mode = excluded.mode,
                    last_active_at = CURRENT_TIMESTAMP;
                """,
                (session_id, transport_session_id, agent_id, repo_root, mode_value),
            )

    async def set_session_mode(self, session_id: str, mode: str) -> None:
        await self._initialise()
        if mode not in ("sentinel", "project"):
            return
        async with self._write_lock:
            await self._execute(
                "UPDATE scribe_sessions SET mode = ?, last_active_at = CURRENT_TIMESTAMP WHERE session_id = ?;",
                (mode, session_id),
            )

    async def get_session_mode(self, session_id: str) -> Optional[str]:
        await self._initialise()
        row = await self._fetchone(
            "SELECT mode FROM scribe_sessions WHERE session_id = ?;",
            (session_id,),
        )
        if row and row["mode"]:
            return row["mode"]
        return None

    async def set_session_project(self, session_id: str, project_name: Optional[str]) -> None:
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO session_projects (session_id, project_name, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    project_name = excluded.project_name,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (session_id, project_name),
            )

    async def get_session_project(self, session_id: str) -> Optional[str]:
        await self._initialise()
        row = await self._fetchone(
            "SELECT project_name FROM session_projects WHERE session_id = ?;",
            (session_id,),
        )
        if row and row["project_name"]:
            return row["project_name"]
        return None

    async def get_session_by_transport(self, transport_session_id: str) -> Optional[Dict[str, Any]]:
        await self._initialise()
        row = await self._fetchone(
            """
            SELECT session_id, transport_session_id, agent_id, repo_root, mode
            FROM scribe_sessions
            WHERE transport_session_id = ?
            ORDER BY last_active_at DESC
            LIMIT 1;
            """,
            (transport_session_id,),
        )
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "transport_session_id": row["transport_session_id"],
            "agent_id": row["agent_id"],
            "repo_root": row["repo_root"],
            "mode": row["mode"],
        }

    async def upsert_agent_recent_project(self, agent_id: str, project_name: str) -> None:
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                """
                INSERT INTO agent_recent_projects (agent_id, project_name, last_access_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id, project_name) DO UPDATE SET
                    last_access_at = CURRENT_TIMESTAMP;
                """,
                (agent_id, project_name),
            )

    async def heartbeat_session(self, session_id: str) -> None:
        """Update session last_active_at timestamp."""
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                """
                UPDATE agent_sessions
                SET last_active_at = CURRENT_TIMESTAMP
                WHERE session_id = ?;
                """,
                (session_id,)
            )

    async def end_session(self, session_id: str) -> None:
        """Mark a session as expired (sets expires_at to now)."""
        await self._initialise()
        async with self._write_lock:
            await self._execute(
                """
                UPDATE agent_sessions
                SET expires_at = CURRENT_TIMESTAMP, last_active_at = CURRENT_TIMESTAMP
                WHERE session_id = ?;
                """,
                (session_id,)
            )

    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent's current project with version info."""
        await self._initialise()
        row = await self._fetchone(
            """
            SELECT agent_id, project_name, version, updated_at, updated_by, session_id
            FROM agent_projects
            WHERE agent_id = ?;
            """,
            (agent_id,)
        )
        if not row:
            return None

        return {
            "agent_id": row["agent_id"],
            "project_name": row["project_name"],
            "version": row["version"],
            "updated_at": row["updated_at"],
            "updated_by": row["updated_by"],
            "session_id": row["session_id"]
        }

    async def set_agent_project(self, agent_id: str, project_name: Optional[str], expected_version: Optional[int], updated_by: str, session_id: str) -> Dict[str, Any]:
        """Set an agent's current project with optimistic concurrency control."""
        await self._initialise()
        async with self._write_lock:
            if expected_version is not None:
                # Optimistic concurrency check
                cursor = await self._fetchone(
                    """
                    UPDATE agent_projects
                    SET project_name = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP,
                        updated_by = ?, session_id = ?
                    WHERE agent_id = ? AND version = ?
                    RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
                    """,
                    (project_name, updated_by, session_id, agent_id, expected_version)
                )
                if not cursor:
                    from scribe_mcp.storage.base import ConflictError
                    raise ConflictError(f"Version conflict for agent {agent_id}: expected version {expected_version}")
                result = cursor
            else:
                # First time or no version check
                await self._execute(
                    """
                    INSERT INTO agent_projects (agent_id, project_name, version, updated_by, session_id)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        project_name = excluded.project_name,
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = excluded.updated_by,
                        session_id = excluded.session_id;
                    """,
                    (agent_id, project_name, updated_by, session_id)
                )
                result = await self.get_agent_project(agent_id)

            return result or await self.get_agent_project(agent_id)

    async def get_or_create_agent_session(
        self,
        identity_key: str,
        agent_name: str,
        agent_key: str,
        repo_root: str,
        mode: str,
        scope_key: str,
        ttl_hours: int = 24
    ) -> str:
        """Get existing session or create new one. Race-safe via upsert.

        Args:
            identity_key: SHA-256 hash of the identity components
            agent_name: Display name for the agent (metadata)
            agent_key: Actual identity component used in hash
            repo_root: Canonicalized repository root path
            mode: "project" or "sentinel"
            scope_key: execution_id (project) or sentinel_day (sentinel)
            ttl_hours: Time-to-live in hours (default: 24)

        Returns:
            session_id: UUID string for this session
        """
        await self._initialise()
        async with self._write_lock:
            new_session_id = str(uuid.uuid4())
            expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

            # Upsert pattern: INSERT OR IGNORE, then UPDATE last_active, then SELECT
            await self._execute(
                """
                INSERT OR IGNORE INTO agent_sessions
                (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (new_session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at)
            )

            # Update activity timestamp and extend TTL
            await self._execute(
                """
                UPDATE agent_sessions
                SET last_active_at = CURRENT_TIMESTAMP,
                    expires_at = ?
                WHERE identity_key = ?
                """,
                (expires_at, identity_key)
            )

            # Get the actual session_id (might be pre-existing)
            row = await self._fetchone(
                "SELECT session_id FROM agent_sessions WHERE identity_key = ?",
                (identity_key,)
            )

            if not row:
                raise RuntimeError(f"Failed to retrieve session for identity_key: {identity_key}")

            return row['session_id']

    async def cleanup_expired_sessions(self, batch_size: int = 100) -> int:
        """Remove expired sessions. Call periodically.

        Args:
            batch_size: Maximum number of sessions to delete in one call

        Returns:
            Number of sessions deleted
        """
        await self._initialise()
        async with self._write_lock:
            # Use subquery workaround since DELETE LIMIT requires compile-time flag
            cursor = await self._execute(
                """
                DELETE FROM agent_sessions
                WHERE session_id IN (
                    SELECT session_id FROM agent_sessions
                    WHERE expires_at < CURRENT_TIMESTAMP
                    LIMIT ?
                )
                """,
                (batch_size,)
            )
            return cursor.rowcount if cursor else 0

    async def record_reminder_shown(
        self,
        session_id: str,
        reminder_hash: str,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        reminder_key: Optional[str] = None,
        operation_status: str = "neutral",
        context_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record that a reminder was shown in a session (inserts new record).

        Args:
            session_id: Session identifier (FK to scribe_sessions)
            reminder_hash: Hash identifying the reminder
            project_root: Optional project root path
            agent_id: Optional agent identifier
            tool_name: Optional tool name (e.g., 'append_entry')
            reminder_key: Optional reminder key (e.g., 'log_warning')
            operation_status: Operation status ('success', 'failure', 'neutral')
            context_metadata: Optional context metadata as dict
        """
        # Performance monitoring (Stage 6)
        start_time = time.perf_counter()

        await self._initialise()
        async with self._write_lock:
            context_json = json.dumps(context_metadata or {}, sort_keys=True)
            await self._execute(
                """
                INSERT INTO reminder_history
                (session_id, reminder_hash, project_root, agent_id, tool_name,
                 reminder_key, shown_at, operation_status, context_metadata)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?);
                """,
                (
                    session_id,
                    reminder_hash,
                    project_root,
                    agent_id,
                    tool_name,
                    reminder_key,
                    operation_status,
                    context_json,
                ),
            )

        # Log slow queries (Stage 6)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                f"Slow reminder query: record_reminder_shown took {elapsed_ms:.2f}ms "
                f"(threshold: {SLOW_QUERY_THRESHOLD_MS}ms) [session={session_id[:16]}...]"
            )

    async def check_reminder_cooldown(
        self,
        session_id: str,
        reminder_hash: str,
        cooldown_minutes: int = 15,
    ) -> bool:
        """Check if a reminder is within its cooldown period for a session.

        Args:
            session_id: Session identifier
            reminder_hash: Hash identifying the reminder
            cooldown_minutes: Cooldown period in minutes (default: 15)

        Returns:
            True if reminder was shown within cooldown window (suppress),
            False if reminder can be shown (cooldown expired or never shown)
        """
        # Performance monitoring (Stage 6)
        start_time = time.perf_counter()

        await self._initialise()
        cutoff_time = f"datetime('now', '-{cooldown_minutes} minutes')"

        row = await self._fetchone(
            f"""
            SELECT COUNT(*) as count
            FROM reminder_history
            WHERE session_id = ?
              AND reminder_hash = ?
              AND shown_at > {cutoff_time};
            """,
            (session_id, reminder_hash),
        )

        result = (row["count"] if row else 0) > 0

        # Log slow queries (Stage 6)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                f"Slow reminder query: check_reminder_cooldown took {elapsed_ms:.2f}ms "
                f"(threshold: {SLOW_QUERY_THRESHOLD_MS}ms) [session={session_id[:16]}...]"
            )

        return result

    async def cleanup_reminder_history(
        self,
        cutoff_hours: int = 168,
    ) -> int:
        """Delete old reminder history entries.

        Args:
            cutoff_hours: Delete entries older than this (default: 168 = 7 days)

        Returns:
            Number of entries deleted
        """
        # Performance monitoring (Stage 6)
        start_time = time.perf_counter()

        await self._initialise()
        async with self._write_lock:
            # Use direct connection since _execute doesn't return cursor
            def _cleanup_sync():
                conn = self._connect()
                try:
                    cursor = conn.execute(
                        """
                        DELETE FROM reminder_history
                        WHERE shown_at < datetime('now', ? || ' hours');
                        """,
                        (f"-{cutoff_hours}",),
                    )
                    deleted = cursor.rowcount
                    conn.commit()
                    return deleted
                finally:
                    conn.close()

            result = await asyncio.to_thread(_cleanup_sync)

        # Log slow queries (Stage 6) - cleanup has higher threshold (100ms vs 5ms)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        cleanup_threshold_ms = 100.0  # Cleanup allowed to be slower
        if elapsed_ms > cleanup_threshold_ms:
            logger.warning(
                f"Slow reminder query: cleanup_reminder_history took {elapsed_ms:.2f}ms "
                f"(threshold: {cleanup_threshold_ms}ms) [deleted={result} records]"
            )

        return result

    # Tool Call Logging Methods (Scope 1: Direct logging without recursion)

    async def record_tool_call(
        self,
        session_id: str,
        tool_name: str,
        duration_ms: Optional[float] = None,
        status: str = "success",
        format_requested: Optional[str] = None,
        project_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
        response_size_bytes: Optional[int] = None,
        repo_root: Optional[str] = None
    ) -> None:
        """Record a tool call to the database for analytics.

        This method provides direct SQL logging without triggering append_entry,
        preventing recursion in finalize_tool_response().

        Args:
            session_id: Session identifier from scribe_sessions table
            tool_name: Name of the tool that was called
            duration_ms: Optional execution time in milliseconds
            status: Tool execution status (success, error, partial)
            format_requested: Format parameter from tool call (readable/structured/compact)
            project_name: Optional project context
            agent_id: Optional agent identifier
            error_message: Optional error details if status=error
            response_size_bytes: Optional response payload size for cost tracking
            repo_root: Optional repository root path for per-repo tool logging
        """
        await self._initialise()
        async with self._write_lock:
            try:
                await self._execute(
                    """
                    INSERT INTO tool_calls (
                        session_id, tool_name, timestamp, duration_ms, status,
                        format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root
                    ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, tool_name, duration_ms, status,
                     format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root)
                )
            except Exception as e:
                # Log error but don't raise - tool logging should never block tool execution
                logger.error(f"Failed to record tool call: {e}")

    def record_tool_call_sync(
        self,
        session_id: str,
        tool_name: str,
        duration_ms: Optional[float] = None,
        status: str = "success",
        format_requested: Optional[str] = None,
        project_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
        response_size_bytes: Optional[int] = None,
        repo_root: Optional[str] = None
    ) -> None:
        """Synchronous version of record_tool_call for background thread execution.

        This method is designed to be called via asyncio.to_thread() from
        finalize_tool_response(). It uses synchronous sqlite3 connection
        instead of aiosqlite for thread-safe execution.

        Args:
            session_id: Session identifier from scribe_sessions table
            tool_name: Name of the tool that was called
            duration_ms: Optional execution time in milliseconds
            status: Tool execution status (success, error, partial)
            format_requested: Format parameter from tool call
            project_name: Optional project context
            agent_id: Optional agent identifier
            error_message: Optional error details if status=error
            response_size_bytes: Optional response payload size
            repo_root: Optional repository root path for per-repo tool logging

        Thread Safety:
            SQLite with WAL mode supports concurrent writes from multiple threads.
            This method acquires a lock via SQLite's internal locking mechanism.

        Error Handling:
            Exceptions are caught and logged to stderr. SQL logging failures
            must never propagate to the calling code or block tool execution.
        """
        try:
            # Use synchronous sqlite3 connection (not aiosqlite)
            import sqlite3
            conn = sqlite3.connect(str(self._path))
            conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for concurrency

            # Execute insert directly (no await needed)
            conn.execute(
                """
                INSERT INTO tool_calls (
                    session_id, tool_name, timestamp, duration_ms, status,
                    format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root
                ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, tool_name, duration_ms, status,
                 format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root)
            )
            conn.commit()
            conn.close()

        except Exception as e:
            # SQL logging is optional, never block or raise
            import sys
            print(f"Warning: SQL tool logging failed in background thread: {e}", file=sys.stderr)

    async def get_session_tool_calls(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get tool call history for a session.

        Args:
            session_id: Session identifier
            limit: Optional maximum number of results

        Returns:
            List of tool call records ordered by timestamp (newest first)
        """
        await self._initialise()

        query = """
            SELECT id, tool_name, timestamp, duration_ms, status,
                   format_requested, project_name, agent_id, error_message, response_size_bytes
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY timestamp DESC
        """

        if limit:
            query += f" LIMIT {int(limit)}"

        rows = await self._fetchall(query, (session_id,))
        return [dict(row) for row in rows]

    async def get_tool_metrics(
        self,
        tool_name: Optional[str] = None,
        project_name: Optional[str] = None,
        time_range_hours: Optional[int] = 24
    ) -> Dict[str, Any]:
        """Get aggregated metrics for tool calls.

        Args:
            tool_name: Optional tool name filter
            project_name: Optional project name filter
            time_range_hours: Time range in hours (default: 24)

        Returns:
            Dictionary with aggregated metrics:
            - total_calls: Total number of tool calls
            - success_count: Number of successful calls
            - error_count: Number of failed calls
            - avg_duration_ms: Average execution time
            - p95_duration_ms: 95th percentile execution time (approximation)
            - total_response_bytes: Total response size
        """
        await self._initialise()

        # Build WHERE clause
        where_clauses = []
        params = []

        if tool_name:
            where_clauses.append("tool_name = ?")
            params.append(tool_name)

        if project_name:
            where_clauses.append("project_name = ?")
            params.append(project_name)

        if time_range_hours:
            where_clauses.append("timestamp >= datetime('now', ? || ' hours')")
            params.append(f"-{time_range_hours}")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Main aggregation query
        row = await self._fetchone(
            f"""
            SELECT
                COUNT(*) as total_calls,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                AVG(duration_ms) as avg_duration_ms,
                SUM(response_size_bytes) as total_response_bytes
            FROM tool_calls
            WHERE {where_sql}
            """,
            tuple(params)
        )

        result = dict(row) if row else {
            "total_calls": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_duration_ms": None,
            "total_response_bytes": None
        }

        # Calculate p95 approximation using LIMIT/OFFSET
        # (SQLite doesn't have percentile_cont, so we approximate)
        if result["total_calls"] > 0:
            p95_offset = int(result["total_calls"] * 0.05)  # Skip bottom 5%
            p95_row = await self._fetchone(
                f"""
                SELECT duration_ms
                FROM tool_calls
                WHERE {where_sql} AND duration_ms IS NOT NULL
                ORDER BY duration_ms DESC
                LIMIT 1 OFFSET ?
                """,
                tuple(params + [p95_offset])
            )
            result["p95_duration_ms"] = p95_row["duration_ms"] if p95_row else None
        else:
            result["p95_duration_ms"] = None

        return result

    # Bridge management methods
    async def insert_bridge(
        self,
        bridge_id: str,
        name: str,
        version: str,
        manifest_json: str,
        state: str
    ) -> None:
        """Insert new bridge record."""
        await self._initialise()
        await self._execute(
            """
            INSERT INTO scribe_bridges (bridge_id, name, version, manifest_json, state)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bridge_id, name, version, manifest_json, state)
        )

    async def update_bridge_state(self, bridge_id: str, state: str) -> None:
        """Update bridge state."""
        await self._initialise()
        await self._execute(
            """
            UPDATE scribe_bridges
            SET state = ?
            WHERE bridge_id = ?
            """,
            (state, bridge_id)
        )

    async def update_bridge_health(
        self,
        bridge_id: str,
        health_json: str,
        error: Optional[str] = None
    ) -> None:
        """Update bridge health status."""
        await self._initialise()
        await self._execute(
            """
            UPDATE scribe_bridges
            SET health_json = ?,
                last_health_check = CURRENT_TIMESTAMP,
                last_error = ?
            WHERE bridge_id = ?
            """,
            (health_json, error, bridge_id)
        )

    async def fetch_bridge(self, bridge_id: str) -> Optional[Dict[str, Any]]:
        """Fetch bridge by ID."""
        await self._initialise()
        row = await self._fetchone(
            """
            SELECT bridge_id, name, version, manifest_json, state,
                   health_json, registered_at, last_health_check, last_error
            FROM scribe_bridges
            WHERE bridge_id = ?
            """,
            (bridge_id,)
        )
        return dict(row) if row else None

    async def list_bridges(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """List bridges, optionally filtered by state."""
        await self._initialise()

        if state:
            rows = await self._fetchall(
                """
                SELECT bridge_id, name, version, manifest_json, state,
                       health_json, registered_at, last_health_check, last_error
                FROM scribe_bridges
                WHERE state = ?
                ORDER BY registered_at DESC
                """,
                (state,)
            )
        else:
            rows = await self._fetchall(
                """
                SELECT bridge_id, name, version, manifest_json, state,
                       health_json, registered_at, last_health_check, last_error
                FROM scribe_bridges
                ORDER BY registered_at DESC
                """
            )

        return [dict(row) for row in rows]

    async def delete_bridge(self, bridge_id: str) -> None:
        """Delete bridge record."""
        await self._initialise()
        await self._execute(
            """
            DELETE FROM scribe_bridges
            WHERE bridge_id = ?
            """,
            (bridge_id,)
        )
