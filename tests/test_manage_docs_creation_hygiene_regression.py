from pathlib import Path

import pytest

from scribe_mcp.doc_management.naming import normalize_research_doc_name
from scribe_mcp.doc_management.preflight import write_index_with_policy


def test_normalize_research_name_avoids_research_research_duplication() -> None:
    assert normalize_research_doc_name("research_RESEARCH_DUPLICATE.md") == "RESEARCH_DUPLICATE"


@pytest.mark.parametrize("suffix", [".invalid.backup", ".corrupted.backup"])
def test_write_index_removes_stale_index_backup_after_success(tmp_path: Path, suffix: str) -> None:
    research_dir = tmp_path / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "RESEARCH_A.md").write_text("# A\n", encoding="utf-8")
    index_path = research_dir / "INDEX.md"
    index_path.write_text("invalid body", encoding="utf-8")
    stale_backup = index_path.with_suffix(suffix)
    stale_backup.write_text("stale", encoding="utf-8")

    ok = write_index_with_policy(index_path, "# Research Documents Index\n", research_dir)
    assert ok is True
    assert index_path.exists()
    assert not stale_backup.exists()
