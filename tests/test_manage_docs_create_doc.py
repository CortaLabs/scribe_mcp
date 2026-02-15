from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp import server as server_module


@contextmanager
def _isolated_server(state_manager, project_root=None):
    """Monkey-patch server module for isolated test execution."""
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

    fake_root = Path(project_root).resolve() if project_root else Path("/tmp")
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
    project_root = tmp_path / "create_doc_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Create Doc Project",
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
async def test_create_doc_from_body(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    target_dir = Path(project["docs_dir"]) / "custom"
    target_dir.mkdir(parents=True, exist_ok=True)

    change = await apply_doc_change(
        project,
        doc="custom_doc",
        action="create_doc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={
            "doc_name": "lore_drop_003",
            "doc_type": "lore_drop",
            "body": "# Lore Drop\nDetails here.",
            "target_dir": str(target_dir),
            "frontmatter": {"category": "lore"},
        },
        dry_run=False,
    )

    assert change.success
    path = Path(change.path)
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("doc_type") == "lore_drop"
    assert parsed.frontmatter_data.get("category") == "lore"
    assert "# Lore Drop" in parsed.body


@pytest.mark.asyncio
async def test_create_doc_missing_content_fails(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)

    change = await apply_doc_change(
        project,
        doc="custom_doc",
        action="create_doc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"doc_name": "empty_doc"},
        dry_run=False,
    )

    assert not change.success
    assert "CREATE_DOC_MISSING_CONTENT" in (change.error_message or "")


@pytest.mark.asyncio
async def test_create_doc_registry_warning(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async def _fail_set_current(*args, **kwargs):
        raise RuntimeError("boom")

    state_manager.set_current_project = _fail_set_current  # type: ignore[assignment]

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="custom_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "one_off_note",
                "body": "# Note\nDetails.",
                "register_doc": True,
            },
            dry_run=False,
        )
        assert result["ok"] is True
        assert "warnings" in result
        assert "Registry update failed" in result["warnings"][0]


@pytest.mark.asyncio
async def test_manage_docs_create_doc_dry_run_does_not_register_doc(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="custom_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "dry_run_note",
                "body": "# Dry Run Note\nShould not register.",
            },
            dry_run=True,
        )
        assert result["ok"] is True

        state = await state_manager.load()
        stored_project = state.get_project(project["name"])
        assert stored_project is not None
        assert "dry_run_note" not in (stored_project.get("docs") or {})

        preview_path = Path(result["path"])
        assert not preview_path.exists()

        warnings = result.get("warnings") or []
        assert any("register_doc skipped during dry_run" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_manage_docs_create_doc_preserves_newlines(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="custom_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "newline_note",
                "body": "# Note\nDetails line two.",
            },
            dry_run=False,
        )
        assert result["ok"] is True
        path = Path(result["path"])
        parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
        assert "# Note\nDetails line two." in parsed.body


@pytest.mark.asyncio
async def test_create_custom_doc_respects_doc_name_parameter(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)

    change = await apply_doc_change(
        project,
        doc_name="COORDINATION_PROTOCOL",
        action="create_doc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"doc_type": "custom", "body": "# Protocol\n\nCoordination rules here."},
        dry_run=False,
    )

    assert change.success, f"Failed: {change.error_message}"
    path = Path(change.path)
    assert path.name == "COORDINATION_PROTOCOL.md", f"Expected COORDINATION_PROTOCOL.md but got {path.name}"
    assert "custom.md" not in str(path), f"Should not create custom.md, got {path}"

    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert "# Protocol" in parsed.body
    assert "Coordination rules here." in parsed.body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        "create_doc",
        "create_research_doc",
        "create_bug_report",
        "create_review_report",
        "create_agent_report_card",
    ],
)
async def test_manage_docs_deprecated_create_aliases_fail_hard(
    tmp_path: Path,
    action: str,
) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action=action,
            doc="legacy_alias_doc",
            content="# Legacy Alias\n\nBody content.",
            metadata={"category": "router"},
            dry_run=False,
        )
        assert result["ok"] is False
        assert "Invalid manage_docs action" in result.get("error", "")
        allowed = result.get("allowed_actions") or result.get("extra", {}).get("allowed_actions", [])
        assert "create" in allowed
        assert action not in allowed
