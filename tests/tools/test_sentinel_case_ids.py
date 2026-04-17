from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scribe_mcp.tools.sentinel_tools import _next_case_id_for_project, open_bug, open_security


def _make_execution_context(mode: str = "project") -> MagicMock:
    ctx = MagicMock()
    ctx.mode = mode
    return ctx


def _make_append_entry_result(progress_log: Path, **extra: Any) -> Dict[str, Any]:
    base = {
        "ok": True,
        "id": "test-entry-id",
        "path": str(progress_log),
        "paths": [str(progress_log)],
        "project_name": "test-project",
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_open_bug_repeated_allocates_unique_case_ids(tmp_path: Path) -> None:
    ctx = _make_execution_context("project")
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")

    mock_append = AsyncMock(return_value=_make_append_entry_result(progress_log))
    mock_manage = AsyncMock(
        side_effect=[
            {"ok": True, "path": "/tmp/bug-1.md"},
            {"ok": True, "path": "/tmp/bug-2.md"},
        ]
    )

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        first = await open_bug(
            agent="test-agent",
            title="Repeated bug A",
            symptoms="symptom A",
            category="runtime",
        )
        second = await open_bug(
            agent="test-agent",
            title="Repeated bug B",
            symptoms="symptom B",
            category="runtime",
        )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["case_id"] != second["case_id"]
    assert first["case_id"].endswith("0001")
    assert second["case_id"].endswith("0002")
    assert first["bug_report"] != second["bug_report"]
    assert mock_manage.call_args_list[0].kwargs["metadata"]["slug"] == first["case_id"]
    assert mock_manage.call_args_list[1].kwargs["metadata"]["slug"] == second["case_id"]


@pytest.mark.asyncio
async def test_open_security_repeated_allocates_unique_case_ids(tmp_path: Path) -> None:
    ctx = _make_execution_context("project")
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")

    mock_append = AsyncMock(return_value=_make_append_entry_result(progress_log))
    mock_manage = AsyncMock(
        side_effect=[
            {"ok": True, "path": "/tmp/sec-1.md"},
            {"ok": True, "path": "/tmp/sec-2.md"},
        ]
    )

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        first = await open_security(
            agent="test-agent",
            title="Repeated security A",
            symptoms="symptom A",
            category="auth",
        )
        second = await open_security(
            agent="test-agent",
            title="Repeated security B",
            symptoms="symptom B",
            category="auth",
        )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["case_id"] != second["case_id"]
    assert first["case_id"].endswith("0001")
    assert second["case_id"].endswith("0002")
    assert first["security_report"] != second["security_report"]
    assert mock_manage.call_args_list[0].kwargs["metadata"]["slug"] == first["case_id"]
    assert mock_manage.call_args_list[1].kwargs["metadata"]["slug"] == second["case_id"]


@pytest.mark.asyncio
async def test_open_bug_and_security_mixed_do_not_collide_or_regress_doc_creation(tmp_path: Path) -> None:
    ctx = _make_execution_context("project")
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")

    mock_append = AsyncMock(return_value=_make_append_entry_result(progress_log))
    mock_manage = AsyncMock(return_value={"ok": True, "path": "/tmp/report.md"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        bug = await open_bug(
            agent="test-agent",
            title="Mixed bug",
            symptoms="bug symptom",
            category="runtime",
        )
        sec = await open_security(
            agent="test-agent",
            title="Mixed security",
            symptoms="security symptom",
            category="auth",
        )
        bug_2 = await open_bug(
            agent="test-agent",
            title="Mixed bug 2",
            symptoms="bug symptom 2",
            category="runtime",
        )
        sec_2 = await open_security(
            agent="test-agent",
            title="Mixed security 2",
            symptoms="security symptom 2",
            category="auth",
        )

    ids = {bug["case_id"], sec["case_id"], bug_2["case_id"], sec_2["case_id"]}
    assert len(ids) == 4
    assert bug["case_id"].startswith("BUG-")
    assert bug_2["case_id"].startswith("BUG-")
    assert sec["case_id"].startswith("SEC-")
    assert sec_2["case_id"].startswith("SEC-")
    assert bug["case_id"].endswith("0001")
    assert bug_2["case_id"].endswith("0002")
    assert sec["case_id"].endswith("0001")
    assert sec_2["case_id"].endswith("0002")

    # Ensure each returned case_id is used for document creation metadata.
    created_slugs = [call.kwargs["metadata"]["slug"] for call in mock_manage.call_args_list]
    assert bug["case_id"] in created_slugs
    assert bug_2["case_id"] in created_slugs
    assert sec["case_id"] in created_slugs
    assert sec_2["case_id"] in created_slugs


def test_next_case_id_for_project_raises_when_project_dir_unresolvable(tmp_path: Path) -> None:
    missing_log = tmp_path / "missing" / "PROGRESS_LOG.md"
    result = _make_append_entry_result(missing_log)
    with pytest.raises(RuntimeError, match="unable to resolve project directory"):
        _next_case_id_for_project("BUG", result)


def test_next_case_id_for_project_raises_on_lock_timeout(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with patch("scribe_mcp.tools.sentinel_tools.os.open", side_effect=FileExistsError), patch(
        "scribe_mcp.tools.sentinel_tools.time.monotonic", side_effect=[0.0, 3.0]
    ):
        with pytest.raises(TimeoutError, match="timeout acquiring counter lock"):
            _next_case_id_for_project("BUG", result)


def test_next_case_id_for_project_raises_on_lock_acquisition_exception(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with patch("scribe_mcp.tools.sentinel_tools.os.open", side_effect=OSError("boom")):
        with pytest.raises(RuntimeError, match="lock acquisition error"):
            _next_case_id_for_project("BUG", result)


def test_next_case_id_for_project_raises_on_malformed_persisted_counter_state(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    counter_file = tmp_path / ".sentinel_case_id_counters.json"
    counter_file.write_text("{", encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with pytest.raises(RuntimeError, match="unable to read persisted counter state"):
        _next_case_id_for_project("BUG", result)


def test_next_case_id_for_project_raises_when_today_bucket_is_not_object(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counter_file = tmp_path / ".sentinel_case_id_counters.json"
    counter_file.write_text(f'{{"{today}": 7}}', encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with pytest.raises(RuntimeError, match="expected object at date bucket"):
        _next_case_id_for_project("BUG", result)


def test_next_case_id_for_project_raises_when_bug_leaf_is_malformed(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counter_file = tmp_path / ".sentinel_case_id_counters.json"
    counter_file.write_text(f'{{"{today}": {{"BUG": "bad", "SEC": 1}}}}', encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with pytest.raises(RuntimeError, match="expected non-negative integer"):
        _next_case_id_for_project("BUG", result)


def test_next_case_id_for_project_raises_when_sec_leaf_is_malformed(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counter_file = tmp_path / ".sentinel_case_id_counters.json"
    counter_file.write_text(f'{{"{today}": {{"BUG": 1, "SEC": false}}}}', encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with pytest.raises(RuntimeError, match="expected non-negative integer"):
        _next_case_id_for_project("SEC", result)


def test_next_case_id_for_project_raises_on_unreadable_persisted_counter_state(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")
    counter_file = tmp_path / ".sentinel_case_id_counters.json"
    counter_file.write_text("{}", encoding="utf-8")
    result = _make_append_entry_result(progress_log)

    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        with pytest.raises(RuntimeError, match="unable to read persisted counter state"):
            _next_case_id_for_project("BUG", result)


@pytest.mark.asyncio
async def test_open_bug_fails_closed_when_case_id_allocation_fails(tmp_path: Path) -> None:
    ctx = _make_execution_context("project")
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")

    mock_append = AsyncMock(return_value=_make_append_entry_result(progress_log))
    mock_manage = AsyncMock(return_value={"ok": True, "path": "/tmp/bug.md"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), patch(
        "scribe_mcp.tools.append_entry.append_entry", mock_append
    ), patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage), patch(
        "scribe_mcp.tools.sentinel_tools._next_case_id_for_project",
        side_effect=TimeoutError("case-id allocation failed: timeout acquiring counter lock"),
    ):
        result = await open_bug(
            agent="test-agent",
            title="Allocator failure bug",
            symptoms="symptom",
            category="runtime",
        )

    assert result["ok"] is False
    assert "Failed to allocate BUG case ID" in result["error"]
    assert mock_manage.await_count == 0


@pytest.mark.asyncio
async def test_open_security_fails_closed_when_case_id_allocation_fails(tmp_path: Path) -> None:
    ctx = _make_execution_context("project")
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")

    mock_append = AsyncMock(return_value=_make_append_entry_result(progress_log))
    mock_manage = AsyncMock(return_value={"ok": True, "path": "/tmp/sec.md"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), patch(
        "scribe_mcp.tools.append_entry.append_entry", mock_append
    ), patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage), patch(
        "scribe_mcp.tools.sentinel_tools._next_case_id_for_project",
        side_effect=TimeoutError("case-id allocation failed: timeout acquiring counter lock"),
    ):
        result = await open_security(
            agent="test-agent",
            title="Allocator failure sec",
            symptoms="symptom",
            category="auth",
        )

    assert result["ok"] is False
    assert "Failed to allocate SEC case ID" in result["error"]
    assert mock_manage.await_count == 0
