from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_TEMPLATE = (
    REPO_ROOT
    / "packages"
    / "scribe_council"
    / "src"
    / "scribe_council"
    / "council_templates"
    / "skills"
    / "scribe-integration"
    / "SKILL.md.j2"
)


def test_bug_reporting_keeps_visibility_immediate_and_case_ceremony_conditional() -> (
    None
):
    source = SKILL_TEMPLATE.read_text(encoding="utf-8")
    rendered = Environment(undefined=StrictUndefined).from_string(source).render()
    normalized = " ".join(rendered.split())

    assert "Every discovered bug MUST be logged immediately" in normalized
    assert "never hide, defer, or silently absorb discovery" in normalized
    assert "Tiny in-contract defects remain attached" in normalized
    assert "do not automatically require `open_bug`" in normalized
    assert "Open a durable case immediately when severity, recurrence" in normalized
    assert "cross-session coordination" in normalized
    assert "security significance" in normalized
    assert "knowledge value" in normalized
    assert "operator direction, or Atlas routing warrants it" in normalized
    assert "Preserve Mantis's diagnosis/repair authority" in normalized
    assert "After the durable-case threshold is met" in normalized
    assert "# Step 1: Open the durable case" in rendered
    assert "open_bug(" in rendered
    assert 'action="create"' in rendered
    for required_section in (
        'section="symptoms"',
        'section="root_cause"',
        'section="fix"',
    ):
        assert required_section in rendered
    assert "# Step 4: Link the fix when resolved" in rendered
    assert "link_fix(" in rendered
    assert "Open a durable bug case" in normalized
    assert "after the durable-case threshold is met" in normalized
    assert "Every discovery is still logged immediately" in normalized
    assert "When you find a bug, file it immediately" not in normalized
    assert "File immediately when you find a bug" not in normalized
