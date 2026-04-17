from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from scribe_mcp.doc_management.actions.query import _handle_preview_reconciliation


class _QueryHelper:
    @staticmethod
    def apply_context_payload(payload, _context):
        return payload

    @staticmethod
    def error_response(message):
        return {"ok": False, "error": message}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_preview_reconciliation_reports_unmapped_and_stale_without_writes(tmp_path: Path) -> None:
    phase_plan_path = tmp_path / "PHASE_PLAN.md"
    checklist_path = tmp_path / "CHECKLIST.md"

    phase_plan_path.write_text(
        "\n".join(
            [
                "# Phase Plan",
                "",
                "**Task Package 1.1 - Scaffold Hygiene**",
                "- Scope: ...",
                "",
                "**Task Package 1.2 - Reconciliation Preview**",
                "- Scope: ...",
                "",
                "**Task Package 1.3 - Readiness Proof**",
                "- Scope: ...",
                "",
            ]
        ),
        encoding="utf-8",
    )
    checklist_path.write_text(
        "\n".join(
            [
                "# Checklist",
                "",
                "- [x] <!-- id: p1-scaffold-hygiene --> Scaffold hygiene proof.",
                "- [ ] <!-- id: p1-readiness-proof --> Readiness proof.",
                "- [ ] <!-- id: p1-retired-item --> Retired checklist item.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    phase_before = _sha256(phase_plan_path)
    checklist_before = _sha256(checklist_path)

    project = {
        "name": "preview_hygiene",
        "docs": {
            "phase_plan": str(phase_plan_path),
            "checklist": str(checklist_path),
        },
        "meta": {
            "docs": {
                "flags": {
                    "docs_ready_for_work": True,
                    "phase_plan_modified": False,
                    "checklist_modified": False,
                },
                "baseline_hashes": {
                    "phase_plan": "aaaa1111",
                    "checklist": "bbbb2222",
                },
                "current_hashes": {
                    "phase_plan": "cccc3333",
                    "checklist": "bbbb2222",
                },
            }
        },
    }

    result = asyncio.run(
        _handle_preview_reconciliation(
            project=project,
            metadata={},
            helper=_QueryHelper(),
            context=None,
        )
    )

    assert result["ok"] is True
    assert result["writes_performed"] is False

    assert result["summary"]["phase_task_packages"] == 3
    assert result["summary"]["unmapped_package_count"] == 1
    assert result["summary"]["stale_checklist_count"] == 1
    assert result["summary"]["has_drift"] is True

    assert result["unmapped_packages"][0]["package_id"] == "1.2"
    assert result["stale_checklist_items"][0]["id"] == "p1-retired-item"

    readiness_conflicts = result["readiness_signals"]["readiness_conflicts"]
    assert readiness_conflicts
    assert any("docs_ready_for_work is true" in conflict for conflict in readiness_conflicts)
    assert any("phase_plan_modified flag is false" in conflict for conflict in readiness_conflicts)

    assert _sha256(phase_plan_path) == phase_before
    assert _sha256(checklist_path) == checklist_before


def test_preview_reconciliation_action_is_wired_as_query_read_only() -> None:
    runtime_source = (
        Path(__file__).resolve().parents[2] / "src" / "scribe_mcp" / "doc_management" / "runtime.py"
    ).read_text(encoding="utf-8")
    assert '"preview_reconciliation"' in runtime_source
    assert '"preview_reconciliation": "query"' in runtime_source
