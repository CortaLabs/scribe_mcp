"""Retained-WAL append cost and integrity contracts on real files."""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import builtins

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


def _lock_exclusion_worker(log, root, connection, parent_active, backend, bypass):
    """Attempt the parent's sibling lock before and after its release."""
    files.HAS_WINDOWS_LOCK = False
    files.HAS_PORTALOCKER = backend == "portalocker"
    files.HAS_FCNTL = backend == "fcntl"

    @contextmanager
    def unlocked(path, mode, **kwargs):
        with open(path, mode, encoding="utf-8") as handle:
            yield handle

    acquire = unlocked if bypass else files.file_lock
    try:
        connection.send("ready")
        if not connection.poll(10) or connection.recv() != "attempt-held":
            raise AssertionError("missing held-phase command")
        try:
            with acquire(log, "a", timeout=.05, repo_root=Path(root)):
                connection.send(("entered-held", parent_active.is_set()))
        except files.FileLockError:
            connection.send(("blocked", False))
        if not connection.poll(10) or connection.recv() != "attempt-released":
            raise AssertionError("missing released-phase command")
        with acquire(log, "a", timeout=2, repo_root=Path(root)):
            connection.send(("entered-released", parent_active.is_set()))
    finally:
        connection.close()


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

pytestmark = [pytest.mark.core, pytest.mark.regression, pytest.mark.storage,
              pytest.mark.usefixtures("test_agent")]


@pytest.mark.parametrize("native_ok", [True, False])
@pytest.mark.parametrize("fallback", [True, False])
def test_windows_import_and_native_fallback(tmp_path, native_ok, fallback):
    """Execute the actual capability imports with a simulated Windows module."""
    calls = []
    native = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)

    def locking(fd, operation, size):
        calls.append(operation)
        if operation == native.LK_NBLCK and not native_ok:
            raise OSError("contended")

    native.locking = locking
    original_import = builtins.__import__

    def controlled_import(name, *args, **kwargs):
        if name == "msvcrt":
            return native
        if name == "fcntl" or (name == "portalocker" and not fallback):
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    namespace = {}
    source = Path(files.__file__).read_text().split("def _ensure_safe_path", 1)[0]
    with patch("builtins.__import__", controlled_import):
        exec(compile(source, files.__file__, "exec"), namespace)
    assert namespace["HAS_PORTALOCKER"] is fallback
    fake_os = SimpleNamespace(name="nt", open=os.open, close=os.close,
                              O_RDWR=os.O_RDWR, O_CREAT=os.O_CREAT)
    log = tmp_path / "windows.txt"
    log.touch()
    with patch.dict(files.file_lock.__wrapped__.__globals__, {
        "os": fake_os, "msvcrt": native,
        "HAS_WINDOWS_LOCK": True, "HAS_FCNTL": False,
        "HAS_PORTALOCKER": namespace["HAS_PORTALOCKER"],
    }):
        if native_ok or fallback:
            with files.file_lock(log, repo_root=tmp_path) as handle:
                handle.write("ok")
            assert log.read_text() == "ok"
        else:
            with pytest.raises(files.FileLockError):
                with files.file_lock(log, timeout=0, repo_root=tmp_path):
                    pytest.fail("unlocked entry")
    assert calls == ([native.LK_NBLCK, native.LK_UNLCK] if native_ok
                     else [native.LK_NBLCK])


def test_native_unlock_error_always_closes_descriptor(tmp_path):
    descriptors = []
    native = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)

    def locking(fd, operation, size):
        if operation == native.LK_UNLCK:
            raise OSError("unlock failure")

    def tracked_open(*args):
        fd = os.open(*args)
        descriptors.append(fd)
        return fd

    native.locking = locking
    fake_os = SimpleNamespace(name="nt", open=tracked_open, close=os.close,
                              O_RDWR=os.O_RDWR, O_CREAT=os.O_CREAT)
    log = tmp_path / "unlock.txt"
    log.touch()
    try:
        with patch.dict(files.file_lock.__wrapped__.__globals__, {
            "os": fake_os, "msvcrt": native, "HAS_WINDOWS_LOCK": True,
            "HAS_PORTALOCKER": False, "HAS_FCNTL": False,
        }):
            with files.file_lock(log, repo_root=tmp_path):
                pass
        for fd in descriptors:
            with pytest.raises(OSError):
                os.fstat(fd)
    finally:
        for fd in descriptors:
            try:
                os.close(fd)
            except OSError:
                pass


