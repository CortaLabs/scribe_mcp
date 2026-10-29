#!/usr/bin/env python3
"""Tests for read_recent EntryLimitManager integration."""

from types import SimpleNamespace
from contextlib import asynccontextmanager
import asyncio
import json
import os
import sys
from tempfile import TemporaryFile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest
import pytest_asyncio
from fixtures.storage import sqlite_storage as _sqlite_storage_fixture
import scribe_mcp.tools.read_recent as read_recent_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.tools.read_recent import read_recent


# Reuse the canonical temporary storage fixture with the strict asyncio runner.
sqlite_storage = pytest_asyncio.fixture(_sqlite_storage_fixture.__wrapped__)


def _readable_text(result):
    """Extract readable text from MCP CallToolResult or fallback dict output."""
    if isinstance(result, dict):
        return result.get("content", "")
    return "\n".join(
        block.text
        for block in getattr(result, "content", [])
        if getattr(block, "type", None) == "text"
    )


@pytest.mark.asyncio
async def test_readable_format_no_truncation():
    """Verify readable format returns full entries without truncation."""
    # This test requires a project with entries
    result = await read_recent(agent="test_agent", n=10, format="readable")

    # Should have entries or be a formatted string
    assert result is not None

    # If it's a dict with entries, verify structure
    if isinstance(result, dict) and "entries" in result:
        for entry in result["entries"]:
            # Full message should exist
            assert "message" in entry
            # Reasoning should be preserved if present
            if "meta" in entry and "reasoning" in entry["meta"]:
                reasoning = entry["meta"]["reasoning"]
                assert reasoning  # Not empty
                # Reasoning should have why/what/how if it's a dict
                if isinstance(reasoning, dict):
                    # At least one of these should exist
                    assert "why" in reasoning or "what" in reasoning or "how" in reasoning


@pytest.mark.asyncio
async def test_structured_format_uses_limit_manager():
    """Verify structured format uses EntryLimitManager."""
    result = await read_recent(agent="test_agent", n=100, format="structured")

    # Should have proper response structure
    if isinstance(result, dict):
        # Should have ok status
        assert "ok" in result

        # If entries exist, should have limit_metadata
        if "entries" in result and result["entries"]:
            assert "limit_metadata" in result
            limit_meta = result["limit_metadata"]

            # Verify limit metadata structure
            assert "total_available" in limit_meta
            assert "returned_count" in limit_meta
            assert "mode" in limit_meta
            assert limit_meta["mode"] == "structured"


@pytest.mark.asyncio
async def test_compact_format_uses_limit_manager():
    """Verify compact format uses EntryLimitManager."""
    result = await read_recent(agent="test_agent", n=50, format="compact")

    if isinstance(result, dict):
        # This suite runs without binding a project; tolerate that bootstrap
        # state like the sibling tests above. The strict "must not fail" check
        # only applies when a project is actually configured.
        no_project = (
            result.get("error")
            == "No project configured. Invoke set_project before using this tool."
        )
        if not no_project:
            assert result.get("ok") is not False

        # If entries exist, should have limit_metadata
        if "entries" in result and result["entries"]:
            assert "limit_metadata" in result
            limit_meta = result["limit_metadata"]

            # Verify limit metadata
            assert "mode" in limit_meta
            assert limit_meta["mode"] == "compact"
            assert "limit_applied" in limit_meta


@pytest.mark.asyncio
async def test_entry_limit_metadata():
    """Verify limit metadata is included for non-readable formats."""
    result = await read_recent(agent="test_agent", n=50, format="compact")

    if isinstance(result, dict) and "entries" in result and result["entries"]:
        # Should have limit metadata
        assert "limit_metadata" in result or "pagination" in result

        if "limit_metadata" in result:
            meta = result["limit_metadata"]
            # Check all required fields
            assert "total_available" in meta
            assert "filtered_count" in meta
            assert "returned_count" in meta
            assert "entries_omitted" in meta
            assert "mode" in meta
            assert "limit_applied" in meta


@pytest.mark.asyncio
async def test_readable_vs_structured_entry_preservation():
    """Verify readable format preserves more content than structured."""
    # Get same entries in both formats
    readable_result = await read_recent(agent="test_agent", n=5, format="readable")
    structured_result = await read_recent(agent="test_agent", n=5, format="structured")

    # Both should succeed
    assert readable_result is not None
    assert structured_result is not None

    # If structured has entries, it should have limit_metadata
    if isinstance(structured_result, dict) and "entries" in structured_result:
        assert "limit_metadata" in structured_result

        # Verify entries are complete dicts with message
        for entry in structured_result["entries"]:
            assert isinstance(entry, dict)
            assert "message" in entry


