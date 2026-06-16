"""Public-safe repo-local write barrier for controlled Scribe maintenance."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class WriteBarrierError(RuntimeError):
    """Raised when a Scribe write is not allowed by the active barrier."""


@dataclass(frozen=True)
class WriteBarrierEvidence:
    status_label: str
    lock_fingerprint: str | None
    operation_label: str
    private_values_recorded: bool = False


_LOCK_RELATIVE_PATH = Path(".scribe") / "locks" / "write-barrier.lock"
_STATUS_ACQUIRED = "scribe_owned_write_barrier_lock:acquired"
_STATUS_MALFORMED = "scribe_owned_write_barrier_lock:malformed"


def _lock_path(root: Path) -> Path:
    return root.expanduser().resolve() / _LOCK_RELATIVE_PATH


def _safe_label(value: str) -> str:
    candidate = "".join(
        character if character.isalnum() or character in {"_", "-", ".", ":"} else "_"
        for character in str(value or "").strip()
    ).strip("._-:")
    return candidate or "unknown"


def _fingerprint_payload(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _malformed_evidence(raw_value: str) -> WriteBarrierEvidence:
    return WriteBarrierEvidence(
        status_label=_STATUS_MALFORMED,
        lock_fingerprint=_fingerprint_payload({"malformed": raw_value}),
        operation_label="unknown",
    )


def read_write_barrier_state(root: Path) -> WriteBarrierEvidence | None:
    """Return public-safe barrier evidence without exposing the lock path or payload."""
    path = _lock_path(root)
    if not path.exists():
        return None
    try:
        raw_value = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _malformed_evidence(type(exc).__name__)
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return _malformed_evidence(raw_value)
    if not isinstance(payload, dict):
        return _malformed_evidence(raw_value)

    status_label = payload.get("status_label")
    lock_fingerprint = payload.get("lock_fingerprint")
    operation_label = payload.get("operation_label")
    private_values_recorded = payload.get("private_values_recorded", False)
    if (
        status_label != _STATUS_ACQUIRED
        or not isinstance(lock_fingerprint, str)
        or not lock_fingerprint
        or not isinstance(operation_label, str)
        or not operation_label
        or private_values_recorded is not False
    ):
        return _malformed_evidence(raw_value)
    return WriteBarrierEvidence(
        status_label=status_label,
        lock_fingerprint=lock_fingerprint,
        operation_label=operation_label,
        private_values_recorded=False,
    )


def assert_writes_allowed(root: Path, *, operation_label: str) -> None:
    """Fail closed when another operation owns the Scribe write barrier."""
    state = read_write_barrier_state(root)
    if state is None:
        return
    requested_label = _safe_label(operation_label)
    if state.status_label == _STATUS_ACQUIRED and state.operation_label == requested_label:
        return
    raise WriteBarrierError(
        "Scribe write barrier is active; write operation refused before mutation."
    )


@contextmanager
def scribe_owned_write_barrier_lock(
    root: Path,
    *,
    owner_label: str,
    reason_label: str,
) -> Iterator[WriteBarrierEvidence]:
    """Acquire a repo/project-local Scribe write barrier and release it on exit."""
    path = _lock_path(root)
    operation_label = _safe_label(reason_label)
    owner = _safe_label(owner_label)
    fingerprint = _fingerprint_payload(
        {
            "owner_label": owner,
            "operation_label": operation_label,
            "nonce": secrets.token_hex(16),
        }
    )
    evidence = WriteBarrierEvidence(
        status_label=_STATUS_ACQUIRED,
        lock_fingerprint=fingerprint,
        operation_label=operation_label,
    )
    payload = {
        "status_label": evidence.status_label,
        "lock_fingerprint": evidence.lock_fingerprint,
        "operation_label": evidence.operation_label,
        "owner_label": owner,
        "private_values_recorded": False,
    }

    lock_parent = path.parent
    lock_parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        lock_parent.chmod(0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise WriteBarrierError("Scribe write barrier is already active.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(OSError):
            path.chmod(0o600)
        yield evidence
    finally:
        current = read_write_barrier_state(root)
        if current is not None and current.lock_fingerprint == evidence.lock_fingerprint:
            with suppress(FileNotFoundError):
                path.unlink()
