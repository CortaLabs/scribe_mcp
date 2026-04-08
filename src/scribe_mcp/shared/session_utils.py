"""
Session utilities for canonical session key derivation.

This module provides the SINGLE SOURCE OF TRUTH for deriving session keys
across all Scribe MCP operations. This fixes the session isolation bug where
different components used different fallback chains, causing session-to-project
binding mismatches.

CRITICAL: All code that needs a session key MUST use get_canonical_session_key().
DO NOT derive session keys inline anywhere else in the codebase.
"""

from typing import Optional
from scribe_mcp.shared.execution_context import ExecutionContext


def get_canonical_session_key(exec_context: Optional[ExecutionContext]) -> Optional[str]:
    """
    Return THE canonical session key for this execution context.

    This is the single source of truth for session key derivation.
    Used by both set_project (binding) and logging_utils (resolution).

    Precedence (CRITICAL - this order is the contract):
    1. stable_session_id (preferred - deterministic, from agent_sessions table)
    2. session_id (fallback - may be unstable UUID depending on context)
    3. None (no context available)

    Args:
        exec_context: The execution context from MCP request, or None

    Returns:
        Session key string, or None if no context available

    Note:
        We do NOT include context_session_id or transport_session_id in the
        fallback chain because they are unstable across requests. Only
        stable_session_id and session_id are safe for binding.
    """
    if not exec_context:
        return None

    # Prefer stable_session_id (deterministic from agent_sessions table)
    if hasattr(exec_context, "stable_session_id") and exec_context.stable_session_id:
        return exec_context.stable_session_id

    # Fallback to session_id (execution-level session)
    if hasattr(exec_context, "session_id") and exec_context.session_id:
        return exec_context.session_id

    # No valid session key available
    return None


def validate_session_key_consistency(
    binding_key: Optional[str],
    resolution_key: Optional[str],
    operation: str = "unknown"
) -> None:
    """
    Validate that session key used for binding matches the one used for resolution.

    This catches bugs where set_project binds with one key but logging_utils
    resolves with a different key, causing silent cross-project logging.

    Args:
        binding_key: Session key that was used to bind session to project
        resolution_key: Session key being used to resolve project
        operation: Name of operation for error messages

    Raises:
        ValueError: If keys don't match (indicating a session isolation bug)
    """
    if binding_key and resolution_key and binding_key != resolution_key:
        raise ValueError(
            f"Session key mismatch in {operation}: "
            f"binding_key={binding_key!r} != resolution_key={resolution_key!r}. "
            f"This indicates a session isolation bug - different components are using "
            f"different fallback chains for session key derivation."
        )
