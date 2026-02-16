"""Key resolution helpers for the object store layer.

Converts between filesystem paths and store keys, and determines which
paths should be synchronised to a remote object store.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

# Prefixes (relative to repo root) whose documents should be synced.
_SYNC_PREFIXES: tuple[str, ...] = (
    ".scribe/docs/dev_plans/",
    ".scribe/docs/agent_report_cards/",
    "docs/bugs/",
)

# Suffixes eligible for sync.
_SYNC_SUFFIXES: tuple[str, ...] = (".md",)

# Prefixes that must **never** be synced even if they match above.
_DENY_PREFIXES: tuple[str, ...] = (
    ".scribe/sentinel/",
    ".scribe/config/",
    ".scribe/logs/",
    ".scribe/cli/",
    ".scribe/templates/",  # Jinja2 source files
)


def path_to_key(file_path: Path | str, repo_root: Path | str) -> str:
    """Convert a filesystem path to a normalised store key.

    The leading dot in ``.scribe/`` is stripped so the key reads
    ``scribe/docs/dev_plans/...`` — safe for S3 and URL paths.
    """
    rel = Path(file_path).resolve().relative_to(Path(repo_root).resolve())
    posix = str(PurePosixPath(rel))
    if posix.startswith(".scribe/"):
        posix = "scribe/" + posix[len(".scribe/"):]
    return posix


def key_to_path(key: str, repo_root: Path | str) -> Path:
    """Inverse of :func:`path_to_key` — resolve a key back to a local path."""
    if key.startswith("scribe/"):
        key = ".scribe/" + key[len("scribe/"):]
    return Path(repo_root).resolve() / key


def should_sync(file_path: Path | str, repo_root: Path | str) -> bool:
    """Return ``True`` when *file_path* should be pushed to remote storage."""
    try:
        rel = str(
            PurePosixPath(Path(file_path).resolve().relative_to(Path(repo_root).resolve()))
        )
    except ValueError:
        return False

    # Explicit deny list takes priority.
    for dp in _DENY_PREFIXES:
        if rel.startswith(dp):
            return False

    # Must be under a sync prefix *and* have an eligible suffix.
    for sp in _SYNC_PREFIXES:
        if rel.startswith(sp):
            return any(rel.endswith(s) for s in _SYNC_SUFFIXES)

    # Also catch review docs nested under dev_plans
    if rel.startswith(".scribe/docs/") and "/reviews/" in rel:
        return any(rel.endswith(s) for s in _SYNC_SUFFIXES)

    return False
