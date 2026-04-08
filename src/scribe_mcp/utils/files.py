"""File utilities for Scribe MCP with bulletproof atomic operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)
import shutil
import tempfile
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from scribe_mcp.config.settings import settings
from scribe_mcp.security.sandbox import safe_file_operation

# Cross-platform file locking
try:
    import msvcrt
    HAS_WINDOWS_LOCK = True
except ImportError:
    HAS_WINDOWS_LOCK = False
    # Try to import portalocker as fallback
    try:
        import portalocker
        HAS_PORTALOCKER = True
    except ImportError:
        HAS_PORTALOCKER = False

# POSIX fcntl - conditional import to prevent Windows crashes
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False


def _ensure_safe_path(
    path: Union[str, Path],
    operation: str = "read",
    context: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> Path:
    """
    Validate path access against the repo sandbox before performing operations.
    """
    root = (repo_root or settings.project_root).resolve()
    context_payload = dict(context or {"component": "files"})
    context_payload.setdefault("enforce_project", False)
    return safe_file_operation(root, Path(path), operation=operation, context=context_payload)


class FileLockError(Exception):
    """Raised when file locking fails."""
    pass


class AtomicFileError(Exception):
    """Raised when atomic file operation fails."""
    pass


@contextmanager
def file_lock(
    file_path: Union[str, Path],
    mode: str = 'r+',
    timeout: float = 30.0,
    repo_root: Optional[Path] = None,
):
    """
    Cross-platform file locking context manager.

    Note: This locks a sibling '.lock' file, not the target file itself.
    This design prevents accidental "optimization" that would compromise
    the cross-platform locking mechanism. The lock file coordinates
    access while the actual file handle is yielded for operations.

    Args:
        file_path: Path to the file to lock (creates sibling .lock file)
        mode: File mode for opening the target file
        timeout: Lock timeout in seconds

    Yields:
        File handle with exclusive lock held on sibling .lock file

    Raises:
        FileLockError: If lock cannot be acquired within timeout
    """
    file_path = _ensure_safe_path(file_path, operation="lock", repo_root=repo_root)
    lock_file = file_path.with_suffix(file_path.suffix + '.lock')

    # Create lock file
    lock_file.touch(exist_ok=True)

    lock_fd = None
    file_handle = None
    lock_acquired = False
    portalocker_lock = None

    try:
        # Try Windows locking first if available
        if HAS_WINDOWS_LOCK and os.name == 'nt':
            lock_fd = os.open(lock_file, os.O_RDWR | os.O_CREAT)
            try:
                msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
                lock_acquired = True
            except OSError:
                pass

        # Fallback to portalocker if Windows lock failed or not available
        if not lock_acquired and HAS_PORTALOCKER:
            try:
                portalocker_lock = portalocker.Lock(lock_file, 'r+', timeout=timeout)
                portalocker_lock.acquire()  # Acquire and hold across yield
                lock_acquired = True
            except portalocker.LockException:
                if portalocker_lock:
                    try:
                        portalocker_lock.release()
                    except Exception:
                        pass
                    portalocker_lock = None

        # Final fallback to POSIX fcntl
        if not lock_acquired and HAS_FCNTL:
            lock_fd = os.open(lock_file, os.O_RDWR | os.O_CREAT)
            start_time = time.time()
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_acquired = True
                    break
                except (IOError, OSError):
                    if time.time() - start_time > timeout:
                        raise FileLockError(f"Could not acquire lock on {file_path} within {timeout}s")
                    time.sleep(0.1)

        if not lock_acquired:
            raise FileLockError(f"Could not acquire lock on {file_path} within {timeout}s - no locking mechanism available")

        # Open the actual file
        file_handle = open(file_path, mode, encoding='utf-8')
        yield file_handle

    finally:
        # Release lock based on what we acquired
        if file_handle:
            file_handle.close()

        # Release portalocker lock last
        if portalocker_lock:
            try:
                portalocker_lock.release()
            except Exception:
                pass

        if lock_fd is not None:
            try:
                if HAS_WINDOWS_LOCK and os.name == 'nt':
                    msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
                os.close(lock_fd)
            except OSError:
                pass


class WriteAheadLog:
    """
    Write-Ahead Log for crash recovery.

    Every operation is first written to the journal before being applied
    to the main file. On startup, any uncommitted operations are replayed.
    """

    def __init__(
        self,
        log_path: Union[str, Path],
        repo_root: Optional[Path] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.repo_root = repo_root
        self.context = context or {"component": "wal"}
        safe_log = _ensure_safe_path(
            log_path,
            operation="append",
            context=self.context,
            repo_root=self.repo_root,
        )
        self.log_path = safe_log
        self.journal_path = _ensure_safe_path(
            safe_log.with_suffix(safe_log.suffix + '.journal'),
            operation="append",
            context={**self.context, "type": "journal"},
            repo_root=self.repo_root,
        )

    def write_entry(self, entry: Dict[str, Any]) -> str:
        """
        Write an entry to the journal.

        Args:
            entry: Dictionary containing operation details

        Returns:
            Entry ID (timestamp + hash)
        """
        entry_id = f"{datetime.now(timezone.utc).isoformat()}_{hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()[:8]}"
        entry['id'] = entry_id
        entry['timestamp'] = datetime.now(timezone.utc).isoformat()

        journal_line = json.dumps(entry) + '\n'

        with file_lock(self.journal_path, 'a', repo_root=self.repo_root) as f:
            f.write(journal_line)
            f.flush()
            os.fsync(f.fileno())

        return entry_id

    def commit_entry(self, entry_id: str):
        """Mark an entry as committed in the journal."""
        commit_entry = {
            'op': 'commit',
            'ref_id': entry_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        with file_lock(self.journal_path, 'a', repo_root=self.repo_root) as f:
            f.write(json.dumps(commit_entry) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def replay_uncommitted(self) -> int:
        """
        Replay any uncommitted entries from the journal.

        Returns:
            Number of entries replayed
        """
        if not self.journal_path.exists():
            return 0

        replayed = 0
        uncommitted = []

        with file_lock(self.journal_path, 'r', repo_root=self.repo_root) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('op') == 'append' and 'ref_id' not in entry:
                        uncommitted.append(entry)
                    elif entry.get('op') == 'commit':
                        # Remove committed entries from uncommitted list
                        ref_id = entry.get('ref_id')
                        uncommitted = [e for e in uncommitted if e.get('id') != ref_id]
                except json.JSONDecodeError:
                    continue

        # Replay uncommitted entries
        for entry in uncommitted:
            if entry.get('op') == 'append':
                content = entry.get('content', '')
                try:
                    self._apply_append(content)
                    self.commit_entry(entry['id'])
                    replayed += 1
                except Exception as e:
                    logger.warning("Failed to replay journal entry %s: %s", entry['id'], e)

        return replayed

    def _apply_append(self, content: str):
        """Apply an append operation to the main log."""
        with file_lock(self.log_path, 'a', repo_root=self.repo_root) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())


def atomic_write(
    file_path: Union[str, Path],
    content: str,
    mode: str = 'w',
    repo_root: Optional[Path] = None,
) -> None:
    """
    Atomically write content to a file.

    Write to temporary file first, then atomic rename.

    Note: This function only supports overwrite mode ('w'). For atomic append
    operations, use WriteAheadLog which provides proper WAL-based appending.

    Args:
        file_path: Target file path
        content: Content to write
        mode: Write mode - must be 'w' (overwrite) for atomic operations

    Raises:
        AtomicFileError: If atomic operation fails
        ValueError: If mode is not 'w' (only overwrite is atomic)
    """
    file_path = _ensure_safe_path(
        file_path,
        operation="write",
        context={"component": "files", "op": "atomic_write"},
        repo_root=repo_root,
    )

    # Validate mode - only overwrite is atomic
    if mode != 'w':
        raise ValueError(f"atomic_write only supports mode='w' (overwrite), got mode='{mode}'. Use WriteAheadLog for atomic append operations.")

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temporary file in same directory
    temp_path = file_path.with_suffix(file_path.suffix + '.tmp')

    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename with retry for Windows compatibility
        for attempt in range(5):
            try:
                temp_path.replace(file_path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1)

        # Sync parent directory
        dir_fd = os.open(file_path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    except Exception as e:
        # Clean up temp file on failure
        if temp_path.exists():
            temp_path.unlink()
        raise AtomicFileError(f"Atomic write failed: {e}")


async def async_atomic_write(
    file_path: Union[str, Path],
    content: str,
    mode: str = 'w',
    repo_root: Optional[Path] = None,
    document_store: Optional[Any] = None,
) -> None:
    """
    Asynchronously atomically write content to a file.

    This is the async version of atomic_write that maintains all bulletproof
    reliability while providing async compatibility for the codebase.

    Uses asyncio.to_thread() to execute the proven synchronous atomic_write
    implementation without blocking the event loop.

    Args:
        file_path: Target file path
        content: Content to write
        mode: Write mode - must be 'w' (overwrite) for atomic operations
        repo_root: Repository root for path validation
        document_store: Optional DocumentStore for remote sync

    Raises:
        AtomicFileError: If atomic operation fails
        ValueError: If mode is not 'w' (only overwrite is atomic)
    """
    await asyncio.to_thread(atomic_write, file_path, content, mode, repo_root)

    # Fire-and-forget sync to remote object store when configured.
    if document_store and repo_root:
        try:
            from scribe_mcp.object_store import sync_file_to_store

            await sync_file_to_store(Path(file_path), content, Path(repo_root))
        except Exception:
            pass  # Never fail a write due to object store issues


def preflight_backup(
    file_path: Union[str, Path],
    *,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Create a preflight backup of the file in .scribe/backups/ directory.

    Args:
        file_path: File to backup
        repo_root: Repository root (defaults to settings.project_root)
        context: Optional context for security validation

    Returns:
        Path to the backup file in .scribe/backups/
    """
    file_path = _ensure_safe_path(
        file_path,
        operation="read",
        context=context or {"component": "files", "op": "backup"},
        repo_root=repo_root,
    )

    if not file_path.exists():
        raise AtomicFileError(f"Cannot backup non-existent file: {file_path}")

    # Determine effective repo root
    root = (repo_root or settings.project_root).resolve()

    # Create centralized backup directory
    backup_dir = root / ".scribe" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate path-preserving filename
    # Convert file path relative to repo root to use double underscores for directory separators
    try:
        relative_path = file_path.relative_to(root)
    except ValueError:
        # File is outside repo root, use absolute path components
        relative_path = Path(*file_path.parts[-3:])  # Use last 3 components

    # Replace directory separators with __ to preserve path structure
    path_parts = list(relative_path.parts)
    if len(path_parts) > 1:
        # Join directory parts with __, keep filename separate
        dir_prefix = "__".join(path_parts[:-1])
        filename = path_parts[-1]
        backup_name = f"{dir_prefix}__{filename}"
    else:
        backup_name = relative_path.name

    # Add timestamp and .bak extension
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    backup_filename = f"{backup_name}.preflight-{timestamp}.bak"
    backup_path = backup_dir / backup_filename

    shutil.copy2(file_path, backup_path)

    # Compatibility mirror: keep sibling backups only for core plan docs.
    # Research and nested artifacts must remain clean (no local .bak files).
    core_plan_docs = {
        "ARCHITECTURE_GUIDE.md",
        "PHASE_PLAN.md",
        "CHECKLIST.md",
        "PROGRESS_LOG.md",
        "BUG_LOG.md",
        "SECURITY_LOG.md",
        "DOC_UPDATES.md",
    }
    if file_path.name in core_plan_docs:
        legacy_backup_path = file_path.parent / f"{file_path.stem}.preflight-{timestamp}.bak"
        if legacy_backup_path != backup_path:
            try:
                shutil.copy2(file_path, legacy_backup_path)
                legacy_backups = sorted(
                    file_path.parent.glob(f"{file_path.stem}.preflight-*.bak"),
                    key=lambda candidate: candidate.name,
                    reverse=True,
                )
                for stale_backup in legacy_backups[3:]:
                    try:
                        stale_backup.unlink()
                        logger.debug("Pruned stale legacy preflight backup: %s", stale_backup)
                    except OSError as exc:
                        logger.warning(
                            "Failed to prune stale legacy preflight backup %s: %s",
                            stale_backup,
                            exc,
                        )
            except OSError as exc:
                logger.warning("Failed to write legacy preflight backup %s: %s", legacy_backup_path, exc)

    # Enforce retention: keep only the 3 most recent preflight backups per source file.
    backups_for_file = sorted(
        backup_dir.glob(f"{backup_name}.preflight-*.bak"),
        key=lambda candidate: candidate.name,
        reverse=True,
    )
    stale_backups = backups_for_file[3:]
    for stale_backup in stale_backups:
        try:
            stale_backup.unlink()
            logger.debug("Pruned stale preflight backup: %s", stale_backup)
        except OSError as exc:
            logger.warning("Failed to prune stale preflight backup %s: %s", stale_backup, exc)

    return backup_path


