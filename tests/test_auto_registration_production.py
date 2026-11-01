from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from scribe_mcp.state import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from test_manage_docs_create_intent import (
    _call_manage_docs,
    _isolated_server,
    _read_persisted_project,
)


@pytest_asyncio.fixture
async def state_manager(tmp_path: Path):
    backend = SQLiteStorage(tmp_path / "registration.sqlite")
    await backend.setup()
    try:
        yield StateManager(path=tmp_path / "state.json", storage_backend=backend)
    finally:
        await backend.close()


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "auto_registration_prod_repo"
    docs_dir = (
        project_root
        / ".scribe"
        / "docs"
        / "dev_plans"
        / "auto_registration_production_project"
    )
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Auto Registration Production Project",
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


@pytest.mark.regression
@pytest.mark.asyncio
async def test_read_only_actions_auto_register_existing_physical_docs(
    tmp_path: Path, state_manager: StateManager, test_agent: str
) -> None:
    project = await _setup_project(tmp_path)
    await state_manager.set_current_project(project["name"], project)

    docs_dir = Path(project["docs_dir"])
    detached_name = "UNREGISTERED_READONLY"
    target_doc = docs_dir / f"{detached_name}.md"
    target_doc.write_text("# Detached\n\n- [ ] Detached task\n", encoding="utf-8")

    async with _isolated_server(
        state_manager, project_root=Path(project["root"]),
        project_name=project["name"], agent=test_agent,
    ) as client:
        before = await _read_persisted_project(state_manager, client, test_agent)
        assert detached_name not in before.get("docs", {})
        list_sections = await _call_manage_docs(client, test_agent,
            action="list_sections",
            doc=detached_name,
            project=project["name"],
        )
        assert list_sections["ok"] is True
        assert list_sections["path"] == str(target_doc)

        list_checklist = await _call_manage_docs(client, test_agent,
            action="list_checklist_items",
            doc=detached_name,
            project=project["name"],
        )
        assert list_checklist["ok"] is False
        assert "DOC_NOT_FOUND" not in list_checklist["error"]

        search_result = await _call_manage_docs(client, test_agent,
            action="search",
            doc=detached_name,
            metadata={"query": "Detached"},
            project=project["name"],
        )
        assert search_result["ok"] is True

        stored_project = await _read_persisted_project(state_manager, client, test_agent)
        assert stored_project is not None
        assert stored_project.get("docs", {}).get(detached_name) == str(target_doc)
        # A fresh SQLite reader proves registration survived beyond caller caches.
        reader = SQLiteStorage(state_manager._storage_backend._path)
        await reader.setup()
        try:
            record = await reader.fetch_project(project["name"], repo_root=project["root"])
            assert record is not None
            assert json.loads(record.docs_json)[detached_name] == str(target_doc)
        finally:
            await reader.close()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mutation_fails_explicitly_when_file_cannot_be_resolved_or_missing(
    tmp_path: Path, state_manager: StateManager, test_agent: str
) -> None:
    project = await _setup_project(tmp_path)
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(
        state_manager, project_root=Path(project["root"]),
        project_name=project["name"], agent=test_agent,
    ) as client:
        unresolved = await _call_manage_docs(client, test_agent,
            action="replace_text",
            doc="definitely/nonexistent/path",
            metadata={"old_text": "x", "new_text": "y"},
            project=project["name"],
            dry_run=False,
        )
        assert unresolved["ok"] is False
        assert "Auto-registration failed" in unresolved["error"]

        missing = await _call_manage_docs(client, test_agent,
            action="replace_text",
            doc="MISSING_AFTER_RESOLVE",
            metadata={"old_text": "x", "new_text": "y"},
            project=project["name"],
            dry_run=False,
        )
        assert missing["ok"] is False
        assert "Auto-registration failed" in missing["error"]
        auto_registration_error = str(missing.get("auto_registration_error", ""))
        assert (
            "does not exist" in auto_registration_error
            or "Invalid document identifier" in auto_registration_error
            or "outside project root" in auto_registration_error
        )
