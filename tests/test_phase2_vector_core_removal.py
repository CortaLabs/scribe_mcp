from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.scripts import scribe_probe
from scribe_mcp.state import StateManager
from scribe_mcp.tools import __all__ as tool_exports
from scribe_mcp.tools import tool_module_for_name
from scribe_mcp.tools.base import tool_metadata
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager: StateManager, project_root: str | Path):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)

    server_module.state_manager = state_manager
    server_module.storage_backend = None
    server_module.get_execution_context = lambda: None
    server_module.get_agent_identity = lambda: None

    fake_root = Path(project_root).resolve()
    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="test", repo_root=fake_root)

    try:
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


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "vectorless_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text(
        "# Architecture\nneedle text appears here\n",
        encoding="utf-8",
    )
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text(
        "# Progress\nneedle text also appears here\n",
        encoding="utf-8",
    )

    return {
        "name": "Vectorless Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }


@pytest.mark.parametrize("search_mode", ["semantic", "vector"])
@pytest.mark.asyncio
async def test_manage_docs_search_falls_back_to_text(search_mode: str, tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="search",
            metadata={"query": "needle text", "search_mode": search_mode},
            dry_run=True,
        )

    assert result["ok"] is True
    assert result["fallback_applied"] is True
    assert result["requested_search_mode"] == search_mode
    assert result["effective_search_mode"] == "text"
    assert "text search" in result["warning"].lower()
    assert result["search_mode"] == "text"
    assert result["results_count"] == 2
    assert {item["doc"] for item in result["results"]} == {"architecture", "progress_log"}


def test_vector_tool_surfaces_are_removed_from_core_exports() -> None:
    assert tool_module_for_name("vector_search") is None
    assert "vector_search" not in tool_exports
    assert "vector_search" not in tool_metadata.TOOL_METADATA
    assert "vector_search" not in scribe_probe.TOOL_RUNNERS
