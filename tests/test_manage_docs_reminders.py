from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.reminders import reset_reminder_cooldowns
from scribe_mcp.reminders import get_reminders
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager, project_root=None):
    """Neutralize execution-context routing so tests can use isolated project state."""
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
    server_module.get_execution_context = lambda: None
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
    project_root = tmp_path / "reminder_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "# Architecture\n<!-- ID: problem_statement -->\nSeed\n",
        encoding="utf-8",
    )
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")
    (docs_dir / "DECISIONS.md").write_text("[2026-05-01] custom log entry\n", encoding="utf-8")
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

    return {
        "name": "Test Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            "decisions": str(docs_dir / "DECISIONS.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }


@pytest.mark.asyncio
async def test_manage_docs_reminder_scaffold_and_non_scaffold(tmp_path: Path) -> None:
    """Ensure replace_section reminders distinguish scaffold vs non-scaffold usage."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        reset_reminder_cooldowns(project_root=project["root"])
        scaffold_result = await manage_docs(
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="Scaffold",
            metadata={"scaffold": "TRUE "},
            dry_run=True,
        )

        scaffold_messages = [r["message"] for r in scaffold_result.get("reminders", [])]
        assert not any("prefer apply_patch" in msg.lower() for msg in scaffold_messages)

        reset_reminder_cooldowns(project_root=project["root"])
        non_scaffold_result = await manage_docs(
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="Edit",
            metadata={"scaffold": False},
            dry_run=True,
        )

        non_scaffold_messages = [r["message"] for r in non_scaffold_result.get("reminders", [])]
        assert all(isinstance(msg, str) for msg in non_scaffold_messages)
        if any("apply_patch" in msg.lower() or "replace_section" in msg.lower() for msg in non_scaffold_messages):
            assert any("apply_patch" in msg.lower() for msg in non_scaffold_messages)
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend


@pytest.mark.asyncio
async def test_manage_docs_successful_edit_has_no_vector_runtime_reminder(tmp_path: Path) -> None:
    """Successful edit responses must not advertise removed built-in vector flows."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        reset_reminder_cooldowns(project_root=project["root"])
        result = await manage_docs(
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="## Problem Statement\n\nUpdated problem statement\n",
            metadata={"scaffold": False},
            dry_run=False,
        )

        assert result["ok"] is True, result
        reminder_messages = [r["message"] for r in result.get("reminders", [])]
        assert not any("vector_index_docs" in msg for msg in reminder_messages)
        assert not any(".scribe/config/scribe.yaml" in msg for msg in reminder_messages)
        assert not any("scripts/reindex_vector.py --docs" in msg for msg in reminder_messages)
        assert not any(r.get("category") == "vector_index_docs" for r in result.get("reminders", []))


@pytest.mark.asyncio
async def test_manage_docs_reminder_precision_tools_no_nag(tmp_path: Path) -> None:
    """Ensure apply_patch/replace_range do not trigger replace_section reminders."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        patch_text = "\n".join(
            [
                "--- before",
                "+++ after",
                "@@ -1,2 +1,2 @@",
                "-# Architecture",
                "+# Architecture Updated",
                " <!-- ID: problem_statement -->",
            ]
        )

        patch_result = await manage_docs(
            action="apply_patch",
            doc="architecture",
            patch=patch_text,
            patch_mode="unified",
            dry_run=True,
        )

        patch_messages = [r["message"] for r in patch_result.get("reminders", [])]
        assert not any("For edits, prefer manage_docs apply_patch" in msg for msg in patch_messages)
        assert not any("Scaffolding detected" in msg for msg in patch_messages)

        structured_result = await manage_docs(
            action="apply_patch",
            doc="architecture",
            edit={
                "type": "replace_range",
                "start_line": 1,
                "end_line": 1,
                "content": "# Architecture Updated\n",
            },
            dry_run=True,
        )

        structured_messages = [r["message"] for r in structured_result.get("reminders", [])]
        assert not any("For edits, prefer manage_docs apply_patch" in msg for msg in structured_messages)
        assert not any("Scaffolding detected" in msg for msg in structured_messages)

        range_result = await manage_docs(
            action="replace_range",
            doc="architecture",
            start_line=1,
            end_line=1,
            content="# Architecture Updated\n",
            dry_run=True,
        )

        range_messages = [r["message"] for r in range_result.get("reminders", [])]
        assert not any("For edits, prefer manage_docs apply_patch" in msg for msg in range_messages)
        assert not any("Scaffolding detected" in msg for msg in range_messages)
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend


@pytest.mark.asyncio
async def test_manage_docs_create_returns_next_step_guidance(tmp_path: Path) -> None:
    """create responses should include explicit scaffold follow-up guidance."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="create",
            doc="custom_doc",
            metadata={
                "doc_type": "custom",
                "doc_name": "guidance_note",
                "body": "# Guidance\n\nBody content.",
            },
            dry_run=True,
        )

    assert result["ok"] is True
    assert "replace_section" in result.get("next_step_guidance", "")


