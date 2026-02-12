from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.utils.frontmatter import parse_frontmatter


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "structured_repo"
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
        "name": "Structured Project",
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
async def test_apply_structured_edit_replace_range(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_range",
            "start_line": 2,
            "end_line": 2,
            "content": "beta updated\n",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    assert change.extra.get("hunks_applied", 0) >= 0
    updated = architecture_path.read_text(encoding="utf-8")
    assert "beta updated" in updated


@pytest.mark.asyncio
async def test_structured_replace_range_with_header_content_honors_line_range(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "## Section A\nline a1\nline a2\n\n## Section B\nline b1\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_range",
            "start_line": 2,
            "end_line": 2,
            "content": "## Section B\n",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert change.success
    parsed = parse_frontmatter(change.content_written)
    body = parsed.body
    assert "line a1" not in body
    assert "line a2" in body
    assert "line b1" in body


@pytest.mark.asyncio
async def test_apply_structured_edit_replace_block(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "## Title\n**Solution Summary:** Old summary\nMore detail\n\nNext section\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_block",
            "anchor": "**Solution Summary:**",
            "new_content": "**Solution Summary:** New summary",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    updated = architecture_path.read_text(encoding="utf-8")
    assert "New summary" in updated
    assert "Old summary" not in updated


@pytest.mark.asyncio
async def test_replace_block_ignores_code_fence(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "## Title\n```\n**Solution Summary:** Old summary\n```\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_block",
            "anchor": "**Solution Summary:**",
            "new_content": "**Solution Summary:** New summary",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "STRUCTURED_EDIT_ANCHOR_NOT_FOUND" in (change.error_message or "")


@pytest.mark.asyncio
async def test_replace_block_ambiguous_anchor(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    progress_log_path = Path(project["docs"]["progress_log"])
    architecture_path.write_text(
        "## Title\n**Solution Summary:** One\n\n**Solution Summary:** Two\n",
        encoding="utf-8",
    )
    progress_log_path.write_text("Progress\n", encoding="utf-8")
    original_doc = architecture_path.read_text(encoding="utf-8")
    original_log = progress_log_path.read_text(encoding="utf-8")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_block",
            "anchor": "**Solution Summary:**",
            "new_content": "**Solution Summary:** New summary",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert not change.success
    error_message = change.error_message or ""
    assert "STRUCTURED_EDIT_ANCHOR_AMBIGUOUS" in error_message
    assert "matches: [line 2, line 4]" in error_message
    assert change.diff_preview == ""
    assert architecture_path.read_text(encoding="utf-8") == original_doc
    assert progress_log_path.read_text(encoding="utf-8") == original_log


@pytest.mark.asyncio
async def test_normalize_headers_idempotent_and_skip_fences(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "# Title\n## Subtitle\n```\n## 3. Code Block\n```\n### Third\n",
        encoding="utf-8",
    )

    first = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers",
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
    parsed_first = parse_frontmatter(architecture_path.read_text(encoding="utf-8"))
    assert "# 1 Title" in parsed_first.body
    assert "## 1.1 Subtitle" in parsed_first.body
    assert "### 1.1.1 Third" in parsed_first.body
    assert "## 3. Code Block" in parsed_first.body

    second = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers",
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
async def test_normalize_headers_guardrail_rejects_non_atx_promotions(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = (
        "- Keep this section updated before each implementation phase.\n"
        "---\n"
        "No optimization patches until functional parity is complete.\n"
        "---\n"
        "- [ ] Stakeholder sign-off recorded in PROGRESS_LOG.md\n"
        "---\n"
        "# Valid Header\n"
    )
    architecture_path.write_text(original, encoding="utf-8")

    result = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers",
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

    assert not result.success
    assert "NORMALIZE_HEADERS_GUARDRAIL" in (result.error_message or "")
    assert result.extra.get("guardrail") == "non_atx_promotion"
    violations = result.extra.get("violations") or []
    assert violations
    assert architecture_path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_normalize_headers_invalid_doc_fails(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    result = await apply_doc_change(
        project,
        doc="missing_doc_key",
        action="normalize_headers",
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

    assert not result.success
    error_message = result.error_message or ""
    assert "DOC_NOT_FOUND" in error_message