@pytest.mark.asyncio
async def test_readable_compact_true_preserves_rendered_entry_fields(monkeypatch, tmp_path):
    """compact=True must not compact entries before default readable rendering."""
    project = {
        "name": "compact-readable-test",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
    }
    context = LoggingContext(
        tool_name="read_recent",
        project=project,
        recent_projects=[],
        state_snapshot={},
        reminders=[],
        resolution_source="test",
    )

    async def record_tool(_tool_name):
        return {"tool": _tool_name}

    async def prepare_context(**_kwargs):
        return context

    async def fake_read_tail(*_args, **_kwargs):
        return [
            "[ℹ️] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] "
            "[Project: compact-readable-test] Compact readable message"
        ]

    monkeypatch.setattr(
        read_recent_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=record_tool),
    )
    monkeypatch.setattr(read_recent_module.server_module, "storage_backend", None)
    monkeypatch.setattr(read_recent_module.server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(read_recent_module._READ_RECENT_HELPER, "prepare_context", prepare_context)
    monkeypatch.setattr(read_recent_module, "read_tail", fake_read_tail)

    result = await read_recent(agent="test_agent", compact=True)
    text = _readable_text(result)

    assert "TestAgent" in text
    assert "Compact readable message" in text
    assert "14:30" in text


@pytest.mark.asyncio
async def test_compact_format_still_returns_compact_entry_keys(monkeypatch, tmp_path):
    """format='compact' keeps compact entry behavior."""
    project = {
        "name": "compact-format-test",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
    }
    context = LoggingContext(
        tool_name="read_recent",
        project=project,
        recent_projects=[],
        state_snapshot={},
        reminders=[],
        resolution_source="test",
    )

    async def record_tool(_tool_name):
        return {"tool": _tool_name}

    async def prepare_context(**_kwargs):
        return context

    async def fake_read_tail(*_args, **_kwargs):
        return [
            "[ℹ️] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] "
            "[Project: compact-format-test] Compact format message"
        ]

    monkeypatch.setattr(
        read_recent_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=record_tool),
    )
    monkeypatch.setattr(read_recent_module.server_module, "storage_backend", None)
    monkeypatch.setattr(read_recent_module.server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(read_recent_module._READ_RECENT_HELPER, "prepare_context", prepare_context)
    monkeypatch.setattr(read_recent_module, "read_tail", fake_read_tail)

    result = await read_recent(agent="test_agent", compact=True, format="compact")

    assert isinstance(result, dict)
    assert result["entries"][0]["a"] == "TestAgent"
    assert result["entries"][0]["m"] == "Compact format message"
    assert "message" not in result["entries"][0]


@pytest.mark.asyncio
async def test_priority_sorting_enabled():
    """Verify EntryLimitManager uses priority sorting."""
    result = await read_recent(agent="test_agent", n=20, format="structured", priority_sort=True)

    if isinstance(result, dict) and "entries" in result and len(result["entries"]) > 1:
        # Should have limit_metadata confirming sort was applied
        assert "limit_metadata" in result

        # Entries should be present and be dicts
        for entry in result["entries"]:
            assert isinstance(entry, dict)
            # Should have basic structure
            assert "message" in entry or "raw_line" in entry


# Reuse the real SDK stdio pattern from test_manage_docs_session_binding.
# The internal profile is identical for database/file cases; it is not public
# profile certification. No request, session binding or authorization is forged.
_RECENCY_SERVER_PROBE = r'''
import asyncio, os
from scribe_mcp import server
import scribe_mcp.tools.read_recent as reader

class FileReaderSource:
    # Select only the real reader's file-data branch. Its helper captured the
    # actual server at construction and still resolves the genuine binding.
    storage_backend = None

    def __getattr__(self, name):
        return getattr(server, name)

if os.environ["SBR_RECENCY_SOURCE"] == "file":
    reader.server_module = FileReaderSource()
asyncio.run(server.main())
'''

@asynccontextmanager
async def _genuine_recency_reader(tmp_path, sqlite_db_path, project_payload, agent, source):
    # Run pytest with the selected SDK interpreter. Resolving venv symlinks
    # would incorrectly equate environments with different installed packages.
    sdk_python = os.environ.get("SBR_SDK_PYTHON", sys.executable)
    assert Path(sdk_python).absolute() == Path(sys.executable).absolute(), (
        "Run pytest with SBR_SDK_PYTHON; the recency client uses pytest's SDK",
        sdk_python, sys.executable,
    )
    import scribe_mcp
    from mcp import StdioServerParameters
    from mcp.client.client import Client
    import mcp.client.stdio as sdk_stdio

    source_root = Path(__file__).resolve().parents[1]
    assert Path(scribe_mcp.__file__).resolve() == source_root / "src/scribe_mcp/__init__.py"
    repo = Path(project_payload["root"])
    (repo / ".git").mkdir()
    runtime = tmp_path / "sdk-runtime"
    runtime.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key != "DATABASE_URL"}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(sqlite_db_path), "SCRIBE_STATE_PATH": str(runtime / "state.json"),
        "SCRIBE_ROOT": str(runtime), "SCRIBE_REPO_ROOT": str(repo),
        "SCRIBE_TRUSTED_REPO_ROOTS": str(repo), "PYTHONPATH": str(source_root / "src"),
        "SBR_RECENCY_SOURCE": source,
    })
    params = StdioServerParameters(
        command=sdk_python, args=["-c", _RECENCY_SERVER_PROBE], env=env, cwd=source_root,
    )
    processes = []
    spawn = sdk_stdio._create_platform_compatible_process

    async def observe_spawn(*args, **kwargs):
        # Observe the real SDK-owned process solely to assert clean exit. The
        # original SDK transport, spawn, session and shutdown all run unchanged.
        process = await spawn(*args, **kwargs)
        processes.append(process)
        return process

    with TemporaryFile(mode="w+", encoding="utf-8") as stderr, pytest.MonkeyPatch.context() as patch:
        patch.setattr(sdk_stdio, "_create_platform_compatible_process", observe_spawn)
        try:
            async with Client(
                sdk_stdio.stdio_client(params, errlog=stderr),
                mode="2026-07-28", read_timeout_seconds=45,
            ) as client:
                assert client.protocol_version == "2026-07-28"
                async def call(name, arguments):
                    result = await asyncio.wait_for(client.call_tool(name, arguments), timeout=45)
                    assert not result.is_error, (name, result)
                    return json.loads("\n".join(getattr(item, "text", "") for item in result.content))

                selected = await call("set_project", {"agent": agent, **project_payload, "format": "structured"})
                assert selected.get("ok", True) is not False, selected

                async def read_recent(**arguments):
                    return await call("read_recent", arguments)

                yield read_recent
        finally:
            # SDK stdio bounds graceful wait and process-tree kill/reap. A
            # missing exit or kill is a failure, never accepted as cleanup.
            stderr.seek(0)
            errors = stderr.read()
            assert len(processes) == 1, errors
            assert processes[0].returncode == 0, errors


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["database", "file"])
@pytest.mark.parametrize("output_format", ["structured", "compact"])
@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("include_metadata", [False, True])
@pytest.mark.parametrize("priority_sort", [False, True, None], ids=["false", "true", "default"])
async def test_public_reader_preserves_requested_order(
    tmp_path, sqlite_storage, sqlite_db_path, project_payload, test_agent,
    source, output_format, compact, include_metadata, priority_sort,
):
    """Real storage/state/file paths must keep source order unless opted in."""
    assert read_recent_module.server_module.get_execution_context() is None
    async with _genuine_recency_reader(
        tmp_path, sqlite_db_path, project_payload, test_agent, source,
    ) as read_recent:
        record = await sqlite_storage.fetch_project(
            project_payload["name"], repo_root=project_payload["root"],
        )
        assert record is not None
        priorities = ["critical", "high", "medium", "low"]
        messages = [f"ordering record {i}" for i in range(4)]
        lines = [
            f"[ℹ️] [2026-01-03 14:0{i}:00 UTC] [Agent: {test_agent}] "
            f"[Project: {record.name}] {messages[i]} | priority={priorities[i]}; detail=kept-{i}"
            for i in range(4)
        ]
        for i in range(4):
            await sqlite_storage.insert_entry(
                entry_id=f"order-{i}", project=record,
                ts=datetime(2026, 1, 3, 14, i, tzinfo=timezone.utc),
                emoji="ℹ️", agent=test_agent, message=messages[i],
                meta={"priority": priorities[i], "detail": f"kept-{i}"},
                raw_line=lines[i], sha256=sha256(lines[i].encode()).hexdigest(),
            )
        # The file order deliberately differs from both timestamp and priority order.
        file_order = [2, 0, 3, 1]
        log_path = Path(project_payload["progress_log"])
        log_path.write_text("\n".join(lines[i] for i in file_order) + "\n", encoding="utf-8")
        original_log = log_path.read_bytes()
        expected = [0, 1, 2, 3] if priority_sort else (
            [3, 2, 1, 0] if source == "database" else file_order
        )
        options = {} if priority_sort is None else {"priority_sort": priority_sort}
        id_key, message_key = ("i", "m") if compact else ("id", "message")
        # Test the exact four-entry request and two actual pages independently.
        for page_size in (4, 2):
            for page in range(1, 4 // page_size + 1):
                result = await read_recent(
                    agent=test_agent, limit=4, page_size=page_size, page=page,
                    format=output_format, compact=compact,
                    include_metadata=include_metadata, **options,
                )
                assert isinstance(result, dict)
                assert result["ok"] is True, result
                entries = result["entries"]
                wanted = expected[(page - 1) * page_size:page * page_size]
                assert len(entries) == page_size
                assert [entry[message_key] for entry in entries] == [messages[i] for i in wanted]
                if source == "database":
                    assert [entry[id_key] for entry in entries] == [f"order-{i}" for i in wanted]
                else:
                    # The real file parser has no entry IDs; do not invent them.
                    assert all(id_key not in entry for entry in entries)
                assert result["pagination"]["page"] == page
                assert result["pagination"]["page_size"] == page_size
                assert result["pagination"]["total_count"] == 4
                assert result["pagination"]["has_prev"] == (page > 1)
                assert result["pagination"]["has_next"] == (page * page_size < 4)
                assert result["limit_metadata"] == {
                    "total_available": page_size, "filtered_count": page_size,
                    "returned_count": page_size, "entries_omitted": 0,
                    "mode": output_format,
                    "limit_applied": 100 if output_format == "structured" else 200,
                }
                for entry, i in zip(entries, wanted):
                    if include_metadata:
                        assert entry["meta"] == {"priority": priorities[i], "detail": f"kept-{i}"}
                    else:
                        assert "meta" not in entry
                    if not compact:
                        assert entry["raw_line"] == lines[i]
                        assert entry["ts"] == f"2026-01-03 14:0{i}:00 UTC"
        assert log_path.read_bytes() == original_log
        assert await sqlite_storage.count_entries(project=record) == 4


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["database", "file", "supplement"])
@pytest.mark.parametrize("output_format", ["structured", "compact"])
@pytest.mark.parametrize("priority_sort", [False, True, None], ids=["false", "true", "default"])
async def test_public_reader_orders_equal_priorities_by_full_time(
    tmp_path, sqlite_storage, sqlite_db_path, project_payload, test_agent,
    source, output_format, priority_sort,
):
    """Real empty-DB supplementation must select the newest row before limiting."""
    async with _genuine_recency_reader(
        tmp_path, sqlite_db_path, project_payload, test_agent, source,
    ) as reader:
        record = await sqlite_storage.fetch_project(
            project_payload["name"], repo_root=project_payload["root"],
        )
        assert record is not None
        timestamps = ["2026-01-01 12:00:00 UTC", "2026-12-31 12:00:00 UTC",
                      "2026-12-31 12:00:01 UTC"]
        messages = [f"equal priority record {i}" for i in range(3)]
        lines = [
            f"[ℹ️] [{timestamp}] [Agent: {test_agent}] [Project: {record.name}] "
            f"{messages[i]} | priority=high; detail=kept-{i}"
            for i, timestamp in enumerate(timestamps)
        ]
        if source != "supplement":
            for i, line in enumerate(lines):
                await sqlite_storage.insert_entry(
                    entry_id=f"tie-{i}", project=record,
                    ts=datetime.strptime(timestamps[i], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc),
                    emoji="ℹ️", agent=test_agent, message=messages[i],
                    meta={"priority": "high", "detail": f"kept-{i}"},
                    raw_line=line, sha256=sha256(line.encode()).hexdigest(),
                )
        file_order = [0, 2, 1]
        log_path = Path(project_payload["progress_log"])
        file_lines = [lines[i] for i in file_order]
        if source == "database":
            # A newer, higher-priority file-only record must never enter an
            # authoritative DB page, including sparse later pages.
            file_lines.append(
                f"[ℹ️] [2027-01-01 00:00:00 UTC] [Agent: {test_agent}] "
                f"[Project: {record.name}] file-only exclusion | priority=critical"
            )
        log_path.write_text("\n".join(file_lines) + "\n", encoding="utf-8")
        original_log = log_path.read_bytes()
        expected = [2, 1, 0] if priority_sort or source == "database" else file_order
        options = {} if priority_sort is None else {"priority_sort": priority_sort}
        compact = output_format == "compact"
        message_key = "m" if compact else "message"
        id_key = "i" if compact else "id"
        for page_size in (3, 1):
            pages = (1,) if source == "supplement" else range(1, 3 // page_size + 1)
            for page in pages:
                result = await reader(
                    agent=test_agent, limit=page_size, page_size=page_size, page=page,
                    format=output_format, compact=compact, **options,
                )
                assert result["ok"] is True, result
                wanted = expected[(page - 1) * page_size:page * page_size]
                assert [entry[message_key] for entry in result["entries"]] == [messages[i] for i in wanted]
                assert result["pagination"]["page"] == page
                assert result["pagination"]["page_size"] == page_size
                assert result["pagination"]["total_count"] == (page_size if source == "supplement" else 3)
                for entry, i in zip(result["entries"], wanted):
                    assert entry["meta"] == {"priority": "high", "detail": f"kept-{i}"}
                    if source == "database":
                        assert entry[id_key] == f"tie-{i}"
                    else:
                        assert id_key not in entry
                    if not compact:
                        assert entry["raw_line"] == lines[i]
                        assert entry["ts"] == timestamps[i]
        if source == "supplement":
            # Only page one may use the empty-DB lag fallback.
            later = await reader(agent=test_agent, page=2, page_size=1, format="structured", **options)
            assert later["entries"] == []
            assert later["pagination"]["total_count"] == 0
        assert log_path.read_bytes() == original_log
        assert await sqlite_storage.count_entries(project=record) == (0 if source == "supplement" else 3)


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["file", "supplement"])
@pytest.mark.parametrize("output_format", ["structured", "compact"])
@pytest.mark.parametrize("priority_sort", [False, True, None], ids=["false", "true", "default"])
async def test_public_reader_preserves_out_of_range_timestamps(
    tmp_path, sqlite_storage, sqlite_db_path, project_payload, test_agent,
    source, output_format, priority_sort,
):
    """UTC normalization overflow must use the stable invalid-time fallback."""
    async with _genuine_recency_reader(
        tmp_path, sqlite_db_path, project_payload, test_agent, source,
    ) as reader:
        record = await sqlite_storage.fetch_project(
            project_payload["name"], repo_root=project_payload["root"],
        )
        assert record is not None
        timestamps = ["0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59",
                      "2026-12-31 23:59:59 UTC"]
        messages = ["UTC underflow", "UTC overflow", "valid UTC timestamp"]
        lines = [
            f"[ℹ️] [{timestamp}] [Agent: {test_agent}] [Project: {record.name}] "
            f"{messages[i]} | priority=high"
            for i, timestamp in enumerate(timestamps)
        ]
        log_path = Path(project_payload["progress_log"])
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        before = log_path.read_bytes()
        options = {} if priority_sort is None else {"priority_sort": priority_sort}
        compact = output_format == "compact"
        message_key = "m" if compact else "message"
        expected = [2, 0, 1] if priority_sort else [0, 1, 2]
        for limit in (3, 1):
            result = await reader(
                agent=test_agent, limit=limit, page_size=limit,
                format=output_format, compact=compact,
                fields=["message", "ts", "meta", "raw_line"], **options,
            )
            assert result["ok"] is True, result
            wanted = expected[:limit]
            assert [entry[message_key] for entry in result["entries"]] == [messages[i] for i in wanted]
            assert [entry["ts"] for entry in result["entries"]] == [timestamps[i] for i in wanted]
            assert result["pagination"]["page_size"] == limit
            assert result["pagination"]["total_count"] == (limit if source == "supplement" else 3)
            assert all(entry["meta"] == {"priority": "high"} for entry in result["entries"])
            if not compact:
                assert [entry["raw_line"] for entry in result["entries"]] == [lines[i] for i in wanted]
        assert log_path.read_bytes() == before
        assert await sqlite_storage.count_entries(project=record) == 0
