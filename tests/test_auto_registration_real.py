from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.client.client import Client

from scribe_mcp.state import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from test_manage_docs_create_doc import _call_manage_docs, _isolated_server
from test_manage_docs_create_intent import _read_persisted_project


pytestmark = pytest.mark.regression


async def _read_registered_project(
    state_manager: StateManager, client: Client, agent: str,
) -> tuple[dict, dict[str, str]]:
    """Read the real binding, then verify its mappings with a fresh DB client."""
    project = await _read_persisted_project(state_manager, client, agent)
    reader = SQLiteStorage(state_manager._storage_backend._path)
    try:
        await reader.setup()
        record = await reader.fetch_project(
            project["name"], repo_root=project["root"], project_key=project["project_key"],
        )
        assert record is not None
        assert record.project_key == project["project_key"]
        return project, json.loads(record.docs_json)
    finally:
        await reader.close()


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
async def test_mutation_auto_registers_unregistered_root_doc(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    docs_dir = Path(project["docs_dir"])
    target_doc = docs_dir / "UNREGISTERED_ROOT.md"
    target_doc.write_text("# Root Doc\nStatus: draft\n", encoding="utf-8")

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"],
        agent=test_agent,
    ) as client:
        before = await _read_persisted_project(state_manager, client, test_agent)
        assert str(target_doc) not in before["docs"].values()
        result = await _call_manage_docs(
            client, test_agent,
            action="replace_text",
            doc="UNREGISTERED_ROOT",
            metadata={"find": "draft", "replace": "active"},
            project=project["name"],
            dry_run=False,
        )
        assert result["ok"] is True

        stored_project, persisted_docs = await _read_registered_project(
            state_manager, client, test_agent,
        )
        assert stored_project is not None
        assert stored_project.get("docs", {}).get("UNREGISTERED_ROOT") == str(target_doc)
        assert persisted_docs["UNREGISTERED_ROOT"] == str(target_doc)
        assert "Status: active" in target_doc.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_list_sections_auto_registers_unregistered_physical_doc(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    docs_dir = Path(project["docs_dir"])
    target_doc = docs_dir / "RAILS_MAP_CURRENT_STATE.md"
    target_doc.write_text(
        "---\n"
        "title: Rails Map Current State\n"
        "doc_type: custom\n"
        "---\n"
        "# Rails Map\n\n"
        "## Current State\n\n"
        "Ready.\n",
        encoding="utf-8",
    )

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"],
        agent=test_agent,
    ) as client:
        before = await _read_persisted_project(state_manager, client, test_agent)
        assert str(target_doc) not in before["docs"].values()
        result = await _call_manage_docs(
            client, test_agent,
            action="list_sections",
            doc="RAILS_MAP_CURRENT_STATE",
            project=project["name"],
        )
        assert result["ok"] is True
        assert result["doc_name"] == "RAILS_MAP_CURRENT_STATE"
        assert [section["id"] for section in result["sections"]] == [
            "rails_map",
            "current_state",
        ]

        lower_result = await _call_manage_docs(
            client, test_agent,
            action="list_sections",
            doc="rails_map_current_state",
            project=project["name"],
        )
        assert lower_result["ok"] is True
        assert lower_result["path"] == str(target_doc)

        relative_result = await _call_manage_docs(
            client, test_agent,
            action="list_sections",
            doc=str(target_doc.relative_to(Path(project["root"]))),
            project=project["name"],
        )
        assert relative_result["ok"] is True
        assert relative_result["path"] == str(target_doc)

        stored_project, persisted_docs = await _read_registered_project(
            state_manager, client, test_agent,
        )
        assert stored_project is not None
        assert stored_project.get("docs", {}).get("RAILS_MAP_CURRENT_STATE") == str(target_doc)
        assert persisted_docs["RAILS_MAP_CURRENT_STATE"] == str(target_doc)


@pytest.mark.asyncio
async def test_mutation_auto_registers_custom_doc_with_persistent_mapping(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    docs_dir = Path(project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    doc_name = "RESEARCH_UNREGISTERED_FLOW"
    target_doc = research_dir / f"{doc_name}.md"
    target_doc.write_text("# Research\nStatus: draft\n", encoding="utf-8")

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"],
        agent=test_agent,
    ) as client:
        before = await _read_persisted_project(state_manager, client, test_agent)
        assert str(target_doc) not in before["docs"].values()
        result = await _call_manage_docs(
            client, test_agent,
            action="replace_text",
            doc_category="research",
            doc=doc_name,
            metadata={"find": "draft", "replace": "active"},
            project=project["name"],
            dry_run=False,
        )
        assert result["ok"] is True

        stored_project, persisted_docs = await _read_registered_project(
            state_manager, client, test_agent,
        )
        assert stored_project is not None
        docs = stored_project.get("docs", {})
        assert docs.get(doc_name) == str(target_doc)
        assert docs.get("research") == str(target_doc)
        assert persisted_docs[doc_name] == str(target_doc)
        assert persisted_docs["research"] == str(target_doc)
        assert "Status: active" in target_doc.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_path_like_auto_registration_preserves_existing_stem_alias(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")

    docs_dir = Path(project["docs_dir"])
    root_doc = docs_dir / "COLLISION.md"
    root_doc.write_text("# Root Collision\n", encoding="utf-8")
    project["docs"]["COLLISION"] = str(root_doc)

    await state_manager.set_current_project(project["name"], project)

    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    target_doc = research_dir / "COLLISION.md"
    target_doc.write_text("# Research Collision\n", encoding="utf-8")
    path_like_doc = str(target_doc.relative_to(Path(project["root"])))

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"],
        agent=test_agent,
    ) as client:
        before = await _read_persisted_project(state_manager, client, test_agent)
        assert str(target_doc) not in before["docs"].values()
        result = await _call_manage_docs(
            client, test_agent,
            action="list_sections",
            doc=path_like_doc,
            project=project["name"],
        )
        assert result["ok"] is True
        assert result["path"] == str(target_doc)

        stored_project, persisted_docs = await _read_registered_project(
            state_manager, client, test_agent,
        )
        assert stored_project is not None
        docs = stored_project.get("docs", {})
        assert docs["COLLISION"] == str(root_doc)
        assert docs[path_like_doc] == str(target_doc)
        assert persisted_docs["COLLISION"] == str(root_doc)
        assert persisted_docs[path_like_doc] == str(target_doc)
