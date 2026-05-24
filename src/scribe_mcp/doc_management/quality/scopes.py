from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass(frozen=True)
class DocumentScope:
    kind: str
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int
    container_chain: tuple[str, ...] = field(default_factory=tuple)
    attributes: dict[str, str] = field(default_factory=dict)

    def contains_offset(self, offset: int) -> bool:
        return self.start_offset <= offset < self.end_offset


class ScopeProvider(Protocol):
    backend_name: str

    def collect_scopes(self, body: str) -> Sequence[DocumentScope]:
        ...


class HeuristicFenceScopeProvider:
    backend_name = "heuristic-fence-v1"

    def collect_scopes(self, body: str) -> Sequence[DocumentScope]:
        scopes: list[DocumentScope] = []
        lines = body.splitlines(keepends=True)
        line_offsets: list[int] = []
        running_offset = 0
        for raw_line in lines:
            line_offsets.append(running_offset)
            running_offset += len(raw_line)
        offset = 0
        active: tuple[str, int, int] | None = None
        start_line = 1
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip("\n")
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            marker = ""
            fence_len = 0
            if indent <= 3 and stripped.startswith("`"):
                fence_len = len(stripped) - len(stripped.lstrip("`"))
                marker = "`" if fence_len >= 3 else ""
            if indent <= 3 and not marker and stripped.startswith("~"):
                fence_len = len(stripped) - len(stripped.lstrip("~"))
                marker = "~" if fence_len >= 3 else ""

            if marker and fence_len >= 3:
                if active is None:
                    active = (marker, fence_len, offset)
                    start_line = line_no
                else:
                    active_marker, active_len, start_offset = active
                    if marker == active_marker and fence_len >= active_len:
                        end_offset = offset + len(raw_line)
                        scopes.append(
                            DocumentScope(
                                kind="fenced_code",
                                start_line=start_line,
                                end_line=line_no,
                                start_offset=start_offset,
                                end_offset=end_offset,
                                attributes={"fence_marker": marker, "fence_length": str(active_len)},
                            )
                        )
                        active = None
            offset += len(raw_line)

        if active is not None:
            marker, fence_len, start_offset = active
            scopes.append(
                DocumentScope(
                    kind="fenced_code",
                    start_line=start_line,
                    end_line=max(start_line, body.count("\n") + 1),
                    start_offset=start_offset,
                    end_offset=len(body),
                    attributes={"fence_marker": marker, "fence_length": str(fence_len), "unclosed": "true"},
                )
            )
        # Inline code spans: suppress placeholder/lifecycle checks inside `...`.
        for match in re.finditer(r"`[^`\n]+`", body):
            start_offset, end_offset = match.span()
            start_line = body.count("\n", 0, start_offset) + 1
            end_line = body.count("\n", 0, max(start_offset, end_offset - 1)) + 1
            scopes.append(
                DocumentScope(
                    kind="inline_code",
                    start_line=start_line,
                    end_line=end_line,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            )

        # Indented code blocks (CommonMark): consecutive non-blank lines with >=4 spaces.
        in_indented = False
        block_start_line = 0
        block_start_offset = 0
        block_end_line = 0
        block_end_offset = 0
        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip("\n")
            is_blank = line.strip() == ""
            is_indented = line.startswith("    ") and not is_blank
            if is_indented and not in_indented:
                in_indented = True
                block_start_line = idx
                block_start_offset = line_offsets[idx - 1]
            if in_indented:
                if is_indented:
                    block_end_line = idx
                    block_end_offset = line_offsets[idx - 1] + len(raw_line)
                elif is_blank:
                    block_end_line = idx
                    block_end_offset = line_offsets[idx - 1] + len(raw_line)
                else:
                    scopes.append(
                        DocumentScope(
                            kind="indented_code",
                            start_line=block_start_line,
                            end_line=block_end_line,
                            start_offset=block_start_offset,
                            end_offset=block_end_offset,
                        )
                    )
                    in_indented = False
        if in_indented:
            scopes.append(
                DocumentScope(
                    kind="indented_code",
                    start_line=block_start_line,
                    end_line=block_end_line,
                    start_offset=block_start_offset,
                    end_offset=block_end_offset,
                )
            )
        return scopes


class MarkdownItScopeProvider(HeuristicFenceScopeProvider):
    backend_name = "markdown-it-py"

    def __init__(self) -> None:
        from markdown_it import MarkdownIt

        self._md = MarkdownIt("commonmark")

    def collect_scopes(self, body: str) -> Sequence[DocumentScope]:
        tokens = self._md.parse(body)
        lines = body.splitlines(keepends=True)
        line_offsets: list[int] = []
        running_offset = 0
        for raw_line in lines:
            line_offsets.append(running_offset)
            running_offset += len(raw_line)

        scopes: list[DocumentScope] = []
        for token in tokens:
            token_map = getattr(token, "map", None)
            if not isinstance(token_map, list) or len(token_map) < 2:
                continue
            start_line = max(1, int(token_map[0]) + 1)
            end_line = max(start_line, int(token_map[1]))
            if start_line - 1 >= len(line_offsets):
                continue
            start_offset = line_offsets[start_line - 1]
            if end_line <= len(line_offsets):
                end_offset = line_offsets[end_line - 1]
            else:
                end_offset = len(body)

            if token.type == "fence":
                source_line = lines[start_line - 1] if start_line - 1 < len(lines) else ""
                if source_line.lstrip().startswith(">"):
                    continue
                scopes.append(
                    DocumentScope(
                        kind="fenced_code",
                        start_line=start_line,
                        end_line=end_line,
                        start_offset=start_offset,
                        end_offset=end_offset,
                        attributes={
                            "fence_marker": str(getattr(token, "markup", "")[:1] or ""),
                            "fence_length": str(len(str(getattr(token, "markup", "")))),
                            "token_source": "markdown-it-py",
                        },
                    )
                )
            elif token.type == "code_block":
                scopes.append(
                    DocumentScope(
                        kind="indented_code",
                        start_line=start_line,
                        end_line=end_line,
                        start_offset=start_offset,
                        end_offset=end_offset,
                        attributes={"token_source": "markdown-it-py"},
                    )
                )

        for token in tokens:
            if token.type != "inline":
                continue
            search_cursor = 0
            token_map = getattr(token, "map", None)
            search_start = 0
            search_end = len(body)
            if isinstance(token_map, list) and len(token_map) >= 2:
                token_start_line = int(token_map[0])
                token_end_line = int(token_map[1])
                if 0 <= token_start_line < len(line_offsets):
                    search_start = line_offsets[token_start_line]
                if 0 <= token_end_line < len(line_offsets):
                    search_end = line_offsets[token_end_line]
            for child in token.children or []:
                if child.type != "code_inline":
                    continue
                content = str(getattr(child, "content", "") or "")
                if not content:
                    continue
                seek = f"`{content}`"
                pos = body.find(seek, max(search_start, search_cursor), search_end)
                if pos == -1:
                    pos = body.find(seek, search_cursor)
                if pos == -1:
                    pos = body.find(seek, search_start)
                if pos == -1:
                    continue
                search_cursor = pos + len(seek)
                scopes.append(
                    DocumentScope(
                        kind="inline_code",
                        start_line=body.count("\n", 0, pos) + 1,
                        end_line=body.count("\n", 0, pos + len(seek) - 1) + 1,
                        start_offset=pos,
                        end_offset=pos + len(seek),
                        attributes={"token_source": "markdown-it-py"},
                    )
                )

        heuristic_scopes = list(super().collect_scopes(body))
        if not scopes:
            return heuristic_scopes
        if not any(scope.attributes.get("unclosed") == "true" for scope in scopes):
            scopes.extend(scope for scope in heuristic_scopes if scope.attributes.get("unclosed") == "true")
        scopes.extend(scope for scope in heuristic_scopes if scope.kind == "indented_code")
        return scopes


def create_scope_provider() -> ScopeProvider:
    try:
        return MarkdownItScopeProvider()
    except Exception:
        return HeuristicFenceScopeProvider()
