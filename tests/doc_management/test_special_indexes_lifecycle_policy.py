import asyncio
import tempfile
from pathlib import Path

from scribe_mcp.doc_management import special_indexes as special_indexes_shared


def test_explicit_security_index_entrypoint_writes_security_heading():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        security_root = project_root / "docs" / "security"
        report_dir = security_root / "auth" / "2026-01-20_token_leak"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.md").write_text("# Security Report\n")

        asyncio.run(
            special_indexes_shared.update_security_index(
                security_root,
                agent_id="test_agent",
                repo_root=None,
            )
        )

        index_text = (security_root / "INDEX.md").read_text(encoding="utf-8")
        assert "# Security Reports Index" in index_text
        assert "## Security Statistics" in index_text
        assert "auth/2026-01-20_token_leak" in index_text


def test_index_families_share_preflight_write_policy(monkeypatch):
    calls = []

    def _capture_write_policy(index_path: Path, content: str, doc_dir: Path | None = None) -> bool:
        calls.append((index_path.name, doc_dir))
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(content, encoding="utf-8")
        return True

    monkeypatch.setattr(
        special_indexes_shared.preflight_shared,
        "write_index_with_policy",
        _capture_write_policy,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        docs_dir = root / ".scribe" / "docs" / "dev_plans" / "p1"
        research_dir = docs_dir / "research"
        bugs_dir = root / "docs" / "bugs"
        security_dir = root / "docs" / "security"
        research_dir.mkdir(parents=True, exist_ok=True)
        (research_dir / "RESEARCH_A.md").write_text("# Research\n")

        bug_report = bugs_dir / "logic" / "2026-01-20_bug"
        bug_report.mkdir(parents=True, exist_ok=True)
        (bug_report / "report.md").write_text("# Bug\n")

        sec_report = security_dir / "auth" / "2026-01-20_sec"
        sec_report.mkdir(parents=True, exist_ok=True)
        (sec_report / "report.md").write_text("# Security\n")

        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "REVIEW_REPORT_phase0_2026-01-20_1200.md").write_text("# Review\n")
        (docs_dir / "AGENT_REPORT_CARD_Coder_phase0_20260120_1200.md").write_text("# Card\n")

        asyncio.run(special_indexes_shared.update_research_index(research_dir, "test_agent", repo_root=None))
        asyncio.run(special_indexes_shared.update_bug_index(bugs_dir, "test_agent", repo_root=None))
        asyncio.run(
            special_indexes_shared.update_security_index(security_dir, "test_agent", repo_root=None)
        )
        asyncio.run(special_indexes_shared.update_review_index(docs_dir, "test_agent", repo_root=None))
        asyncio.run(
            special_indexes_shared.update_agent_card_index(docs_dir, "test_agent", repo_root=None)
        )

    written_index_names = {name for name, _ in calls}
    assert "INDEX.md" in written_index_names
    assert "REVIEW_INDEX.md" in written_index_names
    assert "AGENT_CARDS_INDEX.md" in written_index_names
    assert len(calls) == 5
    assert all(doc_dir is not None for _, doc_dir in calls)
