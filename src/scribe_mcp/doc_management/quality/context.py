from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from scribe_mcp.doc_management.quality.scopes import DocumentScope, ScopeProvider, create_scope_provider
from scribe_mcp.utils.frontmatter import parse_frontmatter


@dataclass(frozen=True)
class DocumentContext:
    raw_text: str
    body_text: str
    frontmatter_data: dict[str, Any]
    doc_name: Optional[str]
    resolved_path: Optional[Path]
    mode: str
    content_hash: str
    parser_backend: str
    scopes: tuple[DocumentScope, ...]
    # Per-kind interval index for O(log S) containment checks. Maps a scope kind
    # to (sorted start offsets, prefix-max of end offsets). Replaces the previous
    # O(S) ``any(... for scope in self.scopes)`` scan, which became O(P x S) ->
    # O(N^2) on large docs with many code scopes.
    scope_index: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = field(
        default_factory=dict, compare=False, hash=False, repr=False
    )

    def offset_in_scope(self, offset: int, *, kind: str) -> bool:
        index = self.scope_index.get(kind)
        if not index:
            return False
        starts, prefix_max_end = index
        # Last interval of this kind whose start <= offset; if the running max
        # end across those intervals exceeds offset, some interval contains it
        # (start <= offset < end). Overlap-safe, O(log S).
        i = bisect_right(starts, offset) - 1
        return i >= 0 and prefix_max_end[i] > offset


class DocumentContextBuilder:
    def __init__(self, provider: ScopeProvider | None = None) -> None:
        self._provider = provider or create_scope_provider()

    def build(
        self,
        *,
        text: str,
        doc_name: Optional[str] = None,
        path: str | Path | None = None,
        mode: str = "local_default",
        content_hash: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> DocumentContext:
        _ = metadata
        parsed = parse_frontmatter(text)
        body = parsed.body
        scopes = tuple(self._provider.collect_scopes(body))
        return DocumentContext(
            raw_text=text,
            body_text=body,
            frontmatter_data=dict(parsed.frontmatter_data),
            doc_name=doc_name,
            resolved_path=Path(path).resolve() if path is not None else None,
            mode=mode,
            content_hash=content_hash,
            parser_backend=self._provider.backend_name,
            scopes=scopes,
            scope_index=_build_scope_index(scopes),
        )


def _build_scope_index(
    scopes: tuple[DocumentScope, ...],
) -> dict[str, tuple[tuple[int, ...], tuple[int, ...]]]:
    """Build a per-kind interval index for O(log S) offset-containment queries.

    For each scope kind, intervals are sorted by start offset and a prefix maximum
    of end offsets is precomputed. A query offset is contained iff the last
    interval whose start <= offset has a running max end > offset. This is
    overlap-safe and replaces the previous O(S)-per-query linear scan.
    """
    by_kind: dict[str, list[tuple[int, int]]] = {}
    for scope in scopes:
        by_kind.setdefault(scope.kind, []).append((scope.start_offset, scope.end_offset))
    index: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {}
    for kind, intervals in by_kind.items():
        intervals.sort()
        starts: list[int] = []
        prefix_max_end: list[int] = []
        running_max = -1
        for start, end in intervals:
            running_max = end if end > running_max else running_max
            starts.append(start)
            prefix_max_end.append(running_max)
        index[kind] = (tuple(starts), tuple(prefix_max_end))
    return index