def verify_file_integrity(
    file_path: Union[str, Path],
    *,
    include_line_count: bool = True,
    include_hash: bool = True,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Verify file integrity and return metadata.

    Args:
        file_path: File to verify

    Returns:
        Dictionary with integrity information
    """
    file_path = _ensure_safe_path(
        file_path,
        operation="read",
        context={"component": "files", "op": "verify"},
        repo_root=repo_root,
    )

    if not file_path.exists():
        return {
            'exists': False,
            'error': 'File does not exist'
        }

    try:
        stat = file_path.stat()

        sha256_digest = None
        line_count = None
        with open(file_path, 'rb') as f:
            sha256_hash = hashlib.sha256() if include_hash else None
            newline_count = 0
            last_byte = None
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                if include_hash and sha256_hash is not None:
                    sha256_hash.update(chunk)
                if include_line_count:
                    newline_count += chunk.count(b"\n")
                    last_byte = chunk[-1]

        if include_hash and sha256_hash is not None:
            sha256_digest = sha256_hash.hexdigest()

        if include_line_count:
            if newline_count > 0:
                line_count = newline_count
                if stat.st_size > 0 and last_byte is not None and last_byte != ord("\n"):
                    line_count += 1
            elif stat.st_size > 0:
                # No newline characters; treat entire file as single line
                line_count = 1

        return {
            'exists': True,
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 3),
            'line_count': line_count,
            'sha256': sha256_digest,
            'modified_time': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            'created_time': datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
        }

    except Exception as e:
        return {
            'exists': True,
            'error': str(e)
        }


async def ensure_parent(
    path: Path,
    *,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Create parent directories for the given path if missing."""
    await asyncio.to_thread(ensure_parent_sync, path, repo_root=repo_root, context=context)


def ensure_parent_sync(
    path: Path,
    *,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Create parent directories for the given path if missing (sync)."""
    safe_path = _ensure_safe_path(
        path,
        operation="mkdir",
        context=context or {"component": "files"},
        repo_root=repo_root,
    )
    safe_path.parent.mkdir(parents=True, exist_ok=True)


async def append_line(
    path: Path,
    line: str,
    use_wal: bool = True,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Bulletproof append a single line to the provided file path.

    Args:
        path: File path to append to
        line: Line content to append
        use_wal: Whether to use Write-Ahead Log for crash safety
    """
    path = _ensure_safe_path(
        path,
        operation="append",
        context=context or {"component": "logs"},
        repo_root=repo_root,
    )
    await ensure_parent(path, repo_root=repo_root, context=context)

    if use_wal:
        await asyncio.to_thread(_write_line_with_wal, path, line, repo_root, context)
    else:
        await asyncio.to_thread(_write_line, path, line, True, repo_root, context)


def _write_line_with_wal(
    path: Path,
    line: str,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Write line with Write-Ahead Log for crash safety."""
    path = _ensure_safe_path(
        path,
        operation="append",
        context=context or {"component": "wal"},
        repo_root=repo_root,
    )
    wal = WriteAheadLog(path, repo_root=repo_root, context=context)

    # Journal the operation first
    entry_id = wal.write_entry({
        'op': 'append',
        'content': line if line.endswith('\n') else line + '\n',
        'file_path': str(path)
    })

    try:
        # Apply the operation with file locking
        with file_lock(path, 'a', repo_root=repo_root) as f:
            f.write(line)
            if not line.endswith("\n"):
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        # Commit the operation
        wal.commit_entry(entry_id)
    except Exception as e:
        logger.warning("Failed to append line %s: %s", entry_id, e)
        raise


def _write_line(
    path: Path,
    line: str,
    use_lock: bool = True,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write line with optional file locking for safety.

    Args:
        path: File path to write to
        line: Line content to write
        use_lock: Whether to use file locking
    """
    path = _ensure_safe_path(
        path,
        operation="append",
        context=context or {"component": "logs"},
        repo_root=repo_root,
    )
    if use_lock:
        with file_lock(path, 'a', repo_root=repo_root) as handle:
            handle.write(line)
            if not line.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    else:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            if not line.endswith("\n"):
                handle.write("\n")


async def read_tail(
    path: Path,
    count: int,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Return the last `count` lines from `path`."""
    safe_path = _ensure_safe_path(
        path,
        operation="read",
        context=context or {"component": "logs", "op": "tail"},
        repo_root=repo_root,
    )
    return await asyncio.to_thread(_read_tail_sync, safe_path, count, repo_root, context)


def _read_tail_sync(
    path: Path,
    count: int,
    repo_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    path = _ensure_safe_path(
        path,
        operation="read",
        context=context or {"component": "logs", "op": "tail"},
        repo_root=repo_root,
    )
    if count <= 0:
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            tail = deque(handle, maxlen=count)
    except FileNotFoundError:
        return []
    return [line.rstrip("\n") for line in tail]


async def rotate_file(
    path: Path,
    suffix: str | None,
    confirm: bool = False,
    dry_run: bool = False,
    template_content: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Path:
    """
    Bulletproof rotate `path` to a timestamped copy and return the archive path.

    Args:
        path: File path to rotate
        suffix: Suffix for the archive name
        confirm: Whether to actually perform the rotation
        dry_run: If True, simulate rotation without making changes
        template_content: Optional template content to use for new log

    Returns:
        Archive path

    Raises:
        AtomicFileError: If rotation fails
    """
    path = _ensure_safe_path(path, operation="rotate", context={"component": "logs"}, repo_root=repo_root)
    suffix_part = suffix or "archive"
    archive = path.with_name(f"{path.name}.{suffix_part}.md")

    if not path.exists():
        raise AtomicFileError(f"Cannot rotate non-existent file: {path}")

    file_stat = path.stat()
    if file_stat.st_size == 0:
        raise AtomicFileError(f"Cannot rotate empty file: {path}")

    if dry_run or not confirm:
        # Return what would happen without actually doing it
        return archive

    # Pre-flight backup
    backup_path = await asyncio.to_thread(preflight_backup, path, repo_root=repo_root)

    # Lock order: journal → log
    log_lock_acquired = False
    try:
        # Generate new log content in temp file first (avoid template race)
        new_log_content = template_content or "# Progress Log\n\n"

        # Create temp file for new log content
        temp_path = path.with_suffix(path.suffix + '.new')
        await asyncio.to_thread(_write_temp_file, temp_path, new_log_content, repo_root)

        try:
            # Acquire log lock BEFORE any file operations
            with file_lock(path, 'r+', timeout=30.0, repo_root=repo_root) as f:
                log_lock_acquired = True

                # Create archive with unique name to avoid overwrites
                if archive.exists():
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
                    archive = archive.with_name(f"{archive.stem}_{timestamp}{archive.suffix}")

                await ensure_parent(archive, repo_root=repo_root)

                # Atomic rotation: rename original to archive
                await asyncio.to_thread(path.rename, archive)

                # Atomic rename: temp → new log
                temp_path.replace(path)

                # Sync parent directory
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)

                return archive

        finally:
            # Ensure temp file is cleaned up
            if temp_path.exists():
                temp_path.unlink()

    except Exception as e:
        # Rollback: restore from backup if rotation failed
        try:
            if backup_path.exists():
                await asyncio.to_thread(backup_path.rename, path)
        except Exception as rollback_error:
            logger.error("Critical: Failed to rollback rotation: %s", rollback_error)

        raise AtomicFileError(f"Rotation failed and was rolled back: {e}")

    finally:
        # Lock will be automatically released by file_lock context manager
        if log_lock_acquired:
            # Log lock is released by exiting the context manager
            pass


def _write_temp_file(temp_path: Path, content: str, repo_root: Optional[Path] = None) -> None:
    """Write content to temporary file."""
    temp_path = _ensure_safe_path(
        temp_path,
        operation="write",
        context={"component": "files", "op": "temp"},
        repo_root=repo_root,
    )
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


def _create_new_log(path: Path, repo_root: Optional[Path] = None) -> None:
    """
    Create a new progress log file with proper header.

    DEPRECATED: Use template_content parameter in rotate_file instead.

    Args:
        path: Path where to create the new log
    """
    path = _ensure_safe_path(path, operation="write", context={"component": "logs", "op": "new"}, repo_root=repo_root)
    with file_lock(path, 'w', repo_root=repo_root) as f:
        f.write("# Progress Log\n\n")
        f.flush()
        os.fsync(f.fileno())
