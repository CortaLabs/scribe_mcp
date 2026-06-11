"""Regression tests for P1.2 — replace_text multi-line contract.

Live-reproduced defect (RESEARCH_AGENT_FRICTION_AUDIT F4): replace_text
returned REPLACE_TEXT_NO_MATCH for a find string verbatim in the file.
Root cause: BulletproofParameterCorrector.correct_metadata_parameter
sanitized metadata string values (newlines flattened to spaces, <>|
rewritten, 500-char truncation) before the matcher ran, so any multi-line
or angle-bracket find could never match — and a multi-line `replace`
value would be silently flattened into the document.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.healing import normalize_metadata_with_healing
from scribe_mcp.doc_management.manager import (
    DocumentOperationError,
    _replace_text_with_scope,
)
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector

DOC = (
    "# Title\n"
    "\n"
    "## Research Scope\n"
    "<!-- ID: research_scope -->\n"
    "## Research Scope\n"
    "\n"
    "**Goal:** Establish evidence-backed findings.\n"
    "\n"
    "---\n"
    "## Findings\n"
)

MULTILINE_FIND = "<!-- ID: research_scope -->\n## Research Scope\n\n**Goal:**"


def test_corrector_preserves_find_and_replace_verbatim():
    meta = {
        "find": MULTILINE_FIND,
        "replace": "line one\nline two\n",
        "note": "a|b\nc",  # non-payload key still sanitized
    }
    corrected = BulletproofParameterCorrector.correct_metadata_parameter(meta)
    assert corrected["find"] == MULTILINE_FIND
    assert corrected["replace"] == "line one\nline two\n"
    assert "\n" not in corrected["note"]


def test_corrector_preserves_long_and_angle_bracket_finds():
    long_find = ("x" * 600) + "<tag>|pipe"
    corrected = BulletproofParameterCorrector.correct_metadata_parameter(
        {"find": long_find}
    )
    assert corrected["find"] == long_find


def test_multiline_find_survives_healing_and_matches():
    """The exact live failure scenario: healed metadata feeding the matcher."""
    healed, _, _ = normalize_metadata_with_healing({"find": MULTILINE_FIND, "replace": "<!-- ID: research_scope -->\n**Goal:**"})
    updated, hits = _replace_text_with_scope(
        DOC,
        find_text=healed["find"],
        replace_text=healed["replace"],
        match_mode="literal",
        replace_all=True,
        scope=None,
        allow_no_match=False,
    )
    assert hits == 1
    assert "## Research Scope\n<!-- ID: research_scope -->\n**Goal:**" in updated
    # the duplicate heading between anchor and Goal is gone
    assert updated.count("## Research Scope") == 1


def test_single_line_replace_unchanged():
    updated, hits = _replace_text_with_scope(
        DOC,
        find_text="**Goal:** Establish evidence-backed findings.",
        replace_text="**Goal:** Updated.",
        match_mode="literal",
        replace_all=True,
        scope=None,
        allow_no_match=False,
    )
    assert hits == 1
    assert "**Goal:** Updated." in updated


def test_no_match_error_includes_span_and_near_miss_hint():
    with pytest.raises(DocumentOperationError) as exc_info:
        _replace_text_with_scope(
            DOC,
            find_text="<!-- ID: research_scope -->\n## Research Scopes\n\n**Goal:**",
            replace_text="x",
            match_mode="literal",
            replace_all=True,
            scope=None,
            allow_no_match=False,
        )
    message = str(exc_info.value)
    assert message.startswith("REPLACE_TEXT_NO_MATCH")
    assert "find spans 4 lines" in message
    assert "nearest line in document" in message


def test_no_match_single_line_keeps_code_and_reports_no_similar():
    with pytest.raises(DocumentOperationError) as exc_info:
        _replace_text_with_scope(
            DOC,
            find_text="zzz completely absent zzz",
            replace_text="x",
            match_mode="literal",
            replace_all=True,
            scope=None,
            allow_no_match=False,
        )
    message = str(exc_info.value)
    assert message.startswith("REPLACE_TEXT_NO_MATCH")
    assert "no similar line found" in message
