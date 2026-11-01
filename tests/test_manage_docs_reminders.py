from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scribe_mcp.reminders import reset_reminder_cooldowns
from scribe_mcp.reminders import get_reminders
from scribe_mcp.state import StateManager
from test_manage_docs_create_doc import _call_manage_docs, _isolated_server


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
async def test_manage_docs_returns_structured_error_when_runtime_raises(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async def _raise_runtime_error(**kwargs):
        raise RuntimeError("boom")

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
        with patch(
            "scribe_mcp.tools.manage_docs.runtime_shared.handle_manage_docs_request",
            _raise_runtime_error,
        ):
            result = await _call_manage_docs(client, test_agent, action="list_sections", doc="architecture")

    assert result["ok"] is False
    assert result["error"] == "manage_docs_runtime_error"
    assert result["error_code"] == "MANAGE_DOCS_RUNTIME_EXCEPTION"
    assert result["exception_type"] == "RuntimeError"
    assert result["action"] == "list_sections"
    assert "supported_actions" in result


@pytest.mark.asyncio
async def test_manage_docs_reminder_scaffold_and_non_scaffold(tmp_path: Path, test_agent: str) -> None:
    """Ensure replace_section reminders distinguish scaffold vs non-scaffold usage."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
        reset_reminder_cooldowns(project_root=project["root"])
        scaffold_result = await _call_manage_docs(client, test_agent,
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="Scaffold",
            metadata={"scaffold": "TRUE "},
            dry_run=True,
        )

        assert scaffold_result["ok"] is True, scaffold_result
        scaffold_messages = [r["message"] for r in scaffold_result.get("reminders", [])]
        assert not any("prefer apply_patch" in msg.lower() for msg in scaffold_messages)

        reset_reminder_cooldowns(project_root=project["root"])
        non_scaffold_result = await _call_manage_docs(client, test_agent,
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="Edit",
            metadata={"scaffold": False},
            dry_run=True,
        )

        assert non_scaffold_result["ok"] is True, non_scaffold_result
        non_scaffold_messages = [r["message"] for r in non_scaffold_result.get("reminders", [])]
        assert all(isinstance(msg, str) for msg in non_scaffold_messages)
        if any("apply_patch" in msg.lower() or "replace_section" in msg.lower() for msg in non_scaffold_messages):
            assert any("apply_patch" in msg.lower() for msg in non_scaffold_messages)


@pytest.mark.asyncio
async def test_manage_docs_successful_edit_has_no_vector_runtime_reminder(tmp_path: Path, test_agent: str) -> None:
    """Successful edit responses must not advertise removed built-in vector flows."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
        reset_reminder_cooldowns(project_root=project["root"])
        result = await _call_manage_docs(client, test_agent,
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
async def test_manage_docs_reminder_precision_tools_no_nag(tmp_path: Path, test_agent: str) -> None:
    """Ensure apply_patch/replace_range do not trigger replace_section reminders."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
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

        patch_result = await _call_manage_docs(client, test_agent,
            action="apply_patch",
            doc="architecture",
            patch=patch_text,
            patch_mode="unified",
            dry_run=True,
        )

        assert patch_result["ok"] is True, patch_result
        patch_messages = [r["message"] for r in patch_result.get("reminders", [])]
        assert not any("For edits, prefer manage_docs apply_patch" in msg for msg in patch_messages)
        assert not any("Scaffolding detected" in msg for msg in patch_messages)

        structured_result = await _call_manage_docs(client, test_agent,
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

        assert structured_result["ok"] is True, structured_result
        structured_messages = [r["message"] for r in structured_result.get("reminders", [])]
        assert not any("For edits, prefer manage_docs apply_patch" in msg for msg in structured_messages)
        assert not any("Scaffolding detected" in msg for msg in structured_messages)

        range_result = await _call_manage_docs(client, test_agent,
            action="replace_range",
            doc="architecture",
            start_line=1,
            end_line=1,
            content="# Architecture Updated\n",
            dry_run=True,
        )

        assert range_result["ok"] is True, range_result
        range_messages = [r["message"] for r in range_result.get("reminders", [])]
        assert not any("For edits, prefer manage_docs apply_patch" in msg for msg in range_messages)
        assert not any("Scaffolding detected" in msg for msg in range_messages)


@pytest.mark.asyncio
async def test_manage_docs_create_returns_next_step_guidance(tmp_path: Path, test_agent: str) -> None:
    """create responses should include explicit scaffold follow-up guidance."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
        result = await _call_manage_docs(client, test_agent,
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
async def test_readiness_claim_blocked_but_edit_persists(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
        write_result = await _call_manage_docs(client, test_agent,
            action="replace_section",
            doc="architecture",
            section="problem_statement",
            content="[fill this section]\n",
            metadata={"scaffold": False},
            dry_run=False,
        )
        assert write_result["ok"] is True

        result = await _call_manage_docs(client, test_agent,
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
async def test_replace_section_with_readiness_claim_blocks_whole_mutation(tmp_path: Path, test_agent: str) -> None:
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original = Path(project["docs"]["architecture"]).read_text(encoding="utf-8")
    async with _isolated_server(
        state_manager, project_root=project["root"], project_name=project["name"], agent=test_agent,
    ) as client:
        result = await _call_manage_docs(client, test_agent,
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
