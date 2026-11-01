from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest
from mcp import Client, StdioServerParameters


pytestmark = pytest.mark.regression


@asynccontextmanager
async def _isolated_server(project: dict, agent: str):
    """Bind a real stdio session to a disposable project and SQLite database."""
    source = Path(__file__).resolve().parents[1]
    root = Path(project["root"])
    runtime = root.parent / "runtime"
    runtime.mkdir()
    database = runtime / "scribe.sqlite3"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key not in {"DATABASE_URL", "REPO_ROOT"}}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(database), "SCRIBE_ROOT": str(runtime),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"),
        "SCRIBE_PROJECT_ROOT": str(root), "SCRIBE_DEV_PLANS_BASE": ".scribe/docs/dev_plans",
        "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1",
    })
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                   env=env, cwd=str(root))
    async with asyncio.timeout(60):
        async with Client(params, mode="2026-07-28", cache=None) as client:
            await client.session.send_discover("2026-07-28")

            async def call(tool_name: str, **arguments) -> dict:
                response = await client.call_tool(tool_name, {"agent": agent, **arguments})
                assert not response.is_error, response
                body = response.model_dump(mode="json", by_alias=True)["structuredContent"]
                assert isinstance(body, dict), response
                return body

            bound = await call("set_project", name=project["name"], root=str(root), format="structured")
            assert bound["ok"] is True, bound
            assert Path(bound["project"]["docs_dir"]) == Path(project["docs_dir"])
            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT docs_json FROM scribe_projects WHERE name = ?", (project["name"],)
                ).fetchone()
                assert row is not None
                assert json.loads(row[0])["checklist"] == project["docs"]["checklist"]
                bindings = connection.execute(
                    "SELECT project_name FROM session_projects"
                ).fetchall()
                assert bindings and all(row[0] == project["name"] for row in bindings)

            async def manage_docs(**arguments) -> dict:
                return await call("manage_docs", **arguments)

            before = {key: Path(project["docs"][key]).read_bytes()
                      for key in ("architecture", "phase_plan", "checklist")}
            yield manage_docs
            assert all(Path(project["docs"][key]).read_bytes() == value
                       for key, value in before.items())


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "checklist_repo"
    (project_root / ".git").mkdir(parents=True)
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    checklist_path = docs_dir / "CHECKLIST.md"
    checklist_path.write_text(
        "\n".join(
            [
                "# Checklist",
                "- [ ] Item A",
                "- [x] Item B",
                "- [ ] Item C",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Arch\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "test_project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(checklist_path),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }


@pytest.mark.asyncio
async def test_list_checklist_items_filters_exact_match(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)

    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Item B"},
            dry_run=True,
        )
        assert result.get("ok")
        matches = result.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["text"] == "Item B"
        assert matches[0]["status"] == "checked"
        assert matches[0]["start_line"] == matches[0]["end_line"]


@pytest.mark.asyncio
async def test_list_checklist_items_case_insensitive(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)

    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "item c", "case_sensitive": False},
            dry_run=True,
        )
        assert result.get("ok")
        matches = result.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["text"] == "Item C"


@pytest.mark.asyncio
async def test_list_checklist_items_accepts_doc_alias_case_variants(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)

    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="list_checklist_items",
            doc="CHECKLIST",
            metadata={"text": "Item A"},
            dry_run=True,
        )
        assert result.get("ok")
        matches = result.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["text"] == "Item A"


@pytest.mark.asyncio
async def test_list_checklist_items_requires_match(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)

    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Missing", "require_match": True},
            dry_run=True,
        )
        assert not result.get("ok")
        assert "No checklist items matched" in result.get("error", "")


@pytest.mark.asyncio
async def test_list_checklist_items_body_line_offset(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    checklist_path = Path(project["docs"]["checklist"])
    checklist_path.write_text(
        "\n".join(
            [
                "---",
                "id: checklist-frontmatter",
                "title: \"Checklist\"",
                "doc_type: checklist",
                "---",
                "# Checklist",
                "- [ ] Item A",
                "- [ ] Item B",
                "",
            ]
        ),
        encoding="utf-8",
    )


    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Item A"},
            dry_run=True,
        )
        assert result.get("ok")
        assert result.get("body_line_offset") == 5
        matches = result.get("matches", [])
        assert matches[0]["line"] == 2
        assert matches[0]["file_line"] == 7


@pytest.mark.asyncio
async def test_status_update_frontmatter_intent_returns_exact_mismatch_code(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)

    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="status_update",
            doc="architecture",
            section="main",
            metadata={"frontmatter": {"status": "done"}},
            dry_run=True,
        )
        assert not result.get("ok")
        assert result.get("code") == "DOC_STATUS_INTENT_MISMATCH"
        error = result.get("error", "")
        assert "frontmatter_update" in error
        assert "metadata.frontmatter" in error


@pytest.mark.asyncio
async def test_status_update_targets_lowercase_inline_item_id(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    checklist_path = Path(project["docs"]["checklist"])
    checklist_path.write_text(
        "\n".join(
            [
                "# Checklist",
                "- [ ] <!-- id: p4-task-3 --> BLOCKED: Final quality gate pending.",
                "- [ ] <!-- id: final-gate-1 --> Final review pending.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    async with _isolated_server(project, test_agent) as manage_docs:
        result = await manage_docs(
            action="status_update",
            doc="checklist",
            section="p4-task-3",
            metadata={"status": "done", "proof": "live project_health pass"},
            dry_run=True,
        )

    assert result.get("ok") is True, result
    diff = str(result.get("diff") or "")
    assert "- [x] <!-- id: p4-task-3 --> BLOCKED: Final quality gate pending. | proof=live project_health pass" in diff
    assert "+- [x] <!-- id: final-gate-1 -->" not in diff
    assert "-- [ ] <!-- id: final-gate-1 -->" not in diff
    assert "\n\n<!-- ID: p4-task-3 -->\n" not in diff
