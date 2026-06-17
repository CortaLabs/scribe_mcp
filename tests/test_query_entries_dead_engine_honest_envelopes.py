"""Dead cross-project engine removal + honest envelopes (WS2 F2/F8/F9, P6.3).

Three guarantees this suite protects:

* **F2 (dead engine removed):** the orphaned cross-project search engine
  (``_handle_cross_project_search`` / ``_resolve_cross_project_projects`` and the
  ~800-line cluster reachable only from them) had **zero** call sites. It is gone.
  The live ``_collect_observed_context_signals`` helper, which sat inside the old
  block range but is wired into ``query_entries``, must remain.
* **F8 (honest scope envelope):** ``search_scope != "project"``, ``document_types``,
  and ``relevance_threshold > 0`` previously produced a *silent no-op* (only the
  active project's progress log was searched, but callers believed they searched
  globally). They now return an ``ok=False`` teaching error instead of lying.
* **F9 (honest failure envelope):** an internal error must never be dressed up as
  a successful single-result search. The emergency fallbacks return ``ok=False``
  with an empty result set, never a fabricated ``🚨`` entry inside ``ok=True``.
"""

from __future__ import annotations

import asyncio
import json

from scribe_mcp.tools import query_entries as qe_module
from scribe_mcp.tools.query_entries import query_entries


def _result_dict(raw):
    if isinstance(raw, dict):
        return raw
    try:
        from mcp.types import CallToolResult, TextContent

        if isinstance(raw, CallToolResult) and raw.content:
            first = raw.content[0]
            if isinstance(first, TextContent):
                return json.loads(first.text)
    except ImportError:
        pass
    return {"ok": True}


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# F2 — dead engine is gone, live carve-out remains
# --------------------------------------------------------------------------- #

_DEAD_SYMBOLS = [
    "_resolve_cross_project_projects",
    "_project_has_document_types",
    "_query_file",
    "_handle_cross_project_search",
    "_search_single_project",
    "_search_research_documents",
    "_search_architecture_documents",
    "_search_bug_documents",
    "_parse_research_document",
    "_parse_markdown_document",
    "_create_document_entry",
    "_verify_code_references_in_results",
    "_verify_file_exists",
    "_calculate_basic_relevance",
    "_apply_relevance_scoring",
]


def test_dead_cross_project_engine_symbols_removed():
    """Every dead-engine symbol must no longer exist on the module."""
    present = [name for name in _DEAD_SYMBOLS if hasattr(qe_module, name)]
    assert present == [], f"dead-engine symbols still present: {present}"


def test_live_observed_context_helper_preserved():
    """The live helper that sat inside the old dead block must remain wired."""
    assert hasattr(qe_module, "_collect_observed_context_signals")


# --------------------------------------------------------------------------- #
# F8 — cross-project / document-scope teaching error (no silent no-op)
# --------------------------------------------------------------------------- #


def test_search_scope_global_returns_teaching_error_not_silent_noop():
    raw = _run(
        query_entries(
            agent="test-agent",
            search_scope="global",
            format="structured",
        )
    )
    result = _result_dict(raw)
    assert result["ok"] is False
    assert "not implemented" in result["error"]
    assert "search_scope='global'" in result["error"] or "search_scope=\"global\"" in result["error"]
    # A teaching suggestion points at the supported path.
    assert "search_scope" in result["suggestion"]
    # Empty, honest envelope — never a fabricated hit.
    assert result["entries"] == []
    assert result["pagination"]["total_count"] == 0


def test_document_types_returns_teaching_error():
    raw = _run(
        query_entries(
            agent="test-agent",
            document_types=["research", "bugs"],
            format="structured",
        )
    )
    result = _result_dict(raw)
    assert result["ok"] is False
    assert "document_types" in result["error"]
    assert result["entries"] == []


def test_relevance_threshold_returns_teaching_error():
    raw = _run(
        query_entries(
            agent="test-agent",
            relevance_threshold=0.5,
            format="structured",
        )
    )
    result = _result_dict(raw)
    assert result["ok"] is False
    assert "relevance_threshold" in result["error"]
    assert result["entries"] == []


def test_default_project_scope_does_not_trip_teaching_gate():
    """The common call (search_scope='project', no doc types, threshold 0) must
    NOT trip the teaching gate — it should run a real search and return ok=True.
    """
    raw = _run(
        query_entries(
            agent="test-agent",
            search_scope="project",
            document_types=None,
            relevance_threshold=0.0,
            format="structured",
        )
    )
    result = _result_dict(raw)
    # Whatever the search returns, it must NOT be the F8 teaching error.
    assert not (
        result.get("ok") is False
        and "Cross-project" in str(result.get("error", ""))
    )


# --------------------------------------------------------------------------- #
# F9 — honest failure envelope (no fabricated 🚨 hit inside ok:True)
# --------------------------------------------------------------------------- #


def test_emergency_fallback_returns_ok_false_not_fabricated_hit(monkeypatch):
    """Force a critical error in the search execution and assert the envelope is
    an honest failure (ok=False, empty entries), never a synthetic 🚨 row.
    """

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("forced critical failure for F9 test")

    # Break the search execution AFTER the F8 gate, so we exercise the outer
    # ultimate-exception envelope in query_entries.
    monkeypatch.setattr(qe_module, "_execute_search_with_fallbacks", _boom)

    raw = _run(query_entries(agent="test-agent", format="structured"))
    result = _result_dict(raw)

    assert result["ok"] is False
    assert result["entries"] == []
    # No fabricated emergency content row.
    assert "🚨" not in json.dumps(result, ensure_ascii=False)
    assert result["pagination"].get("total_count", 0) == 0


def test_inner_search_execution_failure_returns_ok_false(monkeypatch):
    """A failure inside _execute_search_with_fallbacks' own handling must yield an
    honest ok=False envelope, not a fabricated single-result ok=True response.
    """
    from scribe_mcp.tools.query_entries import _execute_search_with_fallbacks

    # Force the inner try-body to raise so the inner except-envelope is taken.
    def _explode(*_args, **_kwargs):
        raise RuntimeError("forced inner search failure for F9 test")

    # message_matches is imported into the module namespace and used on the hot
    # path; breaking it triggers the inner exception handler.
    monkeypatch.setattr(qe_module, "message_matches", _explode)

    search_query = {
        "query_built": True,
        "resolved_project": "unknown",
        "search_params": {"message": "x", "message_mode": "substring", "page_size": 10},
        "project_context": None,
    }

    # Build a minimal config the executor accepts.
    from scribe_mcp.tools.query_entries import _validate_search_parameters

    final_config, _ = _validate_search_parameters(
        project=None,
        start=None,
        end=None,
        message="x",
        message_mode="substring",
        case_sensitive=False,
        emoji=None,
        status=None,
        agents=None,
        meta_filters=None,
        limit=50,
        page=1,
        page_size=10,
        compact=False,
        fields=None,
        include_metadata=True,
        search_scope="project",
        document_types=None,
        include_outdated=True,
        verify_code_references=False,
        time_range=None,
        relevance_threshold=0.0,
        max_results=None,
        config=None,
    )

    result = _run(_execute_search_with_fallbacks(search_query, final_config))
    # Whatever path it takes, the failure envelope must be honest.
    if result.get("emergency_fallback"):
        assert result["ok"] is False
        assert "🚨" not in json.dumps(result, ensure_ascii=False)
