from __future__ import annotations

from dataclasses import dataclass
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

    def offset_in_scope(self, offset: int, *, kind: str) -> bool:
        return any(scope.kind == kind and scope.contains_offset(offset) for scope in self.scopes)


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
        )
