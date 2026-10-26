from __future__ import annotations

import asyncio
import sqlite3
import pytest
from pathlib import Path

from test_get_project_integration import verified_reader_context
from scribe_mcp import server
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.models import compute_project_key, compute_repo_id, normalize_repo_root
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.storage.sqlite import projects as project_ops


def test_sqlite_migration_backfills_repo_identity_for_legacy_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_projects.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            repo_root TEXT NOT NULL,
            progress_log_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            docs_json TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO scribe_projects (name, repo_root, progress_log_path)
        VALUES (?, ?, ?);
        """,
        ("legacy_project", str(tmp_path / "repo_a"), str(tmp_path / "repo_a" / "PROGRESS_LOG.md")),
    )
    conn.commit()
    conn.close()

    async def _run() -> None:
        storage = SQLiteStorage(db_path)
        try:
            await storage.upsert_project(
                name="new_project",
                repo_root=str(tmp_path / "repo_b"),
                progress_log_path=str(tmp_path / "repo_b" / "PROGRESS_LOG.md"),
            )

            migrated = await storage.fetch_project("legacy_project")
            assert migrated is not None
            expected_root = normalize_repo_root(str(tmp_path / "repo_a"))
            assert migrated.repo_root == expected_root
            assert migrated.repo_id == compute_repo_id(expected_root)
            assert migrated.project_key == compute_project_key(repo_root=expected_root, project_name="legacy_project")
        finally:
            await storage.close()

    asyncio.run(_run())


def test_same_name_in_two_repos_persists_as_two_records(tmp_path: Path) -> None:
    db_path = tmp_path / "scoped_projects.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            repo_root TEXT NOT NULL,
            progress_log_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            docs_json TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    async def _run() -> None:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        async def _initialise() -> None:
            bootstrap = SQLiteStorage(db_path)
            try:
                await bootstrap.setup()
            finally:
                await bootstrap.close()

        async def _execute(query: str, params: tuple[object, ...]) -> None:
            conn.execute(query, params)
            conn.commit()

        async def _fetchone(query: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
            return conn.execute(query, params).fetchone()

        repo_a = str(tmp_path / "repo_a")
        repo_b = str(tmp_path / "repo_b")

        rec_a = await project_ops.upsert_project(
            initialise_fn=_initialise,
            write_lock=asyncio.Lock(),
            execute_fn=_execute,
            fetchone_fn=_fetchone,
            name="shared_name",
            repo_root=repo_a,
            progress_log_path=str(Path(repo_a) / "PROGRESS_LOG.md"),
        )
        rec_b = await project_ops.upsert_project(
            initialise_fn=_initialise,
            write_lock=asyncio.Lock(),
            execute_fn=_execute,
            fetchone_fn=_fetchone,
            name="shared_name",
            repo_root=repo_b,
            progress_log_path=str(Path(repo_b) / "PROGRESS_LOG.md"),
        )

        assert rec_a.project_key != rec_b.project_key

        rows = conn.execute("SELECT name FROM scribe_projects WHERE name = 'shared_name';").fetchall()
        assert len(rows) == 2

        ambiguous = await project_ops.fetch_project(
            initialise_fn=_initialise,
            execute_fn=_execute,
            fetchone_fn=_fetchone,
            name="shared_name",
        )
        assert ambiguous is None

        storage = SQLiteStorage(db_path)
        try:
            resolved_by_repo = await storage.fetch_project("shared_name", repo_root=repo_a)
            assert resolved_by_repo is not None
            assert resolved_by_repo.repo_root == normalize_repo_root(repo_a)
            assert resolved_by_repo.project_key == rec_a.project_key

            resolved_by_key = await storage.fetch_project("shared_name", project_key=rec_b.project_key)
            assert resolved_by_key is not None
            assert resolved_by_key.repo_root == normalize_repo_root(repo_b)
            assert resolved_by_key.project_key == rec_b.project_key
        finally:
            await storage.close()

        conn.close()

    asyncio.run(_run())


def test_sqlite_migration_deconflicts_legacy_canonical_alias_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_alias_duplicates.db"
    repo_root = tmp_path / "repo_a"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            progress_log_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            docs_json TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO scribe_projects (name, repo_root, progress_log_path)
        VALUES (?, ?, ?);
        """,
        [
            ("alias-project", str(repo_root), str(repo_root / "alias-project" / "PROGRESS_LOG.md")),
            ("alias_project", str(repo_root), str(repo_root / "alias_project" / "PROGRESS_LOG.md")),
        ],
    )
    conn.commit()
    conn.close()

    async def _run() -> None:
        storage = SQLiteStorage(db_path)
        try:
            await storage.upsert_project(
                name="new_project",
                repo_root=str(tmp_path / "repo_b"),
                progress_log_path=str(tmp_path / "repo_b" / "PROGRESS_LOG.md"),
            )

            canonical = await storage.fetch_project("alias-project", repo_root=str(repo_root))
            assert canonical is not None
            assert canonical.name == "alias-project"
            assert canonical.project_key == compute_project_key(
                repo_root=str(repo_root),
                project_name="alias-project",
            )

            with sqlite3.connect(str(db_path)) as verify_conn:
                rows = verify_conn.execute(
                    """
                    SELECT project_key
                    FROM scribe_projects
                    WHERE name IN ('alias-project', 'alias_project')
                    ORDER BY id;
                    """
                ).fetchall()

            project_keys = [str(row[0]) for row in rows]
            assert len(project_keys) == 2
            assert len(set(project_keys)) == 2
            assert project_keys[0].startswith("pk_")
            assert project_keys[1].startswith("pk_legacy_")
        finally:
            await storage.close()

    asyncio.run(_run())


