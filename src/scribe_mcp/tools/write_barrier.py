"""Public-safe Scribe write-barrier tool surface."""

from __future__ import annotations

from pathlib import Path

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.shared.write_barrier import (
    WriteBarrierError,
    WriteBarrierEvidence,
    read_write_barrier_state as _read_write_barrier_state,
    scribe_owned_write_barrier_lock,
)
from scribe_mcp.tool_contracts import read_only_local_tool, stateful_local_tool

_READ_OPERATION_LABEL = "read_write_barrier_state"
_PROOF_OPERATION_LABEL = "write_barrier_acquire_release_proof"
_STATE_ABSENT = "write_barrier_state:absent"
_STATE_FAILED_CLOSED = "write_barrier_state:failed_closed"
_PROOF_SUCCESS = "write_barrier_proof:acquired_and_released"
_PROOF_BLOCKED_ACTIVE = "write_barrier_proof:blocked_active"
_PROOF_FAILED_CLOSED = "write_barrier_proof:failed_closed"


def _public_response(
    *,
    status_label: str,
    lock_present: bool,
    proof_acquired: bool = False,
    proof_released: bool = False,
    operation_label: str,
    lock_fingerprint: str | None = None,
    error_class_label: str | None = None,
) -> dict[str, object]:
    return {
        "status_label": status_label,
        "lock_present": lock_present,
        "proof_acquired": proof_acquired,
        "proof_released": proof_released,
        "operation_label": operation_label,
        "lock_fingerprint": lock_fingerprint,
        "private_values_recorded": False,
        "error_class_label": error_class_label,
    }


def _evidence_response(evidence: WriteBarrierEvidence) -> dict[str, object]:
    return _public_response(
        status_label=evidence.status_label,
        lock_present=True,
        operation_label=evidence.operation_label,
        lock_fingerprint=evidence.lock_fingerprint,
    )


def _resolve_repo_root() -> Path | None:
    try:
        exec_context = server_module.get_execution_context()
    except Exception:
        return None
    if exec_context is None:
        return None

    resolved_scope = getattr(exec_context, "resolved_scope", None)
    root_value = getattr(resolved_scope, "repo_root", None) or getattr(exec_context, "repo_root", None)
    if resolved_scope is not None:
        provenance = getattr(getattr(resolved_scope, "provenance", None), "repo_root", None)
        if provenance != "verified":
            return None
    if not root_value:
        return None
    try:
        root = Path(str(root_value)).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    if not root.is_absolute():
        return None
    return root


@app.tool(**read_only_local_tool(title="Read Write Barrier State", tags=("write-barrier", "read-only")))
async def read_write_barrier_state(agent: str) -> dict[str, object]:
    """Return public-safe Scribe write-barrier state for the active repo."""
    root = _resolve_repo_root()
    if root is None:
        return _public_response(
            status_label=_STATE_FAILED_CLOSED,
            lock_present=False,
            operation_label=_READ_OPERATION_LABEL,
            error_class_label="RootResolutionError",
        )
    try:
        evidence = _read_write_barrier_state(root)
    except Exception:
        return _public_response(
            status_label=_STATE_FAILED_CLOSED,
            lock_present=False,
            operation_label=_READ_OPERATION_LABEL,
            error_class_label="WriteBarrierReadError",
        )
    if evidence is None:
        return _public_response(
            status_label=_STATE_ABSENT,
            lock_present=False,
            operation_label=_READ_OPERATION_LABEL,
        )
    return _evidence_response(evidence)


@app.tool(
    **stateful_local_tool(
        title="Scribe Owned Write Barrier Acquire Release Proof",
        tags=("write-barrier", "proof", "write"),
    )
)
async def scribe_owned_write_barrier_acquire_release_proof(
    agent: str,
    owner_label: str,
    reason_label: str,
) -> dict[str, object]:
    """Acquire and release the active repo's write barrier without durable state."""
    root = _resolve_repo_root()
    if root is None:
        return _public_response(
            status_label=_PROOF_FAILED_CLOSED,
            lock_present=False,
            operation_label=_PROOF_OPERATION_LABEL,
            error_class_label="RootResolutionError",
        )

    try:
        with scribe_owned_write_barrier_lock(
            root,
            owner_label=owner_label,
            reason_label=reason_label,
        ) as evidence:
            acquired = evidence
    except WriteBarrierError:
        state = _read_write_barrier_state(root)
        return _public_response(
            status_label=_PROOF_BLOCKED_ACTIVE,
            lock_present=state is not None,
            operation_label=_PROOF_OPERATION_LABEL,
            lock_fingerprint=state.lock_fingerprint if state else None,
            error_class_label="WriteBarrierError",
        )
    except Exception:
        return _public_response(
            status_label=_PROOF_FAILED_CLOSED,
            lock_present=False,
            operation_label=_PROOF_OPERATION_LABEL,
            error_class_label="WriteBarrierError",
        )

    released_state = _read_write_barrier_state(root)
    if released_state is not None:
        return _public_response(
            status_label=_PROOF_FAILED_CLOSED,
            lock_present=True,
            proof_acquired=True,
            proof_released=False,
            operation_label=acquired.operation_label,
            lock_fingerprint=released_state.lock_fingerprint,
            error_class_label="WriteBarrierReleaseError",
        )

    return _public_response(
        status_label=_PROOF_SUCCESS,
        lock_present=False,
        proof_acquired=True,
        proof_released=True,
        operation_label=acquired.operation_label,
        lock_fingerprint=acquired.lock_fingerprint,
    )
