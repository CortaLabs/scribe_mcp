"""Status-update action wrapper for manage_docs decomposition."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .edit import handle_edit_action


async def handle_status_action(**kwargs: Any) -> Optional[Dict[str, Any]]:
    """Handle status_update action via shared edit-action pipeline."""
    if kwargs.get("action") != "status_update":
        return None
    return await handle_edit_action(**kwargs)
