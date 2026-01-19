"""File system watcher for detecting manual document edits."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None



@dataclass
class FileChangeEvent:
    """Represents a file system change event."""
    file_path: Path
    event_type: str  # 'created', 'modified', 'deleted', 'moved'
    timestamp: float = field(default_factory=time.time)
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    metadata: Dict[str, any] = field(default_factory=dict)


class DocumentFileHandler(FileSystemEventHandler):
    """Handles file system events for document files."""

    def __init__(
        self,
        callback: Callable[[FileChangeEvent], None],
        watched_extensions: Set[str] = None,
        debounce_seconds: float = 1.0
    ):
        super().__init__()
        self.callback = callback
        self.watched_extensions = watched_extensions or {'.md', '.txt', '.json'}
        self.debounce_seconds = debounce_seconds
        self._pending_events: Dict[str, float] = {}
        self._logger = logging.getLogger(__name__)

    def _should_process_file(self, file_path: str) -> bool:
        """Check if file should be processed based on extension."""
        return Path(file_path).suffix.lower() in self.watched_extensions

    def _debounce_event(self, file_path: str) -> bool:
        """Check if event should be debounced (ignored due to recent activity)."""
        now = time.time()
        last_time = self._pending_events.get(file_path, 0)

        if now - last_time < self.debounce_seconds:
            return True  # Debounce this event

        self._pending_events[file_path] = now
        return False

    def _create_change_event(self, event: FileSystemEvent) -> Optional[FileChangeEvent]:
        """Create a FileChangeEvent from a watchdog event."""
        file_path = Path(event.src_path)

        if not self._should_process_file(str(file_path)):
            return None

        # Debounce rapid successive events
        if self._debounce_event(str(file_path)):
            return None

        try:
            # Calculate file size and checksum for file content changes
            size_bytes = None
            checksum = None

            if event.event_type in ['created', 'modified'] and file_path.exists():
                size_bytes = file_path.stat().st_size
                # Calculate simple checksum for change detection
                checksum = self._calculate_checksum(file_path)

            return FileChangeEvent(
                file_path=file_path,
                event_type=event.event_type,
                size_bytes=size_bytes,
                checksum=checksum,
                metadata={
                    'is_directory': event.is_directory,
                    'dest_path': getattr(event, 'dest_path', None)
                }
            )

        except (OSError, IOError) as e:
            self._logger.warning(f"Failed to process file event for {file_path}: {e}")
            return None

    def _calculate_checksum(self, file_path: Path) -> Optional[str]:
        """Calculate SHA-256 checksum of file content (first 64KB for consistency)."""
        try:
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                content = f.read(65536)  # 64KB for consistency with integrity verifier
                h.update(content)
            return h.hexdigest()
        except (OSError, IOError):
            return None

    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event."""
        if event.is_directory:
            return

        change_event = self._create_change_event(event)
        if change_event:
            try:
                self.callback(change_event)
            except Exception as e:
                self._logger.error(f"Error in file change callback: {e}")


