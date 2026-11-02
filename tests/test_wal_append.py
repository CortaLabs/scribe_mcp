"""Retained-WAL append cost and integrity contracts on real files."""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scribe_mcp.utils import files

def _seed(log: Path, count: int) -> files.WriteAheadLog:
    """Seed valid retained history in linear time, outside measurements."""
    wal = files.WriteAheadLog(log, repo_root=log.parent)
    payload, digest = wal._canonical_payload(
        {"op": "append", "content": "seed\n", "file_path": str(log)}
    )
    with wal.journal_path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            stamp = f"2020-01-01T00:00:00.{index:06d}+00:00"
            entry_id = f"{stamp}_{digest[:8]}"
            handle.write(json.dumps(dict(payload, id=entry_id, payload_digest=digest,
                                         timestamp=stamp)) + "\n")
            handle.write(json.dumps({"op": "commit", "ref_id": entry_id,
                                     "timestamp": stamp}) + "\n")
    return wal


def _append_worker(log: str, root: str, count: int) -> None:
    for index in range(count):
        files._write_line_with_wal(Path(log), f"{os.getpid()}:{index}", repo_root=Path(root))


def _assert_warm_append_does_not_rescan(tmp_path: Path, history: int) -> None:
    log = tmp_path / "progress.md"
    _seed(log, history)
    files._write_line_with_wal(log, "warm", repo_root=tmp_path)
    scans = []
    original = files.WriteAheadLog._read_journal_locked

    def counted(self, handle):
        scans.append(os.fstat(handle.fileno()).st_size)
        return original(self, handle)

    with patch.object(files.WriteAheadLog, "_read_journal_locked", counted):
        for index in range(8):
            files._write_line_with_wal(log, f"next {index}", repo_root=tmp_path)
    assert scans == [], f"warm appends rescanned {sum(scans)} retained bytes"
    assert log.read_text().splitlines() == ["warm"] + [f"next {i}" for i in range(8)]


# The same permanent regression also runs with the declared standard-library
# Python capability, so its RED proof does not depend on pytest installation.
if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="scribe-wal-regression-") as directory:
        _assert_warm_append_does_not_rescan(Path(directory), 1000)
    print("warm retained-WAL append regression: PASS")
    raise SystemExit(0)


import pytest

pytestmark = [pytest.mark.core, pytest.mark.regression]


@pytest.mark.skipif(os.name != "posix", reason="fast path requires POSIX change time")
@pytest.mark.parametrize("history", [10, 1000])
def test_warm_append_does_not_rescan_retained_history(tmp_path, history):
    _assert_warm_append_does_not_rescan(tmp_path, history)


def test_stable_ids_idempotence_conflict_and_format(tmp_path):
    wal = _seed(tmp_path / "progress.md", 20)
    payload = {"op": "append", "content": "hello\n", "file_path": str(wal.log_path)}
    snapshot = dict(payload)
    entry_id = wal.write_entry(payload)
    assert payload == snapshot
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{6})?\+00:00_[0-9a-f]{8}", entry_id)
    before = wal.journal_path.read_bytes()
    assert wal.write_entry(payload, entry_id=entry_id) == entry_id
    assert wal.journal_path.read_bytes() == before
    with pytest.raises(files.WalEntryConflictError):
        wal.write_entry(dict(payload, content="changed"), entry_id=entry_id)
    wal.commit_entry(entry_id)
    committed = wal.journal_path.read_bytes()
    wal.commit_entry(entry_id)
    assert wal.journal_path.read_bytes() == committed
    # Retry an ID from retained history, well outside any recent-intent proof.
    old = wal.read_uncommitted()
    assert old == ()
    rows = [json.loads(line) for line in committed.splitlines()]
    first = rows[0]
    assert wal.write_entry(first, entry_id=first["id"]) == first["id"]
    with pytest.raises(files.WalEntryConflictError):
        wal.write_entry(dict(first, content="conflict"), entry_id=first["id"])
    assert set(rows[-1]) == {"op", "ref_id", "timestamp"}
    assert wal.journal_path.stat().st_mode & 0o777 == 0o600


def test_generated_id_clock_rollback_uses_authoritative_history(tmp_path, monkeypatch):
    wal = _seed(tmp_path / "progress.md", 10)
    files._write_line_with_wal(wal.log_path, "warm", repo_root=tmp_path)
    # datetime.isoformat omits a zero microsecond component. Use the next
    # seeded intent so its textual ID exactly matches the real generator.
    row = json.loads(wal.journal_path.read_text().splitlines()[2])

    class Clock:
        @staticmethod
        def now(tz):
            return datetime.fromisoformat(row["timestamp"])

    monkeypatch.setattr(files, "datetime", Clock)
    before = wal.journal_path.read_bytes()
    assert wal.write_entry(row) == row["id"]
    assert wal.journal_path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["append", "replace", "truncate", "restored_mtime"])
