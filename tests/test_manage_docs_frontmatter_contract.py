from __future__ import annotations

from pathlib import Path
import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.doc_management.special_create import _ensure_export_policy_frontmatter
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


def test_special_create_persists_complete_non_exportable_policy_by_default(
    tmp_path: Path,
) -> None:
    project = {
        "name": "Frontmatter Contract Project",
        "root": str(tmp_path),
    }

    rendered = _ensure_export_policy_frontmatter(
        "# Narrative\n", project, {}, "agent:forge"
    )
    frontmatter = parse_frontmatter(rendered).frontmatter_data

    assert frontmatter["visibility"] == "internal"
    assert frontmatter["owner_principal_id"] == "agent:forge"
    assert frontmatter["council_id"] == ""
    assert frontmatter["project_id"] == "Frontmatter Contract Project"
    assert frontmatter["required_grants"] == []
    assert frontmatter["revoked_at"] is None
    assert len(frontmatter["policy_digest"]) == 64


@pytest.mark.asyncio
async def test_response_exposes_compact_frontmatter_summaries_by_default(
    tmp_path: Path,
) -> None:
    project = await _setup_project(tmp_path)
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
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
async def test_include_frontmatter_extra_exposes_merged_frontmatter(
    tmp_path: Path,
) -> None:
    project = await _setup_project(tmp_path)
    metadata = {"include_frontmatter_extra": True, "agent_id": "CoderAgent-Phase1"}
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata=metadata,
        dry_run=False,
    )

    assert change.success
    assert metadata == {
        "include_frontmatter_extra": True,
        "agent_id": "CoderAgent-Phase1",
    }
    assert isinstance(change.extra.get("frontmatter"), dict)
    assert change.extra.get("attribution", {}).get("actor_id") == "CoderAgent-Phase1"


@pytest.mark.asyncio
async def test_edit_ignores_raw_edit_trace_and_created_by_override(
    tmp_path: Path,
) -> None:
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
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
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

    hint_codes = {
        item.get("code")
        for item in (change.extra.get("metadata_hints") or [])
        if isinstance(item, dict)
    }
    assert "created_by_edit_override_ignored" in hint_codes
    assert "edit_trace_ignored" in hint_codes
    assert "legacy_created_by_placeholder_preserved" in hint_codes


@pytest.mark.asyncio
async def test_edit_ignores_maintained_by_overrides_from_metadata_and_frontmatter(
    tmp_path: Path,
) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text(
        "\n".join(
            [
                "---",
                "id: arch-doc",
                'title: "Title"',
                "doc_type: architecture",
                "created_by: LegacyCreator",
                "maintained_by: LegacyMaintainer",
                "---",
                "# Title",
                "",
                "Body",
                "",
            ]
        ),
        encoding="utf-8",
    )

    metadata = {
        "agent_id": "CoderAgent-Phase1",
        "maintained_by": "OverrideIgnored",
        "frontmatter": {"maintained_by": "FrontmatterOverrideIgnored"},
    }
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata=metadata,
        dry_run=False,
    )

    assert change.success
    assert metadata == {
        "agent_id": "CoderAgent-Phase1",
        "maintained_by": "OverrideIgnored",
        "frontmatter": {"maintained_by": "FrontmatterOverrideIgnored"},
    }
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("maintained_by") == "CoderAgent-Phase1"

    ignored = change.extra.get("frontmatter_ignored_keys") or []
    fields = {item.get("field") for item in ignored if isinstance(item, dict)}
    assert "metadata.maintained_by" in fields
    assert "metadata.frontmatter.maintained_by" in fields

    hint_codes = {
        item.get("code")
        for item in (change.extra.get("metadata_hints") or [])
        if isinstance(item, dict)
    }
    assert "maintained_by_ignored" in hint_codes


@pytest.mark.asyncio
async def test_explicit_workflow_actor_precedes_ambient_runtime_identity(
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

    metadata = {"agent_id": "ReviewAgent"}
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata=metadata,
        dry_run=False,
    )

    assert change.success
    assert metadata == {"agent_id": "ReviewAgent"}
    assert change.extra.get("attribution", {}).get("actor_id") == "ReviewAgent"

    parsed = parse_frontmatter(
        Path(project["docs"]["architecture"]).read_text(encoding="utf-8")
    )
    assert parsed.frontmatter_data.get("maintained_by") == "ReviewAgent"


