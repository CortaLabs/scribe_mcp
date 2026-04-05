"""Deprecated import shim for the optional `scribe-council` template provider.

Removal target: the next breaking release and no later than v3.
Install `scribe-council` and import `scribe_council.council_templates` instead.
"""
from __future__ import annotations

import warnings
from typing import Any

_DEPRECATION_MESSAGE = (
    "scribe_mcp.council_templates is deprecated and will be removed in the next "
    "breaking release and no later than v3. Install `scribe-council` and import "
    "`scribe_council.council_templates` instead."
)

def get_council_templates() -> dict[str, Any]:
    """Forward legacy imports to the extension package with a deprecation warning."""
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)

    from scribe_council.council_templates import (
        get_council_templates as extension_get_council_templates,
    )

    return extension_get_council_templates()


__all__ = ["get_council_templates"]
