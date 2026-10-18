from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.doc_management.utils import classify_scribe_source_document
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.doc_management.special_create import _normalize_stage
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp import server as server_module
from scribe_mcp.config.repo_config import RepoConfig, resolve_create_doc_type_config


@contextmanager
def _isolated_server(state_manager, project_root=None):
    """Monkey-patch server module for isolated test execution."""
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
        session_id="test-session",
        stable_session_id="test-session",
    )
    server_module.get_agent_identity = lambda: None

    fake_root = Path(project_root).resolve() if project_root else Path("/tmp")
    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="test", repo_root=fake_root)

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
                tool_name=str(kwargs.get("tool_name") or "manage_docs"),
                project=current_project,
                recent_projects=list(getattr(state, "recent_projects", []) or []),
                state_snapshot=state_snapshot if isinstance(state_snapshot, dict) else {},
                reminders=[],
            )

        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
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
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = orig_prepare_context


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


async def _seed_runtime_session(
    state_manager: StateManager,
    project_root: str,
    session_id: str = "test-session",
) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(
            session_id=session_id,
            repo_root=project_root,
            mode="project",
        )


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
    assert not any(line.endswith((" ", "\t")) for line in parsed.body.splitlines())


@pytest.mark.asyncio
async def test_create_doc_strips_trailing_whitespace_from_body(tmp_path: Path) -> None:
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
            "doc_name": "whitespace_safe_doc",
            "doc_type": "note",
            "body": "# Whitespace  \nBody\t\n",
            "target_dir": str(target_dir),
        },
        dry_run=False,
    )

    assert change.success
    written = Path(change.path).read_text(encoding="utf-8")
    assert not any(line.endswith((" ", "\t")) for line in written.splitlines())
    assert "# Whitespace\n" in written


