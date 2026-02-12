"""YAML frontmatter parsing and preservation utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import yaml


FRONTMATTER_BOUNDARY = "---"
FRONTMATTER_RE = re.compile(r"^---\s*$")


@dataclass
class FrontmatterResult:
    has_frontmatter: bool
    frontmatter_raw: str
    frontmatter_data: Dict[str, Any]
    body: str


def parse_frontmatter(text: str) -> FrontmatterResult:
    """Parse YAML frontmatter from the top of a document."""
    lines = text.splitlines(keepends=True)
    if not lines or not FRONTMATTER_RE.match(lines[0].strip()):
        return FrontmatterResult(False, "", {}, text)

    end_index = None
    for idx in range(1, len(lines)):
        if FRONTMATTER_RE.match(lines[idx].strip()):
            end_index = idx
            break
    if end_index is None:
        raise ValueError("FRONTMATTER_PARSE_ERROR: missing closing '---' delimiter")

    frontmatter_lines = lines[: end_index + 1]
    body_lines = lines[end_index + 1 :]
    frontmatter_content = "".join(lines[1:end_index])
    if frontmatter_content:
        # Remove YAML document end markers that can break parsing mid-frontmatter.
        sanitized_lines = []
        for line in frontmatter_content.splitlines(keepends=True):
            if line.strip() == "...":
                continue
            sanitized_lines.append(line)
        frontmatter_content = "".join(sanitized_lines)
    try:
        data = yaml.safe_load(frontmatter_content) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"FRONTMATTER_PARSE_ERROR: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("FRONTMATTER_PARSE_ERROR: frontmatter must be a mapping")

    return FrontmatterResult(
        has_frontmatter=True,
        frontmatter_raw="".join(frontmatter_lines),
        frontmatter_data=data,
        body="".join(body_lines),
    )


def _format_yaml_scalar(value: Any) -> str:
    rendered = yaml.safe_dump(
        value,
        default_flow_style=True,
        sort_keys=False,
        explicit_end=False,
    )
    return rendered.strip()


def _rewrite_frontmatter_block(data: Dict[str, Any]) -> str:
    rendered = yaml.safe_dump(data, sort_keys=False, explicit_end=False)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return f"{FRONTMATTER_BOUNDARY}\n{rendered}{FRONTMATTER_BOUNDARY}\n"


def apply_frontmatter_updates(
    frontmatter_raw: str,
    data: Dict[str, Any],
    updates: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Apply updates to frontmatter while preserving original formatting when possible."""
    if not updates:
        return frontmatter_raw, data

    complex_update = any(isinstance(value, (list, dict)) for value in updates.values())
    merged = dict(data)
    merged.update(updates)
    if complex_update:
        return _rewrite_frontmatter_block(merged), merged

    lines = frontmatter_raw.splitlines(keepends=True)
    if not lines:
        return frontmatter_raw, merged

    content_lines = [line for line in lines[1:-1] if line.strip() != "..."]
    keys_remaining = dict(updates)
    for idx, line in enumerate(content_lines):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        for key in list(keys_remaining.keys()):
            if stripped.startswith(f"{key}:"):
                value = _format_yaml_scalar(keys_remaining[key])
                content_lines[idx] = f"{indent}{key}: {value}\n"
                keys_remaining.pop(key, None)
                break

    if keys_remaining:
        for key, value in keys_remaining.items():
            content_lines.append(f"{key}: {_format_yaml_scalar(value)}\n")

    new_raw = "".join([lines[0]] + content_lines + [lines[-1]])
    return new_raw, merged


def build_frontmatter(
    data: Dict[str, Any],
) -> str:
    """Build a frontmatter block from data."""
    return _rewrite_frontmatter_block(data)
