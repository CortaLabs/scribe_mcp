from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import types
from typing import Any
from unittest.mock import patch

import pytest

os.environ["SCRIBE_MODE"] = "standalone"
os.environ["SCRIBE_STORAGE_BACKEND"] = "sqlite"

if "httpx" not in sys.modules:
    httpx_stub = types.SimpleNamespace(
        AsyncClient=object,
        ConnectError=Exception,
        TimeoutException=Exception,
    )
    sys.modules["httpx"] = httpx_stub

if "mcp" not in sys.modules:
    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    mcp_types_module = types.ModuleType("mcp.types")

    class _ServerStub:
        def __init__(self, _name: str) -> None:
            self.state = SimpleNamespace()

        def tool(self, _func=None, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

        def list_tools(self, *args, **kwargs):
            def _decorator(func):
                return func

            return _decorator

        def call_tool(self, *args, **kwargs):
            def _decorator(func):
                return func

            return _decorator

    mcp_server_module.Server = _ServerStub
    mcp_server_module.stdio = SimpleNamespace(stdio_server=lambda: None)
    mcp_module.server = mcp_server_module
    mcp_module.types = mcp_types_module
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = mcp_server_module
    sys.modules["mcp.types"] = mcp_types_module

from scribe_mcp import server as server_module
from scribe_mcp.doc_management import runtime as doc_runtime
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools import sentinel_tools
from scribe_mcp.tools.list_open_cases import list_open_cases


def _context(*, repo_root: Path, project_name: str, session_key: str, execution_id: str) -> Any:
    resolved_root = str(repo_root.resolve())
    return SimpleNamespace(
        mode="project",
        repo_root=resolved_root,
        execution_id=execution_id,
        parent_execution_id=None,
        stable_session_id=session_key,
        authoritative_session_key=session_key,
        resolved_scope=SimpleNamespace(
            authoritative_session_key=session_key,
            stable_session_id=session_key,
            repo_root=resolved_root,
            project_name=project_name,
            trust_level="verified",
            resolution_source="runtime_context",
            provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
        ),
    )


def _write_report(*, path: Path, doc_type: str, case_id: str, title: str, status: str, category: str, severity: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"doc_type: {doc_type}\n"
        f"case_id: {case_id}\n"
        f"title: {title}\n"
        f"status: {status}\n"
        f"category: {category}\n"
        f"severity: {severity}\n"
        "---\n\n"
        "# Report\n",
        encoding="utf-8",
    )


def test_phase2_package_2_3_sqlite_end_to_end_registry_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        repo_a = tmp_path / "repo-a"
        repo_b = tmp_path / "repo-b"
        repo_a.mkdir(parents=True)
        repo_b.mkdir(parents=True)
        (repo_a / ".git").mkdir()
        (repo_b / ".git").mkdir()
        project_name = "integrate_bug_management_system_20260417"

        storage = SQLiteStorage(tmp_path / "phase2_case_registry_contract.db")
        await storage.setup()

        active_context = _context(
            repo_root=repo_a,
            project_name=project_name,
            session_key="session-a",
            execution_id="exec-a",
        )

        async def _append_entry(**_kwargs: Any) -> dict[str, Any]:
            repo_root = Path(str(server_module.get_execution_context().repo_root))
            progress = repo_root / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md"
            progress.parent.mkdir(parents=True, exist_ok=True)
            return {
                "ok": True,
                "id": f"entry-{repo_root.name}",
                "path": str(progress),
                "paths": [str(progress)],
                "project_name": project_name,
            }

        async def _manage_docs(**kwargs: Any) -> dict[str, Any]:
            action = str(kwargs.get("action", ""))
            if action == "create":
                metadata = kwargs.get("metadata", {}) or {}
                case_id = str(metadata.get("case_id", "UNKNOWN"))
                doc_type = str(metadata.get("doc_type", "bug"))
                category = str(metadata.get("category", "runtime"))
                severity = str(metadata.get("severity", "medium"))
                root = Path(str(server_module.get_execution_context().repo_root))
                case_dir = "security" if doc_type == "security" else "bugs"
                report = root / "docs" / case_dir / category / f"2026-04-18_{case_id}" / "report.md"
                _write_report(
                    path=report,
                    doc_type=doc_type,
                    case_id=case_id,
                    title=str(metadata.get("title", case_id)),
                    status="open",
                    category=category,
                    severity=severity,
                )
                return {"ok": True, "path": str(report)}
            if action == "replace_section":
                return {"ok": True, "path": str(kwargs.get("doc_name", ""))}
            return {"ok": False, "error": f"unexpected action {action}"}

        monkeypatch.setattr(server_module, "storage_backend", storage)
        monkeypatch.setattr(server_module, "get_execution_context", lambda: active_context)

        with (
            patch("scribe_mcp.tools.append_entry.append_entry", side_effect=_append_entry),
            patch("scribe_mcp.tools.manage_docs.manage_docs", side_effect=_manage_docs),
            patch(
                "scribe_mcp.tools.sentinel_tools._next_case_id_for_project",
                side_effect=["BUG-2026-04-18-0001", "SEC-2026-04-18-0001"],
            ),
        ):
            bug = await sentinel_tools.open_bug(
                agent="test-agent",
                title="registry bug",
                symptoms="bug symptoms",
                category="runtime",
                severity="high",
            )
            security = await sentinel_tools.open_security(
                agent="test-agent",
                title="registry security",
                symptoms="security symptoms",
                category="auth",
                severity="critical",
            )

            assert bug["ok"] is True
            assert security["ok"] is True

            open_bugs = await list_open_cases(case_type="bug", severity="high", limit=10)
            assert open_bugs["ok"] is True
            assert {item["case_id"] for item in open_bugs["cases"]} == {"BUG-2026-04-18-0001"}

            # Simulate governed report mutation and force runtime registry refresh against real SQLite.
            bug_report = repo_a / "docs" / "bugs" / "runtime" / "2026-04-18_BUG-2026-04-18-0001" / "report.md"
            _write_report(
                path=bug_report,
                doc_type="bug",
                case_id="BUG-2026-04-18-0001",
                title="registry bug",
                status="investigating",
                category="runtime",
                severity="high",
            )

            warning = await doc_runtime._refresh_case_registry_for_mutation(
                storage_backend=storage,
                project={"name": project_name, "root": str(repo_a), "docs": {}},
                response={"path": str(bug_report)},
                doc_name="BUG-2026-04-18-0001",
                doc_category="bug",
            )
            assert warning is None
            post_mutation_filtered = await list_open_cases(
                case_type="bug",
                category="runtime",
                severity="high",
                limit=10,
            )
            assert post_mutation_filtered["ok"] is True
            assert [item["case_id"] for item in post_mutation_filtered["cases"]] == ["BUG-2026-04-18-0001"]

            # Wrong-repo fix linking must fail even when project names are identical across repos.
            active_context = _context(
                repo_root=repo_b,
                project_name=project_name,
                session_key="session-b",
                execution_id="exec-b",
            )
            denied = await sentinel_tools.link_fix(
                agent="test-agent",
                case_id="BUG-2026-04-18-0001",
                execution_id="exec-b",
                artifact_ref="src/feature.py:11",
                landing_status="merged",
            )
            assert denied["ok"] is False
            assert "repo ownership mismatch" in denied["error"]

            active_context = _context(
                repo_root=repo_a,
                project_name=project_name,
                session_key="session-a",
                execution_id="exec-a",
            )
            linked = await sentinel_tools.link_fix(
                agent="test-agent",
                case_id="BUG-2026-04-18-0001",
                execution_id="exec-a",
                artifact_ref="src/feature.py:22",
                landing_status="merged",
            )
            assert linked["ok"] is True
            assert linked["warnings"] == []

        record = await storage.fetch_case_registry_record("BUG-2026-04-18-0001")
        assert record is not None
        assert record.metadata["category"] == "runtime"
        assert record.metadata["fix_link"] == {
            "execution_id": "exec-a",
            "artifact_ref": "src/feature.py:22",
            "landing_status": "merged",
        }
        assert record.metadata["execution_provenance"]["execution_id"] == "exec-a"
        assert record.metadata["execution_provenance"]["stable_session_id"] == "session-a"

        filtered_after_link = await list_open_cases(case_type="bug", category="runtime", severity="high", limit=10)
        assert filtered_after_link["ok"] is True
        assert [item["case_id"] for item in filtered_after_link["cases"]] == ["BUG-2026-04-18-0001"]

        await storage.close()

    import asyncio

    asyncio.run(_run())


def test_phase2_package_2_3_link_fix_partial_doc_update_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        repo_root = tmp_path / "repo-partial"
        repo_root.mkdir(parents=True)
        (repo_root / ".git").mkdir()
        project_name = "integrate_bug_management_system_20260417"

        storage = SQLiteStorage(tmp_path / "phase2_case_registry_partial.db")
        await storage.setup()

        active_context = _context(
            repo_root=repo_root,
            project_name=project_name,
            session_key="session-partial",
            execution_id="exec-partial",
        )

        async def _append_entry(**_kwargs: Any) -> dict[str, Any]:
            progress = repo_root / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md"
            progress.parent.mkdir(parents=True, exist_ok=True)
            return {
                "ok": True,
                "id": "entry-partial",
                "path": str(progress),
                "paths": [str(progress)],
                "project_name": project_name,
            }

        async def _manage_docs(**kwargs: Any) -> dict[str, Any]:
            action = str(kwargs.get("action", ""))
            if action == "create":
                metadata = kwargs.get("metadata", {}) or {}
                case_id = str(metadata.get("case_id", "UNKNOWN"))
                report = repo_root / "docs" / "bugs" / "runtime" / f"2026-04-18_{case_id}" / "report.md"
                _write_report(
                    path=report,
                    doc_type="bug",
                    case_id=case_id,
                    title=str(metadata.get("title", case_id)),
                    status="open",
                    category="runtime",
                    severity="high",
                )
                return {"ok": True, "path": str(report)}
            if action == "replace_section":
                return {"ok": False, "error": "appendix write denied"}
            return {"ok": False, "error": f"unexpected action {action}"}

        monkeypatch.setattr(server_module, "storage_backend", storage)
        monkeypatch.setattr(server_module, "get_execution_context", lambda: active_context)

        with (
            patch("scribe_mcp.tools.append_entry.append_entry", side_effect=_append_entry),
            patch("scribe_mcp.tools.manage_docs.manage_docs", side_effect=_manage_docs),
            patch("scribe_mcp.tools.sentinel_tools._next_case_id_for_project", return_value="BUG-2026-04-18-0002"),
        ):
            bug = await sentinel_tools.open_bug(
                agent="test-agent",
                title="partial doc update bug",
                symptoms="bug symptoms",
                category="runtime",
                severity="high",
            )
            assert bug["ok"] is True

            linked = await sentinel_tools.link_fix(
                agent="test-agent",
                case_id="BUG-2026-04-18-0002",
                execution_id="exec-partial",
                artifact_ref="src/partial.py:5",
                landing_status="merged",
            )

        assert linked["ok"] is True
        assert linked["partial"] is True
        assert linked["doc_update_warning"] == "appendix write denied"
        assert linked["warnings"] == ["appendix write denied"]
        assert "Fix report updates for BUG-2026-04-18-0002" in linked["next_step"]

        record = await storage.fetch_case_registry_record("BUG-2026-04-18-0002")
        assert record is not None
        assert record.metadata["fix_link"]["artifact_ref"] == "src/partial.py:5"

        await storage.close()

    import asyncio

    asyncio.run(_run())
