from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.utils.frontmatter import build_frontmatter


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "crosslinks_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    target_path = docs_dir / "TARGET.md"
    target_body = "# Target Doc\n## Section A\n"
    target_path.write_text(target_body, encoding="utf-8")

    frontmatter = build_frontmatter(
        {
            "id": "crosslinks-test",
            "title": "Crosslinks Test",
            "doc_type": "note",
            "related_docs": ["TARGET.md#section-a", "MISSING.md"],
        }
    )
    source_path = docs_dir / "SOURCE.md"
    source_path.write_text(frontmatter + "# Source Doc\n", encoding="utf-8")

    return {
        "name": "Crosslinks Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            "source": str(source_path),
        },
        "defaults": {"agent": "QA Bot"},
    }


@pytest.mark.asyncio
async def test_validate_crosslinks_diagnostics(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)

    change = await apply_doc_change(
        project,
        doc="source",
        action="validate_crosslinks",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"check_anchors": True},
        dry_run=False,
    )

    assert change.success
    diagnostics = change.extra.get("crosslinks", [])
    assert len(diagnostics) == 2
    assert diagnostics[0]["exists"] is True
    assert diagnostics[0]["anchor_found"] is True
    assert diagnostics[1]["exists"] is False
