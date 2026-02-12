from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.reminders import reset_reminder_cooldowns
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


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
