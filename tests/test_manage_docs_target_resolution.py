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


class _CaseRegistryBackend:
    def __init__(
        self,
        *,
        case_id: str,
        doc_path: Path,
        project_name: str,
        repo_root: Path,
        case_type: str = "bug",
    ) -> None:
        self.case_id = case_id
        self.doc_path = doc_path
        self.project_name = project_name
        self.repo_root = repo_root
        self.case_type = case_type
        self.docs_json: str | None = None

    async def fetch_case_registry_record(self, case_id: str, **_kwargs):
        if case_id != self.case_id:
            return None
        return SimpleNamespace(
            case_id=self.case_id,
            case_type=self.case_type,
            project_name=self.project_name,
            repo_root=str(self.repo_root),
            doc_type=self.case_type,
            doc_name=self.case_id,
            doc_path=str(self.doc_path),
            metadata={},
        )

    async def update_project_docs(self, _project_name: str, docs_json: str, **_kwargs):
        self.docs_json = docs_json


@contextmanager
def _isolated_server(state_manager: StateManager, *, project_root: Path, storage_backend=None):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)
    from scribe_mcp.tools import manage_docs as manage_docs_module

    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context

    server_module.state_manager = state_manager
    server_module.storage_backend = storage_backend
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project",
        session_id="target-resolution-test",
        stable_session_id="target-resolution-test",
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
    project_root = tmp_path / "target_resolution_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "target_resolution_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    checklist_path = docs_dir / "CHECKLIST.md"
    checklist_path.write_text(
        "# Checklist\n\n## Overview\n\n- [ ] Item A\n",
        encoding="utf-8",
    )
    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Target Resolution Project",
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


async def _seed_runtime_session(
    state_manager: StateManager,
    *,
    project_root: Path,
    session_id: str = "target-resolution-test",
) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(
            session_id=session_id,
            repo_root=str(project_root),
            mode="project",
        )


