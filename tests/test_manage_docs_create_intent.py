from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys

import anyio
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client
import pytest

from scribe_mcp.state import StateManager


@asynccontextmanager
async def _isolated_server(
    state_manager: StateManager, *, project_root: Path, project_name: str, agent: str
):
    """Use one disposable stdio server and its real caller binding per scenario."""
    source = Path(__file__).resolve().parents[1]
    (project_root / ".git").mkdir(exist_ok=True)
    runtime = state_manager._storage_backend._path.parent / "intent-runtime"
    runtime.mkdir(exist_ok=True)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key != "DATABASE_URL"}
    if "SCRIBE_RELEASE_PROFILE" in os.environ:
        env["SCRIBE_RELEASE_PROFILE"] = os.environ["SCRIBE_RELEASE_PROFILE"]
    env.update({
        "SCRIBE_DISABLE_DOTENV": "1", "SCRIBE_LOAD_REPO_DOTENV": "0",
        "SCRIBE_MODE": "standalone", "SCRIBE_STORAGE_BACKEND": "sqlite",
        "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(state_manager._storage_backend._path),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"), "SCRIBE_ROOT": str(runtime),
        "SCRIBE_REPO_ROOT": str(project_root), "SCRIBE_TRUSTED_REPO_ROOTS": str(project_root),
        "PYTHONPATH": str(source / "src"),
    })
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                   env=env, cwd=str(source))
    with anyio.fail_after(60):
        async with Client(stdio_client(params), mode="auto") as client:
            selected = await client.call_tool("set_project", {
                "agent": agent, "name": project_name, "root": str(project_root),
                "format": "structured",
            })
            selected_data = selected.structured_content
            if not isinstance(selected_data, dict):
                selected_data = json.loads("\n".join(
                    getattr(item, "text", "") for item in selected.content))
            if selected.is_error or selected_data.get("ok", True) is False:
                raise AssertionError(f"Real caller binding setup failed: {selected}")
            doctor = await client.call_tool("scribe_doctor", {"agent": agent})
            doctor_data = doctor.structured_content
            if not isinstance(doctor_data, dict):
                doctor_data = json.loads("\n".join(
                    getattr(item, "text", "") for item in doctor.content))
            authority = doctor_data["runtime"]["repo_authority"]
            binding = await state_manager._storage_backend.get_session_project(
                authority["authoritative_session_key"])
            assert binding is not None
            assert binding.project_name == project_name
            assert binding.canonical_repo_root == str(project_root.resolve())
            yield client


async def _call_manage_docs(client: Client, agent: str, **arguments) -> dict:
    result = await client.call_tool("manage_docs", {"agent": agent, **arguments})
    if isinstance(result.structured_content, dict):
        return result.structured_content
    return json.loads("\n".join(getattr(item, "text", "") for item in result.content))


async def _read_persisted_project(state_manager: StateManager, client: Client, agent: str) -> dict:
    """Observe the bound project's persisted metadata without selecting a target."""
    doctor = await client.call_tool("scribe_doctor", {"agent": agent})
    payload = doctor.structured_content
    if not isinstance(payload, dict):
        payload = json.loads("\n".join(getattr(item, "text", "") for item in doctor.content))
    authority = payload["runtime"]["repo_authority"]
    backend = state_manager._storage_backend
    binding = await backend.get_session_project(authority["authoritative_session_key"])
    assert binding is not None
    assert binding.project_name == authority["project_name"]
    assert binding.project_key == authority["project_key"]
    assert binding.canonical_repo_root == authority["repo_root"]
    record = await backend.fetch_project(binding.project_name,
        repo_root=binding.canonical_repo_root, project_key=binding.project_key)
    assert record is not None
    assert record.name == binding.project_name
    assert record.project_key == binding.project_key
    assert str(Path(record.repo_root).resolve()) == binding.canonical_repo_root
    return state_manager._record_to_project_dict(record)


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
async def test_create_custom_returns_governed_scaffold_intent(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(state_manager, project_root=Path(project["root"]),
                                project_name=project["name"], agent=test_agent) as client:
        result = await _call_manage_docs(client, test_agent,
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
    assert result.get("section_source") == "headings"
    assert result.get("first_write_action") == "apply_patch"
    assert "heading-derived section inventory" in result.get("next_step_guidance", "")
    assert "apply_patch" in result.get("next_step_guidance", "")
    assert "replace_range" in result.get("next_step_guidance", "")
    assert "INTENT_CUSTOM_DOC" in result.get("next_step_guidance", "")


@pytest.mark.asyncio
async def test_create_special_doc_returns_contentful_intent(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(state_manager, project_root=Path(project["root"]),
                                project_name=project["name"], agent=test_agent) as client:
        result = await _call_manage_docs(client, test_agent,
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
    assert result.get("first_write_action") == "replace_section"


@pytest.mark.asyncio
async def test_create_register_existing_returns_empty_registered_intent(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    docs_dir = Path(project["docs_dir"])
    existing = docs_dir / "existing_doc.md"
    existing.write_text("# Existing\n\nNo changes.", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(state_manager, project_root=Path(project["root"]),
                                project_name=project["name"], agent=test_agent) as client:
        result = await _call_manage_docs(client, test_agent,
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
async def test_create_special_doc_dry_run_includes_editable_sections(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(state_manager, project_root=Path(project["root"]),
                                project_name=project["name"], agent=test_agent) as client:
        result = await _call_manage_docs(client, test_agent,
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


@pytest.mark.asyncio
@pytest.mark.regression
async def test_create_review_dry_run_avoids_reserved_mcp_content_shape_and_side_effects(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(state_manager, project_root=Path(project["root"]),
                                project_name=project["name"], agent=test_agent) as client:
        original_docs = dict((await _read_persisted_project(state_manager, client, test_agent))["docs"])
        host_result = await client.call_tool(
            "manage_docs",
            {
                "agent": test_agent,
                "action": "create",
                "doc": "REVIEW_CI_RUNNER_01",
                "project": project["name"],
                "metadata": {
                    "doc_type": "review",
                    "doc_name": "REVIEW_CI_RUNNER_01",
                    "stage": "general",
                },
                "dry_run": True,
            },
        )
        persisted_project = await _read_persisted_project(state_manager, client, test_agent)

    assert isinstance(host_result.content, Sequence)
    assert not isinstance(host_result.content, (str, bytes))
    result = host_result.structured_content
    assert isinstance(result, dict)
    assert result["ok"] is True, result
    assert result["dry_run"] is True
    assert "content" not in result
    assert isinstance(result.get("preview"), str)
    assert result["preview"]
    assert not Path(result["path"]).exists()

    assert persisted_project is not None
    assert persisted_project["docs"] == original_docs
    assert "REVIEW_CI_RUNNER_01" not in persisted_project["docs"]
