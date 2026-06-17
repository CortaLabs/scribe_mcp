"""P4.2 — unified pagination/limit/filter contract for ``query_entries``.

These tests protect the WS2 F3/F6/F7 + status-asymmetry fixes: before P4.2 the
DB execution path and the flat-file fallback diverged.

  * F3 — the flat-file path honored ``limit`` only when it was SMALLER than
    ``page_size`` (so the default ``limit=50, page_size=10`` returned 10, not
    what the docstring implied).
  * F6 — the DB path ignored ``limit`` AND the documented ``max_results``
    override entirely; ``max_results`` was wired nowhere.
  * F7 — the DB path paginated THEN post-filtered (priority/category/confidence)
    in Python, so a page could under-fill while ``total_count`` over-counted.
  * status asymmetry — the DB path never forwarded ``status`` to the backend, so
    a ``status=[...]`` filter silently did nothing on the DB path.

Contract proven here (identical on BOTH paths):
  * ``page``/``page_size`` is the window; ``limit`` is the total cap on the
    matched+filtered set; ``max_results`` is a deprecated alias for ``limit``.
  * The DB path and the flat-file path return IDENTICAL entries for the same
    call over the same logical data.
  * A filtered query paginates correctly: pages fill and ``total_count`` is the
    true post-filter count.

Bounded-op: a fixed in-memory dataset and a handful of queries. No sleeps, no
input-size-dependent loops in the assertions.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from scribe_mcp.tools.query_entries import (
    _entry_passes_python_filters,
    _resolve_pagination,
    _status_to_emojis,
    query_entries,
)


# ---------------------------------------------------------------------------
# Helpers shared by the DB-path and flat-file-path drivers.
# ---------------------------------------------------------------------------

_STATUS_EMOJI = {
    "info": "ℹ️",
    "success": "✅",
    "warn": "⚠️",
    "error": "❌",
    "bug": "🐞",
    "plan": "🧭",
}


def _make_rows(n: int, *, emoji: str = "ℹ️", priority: str | None = None):
    """Build ``n`` synthetic DB rows in newest-first (``ts_iso`` DESC) order."""
    rows = []
    for i in range(n):
        # index 0 is newest; ts decreases with index so order == list order.
        idx = n - 1 - i
        meta = {}
        if priority is not None:
            meta["priority"] = priority
        rows.append(
            {
                "id": f"entry-{idx}",
                "ts": f"{idx:08d}",
                "ts_iso": f"2026-01-01T00:{idx // 60:02d}:{idx % 60:02d}Z",
                "emoji": emoji,
                "agent": "TestAgent",
                "message": f"log line {idx} token",
                "meta": meta,
                "raw_line": f"{emoji} log line {idx} token",
            }
        )
    return rows


class _FakeBackend:
    """In-memory backend mirroring the real ``query_entries_paginated`` contract.

    Applies the filters the real backend pushes into SQL (message substring +
    emoji membership), orders newest-first (rows are pre-ordered), and returns a
    ``(page_slice, total_count)`` tuple. The 500-row single-fetch clamp of the
    real backends is honored so the tool's chunked fetch is exercised.
    """

    SINGLE_FETCH_CLAMP = 500

    def __init__(self, rows):
        self._rows = rows
        self.calls = []
        self.fetch_project = AsyncMock(
            return_value=SimpleNamespace(id=1, name="test_project")
        )

    def _matched(self, *, message, emojis, **_kw):
        matched = self._rows
        if message:
            matched = [r for r in matched if message.lower() in r["message"].lower()]
        if emojis:
            matched = [r for r in matched if r["emoji"] in emojis]
        return matched

    async def query_entries_paginated(
        self, *, project, page, page_size, message=None, emojis=None, **_kw
    ):
        self.calls.append({"page": page, "page_size": page_size, "emojis": emojis})
        matched = self._matched(message=message, emojis=emojis)
        total = len(matched)
        window = max(1, min(page_size, self.SINGLE_FETCH_CLAMP))
        start = (page - 1) * window
        return matched[start : start + window], total


def extract(result):
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                try:
                    return json.loads(item.text)
                except json.JSONDecodeError:
                    return {"text_content": item.text}
        return {}
    return result


async def _run_db(backend, **kwargs):
    ctx = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md",
    }
    with patch("scribe_mcp.tools.query_entries.server_module") as srv:
        srv.storage_backend = backend
        srv.state_manager.record_tool = AsyncMock(return_value={})
        with patch("scribe_mcp.tools.query_entries.resolve_logging_context") as res:
            mctx = Mock()
            mctx.project = ctx
            mctx.recent_projects = []
            mctx.reminders = []
            mctx.fallback_chain = []
            mctx.fallback_used = False
            mctx.resolution_source = "explicit_project"
            res.return_value = mctx
            with patch("scribe_mcp.tools.query_entries.load_project_config") as lp:
                lp.return_value = ctx
                result = await query_entries(
                    agent="TestAgent", project="test_project",
                    format="structured", **kwargs
                )
    return extract(result)


def _rows_to_lines(rows):
    """Render DB rows as canonical flat-file log lines (same newest-first order)."""
    lines = []
    for r in rows:
        meta = r.get("meta") or {}
        meta_text = ";".join(f"{k}={v}" for k, v in meta.items())
        suffix = f" | {meta_text}" if meta_text else ""
        lines.append(
            f"[{r['emoji']}] [{r['ts_iso']}] [Agent: {r['agent']}] "
            f"[Project: test_project] {r['message']}{suffix}"
        )
    return lines


async def _run_flatfile(rows, **kwargs):
    ctx = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md",
    }
    with patch("scribe_mcp.tools.query_entries.server_module") as srv:
        srv.storage_backend = None  # force flat-file path
        srv.state_manager.record_tool = AsyncMock(return_value={})
        with patch("scribe_mcp.tools.query_entries.resolve_logging_context") as res:
            res.return_value = SimpleNamespace(
                project=ctx, recent_projects=[], reminders=[],
                fallback_chain=[], fallback_used=False,
                resolution_source="explicit_project",
            )
            with patch("scribe_mcp.tools.query_entries.load_project_config") as lp:
                lp.return_value = ctx
                with patch("scribe_mcp.tools.query_entries.read_all_lines") as rl:
                    rl.return_value = _rows_to_lines(rows)
                    result = await query_entries(
                        agent="TestAgent", project="test_project",
                        format="structured", **kwargs
                    )
    return extract(result)


# ---------------------------------------------------------------------------
# Unit-level helper tests (the contract's single source of truth).
# ---------------------------------------------------------------------------

def test_resolve_pagination_default_uses_limit_not_page_size():
    """F3: the default contract must not silently shrink to page_size."""
    page, page_size, limit = _resolve_pagination({})
    assert (page, page_size, limit) == (1, 50, 50)


def test_resolve_pagination_max_results_is_alias_when_limit_default():
    """F6: max_results is honored as the cap when limit is left at its default."""
    _, _, limit = _resolve_pagination({"limit": 50, "max_results": 7})
    assert limit == 7


def test_resolve_pagination_explicit_limit_wins_over_max_results():
    _, _, limit = _resolve_pagination({"limit": 3, "max_results": 99})
    assert limit == 3


def test_status_to_emojis_maps_and_dedups():
    assert _status_to_emojis(["info", "info", "error"]) == ["ℹ️", "❌"]
    assert _status_to_emojis(None) == []
    assert _status_to_emojis(["nope"]) == []


def test_entry_passes_python_filters_status_uses_emoji():
    entry = {"emoji": "✅", "message": "x", "meta": {}}
    assert _entry_passes_python_filters(entry, {"status": ["success"]}) is True
    assert _entry_passes_python_filters(entry, {"status": ["error"]}) is False


# ---------------------------------------------------------------------------
# F6 — DB path honors limit / max_results (previously dead).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_path_honors_limit_total_cap():
    backend = _FakeBackend(_make_rows(40))
    res = await _run_db(backend, limit=5, page=1, page_size=50)
    assert res["ok"] is True and res["source"] == "database"
    assert res["pagination"]["total_count"] == 5  # capped, not 40
    assert res["returned"] == 5


@pytest.mark.asyncio
async def test_db_path_honors_max_results_alias():
    backend = _FakeBackend(_make_rows(40))
    # limit left at default (50) so max_results is the effective cap.
    res = await _run_db(backend, max_results=8, page=1, page_size=50)
    assert res["pagination"]["total_count"] == 8
    assert res["pagination"]["limit"] == 8


@pytest.mark.asyncio
async def test_db_path_limit_cap_trims_partial_last_page():
    # 40 rows, limit cap 25, page_size 10 -> page 3 must show only 5 rows
    # (rows 21-25), not the natural 10 the backend would return.
    backend = _FakeBackend(_make_rows(40))
    res = await _run_db(backend, limit=25, page=3, page_size=10)
    assert res["pagination"]["total_count"] == 25
    assert res["returned"] == 5  # 25 - (3-1)*10
    assert res["pagination"]["has_next"] is False


# ---------------------------------------------------------------------------
# F7 — filtered DB query paginates correctly (page fills, count honest).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_path_filtered_pagination_fills_and_counts_true():
    # 30 rows: 12 critical, 18 low — interleaved so the OLD paginate-then-filter
    # would under-fill page 1 and over-count total.
    rows = []
    for i in range(30):
        prio = "critical" if i % 5 == 0 else "low"  # 6 critical of 30
        rows += _make_rows(1)
        rows[-1]["id"] = f"e-{i}"
        rows[-1]["ts_iso"] = f"2026-01-01T00:00:{29 - i:02d}Z"
        rows[-1]["message"] = f"row {i}"
        rows[-1]["meta"] = {"priority": prio}
    backend = _FakeBackend(rows)

    res = await _run_db(backend, priority=["critical"], page=1, page_size=3)
    assert res["source"] == "database"
    # 6 critical rows total -> honest count, full first page of 3.
    assert res["pagination"]["total_count"] == 6
    assert res["returned"] == 3
    assert res["pagination"]["has_next"] is True
    assert all(e["meta"]["priority"] == "critical" for e in res["entries"])

    res2 = await _run_db(backend, priority=["critical"], page=2, page_size=3)
    assert res2["returned"] == 3
    assert res2["pagination"]["has_next"] is False


# ---------------------------------------------------------------------------
# status asymmetry — status now applied on the DB path (pushed + per-entry).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_path_status_filter_no_longer_dropped():
    success = _make_rows(5, emoji="✅")
    errors = _make_rows(3, emoji="❌")
    backend = _FakeBackend(success + errors)
    res = await _run_db(backend, status=["error"], page=1, page_size=50)
    assert res["pagination"]["total_count"] == 3
    assert all(e["emoji"] == "❌" for e in res["entries"])
    # status was pushed into the backend as emojis (union), not dropped.
    assert backend.calls, "backend should have been queried"
    assert "❌" in (backend.calls[0]["emojis"] or [])


# ---------------------------------------------------------------------------
# DB == flat-file parity for the same call over the same data.
# ---------------------------------------------------------------------------

def _ids(res):
    # Compare on ``message`` — the field both the DB rows and the flat-file
    # parser carry (parse_log_line does not emit an ``id``).
    return [e["message"] for e in res["entries"]]


@pytest.mark.asyncio
async def test_db_and_flatfile_parity_default_call():
    rows = _make_rows(25)
    db = await _run_db(_FakeBackend(rows), page=1, page_size=10)
    ff = await _run_flatfile(rows, page=1, page_size=10)
    assert _ids(db) == _ids(ff)
    assert db["pagination"]["total_count"] == ff["pagination"]["total_count"] == 25
    assert db["pagination"]["has_next"] == ff["pagination"]["has_next"] is True


@pytest.mark.asyncio
async def test_db_and_flatfile_parity_with_limit_cap():
    rows = _make_rows(25)
    db = await _run_db(_FakeBackend(rows), limit=7, page=1, page_size=50)
    ff = await _run_flatfile(rows, limit=7, page=1, page_size=50)
    assert _ids(db) == _ids(ff)
    assert db["pagination"]["total_count"] == ff["pagination"]["total_count"] == 7


@pytest.mark.asyncio
async def test_db_and_flatfile_parity_filtered():
    # 40 rows, newest-first, unique messages, half critical / half low interleaved.
    rows = []
    for i in range(40):
        prio = "critical" if i % 2 == 0 else "low"  # 20 critical
        rows.append(
            {
                "id": f"p-{i}",
                "ts": f"{40 - i:08d}",
                "ts_iso": f"2026-01-01T00:{(40 - i) // 60:02d}:{(40 - i) % 60:02d}Z",
                "emoji": "ℹ️",
                "agent": "TestAgent",
                "message": f"unique row {i:02d}",
                "meta": {"priority": prio},
                "raw_line": f"ℹ️ unique row {i:02d}",
            }
        )
    db = await _run_db(_FakeBackend(rows), priority=["critical"], page=1, page_size=5)
    ff = await _run_flatfile(rows, priority=["critical"], page=1, page_size=5)
    assert _ids(db) == _ids(ff)
    assert db["pagination"]["total_count"] == ff["pagination"]["total_count"] == 20


# ---------------------------------------------------------------------------
# F3 — flat-file default no longer collapses to page_size when limit > page_size.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flatfile_default_limit_not_overridden_by_page_size():
    rows = _make_rows(40)
    # default limit=50, page_size=10 -> page returns page_size(10), total honest(40).
    res = await _run_flatfile(rows)
    assert res["pagination"]["page_size"] == 10
    assert res["returned"] == 10  # one window, not silently capped at limit/other
    assert res["pagination"]["total_count"] == 40
    assert res["pagination"]["has_next"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
