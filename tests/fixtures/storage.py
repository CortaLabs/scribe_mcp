"""Reusable storage fixtures for integration and tool tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.storage.models import ApplyPreviewReceiptRecord


@pytest.fixture
def sqlite_db_path(tmp_path: Path) -> Path:
    """Return an isolated SQLite DB path for a test."""
    return tmp_path / "scribe_projects.db"


@pytest.fixture
async def sqlite_storage(sqlite_db_path: Path):
    """Return an initialized SQLiteStorage backed by tmp_path."""
    storage = SQLiteStorage(sqlite_db_path)
    await storage.setup()
    try:
        yield storage
    finally:
        close_fn = getattr(storage, "close", None)
        if callable(close_fn):
            maybe_awaitable = close_fn()
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable


def apply_preview_receipt(*, state: str = "issued", fence: int = 0) -> ApplyPreviewReceiptRecord:
    now = datetime.now(timezone.utc)
    terminal = state in {"applied", "failed_terminal"}
    return ApplyPreviewReceiptRecord(
        token_sha256="a" * 64,
        receipt_version=1,
        state=state,  # type: ignore[arg-type]
        principal_id="principal-1",
        session_id="session-1",
        run_id="run-1",
        project_key="project-1",
        repo_id="repo-1",
        action="replace_section",
        normalized_intent_json='{"action":"replace_section"}',
        target_binding_json='{"doc":"ARCHITECTURE_GUIDE"}',
        precondition_json='{"sha256":"before"}',
        predicted_after_json='{"sha256":"after"}',
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        fence=fence,
        apply_lease_expires_at=(now + timedelta(seconds=60))
        if state == "applying"
        else None,
        terminal_result_code="APPLY_RECEIPT_APPLIED" if terminal else None,
        terminal_result_json='{"ok":true}' if terminal else None,
        terminal_at=now if terminal else None,
        audit_correlation_id="audit-1",
        updated_at=now,
    )


def apply_preview_receipt_row(record: ApplyPreviewReceiptRecord) -> dict[str, Any]:
    return {
        "token_sha256": record.token_sha256,
        "receipt_version": record.receipt_version,
        "state": record.state,
        "principal_id": record.principal_id,
        "session_id": record.session_id,
        "run_id": record.run_id,
        "project_key": record.project_key,
        "repo_id": record.repo_id,
        "action": record.action,
        "normalized_intent_json": {"action": "replace_section"},
        "target_binding_json": {"doc": "ARCHITECTURE_GUIDE"},
        "precondition_json": {"sha256": "before"},
        "predicted_after_json": {"sha256": "after"},
        "issued_at": record.issued_at,
        "expires_at": record.expires_at,
        "fence": record.fence,
        "apply_lease_expires_at": record.apply_lease_expires_at,
        "terminal_result_code": record.terminal_result_code,
        "terminal_result_json": {"ok": True} if record.terminal_result_json else None,
        "terminal_at": record.terminal_at,
        "audit_correlation_id": record.audit_correlation_id,
        "updated_at": record.updated_at,
    }


def apply_preview_receipt_with_nested_json(*, state: str) -> ApplyPreviewReceiptRecord:
    body = "  café e\u0301 雪\nline two\t\\literal  "
    payload = {"z": [None, {"body": body, "enabled": True}], "a": "value"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return replace(
        apply_preview_receipt(state=state, fence=1 if state == "applied" else 0),
        normalized_intent_json=encoded,
        target_binding_json=encoded,
        precondition_json=encoded,
        predicted_after_json=encoded,
        terminal_result_json=encoded if state == "applied" else None,
    )