def test_fcntl_open_failure_does_not_close_a_reused_descriptor(tmp_path):
    """A failed replacement open must not clean up the released descriptor."""
    native_fds = []
    unrelated_fds = []

    def replacement_open(path, flags):
        if not native_fds:
            fd = os.open(path, flags)
            native_fds.append(fd)
            return fd
        # The released slot is reused by another resource before open fails.
        unrelated_fds.append(os.open(tmp_path / "unrelated", flags))
        raise OSError("replacement open failed")

    def native_contended(*args):
        raise OSError("native lock contended")

    fake_os = SimpleNamespace(name="nt", open=replacement_open, close=os.close,
                              O_RDWR=os.O_RDWR, O_CREAT=os.O_CREAT)
    native = SimpleNamespace(locking=native_contended, LK_NBLCK=1, LK_UNLCK=2)
    log = tmp_path / "replacement.txt"
    log.touch()
    try:
        with patch.dict(files.file_lock.__wrapped__.__globals__, {
            "os": fake_os, "msvcrt": native, "HAS_WINDOWS_LOCK": True,
            "HAS_PORTALOCKER": False, "HAS_FCNTL": True,
        }):
            with pytest.raises(OSError, match="replacement open failed"):
                with files.file_lock(log, repo_root=tmp_path):
                    pytest.fail("failed acquisition entered body")
        assert unrelated_fds == native_fds, "OS must reuse the released slot"
        os.fstat(unrelated_fds[0])
    finally:
        for fd in set(native_fds + unrelated_fds):
            try:
                os.close(fd)
            except OSError:
                pass


def test_fcntl_close_then_raise_does_not_close_a_reused_descriptor(tmp_path):
    native_fds, unrelated_fds, close_calls = [], [], []
    failure = OSError("close released descriptor then failed")

    def native_open(path, flags):
        fd = os.open(path, flags)
        native_fds.append(fd)
        return fd

    def close_then_raise(fd):
        close_calls.append(fd)
        os.close(fd)
        if len(close_calls) == 1:
            unrelated_fds.append(os.open(tmp_path / "unrelated-close", os.O_RDWR | os.O_CREAT))
            raise failure

    def native_contended(*args):
        raise OSError("native lock contended")

    fake_os = SimpleNamespace(name="nt", open=native_open, close=close_then_raise,
                              O_RDWR=os.O_RDWR, O_CREAT=os.O_CREAT)
    native = SimpleNamespace(locking=native_contended, LK_NBLCK=1, LK_UNLCK=2)
    log = tmp_path / "close-raise.txt"
    log.touch()
    try:
        with patch.dict(files.file_lock.__wrapped__.__globals__, {
            "os": fake_os, "msvcrt": native, "HAS_WINDOWS_LOCK": True,
            "HAS_PORTALOCKER": False, "HAS_FCNTL": True,
        }):
            with pytest.raises(OSError) as caught:
                with files.file_lock(log, repo_root=tmp_path):
                    pytest.fail("failed close entered body")
        assert caught.value is failure
        assert unrelated_fds == native_fds, "OS must reuse the released slot"
        os.fstat(unrelated_fds[0])
        assert close_calls == native_fds
    finally:
        for fd in set(native_fds + unrelated_fds):
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.mark.skipif(os.name != "posix" or not files.HAS_FCNTL or not files.HAS_PORTALOCKER,
                    reason="requires actual POSIX fcntl and installed portalocker")
