#!/usr/bin/env python3
"""Exercise entry filters through a real, isolated MCP client session."""

import json
import os
import sys
from collections import Counter
from pathlib import Path

import anyio
import pytest
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client


pytestmark = [pytest.mark.anyio, pytest.mark.regression]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_project(tmp_path, test_agent):
    """Let the public SDK establish identity; never inject a project binding."""
    source = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    # A child server keeps production config, shared globals and other tests out.
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("SCRIBE_")
        and key not in {"DATABASE_URL", "REPO_ROOT"}
    }
    env.update({
        "SCRIBE_DISABLE_DOTENV": "1", "SCRIBE_LOAD_REPO_DOTENV": "0",
        "SCRIBE_MODE": "standalone", "SCRIBE_STORAGE_BACKEND": "sqlite",
        "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_ROOT": str(runtime), "SCRIBE_REPO_ROOT": str(repo),
        "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"),
        "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1",
    })
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"], env=env)
    with anyio.fail_after(60):
        async with Client(stdio_client(params), mode="auto") as client:
            async def call(tool, **arguments):
                result = await client.call_tool(
                    tool, {"agent": test_agent, "format": "structured", **arguments},
                )
                text = "\n".join(getattr(block, "text", "") for block in result.content)
                assert not result.is_error, (tool, text)
                payload = json.loads(text)
                assert isinstance(payload, dict) and payload.get("ok") is True, (tool, payload)
                return payload

            bound = await call("set_project", name="test_priority_filters", root=str(repo))
            assert bound["project"]["session_id"], bound
            assert (runtime / "scribe.sqlite3").is_file()
            # No second bind or global fallback may conceal first-bind failure.
            initial = await call("read_recent", n=50)
            assert initial["entries"] == [], initial
            yield call


def _entries(result, expected, *, ordered=False):
    """Require successful, nonempty exact results, including duplicate detection."""
    assert result.get("ok") is True, result
    entries = result.get("entries")
    assert isinstance(entries, list) and entries, result
    messages = [entry["message"] for entry in entries]
    assert Counter(messages) == Counter(expected), messages
    if ordered:
        assert messages == expected, messages
    return entries


def _field(entry, name):
    # Both public readers expose filter metadata under meta, or at top level.
    return entry[name] if name in entry else entry["meta"][name]


async def _seed(call, rows):
    for message, metadata in rows:
        await call("append_entry", message=message, **metadata)


