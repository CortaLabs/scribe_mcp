from scribe_mcp.doc_management.changelog import (
    accepted_entries,
    is_valid_entry_id,
    parse_changelog_entries,
    preview_current_release_coverage,
)


def test_parse_changelog_entries_and_accept_filter() -> None:
    text = """# Project Changelog

## Added parser
- `entry_id`: 20260512:add-parser
- `entry_status`: accepted
- `title`: Add parser
- `summary`: Added parser for entry model.
- `evidence_refs`:
  - tests/doc_management/test_changelog_model.py

## Draft item
- `entry_id`: 20260512:draft-item
- `entry_status`: draft
- `title`: Draft
- `summary`: WIP
- `evidence_refs`:
  - proof
"""
    entries = parse_changelog_entries(text)
    assert len(entries) == 2
    assert len(accepted_entries(entries)) == 1
    assert entries[0].entry_id == "20260512:add-parser"


def test_entry_id_validation() -> None:
    assert is_valid_entry_id("20260512:add-parser")
    assert not is_valid_entry_id("project:20260512:add-parser")


def test_parse_observed_context_block() -> None:
    text = """# Project Changelog

## Context entry
- `entry_id`: 20260512:context-entry
- `entry_status`: accepted
- `title`: Context entry
- `summary`: Includes observed context.
- `evidence_refs`:
  - tests/doc_management/test_changelog_model.py
- `observed_context`:
  - `value`: 1.2.3
  - `source`: pyproject
  - `commit`: abc1234
  - `dirty`: false
  - `observed_at`: 2026-05-12T00:00:00Z
  - `confidence`: exact
"""
    entries = parse_changelog_entries(text)
    assert len(entries) == 1
    context = entries[0].observed_context
    assert context is not None
    assert context["value"] == "1.2.3"
    assert context["source"] == "pyproject"
    assert context["commit"] == "abc1234"
    assert context["dirty"] is False
    assert context["observed_at"] == "2026-05-12T00:00:00Z"
    assert context["confidence"] == "exact"


def test_preview_current_release_coverage_pass(tmp_path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.2.3"\n', encoding="utf-8")
    changelog = """# Project Changelog

## Entry
- `entry_id`: 20260512:covered
- `entry_status`: accepted
- `title`: Covered
- `summary`: covered
- `evidence_refs`:
  - tests/doc_management/test_changelog_model.py
- `observed_context`:
  - `value`: 1.2.3
  - `source`: pyproject
"""
    result = preview_current_release_coverage(
        project_changelog_text=changelog,
        repo_root=tmp_path,
        pyproject_path=pyproject,
    )
    assert result["status"] == "pass"
    assert result["matching_entry_ids"] == ["20260512:covered"]
    assert result["writes_performed"] is False


def test_preview_current_release_coverage_missing(tmp_path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.2.3"\n', encoding="utf-8")
    changelog = """# Project Changelog

## Entry
- `entry_id`: 20260512:not-covered
- `entry_status`: accepted
- `title`: Not covered
- `summary`: not covered
- `evidence_refs`:
  - tests/doc_management/test_changelog_model.py
- `observed_context`:
  - `value`: 9.9.9
  - `source`: pyproject
"""
    result = preview_current_release_coverage(
        project_changelog_text=changelog,
        repo_root=tmp_path,
        pyproject_path=pyproject,
    )
    assert result["status"] == "missing"
    assert result["matching_entry_ids"] == []
    assert "observed_context.source=pyproject" in result["suggested_repair"]
    assert result["writes_performed"] is False


def test_preview_current_release_coverage_not_applicable_without_pyproject(tmp_path) -> None:
    result = preview_current_release_coverage(
        project_changelog_text="# Project Changelog\n",
        repo_root=tmp_path,
        pyproject_path=tmp_path / "missing.toml",
    )
    assert result["status"] == "not_applicable"
    assert result["matching_entry_ids"] == []
    assert result["writes_performed"] is False