@pytest.mark.parametrize("backend", ["portalocker", "fcntl"])
@pytest.mark.parametrize("bypass", [False, True], ids=["real-lock", "bypass-sensitivity"])
def test_coordinated_process_lock_exclusion(tmp_path, monkeypatch, backend, bypass):
    from contextlib import nullcontext

    monkeypatch.setattr(files, "HAS_WINDOWS_LOCK", False)
    monkeypatch.setattr(files, "HAS_PORTALOCKER", backend == "portalocker")
    monkeypatch.setattr(files, "HAS_FCNTL", backend == "fcntl")
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe()
    parent_active = context.Event()
    log = tmp_path / "process-held.txt"
    process = context.Process(target=_lock_exclusion_worker, args=(
        str(log), str(tmp_path), child_connection, parent_active, backend, bypass))
    try:
        with files.file_lock(log, "a", repo_root=tmp_path):
            parent_active.set()
            process.start()
            child_connection.close()
            assert parent_connection.poll(30), "child did not become ready"
            assert parent_connection.recv() == "ready"
            parent_connection.send("attempt-held")
            assert parent_connection.poll(10), "child did not finish held attempt"
            held_result = parent_connection.recv()
            if bypass:
                assert held_result == ("entered-held", True)
            with (pytest.raises(AssertionError, match="child entered held critical section")
                  if bypass else nullcontext()):
                assert held_result == ("blocked", False), "child entered held critical section"
        parent_active.clear()
        parent_connection.send("attempt-released")
        assert parent_connection.poll(10), "child did not acquire after release"
        assert parent_connection.recv() == ("entered-released", False)
        process.join(10)
        assert not process.is_alive()
        assert process.exitcode == 0
    finally:
        parent_active.clear()
        parent_connection.close()
        child_connection.close()
        if process.pid is not None:
            process.join(2)
            if process.is_alive():
                process.terminate()
                process.join(5)
            assert not process.is_alive(), "owned child failed to terminate"


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_lock_body_failure_releases_target_and_sibling(tmp_path, failure):
    log = tmp_path / "body.txt"
    log.touch()
    with pytest.raises(failure):
        with files.file_lock(log, repo_root=tmp_path) as handle:
            raise failure("body")
    assert handle.closed
    with files.file_lock(log, timeout=0, repo_root=tmp_path):
        pass


def test_lock_unavailable_and_sandbox(tmp_path, monkeypatch):
    for name in ("HAS_WINDOWS_LOCK", "HAS_PORTALOCKER", "HAS_FCNTL"):
        monkeypatch.setattr(files, name, False)
    log = tmp_path / "unavailable"
    with pytest.raises(files.FileLockError, match="no locking mechanism"):
        with files.file_lock(log, timeout=0, repo_root=tmp_path):
            pytest.fail("unlocked entry")
    # Verify delegation to validation, rather than certifying sandbox policy.
    from contextlib import nullcontext

    target = tmp_path / "validation.txt"
    denial = RuntimeError("sentinel validation denial")
    for bypass in (False, True):
        entered = False
        behavior = {"return_value": target} if bypass else {"side_effect": denial}
        with patch.object(files, "_ensure_safe_path", **behavior) as validation:
            with pytest.raises((RuntimeError, files.FileLockError)) as caught:
                with files.file_lock(target, repo_root=tmp_path):
                    entered = True
            validation.assert_called_once_with(target, operation="lock", repo_root=tmp_path)
            assert not entered
            if bypass:
                assert isinstance(caught.value, files.FileLockError)
            # The same identity assertion must fail when validation is bypassed;
            # the unavailable-lock error is not accepted as a validation denial.
            with (pytest.raises(AssertionError, match="validation denial changed")
                  if bypass else nullcontext()):
                assert caught.value is denial, "validation denial changed"


@pytest.mark.skipif(not files.HAS_FCNTL or not files.HAS_PORTALOCKER,
                    reason="requires both cooperative POSIX implementations")
def test_portalocker_and_fcntl_exclude_each_other(tmp_path, monkeypatch):
    log = tmp_path / "interop.txt"
    log.touch()
    sibling = log.with_suffix(".txt.lock")
    with files.portalocker.Lock(sibling, "a", timeout=0):
        with monkeypatch.context() as selected:
            selected.setattr(files, "HAS_PORTALOCKER", False)
            with pytest.raises(files.FileLockError):
                with files.file_lock(log, timeout=0, repo_root=tmp_path):
                    pytest.fail("fcntl ignored portalocker")
    with sibling.open("r+") as native:
        files.fcntl.flock(native, files.fcntl.LOCK_EX | files.fcntl.LOCK_NB)
        with monkeypatch.context() as selected:
            selected.setattr(files, "HAS_FCNTL", False)
            with pytest.raises(files.FileLockError):
                with files.file_lock(log, timeout=0, repo_root=tmp_path):
                    pytest.fail("portalocker ignored fcntl")
    with files.file_lock(log, timeout=0, repo_root=tmp_path):
        pass