@pytest.mark.asyncio
async def test_target_resolution_unifies_md_alias_and_path_variants(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    checklist_path = Path(project["docs"]["checklist"])
    state_manager = StateManager(path=tmp_path / "state.json")
    await _seed_runtime_session(state_manager, project_root=Path(project["root"]))
    await state_manager.set_current_project(project["name"], project)

    variants = [
        "checklist",
        "CHECKLIST",
        "CHECKLIST.md",
        str(checklist_path),
        str(checklist_path.relative_to(Path(project["root"]))),
    ]

    with _isolated_server(state_manager, project_root=Path(project["root"])):
        all_section_ids = []
        for variant in variants:
            result = await manage_docs(
                action="list_sections",
                doc=variant,
                dry_run=True,
            )
            assert result.get("ok") is True, f"variant={variant} failed: {result}"
            section_ids = [section.get("id") for section in result.get("sections", [])]
            all_section_ids.append(section_ids)

    assert all_section_ids
    assert all(section_ids == all_section_ids[0] for section_ids in all_section_ids)


@pytest.mark.asyncio
async def test_first_write_guidance_for_registered_existing_doc_uses_apply_patch(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    docs_dir = Path(project["docs_dir"])
    existing_path = docs_dir / "existing_first_write.md"
    existing_path.write_text("# Existing\n\nLine A\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await _seed_runtime_session(state_manager, project_root=Path(project["root"]))
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=Path(project["root"])):
        create_result = await manage_docs(
            action="create",
            doc="existing_first_write",
            metadata={
                "doc_type": "custom",
                "doc_name": "existing_first_write",
                "register_existing": True,
            },
            dry_run=False,
        )

        assert create_result.get("ok") is True
        assert create_result.get("create_intent", {}).get("kind") == "empty_registered_doc"
        assert create_result.get("create_intent", {}).get("first_write_action") == "apply_patch"
        assert create_result.get("first_write_action") == "apply_patch"
        assert "apply_patch" in (create_result.get("next_step_guidance") or "")

        patch_result = await manage_docs(
            action="apply_patch",
            doc="existing_first_write.md",
            patch=(
                "--- a/existing_first_write.md\n"
                "+++ b/existing_first_write.md\n"
                "@@ -1,3 +1,3 @@\n"
                " # Existing\n"
                " \n"
                "-Line A\n"
                "+Line B\n"
            ),
            metadata={},
            dry_run=False,
        )

        assert patch_result.get("ok") is True
        assert "Line B" in existing_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_bug_report_resolution_accepts_case_id_governed_path_and_canonical_alias(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    project_root = Path(project["root"])
    case_id = "BUG-2026-06-04-0001"
    report_path = project_root / "docs" / "bugs" / "runtime" / f"2026-06-04_{case_id}" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "# Bug Report\n\n## Investigation\n<!-- ID: investigation -->\n\nOriginal investigation.\n",
        encoding="utf-8",
    )

    state_manager = StateManager(path=tmp_path / "state.json")
    await _seed_runtime_session(state_manager, project_root=project_root)
    await state_manager.set_current_project(project["name"], project)
    backend = _CaseRegistryBackend(
        case_id=case_id,
        doc_path=report_path,
        project_name=project["name"],
        repo_root=project_root,
    )

    with _isolated_server(state_manager, project_root=project_root, storage_backend=backend):
        case_result = await manage_docs(
            action="replace_section",
            doc_name=case_id,
            doc_category="bugs",
            section="investigation",
            content="Registry-backed investigation.",
            dry_run=False,
        )
        assert case_result.get("ok") is True, case_result
        assert "Registry-backed investigation." in report_path.read_text(encoding="utf-8")
        assert backend.docs_json is not None
        assert case_id in backend.docs_json
        assert str(report_path) in backend.docs_json

        path_result = await manage_docs(
            action="replace_section",
            doc_name=str(report_path),
            section="investigation",
            content="Path-backed investigation.",
            dry_run=False,
        )
        assert path_result.get("ok") is True, path_result

    assert "Path-backed investigation." in report_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_bug_report_path_resolution_does_not_collapse_to_first_report(tmp_path: Path) -> None:
    """Explicit report paths must not match an unrelated registered report.md basename."""
    project = await _setup_project(tmp_path)
    project_root = Path(project["root"])
    first_case_id = "BUG-2026-06-16-0001"
    second_case_id = "BUG-2026-06-16-0002"
    first_report = project_root / "docs" / "bugs" / "performance" / f"2026-06-16_{first_case_id}" / "report.md"
    second_report = project_root / "docs" / "bugs" / "performance" / f"2026-06-16_{second_case_id}" / "report.md"
    first_report.parent.mkdir(parents=True, exist_ok=True)
    second_report.parent.mkdir(parents=True, exist_ok=True)
    first_report.write_text(
        "# First\n\n## Investigation\n<!-- ID: investigation -->\nFirst report.\n",
        encoding="utf-8",
    )
    second_report.write_text(
        "# Second\n\n## Investigation\n<!-- ID: investigation -->\nSecond report.\n",
        encoding="utf-8",
    )
    project.setdefault("docs", {})[first_case_id] = str(first_report)

    state_manager = StateManager(path=tmp_path / "state.json")
    await _seed_runtime_session(state_manager, project_root=project_root)
    await state_manager.set_current_project(project["name"], project)
    backend = _CaseRegistryBackend(
        case_id=second_case_id,
        doc_path=second_report,
        project_name=project["name"],
        repo_root=project_root,
    )

    with _isolated_server(state_manager, project_root=project_root, storage_backend=backend):
        result = await manage_docs(
            action="replace_section",
            doc_name=str(second_report),
            doc_category="bugs",
            section="investigation",
            content="Second report updated.",
            dry_run=False,
        )

    assert result.get("ok") is True, result
    assert "First report." in first_report.read_text(encoding="utf-8")
    assert "Second report updated." in second_report.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_security_report_resolution_accepts_case_id_governed_path_and_canonical_alias(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    project_root = Path(project["root"])
    case_id = "SEC-2026-06-04-0001"
    report_path = project_root / "docs" / "security" / "runtime" / f"2026-06-04_{case_id}" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "# Security Report\n\n## Fix\n<!-- ID: fix -->\n\nOriginal fix.\n",
        encoding="utf-8",
    )

    state_manager = StateManager(path=tmp_path / "state.json")
    await _seed_runtime_session(state_manager, project_root=project_root)
    await state_manager.set_current_project(project["name"], project)
    backend = _CaseRegistryBackend(
        case_id=case_id,
        doc_path=report_path,
        project_name=project["name"],
        repo_root=project_root,
        case_type="security",
    )

    with _isolated_server(state_manager, project_root=project_root, storage_backend=backend):
        case_result = await manage_docs(
            action="replace_section",
            doc_name=case_id,
            doc_category="security",
            section="fix",
            content="Registry-backed security fix.",
            dry_run=False,
        )
        assert case_result.get("ok") is True, case_result
        assert "Registry-backed security fix." in report_path.read_text(encoding="utf-8")
        assert backend.docs_json is not None
        assert case_id in backend.docs_json
        assert str(report_path) in backend.docs_json

        path_result = await manage_docs(
            action="replace_section",
            doc_name=str(report_path),
            section="fix",
            content="Path-backed security fix.",
            dry_run=False,
        )
        assert path_result.get("ok") is True, path_result

    assert "Path-backed security fix." in report_path.read_text(encoding="utf-8")
