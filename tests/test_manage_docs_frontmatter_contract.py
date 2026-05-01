from __future__ import annotations

from pathlib import Path
import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.utils.frontmatter import parse_frontmatter


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "contract_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text("# Title\n\nBody\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")
    return {
        "name": "Frontmatter Contract Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
    }


@pytest.mark.asyncio
async def test_response_exposes_compact_frontmatter_summaries_by_default(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
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
        metadata={"agent_id": "CoderAgent-Phase1", "tags": "priority"},
        dry_run=False,
    )

    assert change.success
    assert "frontmatter_updates" in change.extra
    assert "frontmatter_ignored_keys" in change.extra
    assert "attribution" in change.extra
    assert "metadata_hints" in change.extra
    assert "frontmatter" not in change.extra


@pytest.mark.asyncio
async def test_include_frontmatter_extra_exposes_merged_frontmatter(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
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
        metadata={"include_frontmatter_extra": True, "agent_id": "CoderAgent-Phase1"},
        dry_run=False,
    )

    assert change.success
    assert isinstance(change.extra.get("frontmatter"), dict)
    assert change.extra.get("attribution", {}).get("actor_id") == "CoderAgent-Phase1"


@pytest.mark.asyncio
async def test_edit_ignores_raw_edit_trace_and_created_by_override(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text(
        "\n".join(
            [
                "---",
                "id: arch-doc",
                'title: "Title"',
                "doc_type: architecture",
                "created_by: Corta Labs",
                "maintained_by: Corta Labs",
                "---",
                "# Title",
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
        content="# Title\n\nBody updated\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={
            "agent_id": "CoderAgent-Phase1",
            "created_by": "OverrideIgnored",
            "frontmatter": {"edit_trace": {"tool": "malicious"}},
        },
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("created_by") == "Corta Labs"
    assert parsed.frontmatter_data.get("maintained_by") == "CoderAgent-Phase1"

    ignored = change.extra.get("frontmatter_ignored_keys") or []
    fields = {item.get("field") for item in ignored if isinstance(item, dict)}
    assert "metadata.created_by" in fields
    assert "metadata.frontmatter.edit_trace" in fields

    hint_codes = {item.get("code") for item in (change.extra.get("metadata_hints") or []) if isinstance(item, dict)}
    assert "created_by_edit_override_ignored" in hint_codes
    assert "edit_trace_ignored" in hint_codes
    assert "legacy_created_by_placeholder_preserved" in hint_codes


@pytest.mark.asyncio
async def test_explicit_metadata_actor_id_is_not_overridden_by_internal_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await _setup_project(tmp_path)

    class _InternalIdentity:
        async def get_or_create_agent_id(self) -> str:
            return "agent-20260417-deadbeef"

    monkeypatch.setattr(
        "scribe_mcp.server.get_agent_identity",
        lambda: _InternalIdentity(),
    )

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
        metadata={"agent_id": "ReviewAgent"},
        dry_run=False,
    )

    assert change.success
    assert change.extra.get("attribution", {}).get("actor_id") == "ReviewAgent"

    parsed = parse_frontmatter(Path(project["docs"]["architecture"]).read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("maintained_by") == "ReviewAgent"


@pytest.mark.asyncio
async def test_frontmatter_update_changes_metadata_without_dummy_body_content(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    original_body = path.read_text(encoding="utf-8")

    dry_change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        metadata={"agent_id": "CoderAgent-Phase1", "status": "in_progress"},
        template=None,
        dry_run=True,
    )
    assert dry_change.success
    parsed_source = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed_source.body == original_body
    assert dry_change.extra.get("frontmatter_updates", {}).get("updated_keys")

    apply_change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        metadata={"agent_id": "CoderAgent-Phase1", "frontmatter": {"summary": "Body preserved"}},
        template=None,
        dry_run=False,
    )
    assert apply_change.success
    parsed_apply = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed_apply.body == original_body
    assert parsed_apply.frontmatter_data.get("summary") == "Body preserved"