def test_fallback_uses_one_monotonic_deadline(tmp_path, monkeypatch):
    clock = [10.0]
    attempts = []
    log = tmp_path / "deadline.txt"
    log.touch()
    real_portalocker = files.portalocker

    class Exhausted:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs["timeout"]
        def acquire(self):
            clock[0] += self.timeout
            raise real_portalocker.LockException("held")
        def release(self):
            pass

    def contended(fd, flags):
        attempts.append(clock[0])
        raise OSError("held")

    monkeypatch.setattr(files, "HAS_WINDOWS_LOCK", False)
    monkeypatch.setattr(files, "HAS_PORTALOCKER", True)
    monkeypatch.setattr(files, "HAS_FCNTL", True)
    monkeypatch.setattr(files, "portalocker", SimpleNamespace(
        Lock=Exhausted, LockException=real_portalocker.LockException))
    monkeypatch.setattr(files, "fcntl", SimpleNamespace(
        flock=contended, LOCK_EX=1, LOCK_NB=2))
    monkeypatch.setattr(files, "time", SimpleNamespace(
        monotonic=lambda: clock[0], time=lambda: clock[0],
        sleep=lambda delay: clock.__setitem__(0, clock[0]+delay)))
    with pytest.raises(files.FileLockError):
        with files.file_lock(log, timeout=.2, repo_root=tmp_path):
            pytest.fail("unlocked entry")
    assert clock[0] == pytest.approx(10.2)
    assert len(attempts) == 1


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_lock_acquisition_error_releases_resources(tmp_path, monkeypatch, failure):
    released = []
    class BrokenLock:
        def __init__(self, *args, **kwargs):
            pass
        def acquire(self):
            raise failure("acquire")
        def release(self):
            released.append(True)
    monkeypatch.setattr(files.portalocker, "Lock", BrokenLock)
    log = tmp_path / "acquire.txt"
    log.touch()
    with pytest.raises(failure):
        with files.file_lock(log, repo_root=tmp_path):
            pytest.fail("unlocked entry")
    assert released == [True]


def test_target_open_and_close_errors_release_sibling(tmp_path):
    log = tmp_path / "target.txt"
    with pytest.raises(FileNotFoundError):
        with files.file_lock(log, "r", timeout=0, repo_root=tmp_path):
            pytest.fail("missing target opened")
    log.touch()
    actual_open = builtins.open
    handles = []
    class BrokenClose:
        def __init__(self, handle):
            self.handle = handle
        def close(self):
            self.handle.close()
            raise OSError("target close")
    def target_open(path, *args, **kwargs):
        handle = actual_open(path, *args, **kwargs)
        if Path(path) == log:
            handles.append(handle)
            return BrokenClose(handle)
        return handle
    with patch.object(files, "open", target_open, create=True):
        with pytest.raises(OSError, match="target close"):
            with files.file_lock(log, repo_root=tmp_path):
                pass
    assert all(h.closed for h in handles)
    with files.file_lock(log, timeout=0, repo_root=tmp_path):
        pass


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
               for signature, highwater, _lineage, _commit_bound in cache.values())


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


@pytest.mark.storage
@pytest.mark.skipif(os.name != "posix", reason="fast path requires POSIX change time")
@pytest.mark.parametrize("history", [10, 3000])
def test_interleaved_pending_commits_do_not_rescan_history(tmp_path, test_agent, history):
    log = tmp_path / "interleaved.md"
    _seed(log, history)
    files._write_line_with_wal(log, "warm", repo_root=tmp_path)
    writers = [files.WriteAheadLog(log, repo_root=tmp_path, context={"agent": test_agent})
               for _ in range(2)]
    scans = []
    original = files.WriteAheadLog._read_journal_locked

    def counted(self, handle):
        scans.append(os.fstat(handle.fileno()).st_size)
        return original(self, handle)

    with patch.object(files.WriteAheadLog, "_read_journal_locked", counted):
        ids = [wal.write_entry({"op": "append", "content": f"{index}\n"})
               for index, wal in enumerate(writers)]
        for index, (wal, entry_id) in enumerate(zip(writers, ids)):
            wal._apply_append(f"{index}\n")
            wal.commit_entry(entry_id)
    assert scans == [], f"interleaved commits rescanned {sum(scans)} retained bytes"
    assert log.read_text().splitlines() == ["warm", "0", "1"]
    assert writers[0].read_uncommitted() == ()


