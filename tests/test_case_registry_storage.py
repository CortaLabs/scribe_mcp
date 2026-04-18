from __future__ import annotations

import asyncio
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
