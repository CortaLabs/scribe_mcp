from __future__ import annotations

import asyncio
from pathlib import Path

from scribe_mcp.doc_management.actions.query import (
    _handle_list_checklist_items,
    _handle_list_sections,
)
from scribe_mcp.template_engine import Jinja2TemplateEngine


class _QueryHelper:
    @staticmethod
    def apply_context_payload(payload, _context):
        return payload

    @staticmethod
    def error_response(message):
        return {"ok": False, "error": message}


def test_planning_templates_render_neutral_scaffolds_and_stay_queryable(tmp_path: Path) -> None:
    engine = Jinja2TemplateEngine(project_root=tmp_path, project_name="scaffold_hygiene")

    phase_plan = engine.render_template(
        "documents/PHASE_PLAN_TEMPLATE.md",
        metadata={"summary": "Execution roadmap for scaffold_hygiene.", "phases": [], "milestones": []},
    )
    checklist = engine.render_template(
        "documents/CHECKLIST_TEMPLATE.md",
        metadata={"summary": "Acceptance checklist for scaffold_hygiene.", "sections": []},
    )

    assert "Fix async/await bug in manager.py" not in phase_plan
    assert "Template Engine Ship" not in phase_plan
    assert "Integrate Jinja2 template engine with security sandboxing" not in checklist
    assert "Implement file system watcher for manual edit detection" not in checklist

    assert "Describe the first bounded outcome" in phase_plan
    assert "Add package-specific acceptance item with expected verification command" in checklist
    assert not any(line.endswith((" ", "\t")) for line in phase_plan.splitlines())
    assert not any(line.endswith((" ", "\t")) for line in checklist.splitlines())

    docs_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "scaffold_hygiene"
    docs_dir.mkdir(parents=True, exist_ok=True)
    phase_plan_path = docs_dir / "PHASE_PLAN.md"
    checklist_path = docs_dir / "CHECKLIST.md"
    phase_plan_path.write_text(phase_plan, encoding="utf-8")
    checklist_path.write_text(checklist, encoding="utf-8")

    registered_project = {
        "name": "scaffold_hygiene",
        "docs": {
            "phase_plan": str(phase_plan_path),
            "checklist": str(checklist_path),
        },
    }
    helper = _QueryHelper()

    sections_result = asyncio.run(
        _handle_list_sections(
            registered_project,
            doc_name="phase_plan",
            metadata={"page": 1, "page_size": 50},
            helper=helper,
            context=None,
        )
    )
    assert sections_result["ok"] is True
    assert sections_result["sections"]

    checklist_result = asyncio.run(
        _handle_list_checklist_items(
            registered_project,
            doc_name="checklist",
            metadata={
                "text": "Add package-specific acceptance item with expected verification command (proof: test output or artifact path)."
            },
            helper=helper,
            context=None,
        )
    )
    assert checklist_result["ok"] is True
    assert checklist_result["matches"]