@pytest.mark.asyncio
async def test_runtime_actor_identity_is_fallback_without_explicit_workflow_actor(
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

    metadata: dict[str, object] = {}
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata=metadata,
        dry_run=False,
    )

    assert change.success
    assert metadata == {}
    assert (
        change.extra.get("attribution", {}).get("actor_id")
        == "agent-20260417-deadbeef"
    )


@pytest.mark.asyncio
async def test_replace_range_does_not_create_frontmatter_without_explicit_opt_in(
    tmp_path: Path,
) -> None:
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text("# No Frontmatter\n\nBody\n", encoding="utf-8")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="# No Frontmatter\n\nBody updated\n",
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
    assert parsed.has_frontmatter is False


@pytest.mark.asyncio
async def test_body_edit_preserves_explicit_title_when_heading_differs(
    tmp_path: Path,
) -> None:
    """Regression for BUG-2026-06-17-0002 (case a).

    A doc whose body's first heading differs from its explicit frontmatter
    ``title`` must NOT have that title re-inferred/clobbered on a body edit.
    """
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text(
        "\n".join(
            [
                "---",
                "id: arch-doc",
                "title: RAILS MAP CURRENT STATE",
                "doc_type: architecture",
                "---",
                "## Purpose",
                "",
                "Original body",
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
        content="## Purpose\n\nBody updated\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={"agent_id": "CoderAgent-Phase1"},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    # Title must survive the body edit even though the first heading is "Purpose".
    assert parsed.frontmatter_data.get("title") == "RAILS MAP CURRENT STATE"
    assert "Body updated" in parsed.body


@pytest.mark.asyncio
async def test_frontmatter_update_sets_title_authoritatively_and_it_persists(
    tmp_path: Path,
) -> None:
    """Regression for BUG-2026-06-17-0002 (case b).

    ``frontmatter_update`` with ``metadata.frontmatter.title`` is the governed
    path to set/repair a title, and the new title survives a later body edit.
    """
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    path.write_text(
        "\n".join(
            [
                "---",
                "id: arch-doc",
                "title: OLD TITLE",
                "doc_type: architecture",
                "---",
                "## Purpose",
                "",
                "Original body",
                "",
            ]
        ),
        encoding="utf-8",
    )

    set_change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={
            "agent_id": "CoderAgent-Phase1",
            "frontmatter": {"title": "NEW TITLE"},
        },
        dry_run=False,
    )
    assert set_change.success
    parsed_set = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed_set.frontmatter_data.get("title") == "NEW TITLE"

    # A subsequent body edit with no title in metadata must keep the new title.
    body_change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="## Purpose\n\nBody updated again\n",
        patch=None,
        patch_source_hash=None,
        start_line=1,
        end_line=3,
        template=None,
        metadata={"agent_id": "CoderAgent-Phase1"},
        dry_run=False,
    )
    assert body_change.success
    parsed_after = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed_after.frontmatter_data.get("title") == "NEW TITLE"


@pytest.mark.asyncio
async def test_doc_without_explicit_title_still_infers_from_heading(
    tmp_path: Path,
) -> None:
    """Regression for BUG-2026-06-17-0002 (case c — back-compat).

    A doc with NO explicit frontmatter title still gets the inferred title from
    the first heading, preserving the original create-time convenience.
    """
    project = await _setup_project(tmp_path)
    path = Path(project["docs"]["architecture"])
    # No frontmatter title at all — only a heading.
    path.write_text("## Purpose\n\nOriginal body\n", encoding="utf-8")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="frontmatter_update",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"agent_id": "CoderAgent-Phase1"},
        dry_run=False,
    )

    assert change.success
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed.frontmatter_data.get("title") == "Purpose"


@pytest.mark.asyncio
async def test_frontmatter_update_changes_metadata_without_dummy_body_content(
    tmp_path: Path,
) -> None:
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
        metadata={
            "agent_id": "CoderAgent-Phase1",
            "frontmatter": {"summary": "Body preserved"},
        },
        template=None,
        dry_run=False,
    )
    assert apply_change.success
    parsed_apply = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert parsed_apply.body == original_body
    assert parsed_apply.frontmatter_data.get("summary") == "Body preserved"
