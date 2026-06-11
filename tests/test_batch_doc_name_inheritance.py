"""Regression tests for P1.1 — batch operations inherit the top-level doc_name.

Live-reproduced defect (RESEARCH_AGENT_FRICTION_AUDIT F4): a batch whose
operations omitted doc_name dispatched each op with doc_name=None and failed
with "DOC_NOT_FOUND: doc_name 'None' is not registered" even when the batch
call itself supplied doc_name.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.actions.batch import (
    _inherit_doc_name,
    handle_batch_action,
)


class _Helper:
    @staticmethod
    def apply_context_payload(response, _context):
        return response

    @staticmethod
    def error_response(message):
        return {"ok": False, "error": message}


def _run_batch(operations, doc_name):
    captured = []

    async def fake_manage_docs(**kwargs):
        captured.append(kwargs)
        return {"ok": True, "action": kwargs.get("action")}

    with patch("scribe_mcp.tools.manage_docs.manage_docs", fake_manage_docs):
        result = asyncio.run(
            handle_batch_action(
                action="batch",
                project={"name": "test"},
                metadata={"operations": operations},
                dry_run=False,
                helper=_Helper(),
                context=None,
                doc_name=doc_name,
            )
        )
    return result, captured


def test_ops_without_doc_name_inherit_batch_level():
    result, captured = _run_batch(
        [
            {"action": "replace_range", "start_line": 5, "end_line": 5, "content": "x"},
            {"action": "replace_range", "start_line": 2, "end_line": 2, "content": "y"},
        ],
        doc_name="PARENT_DOC",
    )
    assert result["ok"] is True
    assert len(captured) == 2
    assert all(call["doc_name"] == "PARENT_DOC" for call in captured)


def test_explicit_op_doc_name_overrides_batch_level():
    result, captured = _run_batch(
        [
            {"action": "append", "doc_name": "OTHER_DOC", "content": "x"},
            {"action": "append", "content": "y"},
        ],
        doc_name="PARENT_DOC",
    )
    assert result["ok"] is True
    assert captured[0]["doc_name"] == "OTHER_DOC"
    assert captured[1]["doc_name"] == "PARENT_DOC"


def test_op_doc_key_blocks_inheritance():
    ops = [{"action": "append", "doc": "ALIAS_DOC", "content": "x"}]
    merged = _inherit_doc_name(ops, "PARENT_DOC")
    assert "doc_name" not in merged[0]
    assert merged[0]["doc"] == "ALIAS_DOC"


def test_no_batch_doc_name_leaves_ops_untouched():
    ops = [{"action": "append", "content": "x"}]
    merged = _inherit_doc_name(ops, None)
    assert merged[0] is ops[0]


def test_inheritance_does_not_mutate_caller_operations():
    ops = [{"action": "append", "content": "x"}]
    _inherit_doc_name(ops, "PARENT_DOC")
    assert "doc_name" not in ops[0]
