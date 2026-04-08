from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.tools.append_entry import _tee_entry_to_log_type, _make_missing_meta_reminder


@pytest.mark.asyncio
async def test_tee_to_bug_log_requires_meta(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "p"
    project = {
        "name": "p",
        "root": str(repo_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "defaults": {"emoji": "ℹ️", "agent": "Codex"},
    }
    log_cache = {}

    meta_payload = {"log_type": "progress"}  # missing bug meta
    log_path, missing = await _tee_entry_to_log_type(
        project=project,
        repo_root=repo_root,
        log_type="bugs",
        message="bug occurred",
        emoji="🐞",
        timestamp="2025-01-01 00:00:00 UTC",
        agent="Codex",
        meta_payload=meta_payload,
        log_cache=log_cache,
    )
    assert log_path is None
    assert set(missing) == {"severity", "component", "status"}

    reminder = _make_missing_meta_reminder(target_log_type="bugs", missing_keys=missing)
    assert "severity" in reminder["message"]


@pytest.mark.asyncio
async def test_tee_to_bug_log_writes_when_meta_present(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "p"
    bug_log = docs_dir / "BUG_LOG.md"
    project = {
        "name": "p",
        "root": str(repo_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "defaults": {"emoji": "ℹ️", "agent": "Codex"},
    }
    log_cache = {}

    meta_payload = {
        "severity": "high",
        "component": "auth",
        "status": "open",
    }
    log_path, missing = await _tee_entry_to_log_type(
        project=project,
        repo_root=repo_root,
        log_type="bugs",
        message="bug occurred",
        emoji="🐞",
        timestamp="2025-01-01 00:00:00 UTC",
        agent="Codex",
        meta_payload=meta_payload,
        log_cache=log_cache,
    )

    assert missing == []
    assert log_path is not None
    assert log_path == bug_log
    assert bug_log.read_text(encoding="utf-8")
