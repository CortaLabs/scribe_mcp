"""Focused regression tests for repo-local runtime path policy."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scribe_mcp.cli.session_store import CliSessionState, save_session_state
from scribe_mcp.config.paths import (
    cli_session_dir,
    cli_session_state_path,
    runtime_logs_dir,
    runtime_state_dir,
)
from scribe_mcp.object_store.keys import should_sync
from scribe_mcp.utils.audit import AuditTrailManager
from scribe_mcp.utils.rotation_state import RotationStateManager


def test_runtime_helpers_resolve_repo_local_namespaces(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))

    assert cli_session_dir() == tmp_path / ".scribe" / "cli"
    assert runtime_state_dir() == tmp_path / ".scribe" / "state"
    assert runtime_logs_dir() == tmp_path / ".scribe" / "logs"


def test_cli_session_state_writes_under_repo_local_cli_namespace(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))

    state = CliSessionState(
        session_name="release/profile",
        repo_root=str(tmp_path),
        agent="Tester",
        transport_session_id="cli:test",
        context={"repo_root": str(tmp_path), "transport_session_id": "cli:test"},
    )

    session_path = save_session_state(state)

    assert session_path == cli_session_state_path("release/profile")
    assert session_path == tmp_path / ".scribe" / "cli" / "release_profile.json"
    assert not (tmp_path / "state").exists()
    assert json.loads(session_path.read_text(encoding="utf-8"))["session_name"] == "release/profile"


def test_rotation_and_audit_defaults_stay_under_scribe_state(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    expected_state_dir = tmp_path / ".scribe" / "state"

    rotation_manager = RotationStateManager()
    audit_manager = AuditTrailManager()

    assert rotation_manager.state_dir == expected_state_dir
    assert rotation_manager.state_file == expected_state_dir / "rotation_state.json"
    assert not (tmp_path / "state").exists()

    rotation_metadata = {
        "rotation_uuid": str(uuid.uuid4()),
        "rotation_timestamp_utc": datetime.utcnow().isoformat() + " UTC",
        "sequence_number": 1,
        "archived_file_path": "/tmp/example.log",
        "file_hash": "sha256:test_hash_1234567890abcdef",
        "entry_count": 3,
    }

    assert rotation_manager.update_project_state("Runtime Policy", rotation_metadata) is True
    assert rotation_manager.state_file.exists()

    audit_metadata = {
        "rotation_uuid": str(uuid.uuid4()),
        "rotation_timestamp_utc": datetime.utcnow().isoformat() + " UTC",
        "sequence_number": 1,
        "archived_file_path": "/tmp/example.log",
        "entry_count": 3,
        "file_hash": "sha256:audit_hash_1234567890abcdef",
    }

    assert audit_manager.store_rotation_metadata("Runtime Policy", audit_metadata) is True
    assert (expected_state_dir / "rotation_audit_Runtime_Policy.json").exists()
    assert not (tmp_path / "state").exists()


def test_object_store_denies_runtime_namespaces(tmp_path: Path) -> None:
    assert should_sync(tmp_path / ".scribe" / "cli" / "profile.json", tmp_path) is False
    assert should_sync(tmp_path / ".scribe" / "state" / "rotation_state.json", tmp_path) is False
    assert should_sync(tmp_path / ".scribe" / "logs" / "TOOL_LOG.jsonl", tmp_path) is False
