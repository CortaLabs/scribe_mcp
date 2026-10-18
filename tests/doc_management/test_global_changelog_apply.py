from __future__ import annotations

import asyncio
from pathlib import Path

from scribe_mcp.doc_management.actions.query import handle_query_actions


class _QueryHelper:
    @staticmethod
    def apply_context_payload(payload, _context):
        return payload

    @staticmethod
    def error_response(message):
        return {"ok": False, "error": message}


def test_apply_global_changelog_writes_only_global_doc_and_preserves_source_keys(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    project_changelog_original = """# Project Changelog

## Add parser
- `entry_id`: 20260512:add-parser
- `entry_status`: accepted
- `title`: Add parser
- `summary`: Added parser summary
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 1.2.3
"""
    changelog_path.write_text(project_changelog_original, encoding="utf-8")
    (tmp_path / ".scribe" / "docs").mkdir(parents=True, exist_ok=True)
    global_path.write_text("# Global Changelog\n\n", encoding="utf-8")

    project = {
        "name": "apply_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }
    result = asyncio.run(
        handle_query_actions(
            action="apply_global_changelog",
            project=project,
            doc_name=None,
            metadata={},
            helper=_QueryHelper(),
            context=None,
        )
    )
    assert result is not None
    assert result["ok"] is True
    assert result["writes_performed"] is True
    assert result["applied_source_keys"] == [["apply_changelog", "20260512:add-parser"]]
    assert changelog_path.read_text(encoding="utf-8") == project_changelog_original
    assert "- `source_project`: apply_changelog" in global_path.read_text(encoding="utf-8")
    assert "- `source_entry_id`: 20260512:add-parser" in global_path.read_text(encoding="utf-8")


def test_apply_global_changelog_is_noop_when_global_matches(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    changelog_path.write_text(
        """# Project Changelog

## Add parser
- `entry_id`: 20260512:add-parser
- `entry_status`: accepted
- `title`: Add parser
- `summary`: Added parser summary
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 1.2.3
""",
        encoding="utf-8",
    )
    (tmp_path / ".scribe" / "docs").mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        """# Global Changelog

## Add parser
- `source_project`: apply_changelog
- `source_entry_id`: 20260512:add-parser
- `summary`: Added parser summary
""",
        encoding="utf-8",
    )
    before = global_path.read_text(encoding="utf-8")
    project = {
        "name": "apply_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }
    result = asyncio.run(
        handle_query_actions(
            action="apply_global_changelog",
            project=project,
            doc_name=None,
            metadata={},
            helper=_QueryHelper(),
            context=None,
        )
    )
    assert result is not None
    assert result["ok"] is True
    assert result["writes_performed"] is False
    assert global_path.read_text(encoding="utf-8") == before


def test_apply_global_changelog_preserves_other_projects_and_replaces_current_project_entries(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    project_changelog_original = """# Project Changelog

## Add parser
- `entry_id`: 20260512:add-parser
- `entry_status`: accepted
- `title`: Add parser
- `summary`: New parser summary
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 1.2.3
"""
    changelog_path.write_text(project_changelog_original, encoding="utf-8")
    (tmp_path / ".scribe" / "docs").mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        """# Global Changelog

## 20260510:other-change
- `source_project`: other_project
- `source_entry_id`: 20260510:other-change
- `summary`: Keep this untouched

## 20260512:add-parser
- `source_project`: apply_changelog
- `source_entry_id`: 20260512:add-parser
- `summary`: Old stale summary
""",
        encoding="utf-8",
    )

    project = {
        "name": "apply_changelog",
        "root": str(tmp_path),
        "docs": {"CHANGELOG": str(changelog_path)},
    }
    result = asyncio.run(
        handle_query_actions(
            action="apply_global_changelog",
            project=project,
            doc_name=None,
            metadata={},
            helper=_QueryHelper(),
            context=None,
        )
    )

    assert result is not None
    assert result["ok"] is True
    assert result["writes_performed"] is True
    assert result["applied_source_keys"] == [
        ["other_project", "20260510:other-change"],
        ["apply_changelog", "20260512:add-parser"],
    ]
    global_text = global_path.read_text(encoding="utf-8")
    assert "- `source_project`: other_project" in global_text
    assert "- `source_entry_id`: 20260510:other-change" in global_text
    assert "- `summary`: Keep this untouched" in global_text
    assert "- `summary`: New parser summary" in global_text
    assert "Old stale summary" not in global_text
    assert changelog_path.read_text(encoding="utf-8") == project_changelog_original


def test_apply_global_changelog_blocks_unsafe_accepted_entries_and_preserves_existing_global(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    changelog_path.write_text(
        """# Project Changelog

## Unsafe accepted
- `entry_id`: 20260512:unsafe
- `entry_status`: accepted
- `title`: Unsafe accepted
- `summary`: Unsafe summary
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: unknown
  - `value`: old
""",
        encoding="utf-8",
    )
    (tmp_path / ".scribe" / "docs").mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        """# Global Changelog

## Existing trusted
- `source_project`: other_project
- `source_entry_id`: 20260510:trusted
- `summary`: Keep trusted
""",
        encoding="utf-8",
    )
    before = global_path.read_text(encoding="utf-8")
    project = {"name": "apply_changelog", "root": str(tmp_path), "docs": {"CHANGELOG": str(changelog_path)}}
    result = asyncio.run(
        handle_query_actions(
            action="apply_global_changelog",
            project=project,
            doc_name=None,
            metadata={},
            helper=_QueryHelper(),
            context=None,
        )
    )
    assert result is not None
    assert result["ok"] is False
    assert result["writes_performed"] is False
    assert result["provenance_blocked_entries"] == [
        {"entry_id": "20260512:unsafe", "reason": "unsafe_observed_source:unknown"}
    ]
    assert global_path.read_text(encoding="utf-8") == before


def test_apply_global_changelog_blocks_allowed_source_with_empty_value_and_preserves_existing_global(tmp_path: Path) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    global_path = tmp_path / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    changelog_path.write_text(
        """# Project Changelog

## Empty release manifest value
- `entry_id`: 20260512:empty-release-manifest
- `entry_status`: accepted
- `title`: Empty release manifest value
- `summary`: Empty values must fail closed.
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: release_manifest
  - `value`:
""",
        encoding="utf-8",
    )
    (tmp_path / ".scribe" / "docs").mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        """# Global Changelog

## Existing trusted
- `source_project`: other_project
- `source_entry_id`: 20260510:trusted
- `summary`: Keep trusted
""",
        encoding="utf-8",
    )
    before = global_path.read_text(encoding="utf-8")
    project = {"name": "apply_changelog", "root": str(tmp_path), "docs": {"CHANGELOG": str(changelog_path)}}
    result = asyncio.run(
        handle_query_actions(
            action="apply_global_changelog",
            project=project,
            doc_name=None,
            metadata={},
            helper=_QueryHelper(),
            context=None,
        )
    )
    assert result is not None
    assert result["ok"] is False
    assert result["writes_performed"] is False
    assert result["provenance_blocked_entries"] == [
        {"entry_id": "20260512:empty-release-manifest", "reason": "missing_observed_value"}
    ]
    assert global_path.read_text(encoding="utf-8") == before
