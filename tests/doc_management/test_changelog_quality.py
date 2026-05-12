from scribe_mcp.doc_management.scaffold_quality import collect_managed_doc_quality_warnings


def _codes(warnings):
    return {w.get("code") for w in warnings}


def test_changelog_quality_blocks_missing_fields_and_ambiguous_status() -> None:
    text = """# Project Changelog

## Bad accepted entry
- `entry_id`: 20260512:entry-one
- `entry_status`: accepted
- `title`: Entry One
- `evidence_refs`:
Status: accepted
"""
    warnings = collect_managed_doc_quality_warnings(text=text, doc_name="CHANGELOG")
    codes = _codes(warnings)
    assert "SCF_CHANGELOG_SUMMARY_MISSING" in codes
    assert "SCF_CHANGELOG_AMBIGUOUS_BODY_STATUS" in codes


def test_changelog_quality_blocks_duplicate_and_progress_dump() -> None:
    text = """# Project Changelog

## First
- `entry_id`: 20260512:dup
- `entry_status`: accepted
- `title`: One
- `summary`: Summary one
- `evidence_refs`:
  - tests/a.py
[✅] [2026-05-12 01:00 UTC] [Agent: x] [Project: y] raw log

## Second
- `entry_id`: 20260512:dup
- `entry_status`: accepted
- `title`: Two
- `summary`: Summary two
- `evidence_refs`:
  - tests/b.py
"""
    warnings = collect_managed_doc_quality_warnings(text=text, doc_name="CHANGELOG")
    codes = _codes(warnings)
    assert "SCF_CHANGELOG_DUPLICATE_SOURCE_KEY" in codes
    assert "SCF_CHANGELOG_RAW_PROGRESS_DUMP" in codes


def test_changelog_quality_blocks_literal_escaped_newline_scaffold() -> None:
    text = (
        "# Project Changelog\\n\\n"
        "Use one section per curated project outcome.\\n\\n"
        "## Entry Template\\n"
        "- `entry_id`: <yyyymmdd>:<slug>\\n"
    )
    warnings = collect_managed_doc_quality_warnings(text=text, doc_name="CHANGELOG")
    codes = _codes(warnings)
    assert "SCF_CHANGELOG_ESCAPED_NEWLINES" in codes


def test_changelog_quality_blocks_literal_escaped_newline_scaffold_with_frontmatter_and_real_newline() -> None:
    text = """---
status: draft
---
# Project Changelog
Use one section per curated project outcome.
# Project Changelog\\n\\nUse one section per curated project outcome.\\n\\n## Entry Template\\n- `entry_id`: <yyyymmdd>:<slug>\\n- `entry_status`: accepted\\n- `title`: Example\\n- `summary`: Example summary\\n- `evidence_refs`:\\n  - tests/example.py\\n
"""
    warnings = collect_managed_doc_quality_warnings(text=text, doc_name="CHANGELOG")
    codes = _codes(warnings)
    assert "SCF_CHANGELOG_ESCAPED_NEWLINES" in codes
