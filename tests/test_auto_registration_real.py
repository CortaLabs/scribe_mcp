from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.utils.slug import normalize_project_input


@dataclass
class _StorageProjectRecord:
    name: str
    docs_json: str = "{}"
    repo_root: str = ""
    progress_log_path: str = ""


class _FakeBackend:
    def __init__(self) -> None:
        self.docs_by_project: dict[str, dict[str, str]] = {}
        self.project_records: dict[str, _StorageProjectRecord] = {}

    async def update_project_docs(self, project_name: str, docs_json: str) -> None:
        self.docs_by_project[project_name] = json.loads(docs_json or "{}")

    async def fetch_project(self, name: str):
        record = self.project_records.get(name)
        if record is not None:
            record.docs_json = json.dumps(self.docs_by_project.get(name, {}))
            return record
        return _StorageProjectRecord(name=name, docs_json=json.dumps(self.docs_by_project.get(name, {})))

    async def upsert_project(self, name: str, repo_root: str, progress_log_path: str):
        record = _StorageProjectRecord(
            name=name,
            docs_json=json.dumps(self.docs_by_project.get(name, {})),
            repo_root=repo_root,
            progress_log_path=progress_log_path,
        )
        self.project_records[name] = record
        return record

    async def record_doc_change(self, *args, **kwargs) -> None:
        return None


def _seed_backend_project(backend: _FakeBackend, project: dict) -> None:
    record = _StorageProjectRecord(
        name=project["name"],
        docs_json=json.dumps(backend.docs_by_project.get(project["name"], {})),
        repo_root=project["root"],
        progress_log_path=project["progress_log"],
    )
    backend.project_records[project["name"]] = record
    normalized = normalize_project_input(project["name"])
    if normalized and normalized != project["name"]:
        backend.project_records[normalized] = record


@contextmanager
def _isolated_server(state_manager: StateManager, backend: _FakeBackend, project_root: str):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)

    server_module.state_manager = state_manager
    server_module.storage_backend = backend
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
    project_root = tmp_path / "auto_registration_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "auto_registration_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Auto Registration Project",
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
async def test_mutation_auto_registers_unregistered_root_doc(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    backend = _FakeBackend()
    _seed_backend_project(backend, project)
    await state_manager.set_current_project(project["name"], project)

    docs_dir = Path(project["docs_dir"])
    target_doc = docs_dir / "UNREGISTERED_ROOT.md"
    target_doc.write_text("# Root Doc\nStatus: draft\n", encoding="utf-8")

    with _isolated_server(state_manager, backend, project_root=project["root"]):
        result = await manage_docs(
            action="replace_text",
            doc="UNREGISTERED_ROOT",
            metadata={"find": "draft", "replace": "active"},
            project=project["name"],
            dry_run=False,
        )
        assert result["ok"] is True

        state = await state_manager.load()
        stored_project = state.get_project(project["name"])
        assert stored_project is not None
        assert stored_project.get("docs", {}).get("UNREGISTERED_ROOT") == str(target_doc)
        assert backend.docs_by_project[project["name"]]["UNREGISTERED_ROOT"] == str(target_doc)
        assert "Status: active" in target_doc.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_mutation_auto_registers_custom_doc_with_persistent_mapping(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    backend = _FakeBackend()
    _seed_backend_project(backend, project)
    await state_manager.set_current_project(project["name"], project)

    docs_dir = Path(project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    doc_name = "RESEARCH_UNREGISTERED_FLOW"
    target_doc = research_dir / f"{doc_name}.md"
    target_doc.write_text("# Research\nStatus: draft\n", encoding="utf-8")

    with _isolated_server(state_manager, backend, project_root=project["root"]):
        result = await manage_docs(
            action="replace_text",
            doc_category="research",
            doc=doc_name,
            metadata={"find": "draft", "replace": "active"},
            project=project["name"],
            dry_run=False,
        )
        assert result["ok"] is True

        state = await state_manager.load()
        stored_project = state.get_project(project["name"])
        assert stored_project is not None
        docs = stored_project.get("docs", {})
        assert docs.get(doc_name) == str(target_doc)
        assert docs.get("research") == str(target_doc)
        assert backend.docs_by_project[project["name"]][doc_name] == str(target_doc)
        assert backend.docs_by_project[project["name"]]["research"] == str(target_doc)
        assert "Status: active" in target_doc.read_text(encoding="utf-8")
