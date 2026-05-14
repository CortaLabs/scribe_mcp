from __future__ import annotations

import json
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
def _isolated_server(
    state_manager: StateManager,
    *,
    project_root: Path,
    session_id: str = "cleanup-test-session",
):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)
    from scribe_mcp.tools import manage_docs as manage_docs_module

    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context

    server_module.state_manager = state_manager
    server_module.storage_backend = getattr(state_manager, "_storage_backend", None)
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project",
        session_id=session_id,
        stable_session_id=session_id,
    )
    server_module.get_agent_identity = lambda: None

    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="test", repo_root=project_root)

    try:
        async def _prepare_context_stub(**kwargs):
            state = await state_manager.load()
            explicit_project = kwargs.get("explicit_project")
            current_name = str(explicit_project).strip() if explicit_project else state.current_project
            if not current_name and getattr(state, "recent_projects", None):
                current_name = state.recent_projects[0]
            current_project = state.get_project(current_name) if current_name else None
            state_snapshot = kwargs.get("state_snapshot")
            return LoggingContext(
                tool_name="manage_docs",
                project=current_project,
                recent_projects=list(getattr(state, "recent_projects", []) or []),
                state_snapshot=state_snapshot if isinstance(state_snapshot, dict) else {},
                reminders=[],
                resolution_source="session_binding",
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


async def _seed_runtime_session(state_manager: StateManager, session_id: str, repo_root: str) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(
            session_id=session_id,
            transport_session_id=session_id,
            repo_root=repo_root,
            mode="project",
        )


def _project_payload(project_root: Path, slug: str, *, research_doc: str | None = None) -> dict:
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / slug
    docs_dir.mkdir(parents=True, exist_ok=True)
    for filename, title in (
        ("ARCHITECTURE_GUIDE.md", "Architecture"),
        ("PHASE_PLAN.md", "Phase"),
        ("CHECKLIST.md", "Checklist"),
        ("PROGRESS_LOG.md", "Log"),
    ):
        (docs_dir / filename).write_text(f"# {title}\n", encoding="utf-8")

    docs = {
        "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
        "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
        "checklist": str(docs_dir / "CHECKLIST.md"),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
    }
    if research_doc:
        research_dir = docs_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        doc_path = research_dir / f"{research_doc}.md"
        doc_path.write_text("# Research\n\nCleanup support.\n", encoding="utf-8")
        docs[research_doc] = str(doc_path)

    return {
        "name": slug.replace("_", " ").title(),
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": docs,
    }


@pytest.mark.asyncio
async def test_project_health_surfaces_recent_cross_project_docs(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo"
    active_project = _project_payload(project_root, "active_project")
    other_project = _project_payload(project_root, "other_project", research_doc="RESEARCH_DRIFTED")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(other_project["name"], other_project)
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="project_health",
            metadata={"limit": 10},
            dry_run=True,
        )

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    cross_project = result.get("cross_project_recent_docs") or []
    assert any("RESEARCH_DRIFTED.md" in entry.get("path", "") for entry in cross_project)
    digest = result.get("organization_digest") or {}
    ownership = digest.get("ownership_summary") or {}
    assert isinstance(ownership.get("cross_project"), int)
    status_sections = digest.get("status_sections") or {}
    for key in ("organization", "index", "archive", "artifact_claims", "ownership", "dev_plan_roots"):
        assert key in status_sections
    archive = status_sections["archive"]
    assert archive["cleanup_mode"] == "preview_only"
    assert archive["destructive_default"] is False
    roots = status_sections["dev_plan_roots"]["details"]
    assert roots["modern"]["root_kind"] == "modern"
    assert roots["legacy"]["root_kind"] == "legacy"


@pytest.mark.asyncio
async def test_project_health_archive_preview_classifies_legacy_docs_lane(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_legacy"
    legacy_docs_dir = project_root / "docs" / "dev_plans" / "legacy_project"
    research_dir = legacy_docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    archive_group = legacy_docs_dir / "archive" / "preflight" / "research"
    archive_group.mkdir(parents=True, exist_ok=True)
    (archive_group / "evidence.md").write_text("archive evidence", encoding="utf-8")

    active_project = {
        "name": "legacy_project",
        "root": str(project_root),
        "docs_dir": str(legacy_docs_dir),
        "progress_log": str(legacy_docs_dir / "PROGRESS_LOG.md"),
        "docs": {"RESEARCH_SAMPLE": str(research_dir / "RESEARCH_SAMPLE.md")},
    }
    (research_dir / "RESEARCH_SAMPLE.md").write_text("# Sample", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(action="project_health", metadata={"limit": 10}, dry_run=True)

    status_sections = (result.get("organization_digest") or {}).get("status_sections") or {}
    assert (status_sections.get("dev_plan_roots") or {}).get("status") == "compatibility_present"
    archive = status_sections.get("archive") or {}
    preview_groups = archive.get("preview_groups") or []
    assert preview_groups
    assert all(group.get("root_kind") == "legacy" for group in preview_groups)
    assert all(group.get("lane_class") == "compatibility" for group in preview_groups)


@pytest.mark.asyncio
async def test_rehome_doc_moves_registered_research_doc_to_target_project(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_rehome"
    source_project = _project_payload(project_root, "source_project", research_doc="RESEARCH_DRIFTED")
    target_project = _project_payload(project_root, "target_project")
    source_doc_path = Path(source_project["docs"]["RESEARCH_DRIFTED"])

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(target_project["name"], target_project)
    await state_manager.set_current_project(source_project["name"], source_project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", source_project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="rehome_doc",
            doc="RESEARCH_DRIFTED",
            metadata={"target_project": target_project["name"]},
            dry_run=False,
        )

    assert result["ok"] is True
    assert not source_doc_path.exists()
    target_path = Path(result["target_path"])
    assert target_path.exists()
    assert target_path.is_relative_to(Path(target_project["docs_dir"]))

    backend = getattr(state_manager, "_storage_backend", None)
    assert backend is not None
    target_record = await backend.fetch_project(target_project["name"])
    assert target_record is not None
    target_docs = json.loads(target_record.docs_json or "{}")
    assert target_docs["RESEARCH_DRIFTED"] == str(target_path)
    verification = result.get("rehome_verification") or {}
    assert verification["file_location"]["ok"] is True
    assert verification["registry_mapping"]["source_mapping_removed"] is True
    assert verification["registry_mapping"]["target_mapping_written"] is True
    assert verification["quality_check_binding"]["project"] == target_project["name"]
    assert verification["quality_check_binding"]["attempted"] is True
    assert isinstance(verification["quality_check_binding"]["ok"], bool)
    assert isinstance((verification["quality_check_binding"].get("summary") or {}).get("total_warnings"), int)
    assert isinstance((verification["quality_check_binding"].get("summary") or {}).get("readiness_blocker_count"), int)
    assert verification["readiness"]["attempted"] is True
    assert isinstance(verification["readiness"]["ok"], bool)
    assert isinstance(verification["readiness"]["readiness_blocker_count"], int)
    assert verification["index_freshness"]["index_freshness_reported_separately"] is True

    cached_state = await state_manager.load()
    cached_target_project = cached_state.get_project(target_project["name"])
    assert cached_target_project is not None
    assert cached_target_project["docs"]["RESEARCH_DRIFTED"] == str(target_path)

    with _isolated_server(state_manager, project_root=project_root):
        quality_result = await manage_docs(
            action="quality_check",
            doc="RESEARCH_DRIFTED",
            project=target_project["name"],
            dry_run=True,
        )

    assert quality_result["ok"] is True
    assert quality_result["scope"]["doc_name"] == "RESEARCH_DRIFTED"
    assert quality_result["scope"]["path"] == str(target_path)


@pytest.mark.asyncio
async def test_rehome_doc_recovers_registered_repo_root_research_doc(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_rehome_root_research"
    source_project = _project_payload(project_root, "source_project")
    target_project = _project_payload(project_root, "target_project")
    misplaced_research_dir = project_root / "research"
    misplaced_research_dir.mkdir(parents=True, exist_ok=True)
    source_doc_path = misplaced_research_dir / "RESEARCH_DRIFTED.md"
    source_doc_path.write_text("# Research\n\nMisplaced at repo root.\n", encoding="utf-8")
    source_project["docs"]["RESEARCH_DRIFTED"] = str(source_doc_path)

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(target_project["name"], target_project)
    await state_manager.set_current_project(source_project["name"], source_project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", source_project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="rehome_doc",
            doc="RESEARCH_DRIFTED",
            metadata={"target_project": target_project["name"]},
            dry_run=False,
        )

    assert result["ok"] is True
    assert not source_doc_path.exists()
    target_path = Path(result["target_path"])
    assert target_path == Path(target_project["docs_dir"]) / "research" / "RESEARCH_DRIFTED.md"
    assert target_path.exists()

    backend = getattr(state_manager, "_storage_backend", None)
    assert backend is not None
    source_record = await backend.fetch_project(source_project["name"])
    target_record = await backend.fetch_project(target_project["name"])
    assert source_record is not None
    assert target_record is not None
    assert "RESEARCH_DRIFTED" not in json.loads(source_record.docs_json or "{}")
    assert json.loads(target_record.docs_json or "{}")["RESEARCH_DRIFTED"] == str(target_path)
    verification = result.get("rehome_verification") or {}
    assert verification["registry_mapping"]["source_mapping_removed"] is True
    assert verification["registry_mapping"]["target_mapping_written"] is True
    assert verification["index_freshness"]["target_research_index_refresh"] == "updated"


@pytest.mark.asyncio
async def test_rehome_doc_registers_unowned_repo_root_research_doc_on_move(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_rehome_unowned_root_research"
    active_project = _project_payload(project_root, "active_project")
    target_project = _project_payload(project_root, "target_project")
    misplaced_research_dir = project_root / "research"
    misplaced_research_dir.mkdir(parents=True, exist_ok=True)
    source_doc_path = misplaced_research_dir / "RESEARCH_UNOWNED.md"
    source_doc_path.write_text("# Research\n\nUnowned misplaced doc.\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(target_project["name"], target_project)
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="rehome_doc",
            doc="research/RESEARCH_UNOWNED.md",
            metadata={"target_project": target_project["name"]},
            dry_run=False,
        )

    assert result["ok"] is True
    target_path = Path(result["target_path"])
    assert target_path == Path(target_project["docs_dir"]) / "research" / "RESEARCH_UNOWNED.md"
    assert target_path.exists()
    assert not source_doc_path.exists()

    backend = getattr(state_manager, "_storage_backend", None)
    assert backend is not None
    target_record = await backend.fetch_project(target_project["name"])
    assert target_record is not None
    target_docs = json.loads(target_record.docs_json or "{}")
    assert target_docs["RESEARCH_UNOWNED"] == str(target_path)
    verification = result.get("rehome_verification") or {}
    assert verification["registry_mapping"]["source_registered"] is False
    assert verification["registry_mapping"]["source_mapping_removed"] is True
    assert verification["registry_mapping"]["target_mapping_written"] is True


@pytest.mark.asyncio
async def test_rehome_doc_same_project_target_dir_research_moves_to_canonical_path(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_rehome_same_project_research"
    project = _project_payload(project_root, "active_project")
    docs_dir = Path(project["docs_dir"])
    source_doc_path = docs_dir / "RESEARCH_CHANGELOG_UX_AGENT_CONTRACT_MAAT.md"
    source_doc_path.write_text("# Research\n\nNoncanonical root research doc.\n", encoding="utf-8")
    project["docs"]["RESEARCH_CHANGELOG_UX_AGENT_CONTRACT_MAAT"] = str(source_doc_path)

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="rehome_doc",
            doc="RESEARCH_CHANGELOG_UX_AGENT_CONTRACT_MAAT",
            target_dir="research",
            metadata={"target_project": project["name"]},
            dry_run=False,
        )

    assert result["ok"] is True, result
    target_path = Path(result["target_path"])
    expected_path = docs_dir / "research" / "RESEARCH_CHANGELOG_UX_AGENT_CONTRACT_MAAT.md"
    assert target_path == expected_path
    assert target_path.exists()
    assert not source_doc_path.exists()
    assert result["target_path"] != str(source_doc_path)

    with _isolated_server(state_manager, project_root=project_root):
        quality = await manage_docs(
            action="quality_check",
            doc="RESEARCH_CHANGELOG_UX_AGENT_CONTRACT_MAAT",
            project=project["name"],
            dry_run=True,
        )

    assert quality["ok"] is True, quality
    warning_codes = {item.get("code") for item in quality.get("warnings", [])}
    assert "SCF_NONCANONICAL_LOCATION" not in warning_codes
    assert "SCF_DOC_UNINDEXED" not in warning_codes


@pytest.mark.asyncio
async def test_rehome_doc_target_dir_never_creates_nested_scribe_tree(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_rehome_no_nested_scribe"
    project = _project_payload(project_root, "active_project")
    docs_dir = Path(project["docs_dir"])
    source_doc_path = docs_dir / "RESEARCH_NESTED_SCRIBE_GUARD.md"
    source_doc_path.write_text("# Research\n\nGuard nested .scribe paths.\n", encoding="utf-8")
    project["docs"]["RESEARCH_NESTED_SCRIBE_GUARD"] = str(source_doc_path)

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="rehome_doc",
            doc="RESEARCH_NESTED_SCRIBE_GUARD",
            target_dir=".scribe/docs/dev_plans/active_project/research",
            metadata={"target_project": project["name"]},
            dry_run=True,
        )

    assert result["ok"] is True, result
    target_path = Path(result["target_path"])
    expected_path = docs_dir / "research" / "RESEARCH_NESTED_SCRIBE_GUARD.md"
    assert target_path == expected_path
    assert ".scribe" not in target_path.relative_to(docs_dir).parts
    assert f"{docs_dir}/.scribe" not in str(target_path)


@pytest.mark.asyncio
async def test_manage_docs_supported_actions_manifest_surfaces_cleanup_actions(tmp_path: Path) -> None:
    project_root = tmp_path / "cleanup_repo_manifest"
    active_project = _project_payload(project_root, "active_project")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "cleanup-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root):
        result = await manage_docs(
            action="list_sections",
            doc="architecture",
            dry_run=True,
        )

    manifest = result.get("supported_actions")
    assert isinstance(manifest, dict)
    cleanup_actions = manifest.get("cleanup_actions")
    assert cleanup_actions == ["project_health", "rehome_doc"]
    assert "project_health" in (manifest.get("all_actions") or [])
    assert "rehome_doc" in (manifest.get("all_actions") or [])
