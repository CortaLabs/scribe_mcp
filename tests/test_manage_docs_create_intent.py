from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager: StateManager, *, project_root: Path):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)
    from scribe_mcp.tools import manage_docs as manage_docs_module

    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context

    server_module.state_manager = state_manager
    server_module.storage_backend = None
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project",
        session_id="intent-test-session",
        stable_session_id="intent-test-session",
    )
    server_module.get_agent_identity = lambda: None

    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="test", repo_root=project_root)

    try:
        async def _prepare_context_stub(**kwargs):
            state = await state_manager.load()
            current_name = state.current_project
            if not current_name and getattr(state, "recent_projects", None):
                current_name = state.recent_projects[0]
            if not current_name and getattr(state, "projects", None):
                current_name = next(iter(state.projects.keys()))
            current_project = state.get_project(current_name) if current_name else None
            state_snapshot = kwargs.get("state_snapshot")
            return LoggingContext(
                tool_name="manage_docs",
                project=current_project,
                recent_projects=list(getattr(state, "recent_projects", []) or []),
                state_snapshot=state_snapshot if isinstance(state_snapshot, dict) else {},
                reminders=[],
            )

        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        with patch(
            "scribe_mcp.config.repo_config.get_current_repo_config",
            return_value=(project_root, fake_config),
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
    project_root = tmp_path / "create_intent_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "intent_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for filename, title in (
        ("ARCHITECTURE_GUIDE.md", "Architecture"),
        ("PHASE_PLAN.md", "Phase"),
        ("CHECKLIST.md", "Checklist"),
        ("PROGRESS_LOG.md", "Log"),
    ):
        (docs_dir / filename).write_text(f"# {title}\n", encoding="utf-8")

    return {
        "name": "Create Intent Project",
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


@pytest.mark.asyncio
async def test_create_custom_returns_governed_scaffold_intent(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=Path(project["root"])):
        result = await manage_docs(
            action="create",
            doc="custom_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "INTENT_CUSTOM_DOC",
                "body": "# Intent\n\nCustom content.",
            },
            dry_run=False,
        )

    assert result["ok"] is True
    assert result.get("create_intent", {}).get("kind") == "governed_scaffold_doc"
    assert result.get("create_intent", {}).get("canonical_doc_name") == "INTENT_CUSTOM_DOC"
    assert result.get("canonical_doc_name") == "INTENT_CUSTOM_DOC"
    assert result.get("project_name") == project["name"]
    assert isinstance(result.get("editable_sections"), list)
    assert result.get("editable_sections")
    assert "replace_section" in result.get("next_step_guidance", "")
    assert "INTENT_CUSTOM_DOC" in result.get("next_step_guidance", "")


@pytest.mark.asyncio
async def test_create_special_doc_returns_contentful_intent(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=Path(project["root"])):
        result = await manage_docs(
            action="create",
            doc="RESEARCH_INTENT_CONTENTFUL",
            metadata={
                "doc_type": "research",
                "doc_name": "RESEARCH_INTENT_CONTENTFUL",
                "body": "# Research\n\nFindings.",
            },
            dry_run=False,
        )

    assert result["ok"] is True
    assert result.get("create_intent", {}).get("kind") == "contentful_special_doc"
    assert result.get("create_intent", {}).get("canonical_doc_name") == "RESEARCH_INTENT_CONTENTFUL"
    assert result.get("project_name") == project["name"]
    assert isinstance(result.get("editable_sections"), list)
    assert "contentful special document" in result.get("next_step_guidance", "")


@pytest.mark.asyncio
async def test_create_register_existing_returns_empty_registered_intent(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    docs_dir = Path(project["docs_dir"])
    existing = docs_dir / "existing_doc.md"
    existing.write_text("# Existing\n\nNo changes.", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=Path(project["root"])):
        result = await manage_docs(
            action="create",
            doc="existing_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "existing_doc",
                "register_existing": True,
            },
            dry_run=False,
        )

    assert result["ok"] is True
    assert result.get("create_intent", {}).get("kind") == "empty_registered_doc"
    assert result.get("create_intent", {}).get("canonical_doc_name") == "existing_doc"
    assert "without writing new content" in result.get("next_step_guidance", "")
    assert "existing_doc" in result.get("next_step_guidance", "")


@pytest.mark.asyncio
async def test_create_special_doc_dry_run_includes_editable_sections(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=Path(project["root"])):
        result = await manage_docs(
            action="create",
            doc="RESEARCH_INTENT_DRY_RUN",
            metadata={
                "doc_type": "research",
                "doc_name": "RESEARCH_INTENT_DRY_RUN",
                "body": "# Research\n\nFindings.",
            },
            dry_run=True,
        )

    assert result["ok"] is True
    assert result.get("dry_run") is True
    assert isinstance(result.get("editable_sections"), list)
    assert result.get("editable_sections")
    assert result.get("section_source") in {"anchors", "headings"}
