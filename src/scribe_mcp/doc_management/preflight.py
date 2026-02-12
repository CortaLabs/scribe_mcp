"""Preflight helpers for backup/repair operations before doc writes."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from scribe_mcp.utils.files import preflight_backup


logger = logging.getLogger(__name__)


async def create_preflight_backup(path: Path, *, repo_root: Path) -> Optional[Path]:
    """Create a preflight backup with built-in retention handling."""
    if not path.exists():
        return None
    return await asyncio.to_thread(preflight_backup, path, repo_root=repo_root)


def write_file_atomically(file_path: Path, content: str) -> bool:
    """Write file atomically via temp file replacement."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(content)

        if temp_path.exists() and temp_path.stat().st_size >= 0:
            temp_path.replace(file_path)
            return True

        logger.warning("Failed to write %s: temporary file not created properly", file_path)
        if temp_path.exists():
            temp_path.unlink()
        return False
    except (OSError, IOError) as exc:
        logger.warning("Failed to write %s: %s", file_path, exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error writing %s: %s", file_path, exc)
        return False


def validate_and_repair_index(index_path: Path, doc_dir: Path) -> bool:
    """Validate an index file and signal whether regeneration is required."""
    try:
        if not index_path.exists():
            logger.debug("Index file %s missing, will create new one", index_path.name)
            return False

        try:
            content = index_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IOError) as exc:
            logger.debug("Index file %s corrupted (%s), will repair", index_path.name, exc)
            backup_path = index_path.with_suffix(".corrupted.backup")
            if index_path.exists():
                index_path.rename(backup_path)
            return False

        if not content.strip().startswith("#"):
            logger.debug("Index file %s invalid, will repair", index_path.name)
            backup_path = index_path.with_suffix(".invalid.backup")
            index_path.rename(backup_path)
            return False

        if doc_dir.exists():
            actual_docs = [
                doc
                for doc in doc_dir.glob("*.md")
                if doc.name != "INDEX.md" and not doc.name.startswith("_")
            ]
            if "Total Documents:** 0" in content and actual_docs:
                logger.debug(
                    "Index file %s stale (shows 0 docs but %d found), will repair",
                    index_path.name,
                    len(actual_docs),
                )
                return False

        return True
    except Exception as exc:
        logger.debug("Error validating index %s: %s, will repair", index_path.name, exc)
        return False
