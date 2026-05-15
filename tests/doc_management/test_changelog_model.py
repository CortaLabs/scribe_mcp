from scribe_mcp.doc_management.changelog import (
    accepted_entries,
    accepted_entries_with_safe_provenance,
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


def test_accepted_entries_with_safe_provenance_blocks_unknown_manual_and_missing_context() -> None:
    text = """# Project Changelog

## Safe
- `entry_id`: 20260512:safe
- `entry_status`: accepted
- `title`: Safe
- `summary`: Safe summary
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 1.2.3

## Unknown
- `entry_id`: 20260512:unknown
- `entry_status`: accepted
- `title`: Unknown
- `summary`: Unknown summary
- `evidence_refs`:
  - tests/b.py
- `observed_context`:
  - `source`: unknown
  - `value`: old

## Manual backfill
- `entry_id`: 20260512:manual
- `entry_status`: accepted
- `title`: Manual
- `summary`: Manual summary
- `evidence_refs`:
  - tests/c.py
- `observed_context`:
  - `source`: manual_backfill
  - `value`: old

## Missing context
- `entry_id`: 20260512:missing
- `entry_status`: accepted
- `title`: Missing
- `summary`: Missing summary
- `evidence_refs`:
  - tests/d.py
"""
    safe, blocked = accepted_entries_with_safe_provenance(parse_changelog_entries(text))
    assert [entry.entry_id for entry in safe] == ["20260512:safe"]
    assert blocked == [
        {"entry_id": "20260512:manual", "reason": "unsafe_observed_source:manual_backfill"},
        {"entry_id": "20260512:missing", "reason": "missing_observed_context"},
        {"entry_id": "20260512:unknown", "reason": "unsafe_observed_source:unknown"},
    ]


def test_accepted_entries_with_safe_provenance_blocks_empty_values_for_allowed_sources() -> None:
    text = """# Project Changelog

## Empty git tag
- `entry_id`: 20260512:empty-git-tag
- `entry_status`: accepted
- `title`: Empty git tag
- `summary`: Empty value must fail closed.
- `evidence_refs`:
  - tests/a.py
- `observed_context`:
  - `source`: git_tag
  - `value`:

## Empty release manifest
- `entry_id`: 20260512:empty-release-manifest
- `entry_status`: accepted
- `title`: Empty release manifest
- `summary`: Empty value must fail closed.
- `evidence_refs`:
  - tests/b.py
- `observed_context`:
  - `source`: release_manifest
  - `value`:
"""
    safe, blocked = accepted_entries_with_safe_provenance(parse_changelog_entries(text))
    assert safe == []
    assert blocked == [
        {"entry_id": "20260512:empty-git-tag", "reason": "missing_observed_value"},
        {"entry_id": "20260512:empty-release-manifest", "reason": "missing_observed_value"},
    ]