def test_external_corruption_invalidates_warm_proof(tmp_path, mutation):
    wal = _seed(tmp_path / "progress.md", 10)
    files._write_line_with_wal(wal.log_path, "warm", repo_root=tmp_path)
    journal = wal.journal_path
    before = journal.stat()
    data = journal.read_bytes()
    if mutation == "append":
        with journal.open("ab") as handle:
            handle.write(b"{broken\n")
    elif mutation == "replace":
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"!" + data[1:])
        os.replace(replacement, journal)
        os.utime(journal, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif mutation == "truncate":
        journal.write_bytes(data[:17])
    else:
        with journal.open("r+b") as handle:
            handle.write(b"!")
        os.utime(journal, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert journal.stat().st_mtime_ns == before.st_mtime_ns
        assert journal.stat().st_size == before.st_size
    with pytest.raises(files.WalJournalCorruptError):
        files._write_line_with_wal(wal.log_path, "must not append", repo_root=tmp_path)
    assert wal.log_path.read_text() == "warm\n"


@pytest.mark.parametrize("mutation", ["replace", "truncate", "corrupt"])
def test_external_change_between_intent_and_commit_is_validated(tmp_path, mutation):
    wal = _seed(tmp_path / "progress.md", 10)
    entry_id = wal.write_entry({"op": "append", "content": "pending\n"})
    data = wal.journal_path.read_bytes()
    if mutation == "replace":
        replacement = tmp_path / "replacement"
        replacement.write_text("")
        os.replace(replacement, wal.journal_path)
    elif mutation == "truncate":
        wal.journal_path.write_bytes(b"")
    else:
        wal.journal_path.write_bytes(b"!" + data[1:])
    with pytest.raises(files.WalJournalCorruptError):
        wal.commit_entry(entry_id)


def test_other_writer_and_old_ids_remain_visible(tmp_path):
    wal = _seed(tmp_path / "progress.md", 10)
    files._write_line_with_wal(wal.log_path, "warm", repo_root=tmp_path)
    context = multiprocessing.get_context("spawn")
    worker = context.Process(target=_append_worker, args=(str(wal.log_path), str(tmp_path), 1))
    worker.start()
    worker.join(30)
    assert worker.exitcode == 0
    files._write_line_with_wal(wal.log_path, "after external writer", repo_root=tmp_path)
    assert len(wal.log_path.read_text().splitlines()) == 3
    assert wal.read_uncommitted() == ()


def test_recovery_and_legacy_intents(tmp_path):
    wal = files.WriteAheadLog(tmp_path / "progress.md", repo_root=tmp_path)
    legacy = {"op": "append", "id": "legacy", "timestamp": "2020-01-01",
              "content": "legacy recovered\n"}
    wal.journal_path.write_text(json.dumps(legacy) + "\n")
    assert wal.read_uncommitted()[0]["id"] == "legacy"
    assert wal.replay_uncommitted() == 1
    assert wal.replay_uncommitted() == 0
    assert wal.log_path.read_text() == "legacy recovered\n"
    assert wal.has_commit("legacy")
    with pytest.raises(files.WalJournalCorruptError, match="unknown"):
        wal.commit_entry("missing")


@pytest.mark.parametrize("bad_row", [
    [], {"op": "append"},
    {"op": "commit", "ref_id": "missing", "timestamp": "now"},
    {"op": "custom", "id": "x", "timestamp": "now"},
    {"op": "append", "id": "x", "timestamp": "now", "payload_digest": "wrong"},
])
def test_malformed_rows_are_rejected(tmp_path, bad_row):
    wal = files.WriteAheadLog(tmp_path / "progress.md", repo_root=tmp_path)
    wal.journal_path.write_text(json.dumps(bad_row) + "\n")
    with pytest.raises(files.WalJournalCorruptError):
        wal.write_entry({"op": "append", "content": "must not append"})


def test_real_thread_and_process_concurrency(tmp_path):
    log = tmp_path / "progress.md"
    _seed(log, 50)
    context = multiprocessing.get_context("spawn")
    workers = [context.Process(target=_append_worker, args=(str(log), str(tmp_path), 6))
               for _ in range(3)]
    for worker in workers:
        worker.start()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(files._write_line_with_wal, log, f"thread:{i}", tmp_path)
                   for i in range(24)]
        for future in futures:
            future.result(timeout=30)
    for worker in workers:
        worker.join(30)
        assert worker.exitcode == 0
    assert len(log.read_text().splitlines()) == 42
    assert len(set(log.read_text().splitlines())) == 42
    wal = files.WriteAheadLog(log, repo_root=tmp_path)
    assert wal.read_uncommitted() == ()
    with files.file_lock(wal.journal_path, "r", repo_root=tmp_path) as handle:
        entries, digests, committed = wal._read_journal_locked(handle)
    assert len(entries) == len(digests) == len(committed) == 92


def test_fsync_order_and_locks(tmp_path, monkeypatch):
    log = tmp_path / "progress.md"
    journal = log.with_suffix(".md.journal")
    original_lock = files.file_lock
    original_fsync = files.os.fsync
    held = {}
    synced = []

    @contextmanager
    def tracked_lock(path, *args, **kwargs):
        with original_lock(path, *args, **kwargs) as handle:
            held[handle.fileno()] = Path(path)
            try:
                yield handle
            finally:
                held.pop(handle.fileno())

    def synced_locked(fd):
        assert fd in held, "fsync must occur while the existing sibling lock is held"
        synced.append(held[fd])
        original_fsync(fd)

    monkeypatch.setattr(files, "file_lock", tracked_lock)
    monkeypatch.setattr(files.os, "fsync", synced_locked)
    files._write_line_with_wal(log, "durable", repo_root=tmp_path)
    assert synced == [journal, log, journal]
    assert journal.stat().st_mode & 0o777 == 0o600
    assert files.WriteAheadLog(log, repo_root=tmp_path).read_uncommitted() == ()


def test_failed_intent_fsync_does_not_apply_log_or_publish_proof(tmp_path, monkeypatch):
    log = tmp_path / "progress.md"
    _seed(log, 10)
    files._write_line_with_wal(log, "warm", repo_root=tmp_path)
    original = files.os.fsync

    def fail(fd):
        raise OSError("injected durability failure")

    monkeypatch.setattr(files.os, "fsync", fail)
    with pytest.raises(OSError, match="durability"):
        files._write_line_with_wal(log, "pending", repo_root=tmp_path)
    assert log.read_text() == "warm\n"
    monkeypatch.setattr(files.os, "fsync", original)
    wal = files.WriteAheadLog(log, repo_root=tmp_path)
    assert len(wal.read_uncommitted()) == 1
    assert wal.replay_uncommitted() == 1
    assert log.read_text() == "warm\npending\n"


def test_nonterminated_tail_and_reserved_intent_field_are_not_certified(tmp_path):
    wal = _seed(tmp_path / "progress.md", 10)
    wal.journal_path.write_bytes(wal.journal_path.read_bytes().rstrip(b"\n"))
    entry_id = wal.write_entry({"op": "append", "content": "pending"})
    with pytest.raises(files.WalJournalCorruptError):
        wal.commit_entry(entry_id)

    other = _seed(tmp_path / "other.md", 10)
    entry_id = other.write_entry({"op": "append", "ref_id": "not an intent field"})
    with pytest.raises(files.WalJournalCorruptError, match="invalid operation"):
        other.commit_entry(entry_id)


@pytest.mark.skipif(os.name != "posix", reason="fast path requires POSIX change time")
def test_cache_is_bounded_and_eviction_revalidates(tmp_path, monkeypatch):
    first = None
    for index in range(files.WriteAheadLog._VALIDATION_CACHE_LIMIT + 2):
        log = tmp_path / f"{index}.md"
        files._write_line_with_wal(log, "warm", repo_root=tmp_path)
        first = log if first is None else first
    cache = files.WriteAheadLog._validated_journals
    assert len(cache) <= files.WriteAheadLog._VALIDATION_CACHE_LIMIT
    assert first.with_suffix(".md.journal") not in cache
    original = files.WriteAheadLog._read_journal_locked
    scans = []

    def counted(self, handle):
        scans.append(self.journal_path)
        return original(self, handle)

    monkeypatch.setattr(files.WriteAheadLog, "_read_journal_locked", counted)
    files._write_line_with_wal(first, "after eviction", repo_root=tmp_path)
    assert scans == [first.with_suffix(".md.journal")]
    assert all(len(signature) == 5 and isinstance(highwater, str)
               for signature, highwater in cache.values())


def test_unavailable_change_time_retains_full_validation(tmp_path, monkeypatch):
    wal = _seed(tmp_path / "progress.md", 10)
    monkeypatch.setattr(files.WriteAheadLog, "_journal_signature", staticmethod(lambda _: None))
    entry_id = wal.write_entry({"op": "append", "content": "pending"})
    with wal.journal_path.open("ab") as handle:
        handle.write(b"{broken\n")
    with pytest.raises(files.WalJournalCorruptError):
        wal.commit_entry(entry_id)


@pytest.mark.parametrize("contradiction", ["different_payload", "intent_after_commit"])
def test_contradictory_historical_rows_remain_corrupt(tmp_path, contradiction):
    wal = _seed(tmp_path / "progress.md", 10)
    files._write_line_with_wal(wal.log_path, "warm", repo_root=tmp_path)
    row = json.loads(wal.journal_path.read_text().splitlines()[0])
    if contradiction == "different_payload":
        row["content"] = "contradictory"
        _, row["payload_digest"] = wal._canonical_payload(row)
    with wal.journal_path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")
    with pytest.raises(files.WalJournalCorruptError, match="contradictory"):
        wal.write_entry({"op": "append", "content": "must not append"})
