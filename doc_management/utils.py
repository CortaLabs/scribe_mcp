"""Shared utility helpers for doc management actions."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.utils.time import format_utc


def hash_text(content: str) -> str:
    """Return a deterministic hash for document content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _split_into_sections(raw: str) -> List[str]:
    lines = raw.splitlines()
    sections: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line.lstrip().startswith("#"):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    return [
        "\n".join(section).strip()
        for section in sections
        if "\n".join(section).strip()
    ]


def _split_section(section: str, max_chars: int) -> List[str]:
    section = section.strip()
    if not section:
        return []
    if len(section) <= max_chars:
        return [section]

    lines = section.splitlines()
    heading = lines[0].strip() if lines and lines[0].lstrip().startswith("#") else None
    body = "\n".join(lines[1:]).strip() if heading else section
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: List[str] = []
    buffer: List[str] = []
    buffer_len = 0
    header_len = len(heading) + 2 if heading else 0
    limit = max(1, max_chars - header_len)

    for paragraph in paragraphs:
        addition = len(paragraph) + (2 if buffer else 0)
        if buffer_len + addition > limit and buffer:
            chunk = "\n\n".join(buffer)
            if heading:
                chunk = f"{heading}\n\n{chunk}"
            chunks.append(chunk)
            buffer = [paragraph]
            buffer_len = len(paragraph)
            continue
        buffer.append(paragraph)
        buffer_len += addition

    if buffer:
        chunk = "\n\n".join(buffer)
        if heading:
            chunk = f"{heading}\n\n{chunk}"
        chunks.append(chunk)

    return chunks


def chunk_text_for_vector(text: str, max_chars: int = 4000) -> List[str]:
    """Chunk markdown text into stable semantic chunks for vector indexing."""
    if not text:
        return []
    sections = _split_into_sections(text)
    chunks: List[str] = []
    for section in sections:
        chunks.extend(_split_section(section, max_chars=max_chars))
    return chunks


def generate_doc_entry_id(path: Path, chunk_index: int, content_hash: str) -> str:
    """Generate a stable ID for doc-index entries."""
    seed = f"{path}|{chunk_index}|{content_hash}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def parse_int(value: Any) -> Optional[int]:
    """Parse integer-like values, returning None on invalid input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_numeric_grade(value: Any) -> Optional[float]:
    """Convert percentage-like numeric values to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        if text.endswith("%"):
            text = text[:-1]
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def build_special_metadata(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    agent_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prepare metadata payload for template rendering and storage."""
    prepared = metadata.copy()
    prepared.setdefault("project_name", project.get("name"))
    prepared.setdefault("project_root", project.get("root"))
    prepared.setdefault("agent_id", agent_id)
    prepared.setdefault("agent_name", prepared.get("agent_name", agent_id))
    prepared.setdefault("timestamp", prepared.get("timestamp", format_utc()))
    if extra:
        for key, value in extra.items():
            prepared.setdefault(key, value)
    return prepared


def resolve_custom_doc_path(
    project: Dict[str, Any],
    doc_category: str,
    doc_name: str,
) -> Optional[Path]:
    """Resolve custom document path by category and identifier."""
    progress_log = project.get("progress_log")
    if not progress_log:
        return None

    docs_dir = Path(progress_log).parent
    project_root = Path(project.get("root", ""))

    if doc_category == "research":
        research_dir = docs_dir / "research"
        if not research_dir.exists():
            return None

        candidate = research_dir / f"{doc_name}.md"
        if candidate.exists():
            return candidate

        if doc_name.endswith(".md"):
            candidate = research_dir / doc_name
            if candidate.exists():
                return candidate
        return None

    if doc_category == "bugs":
        bugs_root = project_root / "docs" / "bugs"
        if not bugs_root.exists():
            return None
        for category_dir in bugs_root.iterdir():
            if not category_dir.is_dir():
                continue
            for bug_dir in category_dir.iterdir():
                if not bug_dir.is_dir():
                    continue
                if bug_dir.name.endswith(f"_{doc_name}") or doc_name in bug_dir.name:
                    report_file = bug_dir / "report.md"
                    if report_file.exists():
                        return report_file
        return None

    if doc_category == "reviews":
        pattern = f"REVIEW_REPORT_*{doc_name}*.md"
        candidates = list(docs_dir.glob(pattern))
        if candidates:
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    if doc_category == "agent_cards":
        pattern = f"AGENT_REPORT_CARD_*{doc_name}*.md"
        candidates = list(docs_dir.glob(pattern))
        if candidates:
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    return None