@pytest.mark.regression
def test_state_binding_and_project_fetch_share_project_key(tmp_path: Path, monkeypatch, test_agent) -> None:
    """Raw binding identity persists while operational state requires current authority."""
    db_path = tmp_path / "state_scope.db"
    async def _run() -> None:
        storage = SQLiteStorage(db_path)
        manager = StateManager(path=db_path, storage_backend=storage)
        router = RouterContextManager(storage_backend=storage)
        monkeypatch.setattr(server, "router_context_manager", router)
        repo_root = tmp_path / "repo_main"
        repo_root.mkdir()
        try:
            await storage.setup()
            await storage.upsert_session(
                session_id="session-1", repo_root=str(repo_root), agent_id=test_agent,
            )
            await manager.set_session_mode("session-1", "project")
            state = await manager.set_current_project(
                "converged_project",
                {"name": "converged_project", "root": str(repo_root),
                 "progress_log": str(repo_root / "PROGRESS_LOG.md")},
                session_id="session-1",
            )
            assert state.current_project is None
            record = await storage.fetch_project("converged_project", repo_root=str(repo_root))
            binding = await storage.get_session_project("session-1")
            assert record is not None and binding is not None
            assert binding.project_key == record.project_key
            assert binding.canonical_repo_root == str(repo_root)
            context = await verified_reader_context(
                storage, router, repo_root, "session-1", test_agent, record.name,
            )
            token = router.set_current(context)
            try:
                verified = await manager.load()
                assert verified.current_project == record.name
                assert verified.get_session_project("session-1")["project_key"] == record.project_key
                assert verified.get_project(record.name)["root"] == str(repo_root)
            finally:
                router.reset(token)
            assert await storage.get_session_project("session-1") == binding
        finally:
            await storage.close()
    asyncio.run(_run())


def test_sqlite_project_identity_preflight_reports_populated_state(tmp_path: Path) -> None:
    db_path = tmp_path / "preflight_populated_state.db"

    async def _run() -> None:
        storage = SQLiteStorage(db_path)
        try:
            await storage.upsert_project(
                name="preflight_populated",
                repo_root=str(tmp_path / "repo_main"),
                progress_log_path=str(tmp_path / "repo_main" / "PROGRESS_LOG.md"),
            )
            report = await storage.preflight_project_identity_repair()
            payload = report.to_public_dict()

            assert payload["mutation_attempted"] is False
            assert payload["mutation_authorized"] is False
            assert payload["missing_identity_rows"] == 0
            assert payload["partial_identity_rows"] == 0
            assert payload["already_populated_duplicate_project_key_groups"] == 0
        finally:
            await storage.close()

    asyncio.run(_run())
