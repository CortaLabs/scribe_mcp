from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.write_barrier import scribe_owned_write_barrier_lock
from scribe_mcp.tools import ensure_tool_loaded, tool_module_for_name

APPROVED_FIELDS = {
    "status_label",
    "lock_present",
    "proof_acquired",
    "proof_released",
    "operation_label",
    "lock_fingerprint",
    "private_values_recorded",
    "error_class_label",
}


def _verified_context(root: Path) -> SimpleNamespace:
    provenance = SimpleNamespace(repo_root="verified")
    resolved_scope = SimpleNamespace(repo_root=str(root), provenance=provenance)
    return SimpleNamespace(repo_root=str(root), resolved_scope=resolved_scope)


def _assert_public_contract(payload: dict[str, object], forbidden: set[str]) -> None:
    assert set(payload) == APPROVED_FIELDS
    assert payload["private_values_recorded"] is False
    rendered = json.dumps(payload, sort_keys=True)
    for value in forbidden:
        assert value not in rendered


def test_write_barrier_tools_are_lazy_registered() -> None:
    assert tool_module_for_name("read_write_barrier_state") == "write_barrier"
    assert tool_module_for_name("scribe_owned_write_barrier_acquire_release_proof") == "write_barrier"
    assert ensure_tool_loaded("read_write_barrier_state") is True
    assert ensure_tool_loaded("scribe_owned_write_barrier_acquire_release_proof") is True


@pytest.mark.asyncio
async def test_read_write_barrier_state_reports_absent_without_path_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scribe_mcp.tools import write_barrier as tool_module

    monkeypatch.setattr(tool_module.server_module, "get_execution_context", lambda: _verified_context(tmp_path))

    payload = await tool_module.read_write_barrier_state(agent="test-agent")

    assert payload["status_label"] == "write_barrier_state:absent"
    assert payload["lock_present"] is False
    assert payload["proof_acquired"] is False
    assert payload["proof_released"] is False
    _assert_public_contract(payload, {str(tmp_path), "write-barrier.lock"})


@pytest.mark.asyncio
async def test_acquire_release_proof_succeeds_only_after_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scribe_mcp.shared.write_barrier import read_write_barrier_state as internal_state
    from scribe_mcp.tools import write_barrier as tool_module

    monkeypatch.setattr(tool_module.server_module, "get_execution_context", lambda: _verified_context(tmp_path))

    payload = await tool_module.scribe_owned_write_barrier_acquire_release_proof(
        agent="test-agent",
        owner_label="test-owner",
        reason_label="proof maintenance",
    )

    assert payload["status_label"] == "write_barrier_proof:acquired_and_released"
    assert payload["lock_present"] is False
    assert payload["proof_acquired"] is True
    assert payload["proof_released"] is True
    assert payload["operation_label"] == "proof_maintenance"
    assert payload["lock_fingerprint"]
    assert internal_state(tmp_path) is None
    _assert_public_contract(payload, {str(tmp_path), "test-owner", "write-barrier.lock"})


@pytest.mark.asyncio
async def test_acquire_release_proof_blocks_on_active_lock_without_raw_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scribe_mcp.tools import write_barrier as tool_module

    monkeypatch.setattr(tool_module.server_module, "get_execution_context", lambda: _verified_context(tmp_path))

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="existing-owner",
        reason_label="active private path",
    ):
        payload = await tool_module.scribe_owned_write_barrier_acquire_release_proof(
            agent="test-agent",
            owner_label="test-owner",
            reason_label="proof maintenance",
        )

    assert payload["status_label"] == "write_barrier_proof:blocked_active"
    assert payload["lock_present"] is True
    assert payload["proof_acquired"] is False
    assert payload["proof_released"] is False
    assert payload["error_class_label"] == "WriteBarrierError"
    _assert_public_contract(payload, {str(tmp_path), "existing-owner", "active private path", "write-barrier.lock"})


@pytest.mark.asyncio
async def test_read_write_barrier_state_reports_malformed_without_raw_payload_or_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scribe_mcp.tools import write_barrier as tool_module

    lock_path = tmp_path / ".scribe" / "locks" / "write-barrier.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(f"not-json {tmp_path} secret-token", encoding="utf-8")
    monkeypatch.setattr(tool_module.server_module, "get_execution_context", lambda: _verified_context(tmp_path))

    payload = await tool_module.read_write_barrier_state(agent="test-agent")

    assert payload["status_label"] == "scribe_owned_write_barrier_lock:malformed"
    assert payload["lock_present"] is True
    assert payload["operation_label"] == "unknown"
    assert payload["lock_fingerprint"]
    _assert_public_contract(payload, {str(tmp_path), "secret-token", "not-json", "write-barrier.lock"})


@pytest.mark.asyncio
async def test_tools_fail_closed_when_repo_root_resolution_is_unsafe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scribe_mcp.tools import write_barrier as tool_module

    monkeypatch.setattr(tool_module.server_module, "get_execution_context", lambda: None)

    read_payload = await tool_module.read_write_barrier_state(agent="test-agent")
    proof_payload = await tool_module.scribe_owned_write_barrier_acquire_release_proof(
        agent="test-agent",
        owner_label="test-owner",
        reason_label="proof maintenance",
    )

    assert read_payload["status_label"] == "write_barrier_state:failed_closed"
    assert proof_payload["status_label"] == "write_barrier_proof:failed_closed"
    assert read_payload["error_class_label"] == "RootResolutionError"
    assert proof_payload["error_class_label"] == "RootResolutionError"
    _assert_public_contract(read_payload, {"test-owner", "proof maintenance"})
    _assert_public_contract(proof_payload, {"test-owner", "proof maintenance"})
