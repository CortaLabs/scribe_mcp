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


def test_inspect_preview_shape_matches_manifest_builder(tmp_path: Path) -> None:
    project = _project(tmp_path)
    payload = ie.build_export_payload(active_project=project)
    manifest = payload["downstream_ingestion_manifest"]
    assert manifest["schema_version"] == "v1"
    assert isinstance(manifest["records"], list)
    assert "eligible_count" in manifest


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
