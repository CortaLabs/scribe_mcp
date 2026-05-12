from __future__ import annotations

from pathlib import Path

from scribe_mcp import readiness
from scribe_mcp.readiness import build_readiness_summary, collect_managed_doc_quality_state


def test_readiness_preserves_scf_codes_and_counts(tmp_path: Path) -> None:
    checklist = tmp_path / "CHECKLIST.md"
    checklist.write_text("---\nstatus: ready\n---\n\n# Checklist\n\n- [ ] [TODO fill this]", encoding="utf-8")

    project = {
        "docs": {"checklist": str(checklist)},
        "name": "demo",
        "root": str(tmp_path),
    }
    quality = collect_managed_doc_quality_state(project)

    assert quality["readiness_blocker_count"] >= 1
    doc = quality["documents"][0]
    assert "SCF_FRONTMATTER_MISMATCH" in doc["warning_codes"]
    assert "SCF_FRONTMATTER_MISMATCH" in doc["readiness_blocker_codes"]


def test_readiness_phase_scoping_does_not_force_false_failure() -> None:
    managed = {
        "status": "pass",
        "readiness_blocker_count": 0,
        "total_warning_count": 2,
        "documents": [
            {
                "doc_name": "phase_plan",
                "warning_codes": ["SCF_INDEX_STALE", "SCF_DOC_UNINDEXED"],
                "readiness_blocker_codes": [],
            }
        ],
    }
    summary = build_readiness_summary(current_phase="Phase 1", managed_doc_quality=managed, log_signals=[]).to_dict()
    assert summary["blocker_count"] == 0
    assert summary["warning_count"] == 2


def test_readiness_summary_counts_align_with_project_health_shape() -> None:
    managed = {
        "status": "blocked",
        "readiness_blocker_count": 2,
        "total_warning_count": 3,
        "documents": [],
    }
    signals = [{"code": "LOG_MISSING_PRIORITY", "blocking": False}]
    summary = build_readiness_summary(current_phase=None, managed_doc_quality=managed, log_signals=signals).to_dict()

    assert summary["managed_doc_quality"]["readiness_blocker_count"] == 2
    assert summary["log_friction"]["status"] == "advisory"
    assert summary["warning_count"] == 3
    assert summary["blocker_count"] == 2


def test_collect_managed_doc_quality_filters_future_phase_index_warning(tmp_path: Path, monkeypatch) -> None:
    phase_plan = tmp_path / "PHASE_PLAN.md"
    phase_plan.write_text(
        "---\nstatus: in_progress\n---\n\n"
        "## Phase 1 (In Progress)\n\n"
        "## Research Index\n\n"
        "- [ ] [RESEARCH_PHASE2.md](research/RESEARCH_PHASE2.md)\n",
        encoding="utf-8",
    )
    project = {
        "docs": {"phase_plan": str(phase_plan)},
        "name": "demo",
        "root": str(tmp_path),
        "current_phase": "Phase 1",
    }
    monkeypatch.setattr(
        readiness,
        "collect_managed_doc_quality_warnings",
        lambda **_: [
            {
                "code": "SCF_INDEX_STALE",
                "blocking": True,
                "excerpt": "phase 2 index entry missing",
            }
        ],
    )
    quality = collect_managed_doc_quality_state(project)
    doc = quality["documents"][0]
    assert "SCF_INDEX_STALE" in doc["warning_codes"]
    assert "SCF_INDEX_STALE" not in doc["readiness_blocker_codes"]


def test_readiness_includes_lifecycle_status_mismatch_as_blocker(tmp_path: Path) -> None:
    spec = tmp_path / "SPEC.md"
    spec.write_text("---\nstatus: draft\n---\n\nStatus: ready\n", encoding="utf-8")

    project = {
        "docs": {"spec": str(spec)},
        "name": "demo",
        "root": str(tmp_path),
    }
    quality = collect_managed_doc_quality_state(project)

    assert quality["readiness_blocker_count"] >= 1
    doc = quality["documents"][0]
    assert "SCF_LIFECYCLE_STATUS_MISMATCH" in doc["warning_codes"]
    assert "SCF_LIFECYCLE_STATUS_MISMATCH" in doc["readiness_blocker_codes"]
