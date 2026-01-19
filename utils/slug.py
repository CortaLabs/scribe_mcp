"""Canonical slugify functions for Scribe MCP.

This module is designed for early import safety - no dependencies on
tools/, config/, or other modules that may cause circular imports.
"""
from __future__ import annotations

import re
from typing import Optional

_SLUG_CLEANER = re.compile(r"[^0-9a-z_]+")
_FILENAME_CLEANER = re.compile(r"[^\w\-.]+")
_UNDERSCORE_COLLAPSE = re.compile(r"_+")


def slugify_project_name(name: str) -> str:
    """Return a filesystem-friendly slug for project names.

    - Converts to lowercase
    - Replaces spaces and hyphens with underscores
    - Removes all non-alphanumeric chars except underscores
    - Strips leading/trailing underscores
    - Returns "project" if result is empty

    Examples:
        >>> slugify_project_name("My Project")
        'my_project'
        >>> slugify_project_name("manage-docs-fix")
        'manage_docs_fix'
        >>> slugify_project_name("My-Project Name")
        'my_project_name'
        >>> slugify_project_name("")
        'project'
    """
    normalised = name.strip().lower().replace(" ", "_").replace("-", "_")
    return _SLUG_CLEANER.sub("_", normalised).strip("_") or "project"


def normalize_project_input(name: Optional[str]) -> Optional[str]:
    """Normalize project name input, accepting any reasonable format.

    This is the canonical entry-point normalizer. Use at tool boundaries
    to accept hyphens, underscores, spaces, or mixed case.

    Args:
        name: Project name in any format, or None

    Returns:
        Canonical slugified name, or None if input was None/empty

    Examples:
        >>> normalize_project_input("My-Project")
        'my_project'
        >>> normalize_project_input("my_project")
        'my_project'
        >>> normalize_project_input("MY PROJECT")
        'my_project'
        >>> normalize_project_input(None)
        None
        >>> normalize_project_input("")
        None
    """
    if name is None:
        return None
    stripped = str(name).strip()
    if not stripped:
        return None
    return slugify_project_name(stripped)


def slugify_filename(value: str) -> str:
    """Return a filesystem-friendly slug for document filenames.

    - Allows alphanumeric, underscores, hyphens, and dots
    - Collapses multiple underscores
    - Returns "document" if result is empty

    Examples:
        >>> slugify_filename("My Document.md")
        'My_Document.md'
        >>> slugify_filename("config.yaml")
        'config.yaml'
        >>> slugify_filename("my___doc")
        'my_doc'
    """
    slug = _FILENAME_CLEANER.sub("_", value.strip())
    slug = _UNDERSCORE_COLLAPSE.sub("_", slug).strip("_")
    return slug or "document"
