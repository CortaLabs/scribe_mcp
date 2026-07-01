from __future__ import annotations

import json
from pathlib import Path

from scribe_mcp.doc_management import intelligence_exports as ie


def _mk_doc(path: Path, frontmatter: str, body: str = "Body") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


def _project(tmp_path: Path) -> dict:
    root = tmp_path
    docs_dir = root / ".scribe" / "docs" / "dev_plans" / "p"
    a = docs_dir / "A.md"
    b = docs_dir / "B.md"
    _mk_doc(
        a,
        "\n".join([
            "id: doc-a",
            "doc_name: A",
            "doc_type: spec",
            "summary: Alpha",
            "status: ready",
            "quality_status: pass",
            "topology:",
            "  depends_on:",
            "    - B",
        ]),
    )
    _mk_doc(
        b,
        "\n".join([
            "id: doc-b",
            "doc_name: B",
            "doc_type: plan",
            "summary: Beta",
            "status: complete",
            "quality_status: pass",
        ]),
    )
    return {
        "name": "p",
        "root": str(root),
        "docs_dir": str(docs_dir),
        "docs": {"A": str(a), "B": str(b)},
    }


def test_export_artifacts_are_deterministic(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out1 = ie.write_export_artifacts(active_project=project)
    assert set(out1) == {"doc_topology", "work_topology", "downstream_ingestion_manifest", "knowledge_scribe_export"}
    assert Path(out1["knowledge_scribe_export"]).as_posix().endswith(".knowledge/scribe_exports/p.jsonl")
    snap1 = {k: Path(v).read_bytes() for k, v in out1.items()}
    out2 = ie.write_export_artifacts(active_project=project)
    snap2 = {k: Path(v).read_bytes() for k, v in out2.items()}
    assert snap1 == snap2


def test_manifest_rejects_scaffolded_and_missing_quality_and_sanitizes_path(tmp_path: Path) -> None:
    project = _project(tmp_path)
    c = Path(project["docs_dir"]) / "C.md"
    _mk_doc(
        c,
        "\n".join([
            "id: doc-c",
            "doc_name: C",
            "doc_type: note",
            "summary: Gamma",
            "status: in_progress",
        ]),
    )
    project["docs"]["C"] = str(c)

    payload = ie.build_export_payload(active_project=project)
    records = payload["downstream_ingestion_manifest"]["records"]
    c_record = next(r for r in records if r["doc_name"] == "C")
    assert c_record["eligible"] is False
    assert "REJECTED_SCAFFOLDED_OR_IN_PROGRESS" in c_record["rejection_codes"]
    assert "REJECTED_MISSING_QUALITY" in c_record["rejection_codes"]
    assert not c_record["path"].startswith("/")


def test_eligible_docs_export_safe_knowledge_jsonl_rows(tmp_path: Path) -> None:
    project = _project(tmp_path)
    out = ie.write_export_artifacts(active_project=project)
    rows = [
        json.loads(line)
        for line in Path(out["knowledge_scribe_export"]).read_text(encoding="utf-8").splitlines()
    ]
    assert {row["doc_name"] for row in rows} == {"A", "B"}
    row = next(item for item in rows if item["doc_name"] == "A")
    assert set(row) == {
        "chunk_id",
        "content",
        "title",
        "domain",
        "confidence",
        "project",
        "project_slug",
        "doc_id",
        "doc_name",
        "doc_type",
        "source_type",
        "path",
        "source_refs",
        "status",
        "lifecycle",
        "quality_status",
        "section_id",
        "section_title",
        "section_index",
        "citation_ref",
    }
    assert row["source_type"] == "scribe"
    assert row["project"] == "p"
    assert row["project_slug"] == "p"
    assert row["quality_status"] == "pass"
    assert row["path"] == ".scribe/docs/dev_plans/p/A.md"
    assert row["citation_ref"] == ".scribe/docs/dev_plans/p/A.md#document"
    assert row["source_refs"] == [".scribe/docs/dev_plans/p/A.md#document"]
    assert "Body" in row["content"]
    forbidden = {"repo_origin", "frontmatter", "actor", "grants", "bridge_token", "provider", "model"}
    assert forbidden.isdisjoint(row)
    assert all(str(value).startswith("/") is False for item in rows for value in item.values() if isinstance(value, str))


def test_eligible_doc_content_sanitizes_local_absolute_path_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path)
    a = Path(project["docs"]["A"])
    _mk_doc(
        a,
        "\n".join([
            "id: doc-a",
            "doc_name: A",
            "doc_type: spec",
            "summary: Alpha",
            "status: ready",
            "quality_status: pass",
            "topology:",
            "  depends_on:",
            "    - B",
        ]),
        body="\n".join([
            "Evidence includes /home/austin/projects/MCP_SPINE/knowledge_mcp/.scribe/docs/dev_plans/p/A.md.",
            "Report lives at /Users/austin/work/knowledge_mcp/docs/security/exposure/report.md;",
            r"Implementation reference C:\Users\Austin\repo\scribe_mcp\src\scribe_mcp\doc_management\intelligence_exports.py",
            "Scratch path /home/austin/private/token.txt should not leak its local parent.",
        ]),
    )

    out = ie.write_export_artifacts(active_project=project)
    rows = [
        json.loads(line)
        for line in Path(out["knowledge_scribe_export"]).read_text(encoding="utf-8").splitlines()
    ]
    content = next(row["content"] for row in rows if row["doc_name"] == "A")

    assert "/home/austin" not in content
    assert "/Users/austin" not in content
    assert "C:\\Users\\Austin" not in content
    assert "C:/Users/Austin" not in content
    assert ".scribe/docs/dev_plans/p/A.md" in content
    assert "docs/security/exposure/report.md" in content
    assert "src/scribe_mcp/doc_management/intelligence_exports.py" in content
    assert "token.txt" in content


