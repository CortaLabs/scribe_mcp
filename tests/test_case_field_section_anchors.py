"""Regression tests for P1.6 — case completeness fields map to real anchors.

Live-reproduced defect (BUG-2026-06-11-0004 authoring, audit F2/F5): open_bug
guidance named completeness FIELDS (e.g. reproduction_steps) as replace_section
targets, but the bug scaffold's anchors are {bug_overview, description,
investigation, resolution_plan, timeline, appendix} — so following the tool's
own next_step failed with SECTION_ANCHOR_MISSING.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.sentinel_tools import (
    _BUG_FIELD_SECTION_ANCHORS,
    _BUG_TEMPLATE_FIELDS,
    _SECURITY_FIELD_SECTION_ANCHORS,
    _format_unfilled_guidance,
)

TEMPLATES = Path(__file__).parent.parent / "src" / "scribe_mcp" / "templates" / "documents"


def _template_anchors(template_name: str) -> set[str]:
    text = (TEMPLATES / template_name).read_text()
    return set(re.findall(r'\{%\s*call\s+section\([^,]+,\s*"([a-z_]+)"', text))


def test_every_completeness_field_has_an_anchor_mapping():
    for field in _BUG_TEMPLATE_FIELDS:
        assert field in _BUG_FIELD_SECTION_ANCHORS, field
        assert field in _SECURITY_FIELD_SECTION_ANCHORS, field


def test_bug_anchor_map_points_at_real_template_anchors():
    anchors = _template_anchors("BUG_REPORT_TEMPLATE.md")
    for field, anchor in _BUG_FIELD_SECTION_ANCHORS.items():
        assert anchor in anchors, f"{field} -> {anchor} not in bug template anchors {anchors}"


def test_security_anchor_map_points_at_real_template_anchors():
    anchors = _template_anchors("SECURITY_REPORT_TEMPLATE.md")
    for field, anchor in _SECURITY_FIELD_SECTION_ANCHORS.items():
        assert anchor in anchors, (
            f"{field} -> {anchor} not in security template anchors {anchors}"
        )


def test_guidance_renders_fields_with_anchors_and_truncation():
    fields = ["reproduction_steps", "root_cause", "immediate_actions", "symptoms"]
    rendered = _format_unfilled_guidance(fields, _BUG_FIELD_SECTION_ANCHORS, 3)
    assert "reproduction_steps (section='description')" in rendered
    assert "root_cause (section='investigation')" in rendered
    assert "immediate_actions (section='resolution_plan')" in rendered
    assert rendered.endswith(" and 1 more")


def test_guidance_no_truncation_when_under_limit():
    rendered = _format_unfilled_guidance(["symptoms"], _BUG_FIELD_SECTION_ANCHORS, 3)
    assert rendered == "symptoms (section='description')"
