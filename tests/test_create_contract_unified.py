"""Regression tests for P2 — unified create contract (D1).

Pins the contract: empty create is legal for generic doc types, a sections
payload produces ANCHORED sections (stable replace_section targets, listed
in editable_sections), and inspection completeness matches the file truth.
The historical CREATE_DOC_MISSING_CONTENT divergence must never return.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.actions.query import inspect_document_sections_from_text
from scribe_mcp.doc_management.manager import _replace_section, apply_doc_change


def _project(tmp_path: Path) -> dict:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "name": "create-contract-test",
        "root": str(tmp_path),
        "docs_dir": str(docs_dir),
        "docs": {},
    }


def _create(project: dict, doc_name: str, *, content=None, metadata=None):
    return asyncio.run(
        apply_doc_change(
            project,
            doc_name=doc_name,
            doc_category="general",
            action="create_doc",
            section=None,
            content=content,
            template=None,
            metadata=metadata if metadata is not None else {},
            dry_run=False,
        )
    )


def test_empty_create_succeeds(tmp_path):
    project = _project(tmp_path)
    change = _create(project, "EMPTY_DOC")
    assert change.success
    assert change.path and Path(change.path).exists()


def test_empty_create_with_spec_like_metadata_succeeds(tmp_path):
    """The historical CREATE_DOC_MISSING_CONTENT rejection must not return."""
    project = _project(tmp_path)
    change = _create(
        project,
        "SPEC_DOC",
        metadata={"summary": "problem definition", "tags": ["spec"]},
    )
    assert change.success


def test_sections_payload_produces_anchored_sections(tmp_path):
    project = _project(tmp_path)
    change = _create(
        project,
        "SECTIONED_DOC",
        metadata={
            "sections": [
                {"title": "Problem Statement", "content": "the problem"},
                {"title": "Goals", "content": "the goals"},
                {"title": "Open Questions", "content": ""},
            ]
        },
    )
    assert change.success
    text = Path(change.path).read_text()
    payload = inspect_document_sections_from_text(text)
    assert payload["section_source"] == "anchors"
    ids = [s["id"] for s in payload["sections"]]
    assert ids == ["problem_statement", "goals", "open_questions"]


def test_section_id_override_respected(tmp_path):
    project = _project(tmp_path)
    change = _create(
        project,
        "OVERRIDE_DOC",
        metadata={"sections": [{"title": "Findings", "id": "custom_findings", "content": "x"}]},
    )
    text = Path(change.path).read_text()
    assert "<!-- ID: custom_findings -->" in text


def test_created_sections_are_replace_section_targets(tmp_path):
    """create → replace_section round-trip with no list_sections call needed."""
    project = _project(tmp_path)
    change = _create(
        project,
        "ROUNDTRIP_DOC",
        metadata={"sections": [{"title": "Findings", "content": "placeholder"}]},
    )
    text = Path(change.path).read_text()
    updated = _replace_section(text, "findings", "real findings content")
    assert "real findings content" in updated
    assert "placeholder" not in updated


def test_inspection_matches_file_truth_for_contentful_create(tmp_path):
    project = _project(tmp_path)
    change = _create(
        project,
        "CONTENT_DOC",
        content="# Title\n<!-- ID: alpha -->\nbody\n## Beta\n<!-- ID: beta -->\nmore\n",
    )
    text = Path(change.path).read_text()
    payload = inspect_document_sections_from_text(text)
    ids = {s["id"] for s in payload["sections"]}
    assert {"alpha", "beta"} <= ids
