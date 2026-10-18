from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools import manage_docs as manage_docs_module
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager, project_root=None):
    """Monkey-patch server module for isolated test execution.

    Neutralizes execution context and agent identity so project resolution
    falls through to the legacy StateManager path.  Also patches repo-scoping
    so that a tmp_path-based project root is not rejected for being outside
    the real repository.
    """
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)

    server_module.state_manager = state_manager
    server_module.storage_backend = None
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project",
        session_id="checklist-test-session",
        stable_session_id="checklist-test-session",
    )
    server_module.get_agent_identity = lambda: None

    # Patch repo-scoping to accept the test project root.
    fake_root = Path(project_root).resolve() if project_root else Path("/tmp")
    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="test", repo_root=fake_root)

    try:
        async def _prepare_context_stub(**kwargs):
            state = await state_manager.load()
            current_project = state.get_project(state.current_project) if state.current_project else None
            return LoggingContext(
                tool_name="manage_docs",
                project=current_project,
                recent_projects=list(getattr(state, "recent_projects", []) or []),
                state_snapshot={},
                reminders=[],
                resolution_source="session_binding",
            )

        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        with patch(
            "scribe_mcp.config.repo_config.get_current_repo_config",
            return_value=(fake_root, fake_config),
        ):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        if orig_exec_ctx is not None:
            server_module.get_execution_context = orig_exec_ctx
        if orig_agent_id is not None:
            server_module.get_agent_identity = orig_agent_id
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = orig_prepare_context


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "checklist_repo"
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
        "name": "Checklist Project",
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
async def test_list_checklist_items_filters_exact_match(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
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
async def test_list_checklist_items_case_insensitive(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
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
async def test_list_checklist_items_accepts_doc_alias_case_variants(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
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
async def test_list_checklist_items_requires_match(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="list_checklist_items",
            doc="checklist",
            metadata={"text": "Missing", "require_match": True},
            dry_run=True,
        )
        assert not result.get("ok")
        assert "No checklist items matched" in result.get("error", "")


@pytest.mark.asyncio
async def test_list_checklist_items_body_line_offset(tmp_path: Path) -> None:
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

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
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
async def test_status_update_frontmatter_intent_returns_exact_mismatch_code(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
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
async def test_status_update_targets_lowercase_inline_item_id(tmp_path: Path) -> None:
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
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
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
