"""Bounded-op regression guards for the doc-quality O(N^2) fixes.

Two latent O(N^2) defects made managed-doc quality checks ~18s on a single
18k-line furnace document:

1. ``quality/scopes.py`` computed line numbers with ``body.count("\\n", 0, off)``
   once per inline-code span -> O(L) per span -> O(N^2). Fixed by precomputing
   ``line_offsets`` once and using ``bisect_right`` (O(log L) per span).
2. ``quality/context.py`` ``offset_in_scope`` did ``any(... for scope in
   self.scopes)`` -> O(S) per query, called per candidate -> O(P x S). Fixed
   with a per-kind sorted interval index queried via ``bisect`` (O(log S)).

These tests assert OPERATION COUNTS independent of document size, not wall-clock,
so a reintroduction of either O(N^2) pattern fails deterministically.
"""

from __future__ import annotations

from bisect import bisect_right

from scribe_mcp.doc_management.quality.context import DocumentContextBuilder
from scribe_mcp.doc_management.quality.scopes import DocumentScope, create_scope_provider


def _doc_with_inline_spans(n: int) -> str:
    return "\n".join(f"para {i} has an `inline{i}` code span and text" for i in range(n))


def test_collect_scopes_does_not_str_count_per_span():
    """scopes.py must not call body.count() per inline-code span (the O(N^2) bug)."""
    counts: list[int] = []

    class CountingStr(str):
        def count(self, *args, **kwargs):  # type: ignore[override]
            counts.append(1)
            return str.count(self, *args, **kwargs)

    body = _doc_with_inline_spans(2000)
    scopes = list(create_scope_provider().collect_scopes(CountingStr(body)))
    inline = [s for s in scopes if s.kind == "inline_code"]
    assert len(inline) >= 1500, f"expected many inline spans, got {len(inline)}"

    # Old code: ~2 * len(inline) body.count calls. Fixed: bisect over precomputed
    # offsets -> count is not used per span. Bounded constant, independent of N.
    assert len(counts) < 50, (
        f"collect_scopes regressed to O(spans) str.count: "
        f"{len(counts)} count() calls for {len(inline)} inline spans"
    )


def test_collect_scopes_line_numbers_are_correct():
    """The bisect line lookup must match the exact str.count semantics."""
    body = _doc_with_inline_spans(3000)
    scopes = list(create_scope_provider().collect_scopes(body))
    inline = [s for s in scopes if s.kind == "inline_code"]
    assert len(inline) >= 2000

    offsets: list[int] = []
    running = 0
    for raw in body.splitlines(keepends=True):
        offsets.append(running)
        running += len(raw)

    for scope in inline:
        # Old semantics: body.count("\n", 0, off) + 1 == bisect_right(offsets, off)
        assert scope.start_line == bisect_right(offsets, scope.start_offset)


def test_offset_in_scope_uses_index_not_linear_scan(monkeypatch):
    """context.py offset_in_scope must not linear-scan scopes via contains_offset."""
    ctx = DocumentContextBuilder().build(text=_doc_with_inline_spans(2000), doc_name="DOC")
    assert len(ctx.scopes) >= 1500

    calls = {"n": 0}
    original = DocumentScope.contains_offset

    def spy(self, offset):
        calls["n"] += 1
        return original(self, offset)

    monkeypatch.setattr(DocumentScope, "contains_offset", spy)

    # Reference containment computed WITHOUT contains_offset (so it won't trip the spy).
    def brute(off: int, kind: str) -> bool:
        return any(
            s.kind == kind and s.start_offset <= off < s.end_offset for s in ctx.scopes
        )

    mismatches = 0
    for off in range(0, len(ctx.body_text), 37):
        if ctx.offset_in_scope(off, kind="inline_code") != brute(off, "inline_code"):
            mismatches += 1
    assert mismatches == 0, f"offset_in_scope index disagrees with linear scan ({mismatches})"

    # The fixed implementation uses the bisect index and never calls contains_offset.
    assert calls["n"] == 0, (
        f"offset_in_scope regressed to O(S) linear scan: "
        f"{calls['n']} contains_offset calls"
    )
