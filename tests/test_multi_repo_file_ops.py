from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.security.sandbox import SecurityError
from scribe_mcp.utils.files import append_line, read_tail, rotate_file, verify_file_integrity


@pytest.mark.asyncio
async def test_append_line_blocks_outside_server_root_without_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "external_repo"
    log_path = repo_root / ".scribe" / "docs" / "dev_plans" / "x" / "PROGRESS_LOG.md"

    with pytest.raises(SecurityError):
        await append_line(log_path, "blocked")


@pytest.mark.asyncio
async def test_repo_root_override_allows_cross_repo_append_read_rotate(tmp_path: Path) -> None:
    repo_root = tmp_path / "external_repo"
    log_path = repo_root / ".scribe" / "docs" / "dev_plans" / "x" / "PROGRESS_LOG.md"

    await append_line(log_path, "hello", repo_root=repo_root)
    lines = await read_tail(log_path, 10, repo_root=repo_root)
    assert lines[-1] == "hello"

    archive = await rotate_file(log_path, "test", confirm=True, repo_root=repo_root)
    assert archive.exists()

    archive_info = verify_file_integrity(archive, repo_root=repo_root)
    assert archive_info.get("exists") is True
    assert not archive_info.get("error")
