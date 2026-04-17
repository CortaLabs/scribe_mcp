from __future__ import annotations

from scribe_mcp.doc_management.manager import _replace_section
from scribe_mcp.doc_management.runtime import build_create_intent_payload
from scribe_mcp.template_engine import Jinja2TemplateEngine


def _count_marker(text: str, section_id: str) -> int:
    return text.count(f"<!-- ID: {section_id} -->")


def test_replace_section_preserves_adjacent_heading_and_anchor_on_repeated_updates() -> None:
    doc = (
        "# Phase Plan\n\n"
        "## Phase 0 — Initial\n"
        "<!-- ID: phase_0 -->\n"
        "old phase 0\n\n"
        "## Phase 1 — Neighbor\n"
        "<!-- ID: phase_1 -->\n"
        "old phase 1\n"
    )

    first = _replace_section(doc, "phase_0", "updated phase 0")
    assert "## Phase 1 — Neighbor" in first
    assert _count_marker(first, "phase_1") == 1

    second = _replace_section(
        first,
        "phase_0",
        "## Phase 0 — Revised\n<!-- ID: phase_0 -->\nrevised phase 0",
    )

    assert "## Phase 0 — Initial" not in second
    assert "## Phase 0 — Revised" in second
    assert "## Phase 1 — Neighbor" in second
    assert _count_marker(second, "phase_0") == 1
    assert _count_marker(second, "phase_1") == 1


def test_replace_section_keeps_phase_and_checklist_scaffolds_structurally_coherent() -> None:
    engine = Jinja2TemplateEngine(project_root=".", project_name="replace_section_structure")

    phase_plan = engine.render_template(
        "documents/PHASE_PLAN_TEMPLATE.md",
        metadata={"summary": "phase scaffold", "phases": [], "milestones": []},
    )
    checklist = engine.render_template(
        "documents/CHECKLIST_TEMPLATE.md",
        metadata={"summary": "checklist scaffold", "sections": []},
    )

    phase_plan = _replace_section(
        phase_plan,
        "phase_0",
        "## Phase 0 — Bounded Slice\n<!-- ID: phase_0 -->\n- [ ] package 2.3 proof",
    )
    phase_plan = _replace_section(phase_plan, "phase_1", "follow-up package details")
    phase_plan = _replace_section(phase_plan, "phase_0", "tightened phase 0 body")

    checklist = _replace_section(
        checklist,
        "phase_0",
        "## Phase 0\n<!-- ID: phase_0 -->\n- [x] proof attached",
    )
    checklist = _replace_section(checklist, "phase_1", "- [ ] next validation")
    checklist = _replace_section(checklist, "phase_0", "- [x] stability regression added")

    for doc_text in (phase_plan, checklist):
        lines = doc_text.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("<!-- ID:"):
                continue
            previous_non_blank = ""
            for back_index in range(index - 1, -1, -1):
                candidate = lines[back_index].strip()
                if candidate:
                    previous_non_blank = candidate
                    break
            assert previous_non_blank.startswith("#"), (
                f"anchor line {index + 1} became detached from heading context"
            )

    assert _count_marker(phase_plan, "phase_0") == 1
    assert _count_marker(phase_plan, "phase_1") == 1
    assert _count_marker(checklist, "phase_0") == 1
    assert _count_marker(checklist, "phase_1") == 1


def test_create_intent_guidance_calls_out_replace_range_fallback() -> None:
    payload = build_create_intent_payload(
        result={"ok": True, "doc_name": "PHASE_PLAN"},
        metadata={"doc_type": "plan"},
        requested_doc_name="PHASE_PLAN",
    )

    assert payload is not None
    guidance = payload.get("next_step_guidance", "")
    assert "replace_section" in guidance
    assert "replace_range" in guidance
    assert "apply_patch" in guidance
