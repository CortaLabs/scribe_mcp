"""Template provider for the optional `scribe-council` distribution."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def get_council_templates() -> dict[str, Any]:
    """Return the council template manifest for the extension package."""
    pkg_dir = Path(__file__).parent
    rules_dir = pkg_dir / "rules"
    skills_dir = pkg_dir / "skills"

    return {
        "package_name": "scribe-council",
        "package_version": _get_version(),
        "rules_dir": str(rules_dir) if rules_dir.is_dir() else None,
        "skills_dir": str(skills_dir) if skills_dir.is_dir() else None,
    }


def _get_version() -> str:
    """Get the installed package version safely."""
    try:
        from importlib.metadata import version

        return version("scribe-council")
    except Exception:
        return "0.0.0"


__all__ = ["get_council_templates"]
