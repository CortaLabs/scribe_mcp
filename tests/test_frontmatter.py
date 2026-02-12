from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.utils.frontmatter import parse_frontmatter


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "frontmatter_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "# Title\n\nBody\n",
        encoding="utf-8",
    )
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Frontmatter Project",
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
async def test_frontmatter_created_and_updated(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="# Title\n\nBody updated\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    text = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    assert parsed.has_frontmatter
    assert parsed.frontmatter_data.get("title") == "Title"
    assert parsed.frontmatter_data.get("doc_type") == "architecture"
    last_updated = str(parsed.frontmatter_data.get("last_updated") or "")
    assert last_updated
    assert last_updated.endswith("UTC")


@pytest.mark.asyncio
async def test_status_update_does_not_create_frontmatter_when_missing(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["checklist"])
    path.write_text(
        "# Checklist\n\n<!-- ID: phase_0 -->\n- [ ] Ship feature\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="checklist",
        action="status_update",
        section="phase_0",
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"status": "done", "proof": "commit123"},
        dry_run=False,
    )

    assert change.success
    text = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    assert not parsed.has_frontmatter
    assert text.startswith("# Checklist")
    assert "- [x] Ship feature | proof=commit123" in text


@pytest.mark.asyncio
async def test_frontmatter_preserves_custom_fields(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text(
        "\n".join(
            [
                "---",
                "id: custom-id",
                "title: \"Custom Title\"",
                "doc_type: architecture",
                "custom_field: 123",
                "---",
                "# Custom Title",
                "",
                "Body",
                "",
            ]
        ),
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="# Custom Title\n\nBody updated\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("id") == "custom-id"
    assert parsed.frontmatter_data.get("custom_field") == 123
    assert parsed.frontmatter_data.get("last_updated")


@pytest.mark.asyncio
async def test_frontmatter_explicit_updates(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="# Title\n\nBody updated\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={"frontmatter": {"status": "authoritative"}},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("status") == "authoritative"


@pytest.mark.asyncio
async def test_replace_range_content_frontmatter_updates_document_frontmatter(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content=(
            "---\n"
            "title: \"Retitled\"\n"
            "status: active\n"
            "---\n"
            "# Retitled\n\n"
            "Body updated from payload\n"
        ),
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={"frontmatter": {"status": "override"}},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("title") == "Retitled"
    assert parsed.frontmatter_data.get("status") == "override"
    assert parsed.body.startswith("# Retitled")
    assert "Body updated from payload" in parsed.body


@pytest.mark.asyncio
async def test_frontmatter_auto_updates_related_docs_from_links(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="# Title\n\nSee [Phase](PHASE_PLAN.md) and [Checklist](CHECKLIST.md).\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("related_docs") == ["phase_plan", "checklist"]


@pytest.mark.asyncio
async def test_replace_range_uses_body_relative_lines(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text(
        "\n".join(
            [
                "---",
                "id: body-relative-test",
                "title: \"Body Relative\"",
                "doc_type: architecture",
                "---",
                "# Body Relative",
                "",
                "Line A",
                "Line B",
                "",
            ]
        ),
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="# Body Relative\n\nLine A Updated\nLine B\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=4,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("id") == "body-relative-test"
    assert "Line A Updated" in parsed.body
