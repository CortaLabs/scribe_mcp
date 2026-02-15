"""Action routing helpers for manage_docs decomposition."""

from .append import handle_append_action
from .batch import handle_batch_action
from .create import normalize_or_handle_create_action
from .edit import handle_edit_action
from .query import handle_query_actions, handle_query_transform_actions
from .search import handle_search_action
from .status import handle_status_action

__all__ = [
    "handle_append_action",
    "handle_batch_action",
    "handle_edit_action",
    "handle_query_actions",
    "handle_search_action",
    "handle_status_action",
    "normalize_or_handle_create_action",
]
