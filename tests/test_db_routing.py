"""Prove DB routing through a genuine SDK session and disposable SQLite data."""

import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import anyio
import pytest
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client


pytestmark = [pytest.mark.anyio, pytest.mark.regression, pytest.mark.storage]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _checkout_snapshot(source):
    """Include ignored Scribe files: git status alone misses the original bug."""
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for name in ("src", "tests", ".scribe")
        for path in (source / name).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }


class QueryProject:
    """Observation and corpus controls around the real public client."""

    def __init__(self, client, agent, repo, runtime):
        self.client = client
        self.agent = agent
        self.repo = repo
        self.runtime = runtime
        self.database = runtime / "scribe.sqlite3"
        self.log = None

    async def __call__(self, tool, **arguments):
        result = await self.client.call_tool(
            tool, {"agent": self.agent, "format": "structured", **arguments},
        )
        text = "\n".join(getattr(block, "text", "") for block in result.content)
        assert not result.is_error, (tool, text)
        payload = json.loads(text)
        assert isinstance(payload, dict) and payload.get("ok") is True, (tool, payload)
        return payload

    def database_only(self, messages):
        """Check committed DB rows, then make flat-file fallback unable to pass."""
        with sqlite3.connect(f"file:{self.database}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT e.message FROM main.scribe_entries e "
                "JOIN main.scribe_projects p ON p.id = e.project_id WHERE p.repo_root = ?",
                (str(self.repo),),
            ).fetchall()
        assert Counter(row[0] for row in rows) == Counter(messages)
        assert self.log.is_relative_to(self.repo), self.log
        assert self.log.is_file()
        archived = self.runtime / "withheld-progress-log.md"
        self.log.rename(archived)
        assert archived.is_file() and not self.log.exists()


@pytest.fixture
async def query_project(tmp_path, test_agent):
    """Use supported SDK identity, child-owned globals and finite temp cleanup."""
    source = Path(__file__).resolve().parents[1]
    before = _checkout_snapshot(source)
    with TemporaryDirectory(prefix="query-isolation-", dir=tmp_path) as directory:
        sandbox = Path(directory)
        repo = sandbox / "repo"
        (repo / ".git").mkdir(parents=True)
        runtime = sandbox / "runtime"
        runtime.mkdir()
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
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "scribe_mcp"], env=env, cwd=str(repo),
        )
        try:
            with anyio.fail_after(90):
                async with Client(stdio_client(params), mode="auto") as client:
                    call = QueryProject(client, test_agent, repo, runtime)
                    bound = await call("set_project", name="query_isolation", root=str(repo))
                    assert bound["project"]["session_id"], bound
                    call.log = Path(bound["project"]["progress_log"])
                    assert call.database.is_file()
                    initial = await call("query_entries")
                    assert initial["entries"] == [] and initial["total_found"] == 0
                    yield call
        finally:
            assert _checkout_snapshot(source) == before, "Query test changed checkout files"
    assert not sandbox.exists(), "Child runtime/repository cleanup did not finish"


def _entries(result, expected, *, total=None, ordered=False):
    """Nonempty exact oracle; duplicates, absent rows and fallback all fail."""
    assert result.get("ok") is True, result
    assert result.get("source") == "database", result
    entries = result.get("entries")
    assert isinstance(entries, list) and entries, result
    actual = [entry["message"] for entry in entries]
    assert Counter(actual) == Counter(expected), actual
    if ordered:
        assert actual == expected, actual
    assert result["returned"] == len(expected)
    assert result["total_found"] == (len(expected) if total is None else total)
    return entries


async def _missing_result_control(call, expected):
    missing = await call("query_entries", message="never-seeded-sensitivity-control")
    assert missing["entries"] == [] and missing["total_found"] == 0
    with pytest.raises(AssertionError):
        _entries(missing, expected)


async def test_db_routing(query_project):
    """All five committed rows survive withholding the entire flat-file log."""
    messages = [f"Test entry {i+1} for DB routing verification" for i in range(5)]
    for i, message in enumerate(messages):
        await query_project("append_entry", message=message, status="info",
                            meta={"test_id": i, "phase": "db_test"})
    query_project.database_only(messages)
    result = await query_project("query_entries", message="routing", page_size=10)
    _entries(result, messages)
    await _missing_result_control(query_project, messages)
    assert not query_project.log.exists()
