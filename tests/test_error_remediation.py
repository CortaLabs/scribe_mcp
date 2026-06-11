"""Regression tests for P3 — structured error remediation envelope (D2).

Every enriched edit error carries {code, remediation, alternatives[]} so a
failed call is self-documenting (extends the quality_check warning shape).
Targets: DOC_NOT_FOUND, REPLACE_TEXT_NO_MATCH, PATCH_CONTEXT_NOT_FOUND,
SECTION_ANCHOR_MISSING / SECTION_ANCHOR_AMBIGUOUS.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.actions.edit import handle_edit_action
from scribe_mcp.doc_management.errors import (
    attach_remediation,
    document_anchor_ids,
    find_near_misses,
)
from scribe_mcp.doc_management.manager import (
    DocumentOperationError,
    _apply_unified_patch_smart,
    _replace_section,
    _replace_text_with_scope,
)

DOC = (
    "## Scope\n"
    "<!-- ID: scope -->\n"
    "scope body\n"
    "\n"
    "---\n"
    "## Findings\n"
    "<!-- ID: findings -->\n"
    "findings body\n"
)


def _envelope_of(exc_info) -> dict:
    extra = exc_info.value.extra
    assert isinstance(extra, dict)
    assert extra.get("remediation"), "remediation must be non-empty"
    assert isinstance(extra.get("alternatives"), list)
    return extra


def test_section_anchor_missing_lists_available_anchors():
    with pytest.raises(DocumentOperationError) as exc_info:
        _replace_section(DOC, "findngs", "content")  # typo
    envelope = _envelope_of(exc_info)
    assert envelope["code"] == "SECTION_ANCHOR_MISSING"
    assert "findings" in envelope["alternatives"]
    assert "scope" in envelope["remediation"] and "findings" in envelope["remediation"]
    assert "Closest match: 'findings'" in envelope["remediation"]


def test_section_anchor_ambiguous_envelope():
    doc = DOC + "<!-- ID: scope -->\nduplicate\n"
    with pytest.raises(DocumentOperationError) as exc_info:
        _replace_section(doc, "scope", "content")
    envelope = _envelope_of(exc_info)
    assert envelope["code"] == "SECTION_ANCHOR_AMBIGUOUS"
    assert "replace_range" in envelope["alternatives"]


def test_replace_text_no_match_envelope_with_near_line():
    with pytest.raises(DocumentOperationError) as exc_info:
        _replace_text_with_scope(
            DOC,
            find_text="findings bodyy",
            replace_text="x",
            match_mode="literal",
            replace_all=True,
            scope=None,
            allow_no_match=False,
        )
    envelope = _envelope_of(exc_info)
    assert envelope["code"] == "REPLACE_TEXT_NO_MATCH"
    assert envelope["alternatives"], "should carry the nearest-line hint"
    assert "findings body" in envelope["alternatives"][0]


def test_patch_context_not_found_envelope():
    patch = (
        "--- before\n"
        "+++ after\n"
        "@@ -1,3 +1,3 @@\n"
        " totally absent context\n"
        "-old line\n"
        "+new line\n"
    )
    with pytest.raises(DocumentOperationError) as exc_info:
        _apply_unified_patch_smart(DOC, patch)
    envelope = _envelope_of(exc_info)
    assert envelope["code"] in {"PATCH_CONTEXT_NOT_FOUND", "PATCH_DELETE_MISMATCH"}
    assert "structured" in envelope["remediation"]


def test_doc_not_found_response_carries_near_miss():
    class _Helper:
        @staticmethod
        def apply_context_payload(response, _context):
            return response

    async def _unused(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("should not be reached")

    result = asyncio.run(
        handle_edit_action(
            action="replace_section",
            project={"name": "t", "root": "/tmp", "docs": {"ARCHITECTURE_GUIDE": "/tmp/a.md"}},
            doc_name="ARCHITECTURE_GIDE",  # typo
            doc_category="general",
            section="x",
            content="y",
            patch=None,
            patch_source_hash=None,
            edit=None,
            patch_mode=None,
            start_line=None,
            end_line=None,
            template=None,
            metadata={},
            dry_run=False,
            backend=None,
            agent_id="t",
            helper=_Helper(),
            context=None,
            execution_context=None,
            deprecation_warning=None,
            apply_doc_change=_unused,
            get_or_create_storage_project=_unused,
            append_entry=_unused,
            normalize_metadata_with_healing=lambda m: (dict(m or {}), [], []),
            index_doc_for_vector=_unused,
            vector_indexing_enabled=lambda: False,
            get_index_updater_for_path=lambda **_: None,
            project_registry=SimpleNamespace(record_doc_update=lambda *a, **k: None),
            server_module=SimpleNamespace(),
            logger=SimpleNamespace(warning=lambda *a, **k: None),
        )
    )
    assert result["ok"] is False
    assert result["code"] == "DOC_NOT_FOUND"
    assert result["alternatives"] == ["ARCHITECTURE_GUIDE"]
    assert "Did you mean 'ARCHITECTURE_GUIDE'?" in result["remediation"]


def test_helpers_are_deterministic():
    assert find_near_misses("findngs", ["findings", "scope"]) == ["findings"]
    assert document_anchor_ids(DOC) == ["scope", "findings"]
    response = attach_remediation(
        {"ok": False, "error": "X: boom"},
        DocumentOperationError("X: boom", extra={"code": "X", "remediation": "do y", "alternatives": []}),
    )
    assert response["code"] == "X" and response["remediation"] == "do y"
    # exceptions without an envelope leave the response untouched
    plain = attach_remediation({"ok": False, "error": "boom"}, ValueError("boom"))
    assert "remediation" not in plain
