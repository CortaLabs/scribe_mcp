from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from scribe_mcp.storage.models import compute_project_key, compute_repo_id, normalize_repo_root
from scribe_mcp.storage.sqlite import SQLiteStorage


def test_case_registry_upsert_stores_shared_record_with_repo_project_scope(tmp_path: Path) -> None:
    async def _run() -> None:
        storage = SQLiteStorage(tmp_path / "case-registry.sqlite3")
        await storage.setup()
        try:
            repo_root_input = str(tmp_path / "repo" / ".." / "repo")
            normalized_root = normalize_repo_root(repo_root_input)

            record = await storage.upsert_case_registry_record(
                case_id="BUG-2026-04-17-0001",
                case_type="bug",
                project_name="integrate_bug_management_system_20260417",
                repo_root=repo_root_input,
                doc_type="bug",
                doc_name="BUG-2026-04-17-0001",
                doc_path=".scribe/docs/bugs/BUG-2026-04-17-0001/report.md",
                title="Case registry insert",
                status="open",
                severity="high",
                source_tool="open_bug",
                metadata={"lane": "phase-2.1a"},
            )

            assert record.case_id == "BUG-2026-04-17-0001"
            assert record.case_type == "bug"
            assert record.repo_root == normalized_root
            assert record.repo_id == compute_repo_id(normalized_root)
            assert record.project_key == compute_project_key(
                repo_root=normalized_root,
                project_name="integrate_bug_management_system_20260417",
            )
            assert record.metadata == {"lane": "phase-2.1a"}
        finally:
            await storage.close()

    asyncio.run(_run())


def test_case_registry_upsert_updates_existing_case_record(tmp_path: Path) -> None:
    async def _run() -> None:
        storage = SQLiteStorage(tmp_path / "case-registry-upsert.sqlite3")
        await storage.setup()
        try:
            await storage.upsert_case_registry_record(
                case_id="SEC-2026-04-17-0002",
                case_type="security",
                project_name="integrate_bug_management_system_20260417",
                repo_root=str(tmp_path),
                doc_type="security",
                doc_name="SEC-2026-04-17-0002",
                doc_path=".scribe/docs/security/SEC-2026-04-17-0002/report.md",
                status="open",
                source_tool="open_security",
                metadata={"priority": "p1"},
            )

            updated = await storage.upsert_case_registry_record(
                case_id="SEC-2026-04-17-0002",
                case_type="security",
                project_name="integrate_bug_management_system_20260417",
                repo_root=str(tmp_path),
                doc_type="security",
                doc_name="SEC-2026-04-17-0002",
                doc_path=".scribe/docs/security/SEC-2026-04-17-0002/report.md",
                status="investigating",
                severity="critical",
                source_tool="open_security",
                metadata={"priority": "p0", "owner": "sentinel"},
            )

            assert updated.status == "investigating"
            assert updated.severity == "critical"
            assert updated.metadata == {"owner": "sentinel", "priority": "p0"}

            fetched = await storage.fetch_case_registry_record("SEC-2026-04-17-0002")
            assert fetched is not None
            assert fetched.status == "investigating"
            assert fetched.metadata == {"owner": "sentinel", "priority": "p0"}
        finally:
            await storage.close()

    asyncio.run(_run())


def test_case_registry_query_filters_by_repo_project_and_case_type(tmp_path: Path) -> None:
    async def _run() -> None:
        storage = SQLiteStorage(tmp_path / "case-registry-query.sqlite3")
        await storage.setup()
        try:
            repo_a = str(tmp_path / "repo-a")
            repo_b = str(tmp_path / "repo-b")
            project = "integrate_bug_management_system_20260417"

            await storage.upsert_case_registry_record(
                case_id="BUG-2026-04-17-0101",
                case_type="bug",
                project_name=project,
                repo_root=repo_a,
                doc_type="bug",
                doc_name="BUG-2026-04-17-0101",
                doc_path=".scribe/docs/bugs/BUG-2026-04-17-0101/report.md",
            )
            await storage.upsert_case_registry_record(
                case_id="SEC-2026-04-17-0102",
                case_type="security",
                project_name=project,
                repo_root=repo_a,
                doc_type="security",
                doc_name="SEC-2026-04-17-0102",
                doc_path=".scribe/docs/security/SEC-2026-04-17-0102/report.md",
            )
            await storage.upsert_case_registry_record(
                case_id="BUG-2026-04-17-0103",
                case_type="bug",
                project_name=project,
                repo_root=repo_b,
                doc_type="bug",
                doc_name="BUG-2026-04-17-0103",
                doc_path=".scribe/docs/bugs/BUG-2026-04-17-0103/report.md",
            )

            scoped = await storage.query_case_registry_records(
                repo_root=repo_a,
                project_name=project,
                case_type="bug",
            )

            assert [item.case_id for item in scoped] == ["BUG-2026-04-17-0101"]
        finally:
            await storage.close()

    asyncio.run(_run())


