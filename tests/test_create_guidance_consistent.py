"""Regression tests for P1.5 — create-guidance reconciliation.

Live-reproduced friction (RESEARCH_AGENT_FRICTION_AUDIT F1/F4): three
guidance surfaces gave conflicting "next action" recommendations after
create — create_intent said replace_section, the teaching reminder said
prefer apply_patch and reserve replace_section, and the rule text said
apply_patch is primary. The reconciled story, asserted here against the
real sources: populate scaffold sections with replace_section; use
apply_patch for surgical edits to existing content.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.runtime import build_create_intent_payload

REPO = Path(__file__).parent.parent
REMINDERS = REPO / "src" / "scribe_mcp" / "config" / "reminders" / "en-US.json"
RULE_TEMPLATE = (
    REPO / ".council" / "templates" / "claude" / "rules" / "_rule_manage_docs_create.j2"
)

# The old contradictory phrasing must not reappear on any surface.
FORBIDDEN = "best reserved for scaffolding templates"


def _teaching_template() -> str:
    data = json.loads(REMINDERS.read_text())
    entry = data["reminders"]["teaching"]["manage_docs_precision_preferred"]
    return entry["template"]


def test_teaching_reminder_tells_unified_story():
    template = _teaching_template()
    assert "replace_section" in template
    assert "scaffold" in template.lower()
    assert "apply_patch" in template
    assert FORBIDDEN not in template


def test_scaffold_create_intent_recommends_replace_section():
    payload = build_create_intent_payload(
        result={"ok": True, "doc_name": "X"},
        metadata={"doc_type": "custom"},
        requested_doc_name="X",
    )
    assert payload["kind"] == "governed_scaffold_doc"
    assert payload["first_write_action"] == "replace_section"
    assert "replace_section" in payload["next_step_guidance"]
    assert "apply_patch" in payload["next_step_guidance"]


def test_special_doc_create_intent_recommends_section_population():
    payload = build_create_intent_payload(
        result={"ok": True, "doc_name": "X", "document_type": "research_report"},
        metadata={"doc_type": "research"},
        requested_doc_name="X",
    )
    assert payload["kind"] == "contentful_special_doc"
    assert payload["first_write_action"] == "replace_section"
    assert "replace_section" in payload["next_step_guidance"]
    assert "apply_patch" in payload["next_step_guidance"]


def test_registered_existing_doc_still_recommends_apply_patch():
    payload = build_create_intent_payload(
        result={"ok": True, "doc_name": "X"},
        metadata={"register_existing": True},
        requested_doc_name="X",
    )
    assert payload["kind"] == "empty_registered_doc"
    assert payload["first_write_action"] == "apply_patch"


def test_rule_template_tells_unified_story():
    if not RULE_TEMPLATE.exists():
        import pytest

        pytest.skip(".council rule templates are local config, absent on fresh clones")
    text = RULE_TEMPLATE.read_text()
    assert "Populate scaffold sections" in text
    assert "replace_section" in text
    assert "Surgical edits" in text or "surgical edits" in text.lower()
    assert "apply_patch" in text
    # truthful create framing: no longer claims create is always EMPTY
    assert "scaffolds an EMPTY template" not in text
    assert FORBIDDEN not in text


def test_no_surface_contains_old_contradiction():
    for source in (REMINDERS, RULE_TEMPLATE):
        if not source.exists():
            continue
        assert FORBIDDEN not in source.read_text(), source