def test_anchored_docs_export_one_row_per_stable_section_anchor(tmp_path: Path) -> None:
    project = _project(tmp_path)
    a = Path(project["docs"]["A"])
    _mk_doc(
        a,
        "\n".join([
            "id: doc-a",
            "doc_name: A",
            "doc_type: spec",
            "summary: Alpha",
            "status: ready",
            "quality_status: pass",
            "topology:",
            "  depends_on:",
            "    - B",
        ]),
        body="\n".join([
            "<!-- ID: findings -->",
            "## Findings",
            "Evidence belongs here.",
            "",
            "## Recommendations",
            "<!-- ID: recommendations -->",
            "Next steps belong here.",
        ]),
    )

    out = ie.write_export_artifacts(active_project=project)
    rows = [
        json.loads(line)
        for line in Path(out["knowledge_scribe_export"]).read_text(encoding="utf-8").splitlines()
    ]
    a_rows = [row for row in rows if row["doc_name"] == "A"]

    assert [row["section_id"] for row in a_rows] == ["findings", "recommendations"]
    assert [row["section_title"] for row in a_rows] == ["Findings", "Recommendations"]
    assert [row["section_index"] for row in a_rows] == [0, 1]
    assert [row["citation_ref"] for row in a_rows] == [
        ".scribe/docs/dev_plans/p/A.md#findings",
        ".scribe/docs/dev_plans/p/A.md#recommendations",
    ]
    assert [row["source_refs"] for row in a_rows] == [
        [".scribe/docs/dev_plans/p/A.md#findings"],
        [".scribe/docs/dev_plans/p/A.md#recommendations"],
    ]
    assert "Evidence belongs here." in a_rows[0]["content"]
    assert "Next steps belong here." in a_rows[1]["content"]
    assert "## Recommendations" not in a_rows[0]["content"]
    assert "<!-- ID:" not in a_rows[0]["content"]
    assert a_rows[1]["content"].startswith("## Recommendations\nNext steps")


def test_scaffold_quality_docs_are_rejected_and_not_exported(tmp_path: Path) -> None:
    project = _project(tmp_path)
    c = Path(project["docs_dir"]) / "C.md"
    _mk_doc(
        c,
        "\n".join([
            "id: doc-c",
            "doc_name: C",
            "doc_type: note",
            "summary: Gamma",
            "status: ready",
        ]),
        body="Replace this with real findings.",
    )
    project["docs"]["C"] = str(c)

    out = ie.write_export_artifacts(active_project=project)
    manifest = json.loads(Path(out["downstream_ingestion_manifest"]).read_text(encoding="utf-8"))
    c_record = next(r for r in manifest["records"] if r["doc_name"] == "C")
    exported = Path(out["knowledge_scribe_export"]).read_text(encoding="utf-8")
    assert c_record["eligible"] is False
    assert c_record["quality_status"] == "fail"
    assert "SCF_TEMPLATE_PROSE" in c_record["quality_summary"]["warning_codes"]
    assert "REJECTED_QUALITY_FAIL" in c_record["rejection_codes"]
    assert "doc-c" not in exported


