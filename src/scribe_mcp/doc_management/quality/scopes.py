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
        # markdown-it token map yields stable line ranges; use heuristic fallback for offset-precise fences.
        _ = self._md.parse(body)
        return super().collect_scopes(body)


def create_scope_provider() -> ScopeProvider:
    try:
        return MarkdownItScopeProvider()
    except Exception:
        return HeuristicFenceScopeProvider()
