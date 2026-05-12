from scribe_mcp.doc_management.changelog import accepted_entries, is_valid_entry_id, parse_changelog_entries


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
