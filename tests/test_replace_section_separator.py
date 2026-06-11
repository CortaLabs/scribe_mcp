"""Regression tests for P1.4 — replace_section separator + heading behavior.

Live-reproduced defects (RESEARCH_AGENT_FRICTION_AUDIT F2/F4):
1. replace_section consumed the trailing ``---`` separator belonging to the
   next section boundary (reproduced twice while authoring the audit).
2. Content restating the section's own heading produced a duplicated heading,
   because template headings sit above the anchor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.manager import (
    _pull_back_trailing_separator,
    _replace_section,
)

DOC = (
    "# Doc\n"
    "\n"
    "## Scope\n"
    "<!-- ID: scope -->\n"
    "old scope body\n"
    "\n"
    "---\n"
    "## Findings\n"
    "<!-- ID: findings -->\n"
    "old findings body\n"
    "\n"
    "---\n"
)


def test_trailing_separator_preserved_between_sections():
    info = {}
    updated = _replace_section(DOC, "scope", "new scope body", info=info)
    assert "new scope body" in updated
    assert info.get("preserved_separator") is True
    # separator still sits between scope content and the Findings heading
    assert "new scope body\n\n---\n## Findings" in updated
    assert updated.count("---") == 2


def test_last_section_separator_at_eof_preserved():
    info = {}
    updated = _replace_section(DOC, "findings", "new findings body", info=info)
    assert info.get("preserved_separator") is True
    assert updated.rstrip().endswith("---")
    assert "new findings body\n\n---" in updated


def test_duplicate_heading_stripped_and_reported():
    info = {}
    updated = _replace_section(
        DOC, "scope", "## Scope\n\nnew body without dup", info=info
    )
    assert info.get("stripped_duplicate_heading") == "## Scope"
    # heading appears exactly once (the template one above the anchor)
    assert updated.count("## Scope") == 1
    assert "new body without dup" in updated


def test_different_heading_in_content_is_kept():
    info = {}
    updated = _replace_section(
        DOC, "scope", "### Sub-heading\ncontent under it", info=info
    )
    assert "stripped_duplicate_heading" not in info
    assert "### Sub-heading" in updated


def test_pull_back_no_separator_is_noop():
    text = "<!-- ID: a -->\nbody\nmore body\n"
    end, preserved = _pull_back_trailing_separator(text, len("<!-- ID: a -->\n"), len(text))
    assert preserved is False
    assert end == len(text)


def test_existing_marker_strip_behavior_unchanged():
    # Caller includes heading + marker + body: pre-existing strip still works.
    info = {}
    updated = _replace_section(
        DOC, "scope", "## Scope\n<!-- ID: scope -->\nfull structure body", info=info
    )
    assert updated.count("<!-- ID: scope -->") == 1
    assert "full structure body" in updated
    assert updated.count("## Scope") == 1
