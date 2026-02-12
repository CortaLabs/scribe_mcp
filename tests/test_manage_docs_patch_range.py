from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.reminders import reset_reminder_cooldowns
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.utils.frontmatter import parse_frontmatter


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _patch_text(old_line: str, new_line: str) -> str:
    return "\n".join(
        [
            "--- before",
            "+++ after",
            "@@ -1,3 +1,3 @@",
            f"-{old_line}",
            f"+{new_line}",
            " beta",
            " gamma",
        ]
    )


def _patch_text_with_header(old_line: str, new_line: str, header: str) -> str:
    return "\n".join(
        [
            "--- before",
            "+++ after",
            header,
            f"-{old_line}",
            f"+{new_line}",
            " beta",
            " gamma",
        ]
    )


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "patch_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "alpha\nbeta\ngamma\n",
        encoding="utf-8",
    )
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Patch Project",
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
async def test_apply_patch_success_and_hunks(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = architecture_path.read_text(encoding="utf-8")
    patch_text = _patch_text("alpha", "alpha updated")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    assert change.extra.get("hunks_applied", 0) > 0
    updated = architecture_path.read_text(encoding="utf-8")
    assert updated != original
    assert "alpha updated" in updated


@pytest.mark.asyncio
async def test_apply_patch_stale_source_and_precondition(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    patch_text = _patch_text("alpha", "alpha updated")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash="deadbeef",
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "PATCH_STALE_SOURCE" in (change.error_message or "")
    assert change.extra.get("precondition_failed") == "SOURCE_HASH_MISMATCH"


@pytest.mark.asyncio
async def test_replace_text_literal_scoped_section(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "# Doc\n"
        "<!-- ID: problem_statement -->\n"
        "alpha beta\n"
        "<!-- ID: other -->\n"
        "alpha\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_text",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={
            "find": "alpha",
            "replace": "alpha2",
            "replace_all": False,
            "match_mode": "literal",
            "scope": "section:problem_statement",
        },
        dry_run=False,
    )

    assert change.success
    updated = architecture_path.read_text(encoding="utf-8")
    assert "alpha2 beta" in updated
    assert updated.count("alpha2") == 1
    assert updated.rstrip().endswith("alpha")


@pytest.mark.asyncio
async def test_replace_text_literal_scoped_inline_anchor_targets_anchor_line(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    checklist_path = Path(project["docs"]["checklist"])
    checklist_path.write_text(
        "# Checklist\n"
        "- [ ] Ship docs <!-- ID: p4_documents -->\n"
        "- [ ] Ship API <!-- ID: p4_api -->\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="checklist",
        action="replace_text",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={
            "find": "Ship docs",
            "replace": "Ship docs (done)",
            "replace_all": False,
            "match_mode": "literal",
            "scope": "section:p4_documents",
        },
        dry_run=False,
    )

    assert change.success
    updated = checklist_path.read_text(encoding="utf-8")
    assert "Ship docs (done) <!-- ID: p4_documents -->" in updated
    assert "Ship API <!-- ID: p4_api -->" in updated


@pytest.mark.asyncio
async def test_replace_text_scoped_block_ignores_inline_anchor_markers(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    checklist_path = Path(project["docs"]["checklist"])
    checklist_path.write_text(
        "# Checklist\n"
        "<!-- ID: phase_0 -->\n"
        "- [ ] Ship docs <!-- ID: p4_documents -->\n"
        "- [ ] Ship API\n"
        "<!-- ID: phase_1 -->\n"
        "- [ ] Later\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="checklist",
        action="replace_text",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={
            "find": "Ship API",
            "replace": "Ship API (done)",
            "replace_all": False,
            "match_mode": "literal",
            "scope": "section:phase_0",
        },
        dry_run=False,
    )

    assert change.success
    updated = checklist_path.read_text(encoding="utf-8")
    assert "Ship API (done)" in updated
    assert "- [ ] Later" in updated


@pytest.mark.asyncio
async def test_apply_patch_patch_mode_conflict(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        patch_mode="structured",
        edit={
            "type": "replace_range",
            "start_line": 1,
            "end_line": 1,
            "content": "alpha updated\n",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={"patch_mode": "unified"},
        dry_run=False,
    )

    assert not change.success
    assert "PATCH_MODE_CONFLICT" in (change.error_message or "")


@pytest.mark.asyncio
async def test_apply_patch_invalid_diff_fails(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = architecture_path.read_text(encoding="utf-8")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch="not-a-diff",
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "PATCH_INVALID_FORMAT" in (change.error_message or "")
    assert architecture_path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_apply_patch_dry_run_preview(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = architecture_path.read_text(encoding="utf-8")
    patch_text = _patch_text("alpha", "alpha updated")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert change.success
    assert "alpha updated" in change.content_written
    assert change.extra.get("affected_ranges")
    assert change.extra.get("preview_window")
    assert change.extra.get("preview_windows")
    assert architecture_path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_apply_patch_rebase_when_header_out_of_date(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    patch_text = _patch_text_with_header("alpha", "alpha updated", "@@ -9,3 +9,3 @@")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    assert change.extra.get("rebase_applied") is True
    assert "alpha updated" in architecture_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_apply_patch_rebase_expands_missing_context_line(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
    patch_text = "\n".join(
        [
            "--- before",
            "+++ after",
            "@@ -1,4 +1,4 @@",
            "-alpha",
            "+alpha updated",
            " beta",
            " delta",
        ]
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    assert change.extra.get("rebase_applied") is True
    hunks = change.extra.get("rebase_info", {}).get("hunks", [])
    assert hunks and hunks[0].get("context_expanded") is True
    assert "alpha updated" in architecture_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_apply_patch_context_mismatch_diagnostics(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    patch_text = _patch_text("missing", "alpha updated")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    diagnostics = change.extra.get("patch_diagnostics", {})
    assert diagnostics.get("hint")


@pytest.mark.asyncio
async def test_patch_source_hash_passes_when_correct(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = architecture_path.read_text(encoding="utf-8")
    patch_text = _patch_text("alpha", "alpha updated")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=_hash_text(original),
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success


@pytest.mark.asyncio
async def test_replace_range_boundaries_and_invalids(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])

    first_line = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="FIRST\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=1,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert first_line.success
    parsed = parse_frontmatter(architecture_path.read_text(encoding="utf-8"))
    assert parsed.body.startswith("FIRST\n")

    last_line = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="LAST\n",
        patch=None,
        patch_source_hash=None,
        start_line=3,
        end_line=3,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert last_line.success
    parsed = parse_frontmatter(architecture_path.read_text(encoding="utf-8"))
    assert parsed.body.rstrip().endswith("LAST")

    multi_line = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="MID1\nMID2\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=2,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert multi_line.success
    assert "MID1" in architecture_path.read_text(encoding="utf-8")

    invalid_range = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="BAD\n",
        patch=None,
        patch_source_hash=None,
        start_line=5,
        end_line=1,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert not invalid_range.success
    assert "Invalid range" in (invalid_range.error_message or "")

    out_of_bounds = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="BAD\n",
        patch=None,
        patch_source_hash=None,
        start_line=99,
        end_line=100,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert not out_of_bounds.success
    assert "out of range" in (out_of_bounds.error_message or "")


@pytest.mark.asyncio
async def test_replace_range_dry_run_parity(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = architecture_path.read_text(encoding="utf-8")

    dry_run = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="DRY\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=1,
        template=None,
        metadata={},
        dry_run=True,
    )
    assert dry_run.success
    assert "DRY" in dry_run.content_written
    assert architecture_path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_replace_range_honors_explicit_range_even_with_header_content(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original_body = """## A) Config Loading Audit
alpha detail

## B) manage_docs Precision Audit
old section content

## C) manage_docs Secondary
extra detail
"""
    architecture_path.write_text(original_body, encoding="utf-8")

    replacement = """## B) manage_docs Precision Audit
replaced line 1
replaced line 2
"""

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content=replacement,
        patch=None,
        patch_source_hash=None,
        start_line=99,
        end_line=100,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "start_line out of range" in (change.error_message or "")
    assert architecture_path.read_text(encoding="utf-8") == original_body


@pytest.mark.asyncio
async def test_healing_before_reminders(tmp_path: Path) -> None:
    """Ensure healed scaffold/action values drive reminder selection."""
    project = await _setup_project(tmp_path)
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend
    server_module.state_manager = state_manager
    server_module.storage_backend = None

    try:
        reset_reminder_cooldowns(project_root=project["root"])
        result = await manage_docs(
            action=" replace_section ",
            doc="architecture",
            section="problem_statement",
            content="Scaffold",
            metadata={"scaffold": "TRUE "},
            dry_run=True,
        )

        messages = [r["message"] for r in result.get("reminders", [])]
        assert not any("prefer apply_patch" in msg.lower() for msg in messages)
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend
