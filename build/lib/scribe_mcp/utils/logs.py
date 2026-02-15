"""Helpers for working with progress log files."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_LINE_PATTERN = re.compile(
    r"^\[(?P<emoji>.+?)\]\s+\[(?P<timestamp>.+?)\]\s+\[Agent: (?P<agent>.+?)\]\s+\[Project: (?P<project>.+?)\]\s+(?P<message>.*?)(?:\s+\|\s+(?P<meta>.+))?$"
)


def _is_template_entry(timestamp: str, emoji: str, agent: str, message: str) -> bool:
    """Check if entry is a template/placeholder (requires 2+ indicators)."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Structural indicators suggest template formatting
    structural_indicators = ["YYYY-MM-DD", "HH:MM:SS", "<name>", "EMOJI"]
    
    # Content indicators suggest placeholder content
    content_indicators = ["Message text", "key=value", "placeholder", "example"]

    combined_text = f"{timestamp} {emoji} {agent} {message}".lower()
    
    # Count indicators in each category
    structural_count = sum(1 for ind in structural_indicators if ind.lower() in combined_text)
    content_count = sum(1 for ind in content_indicators if ind.lower() in combined_text)
    
    # Require multiple indicators to filter
    is_template = structural_count >= 2 or (structural_count >= 1 and content_count >= 2)
    
    if is_template:
        logger.debug(f"Filtered template entry: {message[:100]}...")
    
    return is_template


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a canonical Scribe log line into structured fields."""
    match = LOG_LINE_PATTERN.match(line.strip())
    if not match:
        return None

    timestamp = match.group("timestamp")
    emoji = match.group("emoji")
    agent = match.group("agent")
    message = match.group("message")

    # Filter out template/example entries
    if _is_template_entry(timestamp, emoji, agent, message):
        return None

    meta_text = match.group("meta")
    meta: Dict[str, str] = {}
    if meta_text:
        for chunk in meta_text.split(";"):
            key, value = _split_meta_chunk(chunk)
            if key:
                meta[key] = value
    return {
        "ts": timestamp,
        "emoji": emoji,
        "agent": agent,
        "project": match.group("project"),
        "message": message,
        "meta": meta,
        "raw_line": line.strip(),
    }


def _split_meta_chunk(chunk: str) -> tuple[str, str]:
    piece = chunk.strip()
    if not piece:
        return "", ""
    if "=" not in piece:
        return piece, ""
    key, value = piece.split("=", 1)
    return key.strip(), value.strip()


async def read_all_lines(path: Path) -> List[str]:
    """Read the entire file (or empty list on missing) without blocking the loop."""
    return await asyncio.to_thread(_read_lines, path)


def _read_lines(path: Path) -> List[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle]
    except FileNotFoundError:
        return []
