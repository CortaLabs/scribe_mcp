from pathlib import Path

from scribe_mcp.doc_management import intelligence_workflows as iw


def _project(tmp_path: Path) -> dict:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    a = docs_dir / "A.md"
    a.write_text("""---\nsummary: a\ntopology:\n  depends_on:\n    - missing.md\n---\nA\n""", encoding="utf-8")
    b = docs_dir / "B.md"
    b.write_text("""---\nid: b-id\nsummary: b\nstatus: scaffolded\n---\nB\n""", encoding="utf-8")
    return {
        "root": str(tmp_path),
        "docs_dir": str(docs_dir),
        "docs": {"A": str(a), "B": str(b)},
        "name": "p",
    }


def test_topology_scan_read_only_and_reports_unresolved(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = iw.topology_scan(active_project=project)
    assert out["ok"] is True
    assert out["read_only"] is True
    dangling = out["snapshot"]["dangling_targets"]
    assert dangling and dangling[0]["proof"]["code"] == "UNRESOLVED_TARGET"


def test_metadata_scan_reports_missing_id(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = iw.metadata_scan(active_project=project)
    codes = {f["code"] for f in out["findings"]}
    assert "MISSING_ID" in codes
    assert "MISSING_DOC_TYPE" in codes
    assert "MISSING_DOC_NAME" in codes


def test_metadata_scan_reports_invalid_id_with_proof(tmp_path: Path) -> None:
    project = _project(tmp_path)
    target = Path(project["docs"]["A"])
    target.write_text(
        """---
id: Bad ID
doc_type: research
doc_name: A
summary: a
status: scaffolded
---
A
""",
        encoding="utf-8",
    )
    out = iw.metadata_scan(active_project=project)
    invalid = [f for f in out["findings"] if f["code"] == "INVALID_ID"]
    assert invalid
    assert invalid[0]["proof"]["field"] == "id"
    assert invalid[0]["proof"]["value"] == "Bad ID"


def test_metadata_repair_invalid_mode_rejected(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = iw.metadata_repair(active_project=project, mode="bad")
    assert out["ok"] is False
    assert out["rejection_code"] == "INVALID_REPAIR_MODE"


def test_metadata_repair_report_only_no_writes(tmp_path: Path) -> None:
    project = _project(tmp_path)
    before = Path(project["docs"]["A"]).read_text(encoding="utf-8")
    out = iw.metadata_repair(active_project=project, mode="report_only")
    after = Path(project["docs"]["A"]).read_text(encoding="utf-8")
    assert out["ok"] is True
    assert out["writes_performed"] is False
    assert before == after
    assert any(item["code"] == "MISSING_STATUS" and item["proposal"] == "set_scaffolded" for item in out["repair_plan"])


def test_metadata_repair_safe_mutates_deterministic_and_sets_scaffolded(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = iw.metadata_repair(active_project=project, mode="repair_safe")
    text = Path(project["docs"]["A"]).read_text(encoding="utf-8")
    assert out["ok"] is True
    assert out["writes_performed"] is True
    assert out["mutations"]
    assert "status: scaffolded" in text
    assert "status: draft" not in text


def test_metadata_repair_safe_preserves_structured_topology(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = iw.metadata_repair(active_project=project, mode="repair_safe")
    assert out["ok"] is True
    parsed = iw.parse_frontmatter(Path(project["docs"]["A"]).read_text(encoding="utf-8"))
    topology = parsed.frontmatter_data.get("topology")
    assert isinstance(topology, dict)
    assert topology.get("depends_on") == ["missing.md"]


def test_metadata_repair_assisted_returns_plan_only_no_writes(tmp_path: Path) -> None:
    project = _project(tmp_path)
    before = Path(project["docs"]["A"]).read_text(encoding="utf-8")
    out = iw.metadata_repair(active_project=project, mode="repair_assisted")
    after = Path(project["docs"]["A"]).read_text(encoding="utf-8")
    assert out["ok"] is True
    assert out["writes_performed"] is False
    assert out["mutations"] == []
    assert before == after
    assert any(item["code"] == "MISSING_STATUS" and item["proposal"] == "set_scaffolded" and item["requires_review"] is True for item in out["repair_plan"])


def test_stale_cleanup_scan_recommendation_only(tmp_path: Path) -> None:
    project = _project(tmp_path)
    empty = Path(project["docs_dir"]) / "empty.md"
    empty.write_text("", encoding="utf-8")
    project["docs"]["empty"] = str(empty)
    out = iw.stale_cleanup_scan(active_project=project)
    assert out["read_only"] is True
    recs = out["recommendations"]
    assert any(r.get("rejection_code") == "DESTRUCTIVE_CLEANUP_REQUIRES_CONFIRM" for r in recs)