@pytest.mark.storage
@pytest.mark.skipif(os.name != "posix", reason="fast path requires POSIX change time")
@pytest.mark.parametrize("log_count", [1, 4])
def test_many_ordered_pending_writers_reuse_bounded_proof(tmp_path, test_agent, log_count):
    logs = [tmp_path / f"ordered-{index}.md" for index in range(log_count)]
    for log in logs:
        _seed(log, 50)
        files._write_line_with_wal(log, "warm", repo_root=tmp_path)
    writers = [files.WriteAheadLog(logs[index % log_count], repo_root=tmp_path,
                                  context={"agent": test_agent}) for index in range(16)]
    with patch.object(files.WriteAheadLog, "_read_journal_locked",
                      side_effect=AssertionError("cooperative history rescan")):
        ids = [wal.write_entry({"op": "append", "content": f"writer:{index}\n"})
               for index, wal in enumerate(writers)]
        for index, (wal, entry_id) in enumerate(zip(writers, ids)):
            wal._apply_append(f"writer:{index}\n")
            wal.commit_entry(entry_id)
    for index, log in enumerate(logs):
        assert log.read_text().splitlines() == ["warm"] + [
            f"writer:{i}" for i in range(index, 16, log_count)]
        assert files.WriteAheadLog(log, repo_root=tmp_path).read_uncommitted() == ()


@pytest.mark.storage
def test_other_instance_commit_does_not_duplicate_original_commit(tmp_path, test_agent):
    log = tmp_path / "duplicate.md"
    _seed(log, 10)
    original = files.WriteAheadLog(log, repo_root=tmp_path, context={"agent": test_agent})
    other = files.WriteAheadLog(log, repo_root=tmp_path, context={"agent": test_agent})
    entry_id = original.write_entry({"op": "append", "content": "original"})
    newer = other.write_entry({"op": "append", "content": "newer"})
    other.commit_entry(entry_id)
    other.commit_entry(newer)
    before = original.journal_path.read_bytes()
    original.commit_entry(entry_id)
    original.commit_entry(entry_id)
    assert original.journal_path.read_bytes() == before
    rows = [json.loads(line) for line in before.splitlines()]
    assert sum(row.get("ref_id") == entry_id for row in rows) == 1
    assert original.read_uncommitted() == ()
    with pytest.raises(files.WalJournalCorruptError, match="unknown"):
        original.commit_entry("unknown-id")


@pytest.mark.storage
def test_reverse_commit_order_retains_authoritative_fallback(tmp_path, test_agent):
    log = tmp_path / "reverse.md"
    _seed(log, 10)
    writers = [files.WriteAheadLog(log, repo_root=tmp_path, context={"agent": test_agent})
               for _ in range(3)]
    ids = [wal.write_entry({"op": "append", "content": str(index)})
           for index, wal in enumerate(writers)]
    for wal, entry_id in reversed(list(zip(writers, ids))):
        wal.commit_entry(entry_id)
    before = writers[0].journal_path.read_bytes()
    for wal, entry_id in zip(writers, ids):
        wal.commit_entry(entry_id)
    assert writers[0].journal_path.read_bytes() == before
    assert writers[0].read_uncommitted() == ()
    assert sum(json.loads(line).get("op") == "commit" for line in before.splitlines()) == 13


