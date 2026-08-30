"""Cross-backend apply-preview fencing and remote-delegation evidence."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

import scribe_mcp.server as server_module
import scribe_mcp.server_sse as sse_module
from scribe_mcp.doc_management.apply_preview import (
    ApplyPreviewBinding,
    ApplyPreviewService,
)
from scribe_mcp.doc_management.manager import MutationLockTarget
from scribe_mcp.shared.write_barrier import scribe_owned_write_barrier_lock
from scribe_mcp.storage.models import ApplyPreviewReceiptRecord
from scribe_mcp.storage.remote import RemoteStorageBackend
from scribe_mcp.storage.sqlite import SQLiteStorage


pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.regression]


def _receipt(
    token_sha256: str,
    *,
    principal_id: str,
    state: str = "issued",
    fence: int = 0,
    lease_expires_at: datetime | None = None,
) -> ApplyPreviewReceiptRecord:
    now = datetime.now(timezone.utc)
    return ApplyPreviewReceiptRecord(
        token_sha256=token_sha256,
        receipt_version=1,
        state=state,  # type: ignore[arg-type]
        principal_id=principal_id,
        session_id="session-parity",
        run_id="run-parity",
        project_key="project-parity",
        repo_id="repo-parity",
        action="replace_text",
        normalized_intent_json='{"find":"before","replace":"after"}',
        target_binding_json='{"doc":"architecture"}',
        precondition_json='{"sha256":"before"}',
        predicted_after_json='{"sha256":"after"}',
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
        fence=fence,
        apply_lease_expires_at=lease_expires_at,
        terminal_result_code=None,
        terminal_result_json=None,
        terminal_at=None,
        audit_correlation_id=uuid.uuid4().hex,
        updated_at=now - timedelta(minutes=1),
    )


async def test_sqlite_and_postgres_share_exactly_once_claim_and_terminal_replay(
    backend, test_agent: str
) -> None:
    storage, backend_name = backend
    token_sha256 = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    record = _receipt(token_sha256, principal_id=test_agent)
    await storage.issue_apply_preview_receipt(record)

    first, second = await asyncio.gather(
        storage.claim_apply_preview_receipt(token_sha256, lease_seconds=60),
        storage.claim_apply_preview_receipt(token_sha256, lease_seconds=60),
    )

    assert sorted((first.status, second.status)) == ["busy", "claimed"], backend_name
    owner = first if first.status == "claimed" else second
    assert owner.record is not None
    assert owner.record.fence == 1

    terminal = await storage.finalize_apply_preview_receipt(
        token_sha256,
        fence=owner.record.fence,
        terminal_state="applied",
        result_code="APPLY_RECEIPT_APPLIED",
        result_json='{"ok":true,"code":"APPLY_RECEIPT_APPLIED"}',
    )
    replay = await storage.claim_apply_preview_receipt(token_sha256, lease_seconds=60)

    assert terminal.state == "applied"
    assert replay.status == "terminal"
    assert replay.record == terminal


async def test_sqlite_and_postgres_recover_expired_claim_with_monotonic_fence(
    backend, test_agent: str
) -> None:
    storage, backend_name = backend
    token_sha256 = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    record = _receipt(
        token_sha256,
        principal_id=test_agent,
        state="applying",
        fence=7,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    await storage.issue_apply_preview_receipt(record)

    recovery = await storage.claim_apply_preview_receipt(token_sha256, lease_seconds=60)

    assert recovery.status == "recovery", backend_name
    assert recovery.record is not None
    assert recovery.record.state == "applying"
    assert recovery.record.fence == 8
    assert recovery.record.apply_lease_expires_at is not None
    assert recovery.record.apply_lease_expires_at > datetime.now(timezone.utc)


class _Executor:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.execute_calls = 0

    async def authorize_apply_preview(self, *, execution_context, binding) -> bool:
        return True

    async def resolve_apply_preview_targets(self, *, execution_context, binding):
        return tuple(
            MutationLockTarget(repo_root=item["repo_root"], path=item["path"])
            for item in binding["targets"]
        )

    async def inspect_apply_preview_state(self, *, execution_context, binding):
        return {"sha256": "before"}

    async def execute_retained_intent(
        self, *, action, normalized_intent, execution_context, binding, fence
    ):
        self.execute_calls += 1
        return {"ok": True}


async def test_current_write_policy_denial_is_parity_safe_before_execution(
    backend, tmp_path: Path, test_agent: str
) -> None:
    storage, backend_name = backend
    root = tmp_path / f"policy-{backend_name}"
    root.mkdir()
    target = root / "DOC.md"
    target.write_text("before", encoding="utf-8")
    service = ApplyPreviewService(storage)
    affordance = await service.issue(
        action="replace_text",
        normalized_intent={"find": "before", "replace": "after"},
        binding=ApplyPreviewBinding(
            principal_id=test_agent,
            session_id="session-parity",
            run_id="run-parity",
            project_key="project-parity",
            repo_id="repo-parity",
            repo_root=str(root),
            targets=(MutationLockTarget(repo_root=str(root), path=target),),
            target_binding={"doc": "architecture"},
        ),
        precondition={"sha256": "before"},
        predicted_after={"sha256": "after"},
    )
    executor = _Executor(root)
    context = SimpleNamespace(
        principal_id=test_agent,
        session_id="session-parity",
        run_id="run-parity",
        project_key="project-parity",
        repo_id="repo-parity",
        repo_root=str(root),
    )

    with scribe_owned_write_barrier_lock(
        root, owner_label="test-maintenance", reason_label="other-operation"
    ):
        result = await service.apply(
            receipt=affordance.receipt,
            execution_context=context,
            executor=executor,
        )

    assert result == {
        "ok": False,
        "code": "APPLY_RECEIPT_POLICY_DENIED",
        "replayed": False,
    }
    assert executor.execute_calls == 0


async def test_remote_boundary_delegates_once_and_fails_closed_before_server_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_agent: str
) -> None:
    server_storage = SQLiteStorage(tmp_path / "remote-server.sqlite3")
    await server_storage.setup()
    record = _receipt("f" * 64, principal_id=test_agent)
    claim_spy = AsyncMock(wraps=server_storage.claim_apply_preview_receipt)
    monkeypatch.setattr(server_storage, "claim_apply_preview_receipt", claim_spy)
    monkeypatch.setattr(server_module, "storage_backend", server_storage)
    monkeypatch.setattr(sse_module, "_is_public_release_transport", lambda: False)
    monkeypatch.setattr(
        server_module, "begin_transport_operation", AsyncMock(return_value="running")
    )
    monkeypatch.setattr(server_module, "end_transport_operation", AsyncMock())
    app = Starlette(
        routes=[
            Route(
                "/api/v1/backend/{operation}",
                sse_module.handle_backend_operation,
                methods=["POST"],
            )
        ]
    )
    remote = RemoteStorageBackend("http://testserver", auth_token="internal-test-token")
    remote._client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )
    try:
        assert await remote.issue_apply_preview_receipt(record) == record
        claimed = await remote.claim_apply_preview_receipt(
            record.token_sha256, lease_seconds=60
        )
        assert claimed.status == "claimed"
        assert claim_spy.await_count == 1

        monkeypatch.setattr(sse_module, "_is_public_release_transport", lambda: True)
        with pytest.raises(PermissionError, match="Forbidden"):
            await remote.claim_apply_preview_receipt(
                record.token_sha256, lease_seconds=60
            )
        assert claim_spy.await_count == 1
    finally:
        await remote.close()
        await server_storage.close()
