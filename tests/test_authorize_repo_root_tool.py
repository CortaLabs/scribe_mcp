from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.tool_runtime import validate_repo_root_grant
from scribe_mcp.tools.authorize_repo_root import authorize_repo_root


class _GrantStorage:
    def __init__(self) -> None:
        self._grants: dict[str, SimpleNamespace] = {}

    async def create_repo_scope_grant(
        self,
        *,
        authoritative_session_key: str,
        repo_root: str,
        reason: str,
        ttl_minutes: int = 30,
    ) -> SimpleNamespace:
        grant_id = f"grant-{len(self._grants) + 1}"
        grant = SimpleNamespace(
            grant_id=grant_id,
            authoritative_session_key=authoritative_session_key,
            repo_root=str(Path(repo_root).resolve()),
            repo_id="repo-id-1",
            reason=reason,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_minutes)),
        )
        self._grants[grant_id] = grant
        return grant

    async def fetch_repo_scope_grant(self, grant_id: str) -> SimpleNamespace | None:
        return self._grants.get(grant_id)


@pytest.mark.asyncio
async def test_authorize_then_set_project_external_root_succeeds_in_same_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    external_root = (tmp_path / "external").resolve()
    external_root.mkdir()
    (external_root / ".git").mkdir()

    monkeypatch.setattr(
        server_module,
        "get_execution_context",
        lambda: SimpleNamespace(
            resolved_scope=SimpleNamespace(authoritative_session_key="stable-session-1"),
            stable_session_id="stable-session-1",
            session_id="transport-session-1",
        ),
    )
    monkeypatch.setattr(server_module, "storage_backend", _GrantStorage())

    grant = await authorize_repo_root(
        root=str(external_root),
        reason="phase-1.2b-test",
    )

    assert grant["ok"] is True
    assert grant["repo_root"] == str(external_root)
    valid, details = await validate_repo_root_grant(
        storage_backend=server_module.storage_backend,
        grant_id=grant["grant_id"],
        repo_root=str(external_root),
        authoritative_session_key="stable-session-1",
    )

    assert valid is True
    assert details["grant_id"] == grant["grant_id"]
    assert details["repo_root"] == str(external_root)
