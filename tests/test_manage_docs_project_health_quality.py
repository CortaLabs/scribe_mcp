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


def _project_payload(project_root: Path, slug: str) -> dict:
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / slug
    docs_dir.mkdir(parents=True, exist_ok=True)
    custom_log_path = docs_dir / "DECISIONS.md"
    for filename, title in (("ARCHITECTURE_GUIDE.md", "Architecture"), ("PHASE_PLAN.md", "Phase"), ("CHECKLIST.md", "Checklist"), ("PROGRESS_LOG.md", "Log")):
        (docs_dir / filename).write_text(f"# {title}\n", encoding="utf-8")
    custom_log_path.write_text("[2026-05-01] custom log entry\n", encoding="utf-8")
    config_dir = project_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        "repo_slug: test\n"
        "logs:\n"
        "  decisions:\n"
        "    path: \"{docs_dir}/DECISIONS.md\"\n"
        "    metadata_requirements: []\n",
        encoding="utf-8",
    )
    return {"name": slug.replace("_", " ").title(), "root": str(project_root), "docs_dir": str(docs_dir), "progress_log": str(docs_dir / "PROGRESS_LOG.md"), "docs": {"architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"), "phase_plan": str(docs_dir / "PHASE_PLAN.md"), "checklist": str(docs_dir / "CHECKLIST.md"), "progress_log": str(docs_dir / "PROGRESS_LOG.md"), "decisions": str(custom_log_path)}}


async def _seed_runtime_session(state_manager: StateManager, session_id: str, repo_root: str) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(session_id=session_id, transport_session_id=session_id, repo_root=repo_root, mode="project")


@pytest.mark.asyncio
async def test_project_health_includes_managed_doc_quality(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    active_project = _project_payload(project_root, "active_project")
    architecture_path = Path(active_project["docs"]["architecture"])
    architecture_path.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "quality-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-test-session"):
        result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    quality = result.get("managed_doc_quality") or {}
    assert quality.get("status") == "blocked"
    assert quality.get("readiness_blocker_count", 0) >= 1
    names = {doc.get("doc_name") for doc in quality.get("documents", [])}
    assert "progress_log" not in names
    assert "decisions" not in names


@pytest.mark.asyncio
async def test_project_health_counts_research_hygiene_for_path_registered_docs(tmp_path: Path) -> None:
    project_root = tmp_path / "research_quality_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_doc = research_dir / "RESEARCH_FRONTMATTER.md"
    research_doc.write_text("# Research\nEvidence.\n", encoding="utf-8")
    active_project["docs"] = {
        "architecture": active_project["docs"]["architecture"],
        "research_frontmatter": str(research_doc),
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "research-quality-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="research-quality-test-session"):
        result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    quality = result.get("managed_doc_quality") or {}
    research_entry = next(doc for doc in quality.get("documents", []) if doc.get("doc_name") == "research_frontmatter")
    assert "SCF_INDEX_MISSING" in research_entry.get("warning_codes", [])
