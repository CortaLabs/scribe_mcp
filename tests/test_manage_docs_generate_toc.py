from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.utils.frontmatter import parse_frontmatter


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "toc_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "# Title\n## Section A\n### Subsection\n```\n## Code Block\n```\n## Section A\n",
        encoding="utf-8",
    )
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "TOC Project",
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
async def test_generate_toc_inserts_and_idempotent(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])

    first = await apply_doc_change(
        project,
        doc="architecture",
        action="generate_toc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert first.success

    parsed = parse_frontmatter(architecture_path.read_text(encoding="utf-8"))
    body = parsed.body
    assert "<!-- TOC:start -->" in body
    assert "<!-- TOC:end -->" in body
    assert "- [Title](#title)" in body
    assert "  - [Section A](#section-a)" in body
    assert "    - [Subsection](#subsection)" in body
    assert "  - [Section A](#section-a-1)" in body
    assert "Code Block" not in body.split("<!-- TOC:end -->", 1)[0]

    second = await apply_doc_change(
        project,
        doc="architecture",
        action="generate_toc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )
    assert second.success
    assert second.diff_preview == ""


@pytest.mark.asyncio
async def test_generate_toc_anchor_parity(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "##Title\nHello?\n====\nHello!\n====\nRelease 🚀\n----\nRelease\n----\nCafé\n----\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="generate_toc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert change.success

    body = parse_frontmatter(architecture_path.read_text(encoding="utf-8")).body
    assert "- [Title](#title)" in body
    assert "- [Hello?](#hello)" in body
    assert "- [Hello!](#hello-1)" in body
    assert "- [Release 🚀](#release)" in body
    assert "- [Release](#release-1)" in body
    assert "- [Café](#cafe)" in body


@pytest.mark.asyncio
async def test_generate_toc_invalid_doc_fails(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    change = await apply_doc_change(
        project,
        doc="missing_doc_key",
        action="generate_toc",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert not change.success
    error_message = change.error_message or ""
    assert "DOC_NOT_FOUND" in error_message
