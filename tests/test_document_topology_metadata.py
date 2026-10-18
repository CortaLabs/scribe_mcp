from scribe_mcp.doc_management.lifecycle import derive_canonical_doc_type, normalize_canonical_status


def test_derive_canonical_doc_type_prefers_intended_doc_type() -> None:
    assert derive_canonical_doc_type("custom", "phase_plan") == "phase_plan"
    assert derive_canonical_doc_type("review", None) == "review"


def test_normalize_canonical_status_handles_aliases() -> None:
    assert normalize_canonical_status("draft") == "scaffolded"
    assert normalize_canonical_status("active") == "in_progress"
    assert normalize_canonical_status("done") == "complete"
