"""Regression tests for BUG-2026-06-11-0003.

The manage_docs edit pipeline auto-logs every mutation to the doc_updates log
via append_entry(log_type="doc_updates"). The doc_updates log definition in
config/log_config.json declares metadata_requirements ["doc", "section",
"action"]. These tests assert the auto-log payloads built inside
handle_edit_action satisfy that contract with a valid status value, so the
internal audit trail can never silently regress into the ~37k
"Log requirements not met: Missing metadata for log entry: doc" error stream
observed in production telemetry.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.doc_management.actions.edit import handle_edit_action
from scribe_mcp.utils.parameter_validator import ToolValidator

VALID_STATUSES = {"info", "success", "warn", "error", "bug", "plan"}

_LOG_CONFIG_PATH = (
    Path(__file__).parent.parent / "src" / "scribe_mcp" / "config" / "log_config.json"
)


def _doc_updates_definition() -> dict:
    config = json.loads(_LOG_CONFIG_PATH.read_text())
    logs = config.get("logs", config)
    definition = logs["doc_updates"]
    assert "metadata_requirements" in definition
    return definition


class _CapturingAppendEntry:
    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


class _Helper:
    @staticmethod
    def apply_context_payload(response, _context):
        return response


def _make_change(content_written: str, extra: dict, path: str) -> SimpleNamespace:
    return SimpleNamespace(
        success=True,
        path=path,
        before_hash="a" * 64,
        after_hash="b" * 64,
        diff_preview="",
        content_written=content_written,
        extra=extra,
        verification_passed=True,
        file_size_before=0,
        file_size_after=len(content_written),
    )


def _run_edit_action(tmp_path: Path, *, preview_change, final_change, metadata):
    append_entry = _CapturingAppendEntry()

    async def apply_doc_change(_project, **kwargs):
        if kwargs.get("dry_run"):
            return preview_change
        return final_change

    async def get_or_create_storage_project(_backend, _project):  # pragma: no cover
        raise AssertionError("backend is None; storage path must not run")

    async def index_doc_for_vector(**_kwargs):
        return None

    project = {
        "name": "autolog-contract-test",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path / "docs"),
        "docs": {"TEST_DOC": str(tmp_path / "docs" / "TEST_DOC.md")},
    }

    result = asyncio.run(
        handle_edit_action(
            action="replace_section",
            project=project,
            doc_name="TEST_DOC",
            doc_category="general",
            section="findings",
            content="updated content",
            patch=None,
            patch_source_hash=None,
            edit=None,
            patch_mode=None,
            start_line=None,
            end_line=None,
            template=None,
            metadata=metadata,
            dry_run=False,
            backend=None,
            agent_id="test-agent",
            helper=_Helper(),
            context=None,
            execution_context=None,
            deprecation_warning=None,
            apply_doc_change=apply_doc_change,
            get_or_create_storage_project=get_or_create_storage_project,
            append_entry=append_entry,
            normalize_metadata_with_healing=lambda meta: (dict(meta or {}), [], []),
            index_doc_for_vector=index_doc_for_vector,
            vector_indexing_enabled=lambda: False,
            get_index_updater_for_path=lambda **_kwargs: None,
            project_registry=SimpleNamespace(record_doc_update=lambda *a, **k: None),
            server_module=SimpleNamespace(),
            logger=SimpleNamespace(warning=lambda *a, **k: None),
        )
    )
    return result, append_entry.calls


def _assert_doc_updates_contract(call: dict) -> None:
    assert call["log_type"] == "doc_updates"
    assert call["status"] in VALID_STATUSES, f"invalid status {call['status']!r}"
    error = ToolValidator.validate_metadata_requirements(
        _doc_updates_definition(), call["meta"]
    )
    assert error is None, f"doc_updates auto-log violates its own contract: {error}"


def test_edit_autolog_meets_doc_updates_requirements(tmp_path):
    doc_path = tmp_path / "docs" / "TEST_DOC.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("# Test Doc\ncontent\n")

    change = _make_change("# Test Doc\ncontent\n", {}, str(doc_path))
    result, calls = _run_edit_action(
        tmp_path, preview_change=change, final_change=change, metadata={}
    )

    assert result["ok"] is True
    doc_update_calls = [c for c in calls if c.get("log_type") == "doc_updates"]
    assert len(doc_update_calls) == 1, "edit must emit exactly one doc_updates entry"
    _assert_doc_updates_contract(doc_update_calls[0])
    assert doc_update_calls[0]["meta"]["doc"] == "TEST_DOC"
    assert doc_update_calls[0]["meta"]["section"] == "findings"
    assert doc_update_calls[0]["meta"]["action"] == "replace_section"


def test_blocked_readiness_autolog_meets_doc_updates_requirements(tmp_path):
    readiness_content = "---\nstatus: done\n---\n# Test Doc\n[TODO placeholder]\n"
    blocking_warning = {
        "code": "SCF_PLACEHOLDER_BRACKET",
        "blocking": True,
        "message": "Bracketed placeholder found.",
        "location": {"line": 4},
        "excerpt": "[TODO placeholder]",
        "suggested_repair": "Replace placeholder.",
    }
    preview = _make_change(
        readiness_content,
        {"scaffold_quality_warnings": [blocking_warning]},
        str(tmp_path / "docs" / "TEST_DOC.md"),
    )

    result, calls = _run_edit_action(
        tmp_path, preview_change=preview, final_change=preview, metadata={}
    )

    assert result["ok"] is False
    assert result["code"] == "DOC_NOT_DONE_SCAFFOLD_QUALITY"
    doc_update_calls = [c for c in calls if c.get("log_type") == "doc_updates"]
    assert len(doc_update_calls) == 1, "blocked readiness must emit one doc_updates entry"
    _assert_doc_updates_contract(doc_update_calls[0])
    assert doc_update_calls[0]["meta"]["doc"] == "TEST_DOC"
    assert doc_update_calls[0]["meta"]["reason_code"] == "DOC_NOT_DONE_SCAFFOLD_QUALITY"
