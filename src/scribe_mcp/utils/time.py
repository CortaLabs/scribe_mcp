"""Time helpers for Scribe MCP server."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def format_utc(dt: datetime | None = None) -> str:
    """Format the provided datetime (or now) as canonical UTC string."""
    target = dt or utcnow()
    return target.strftime("%Y-%m-%d %H:%M:%S UTC")


def parse_utc(value: str) -> Optional[datetime]:
    """Parse a UTC timestamp or date string into an aware datetime."""
    candidate = value.strip()
    if not candidate:
        return None

    # Handle ISO8601 (with optional Z suffix)
    iso_candidate = candidate.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = _parse_with_known_formats(candidate)

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def coerce_range_boundary(value: str, *, end: bool = False) -> Optional[datetime]:
    """Normalise a timestamp/date string into a UTC datetime for range queries."""
    parsed = parse_utc(value)
    if parsed is None:
        return None

    if not _has_time_component(value):
        if end:
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed


def _parse_with_known_formats(value: str) -> Optional[datetime]:
    known_formats = [
        "%Y-%m-%d %H:%M:%S UTC",
        "%Y-%m-%d %H:%M UTC",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in known_formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if "UTC" in fmt:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _has_time_component(value: str) -> bool:
    inspected = value.strip()
    if "T" in inspected or ":" in inspected:
        return True
    parts = inspected.split()
    if len(parts) > 1:
        return True
    return False
