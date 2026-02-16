"""Tests for object_store: FilesystemStore, key resolution, and should_sync."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Ensure scribe_mcp is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scribe_mcp.object_store.keys import key_to_path, path_to_key, should_sync
from scribe_mcp.object_store.filesystem import FilesystemStore


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

class TestPathToKey:
    def test_strips_dot_scribe(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "docs" / "dev_plans" / "proj" / "ARCH.md"
        fp.parent.mkdir(parents=True)
        fp.touch()
        key = path_to_key(fp, tmp_path)
        assert key == "scribe/docs/dev_plans/proj/ARCH.md"

    def test_non_scribe_prefix(self, tmp_path: Path) -> None:
        fp = tmp_path / "docs" / "bugs" / "BUG_001.md"
        fp.parent.mkdir(parents=True)
        fp.touch()
        key = path_to_key(fp, tmp_path)
        assert key == "docs/bugs/BUG_001.md"


class TestKeyToPath:
    def test_restores_dot_scribe(self, tmp_path: Path) -> None:
        key = "scribe/docs/dev_plans/proj/ARCH.md"
        result = key_to_path(key, tmp_path)
        assert result == tmp_path / ".scribe" / "docs" / "dev_plans" / "proj" / "ARCH.md"

    def test_non_scribe_key(self, tmp_path: Path) -> None:
        key = "docs/bugs/BUG_001.md"
        result = key_to_path(key, tmp_path)
        assert result == tmp_path / "docs" / "bugs" / "BUG_001.md"


class TestRoundTrip:
    def test_path_key_roundtrip(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "docs" / "dev_plans" / "p" / "PHASE_PLAN.md"
        fp.parent.mkdir(parents=True)
        fp.touch()
        key = path_to_key(fp, tmp_path)
        restored = key_to_path(key, tmp_path)
        assert restored == fp.resolve()


# ---------------------------------------------------------------------------
# should_sync filtering
# ---------------------------------------------------------------------------

class TestShouldSync:
    def test_dev_plan_md(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "docs" / "dev_plans" / "proj" / "ARCH.md"
        assert should_sync(fp, tmp_path) is True

    def test_agent_report_card(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "docs" / "agent_report_cards" / "CARD.md"
        assert should_sync(fp, tmp_path) is True

    def test_backup_bak(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "backups" / "file.bak"
        assert should_sync(fp, tmp_path) is True

    def test_bugs_md(self, tmp_path: Path) -> None:
        fp = tmp_path / "docs" / "bugs" / "BUG_001.md"
        assert should_sync(fp, tmp_path) is True

    def test_review_nested(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "docs" / "dev_plans" / "proj" / "reviews" / "REVIEW.md"
        assert should_sync(fp, tmp_path) is True

    def test_deny_sentinel(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "sentinel" / "data.md"
        assert should_sync(fp, tmp_path) is False

    def test_deny_config(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "config" / "scribe.yaml"
        assert should_sync(fp, tmp_path) is False

    def test_deny_logs(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "logs" / "TOOL_LOG.jsonl"
        assert should_sync(fp, tmp_path) is False

    def test_deny_non_md(self, tmp_path: Path) -> None:
        fp = tmp_path / ".scribe" / "docs" / "dev_plans" / "proj" / "data.json"
        assert should_sync(fp, tmp_path) is False


# ---------------------------------------------------------------------------
# FilesystemStore CRUD
# ---------------------------------------------------------------------------

@pytest.fixture
def fs_store(tmp_path: Path) -> FilesystemStore:
    return FilesystemStore(tmp_path)


class TestFilesystemStore:
    @pytest.mark.asyncio
    async def test_write_and_read(self, fs_store: FilesystemStore, tmp_path: Path) -> None:
        key = "scribe/docs/dev_plans/test/ARCH.md"
        await fs_store.write(key, "# Architecture\n")
        result = await fs_store.read(key)
        assert result == "# Architecture\n"
        # Verify file on disk.
        on_disk = key_to_path(key, tmp_path)
        assert on_disk.is_file()

    @pytest.mark.asyncio
    async def test_read_missing(self, fs_store: FilesystemStore) -> None:
        result = await fs_store.read("scribe/docs/missing.md")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, fs_store: FilesystemStore) -> None:
        key = "scribe/docs/dev_plans/test/FILE.md"
        assert await fs_store.exists(key) is False
        await fs_store.write(key, "content")
        assert await fs_store.exists(key) is True

    @pytest.mark.asyncio
    async def test_delete(self, fs_store: FilesystemStore) -> None:
        key = "scribe/docs/dev_plans/test/DEL.md"
        await fs_store.write(key, "to delete")
        assert await fs_store.exists(key)
        await fs_store.delete(key)
        assert not await fs_store.exists(key)

    @pytest.mark.asyncio
    async def test_delete_missing_is_noop(self, fs_store: FilesystemStore) -> None:
        await fs_store.delete("scribe/docs/nope.md")  # Should not raise.

    @pytest.mark.asyncio
    async def test_list_keys(self, fs_store: FilesystemStore) -> None:
        await fs_store.write("scribe/docs/dev_plans/p/A.md", "a")
        await fs_store.write("scribe/docs/dev_plans/p/B.md", "b")
        await fs_store.write("docs/bugs/C.md", "c")
        keys = await fs_store.list_keys("scribe/docs/")
        assert "scribe/docs/dev_plans/p/A.md" in keys
        assert "scribe/docs/dev_plans/p/B.md" in keys
        assert "docs/bugs/C.md" not in keys

    @pytest.mark.asyncio
    async def test_list_keys_empty_prefix(self, fs_store: FilesystemStore) -> None:
        await fs_store.write("scribe/docs/dev_plans/p/X.md", "x")
        keys = await fs_store.list_keys()
        assert len(keys) >= 1
