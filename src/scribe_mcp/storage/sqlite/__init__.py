"""SQLite storage backend (default)."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.models import CaseRegistryRecord, ProjectRecord, RepoScopeGrantRecord

from .domain_facade import SQLiteDomainFacadeMixin
from .internals import SQLiteInternals
from . import compat_migrations
from . import cases as case_ops
from . import documents as document_ops
from . import entries as entry_ops
from . import projects as project_ops
from . import telemetry as telemetry_ops
from .migrations import (
    ensure_column,
    ensure_column_sync,
    ensure_index,
    ensure_index_sync,
    mark_migration_complete,
    migration_completed,
    run_all_migrations,
    run_migration,
)
from .schema import create_schema

logger = logging.getLogger(__name__)


class SQLiteStorage(SQLiteDomainFacadeMixin, StorageBackend):
    """SQLite-backed persistence with lazy connections."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path).expanduser()
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._initialised = False
        self._internals = SQLiteInternals(self._path)

    @property
    def _pool(self):
        return self._internals.pool

    @_pool.setter
    def _pool(self, value) -> None:
        self._internals.pool = value

    async def setup(self) -> None:
        await self._internals.setup(self._initialise)

    async def close(self) -> None:
        """Close the connection pool and release all connections."""
        await self._internals.close()

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
        return await project_ops.upsert_project(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            name=name,
            repo_root=repo_root,
            progress_log_path=progress_log_path,
            docs_json=docs_json,
            bridge_id=bridge_id,
            bridge_managed=bridge_managed,
        )

    async def fetch_project(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[ProjectRecord]:
        return await project_ops.fetch_project(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            name=name,
            repo_root=repo_root,
            project_key=project_key,
        )

    def fetch_project_sync(self, name: str) -> Optional[ProjectRecord]:
        return project_ops.fetch_project_sync(db_path=self._path, name=name)

    async def list_projects(self) -> List[ProjectRecord]:
        return await project_ops.list_projects(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
        )

    async def list_projects_by_repo(self, repo_root: str) -> List[ProjectRecord]:
        return await project_ops.list_projects_by_repo(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
            repo_root=repo_root,
        )

    async def delete_project(self, name: str) -> bool:
        return await project_ops.delete_project(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            fetch_project_fn=self.fetch_project,
            name=name,
        )

    async def update_project_docs(
        self,
        name: str,
        docs_json: str,
        *,
        repo_root: Optional[str] = None,
    ) -> bool:
        return await project_ops.update_project_docs(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            name=name,
            docs_json=docs_json,
            repo_root=repo_root,
        )

    async def create_repo_scope_grant(
        self,
        *,
        authoritative_session_key: str,
        repo_root: str,
        reason: str,
        ttl_minutes: int = 30,
    ) -> RepoScopeGrantRecord:
        return await project_ops.create_repo_scope_grant(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            authoritative_session_key=authoritative_session_key,
            repo_root=repo_root,
            reason=reason,
            ttl_minutes=ttl_minutes,
        )

    async def fetch_repo_scope_grant(self, grant_id: str) -> Optional[RepoScopeGrantRecord]:
        return await project_ops.fetch_repo_scope_grant(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            grant_id=grant_id,
        )

    async def upsert_case_registry_record(
        self,
        *,
        case_id: str,
        case_type: str,
        project_name: str,
        repo_root: str,
        doc_type: str,
        doc_name: str,
        doc_path: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        source_tool: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CaseRegistryRecord:
        return await case_ops.upsert_case_registry_record(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            case_id=case_id,
            case_type=case_type,
            project_name=project_name,
            repo_root=repo_root,
            doc_type=doc_type,
            doc_name=doc_name,
            doc_path=doc_path,
            title=title,
            status=status,
            severity=severity,
            source_tool=source_tool,
            metadata=metadata,
        )

    async def fetch_case_registry_record(
        self,
        case_id: str,
        *,
        repo_root: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[CaseRegistryRecord]:
        return await case_ops.fetch_case_registry_record(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            case_id=case_id,
            repo_root=repo_root,
            project_name=project_name,
        )

    async def query_case_registry_records(
        self,
        *,
        repo_root: Optional[str] = None,
        project_name: Optional[str] = None,
        case_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CaseRegistryRecord]:
        return await case_ops.query_case_registry_records(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            fetchall_fn=self._fetchall,
            repo_root=repo_root,
            project_name=project_name,
            case_type=case_type,
            limit=limit,
            offset=offset,
        )

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
        await entry_ops.insert_entry(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            entry_id=entry_id,
            project=project,
            ts=ts,
            emoji=emoji,
            agent=agent,
            message=message,
            meta=meta,
            raw_line=raw_line,
            sha256=sha256,
            priority=priority,
            category=category,
            tags=tags,
            confidence=confidence,
            log_type=log_type,
        )

    async def update_entry_meta(
        self,
        *,
        entry_id: str,
        project: ProjectRecord,
        meta: Dict[str, Any],
    ) -> bool:
        return await entry_ops.update_entry_meta(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            entry_id=entry_id,
            project=project,
            meta=meta,
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
        await document_ops.record_doc_change(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            project=project,
            doc=doc,
            section=section,
            action=action,
            agent=agent,
            metadata=metadata,
            sha_before=sha_before,
            sha_after=sha_after,
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
        await telemetry_ops.record_agent_report_card(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            project=project,
            file_path=file_path,
            agent_name=agent_name,
            stage=stage,
            overall_grade=overall_grade,
            performance_level=performance_level,
            metadata=metadata,
        )

    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await entry_ops.fetch_recent_entries(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
            project=project,
            limit=limit,
            filters=filters,
            offset=offset,
        )

    async def fetch_entry_by_id(
        self,
        *,
        entry_id: str,
        repo_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return await entry_ops.fetch_entry_by_id(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            entry_id=entry_id,
            repo_id=repo_id,
            project_name=project_name,
        )

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
        return await entry_ops.query_entries(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
            project=project,
            limit=limit,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters,
            offset=offset,
        )

    async def count_entries(
        self,
        project: ProjectRecord,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await entry_ops.count_entries(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            project=project,
            filters=filters,
        )

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
        return await entry_ops.count_query_entries(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            fetchall_fn=self._fetchall,
            project=project,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters,
        )

    async def _initialise(self) -> None:
        async with self._init_lock:
            if self._initialised:
                return
            await asyncio.to_thread(self._path.parent.mkdir, parents=True, exist_ok=True)

            # Base schema creation delegated to storage/sqlite/schema.py
            await create_schema(
                self._execute,
                self._execute_many,
                self._migrate_agent_sessions_schema,
            )

            # Tracked migrations are delegated to storage/sqlite/migrations.py
            await run_all_migrations(
                ensure_column_fn=self._ensure_column,
                ensure_index_fn=self._ensure_index,
                execute_fn=self._execute,
                fetchone_fn=self._fetchone,
                migrate_document_sections_fn=self._migrate_document_sections,
                migrate_add_docs_json_column_fn=self.migrate_add_docs_json_column,
                backfill_docs_json_from_state_fn=self.backfill_docs_json_from_state,
                db_path=self._path,
                logger=logger,
            )
            await case_ops.ensure_case_registry_schema(execute_fn=self._execute, fetchone_fn=self._fetchone)

            self._initialised = True

    async def _backfill_log_type_from_meta(self) -> None:
        await compat_migrations.backfill_log_type_from_meta(connect_fn=self._connect)

    def _backfill_log_type_from_meta_sync(self) -> None:
        compat_migrations.backfill_log_type_from_meta_sync(connect_fn=self._connect)

    async def _migrate_document_sections(self) -> None:
        await compat_migrations.migrate_document_sections(connect_fn=self._connect)

    def _migrate_document_sections_sync(self) -> None:
        compat_migrations.migrate_document_sections_sync(connect_fn=self._connect)

    async def _ensure_column(self, table: str, column: str, definition: str) -> None:
        await ensure_column(self._connect, table, column, definition)

    def _ensure_column_sync(self, table: str, column: str, definition: str) -> None:
        ensure_column_sync(self._connect, table, column, definition)

    async def _migrate_agent_sessions_schema(self) -> None:
        await compat_migrations.migrate_agent_sessions_schema(connect_fn=self._connect)

    def _migrate_agent_sessions_schema_sync(self) -> None:
        compat_migrations.migrate_agent_sessions_schema_sync(connect_fn=self._connect)

    async def migrate_add_docs_json_column(self) -> bool:
        return await compat_migrations.migrate_add_docs_json_column(
            connect_fn=self._connect,
            logger=logger,
        )

    def _migrate_add_docs_json_column_sync(self) -> bool:
        return compat_migrations.migrate_add_docs_json_column_sync(
            connect_fn=self._connect,
            logger=logger,
        )

    async def backfill_docs_json_from_state(self, state_path: Path) -> int:
        return await compat_migrations.backfill_docs_json_from_state(
            state_path=state_path,
            connect_fn=self._connect,
            logger=logger,
        )

    def _backfill_docs_json_from_state_sync(self, state_path: Path) -> int:
        return compat_migrations.backfill_docs_json_from_state_sync(
            state_path=state_path,
            connect_fn=self._connect,
            logger=logger,
        )

    async def _ensure_index(self, statement: str) -> None:
        await ensure_index(self._connect, lambda: self._pool, statement)

    def _ensure_index_sync(self, statement: str) -> None:
        ensure_index_sync(self._connect, lambda: self._pool, statement)

    # -------------------------------------------------------------------------
    # Migration Tracking Helpers (Phase 6 Task 6.2)
    # -------------------------------------------------------------------------
    async def _migration_completed(self, name: str) -> bool:
        """Check if a migration has already been completed."""
        return await migration_completed(self._fetchone, name)

    async def _mark_migration_complete(self, name: str) -> None:
        """Mark a migration as completed."""
        await mark_migration_complete(self._execute, name, logger)

    async def _run_migration(self, name: str, coro) -> bool:
        """Run a migration if not already completed, with tracking."""
        return await run_migration(
            name=name,
            migration_coro=coro,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            logger=logger,
        )

    async def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        await self._internals.execute(query, params)

    def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        self._internals.execute_sync(query, params)

    async def _execute_many(self, statements: List[str]) -> None:
        await self._internals.execute_many(statements)

    def _execute_many_sync(self, statements: List[str]) -> None:
        self._internals.execute_many_sync(statements)

    async def _fetchone(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        return await self._internals.fetchone(query, params)

    def _fetchone_sync(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        return self._internals.fetchone_sync(query, params)

    async def _fetchall(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        return await self._internals.fetchall(query, params)

    def _fetchall_sync(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        return self._internals.fetchall_sync(query, params)

    def _connect(self) -> sqlite3.Connection:
        return self._internals.connect()