async def test_read_recent_priority_filter(test_project):
    """Critical/high matches must exclude successfully written medium/low rows."""
    rows = [
        ("Critical bug discovered", {"priority": "critical"}),
        ("High priority task", {"priority": "high"}),
        ("Medium priority work", {"priority": "medium"}),
        ("Low priority note", {"priority": "low"}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("read_recent"), [message for message, _ in rows])
    result = await test_project("read_recent", priority=["critical", "high"])
    entries = _entries(result, ["Critical bug discovered", "High priority task"])
    assert {_field(entry, "priority") for entry in entries} == {"critical", "high"}


async def test_read_recent_category_filter(test_project):
    """Bug/security matches must exclude the implementation row."""
    rows = [
        ("Bug found in authentication", {"category": "bug"}),
        ("Security vulnerability detected", {"category": "security"}),
        ("Implementation completed", {"category": "implementation"}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("read_recent"), [message for message, _ in rows])
    result = await test_project("read_recent", category=["bug", "security"])
    entries = _entries(result, ["Bug found in authentication", "Security vulnerability detected"])
    assert {_field(entry, "category") for entry in entries} == {"bug", "security"}


async def test_read_recent_confidence_filter(test_project):
    """The threshold is inclusive and excludes even a just-below-threshold row."""
    rows = [
        ("Low confidence entry", {"confidence": 0.3}),
        ("Medium confidence entry", {"confidence": 0.7}),
        ("High confidence entry", {"confidence": 0.95}),
        ("Threshold confidence entry", {"confidence": 0.8}),
        ("Below threshold entry", {"confidence": 0.79}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("read_recent"), [message for message, _ in rows])
    result = await test_project("read_recent", min_confidence=0.8)
    entries = _entries(result, ["High confidence entry", "Threshold confidence entry"])
    assert {float(_field(entry, "confidence")) for entry in entries} == {0.8, 0.95}
    assert all(float(_field(entry, "confidence")) >= 0.8 for entry in entries)


async def test_read_recent_priority_sort(test_project):
    """Assert the whole priority order, with time order as a negative control."""
    rows = [
        ("Low priority", {"priority": "low"}),
        ("Critical issue", {"priority": "critical"}),
        ("High priority", {"priority": "high"}),
        ("Medium task", {"priority": "medium"}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("read_recent", priority_sort=False),
             [message for message, _ in reversed(rows)], ordered=True)
    result = await test_project("read_recent", n=10, priority_sort=True)
    entries = _entries(result, ["Critical issue", "High priority", "Medium task", "Low priority"],
                       ordered=True)
    priorities = [_field(entry, "priority") for entry in entries]
    assert priorities == ["critical", "high", "medium", "low"]
    assert priorities.index("critical") < priorities.index("low")


async def test_query_entries_priority_filter(test_project):
    """Query must return the critical row and exclude the low priority row."""
    rows = [
        ("Critical database issue", {"priority": "critical"}),
        ("Low priority cleanup", {"priority": "low"}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("query_entries"), [message for message, _ in rows])
    result = await test_project("query_entries", priority=["critical"])
    entries = _entries(result, ["Critical database issue"])
    assert [_field(entry, "priority") for entry in entries] == ["critical"]


async def test_query_entries_category_filter(test_project):
    """Query must return the bug row and exclude the test category row."""
    rows = [
        ("Test results passing", {"category": "test"}),
        ("Bug fix committed", {"category": "bug"}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("query_entries"), [message for message, _ in rows])
    result = await test_project("query_entries", category=["bug"])
    entries = _entries(result, ["Bug fix committed"])
    assert [_field(entry, "category") for entry in entries] == ["bug"]


async def test_combined_filters(test_project):
    """Each predicate independently excludes an otherwise matching row."""
    rows = [
        ("Critical security bug", {"priority": "critical", "category": "security", "confidence": 0.95}),
        ("Low priority note", {"priority": "low", "category": "documentation", "confidence": 0.5}),
        ("Wrong priority", {"priority": "low", "category": "security", "confidence": 0.95}),
        ("Wrong category", {"priority": "critical", "category": "documentation", "confidence": 0.95}),
        ("Wrong confidence", {"priority": "critical", "category": "security", "confidence": 0.89}),
    ]
    await _seed(test_project, rows)
    _entries(await test_project("read_recent"), [message for message, _ in rows])
    result = await test_project("read_recent", priority=["critical"], category=["security"],
                                min_confidence=0.9, priority_sort=True)
    entries = _entries(result, ["Critical security bug"])
    assert [_field(entry, "priority") for entry in entries] == ["critical"]
    assert [_field(entry, "category") for entry in entries] == ["security"]
    assert all(float(_field(entry, "confidence")) >= 0.9 for entry in entries)
    # Removing any one predicate must expose its specific exclusion control.
    for filters, expected in [
        ({"category": ["security"], "min_confidence": 0.9}, "Wrong priority"),
        ({"priority": ["critical"], "min_confidence": 0.9}, "Wrong category"),
        ({"priority": ["critical"], "category": ["security"]}, "Wrong confidence"),
    ]:
        _entries(await test_project("read_recent", **filters), ["Critical security bug", expected])


async def test_query_entries_priority_sort(test_project):
    """Sort before pagination, preserving recency and combined-filter totals."""
    rows = [
        ("Medium work", {"priority": "medium", "category": "security", "confidence": 0.7}),
        ("Critical alert", {"priority": "critical", "category": "security", "confidence": 0.95}),
        ("High priority", {"priority": "high", "category": "documentation", "confidence": 0.95}),
        ("Critical follow-up", {"priority": "critical", "category": "security", "confidence": 0.95}),
    ]
    for index, (message, metadata) in enumerate(rows):
        await test_project("append_entry", message=message,
                           timestamp_utc=f"2026-01-03 14:0{index}:00 UTC", **metadata)
    chronological = [message for message, _ in reversed(rows)]
    ranked = ["Critical follow-up", "Critical alert", "High priority", "Medium work"]
    _entries(await test_project("query_entries", priority_sort=False),
             chronological, ordered=True)
    result = await test_project("query_entries", priority_sort=True)
    entries = _entries(result, ranked, ordered=True)
    priorities = [_field(entry, "priority") for entry in entries]
    assert priorities == ["critical", "critical", "high", "medium"]
    assert priorities.index("critical") < priorities.index("medium")
    for enabled, expected in ((False, chronological), (True, ranked)):
        # The total cap cuts a partial last page AFTER global sorting.
        for page in (1, 2):
            result = await test_project("query_entries", priority_sort=enabled,
                                        page=page, page_size=2, limit=3)
            _entries(result, expected[(page - 1) * 2:min(page * 2, 3)], ordered=True)
            assert result["pagination"]["total_count"] == result["total_found"] == 3
            assert result["returned"] == len(result["entries"])
            assert result["pagination"]["has_next"] is (page == 1)
            assert result["pagination"]["has_prev"] is (page == 2)
    for page, message in ((1, "Critical follow-up"), (2, "Critical alert")):
        result = await test_project("query_entries", priority_sort=True,
                                    category=["security"], min_confidence=0.9,
                                    page=page, page_size=1)
        _entries(result, [message], ordered=True)
        assert result["pagination"]["total_count"] == result["total_found"] == 2
        assert result["returned"] == 1
