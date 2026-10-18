"""Regression tests for P1.3 — editable_sections completeness.

Live-reproduced defect (RESEARCH_AGENT_FRICTION_AUDIT F2): the research
create response listed 3 of 6 anchored sections. Root cause: the section
inspector only recognized anchors that were the ENTIRE line, while the
base_document section macro renders anchors with an inline description
("<!-- ID: findings -->Detail each...") and the edit path resolves anchors
by substring — so inline-anchored sections were valid edit targets that
inspection silently omitted.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.actions.query import (
    _match_section_anchor,
    inspect_document_sections_from_text,
)

# Mirrors the rendered research scaffold: three block anchors, three inline.
SCAFFOLD = (
    "# Doc\n"
    "\n"
    "## Executive Summary\n"
    "<!-- ID: executive_summary -->High-level overview of the research effort.\n"
    "body\n"
    "## Research Scope\n"
    "<!-- ID: research_scope -->\n"
    "body\n"
    "## Findings\n"
    "<!-- ID: findings -->Detail each major finding with evidence.\n"
    "body\n"
    "## Technical Analysis\n"
    "<!-- ID: technical_analysis -->\n"
    "body\n"
    "## Recommendations\n"
    "<!-- ID: recommendations -->Translate research into recommended actions.\n"
    "body\n"
    "## Appendix\n"
    "<!-- ID: appendix -->\n"
    "body\n"
)

EXPECTED_IDS = [
    "executive_summary",
    "research_scope",
    "findings",
    "technical_analysis",
    "recommendations",
    "appendix",
]


def test_inline_and_block_anchors_all_reported():
    payload = inspect_document_sections_from_text(SCAFFOLD)
    assert payload["section_source"] == "anchors"
    ids = [s["id"] for s in payload["sections"]]
    assert ids == EXPECTED_IDS


def test_match_section_anchor_variants():
    assert _match_section_anchor("<!-- ID: findings -->") == "findings"
    assert _match_section_anchor("<!-- ID: findings -->trailing text") == "findings"
    assert _match_section_anchor("<!--  ID:  spaced  -->x") == "spaced"
    assert _match_section_anchor("not an anchor") is None
    assert _match_section_anchor("text <!-- ID: mid -->") is None
    assert _match_section_anchor("<!-- ID: -->") is None


def test_duplicate_inline_anchors_detected():
    text = "<!-- ID: dup -->a\nbody\n<!-- ID: dup -->\n"
    payload = inspect_document_sections_from_text(text)
    assert payload.get("duplicates", {}).get("dup") == [1, 3]


def test_code_fence_anchor_still_counted_consistently():
    # Anchors are matched before fence handling (pre-existing behavior for
    # block anchors); this pins that inline anchors behave identically.
    text = "```\n<!-- ID: fenced -->inline\n```\n<!-- ID: real -->\n"
    payload = inspect_document_sections_from_text(text)
    ids = [s["id"] for s in payload["sections"]]
    assert "real" in ids
