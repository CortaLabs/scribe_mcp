from __future__ import annotations

import asyncio
from pathlib import Path

from scribe_mcp.doc_management.actions.query import _handle_preview_reconciliation


class _QueryHelper:
    @staticmethod
    def apply_context_payload(payload, _context):
        return payload

    @staticmethod
    def error_response(message):
        return {"ok": False, "error": message}


def test_changelog_reconciliation_preview_reports_drift_without_writes(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    global_path.parent.mkdir(parents=True, exist_ok=True)

    changelog_path.write_text(
        """# Project Changelog

## Added parser
- `entry_id`: 20260512:add-parser
- `entry_status`: accepted
- `title`: Add parser
- `summary`: Added parser summary
- `evidence_refs`:
  - tests/a.py

## Duplicate id
- `entry_id`: 20260512:add-parser
- `entry_status`: accepted
- `title`: Duplicate
- `summary`: Duplicate summary
- `evidence_refs`:
  - tests/b.py

## New feature
- `entry_id`: 20260512:new-feature
- `entry_status`: accepted
- `title`: New feature
- `summary`: New feature summary
- `evidence_refs`:
  - tests/c.py

## Draft item
- `entry_id`: 20260512:draft-item
- `entry_status`: draft
- `title`: Draft item
- `summary`: Draft summary
- `evidence_refs`:
  - tests/d.py
""",
        encoding="utf-8",
    )

    global_path.write_text(
        """# Global Changelog

## Existing
- `source_entry_id`: 20260512:add-parser
- summary: stale summary text

## Orphaned
- `source_entry_id`: 20260501:orphaned
- summary: orphan
""",
        encoding="utf-8",
    )

    project = {
        "name": "preview_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }

    result = asyncio.run(
        _handle_preview_reconciliation(
            project=project,
            metadata={"preview_type": "changelog"},
            helper=_QueryHelper(),
            context=None,
        )
    )

    assert result["ok"] is True
    assert result["writes_performed"] is False
    assert result["missing_in_global"] == ["20260512:new-feature"]
    assert result["changed_since_global"] == ["20260512:add-parser"]
    assert result["duplicate_source_keys"] == ["20260512:add-parser"]
    assert result["orphaned_global_entries"] == ["20260501:orphaned"]
    assert result["unversioned_entries"] == ["20260512:add-parser", "20260512:add-parser", "20260512:new-feature"]
    assert result["source_entry_ids"]["adds"] == ["20260512:new-feature"]
    assert result["source_entry_ids"]["updates"] == ["20260512:add-parser"]
    assert result["source_entry_ids"]["removals"] == ["20260501:orphaned"]
    assert result["source_entry_ids"]["skips"] == []


def test_changelog_preview_handles_missing_global_file_read_only(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        """# Project Changelog

## Item
- `entry_id`: 20260512:one
- `entry_status`: accepted
- `title`: One
- `summary`: One summary
- `evidence_refs`:
  - tests/a.py
""",
        encoding="utf-8",
    )

    project = {
        "name": "preview_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }

    result = asyncio.run(
        _handle_preview_reconciliation(
            project=project,
            metadata={"preview_type": "changelog"},
            helper=_QueryHelper(),
            context=None,
        )
    )

    assert result["ok"] is True
    assert result["writes_performed"] is False
    assert result["missing_in_global"] == ["20260512:one"]
    assert result["changed_since_global"] == []
    assert result["orphaned_global_entries"] == []


def test_changelog_preview_cross_project_collision_reports_missing_for_current_project(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    global_path.parent.mkdir(parents=True, exist_ok=True)

    changelog_path.write_text(
        """# Project Changelog

## Shared key in this project
- `entry_id`: 20260512:shared
- `entry_status`: accepted
- `title`: Shared key
- `summary`: Current project summary
- `evidence_refs`:
  - tests/shared.py
""",
        encoding="utf-8",
    )

    global_path.write_text(
        """# Global Changelog

## Other project entry
- `source_project`: other-project
- `source_entry_id`: 20260512:shared
- `summary`: Other project summary
""",
        encoding="utf-8",
    )

    project = {
        "name": "preview_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }
    result = asyncio.run(
        _handle_preview_reconciliation(
            project=project,
            metadata={"preview_type": "changelog"},
            helper=_QueryHelper(),
            context=None,
        )
    )

    assert result["ok"] is True
    assert result["missing_in_global"] == ["20260512:shared"]
    assert result["changed_since_global"] == []
    assert result["source_entry_ids"]["skips"] == []


def test_changelog_preview_summary_locality_uses_matched_global_entry_only(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    global_path.parent.mkdir(parents=True, exist_ok=True)

    changelog_path.write_text(
        """# Project Changelog

## Item one
- `entry_id`: 20260512:one
- `entry_status`: accepted
- `title`: One
- `summary`: Summary A
- `evidence_refs`:
  - tests/one.py
""",
        encoding="utf-8",
    )

    global_path.write_text(
        """# Global Changelog

## Matched stale entry
- `source_project`: preview_changelog
- `source_entry_id`: 20260512:one
- `summary`: Stale summary

## Unrelated entry with same summary text
- `source_project`: preview_changelog
- `source_entry_id`: 20260512:two
- `summary`: Summary A
""",
        encoding="utf-8",
    )

    project = {
        "name": "preview_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }
    result = asyncio.run(
        _handle_preview_reconciliation(
            project=project,
            metadata={"preview_type": "changelog"},
            helper=_QueryHelper(),
            context=None,
        )
    )

    assert result["ok"] is True
    assert result["changed_since_global"] == ["20260512:one"]