class FileSystemWatcher:
    """File system watcher for monitoring document changes."""

    def __init__(
        self,
        project_root: Path,
        change_callback: Callable[[FileChangeEvent], None],
        watched_patterns: List[str] = None,
        debounce_seconds: float = 1.0,
        enable_watchdog: bool = True
    ):
        self.project_root = Path(project_root)
        self.change_callback = change_callback
        self.watched_patterns = watched_patterns or ['**/*.md', '**/*.txt', '**/*.json']
        self.debounce_seconds = debounce_seconds
        self.enable_watchdog = enable_watchdog and WATCHDOG_AVAILABLE
        self._observer = None
        self._polling_task = None
        self._is_running = False
        self._logger = logging.getLogger(__name__)

        # Track file states for change detection
        self._file_states: Dict[str, Dict[str, any]] = {}
        self._watched_paths: Set[Path] = set()

    async def start(self) -> bool:
        """Start the file system watcher."""
        if self._is_running:
            self._logger.warning("File watcher is already running")
            return True

        try:
            if self.enable_watchdog:
                success = await self._start_watchdog()
            else:
                success = await self._start_polling()

            if success:
                self._is_running = True
                self._logger.info(f"File watcher started for {self.project_root}")
                # Log which method we're using
                method = "watchdog" if self.enable_watchdog else "polling"
                self._logger.info(f"Using {method} for file monitoring")
            else:
                self._logger.error("Failed to start file watcher")

            return success

        except Exception as e:
            self._logger.error(f"Error starting file watcher: {e}")
            return False

    async def stop(self):
        """Stop the file system watcher."""
        if not self._is_running:
            return

        self._is_running = False

        if self._observer:
            # Stop the thread, then join off-loop to avoid blocking
            self._observer.stop()
            await asyncio.to_thread(self._observer.join, 2.0)
            self._observer = None

        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None

        self._logger.info("File watcher stopped")

    async def _start_watchdog(self) -> bool:
        """Start watchdog-based file monitoring."""
        if not WATCHDOG_AVAILABLE:
            self._logger.warning("Watchdog not available, falling back to polling")
            return await self._start_polling()

        try:
            self._observer = Observer()

            # Create event handler
            handler = DocumentFileHandler(
                callback=self._handle_file_change,
                debounce_seconds=self.debounce_seconds
            )

            # Add recursive watch for project root
            self._observer.schedule(handler, str(self.project_root), recursive=True)

            # Start the observer
            self._observer.start()

            # Initialize file states
            await self._initialize_file_states()

            return True

        except Exception as e:
            self._logger.error(f"Failed to start watchdog observer: {e}")
            return False

    async def _start_polling(self) -> bool:
        """Start polling-based file monitoring."""
        try:
            # Initialize file states
            await self._initialize_file_states()

            # Start polling task
            self._polling_task = asyncio.create_task(self._polling_loop())

            return True

        except Exception as e:
            self._logger.error(f"Failed to start polling watcher: {e}")
            return False

    async def _initialize_file_states(self):
        """Initialize tracking of current file states."""
        for pattern in self.watched_patterns:
            # glob off the loop
            paths = await asyncio.to_thread(lambda: list(self.project_root.glob(pattern)))
            for file_path in paths:
                if file_path.is_file():
                    await self._update_file_state(file_path)

    async def _update_file_state(self, file_path: Path):
        """Update the tracked state of a file."""
        try:
            stat = file_path.stat()
            self._file_states[str(file_path)] = {
                'mtime': stat.st_mtime,
                'size': stat.st_size,
                'checksum': self._calculate_checksum(file_path)
            }
        except (OSError, IOError):
            # File might be inaccessible
            pass

    def _calculate_checksum(self, file_path: Path) -> Optional[str]:
        """Calculate SHA-256 checksum of file content (first 64KB for consistency)."""
        try:
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                content = f.read(65536)  # 64KB for consistency with integrity verifier
                h.update(content)
            return h.hexdigest()
        except (OSError, ImportError):
            return None

    def _handle_file_change(self, change_event: FileChangeEvent):
        """Handle a detected file change."""
        try:
            # Add project-specific metadata
            change_event.metadata.update({
                'project_root': str(self.project_root),
                'relative_path': str(change_event.file_path.relative_to(self.project_root))
            })

            # Call the user-provided callback
            self.change_callback(change_event)

        except Exception as e:
            self._logger.error(f"Error handling file change: {e}")

    async def _polling_loop(self):
        """Main polling loop for file change detection."""
        poll_interval = max(1.0, self.debounce_seconds)

        while self._is_running:
            try:
                await self._check_for_changes()
                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(poll_interval)

    async def _check_for_changes(self):
        """Check for file changes via polling."""
        current_files = set()

        # Discover current files
        for pattern in self.watched_patterns:
            for file_path in self.project_root.glob(pattern):
                if file_path.is_file():
                    current_files.add(str(file_path))
                    await self._check_file_changes(file_path)

        # Check for deleted files
        for file_path_str in list(self._file_states.keys()):
            if file_path_str not in current_files:
                await self._handle_file_deletion(file_path_str)

    async def _check_file_changes(self, file_path: Path):
        """Check if a specific file has changed."""
        file_path_str = str(file_path)
        previous_state = self._file_states.get(file_path_str)

        try:
            current_stat = file_path.stat()
            current_state = {
                'mtime': current_stat.st_mtime,
                'size': current_stat.st_size,
                'checksum': self._calculate_checksum(file_path)
            }

            if previous_state:
                # Check for changes
                if (current_state['mtime'] != previous_state['mtime'] or
                    current_state['size'] != previous_state['size'] or
                    current_state['checksum'] != previous_state['checksum']):

                    # File has changed
                    change_event = FileChangeEvent(
                        file_path=file_path,
                        event_type='modified',
                        size_bytes=current_state['size'],
                        checksum=current_state['checksum'],
                        metadata={
                            'previous_state': previous_state,
                            'detection_method': 'polling'
                        }
                    )
                    self._handle_file_change(change_event)

            # Update tracked state
            self._file_states[file_path_str] = current_state

        except (OSError, IOError):
            # File might be inaccessible or deleted
            pass

    async def _handle_file_deletion(self, file_path_str: str):
        """Handle file deletion detected via polling."""
        if file_path_str in self._file_states:
            change_event = FileChangeEvent(
                file_path=Path(file_path_str),
                event_type='deleted',
                metadata={
                    'previous_state': self._file_states[file_path_str],
                    'detection_method': 'polling'
                }
            )
            self._handle_file_change(change_event)
            del self._file_states[file_path_str]

    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._is_running

    def get_method(self) -> str:
        """Get the monitoring method being used."""
        return "watchdog" if self.enable_watchdog else "polling"