@pytest.mark.storage
@pytest.mark.skipif(os.name != "posix", reason="fast path requires POSIX change time")
@pytest.mark.parametrize("reset", ["evict", "rescan", "valid_rewrite"])
def test_pending_lineage_is_lost_after_validation_reset(tmp_path, test_agent, reset):
    wal = _seed(tmp_path / "pending.md", 10)
    wal.context = {"agent": test_agent}
    entry_id = wal.write_entry({"op": "append", "content": "pending"})
    if reset == "evict":
        for index in range(wal._VALIDATION_CACHE_LIMIT):
            files._write_line_with_wal(tmp_path / f"evict-{index}.md", "x", repo_root=tmp_path)
    elif reset == "rescan":
        assert len(wal.read_uncommitted()) == 1
    else:
        wal.journal_path.write_bytes(wal.journal_path.read_bytes())
        # Another reader certifies the new bytes, which must not revive the
        # original instance's stale pending proof merely by matching an ID.
        assert len(files.WriteAheadLog(wal.log_path, repo_root=tmp_path).read_uncommitted()) == 1
    scans = []
    original = files.WriteAheadLog._read_journal_locked

    def counted(self, handle):
        scans.append(self.journal_path)
        return original(self, handle)

    with patch.object(files.WriteAheadLog, "_read_journal_locked", counted):
        wal.commit_entry(entry_id)
    assert scans == [wal.journal_path]
    assert wal.read_uncommitted() == ()


@pytest.mark.storage
def test_simulated_nonposix_interleaving_scans_every_boundary(tmp_path, test_agent, monkeypatch):
    wal = _seed(tmp_path / "nonposix.md", 10)
    other = files.WriteAheadLog(wal.log_path, repo_root=tmp_path, context={"agent": test_agent})
    monkeypatch.setattr(files.WriteAheadLog, "_journal_signature", staticmethod(lambda _: None))
    scans = []
    original = files.WriteAheadLog._read_journal_locked

    def counted(self, handle):
        scans.append(self.journal_path)
        return original(self, handle)

    with patch.object(files.WriteAheadLog, "_read_journal_locked", counted):
        a = wal.write_entry({"op": "append", "content": "a"})
        b = other.write_entry({"op": "append", "content": "b"})
        wal.commit_entry(a)
        other.commit_entry(b)
    assert scans == [wal.journal_path] * 4
    assert wal.read_uncommitted() == ()


@pytest.mark.storage
@pytest.mark.parametrize("operation", ["intent", "commit"])
@pytest.mark.parametrize("fault", ["write", "flush", "fsync"])
def test_failed_cooperative_mutation_invalidates_pending_proof(
    tmp_path, test_agent, monkeypatch, operation, fault,
):
    wal = _seed(tmp_path / "fault.md", 10)
    wal.context = {"agent": test_agent}
    entry_id = wal.write_entry({"op": "append", "content": "pending"})
    original_lock = files.file_lock
    original_fsync = files.os.fsync

    class FaultHandle:
        def __init__(self, handle):
            self.handle = handle

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def write(self, value):
            result = self.handle.write(value)
            if fault == "write":
                raise OSError("ambiguous journal write")
            return result

        def flush(self):
            self.handle.flush()
            if fault == "flush":
                raise OSError("ambiguous journal flush")

    @contextmanager
    def failed_lock(*args, **kwargs):
        with original_lock(*args, **kwargs) as handle:
            yield FaultHandle(handle)

    def failed_fsync(fd):
        original_fsync(fd)
        raise OSError("ambiguous journal fsync")

    with monkeypatch.context() as injected:
        injected.setattr(files, "file_lock", failed_lock)
        if fault == "fsync":
            injected.setattr(files.os, "fsync", failed_fsync)
        with pytest.raises(OSError, match="ambiguous journal"):
            if operation == "intent":
                files.WriteAheadLog(wal.log_path, repo_root=tmp_path).write_entry(
                    {"op": "append", "content": "other"})
            else:
                wal.commit_entry(entry_id)
    assert wal.journal_path not in wal._validated_journals
    scans = []
    original = files.WriteAheadLog._read_journal_locked

    def counted(self, handle):
        scans.append(self.journal_path)
        return original(self, handle)

    before = wal.journal_path.read_bytes()
    with patch.object(files.WriteAheadLog, "_read_journal_locked", counted):
        wal.commit_entry(entry_id)
    assert scans == [wal.journal_path]
    if operation == "commit":
        assert wal.journal_path.read_bytes() == before


