"""PostgreSQL storage backend."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import asyncpg

from scribe_mcp.storage.base import ConflictError, StorageBackend
from scribe_mcp.storage.models import (
    BenchmarkRecord,
    CaseRegistryRecord,
    DevPlanRecord,
    PerformanceMetricsRecord,
    PhaseRecord,
    ProjectRecord,
    RepoScopeGrantRecord,
    compute_project_key,
    compute_repo_id,
    normalize_repo_root,
)
from scribe_mcp.utils.search import message_matches
from scribe_mcp.utils.slug import normalize_project_input
from scribe_mcp.utils.time import format_utc, utcnow
from . import documents as document_ops
from .internals import COMMAND_TIMEOUT_SECONDS, PostgresInternals, PostgresPoolConfig
from .schema import SCHEMA_PATH, ensure_schema
from . import migrations as pg_migrations

SLOW_QUERY_THRESHOLD_MS = 25.0

LOGGER = logging.getLogger(__name__)


def _to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _parse_time_filter(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _coerce_json(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _coerce_json_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:
            return []
    return []


def _append_values(params: List[Any], values: Sequence[Any]) -> str:
    start_idx = len(params) + 1
    params.extend(values)
    return ", ".join(f"${idx}" for idx in range(start_idx, start_idx + len(values)))


def _command_count(tag: str) -> int:
    if not tag:
        return 0
    parts = tag.split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except (ValueError, TypeError):
        return 0


class PostgresStorage(StorageBackend):
    """asyncpg-backed persistence."""

    def __init__(
        self,
        dsn: str,
        *,
        schema_name: str = "scribe",
        pool_min_size: int = 2,
        pool_max_size: int = 20,
        command_timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
        connect_timeout_seconds: float = 10.0,
        max_inactive_connection_lifetime_seconds: float = 300.0,
        connect_retries: int = 3,
        connect_retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._dsn = dsn
        pool_config = PostgresPoolConfig(
            min_size=pool_min_size,
            max_size=pool_max_size,
            command_timeout_seconds=command_timeout_seconds,
            connect_timeout_seconds=connect_timeout_seconds,
            max_inactive_connection_lifetime_seconds=max_inactive_connection_lifetime_seconds,
            connect_retries=connect_retries,
            connect_retry_backoff_seconds=connect_retry_backoff_seconds,
            schema_name=schema_name,
        ).normalized()
        self._schema_name = pool_config.schema_name
        self._internals = PostgresInternals(dsn, config=pool_config)
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False
        self._completed_migrations: set[str] = set()

    @property
    def schema_name(self) -> str:
        return self._schema_name

    async def setup(self) -> None:
        await self._ensure_schema()

    async def close(self) -> None:
        await self._internals.close()
        self._schema_ready = False
        self._completed_migrations.clear()

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
        await self._ensure_repo_scoped_project_identity()
        normalized_root = normalize_repo_root(repo_root)
        repo_id = compute_repo_id(normalized_root)
        project_key = compute_project_key(repo_root=normalized_root, project_name=name)
        row = await self._fetchrow(
            """
            INSERT INTO scribe_projects
                (name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed, updated_at)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT(project_key) DO UPDATE SET
                name = EXCLUDED.name,
                repo_root = EXCLUDED.repo_root,
                repo_id = EXCLUDED.repo_id,
                progress_log_path = EXCLUDED.progress_log_path,
                docs_json = EXCLUDED.docs_json,
                bridge_id = EXCLUDED.bridge_id,
                bridge_managed = EXCLUDED.bridge_managed,
                updated_at = NOW()
            RETURNING id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed;
            """,
            name,
            normalized_root,
            repo_id,
            project_key,
            progress_log_path,
            docs_json,
            bridge_id,
            bridge_managed,
        )
        assert row is not None
        return self._project_from_row(row)

    async def fetch_project(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[ProjectRecord]:
        await self._ensure_repo_scoped_project_identity()
        row = await self._fetch_project_row(name, repo_root=repo_root, project_key=project_key)
        if not row:
            return None
        return self._project_from_row(row)

    def fetch_project_sync(self, name: str) -> Optional[ProjectRecord]:
        async def _fetch() -> Optional[ProjectRecord]:
            await self._ensure_schema()
            row = await self._fetch_project_row(name)
            if not row:
                return None
            return self._project_from_row(row)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_fetch())

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(_fetch())).result(timeout=COMMAND_TIMEOUT_SECONDS * 2)

    async def list_projects(self) -> List[ProjectRecord]:
        rows = await self._fetch(
            """
            SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
            FROM scribe_projects
            ORDER BY name;
            """
        )
        return [self._project_from_row(row) for row in rows]

    async def list_projects_by_repo(self, repo_root: str) -> List[ProjectRecord]:
        normalized_root = normalize_repo_root(repo_root)
        rows = await self._fetch(
            """
            SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE repo_root = $1
            ORDER BY name;
            """,
            normalized_root,
        )
        return [self._project_from_row(row) for row in rows]

    async def delete_project(self, name: str) -> bool:
        project = await self.fetch_project(name)
        if not project:
            return False

        await self._execute("DELETE FROM agent_projects WHERE project_name = $1;", project.name)
        tag = await self._execute("DELETE FROM scribe_projects WHERE name = $1;", project.name)
        return _command_count(tag) > 0

    async def update_project_docs(self, name: str, docs_json: str) -> bool:
        tag = await self._execute(
            "UPDATE scribe_projects SET docs_json = $1, updated_at = NOW() WHERE name = $2;",
            docs_json,
            name,
        )
        return _command_count(tag) > 0

    async def create_repo_scope_grant(
        self,
        *,
        authoritative_session_key: str,
        repo_root: str,
        reason: str,
        ttl_minutes: int = 30,
    ) -> RepoScopeGrantRecord:
        await self._ensure_repo_scope_grants_schema()
        grant_id = uuid.uuid4().hex
        normalized_root = normalize_repo_root(repo_root)
        repo_id = compute_repo_id(normalized_root)
        row = await self._fetchrow(
            """
            INSERT INTO repo_scope_grants
                (grant_id, authoritative_session_key, repo_root, repo_id, reason, expires_at, created_at, updated_at)
            VALUES
                ($1, $2, $3, $4, $5, NOW() + ($6::INT * INTERVAL '1 minute'), NOW(), NOW())
            RETURNING grant_id, authoritative_session_key, repo_root, repo_id, reason, expires_at, created_at, updated_at;
            """,
            grant_id,
            authoritative_session_key,
            normalized_root,
            repo_id,
            reason,
            ttl_minutes,
        )
        assert row is not None
        return RepoScopeGrantRecord(
            grant_id=str(row["grant_id"]),
            authoritative_session_key=str(row["authoritative_session_key"]),
            repo_root=str(row["repo_root"]),
            repo_id=str(row["repo_id"]),
            reason=str(row["reason"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def fetch_repo_scope_grant(self, grant_id: str) -> Optional[RepoScopeGrantRecord]:
        await self._ensure_repo_scope_grants_schema()
        row = await self._fetchrow(
            """
            SELECT grant_id, authoritative_session_key, repo_root, repo_id, reason, expires_at, created_at, updated_at
            FROM repo_scope_grants
            WHERE grant_id = $1
              AND expires_at > NOW();
            """,
            grant_id,
        )
        if not row:
            return None
        return RepoScopeGrantRecord(
            grant_id=str(row["grant_id"]),
            authoritative_session_key=str(row["authoritative_session_key"]),
            repo_root=str(row["repo_root"]),
            repo_id=str(row["repo_id"]),
            reason=str(row["reason"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
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
        await self._ensure_case_registry_schema()
        normalized_root = normalize_repo_root(repo_root)
        repo_id = compute_repo_id(normalized_root)
        project_key = compute_project_key(repo_root=normalized_root, project_name=project_name)
        row = await self._fetchrow(
            """
            INSERT INTO case_registry (
                case_id, case_type, project_name, repo_root, repo_id, project_key,
                doc_type, doc_name, doc_path, title, status, severity, source_tool, metadata, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW())
            ON CONFLICT(project_key, case_id) DO UPDATE SET
                case_type = EXCLUDED.case_type,
                project_name = EXCLUDED.project_name,
                repo_root = EXCLUDED.repo_root,
                repo_id = EXCLUDED.repo_id,
                project_key = EXCLUDED.project_key,
                doc_type = EXCLUDED.doc_type,
                doc_name = EXCLUDED.doc_name,
                doc_path = EXCLUDED.doc_path,
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                severity = EXCLUDED.severity,
                source_tool = EXCLUDED.source_tool,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING case_id, case_type, project_name, repo_root, repo_id, project_key,
                      doc_type, doc_name, doc_path, title, status, severity, source_tool,
                      metadata, created_at, updated_at;
            """,
            case_id,
            case_type,
            project_name,
            normalized_root,
            repo_id,
            project_key,
            doc_type,
            doc_name,
            doc_path,
            title,
            status,
            severity,
            source_tool,
            json.dumps(metadata or {}, sort_keys=True),
        )
        assert row is not None
        return self._case_registry_from_row(row)

    async def fetch_case_registry_record(
        self,
        case_id: str,
        *,
        repo_root: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[CaseRegistryRecord]:
        await self._ensure_case_registry_schema()
        clauses = ["case_id = $1"]
        params: List[Any] = [case_id]
        if repo_root:
            params.append(normalize_repo_root(repo_root))
            clauses.append(f"repo_root = ${len(params)}")
        if project_name:
            params.append(project_name)
            clauses.append(f"project_name = ${len(params)}")

        row = await self._fetchrow(
            f"""
            SELECT case_id, case_type, project_name, repo_root, repo_id, project_key,
                   doc_type, doc_name, doc_path, title, status, severity, source_tool,
                   metadata, created_at, updated_at
            FROM case_registry
            WHERE {' AND '.join(clauses)}
            LIMIT 1;
            """,
            *params,
        )
        if not row:
            return None
        return self._case_registry_from_row(row)

    async def query_case_registry_records(
        self,
        *,
        repo_root: Optional[str] = None,
        project_name: Optional[str] = None,
        case_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CaseRegistryRecord]:
        await self._ensure_case_registry_schema()
        clauses = ["1=1"]
        params: List[Any] = []
        if repo_root:
            params.append(normalize_repo_root(repo_root))
            clauses.append(f"repo_root = ${len(params)}")
        if project_name:
            params.append(project_name)
            clauses.append(f"project_name = ${len(params)}")
        if case_type:
            params.append(case_type)
            clauses.append(f"case_type = ${len(params)}")
        params.extend([limit, offset])

        rows = await self._fetch(
            f"""
            SELECT case_id, case_type, project_name, repo_root, repo_id, project_key,
                   doc_type, doc_name, doc_path, title, status, severity, source_tool,
                   metadata, created_at, updated_at
            FROM case_registry
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, case_id ASC
            LIMIT ${len(params) - 1} OFFSET ${len(params)};
            """,
            *params,
        )
        return [self._case_registry_from_row(row) for row in rows]

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
        meta_obj: Dict[str, Any] = dict(meta or {})
        priority_value = priority if priority is not None else str(meta_obj.get("priority", "medium"))
        category_value = category if category is not None else meta_obj.get("category")
        tags_value = tags if tags is not None else meta_obj.get("tags")
        confidence_value = confidence if confidence is not None else float(meta_obj.get("confidence", 1.0))
        log_type_value = log_type if log_type is not None else str(meta_obj.get("log_type", "progress"))

        if log_type_value == "tool_logs":
            return

        await self._execute(
            """
            INSERT INTO scribe_entries
                (id, project_id, ts, ts_iso, emoji, agent, message, meta, raw_line, sha256, priority, category, tags, confidence, log_type)
            VALUES
                ($1, $2, $3, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT(id) DO NOTHING;
            """,
            entry_id,
            project.id,
            ts,
            emoji,
            agent,
            message,
            json.dumps(meta_obj, sort_keys=True),
            raw_line,
            sha256,
            priority_value,
            category_value,
            tags_value,
            confidence_value,
            log_type_value,
        )
        await self._execute(
            """
            INSERT INTO scribe_metrics (project_id, total_entries, success_count, warn_count, error_count, last_update)
            VALUES ($1, 1, $2, $3, $4, NOW())
            ON CONFLICT(project_id) DO UPDATE SET
                total_entries = scribe_metrics.total_entries + 1,
                success_count = scribe_metrics.success_count + EXCLUDED.success_count,
                warn_count = scribe_metrics.warn_count + EXCLUDED.warn_count,
                error_count = scribe_metrics.error_count + EXCLUDED.error_count,
                last_update = NOW();
            """,
            project.id,
            1 if emoji == "✅" else 0,
            1 if emoji == "⚠️" else 0,
            1 if emoji == "❌" else 0,
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
        await self._execute(
            """
            INSERT INTO doc_changes
                (project_id, doc_name, section, action, agent, metadata, sha_before, sha_after)
            VALUES
                ($1, $2, $3, $4, $5, $6::jsonb, $7, $8);
            """,
            project.id,
            doc,
            section,
            action,
            agent,
            json.dumps(metadata or {}, sort_keys=True),
            sha_before,
            sha_after,
        )
        await self._execute(
            """
            DELETE FROM doc_changes
            WHERE id IN (
                SELECT id
                FROM doc_changes
                WHERE project_id = $1
                ORDER BY created_at DESC
                OFFSET 500
            );
            """,
            project.id,
        )

    async def upsert_document_section(
        self,
        *,
        project_id: Optional[int],
        project_root: Optional[str],
        document_type: str,
        section_id: str,
        file_path: str,
        relative_path: Optional[str],
        content: str,
        file_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        await document_ops.upsert_document_section(
            execute_fn=self._execute,
            project_id=project_id,
            project_root=project_root,
            document_type=document_type,
            section_id=section_id,
            file_path=file_path,
            relative_path=relative_path,
            content=content,
            file_hash=file_hash,
            metadata=metadata,
        )

    async def get_document_section(
        self,
        *,
        project_id: Optional[int],
        document_type: str,
        section_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await document_ops.get_document_section(
            fetchrow_fn=self._fetchrow,
            project_id=project_id,
            document_type=document_type,
            section_id=section_id,
        )

    async def search_document_sections(
        self,
        *,
        query: str,
        project_id: Optional[int] = None,
        document_type: Optional[str] = None,
        threshold: float = 0.3,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return await document_ops.search_document_sections(
            fetch_fn=self._fetch,
            query=query,
            project_id=project_id,
            document_type=document_type,
            threshold=threshold,
            limit=limit,
        )

    async def record_document_change(
        self,
        *,
        project_id: Optional[int],
        project_root: Optional[str],
        file_path: str,
        change_type: str,
        old_content_hash: Optional[str] = None,
        new_content_hash: Optional[str] = None,
        change_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        await document_ops.record_document_change(
            execute_fn=self._execute,
            project_id=project_id,
            project_root=project_root,
            file_path=file_path,
            change_type=change_type,
            old_content_hash=old_content_hash,
            new_content_hash=new_content_hash,
            change_summary=change_summary,
            metadata=metadata,
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
        await self._execute(
            """
            INSERT INTO agent_report_cards
                (project_id, file_path, agent_name, stage, overall_grade, performance_level, metadata, updated_at)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
            ON CONFLICT(project_id, file_path) DO UPDATE SET
                agent_name = EXCLUDED.agent_name,
                stage = EXCLUDED.stage,
                overall_grade = EXCLUDED.overall_grade,
                performance_level = EXCLUDED.performance_level,
                metadata = EXCLUDED.metadata,
                updated_at = NOW();
            """,
            project.id,
            file_path,
            agent_name,
            stage,
            overall_grade,
            performance_level,
            json.dumps(metadata or {}, sort_keys=True),
        )

    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        filters = filters or {}
        clauses, params = self._build_recent_filter_clauses(project.id, filters)
        where_clause = " AND ".join(clauses)

        priority_sort = bool(filters.get("priority_sort", False))
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

        rows = await self._fetch(
            f"""
            SELECT id, ts, emoji, agent, message, meta, raw_line, priority, category, confidence
            FROM scribe_entries
            WHERE {where_clause}
            {order_by}
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2};
            """,
            *params,
            limit,
            offset,
        )

        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "id": row["id"],
                    "ts": self._format_ts(row["ts"]),
                    "emoji": row["emoji"],
                    "agent": row["agent"],
                    "message": row["message"],
                    "meta": _coerce_json(row["meta"]),
                    "raw_line": row["raw_line"],
                    "priority": row.get("priority", "medium"),
                    "category": row.get("category"),
                    "confidence": row.get("confidence", 1.0),
                }
            )
        return results

    async def fetch_entry_by_id(
        self,
        *,
        entry_id: str,
        repo_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        clauses = ["e.id = $1"]
        params: List[Any] = [entry_id]
        if repo_id:
            params.append(repo_id)
            clauses.append(f"p.repo_id = ${len(params)}")
        if project_name:
            params.append(project_name)
            clauses.append(f"p.name = ${len(params)}")

        row = await self._fetchrow(
            f"""
            SELECT e.id AS entry_id, p.name AS project_name, p.repo_id, e.ts, e.agent, e.log_type
            FROM scribe_entries e
            JOIN scribe_projects p ON p.id = e.project_id
            WHERE {' AND '.join(clauses)}
            LIMIT 1;
            """,
            *params,
        )
        if not row:
            return None
        return {
            "entry_id": row["entry_id"],
            "project_name": row["project_name"],
            "repo_id": row["repo_id"],
            "timestamp": self._format_ts(row["ts"]),
            "agent": row["agent"],
            "log_type": row["log_type"],
        }

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
        safe_limit = max(1, min(limit, 500))
        fetch_limit = min(max(safe_limit * 3, safe_limit), 1000)

        clauses = ["project_id = $1"]
        params: List[Any] = [project.id]

        start_dt = _parse_time_filter(start)
        end_dt = _parse_time_filter(end)
        if start_dt is not None:
            params.append(start_dt)
            clauses.append(f"ts_iso >= ${len(params)}")
        if end_dt is not None:
            params.append(end_dt)
            clauses.append(f"ts_iso <= ${len(params)}")

        if agents:
            placeholders = _append_values(params, [agent for agent in agents if agent])
            if placeholders:
                clauses.append(f"agent IN ({placeholders})")

        if emojis:
            placeholders = _append_values(params, [emoji for emoji in emojis if emoji])
            if placeholders:
                clauses.append(f"emoji IN ({placeholders})")

        if meta_filters:
            for key, value in sorted(meta_filters.items()):
                params.append(json.dumps({key: value}, sort_keys=True))
                clauses.append(f"meta @> ${len(params)}::jsonb")

        where_clause = " AND ".join(clauses)

        rows = await self._fetch(
            f"""
            SELECT id, ts, ts_iso, emoji, agent, message, meta, raw_line, priority, category, confidence
            FROM scribe_entries
            WHERE {where_clause}
            ORDER BY ts_iso DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2};
            """,
            *params,
            fetch_limit,
            offset,
        )

        results: List[Dict[str, Any]] = []
        for row in rows:
            entry = {
                "id": row["id"],
                "ts": self._format_ts(row["ts"]),
                "emoji": row["emoji"],
                "agent": row["agent"],
                "message": row["message"],
                "meta": _coerce_json(row["meta"]),
                "raw_line": row["raw_line"],
                "priority": row.get("priority", "medium"),
                "category": row.get("category"),
                "confidence": row.get("confidence", 1.0),
            }
            if not message_matches(
                entry["message"],
                message,
                mode=message_mode,
                case_sensitive=case_sensitive,
            ):
                continue
            results.append(entry)
            if len(results) >= safe_limit:
                break
        return results

    async def count_entries(
        self,
        project: Union[ProjectRecord, str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        project_record = await self._resolve_project_record(project)
        if project_record is None:
            return 0

        clauses, params = self._build_recent_filter_clauses(project_record.id, filters or {})
        where_clause = " AND ".join(clauses)
        value = await self._fetchval(
            f"""
            SELECT COUNT(*)
            FROM scribe_entries
            WHERE {where_clause};
            """,
            *params,
        )
        return int(value or 0)

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
        clauses = ["project_id = $1"]
        params: List[Any] = [project.id]

        start_dt = _parse_time_filter(start)
        end_dt = _parse_time_filter(end)
        if start_dt is not None:
            params.append(start_dt)
            clauses.append(f"ts_iso >= ${len(params)}")
        if end_dt is not None:
            params.append(end_dt)
            clauses.append(f"ts_iso <= ${len(params)}")

        if agents:
            placeholders = _append_values(params, [agent for agent in agents if agent])
            if placeholders:
                clauses.append(f"agent IN ({placeholders})")

        if emojis:
            placeholders = _append_values(params, [emoji for emoji in emojis if emoji])
            if placeholders:
                clauses.append(f"emoji IN ({placeholders})")

        if meta_filters:
            for key, value in sorted(meta_filters.items()):
                params.append(json.dumps({key: value}, sort_keys=True))
                clauses.append(f"meta @> ${len(params)}::jsonb")

        where_clause = " AND ".join(clauses)
        value = await self._fetchval(
            f"""
            SELECT COUNT(*)
            FROM scribe_entries
            WHERE {where_clause};
            """,
            *params,
        )
        total = int(value or 0)

        if not message:
            return total

        fetch_limit = min(total, 10000)
        rows = await self._fetch(
            f"""
            SELECT message
            FROM scribe_entries
            WHERE {where_clause}
            LIMIT ${len(params) + 1};
            """,
            *params,
            fetch_limit,
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
        row = await self._fetchrow(
            """
            INSERT INTO dev_plans (project_id, project_name, plan_type, file_path, version, metadata, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
            ON CONFLICT(project_id, plan_type) DO UPDATE SET
                file_path = EXCLUDED.file_path,
                version = EXCLUDED.version,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id, project_id, project_name, plan_type, file_path, version, created_at, updated_at, metadata;
            """,
            project_id,
            project_name,
            plan_type,
            file_path,
            version,
            json.dumps(metadata or {}, sort_keys=True),
        )
        assert row is not None
        return DevPlanRecord(
            id=row["id"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            plan_type=row["plan_type"],
            file_path=row["file_path"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=_coerce_json(row["metadata"]) if row["metadata"] is not None else None,
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
        row = await self._fetchrow(
            """
            INSERT INTO phases (
                project_id, dev_plan_id, phase_number, phase_name, status,
                start_date, end_date, deliverables_count, deliverables_completed,
                confidence_score, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
            ON CONFLICT(project_id, phase_number) DO UPDATE SET
                phase_name = EXCLUDED.phase_name,
                status = EXCLUDED.status,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                deliverables_count = EXCLUDED.deliverables_count,
                deliverables_completed = EXCLUDED.deliverables_completed,
                confidence_score = EXCLUDED.confidence_score,
                metadata = EXCLUDED.metadata
            RETURNING id, project_id, dev_plan_id, phase_number, phase_name, status,
                      start_date, end_date, deliverables_count, deliverables_completed,
                      confidence_score, metadata;
            """,
            project_id,
            dev_plan_id,
            phase_number,
            phase_name,
            status,
            _parse_time_filter(start_date),
            _parse_time_filter(end_date),
            deliverables_count,
            deliverables_completed,
            confidence_score,
            json.dumps(metadata or {}, sort_keys=True),
        )
        assert row is not None
        return PhaseRecord(
            id=row["id"],
            project_id=row["project_id"],
            dev_plan_id=row["dev_plan_id"],
            phase_number=row["phase_number"],
            phase_name=row["phase_name"],
            status=row["status"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            deliverables_count=row["deliverables_count"],
            deliverables_completed=row["deliverables_completed"],
            confidence_score=row["confidence_score"],
            metadata=_coerce_json(row["metadata"]) if row["metadata"] is not None else None,
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
        requirement_met = (
            requirement_target is not None
            and (
                (benchmark_type in ["throughput", "hash_performance"] and metric_value >= requirement_target)
                or (benchmark_type in ["latency", "time"] and metric_value <= requirement_target)
                or (requirement_target > 0 and metric_value <= requirement_target)
                or (requirement_target < 0 and metric_value >= requirement_target)
            )
        )
        row = await self._fetchrow(
            """
            INSERT INTO benchmarks (
                project_id, benchmark_type, test_name, metric_name, metric_value, metric_unit,
                test_parameters, environment_info, requirement_target, requirement_met
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10)
            RETURNING id, project_id, benchmark_type, test_name, metric_name, metric_value,
                      metric_unit, test_parameters, environment_info, test_timestamp,
                      requirement_target, requirement_met;
            """,
            project_id,
            benchmark_type,
            test_name,
            metric_name,
            metric_value,
            metric_unit,
            json.dumps(test_parameters or {}, sort_keys=True),
            json.dumps(environment_info or {}, sort_keys=True),
            requirement_target,
            requirement_met,
        )
        assert row is not None
        return BenchmarkRecord(
            id=row["id"],
            project_id=row["project_id"],
            benchmark_type=row["benchmark_type"],
            test_name=row["test_name"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            test_parameters=_coerce_json(row["test_parameters"]) if row["test_parameters"] is not None else None,
            environment_info=_coerce_json(row["environment_info"]) if row["environment_info"] is not None else None,
            test_timestamp=row["test_timestamp"],
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
        params: List[Any] = [project_id]
        query = """
            SELECT id, project_id, benchmark_type, test_name, metric_name, metric_value,
                   metric_unit, test_parameters, environment_info, test_timestamp,
                   requirement_target, requirement_met
            FROM benchmarks
            WHERE project_id = $1
        """
        if benchmark_type:
            params.append(benchmark_type)
            query += f" AND benchmark_type = ${len(params)}"
        params.append(limit)
        query += f" ORDER BY test_timestamp DESC LIMIT ${len(params)}"

        rows = await self._fetch(query, *params)
        return [
            BenchmarkRecord(
                id=row["id"],
                project_id=row["project_id"],
                benchmark_type=row["benchmark_type"],
                test_name=row["test_name"],
                metric_name=row["metric_name"],
                metric_value=row["metric_value"],
                metric_unit=row["metric_unit"],
                test_parameters=_coerce_json(row["test_parameters"]) if row["test_parameters"] is not None else None,
                environment_info=_coerce_json(row["environment_info"]) if row["environment_info"] is not None else None,
                test_timestamp=row["test_timestamp"],
                requirement_target=row["requirement_target"],
                requirement_met=bool(row["requirement_met"]),
            )
            for row in rows
        ]

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
        improvement_percentage = None
        if baseline_value is not None and baseline_value != 0:
            improvement_percentage = ((metric_value - baseline_value) / abs(baseline_value)) * 100

        row = await self._fetchrow(
            """
            INSERT INTO performance_metrics (
                project_id, metric_category, metric_name, metric_value, metric_unit,
                baseline_value, improvement_percentage, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            RETURNING id, project_id, metric_category, metric_name, metric_value, metric_unit,
                      baseline_value, improvement_percentage, collection_timestamp, metadata;
            """,
            project_id,
            metric_category,
            metric_name,
            metric_value,
            metric_unit,
            baseline_value,
            improvement_percentage,
            json.dumps(metadata or {}, sort_keys=True),
        )
        assert row is not None
        return PerformanceMetricsRecord(
            id=row["id"],
            project_id=row["project_id"],
            metric_category=row["metric_category"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            baseline_value=row["baseline_value"],
            improvement_percentage=row["improvement_percentage"],
            collection_timestamp=row["collection_timestamp"],
            metadata=_coerce_json(row["metadata"]) if row["metadata"] is not None else None,
        )

    async def upsert_agent_session(
        self,
        agent_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        _ = metadata
        identity_string = f"{agent_id}:{session_id}:legacy"
        identity_key = hashlib.sha256(identity_string.encode("utf-8")).hexdigest()
        await self._execute(
            """
            INSERT INTO agent_sessions (
                session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, created_at, last_active_at
            )
            VALUES ($1, $2, $3, $4, 'legacy', 'project', 'legacy', NOW(), NOW())
            ON CONFLICT(session_id) DO UPDATE SET
                last_active_at = NOW();
            """,
            session_id,
            identity_key,
            agent_id,
            agent_id,
        )

    async def fetch_agent_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchrow(
            """
            SELECT
                session_id, identity_key, agent_name, agent_key, repo_root,
                mode, scope_key, created_at, last_active_at, expires_at,
                recent_tools, session_started_at, last_activity_at
            FROM agent_sessions
            WHERE session_id = $1
            LIMIT 1;
            """,
            session_id,
        )
        if not row:
            return None

        return {
            "session_id": row["session_id"],
            "identity_key": row["identity_key"],
            "agent_name": row["agent_name"],
            "agent_key": row["agent_key"],
            "repo_root": row["repo_root"],
            "mode": row["mode"],
            "scope_key": row["scope_key"],
            "created_at": _to_iso(row["created_at"]),
            "last_active_at": _to_iso(row["last_active_at"]),
            "expires_at": _to_iso(row["expires_at"]),
            "recent_tools": _coerce_json_list(row["recent_tools"]),
            "session_started_at": _to_iso(row["session_started_at"]),
            "last_activity_at": _to_iso(row["last_activity_at"]),
        }

    async def upsert_session(
        self,
        *,
        session_id: str,
        transport_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        repo_root: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        mode_value = mode if mode in ("sentinel", "project") else "sentinel"
        normalized_repo = normalize_repo_root(repo_root) if repo_root else None
        try:
            await self._execute(
                """
                INSERT INTO scribe_sessions (
                    session_id, transport_session_id, agent_id, repo_root, mode, started_at, last_active_at
                )
                VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
                ON CONFLICT(session_id) DO UPDATE SET
                    transport_session_id = COALESCE(EXCLUDED.transport_session_id, scribe_sessions.transport_session_id),
                    agent_id = COALESCE(EXCLUDED.agent_id, scribe_sessions.agent_id),
                    repo_root = COALESCE(EXCLUDED.repo_root, scribe_sessions.repo_root),
                    mode = EXCLUDED.mode,
                    last_active_at = NOW();
                """,
                session_id,
                transport_session_id,
                agent_id,
                normalized_repo,
                mode_value,
            )
        except asyncpg.UniqueViolationError as exc:
            if "idx_scribe_sessions_transport" in str(exc) or "transport_session_id" in str(exc):
                raise ConflictError(
                    "transport_session_id collision detected; refusing ambiguous session binding"
                ) from exc
            raise

    async def set_session_mode(self, session_id: str, mode: str) -> None:
        if mode not in ("sentinel", "project"):
            return
        await self._execute(
            """
            UPDATE scribe_sessions
            SET mode = $1, last_active_at = NOW()
            WHERE session_id = $2;
            """,
            mode,
            session_id,
        )

    async def get_session_mode(self, session_id: str) -> Optional[str]:
        value = await self._fetchval(
            "SELECT mode FROM scribe_sessions WHERE session_id = $1;",
            session_id,
        )
        return str(value) if value else None

    async def set_session_project(self, session_id: str, project_name: Optional[str]) -> None:
        exists = await self._fetchval(
            "SELECT 1 FROM scribe_sessions WHERE session_id = $1;",
            session_id,
        )
        if not exists:
            raise ConflictError(
                f"Cannot bind project for unknown session_id={session_id!r}"
            )
        await self._execute(
            """
            INSERT INTO session_projects (session_id, project_name, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT(session_id) DO UPDATE SET
                project_name = EXCLUDED.project_name,
                updated_at = NOW();
            """,
            session_id,
            project_name,
        )

    async def get_session_project(self, session_id: str) -> Optional[str]:
        value = await self._fetchval(
            "SELECT project_name FROM session_projects WHERE session_id = $1;",
            session_id,
        )
        return str(value) if value else None

    async def get_session_by_transport(self, transport_session_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchrow(
            """
            WITH matches AS (
                SELECT session_id, transport_session_id, agent_id, repo_root, mode
                FROM scribe_sessions
                WHERE transport_session_id = $1
                ORDER BY last_active_at DESC
                LIMIT 2
            )
            SELECT session_id, transport_session_id, agent_id, repo_root, mode
            FROM matches
            WHERE (SELECT COUNT(*) FROM matches) = 1
            LIMIT 1;
            """,
            transport_session_id,
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
        await self._execute(
            """
            INSERT INTO agent_recent_projects (agent_id, project_name, last_access_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT(agent_id, project_name) DO UPDATE SET
                last_access_at = NOW();
            """,
            agent_id,
            project_name,
        )

    async def heartbeat_session(self, session_id: str) -> None:
        await self._execute(
            """
            UPDATE agent_sessions
            SET last_active_at = NOW()
            WHERE session_id = $1;
            """,
            session_id,
        )

    async def end_session(self, session_id: str) -> None:
        await self._execute(
            """
            UPDATE agent_sessions
            SET expires_at = NOW(), last_active_at = NOW()
            WHERE session_id = $1;
            """,
            session_id,
        )
        await self._execute(
            """
            UPDATE scribe_sessions
            SET transport_session_id = NULL, last_active_at = NOW()
            WHERE session_id = $1;
            """,
            session_id,
        )

    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchrow(
            """
            SELECT agent_id, project_name, version, updated_at, updated_by, session_id
            FROM agent_projects
            WHERE agent_id = $1;
            """,
            agent_id,
        )
        if not row:
            return None
        return {
            "agent_id": row["agent_id"],
            "project_name": row["project_name"],
            "version": row["version"],
            "updated_at": _to_iso(row["updated_at"]),
            "updated_by": row["updated_by"],
            "session_id": row["session_id"],
        }

    async def set_agent_project(
        self,
        agent_id: str,
        project_name: Optional[str],
        expected_version: Optional[int],
        updated_by: str,
        session_id: str,
    ) -> Dict[str, Any]:
        if expected_version is not None:
            row = await self._fetchrow(
                """
                UPDATE agent_projects
                SET project_name = $1,
                    version = version + 1,
                    updated_at = NOW(),
                    updated_by = $2,
                    session_id = $3
                WHERE agent_id = $4 AND version = $5
                RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
                """,
                project_name,
                updated_by,
                session_id,
                agent_id,
                expected_version,
            )
            if not row:
                raise ConflictError(
                    f"Version conflict for agent {agent_id}: expected version {expected_version}"
                )
        else:
            row = await self._fetchrow(
                """
                INSERT INTO agent_projects (agent_id, project_name, version, updated_at, updated_by, session_id)
                VALUES ($1, $2, 1, NOW(), $3, $4)
                ON CONFLICT(agent_id) DO UPDATE SET
                    project_name = EXCLUDED.project_name,
                    version = agent_projects.version + 1,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by,
                    session_id = EXCLUDED.session_id
                RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
                """,
                agent_id,
                project_name,
                updated_by,
                session_id,
            )
        assert row is not None
        return {
            "agent_id": row["agent_id"],
            "project_name": row["project_name"],
            "version": row["version"],
            "updated_at": _to_iso(row["updated_at"]),
            "updated_by": row["updated_by"],
            "session_id": row["session_id"],
        }

    async def update_session_activity(
        self,
        session_id: str,
        tool_name: str,
        timestamp: str,
    ) -> None:
        row = await self._fetchrow(
            """
            SELECT recent_tools, session_started_at
            FROM agent_sessions
            WHERE session_id = $1;
            """,
            session_id,
        )
        if not row:
            return

        recent_tools = _coerce_json_list(row.get("recent_tools"))
        recent_tools.insert(0, tool_name)
        recent_tools = recent_tools[:10]

        parsed_ts = _parse_time_filter(timestamp) or utcnow()
        session_started = row["session_started_at"] or parsed_ts

        await self._execute(
            """
            UPDATE agent_sessions
            SET recent_tools = $1::jsonb,
                last_activity_at = $2,
                session_started_at = $3
            WHERE session_id = $4;
            """,
            json.dumps(recent_tools),
            parsed_ts,
            session_started,
            session_id,
        )

    async def get_session_activity(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchrow(
            """
            SELECT recent_tools, session_started_at, last_activity_at
            FROM agent_sessions
            WHERE session_id = $1;
            """,
            session_id,
        )
        if not row:
            return None
        return {
            "recent_tools": _coerce_json_list(row.get("recent_tools")),
            "session_started_at": _to_iso(row.get("session_started_at")),
            "last_activity_at": _to_iso(row.get("last_activity_at")),
        }

    async def get_or_create_agent_session(
        self,
        identity_key: str,
        agent_name: str,
        agent_key: str,
        repo_root: str,
        mode: str,
        scope_key: str,
        ttl_hours: int = 24,
    ) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        existing = await self._fetchrow(
            """
            SELECT session_id
            FROM agent_sessions
            WHERE identity_key = $1;
            """,
            identity_key,
        )
        if existing and existing["session_id"]:
            await self._execute(
                """
                UPDATE agent_sessions
                SET last_active_at = NOW(),
                    expires_at = $1
                WHERE identity_key = $2;
                """,
                expires_at,
                identity_key,
            )
            return str(existing["session_id"])

        session_id = str(uuid.uuid4())
        row = await self._fetchrow(
            """
            INSERT INTO agent_sessions (
                session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key,
                created_at, last_active_at, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW(), $8)
            ON CONFLICT(identity_key) DO UPDATE SET
                last_active_at = NOW(),
                expires_at = EXCLUDED.expires_at
            RETURNING session_id;
            """,
            session_id,
            identity_key,
            agent_name,
            agent_key,
            normalize_repo_root(repo_root),
            mode,
            scope_key,
            expires_at,
        )
        if row and row["session_id"]:
            return str(row["session_id"])

        recovery = await self._fetchrow(
            """
            SELECT session_id
            FROM agent_sessions
            WHERE agent_key = $1 AND repo_root = $2 AND mode = $3 AND scope_key = $4
            ORDER BY last_active_at DESC
            LIMIT 1;
            """,
            agent_key,
            normalize_repo_root(repo_root),
            mode,
            scope_key,
        )
        if recovery and recovery["session_id"]:
            return str(recovery["session_id"])

        raise RuntimeError(
            f"Failed to retrieve session for identity_key: {identity_key} "
            f"(agent_key={agent_key}, mode={mode}, scope_key={scope_key})"
        )

    async def cleanup_expired_sessions(self, batch_size: int = 100) -> int:
        row = await self._fetchrow(
            """
            WITH to_delete AS (
                SELECT session_id
                FROM agent_sessions
                WHERE expires_at IS NOT NULL AND expires_at < NOW()
                LIMIT $1
            ),
            deleted AS (
                DELETE FROM agent_sessions
                WHERE session_id IN (SELECT session_id FROM to_delete)
                RETURNING 1
            )
            SELECT COUNT(*)::int AS count
            FROM deleted;
            """,
            batch_size,
        )
        return int(row["count"]) if row else 0

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
        start_time = asyncio.get_running_loop().time()
        await self._execute(
            """
            INSERT INTO reminder_history (
                session_id, reminder_hash, project_root, agent_id, tool_name,
                reminder_key, shown_at, operation_status, context_metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7, $8::jsonb);
            """,
            session_id,
            reminder_hash,
            project_root,
            agent_id,
            tool_name,
            reminder_key,
            operation_status,
            json.dumps(context_metadata or {}, sort_keys=True),
        )
        elapsed_ms = (asyncio.get_running_loop().time() - start_time) * 1000
        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            LOGGER.warning(
                "Slow reminder query: record_reminder_shown took %.2fms (threshold: %.2fms) [session=%s...]",
                elapsed_ms,
                SLOW_QUERY_THRESHOLD_MS,
                session_id[:16],
            )

    async def check_reminder_cooldown(
        self,
        session_id: str,
        reminder_hash: str,
        cooldown_minutes: int = 15,
    ) -> bool:
        start_time = asyncio.get_running_loop().time()
        value = await self._fetchval(
            """
            SELECT COUNT(*)
            FROM reminder_history
            WHERE session_id = $1
              AND reminder_hash = $2
              AND shown_at > NOW() - ($3 * INTERVAL '1 minute');
            """,
            session_id,
            reminder_hash,
            max(int(cooldown_minutes), 0),
        )
        elapsed_ms = (asyncio.get_running_loop().time() - start_time) * 1000
        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            LOGGER.warning(
                "Slow reminder query: check_reminder_cooldown took %.2fms (threshold: %.2fms) [session=%s...]",
                elapsed_ms,
                SLOW_QUERY_THRESHOLD_MS,
                session_id[:16],
            )
        return int(value or 0) > 0

    async def get_reminder_history(
        self,
        *,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        predicates: List[str] = []
        params: List[Any] = []

        if project_root:
            params.append(project_root)
            predicates.append(f"project_root = ${len(params)}")
        if agent_id:
            params.append(agent_id)
            predicates.append(f"agent_id = ${len(params)}")
        if category:
            params.append(f"{category}.%")
            predicates.append(f"reminder_key LIKE ${len(params)}")

        params.append(max(1, min(int(limit), 200)))
        where_sql = " AND ".join(predicates) if predicates else "TRUE"
        limit_placeholder = f"${len(params)}"

        rows = await self._fetch(
            f"""
            SELECT id, session_id, reminder_hash, project_root, agent_id, tool_name,
                   reminder_key, shown_at, operation_status, context_metadata
            FROM reminder_history
            WHERE {where_sql}
            ORDER BY shown_at DESC
            LIMIT {limit_placeholder};
            """,
            *params,
        )

        history: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_context = item.get("context_metadata")
            if isinstance(raw_context, str) and raw_context:
                try:
                    item["context_metadata"] = json.loads(raw_context)
                except json.JSONDecodeError:
                    pass
            history.append(item)
        return history

    async def clear_reminder_history(
        self,
        *,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> int:
        predicates: List[str] = []
        params: List[Any] = []

        if project_root:
            params.append(project_root)
            predicates.append(f"project_root = ${len(params)}")
        if agent_id:
            params.append(agent_id)
            predicates.append(f"agent_id = ${len(params)}")

        where_sql = " AND ".join(predicates) if predicates else "TRUE"
        row = await self._fetchrow(
            f"""
            WITH deleted AS (
                DELETE FROM reminder_history
                WHERE {where_sql}
                RETURNING 1
            )
            SELECT COUNT(*)::int AS count
            FROM deleted;
            """,
            *params,
        )
        return int(row["count"]) if row else 0

    async def cleanup_reminder_history(self, cutoff_hours: int = 168) -> int:
        start_time = asyncio.get_running_loop().time()
        row = await self._fetchrow(
            """
            WITH deleted AS (
                DELETE FROM reminder_history
                WHERE shown_at < NOW() - ($1 * INTERVAL '1 hour')
                RETURNING 1
            )
            SELECT COUNT(*)::int AS count
            FROM deleted;
            """,
            max(int(cutoff_hours), 0),
        )
        deleted = int(row["count"]) if row else 0
        elapsed_ms = (asyncio.get_running_loop().time() - start_time) * 1000
        if elapsed_ms > 100.0:
            LOGGER.warning(
                "Slow reminder query: cleanup_reminder_history took %.2fms (threshold: 100.00ms) [deleted=%d records]",
                elapsed_ms,
                deleted,
            )
        return deleted

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
        repo_root: Optional[str] = None,
    ) -> None:
        try:
            await self._execute(
                """
                INSERT INTO tool_calls (
                    session_id, tool_name, timestamp, duration_ms, status,
                    format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root
                )
                VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7, $8, $9, $10);
                """,
                session_id,
                tool_name,
                duration_ms,
                status,
                format_requested,
                project_name,
                agent_id,
                error_message,
                response_size_bytes,
                normalize_repo_root(repo_root) if repo_root else None,
            )
        except Exception as exc:
            LOGGER.error("Failed to record tool call: %s", exc)

    def record_tool_call_sync(
        self,
        *,
        session_id: str,
        tool_name: str,
        duration_ms: Optional[float] = None,
        status: str = "success",
        format_requested: Optional[str] = None,
        project_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
        response_size_bytes: Optional[int] = None,
        repo_root: Optional[str] = None,
    ) -> None:
        async def _write() -> None:
            conn = await asyncpg.connect(
                self._dsn,
                timeout=COMMAND_TIMEOUT_SECONDS,
                command_timeout=COMMAND_TIMEOUT_SECONDS,
            )
            try:
                await conn.execute(
                    """
                    INSERT INTO tool_calls (
                        session_id, tool_name, timestamp, duration_ms, status,
                        format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root
                    )
                    VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7, $8, $9, $10);
                    """,
                    session_id,
                    tool_name,
                    duration_ms,
                    status,
                    format_requested,
                    project_name,
                    agent_id,
                    error_message,
                    response_size_bytes,
                    normalize_repo_root(repo_root) if repo_root else None,
                )
            finally:
                await conn.close()

        try:
            asyncio.run(_write())
        except Exception as exc:
            LOGGER.warning("SQL tool logging failed in background thread: %s", exc)

    async def get_session_tool_calls(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: List[Any] = [session_id]
        query = """
            SELECT id, tool_name, timestamp, duration_ms, status,
                   format_requested, project_name, agent_id, error_message, response_size_bytes, repo_root
            FROM tool_calls
            WHERE session_id = $1
            ORDER BY timestamp DESC
        """
        if limit is not None:
            params.append(int(limit))
            query += f" LIMIT ${len(params)}"
        rows = await self._fetch(query, *params)
        return [
            {
                "id": row["id"],
                "tool_name": row["tool_name"],
                "timestamp": _to_iso(row["timestamp"]),
                "duration_ms": row["duration_ms"],
                "status": row["status"],
                "format_requested": row["format_requested"],
                "project_name": row["project_name"],
                "agent_id": row["agent_id"],
                "error_message": row["error_message"],
                "response_size_bytes": row["response_size_bytes"],
                "repo_root": row["repo_root"],
            }
            for row in rows
        ]

    async def get_tool_metrics(
        self,
        tool_name: Optional[str] = None,
        project_name: Optional[str] = None,
        time_range_hours: Optional[int] = 24,
    ) -> Dict[str, Any]:
        clauses: List[str] = []
        params: List[Any] = []

        if tool_name:
            params.append(tool_name)
            clauses.append(f"tool_name = ${len(params)}")
        if project_name:
            params.append(project_name)
            clauses.append(f"project_name = ${len(params)}")
        if time_range_hours:
            params.append(max(int(time_range_hours), 0))
            clauses.append(f"timestamp >= NOW() - (${len(params)} * INTERVAL '1 hour')")

        where_sql = " AND ".join(clauses) if clauses else "TRUE"
        row = await self._fetchrow(
            f"""
            SELECT
                COUNT(*)::int AS total_calls,
                COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0)::int AS success_count,
                COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0)::int AS error_count,
                AVG(duration_ms) AS avg_duration_ms,
                SUM(response_size_bytes)::bigint AS total_response_bytes,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                    FILTER (WHERE duration_ms IS NOT NULL) AS p95_duration_ms
            FROM tool_calls
            WHERE {where_sql};
            """,
            *params,
        )

        if not row:
            return {
                "total_calls": 0,
                "success_count": 0,
                "error_count": 0,
                "avg_duration_ms": None,
                "total_response_bytes": None,
                "p95_duration_ms": None,
            }

        return {
            "total_calls": int(row["total_calls"] or 0),
            "success_count": int(row["success_count"] or 0),
            "error_count": int(row["error_count"] or 0),
            "avg_duration_ms": float(row["avg_duration_ms"]) if row["avg_duration_ms"] is not None else None,
            "total_response_bytes": int(row["total_response_bytes"]) if row["total_response_bytes"] is not None else None,
            "p95_duration_ms": float(row["p95_duration_ms"]) if row["p95_duration_ms"] is not None else None,
        }

    async def insert_bridge(
        self,
        bridge_id: str,
        name: str,
        version: str,
        manifest_json: str,
        state: str,
    ) -> None:
        await self._execute(
            """
            INSERT INTO scribe_bridges (bridge_id, name, version, manifest_json, state)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT(bridge_id) DO UPDATE SET
                name = EXCLUDED.name,
                version = EXCLUDED.version,
                manifest_json = EXCLUDED.manifest_json,
                state = EXCLUDED.state;
            """,
            bridge_id,
            name,
            version,
            manifest_json,
            state,
        )

    async def update_bridge_state(self, bridge_id: str, state: str) -> None:
        await self._execute(
            """
            UPDATE scribe_bridges
            SET state = $1
            WHERE bridge_id = $2;
            """,
            state,
            bridge_id,
        )

    async def update_bridge_health(
        self,
        bridge_id: str,
        health_json: str,
        error: Optional[str] = None,
    ) -> None:
        await self._execute(
            """
            UPDATE scribe_bridges
            SET health_json = $1::jsonb,
                last_health_check = NOW(),
                last_error = $2
            WHERE bridge_id = $3;
            """,
            health_json,
            error,
            bridge_id,
        )

    async def fetch_bridge(self, bridge_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchrow(
            """
            SELECT bridge_id, name, version, manifest_json, state,
                   health_json, registered_at, last_health_check, last_error
            FROM scribe_bridges
            WHERE bridge_id = $1;
            """,
            bridge_id,
        )
        if not row:
            return None
        return {
            "bridge_id": row["bridge_id"],
            "name": row["name"],
            "version": row["version"],
            "manifest_json": row["manifest_json"],
            "state": row["state"],
            "health_json": row["health_json"],
            "registered_at": _to_iso(row["registered_at"]),
            "last_health_check": _to_iso(row["last_health_check"]),
            "last_error": row["last_error"],
        }

    async def list_bridges(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        if state:
            rows = await self._fetch(
                """
                SELECT bridge_id, name, version, manifest_json, state,
                       health_json, registered_at, last_health_check, last_error
                FROM scribe_bridges
                WHERE state = $1
                ORDER BY registered_at DESC;
                """,
                state,
            )
        else:
            rows = await self._fetch(
                """
                SELECT bridge_id, name, version, manifest_json, state,
                       health_json, registered_at, last_health_check, last_error
                FROM scribe_bridges
                ORDER BY registered_at DESC;
                """
            )
        return [
            {
                "bridge_id": row["bridge_id"],
                "name": row["name"],
                "version": row["version"],
                "manifest_json": row["manifest_json"],
                "state": row["state"],
                "health_json": row["health_json"],
                "registered_at": _to_iso(row["registered_at"]),
                "last_health_check": _to_iso(row["last_health_check"]),
                "last_error": row["last_error"],
            }
            for row in rows
        ]

    async def delete_bridge(self, bridge_id: str) -> None:
        await self._execute(
            """
            DELETE FROM scribe_bridges
            WHERE bridge_id = $1;
            """,
            bridge_id,
        )

    async def archive_entries(
        self,
        project_id: Optional[int] = None,
        retention_days: int = 90,
    ) -> int:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        clauses = ["ts_iso < $1"]
        params: List[Any] = [cutoff_date]
        if project_id is not None:
            params.append(project_id)
            clauses.append(f"project_id = ${len(params)}")
        where_clause = " AND ".join(clauses)

        count_value = await self._fetchval(
            f"""
            SELECT COUNT(*)
            FROM scribe_entries
            WHERE {where_clause};
            """,
            *params,
        )
        await self._execute(
            f"""
            INSERT INTO scribe_entries_archive (
                id, project_id, ts, ts_iso, emoji, agent, message, meta,
                raw_line, sha256, log_type, priority, category, confidence
            )
            SELECT
                id, project_id, ts, ts_iso, emoji, agent, message, meta,
                raw_line, sha256, log_type, priority, category, confidence
            FROM scribe_entries
            WHERE {where_clause}
            ON CONFLICT (id) DO NOTHING;
            """,
            *params,
        )
        return int(count_value or 0)

    async def cleanup_old_entries(
        self,
        project_id: Optional[int] = None,
        retention_days: int = 90,
        archive: bool = True,
    ) -> int:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        clauses = ["ts_iso < $1"]
        params: List[Any] = [cutoff_date]
        if project_id is not None:
            params.append(project_id)
            clauses.append(f"project_id = ${len(params)}")
        where_clause = " AND ".join(clauses)

        if archive:
            await self._execute(
                f"""
                INSERT INTO scribe_entries_archive (
                    id, project_id, ts, ts_iso, emoji, agent, message, meta,
                    raw_line, sha256, log_type, priority, category, confidence
                )
                SELECT
                    id, project_id, ts, ts_iso, emoji, agent, message, meta,
                    raw_line, sha256, log_type, priority, category, confidence
                FROM scribe_entries
                WHERE {where_clause}
                ON CONFLICT (id) DO NOTHING;
                """,
                *params,
            )

        count_value = await self._fetchval(
            f"""
            SELECT COUNT(*)
            FROM scribe_entries
            WHERE {where_clause};
            """,
            *params,
        )
        await self._execute(
            f"""
            DELETE FROM scribe_entries
            WHERE {where_clause};
            """,
            *params,
        )
        return int(count_value or 0)

    async def migrate_add_docs_json_column(self) -> bool:
        return await pg_migrations.migrate_add_docs_json_column(
            execute_fn=self._execute,
        )

    async def backfill_docs_json_from_state(self, state_path: Path) -> int:
        return await pg_migrations.backfill_docs_json_from_state(
            execute_fn=self._execute,
            state_path=state_path,
            logger=LOGGER,
        )

    async def _ensure_column(self, table: str, column: str, definition: str) -> None:
        await pg_migrations.ensure_column(
            fetchval_fn=self._fetchval,
            execute_fn=self._execute,
            table=table,
            column=column,
            definition=definition,
            schema_name=self._schema_name,
        )

    async def _migration_completed(self, name: str) -> bool:
        if name in self._completed_migrations:
            return True
        completed = await pg_migrations.migration_completed(self._fetchval, name)
        if completed:
            self._completed_migrations.add(name)
        return completed

    async def _mark_migration_complete(self, name: str) -> None:
        await pg_migrations.mark_migration_complete(self._execute, name)
        self._completed_migrations.add(name)

    async def _run_migration(self, name: str, coro) -> bool:
        return await pg_migrations.run_migration(
            name=name,
            migration_coro=coro,
            fetchval_fn=self._fetchval,
            execute_fn=self._execute,
            logger=LOGGER,
        )

    async def _ensure_pool(self) -> asyncpg.Pool:
        return await self._internals.ensure_pool()

    async def _ensure_schema(self) -> None:
        self._schema_ready = await ensure_schema(
            pool_provider=self._ensure_pool,
            schema_lock=self._schema_lock,
            schema_ready=self._schema_ready,
            schema_name=self._schema_name,
            schema_path=SCHEMA_PATH,
        )

    async def _ensure_repo_scoped_project_identity(self) -> None:
        await self._ensure_column("scribe_projects", "repo_id", "TEXT")
        await self._ensure_column("scribe_projects", "project_key", "TEXT")
        await self._execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_scribe_projects_project_key_unique ON scribe_projects(project_key);"
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_scribe_projects_name_repo_id ON scribe_projects(name, repo_id);"
        )

    async def _backfill_repo_scoped_project_identity_for_row(
        self,
        *,
        row_id: int,
        name: str,
        repo_root: str,
    ) -> None:
        normalized_root = normalize_repo_root(repo_root)
        await self._execute(
            """
            UPDATE scribe_projects
            SET repo_root = $1, repo_id = $2, project_key = $3, updated_at = NOW()
            WHERE id = $4;
            """,
            normalized_root,
            compute_repo_id(normalized_root),
            compute_project_key(repo_root=normalized_root, project_name=name),
            row_id,
        )

    async def _ensure_repo_scope_grants_schema(self) -> None:
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS repo_scope_grants (
                grant_id TEXT PRIMARY KEY,
                authoritative_session_key TEXT NOT NULL,
                repo_root TEXT NOT NULL,
                repo_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        await self._execute(
            """
            CREATE INDEX IF NOT EXISTS idx_repo_scope_grants_expires_at
            ON repo_scope_grants(expires_at);
            """
        )

    async def _ensure_case_registry_schema(self) -> None:
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS case_registry (
                case_id TEXT NOT NULL,
                case_type TEXT NOT NULL,
                project_name TEXT NOT NULL,
                repo_root TEXT NOT NULL,
                repo_id TEXT NOT NULL,
                project_key TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                doc_name TEXT NOT NULL,
                doc_path TEXT NOT NULL,
                title TEXT,
                status TEXT,
                severity TEXT,
                source_tool TEXT,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (project_key, case_id)
            );
            """
        )
        await self._execute(
            "ALTER TABLE case_registry DROP CONSTRAINT IF EXISTS case_registry_pkey;"
        )
        await self._execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'case_registry_project_key_case_id_key'
                ) THEN
                    ALTER TABLE case_registry
                    ADD CONSTRAINT case_registry_project_key_case_id_key UNIQUE(project_key, case_id);
                END IF;
            END
            $$;
            """
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_case_registry_repo_project ON case_registry(repo_id, project_name);"
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_case_registry_case_type ON case_registry(case_type);"
        )
        await self._execute(
            "CREATE INDEX IF NOT EXISTS idx_case_registry_project_key ON case_registry(project_key);"
        )

    async def _execute(self, query: str, *params: Any) -> str:
        await self._ensure_schema()
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *params)

    async def _fetchrow(self, query: str, *params: Any) -> Optional[asyncpg.Record]:
        await self._ensure_schema()
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *params)

    async def _fetch(self, query: str, *params: Any) -> List[asyncpg.Record]:
        await self._ensure_schema()
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def _fetchval(self, query: str, *params: Any) -> Any:
        await self._ensure_schema()
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *params)

    async def _fetch_project_row(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[asyncpg.Record]:
        await self._ensure_repo_scoped_project_identity()
        if project_key:
            return await self._fetchrow(
                """
                SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE project_key = $1;
                """,
                project_key,
            )
        if repo_root:
            scoped_key = compute_project_key(
                repo_root=normalize_repo_root(repo_root),
                project_name=name,
            )
            return await self._fetchrow(
                """
                SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE project_key = $1;
                """,
                scoped_key,
            )

        count = await self._fetchval("SELECT COUNT(*) FROM scribe_projects WHERE name = $1;", name)
        if int(count or 0) > 1:
            return None
        row = await self._fetchrow(
            """
            SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE name = $1;
            """,
            name,
        )
        if row and (not row.get("repo_id") or not row.get("project_key")):
            await self._backfill_repo_scoped_project_identity_for_row(
                row_id=int(row["id"]),
                name=str(row["name"]),
                repo_root=str(row["repo_root"]),
            )
            row = await self._fetchrow(
                """
                SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE id = $1;
                """,
                int(row["id"]),
            )
        if row:
            return row

        canonical = normalize_project_input(name)
        if canonical and canonical != name:
            canonical_count = await self._fetchval(
                "SELECT COUNT(*) FROM scribe_projects WHERE name = $1;",
                canonical,
            )
            if int(canonical_count or 0) > 1:
                return None
                row = await self._fetchrow(
                    """
                    SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = $1;
                    """,
                    canonical,
                )
                if row and (not row.get("repo_id") or not row.get("project_key")):
                    await self._backfill_repo_scoped_project_identity_for_row(
                        row_id=int(row["id"]),
                        name=str(row["name"]),
                        repo_root=str(row["repo_root"]),
                    )
                    row = await self._fetchrow(
                        """
                        SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                        FROM scribe_projects
                        WHERE id = $1;
                        """,
                        int(row["id"]),
                    )
            if row:
                return row

        if "_" in name:
            denormalized = name.replace("_", "-")
            if denormalized != name:
                denormalized_count = await self._fetchval(
                    "SELECT COUNT(*) FROM scribe_projects WHERE name = $1;",
                    denormalized,
                )
                if int(denormalized_count or 0) > 1:
                    return None
                row = await self._fetchrow(
                    """
                    SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = $1;
                    """,
                    denormalized,
                )
                if row and (not row.get("repo_id") or not row.get("project_key")):
                    await self._backfill_repo_scoped_project_identity_for_row(
                        row_id=int(row["id"]),
                        name=str(row["name"]),
                        repo_root=str(row["repo_root"]),
                    )
                    row = await self._fetchrow(
                        """
                        SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, created_at, updated_at, bridge_id, bridge_managed
                        FROM scribe_projects
                        WHERE id = $1;
                        """,
                        int(row["id"]),
                    )
        return row

    def _project_from_row(self, row: asyncpg.Record) -> ProjectRecord:
        return ProjectRecord(
            id=row["id"],
            name=row["name"],
            repo_root=row["repo_root"],
            repo_id=row.get("repo_id"),
            project_key=row.get("project_key"),
            progress_log_path=row["progress_log_path"],
            docs_json=row.get("docs_json"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            bridge_id=row.get("bridge_id"),
            bridge_managed=bool(row.get("bridge_managed", False)),
        )

    def _case_registry_from_row(self, row: asyncpg.Record) -> CaseRegistryRecord:
        return CaseRegistryRecord(
            case_id=str(row["case_id"]),
            case_type=str(row["case_type"]),
            project_name=str(row["project_name"]),
            repo_root=str(row["repo_root"]),
            repo_id=str(row["repo_id"]),
            project_key=str(row["project_key"]),
            doc_type=str(row["doc_type"]),
            doc_name=str(row["doc_name"]),
            doc_path=str(row["doc_path"]),
            title=row.get("title"),
            status=row.get("status"),
            severity=row.get("severity"),
            source_tool=row.get("source_tool"),
            metadata=_coerce_json(row.get("metadata")) if row.get("metadata") is not None else None,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    async def _resolve_project_record(
        self,
        project: Union[ProjectRecord, str],
    ) -> Optional[ProjectRecord]:
        if isinstance(project, ProjectRecord):
            return project
        if isinstance(project, str):
            return await self.fetch_project(project)
        return None

    @staticmethod
    def _format_ts(value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return format_utc(value.astimezone(timezone.utc))
        return value

    @staticmethod
    def _build_recent_filter_clauses(
        project_id: int,
        filters: Dict[str, Any],
    ) -> Tuple[List[str], List[Any]]:
        clauses = ["project_id = $1"]
        params: List[Any] = [project_id]

        agent = filters.get("agent")
        if agent:
            params.append(agent)
            clauses.append(f"agent = ${len(params)}")

        emoji = filters.get("emoji")
        if emoji:
            params.append(emoji)
            clauses.append(f"emoji = ${len(params)}")

        priority = filters.get("priority")
        if priority:
            values = [priority] if isinstance(priority, str) else [item for item in priority if item]
            if values:
                placeholders = _append_values(params, values)
                clauses.append(f"priority IN ({placeholders})")

        category = filters.get("category")
        if category:
            values = [category] if isinstance(category, str) else [item for item in category if item]
            if values:
                placeholders = _append_values(params, values)
                clauses.append(f"category IN ({placeholders})")

        min_confidence = filters.get("min_confidence")
        if min_confidence is not None:
            params.append(float(min_confidence))
            clauses.append(f"confidence >= ${len(params)}")

        log_type = filters.get("log_type")
        if log_type:
            values = [log_type] if isinstance(log_type, str) else [item for item in log_type if item]
            if values:
                placeholders = _append_values(params, values)
                clauses.append(f"log_type IN ({placeholders})")

        return clauses, params