def test_raw_progress_log_rejected_unless_curated_rollup(tmp_path: Path) -> None:
    project = _project(tmp_path)
    raw = Path(project["docs_dir"]) / "PROGRESS_LOG.md"
    _mk_doc(
        raw,
        "\n".join([
            "id: progress-raw",
            "doc_name: progress_log",
            "doc_type: progress_log",
            "summary: Raw log",
            "status: complete",
        ]),
        body="[INFO] [2026-07-01 UTC] [Agent: forge] raw progress line",
    )
    curated = Path(project["docs_dir"]) / "PROGRESS_ROLLUP.md"
    _mk_doc(
        curated,
        "\n".join([
            "id: progress-rollup",
            "doc_name: PROGRESS_ROLLUP",
            "doc_type: progress_log",
            "summary: Curated rollup",
            "status: complete",
            "curated_rollup: true",
        ]),
        body="Curated summary of project outcomes.",
    )
    project["docs"]["progress_log"] = str(raw)
    project["docs"]["PROGRESS_ROLLUP"] = str(curated)

    out = ie.write_export_artifacts(active_project=project)
    manifest = json.loads(Path(out["downstream_ingestion_manifest"]).read_text(encoding="utf-8"))
    export_text = Path(out["knowledge_scribe_export"]).read_text(encoding="utf-8")
    rows = [json.loads(line) for line in export_text.splitlines()]
    raw_record = next(r for r in manifest["records"] if r["doc_name"] == "progress_log")
    assert raw_record["eligible"] is False
    assert "REJECTED_RAW_PROGRESS_LOG" in raw_record["rejection_codes"]
    assert "raw progress line" not in export_text
    assert any(row["doc_name"] == "PROGRESS_ROLLUP" for row in rows)


def test_inspect_preview_shape_matches_manifest_builder(tmp_path: Path) -> None:
    project = _project(tmp_path)
    payload = ie.build_export_payload(active_project=project)
    manifest = payload["downstream_ingestion_manifest"]
    assert manifest["schema_version"] == "v1"
    assert isinstance(manifest["records"], list)
    assert "eligible_count" in manifest
    assert "knowledge_scribe_export_count" in manifest
    assert "knowledge_scribe_export_path" in manifest


def test_dangling_edge_rejection(tmp_path: Path) -> None:
    project = _project(tmp_path)
    a_path = Path(project["docs"]["A"])
    _mk_doc(
        a_path,
        "\n".join([
            "id: doc-a",
            "doc_name: A",
            "doc_type: spec",
            "summary: Alpha",
            "status: ready",
            "quality_status: pass",
            "topology:",
            "  depends_on:",
            "    - missing.md",
        ]),
    )
    payload = ie.build_export_payload(active_project=project)
    rec = next(r for r in payload["downstream_ingestion_manifest"]["records"] if r["doc_name"] == "A")
    assert "REJECTED_DANGLING_EDGE" in rec["rejection_codes"]


def test_export_artifacts_fallback_to_docs_dir_when_docs_mapping_missing(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project["docs"] = {}
    out1 = ie.write_export_artifacts(active_project=project)
    doc_topology_path = Path(out1["doc_topology"])
    manifest_path = Path(out1["downstream_ingestion_manifest"])
    doc_topology = json.loads(doc_topology_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert doc_topology["nodes"]
    assert manifest["records"]

    out2 = ie.write_export_artifacts(active_project=project)
    assert Path(out1["doc_topology"]).read_bytes() == Path(out2["doc_topology"]).read_bytes()
    assert Path(out1["downstream_ingestion_manifest"]).read_bytes() == Path(out2["downstream_ingestion_manifest"]).read_bytes()


def test_export_artifacts_merge_partial_docs_mapping_with_docs_dir_discovery(tmp_path: Path) -> None:
    project = _project(tmp_path)
    c = Path(project["docs_dir"]) / "sub" / "C.md"
    _mk_doc(
        c,
        "\n".join([
            "id: doc-c",
            "doc_name: C",
            "doc_type: note",
            "summary: Gamma",
            "status: ready",
            "quality_status: pass",
        ]),
    )
    project["docs"] = {"A": project["docs"]["A"]}

    payload = ie.build_export_payload(active_project=project)
    names = {node["doc_name"] for node in payload["doc_topology"]["nodes"]}
    assert names == {"A", "B", "C"}
    assert len(payload["downstream_ingestion_manifest"]["records"]) == 3


def test_export_artifacts_dedupes_duplicate_mapping_paths_with_registry_name_preference(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project["docs"] = {
        "AlphaCanonical": project["docs"]["A"],
        "AlphaAlias": project["docs"]["A"],
        "B": project["docs"]["B"],
    }

    payload = ie.build_export_payload(active_project=project)
    records = payload["downstream_ingestion_manifest"]["records"]
    alpha_records = [r for r in records if r["path"] and r["path"].endswith("A.md")]
    assert len(alpha_records) == 1
    assert alpha_records[0]["doc_name"] == "AlphaCanonical"