@pytest.mark.asyncio
async def test_create_doc_normalizes_top_level_workflow_metadata(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    target_dir = Path(project["docs_dir"]) / "custom"
    target_dir.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    class _AmbientIdentity:
        async def get_or_create_agent_id(self) -> str:
            return "agent-ambient-runtime"

    with _isolated_server(state_manager, project_root=project["root"]):
        server_module.get_agent_identity = lambda: _AmbientIdentity()
        result = await manage_docs(
            agent="GeneratedRuntimeAgent",
            action="create",
            doc_name="workflow_doc",
            metadata={
                "doc_name": "workflow_doc",
                "doc_type": "custom",
                "body": "# Workflow\nBody\n",
                "target_dir": str(target_dir),
                "summary": "workflow summary",
                "tags": "priority",
                "owners": ["alpha", "alpha", "beta", ""],
                "category": "internal|engineering",
                "status": "in_progress",
                "version": "1.2",
                "related_docs": ["phase_plan"],
                "maintained_by": "MaintainerA",
                "run_id": "run-1",
                "stage": "phase_1",
                "session_id": "session-9",
                "work_item_id": "work-22",
                "agent_id": "CoderAgent-Phase1",
            },
            dry_run=False,
        )

    assert result["ok"] is True, result
    parsed = parse_frontmatter(Path(result["path"]).read_text(encoding="utf-8"))
    fm = parsed.frontmatter_data
    assert fm.get("summary") == "workflow summary"
    assert fm.get("tags") == ["priority"]
    assert fm.get("owners") == ["alpha", "beta"]
    assert fm.get("category") in {"internal|engineering", "internal;engineering"}
    assert fm.get("status") == "in_progress"
    assert fm.get("version") == "1.2"
    assert fm.get("related_docs") == ["phase_plan"]
    assert fm.get("created_by") == "CoderAgent-Phase1"
    assert fm.get("maintained_by") == "MaintainerA"
    assert fm.get("edit_trace", {}).get("run_id") == "run-1"
    assert fm.get("edit_trace", {}).get("stage") == "phase_1"
    assert fm.get("edit_trace", {}).get("session_id") == "session-9"
    assert fm.get("edit_trace", {}).get("work_item_id") == "work-22"


@pytest.mark.asyncio
async def test_create_doc_allows_empty_body(tmp_path: Path) -> None:
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

    assert change.success
    path = Path(change.path)
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.has_frontmatter
    assert parsed.body.strip() == ""


@pytest.mark.asyncio
async def test_replace_section_cross_session_succeeds_when_review_report_registration_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await _setup_project(tmp_path)
    state_path = tmp_path / "state_cross_session.db"
    state_manager = StateManager(path=state_path)
    await state_manager.set_current_project(project["name"], project, agent_id="test")
    await _seed_runtime_session(state_manager, project["root"], session_id="test-session")

    with _isolated_server(state_manager, project_root=project["root"]):
        create_result = await manage_docs(
            agent="test-agent",
            action="create",
            metadata={"doc_type": "review", "stage": "phase_4_2"},
        )
        assert create_result["ok"] is True
        created_path = Path(str(create_result["path"]))
        assert created_path.exists()
        created_doc_name = str(create_result["doc_name"])
        before_text = created_path.read_text(encoding="utf-8")

    # Simulate a new session with stale/missing custom-doc registry mapping.
    state_reloaded = await state_manager.load()
    persisted = dict(state_reloaded.get_project(project["name"]) or project)
    persisted_docs = dict(persisted.get("docs", {}) or {})
    persisted_docs.pop(created_doc_name, None)
    persisted_docs.pop("review", None)
    persisted["docs"] = persisted_docs
    await state_manager.set_current_project(project["name"], persisted, agent_id="test")

    async def _blocked_register(*_args, **_kwargs):
        raise ValueError("Cannot establish authoritative session binding for manage_docs registration.")

    from scribe_mcp.doc_management import runtime as runtime_shared
    monkeypatch.setattr(runtime_shared, "register_document_path", _blocked_register)
    monkeypatch.setattr(runtime_shared.utils_shared, "resolve_custom_doc_path", lambda **_kwargs: created_path)

    with _isolated_server(state_manager, project_root=project["root"]):
        replace_result = await manage_docs(
            agent="test-agent",
            action="replace_section",
            doc_name=created_doc_name,
            doc_category="review",
            section="executive_summary",
            content="## Executive Summary\n\nCross-session review recovery content.\n",
            metadata={"allow_append": True},
        )
        assert replace_result["ok"] is True, replace_result
        assert "warnings" in replace_result
        assert any("registration degraded" in warning.lower() for warning in replace_result["warnings"])
        after_text = created_path.read_text(encoding="utf-8")
        assert after_text != before_text
        assert "Cross-session review recovery content." in after_text
@pytest.mark.asyncio
async def test_create_doc_registry_warning(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

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
        assert result["ok"] is True, result
        assert "warnings" in result
        assert "Registry update failed" in result["warnings"][0]
        assert "replace_section" in result.get("next_step_guidance", "")


@pytest.mark.asyncio
async def test_create_doc_returns_registration_status_when_docs_json_update_misses(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    class MissingRowStorage:
        async def update_project_docs(self, *_args, **_kwargs):
            return False

    with _isolated_server(state_manager, project_root=project["root"]):
        server_module.storage_backend = MissingRowStorage()
        result = await manage_docs(
            action="create",
            doc="custom_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "docs_json_miss_note",
                "body": "# Note\nRegistration should warn.",
                "register_doc": True,
            },
            dry_run=False,
        )

        assert result["ok"] is True
        status = result["registration_status"]
        assert status["file_written"] is True
        assert status["registration_requested"] is True
        assert status["docs_json_registered"] is False
        assert status["update_project_docs_result"] is False
        assert "rerun set_project" in status["available_action"]
        assert any("did not update docs_json" in warning for warning in result.get("warnings", []))


@pytest.mark.asyncio
async def test_manage_docs_create_doc_dry_run_does_not_register_doc(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

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
        assert "replace_section" in result.get("next_step_guidance", "")
        assert isinstance(result.get("editable_sections"), list)
        assert result.get("editable_sections")
        assert result.get("section_source") in {"anchors", "headings"}

        state = await state_manager.load()
        stored_project = state.get_project(project["name"])
        assert stored_project is not None
        assert "dry_run_note" not in (stored_project.get("docs") or {})

        preview_path = Path(result["path"])
        assert not preview_path.exists()

        warnings = result.get("warnings") or []
        assert any("register_doc skipped during dry_run" in warning for warning in warnings)
        status = result["registration_status"]
        assert status["file_written"] is False
        assert status["docs_json_registered"] is False
        assert "dry_run=false" in status["available_action"]


@pytest.mark.asyncio
async def test_manage_docs_create_doc_preserves_newlines(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

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
async def test_manage_docs_create_spec_routes_to_generic_create_doc(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="spec_doc",
            metadata={
                "doc_type": "spec",
                "doc_name": "SPEC_MANAGE_DOCS_REGISTRATION",
                "body": "# Spec\n\nRegistration behavior.",
            },
            dry_run=False,
        )
        assert result["ok"] is True
        created_path = Path(result["path"])
        assert created_path.name == "spec_doc.md"
        assert created_path.parent == Path(project["docs_dir"])

        parsed = parse_frontmatter(created_path.read_text(encoding="utf-8"))
        assert parsed.has_frontmatter
        assert parsed.frontmatter_data.get("doc_type") == "spec"
        assert parsed.frontmatter_data.get("doc_name") == "SPEC_MANAGE_DOCS_REGISTRATION"
        assert "# Spec" in parsed.body
        classification = classify_scribe_source_document(created_path, docs_dir=Path(project["docs_dir"]))
        assert classification is not None
        assert classification.doc_type == "spec"

        state = await state_manager.load()
        stored_project = state.get_project(project["name"])
        assert stored_project is not None
        assert stored_project.get("docs", {}).get("SPEC_MANAGE_DOCS_REGISTRATION") == str(created_path)


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
    await _seed_runtime_session(state_manager, project["root"])

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


def test_normalize_stage_prevents_unknown_filename_leakage() -> None:
    assert _normalize_stage(None) == "general"
    assert _normalize_stage("") == "general"
    assert _normalize_stage("unknown") == "general"
    assert _normalize_stage("Phase 1 / Review") == "phase_1_review"


@pytest.mark.asyncio
async def test_create_doc_with_md_suffix_does_not_double_append(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    target_dir = Path(project["docs_dir"]) / "custom"
    target_dir.mkdir(parents=True, exist_ok=True)

    change = await apply_doc_change(
        project,
        doc_name="already_named.md",
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
            "doc_type": "custom",
            "doc_name": "already_named.md",
            "body": "# Note\nBody.",
            "target_dir": str(target_dir),
        },
        dry_run=False,
    )

    assert change.success
    assert change.path is not None
    assert str(change.path).endswith("already_named.md")
    assert not str(change.path).endswith(".md.md")


@pytest.mark.asyncio
async def test_create_review_report_allows_followup_replace_section_with_same_session_binding(tmp_path: Path) -> None:
    """Regression: review report create + replace_section should succeed in one bound runtime session."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    with _isolated_server(state_manager, project_root=project["root"]):
        create_result = await manage_docs(
            action="create",
            metadata={
                "doc_type": "review",
                "stage": "phase_4_2",
            },
            dry_run=False,
        )
        assert create_result.get("ok") is True, create_result
        review_doc_name = str(create_result.get("doc_name") or "")
        assert review_doc_name

        replace_result = await manage_docs(
            action="replace_section",
            doc_name=review_doc_name,
            section="executive_summary",
            content="## Executive Summary\n\nReview content updated via manage_docs.\n",
            dry_run=False,
        )
        assert replace_result.get("ok") is True, replace_result


@pytest.mark.asyncio
async def test_manage_docs_create_uses_repo_config_doc_type_alias_and_transparency(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    repo_config_dir = Path(project["root"]) / ".scribe" / "config"
    repo_config_dir.mkdir(parents=True, exist_ok=True)
    (repo_config_dir / "scribe.yaml").write_text(
        "doc_types:\n"
        "  create_aliases:\n"
        "    incident: bug\n",
        encoding="utf-8",
    )

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="incident_note",
            metadata={
                "doc_type": "incident",
                "doc_name": "INCIDENT_001",
                "category": "runtime",
                "symptoms": "Symptom details",
            },
            dry_run=False,
        )
        assert result["ok"] is True
        assert result["requested_doc_type"] == "incident"
        assert result["resolved_doc_type"] == "bug"
        assert result["resolved_handler"] == "create_bug_report"
        assert result["config_source"] == "repo_config:doc_types.create_aliases"


@pytest.mark.asyncio
async def test_manage_docs_create_reserved_alias_config_fails_closed_with_warning(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    repo_config_dir = Path(project["root"]) / ".scribe" / "config"
    repo_config_dir.mkdir(parents=True, exist_ok=True)
    (repo_config_dir / "scribe.yaml").write_text(
        "doc_types:\n"
        "  create_aliases:\n"
        "    bug: security\n"
        "    incident: not_a_type\n",
        encoding="utf-8",
    )

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="incident_note",
            metadata={"doc_type": "incident", "doc_name": "INCIDENT_002"},
            dry_run=False,
        )
        assert result["ok"] is False
        warnings = result.get("warnings") or []
        assert any("reserved built-in doc_type" in warning for warning in warnings)
        assert any("not a valid built-in doc_type" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_manage_docs_create_custom_template_from_top_level_doc_types(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    repo_config_dir = Path(project["root"]) / ".scribe" / "config"
    repo_config_dir.mkdir(parents=True, exist_ok=True)
    (repo_config_dir / "scribe.yaml").write_text(
        "doc_types:\n"
        "  create_templates:\n"
        "    incident: RESEARCH_REPORT_TEMPLATE\n",
        encoding="utf-8",
    )

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="incident_from_template",
            metadata={"doc_type": "incident", "doc_name": "INCIDENT_TEMPLATE_001"},
            dry_run=False,
        )
        assert result["ok"] is True
        assert result["requested_doc_type"] == "incident"
        assert result["resolved_doc_type"] == "incident"
        assert result["resolved_handler"] == "create_doc"
        assert result["config_source"] == "repo_config:doc_types.create_templates"
        created = Path(result["path"])
        rendered_text = created.read_text(encoding="utf-8")
        assert "## Executive Summary" in rendered_text


@pytest.mark.asyncio
async def test_manage_docs_create_template_missing_fails_closed(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    repo_config_dir = Path(project["root"]) / ".scribe" / "config"
    repo_config_dir.mkdir(parents=True, exist_ok=True)
    (repo_config_dir / "scribe.yaml").write_text(
        "doc_types:\n"
        "  create_templates:\n"
        "    incident: DOES_NOT_EXIST_TEMPLATE\n",
        encoding="utf-8",
    )

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="incident_missing_template",
            metadata={"doc_type": "incident", "doc_name": "INCIDENT_TEMPLATE_404"},
            dry_run=False,
        )
        assert result["ok"] is False
        assert "Invalid configured template" in result.get("error", "")
        assert "Template resolution failed before doc registration" in result.get("suggestion", "")
        template_resolution = result.get("template_resolution")
        assert template_resolution["failure_kind"] == "template_resolution"
        assert template_resolution["registration_attempted"] is False
        assert template_resolution["requested_template"] == "DOES_NOT_EXIST_TEMPLATE"
        assert "custom" in template_resolution["available_doc_types"]
        assert "RESEARCH_REPORT_TEMPLATE" in template_resolution["available_templates"]
        assert "metadata.doc_type='custom'" in template_resolution["recommended_action"]
        warnings = result.get("warnings") or []
        assert any("was not found" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_manage_docs_create_alias_legacy_fallback_config_source(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    repo_config_dir = Path(project["root"]) / ".scribe" / "config"
    repo_config_dir.mkdir(parents=True, exist_ok=True)
    (repo_config_dir / "scribe.yaml").write_text(
        "reminder_config:\n"
        "  doc_types:\n"
        "    create_aliases:\n"
        "      incident: bug\n",
        encoding="utf-8",
    )

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="incident_note_legacy",
            metadata={
                "doc_type": "incident",
                "doc_name": "INCIDENT_LEGACY_ALIAS_001",
                "category": "runtime",
                "symptoms": "Legacy fallback alias path",
            },
            dry_run=False,
        )
        assert result["ok"] is True
        assert result["config_source"] == "repo_config:reminder_config.doc_types.create_aliases"


@pytest.mark.asyncio
async def test_special_bug_create_returns_registration_status_when_docs_json_update_misses(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    class MissingRowStorage:
        async def update_project_docs(self, *_args, **_kwargs):
            return False

        async def fetch_project(self, *_args, **_kwargs):
            return SimpleNamespace(docs_json="{}")

        async def upsert_case_registry_record(self, **_kwargs):
            return None

    with _isolated_server(state_manager, project_root=project["root"]):
        server_module.storage_backend = MissingRowStorage()
        result = await manage_docs(
            action="create",
            doc="bug_note",
            metadata={
                "doc_type": "bug",
                "doc_name": "BUG-REGISTRATION-001",
                "category": "runtime",
                "symptoms": "bug doc registration gap",
            },
            dry_run=False,
        )

        assert result["ok"] is True
        status = result["registration_status"]
        assert status["file_written"] is True
        assert status["docs_json_registered"] is False
        assert status["update_project_docs_result"] is False
        assert status["case_registry_registered"] is True
        assert "bug_note" in status["registration_keys"]
        assert any(key.startswith("bug_") for key in status["registration_keys"])
        assert "rerun set_project" in status["available_action"]
        assert "did not update docs_json" in result["registration_warning"]


@pytest.mark.asyncio
async def test_manage_docs_create_template_legacy_fallback_config_source(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    repo_config_dir = Path(project["root"]) / ".scribe" / "config"
    repo_config_dir.mkdir(parents=True, exist_ok=True)
    (repo_config_dir / "scribe.yaml").write_text(
        "reminder_config:\n"
        "  doc_types:\n"
        "    create_templates:\n"
        "      incident: RESEARCH_REPORT_TEMPLATE\n",
        encoding="utf-8",
    )

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="incident_template_legacy",
            metadata={"doc_type": "incident", "doc_name": "INCIDENT_LEGACY_TEMPLATE_001"},
            dry_run=False,
        )
        assert result["ok"] is True
        assert result["config_source"] == "repo_config:reminder_config.doc_types.create_templates"


def test_create_doc_type_config_includes_canonical_semantic_aliases(tmp_path: Path) -> None:
    repo_config = RepoConfig.defaults_for_repo(tmp_path)
    resolved = resolve_create_doc_type_config(repo_config)
    assert resolved.aliases["phase_plan"] == "custom"
    assert resolved.aliases["security_review"] == "security"


@pytest.mark.asyncio
async def test_canonical_doc_type_persists_through_create_and_frontmatter_update(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, project["root"])

    with _isolated_server(state_manager, project_root=project["root"]):
        created = await manage_docs(
            action="create",
            doc="phase_plan",
            metadata={
                "doc_name": "PHASE_PLAN_CANONICAL_PERSIST_001",
                "doc_type": "phase_plan",
                "intended_doc_type": "phase_plan",
            },
            dry_run=False,
        )
        assert created["ok"] is True

        updated = await manage_docs(
            action="frontmatter_update",
            doc="PHASE_PLAN_CANONICAL_PERSIST_001",
            metadata={"frontmatter": {"intended_doc_type": "review"}},
            dry_run=False,
        )
        assert updated["ok"] is True
        doc_path = Path(updated["path"])
        parsed = parse_frontmatter(doc_path.read_text(encoding="utf-8"))
        frontmatter = parsed.frontmatter_data
        assert frontmatter.get("doc_type") == "phase_plan"
        assert frontmatter.get("canonical_doc_type") == "review"
