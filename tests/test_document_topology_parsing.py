from __future__ import annotations

from pathlib import Path

from scribe_mcp.doc_management.actions.query import inspect_document_sections_from_text
from scribe_mcp.doc_management.topology import (
    detect_hard_dependency_cycles,
    normalize_topology_edges,
    resolve_topology_target,
)


def test_topology_normalizes_string_and_structured_edges(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    target = docs_dir / "TARGET.md"
    target.write_text("# Target\n## Section A\n", encoding="utf-8")

    edges = normalize_topology_edges(
        source_doc_id="source",
        source_doc_path=docs_dir / "SOURCE.md",
        edge_map={
            "depends_on": ["TARGET.md#section-a"],
            "supports": [{"target": "TARGET.md", "relation": "soft", "note": "context"}],
            "related_docs": ["TARGET.md"],
        },
        docs_dir=docs_dir,
        project_root=tmp_path,
        registered_docs={"target": target},
    )

    assert len(edges) == 3
    assert all(edge["edge_id"] for edge in edges)
    assert edges[0]["kind"] == "depends_on"
    assert edges[0]["target_anchor"] == "section-a"
    assert edges[1]["note"] == "context"


def test_topology_rejects_outside_repo_and_cross_project(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "p"
    docs_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")

    edges = normalize_topology_edges(
        source_doc_id="source",
        source_doc_path=docs_dir / "SOURCE.md",
        edge_map={"related_docs": [str(outside), "../foreign.md"]},
        docs_dir=docs_dir,
        project_root=project_root,
        registered_docs={},
    )

    assert edges[0]["state"] == "rejected_outside_repo"
    assert edges[0]["target_resolved"] is False
    assert edges[1]["state"] == "rejected_cross_project"


def test_topology_cycle_detection_hard_edges_only() -> None:
    edges = [
        {"kind": "depends_on", "source_doc_id": "a", "target_doc_id": "b"},
        {"kind": "blocked_by", "source_doc_id": "b", "target_doc_id": "a"},
        {"kind": "supports", "source_doc_id": "c", "target_doc_id": "d"},
        {"kind": "supports", "source_doc_id": "d", "target_doc_id": "c"},
    ]

    cycles = detect_hard_dependency_cycles(edges)
    assert cycles == [["a", "b", "a"]]


def test_topology_fallback_matches_section_inspection_anchor_priority(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    target = docs_dir / "TARGET.md"
    target_text = "# Heading First\n\n<!-- ID: canonical_anchor -->\n\n## Later Section\n"
    target.write_text(target_text, encoding="utf-8")

    section_payload = inspect_document_sections_from_text(target_text)
    expected_anchor = section_payload["sections"][0]["id"]

    _, _, resolved_anchor, _, state = resolve_topology_target(
        target_ref="TARGET.md",
        docs_dir=docs_dir,
        project_root=tmp_path,
        registered_docs={"target": target},
    )

    assert state == "ok"
    assert expected_anchor == "canonical_anchor"
    assert resolved_anchor == expected_anchor
