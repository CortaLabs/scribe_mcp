from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.doc_management import runtime as runtime_shared
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager: StateManager, *, project_root: Path, session_id: str):
    originals = {"state_manager": server_module.state_manager, "storage_backend": server_module.storage_backend}
    from scribe_mcp.tools import manage_docs as manage_docs_module
    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)
    server_module.state_manager = state_manager
    server_module.storage_backend = getattr(state_manager, "_storage_backend", None)
    server_module.get_execution_context = lambda: SimpleNamespace(mode="project", session_id=session_id, stable_session_id=session_id)
    server_module.get_agent_identity = lambda: None

    from scribe_mcp.config.repo_config import RepoConfig
    fake_config = RepoConfig(repo_slug="test", repo_root=project_root)
    try:
        async def _prepare_context_stub(**kwargs):
            state = await state_manager.load()
            current_project = state.get_project(state.current_project) if state.current_project else None
            return LoggingContext(tool_name="manage_docs", project=current_project, recent_projects=list(getattr(state, "recent_projects", []) or []), state_snapshot={}, reminders=[], resolution_source="session_binding")

        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        with patch("scribe_mcp.config.repo_config.get_current_repo_config", return_value=(project_root, fake_config)):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        if orig_exec_ctx is not None:
            server_module.get_execution_context = orig_exec_ctx
        if orig_agent_id is not None:
            server_module.get_agent_identity = orig_agent_id
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = orig_prepare_context


async def _seed_runtime_session(state_manager: StateManager, session_id: str, repo_root: str) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(session_id=session_id, transport_session_id=session_id, repo_root=repo_root, mode="project")


@pytest.mark.asyncio
async def test_quality_check_returns_structured_quality_proof(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"ARCHITECTURE_GUIDE": str(arch)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-check-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-check-session"):
        result = await manage_docs(action="quality_check", doc_name="ARCHITECTURE_GUIDE", dry_run=True)

    assert result["ok"] is True
    assert result["quality_status"] in {"warn", "fail"}
    assert result["scope"]["doc_name"] == "ARCHITECTURE_GUIDE"
    assert result["summary"]["total_warnings"] >= 1
    first = result["warnings"][0]
    for key in ("code", "severity", "blocking", "location", "excerpt", "message", "suggested_repair"):
        assert key in first


@pytest.mark.asyncio
async def test_quality_check_clean_doc_passes(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    phase = docs_dir / "PHASE_PLAN.md"
    phase.write_text("---\nstatus: in_progress\n---\n# Phase\nComplete evidence text.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PHASE_PLAN": str(phase)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-pass-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-pass-session"):
        result = await manage_docs(action="quality_check", doc="PHASE_PLAN", dry_run=True)

    assert result["ok"] is True
    assert result["quality_status"] == "pass"
    assert result["readiness_blockers"] == []


@pytest.mark.asyncio
async def test_quality_check_respects_metadata_quality_overrides(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    checklist = docs_dir / "CHECKLIST.md"
    checklist.write_text("---\nstatus: complete\n---\nTODO: do this\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"CHECKLIST": str(checklist)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-override-session", project["root"])

    metadata = {"quality": {"severity_overrides": {"SCF_TODO_ONLY_SECTION": "low"}, "blocking_overrides": {"SCF_TODO_ONLY_SECTION": False}}}
    with _isolated_server(state_manager, project_root=project_root, session_id="quality-override-session"):
        result = await manage_docs(action="quality_check", doc_name="CHECKLIST", metadata=metadata, dry_run=True)

    todo = [w for w in result["warnings"] if w.get("code") == "SCF_TODO_ONLY_SECTION"][0]
    assert todo["severity"] == "low"
    assert todo["blocking"] is False
    assert result["summary"]["config_source"] == "metadata.quality"


@pytest.mark.asyncio
async def test_quality_check_resolves_registered_doc_aliases(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_alias"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    closeout = docs_dir / "PACKAGE_5_1_VERIFICATION_CLOSEOUT.md"
    closeout.write_text("# Closeout\n\nVerification evidence.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PACKAGE_5_1_VERIFICATION_CLOSEOUT": str(closeout)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-alias-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-alias-session"):
        result = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT.md", dry_run=True)

    assert result["ok"] is True
    assert result["scope"]["doc_name"] == "PACKAGE_5_1_VERIFICATION_CLOSEOUT"


@pytest.mark.asyncio
async def test_quality_check_auto_registers_package_doc_and_accepts_alias_forms(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_bind"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    proof_doc = docs_dir / "PACKAGE_5_1_LIVE_PROOF_DOC.md"
    proof_doc.write_text("# Live Proof\n\nEvidence.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs_dir": str(docs_dir), "docs": {}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-bind-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-bind-session"):
        by_doc_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_LIVE_PROOF_DOC.md", dry_run=True)
        by_doc = await manage_docs(action="quality_check", doc="PACKAGE_5_1_LIVE_PROOF_DOC", dry_run=True)

    assert by_doc_name["ok"] is True
    assert by_doc_name["scope"]["doc_name"] == "package_5_1_live_proof_doc"
    assert by_doc["ok"] is True
    assert by_doc["scope"]["doc_name"] == "package_5_1_live_proof_doc"


@pytest.mark.asyncio
async def test_quality_check_derives_docs_dir_from_progress_log_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_progress_derived"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)

    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Progress\n", encoding="utf-8")
    for name in ("ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    closeout = docs_dir / "PACKAGE_5_1_VERIFICATION_CLOSEOUT.md"
    closeout.write_text("# Closeout\n\nVerification evidence.\n", encoding="utf-8")

    project = {
        "name": "Q",
        "root": str(project_root),
        "progress_log": str(progress_log),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(progress_log),
        },
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-progress-derive-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-progress-derive-session"):
        by_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT", dry_run=True)
        by_path_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT.md", dry_run=True)

    assert by_name["ok"] is True
    assert by_path_name["ok"] is True


@pytest.mark.asyncio
async def test_quality_check_uses_discovered_doc_when_auto_registration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "quality_repo_registration_blocked"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)

    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Progress\n", encoding="utf-8")
    for name in ("ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    closeout = docs_dir / "PACKAGE_5_1_VERIFICATION_CLOSEOUT.md"
    closeout.write_text("# Closeout\n\nVerification evidence.\n", encoding="utf-8")
    project = {
        "name": "Q",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(progress_log),
        },
    }

    async def _blocked_registration(*_args, **_kwargs):
        raise ValueError("Cannot establish authoritative session binding for manage_docs registration.")

    monkeypatch.setattr(runtime_shared, "register_document_path", _blocked_registration)

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-registration-blocked-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-registration-blocked-session"):
        by_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT", dry_run=True)
        by_md = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT.md", dry_run=True)

    for result in (by_name, by_md):
        assert result["ok"] is True
        assert result["scope"]["path"] == str(closeout)
        assert result["scope"]["doc_name"] == "package_5_1_verification_closeout"
        assert "authoritative session binding" in result["runtime_warnings"][0]