@pytest.mark.asyncio
async def test_readiness_claim_blocked_but_edit_persists(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_server(state_manager, project_root=project["root"]):
        write_result = await manage_docs(
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="[fill this section]\n",
            metadata={"scaffold": False},
            dry_run=False,
        )
        assert write_result["ok"] is True

        result = await manage_docs(
            action="frontmatter_update",
            doc="architecture",
            metadata={"frontmatter": {"status": "complete"}},
            dry_run=False,
        )

    assert result["ok"] is False
    assert result.get("code") == "DOC_NOT_DONE_SCAFFOLD_QUALITY"
    blockers = result.get("readiness_blockers") or []
    assert blockers
    assert any(b.get("code") == "SCF_PLACEHOLDER_BRACKET" for b in blockers)
    persisted = Path(project["docs"]["architecture"]).read_text(encoding="utf-8")
    assert "[fill this section]" in persisted
    assert "status: complete" not in persisted


@pytest.mark.asyncio
async def test_replace_section_with_readiness_claim_blocks_whole_mutation(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original = Path(project["docs"]["architecture"]).read_text(encoding="utf-8")
    with _isolated_server(state_manager, project_root=project["root"]):
        result = await manage_docs(
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="[fill this section]\n",
            metadata={"frontmatter": {"status": "complete"}},
            dry_run=False,
        )

    assert result["ok"] is False
    assert result.get("code") == "DOC_NOT_DONE_SCAFFOLD_QUALITY"
    blockers = result.get("readiness_blockers") or []
    assert blockers
    persisted = Path(project["docs"]["architecture"]).read_text(encoding="utf-8")
    assert persisted == original
    assert "status: complete" not in persisted
    assert "[fill this section]" not in persisted


@pytest.mark.asyncio
async def test_quality_reminder_categories_and_cooldown(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    project["defaults"] = {
        "reminder": {
            "quality_cooldown_minutes": 60,
            "scaffold_residue_category": "scaffold_residue_custom",
            "frontmatter_mismatch_category": "frontmatter_mismatch_custom",
            "stale_research_index_category": "stale_index_custom",
        }
    }
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")

    reset_reminder_cooldowns(project_root=project["root"])
    with patch("scribe_mcp.reminders._resolve_reminder_storage", return_value=None):
        from scribe_mcp import reminders as reminders_module
        reminders_module._reminder_engine = None
        first = await get_reminders(project, tool_name="manage_docs", state=None, agent_id="qa")
        cats = {r.get("category") for r in first}
        assert "scaffold_residue_custom" in cats
        assert "frontmatter_mismatch_custom" in cats

        second = await get_reminders(project, tool_name="manage_docs", state=None, agent_id="qa")
        cats2 = {r.get("category") for r in second}
        assert "scaffold_residue_custom" not in cats2
        assert "frontmatter_mismatch_custom" not in cats2


@pytest.mark.asyncio
async def test_quality_reminders_ignore_configured_custom_logs(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text("---\nstatus: complete\n---\nFinal architecture content.\n", encoding="utf-8")

    reset_reminder_cooldowns(project_root=project["root"])
    with patch("scribe_mcp.reminders._resolve_reminder_storage", return_value=None):
        from scribe_mcp import reminders as reminders_module

        reminders_module._reminder_engine = None
        result = await get_reminders(project, tool_name="manage_docs", state=None, agent_id="qa")

    cats = {r.get("category") for r in result}
    assert "scaffold_residue" not in cats


@pytest.mark.asyncio
async def test_quality_reminders_count_stale_index_for_path_registered_research_docs(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text("---\nstatus: complete\n---\nFinal architecture content.\n", encoding="utf-8")
    research_dir = Path(project["docs_dir"]) / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_doc = research_dir / "RESEARCH_FRONTMATTER.md"
    research_doc.write_text("# Research\nEvidence.\n", encoding="utf-8")
    project["docs"] = {
        "architecture": project["docs"]["architecture"],
        "research_frontmatter": str(research_doc),
        "progress_log": project["docs"]["progress_log"],
        "decisions": project["docs"]["decisions"],
    }

    reset_reminder_cooldowns(project_root=project["root"])
    with patch("scribe_mcp.reminders._resolve_reminder_storage", return_value=None):
        from scribe_mcp import reminders as reminders_module

        reminders_module._reminder_engine = None
        result = await get_reminders(project, tool_name="manage_docs", state=None, agent_id="qa")

    cats = {r.get("category") for r in result}
    assert "stale_research_index" in cats
    assert "scaffold_residue" not in cats


@pytest.mark.asyncio
async def test_quality_reminders_runtime_efficiency_budget_and_suppression(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    project["defaults"] = {
        "reminder": {
            "runtime_efficiency_budget_category": "runtime_budget_custom",
        }
    }

    from scribe_mcp import reminders as reminders_module
    from scribe_mcp.utils.reminder_engine import ReminderContext

    with patch("scribe_mcp.reminders._resolve_reminder_storage", return_value=None):
        reminders_module._reminder_engine = None
        engine = reminders_module._get_engine()
        context = ReminderContext(
            tool_name="manage_docs",
            project_name=project["name"],
            project_root=project["root"],
            agent_id="qa",
            session_id=None,
            total_entries=0,
            minutes_since_log=None,
            last_log_time=None,
            docs_status={},
            docs_changed=[],
            current_phase="Phase 2",
            session_age_minutes=None,
            variables={
                "readiness_summary": {
                    "current_phase": "Phase 2",
                    "managed_doc_quality": {"readiness_blocker_count": 0, "frontmatter_mismatch_count": 0, "stale_research_index_count": 0},
                    "log_friction": {"runtime_efficiency": {"budget_status": "over_budget"}},
                },
                "quality_reminder_cooldown_minutes": 60,
                "quality_reminder_categories": {"runtime_efficiency_budget": "runtime_budget_custom"},
                "quality_reminder_suppress_codes": [],
            },
            operation_status="failure",
        )
        with patch.object(engine, "_should_show_reminder_async", return_value=True):
            result = engine.to_dict_list(await reminders_module._quality_state_reminders(engine, context))

    cats = {r.get("category") for r in result}
    assert "runtime_budget_custom" in cats
    stale_messages = [r.get("message", "") for r in result if r.get("category") == "stale_research_index"]
    if stale_messages:
        assert "active lane" in stale_messages[0]

    project["defaults"] = {
        "reminder": {
            "runtime_efficiency_budget_category": "runtime_budget_custom",
            "suppress_warning_codes": ["RUNTIME_EFFICIENCY_BUDGET"],
        }
    }

    with patch("scribe_mcp.reminders._resolve_reminder_storage", return_value=None):
        reminders_module._reminder_engine = None
        engine = reminders_module._get_engine()
        suppressed_context = ReminderContext(
            tool_name="manage_docs",
            project_name=project["name"],
            project_root=project["root"],
            agent_id="qa",
            session_id=None,
            total_entries=0,
            minutes_since_log=None,
            last_log_time=None,
            docs_status={},
            docs_changed=[],
            current_phase="Phase 2",
            session_age_minutes=None,
            variables={
                "readiness_summary": {
                    "current_phase": "Phase 2",
                    "managed_doc_quality": {"readiness_blocker_count": 0, "frontmatter_mismatch_count": 0, "stale_research_index_count": 0},
                    "log_friction": {"runtime_efficiency": {"budget_status": "over_budget"}},
                },
                "quality_reminder_cooldown_minutes": 60,
                "quality_reminder_categories": {"runtime_efficiency_budget": "runtime_budget_custom"},
                "quality_reminder_suppress_codes": ["RUNTIME_EFFICIENCY_BUDGET"],
            },
            operation_status="failure",
        )
        with patch.object(engine, "_should_show_reminder_async", return_value=True):
            suppressed = engine.to_dict_list(await reminders_module._quality_state_reminders(engine, suppressed_context))

    suppressed_cats = {r.get("category") for r in suppressed}
    assert "runtime_budget_custom" not in suppressed_cats


@pytest.mark.asyncio
async def test_quality_reminders_emit_release_changelog_coverage_signal(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)

    from scribe_mcp import reminders as reminders_module
    from scribe_mcp.utils.reminder_engine import ReminderContext

    with patch("scribe_mcp.reminders._resolve_reminder_storage", return_value=None):
        reminders_module._reminder_engine = None
        engine = reminders_module._get_engine()
        context = ReminderContext(
            tool_name="manage_docs",
            project_name=project["name"],
            project_root=project["root"],
            agent_id="qa",
            session_id=None,
            total_entries=0,
            minutes_since_log=None,
            last_log_time=None,
            docs_status={},
            docs_changed=[],
            current_phase="Phase 2",
            session_age_minutes=None,
            variables={
                "readiness_summary": {
                    "current_phase": "Phase 2",
                    "managed_doc_quality": {
                        "readiness_blocker_count": 1,
                        "frontmatter_mismatch_count": 0,
                        "stale_research_index_count": 0,
                        "readiness_blocker_counts_by_code": {"SCF_CHANGELOG_CURRENT_VERSION_MISSING": 1},
                    },
                    "log_friction": {},
                },
                "quality_reminder_cooldown_minutes": 60,
                "quality_reminder_categories": {"release_changelog_coverage": "release_changelog_coverage"},
                "quality_reminder_suppress_codes": [],
            },
            operation_status="failure",
        )
        with patch.object(engine, "_should_show_reminder_async", return_value=True):
            result = engine.to_dict_list(await reminders_module._quality_state_reminders(engine, context))

    release = [r for r in result if r.get("category") == "release_changelog_coverage"]
    assert release
    assert "CHANGELOG coverage" in str(release[0].get("message", ""))
