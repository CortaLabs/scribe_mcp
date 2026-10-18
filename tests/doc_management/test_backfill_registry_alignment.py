import asyncio
import sqlite3
from pathlib import Path

from scribe_mcp.doc_management import special_indexes as special_indexes_shared
from scribe_mcp.shared.project_registry import ProjectRegistry


def _seed_project(db_path: Path, name: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scribe_projects (name, created_at, status, meta)
            VALUES (?, '2026-04-16T00:00:00+00:00', 'planning', '{}')
            """,
            (name,),
        )


def test_record_doc_update_keeps_aliases_and_sets_core_readiness(tmp_path):
    db_path = tmp_path / "registry.sqlite"
    registry = ProjectRegistry(db_path=db_path)
    _seed_project(db_path, "p0")

    registry.record_doc_update(
        project_name="p0",
        doc="ARCHITECTURE_GUIDE",
        action="auto_register",
        after_hash="aaa111",
    )
    registry.record_doc_update(
        project_name="p0",
        doc="PHASE_PLAN",
        action="auto_register",
        after_hash="bbb222",
    )
    registry.record_doc_update(
        project_name="p0",
        doc="CHECKLIST",
        action="auto_register",
        after_hash="ccc333",
    )

    info = registry.get_project("p0")
    assert info is not None
    docs_meta = info.meta.get("docs", {})
    current = docs_meta.get("current_hashes", {})
    flags = docs_meta.get("flags", {})

    assert current["architecture"] == "aaa111"
    assert current["ARCHITECTURE_GUIDE"] == "aaa111"
    assert current["phase_plan"] == "bbb222"
    assert current["checklist"] == "ccc333"
    assert flags["architecture_touched"] is True
    assert flags["phase_plan_touched"] is True
    assert flags["checklist_touched"] is True
    assert flags["docs_ready_for_work"] is True


def test_refresh_special_indexes_from_existing_roots_preserves_source_docs(tmp_path):
    project_root = tmp_path
    project_docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "demo"
    research_dir = project_docs_dir / "research"
    bugs_report = project_root / "docs" / "bugs" / "logic" / "2026-04-16_bug" / "report.md"
    sec_report = project_root / "docs" / "security" / "auth" / "2026-04-16_sec" / "report.md"
    review_report = project_docs_dir / "REVIEW_REPORT_phase0_20260416_1200.md"
    card_report = project_docs_dir / "AGENT_REPORT_CARD_Coder_phase0_20260416_1200.md"
    research_doc = research_dir / "RESEARCH_INDEX_LIFECYCLE.md"

    for path in (bugs_report, sec_report, review_report, card_report, research_doc):
        path.parent.mkdir(parents=True, exist_ok=True)
    bugs_report.write_text("# Bug\n", encoding="utf-8")
    sec_report.write_text("# Security\n", encoding="utf-8")
    review_report.write_text("# Review\n", encoding="utf-8")
    card_report.write_text("# Card\n", encoding="utf-8")
    research_doc.write_text("# Research\n", encoding="utf-8")

    source_before = {
        str(path): path.read_text(encoding="utf-8")
        for path in (bugs_report, sec_report, review_report, card_report, research_doc)
    }

    refreshed = asyncio.run(
        special_indexes_shared.refresh_special_indexes_from_roots(
            project_docs_dir=project_docs_dir,
            project_root=project_root,
            agent_id="test_agent",
            repo_root=project_root,
        )
    )

    assert Path(refreshed["research"]).name == "INDEX.md"
    assert Path(refreshed["bug"]).name == "INDEX.md"
    assert Path(refreshed["security"]).name == "INDEX.md"
    assert Path(refreshed["review"]).name == "REVIEW_INDEX.md"
    assert Path(refreshed["agent_card"]).name == "AGENT_CARDS_INDEX.md"

    for path_str, before_text in source_before.items():
        assert Path(path_str).read_text(encoding="utf-8") == before_text