@pytest.mark.storage
def test_ambiguous_materialized_fsync_replay_behavior_is_retained(tmp_path, test_agent, monkeypatch):
    log = tmp_path / "ambiguous.md"
    original_fsync = files.os.fsync
    synced = 0

    def fail_log_fsync(fd):
        nonlocal synced
        original_fsync(fd)
        synced += 1
        if synced == 2:
            raise OSError("ambiguous materialized fsync")

    with monkeypatch.context() as injected:
        injected.setattr(files.os, "fsync", fail_log_fsync)
        with pytest.raises(OSError, match="ambiguous materialized"):
            files._write_line_with_wal(log, "pending", repo_root=tmp_path,
                                       context={"agent": test_agent})
    assert log.read_text() == "pending\n"
    wal = files.WriteAheadLog(log, repo_root=tmp_path)
    assert len(wal.read_uncommitted()) == 1
    assert wal.replay_uncommitted() == 1
    assert log.read_text() == "pending\npending\n"
    assert wal.read_uncommitted() == ()


@pytest.mark.storage
def test_real_interleaved_threads_and_processes_on_different_logs(tmp_path, test_agent, monkeypatch):
    logs = [tmp_path / f"concurrent-{index}.md" for index in range(2)]
    for log in logs:
        _seed(log, 50)
    barrier = threading.Barrier(8)
    original = files.WriteAheadLog._apply_append

    def synchronized_append(self, content):
        barrier.wait(timeout=30)
        return original(self, content)

    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=_append_worker, args=(str(log), str(tmp_path), 3))
                 for log in logs]
    for process in processes:
        process.start()
    monkeypatch.setattr(files.WriteAheadLog, "_apply_append", synchronized_append)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(files._write_line_with_wal, logs[index % 2], f"thread:{index}",
                               tmp_path, {"agent": test_agent}) for index in range(8)]
        for future in futures:
            future.result(timeout=30)
    for process in processes:
        process.join(30)
        assert process.exitcode == 0
    for index, log in enumerate(logs):
        lines = log.read_text().splitlines()
        assert len(lines) == len(set(lines)) == 7
        assert {line for line in lines if line.startswith("thread:")} == {
            f"thread:{i}" for i in range(index, 8, 2)}
        assert files.WriteAheadLog(log, repo_root=tmp_path).read_uncommitted() == ()


@pytest.mark.storage
def test_arbitrary_explicit_ids_do_not_enlarge_validation_metadata(tmp_path, test_agent):
    wal = _seed(tmp_path / "explicit.md", 10)
    wal.context = {"agent": test_agent}
    explicit_id = "z" * 10000
    wal.write_entry({"op": "append", "content": "explicit"}, entry_id=explicit_id)
    wal.commit_entry(explicit_id)
    before = wal.journal_path.read_bytes()
    wal.commit_entry(explicit_id)
    assert wal.journal_path.read_bytes() == before
    assert wal.read_uncommitted() == ()
    for validation in wal._validated_journals.values():
        assert len(validation) == 4
        assert len(validation[0]) == 5
        assert len(validation[1]) <= 41
        assert type(validation[2]) is object
        assert len(validation[3]) <= 41


@pytest.mark.storage
@pytest.mark.skipif(os.name != "posix", reason="fast path requires POSIX change time")
def test_unchanged_pending_signature_still_proves_commit_after_clock_rollback(tmp_path, test_agent):
    wal = _seed(tmp_path / "rollback-pending.md", 10)
    wal.context = {"agent": test_agent}
    future = "2099-01-01T00:00:00.000001+00:00_00000000"
    wal.write_entry({"op": "append", "content": "future"}, entry_id=future)
    wal.commit_entry(future)
    # The new generated ID is below the retained future highwater. Intent
    # creation must scan, but the unchanged post-intent signature still proves
    # this new intent has not been committed: preserve the original shortcut.
    entry_id = wal.write_entry({"op": "append", "content": "present"})
    assert entry_id < future
    with patch.object(files.WriteAheadLog, "_read_journal_locked",
                      side_effect=AssertionError("lost unchanged-signature proof")):
        wal.commit_entry(entry_id)
    assert wal.read_uncommitted() == ()
