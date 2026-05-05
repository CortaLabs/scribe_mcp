"""Naming helpers for document creation flows."""

from __future__ import annotations

import re
from datetime import datetime


def normalize_research_doc_name(doc_name: str) -> str:
    """Normalize research artifact names to a stable single .md suffix."""
    normalized = str(doc_name or "").strip()
    normalized = re.sub(r"(?i)^research_(?=RESEARCH_)", "", normalized)
    while normalized.lower().endswith(".md"):
        normalized = normalized[:-3]
    safe_name = re.sub(r"[^\w\-_.]", "_", normalized)
    safe_name = re.sub(r"_+", "_", safe_name).strip("_")
    if not safe_name:
        safe_name = f"research_{int(datetime.now().timestamp())}"
    return safe_name