def test_case_registry_allows_same_case_id_across_distinct_project_scopes(tmp_path: Path) -> None:
    async def _run() -> None:
        storage = SQLiteStorage(tmp_path / "case-registry-scope.sqlite3")
        await storage.setup()
        try:
            repo_root = str(tmp_path / "repo")
            case_id = "BUG-2026-05-15-0001"

            await storage.upsert_case_registry_record(
                case_id=case_id,
                case_type="bug",
                project_name="project_alpha",
                repo_root=repo_root,
                doc_type="bug",
                doc_name=case_id,
                doc_path=".scribe/docs/bugs/project_alpha/report.md",
                status="open",
                metadata={"owner": "alpha"},
            )
            await storage.upsert_case_registry_record(
                case_id=case_id,
                case_type="bug",
                project_name="project_beta",
                repo_root=repo_root,
                doc_type="bug",
                doc_name=case_id,
                doc_path=".scribe/docs/bugs/project_beta/report.md",
                status="open",
                metadata={"owner": "beta"},
            )

            alpha = await storage.fetch_case_registry_record(
                case_id,
                repo_root=repo_root,
                project_name="project_alpha",
            )
            beta = await storage.fetch_case_registry_record(
                case_id,
                repo_root=repo_root,
                project_name="project_beta",
            )
            assert alpha is not None and beta is not None
            assert alpha.metadata == {"owner": "alpha"}
            assert beta.metadata == {"owner": "beta"}
        finally:
            await storage.close()

    asyncio.run(_run())


def test_case_registry_upsert_readback_respects_project_scope_with_duplicate_case_id(tmp_path: Path) -> None:
    async def _run() -> None:
        storage = SQLiteStorage(tmp_path / "case-registry-upsert-readback-scope.sqlite3")
        await storage.setup()
        try:
            repo_root = str(tmp_path / "repo")
            case_id = "BUG-2026-05-15-0002"

            await storage.upsert_case_registry_record(
                case_id=case_id,
                case_type="bug",
                project_name="project_alpha",
                repo_root=repo_root,
                doc_type="bug",
                doc_name=case_id,
                doc_path=".scribe/docs/bugs/project_alpha/report.md",
                status="open",
                metadata={"owner": "alpha"},
            )

            await storage.upsert_case_registry_record(
                case_id=case_id,
                case_type="bug",
                project_name="project_beta",
                repo_root=repo_root,
                doc_type="bug",
                doc_name=case_id,
                doc_path=".scribe/docs/bugs/project_beta/report.md",
                status="open",
                metadata={"owner": "beta"},
            )

            updated_alpha = await storage.upsert_case_registry_record(
                case_id=case_id,
                case_type="bug",
                project_name="project_alpha",
                repo_root=repo_root,
                doc_type="bug",
                doc_name=case_id,
                doc_path=".scribe/docs/bugs/project_alpha/report.md",
                status="investigating",
                metadata={"owner": "alpha", "state": "updated"},
            )

            assert updated_alpha.project_name == "project_alpha"
            assert updated_alpha.status == "investigating"
            assert updated_alpha.metadata == {"owner": "alpha", "state": "updated"}
        finally:
            await storage.close()

    asyncio.run(_run())


def test_case_registry_migrates_legacy_case_id_primary_key_without_metadata_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "case-registry-legacy.sqlite3"
    repo_root = str(tmp_path / "repo")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE case_registry (
                case_id TEXT PRIMARY KEY,
                case_type TEXT NOT NULL,
                project_name TEXT NOT NULL,
                repo_root TEXT NOT NULL,
                repo_id TEXT NOT NULL,
                project_key TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                doc_name TEXT NOT NULL,
                doc_path TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL,
                severity TEXT,
                source_tool TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO case_registry (
                case_id, case_type, project_name, repo_root, repo_id, project_key, doc_type,
                doc_name, doc_path, title, status, severity, source_tool, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "BUG-2026-05-15-0420",
                "bug",
                "legacy_project",
                repo_root,
                "legacy-repo-id",
                "legacy-project-key",
                "bug",
                "BUG-2026-05-15-0420",
                ".scribe/docs/bugs/legacy/report.md",
                "Legacy title",
                "open",
                "high",
                "open_bug",
                '{"owner":"legacy"}',
                "2026-05-15T00:00:00Z",
                "2026-05-15T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    async def _run() -> None:
        storage = SQLiteStorage(db_path)
        await storage.setup()
        try:
            migrated = await storage.fetch_case_registry_record(
                "BUG-2026-05-15-0420",
                repo_root=repo_root,
                project_name="legacy_project",
            )
            assert migrated is not None
            assert migrated.title == "Legacy title"
            assert migrated.metadata == {"owner": "legacy"}

            await storage.upsert_case_registry_record(
                case_id="BUG-2026-05-15-0420",
                case_type="bug",
                project_name="new_project_same_case_id",
                repo_root=repo_root,
                doc_type="bug",
                doc_name="BUG-2026-05-15-0420",
                doc_path=".scribe/docs/bugs/new/report.md",
                status="open",
                metadata={"owner": "new"},
            )

            legacy = await storage.fetch_case_registry_record(
                "BUG-2026-05-15-0420",
                repo_root=repo_root,
                project_name="legacy_project",
            )
            new = await storage.fetch_case_registry_record(
                "BUG-2026-05-15-0420",
                repo_root=repo_root,
                project_name="new_project_same_case_id",
            )

            assert legacy is not None and new is not None
            assert legacy.metadata == {"owner": "legacy"}
            assert new.metadata == {"owner": "new"}
        finally:
            await storage.close()

    asyncio.run(_run())
