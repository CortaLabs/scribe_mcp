import pytest


@pytest.mark.asyncio
async def test_query_entries_message_filter_regression(monkeypatch):
    """
    Regression test: message filtering in query_entries must not silently drop all entries.

    Previously, tools/query_entries.py called message_matches with positional arguments,
    but message_matches enforces keyword-only args for mode/case_sensitive, causing
    TypeError that was swallowed and resulted in zero matches.
    """
    from scribe_mcp.tools.query_entries import _execute_search_with_fallbacks

    async def fake_read_all_lines(_path):
        return [
            "[ℹ️] [2025-12-17 02:38:42 UTC] [Agent: Codex] [Project: test_project] Smoke test: append_entry with meta payload | foo=bar",
            "[✅] [2025-12-17 02:38:43 UTC] [Agent: Codex] [Project: test_project] Something else entirely | foo=baz",
        ]

    import scribe_mcp.tools.query_entries as qe
    monkeypatch.setattr(qe, "read_all_lines", fake_read_all_lines)

    project_context = type("Ctx", (), {"project": {"progress_log": "dummy.log"}})()

    search_query = {
        "search_params": {
            "message": "Smoke test",
            "message_mode": "substring",
            "case_sensitive": False,
            "page": 1,
            "page_size": 50,
            "include_metadata": True,
        },
        "project_context": project_context,
        "resolved_project": "test_project",
        "validation_warnings": [],
    }

    result = await _execute_search_with_fallbacks(search_query, final_config=None)

    assert result["ok"] is True
    assert result["total_found"] >= 1
    assert any("Smoke test" in entry.get("message", "") for entry in result["entries"])

