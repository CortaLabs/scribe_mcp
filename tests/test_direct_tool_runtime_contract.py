from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scribe_mcp import server
from scribe_mcp.storage.affected_row_referential_inventory import BLOCKED_STORAGE_BACKEND_UNAVAILABLE
from scribe_mcp.readiness import (
    ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL,
    ACCEPTED_SELECTOR_READBACK_STATUS_LABEL,
    BLOCKED_STORAGE_SETUP_REQUIRED,
)
from scribe_mcp.selector_readback import (
    ACTIVE_RUNTIME_EXCLUSION_LABEL,
    DEFAULT_CONTEXT_BYPASS_LABEL,
    PRIVATE_SELECTOR_CLASS_LABEL,
    READBACK_STATUS_LABEL,
    RUNTIME_ROLE_LABEL,
    SOURCE_AUTHORITY_LABEL,
    TARGET_FINGERPRINT_BINDING_LABEL,
)
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import execute_tool_call

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_SAFE_HANDLE_ID = "opaque_handle_30bg_local_test"
PUBLIC_SAFE_NAMESPACE = "train_30bg_public_safe_proof_namespace"


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str) -> str | None:
        return None


class _DummyStateManager:
    async def load(self) -> _DummyState:
        return _DummyState()


def _registered_tool_registry() -> dict[str, Any]:
    server.list_registered_tools()
    registry = getattr(type(server.app), "_scribe_tool_registry", None) or getattr(
        server.app,
        "_scribe_tool_registry",
        None,
    )
    assert isinstance(registry, dict)
    return registry


async def _execute_direct_tool(name: str, arguments: dict[str, Any]) -> Any:
    router = RouterContextManager()
    return await execute_tool_call(
        name=name,
        arguments=arguments,
        kwargs={
            "context": {
                "mode": "project",
                "repo_root": str(REPO_ROOT),
                "session_id": "train-30bg-runtime-session",
            }
        },
        registry=_registered_tool_registry(),
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(
            project_root=REPO_ROOT,
            default_repo_root=str(REPO_ROOT),
            trusted_repo_roots=(str(REPO_ROOT),),
            public_release=False,
        ),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={
            "scribe_private_context_selector_readback",
            "scribe_local_postgres_readiness_roundtrip_preflight",
            "scribe_affected_row_referential_inventory_readonly_public_safe",
        },
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )


def _selector_arguments() -> dict[str, str]:
    return {
        "agent": "forge",
        "selector_class_label": PRIVATE_SELECTOR_CLASS_LABEL,
        "target_fingerprint_binding_label": TARGET_FINGERPRINT_BINDING_LABEL,
        "runtime_role_label": RUNTIME_ROLE_LABEL,
        "default_context_bypass_label": DEFAULT_CONTEXT_BYPASS_LABEL,
        "active_runtime_exclusion_label": ACTIVE_RUNTIME_EXCLUSION_LABEL,
        "source_authority_label": SOURCE_AUTHORITY_LABEL,
    }


def _readiness_arguments() -> dict[str, str]:
    return {
        "agent": "forge",
        "private_target_handle_id": PUBLIC_SAFE_HANDLE_ID,
        "target_class_label": ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL,
        "selected_context_readback_status_label": ACCEPTED_SELECTOR_READBACK_STATUS_LABEL,
        "proof_namespace_label": PUBLIC_SAFE_NAMESPACE,
    }


def _inventory_arguments() -> dict[str, str]:
    return {
        "agent": "forge",
        "target_binding_status_label": "PASS",
        "selected_context_readback_status_label": "PASS",
        "inventory_scope_label": "SOURCE_BACKED_SCRIBE_AFFECTED_ROW_REFERENTIAL_INVENTORY_READONLY_PUBLIC_SAFE",
    }


def _assert_public_only_payload(payload: dict[str, Any]) -> None:
    sensitive_fragments = (
        "dsn",
        "postgresql://",
        "host=",
        "database=",
        "user=",
        "password",
        "credential",
        "select ",
        "insert ",
        "update ",
        "delete ",
        "dump",
        PUBLIC_SAFE_HANDLE_ID,
        PUBLIC_SAFE_NAMESPACE,
    )
    for value in payload.values():
        assert isinstance(value, (str, bool, int, list, dict))
        lowered = str(value).lower()
        assert all(fragment not in lowered for fragment in sensitive_fragments)


@pytest.mark.asyncio
async def test_selector_readback_accepts_agent_through_runtime_dispatch() -> None:
    payload = await _execute_direct_tool(
        "scribe_private_context_selector_readback",
        _selector_arguments(),
    )

    assert payload["selected_context_readback_status_label"] == READBACK_STATUS_LABEL
    assert payload["private_values_recorded"] is False
    assert payload["train_local_db_g_technical_pass_earned"] is False
    assert payload["train_02g2_b_routing_authorized"] is False
    _assert_public_only_payload(payload)


@pytest.mark.asyncio
async def test_readiness_preflight_accepts_agent_through_runtime_dispatch_without_contact() -> None:
    payload = await _execute_direct_tool(
        "scribe_local_postgres_readiness_roundtrip_preflight",
        _readiness_arguments(),
    )

    assert payload["target_class_label"] == ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL
    assert payload["selected_context_readback_status_label"] == ACCEPTED_SELECTOR_READBACK_STATUS_LABEL
    assert payload["connectivity_status_label"] == BLOCKED_STORAGE_SETUP_REQUIRED
    assert payload["storage_setup_status_label"] == BLOCKED_STORAGE_SETUP_REQUIRED
    assert payload["scribe_roundtrip_label"] == BLOCKED_STORAGE_SETUP_REQUIRED
    assert payload["private_values_recorded"] is False
    assert payload["train_local_db_g_technical_pass_candidate_label"] is False
    assert payload["train_local_db_g_technical_pass_earned"] is False
    assert payload["train_02g2_b_routing_authorized"] is False
    _assert_public_only_payload(payload)


@pytest.mark.asyncio
async def test_affected_row_inventory_dispatch_fails_closed_without_storage_backend(monkeypatch) -> None:
    monkeypatch.setattr(server, "storage_backend", None)

    payload = await _execute_direct_tool(
        "scribe_affected_row_referential_inventory_readonly_public_safe",
        _inventory_arguments(),
    )

    assert payload["status_label"] == "BLOCK"
    assert payload["storage_backend_status_label"] == BLOCKED_STORAGE_BACKEND_UNAVAILABLE
    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False
    _assert_public_only_payload(payload)


@pytest.mark.asyncio
async def test_direct_tool_runtime_missing_agent_fails_closed_before_dispatch() -> None:
    arguments = _selector_arguments()
    arguments.pop("agent")

    with pytest.raises(ValueError, match="agent parameter is required for all tool calls"):
        await _execute_direct_tool("scribe_private_context_selector_readback", arguments)
