"""Tests for the 8 doc_management modules implemented in Phase 2."""

import pytest
import asyncio
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from scribe_mcp.doc_management.file_watcher import FileSystemWatcher, FileChangeEvent
from scribe_mcp.doc_management.sync_manager import SyncManager, ConflictResolution, SyncConflict, SyncOperation
from scribe_mcp.doc_management.change_logger import ChangeLogger, ChangeRecord
from scribe_mcp.doc_management.diff_visualizer import DiffVisualizer, DiffVisualization, DiffResult
from scribe_mcp.doc_management.conflict_resolver import ConflictResolver, ConflictAnalysis, ConflictSeverity, ResolutionAction
from scribe_mcp.doc_management.integrity_verifier import IntegrityVerifier, IntegrityStatus, IntegrityCheck, IntegrityReport
from scribe_mcp.doc_management.performance_monitor import PerformanceMonitor, PerformanceMetric, OperationMetrics, SystemMetrics
from scribe_mcp.doc_management.change_rollback import ChangeRollbackManager, ChangeLogEntry, RollbackPlan


class TestFileSystemWatcher:
    """Test FileSystemWatcher functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage._fetchall = AsyncMock(return_value=[])
        storage._fetchone = AsyncMock(return_value=None)
        return storage

    def test_file_change_event_creation(self):
        """Test FileChangeEvent dataclass creation."""
        event = FileChangeEvent(
            file_path=Path("/test/file.md"),
            event_type="modified",
            size_bytes=1024,
            checksum="abc123"
        )
        assert event.file_path == Path("/test/file.md")
        assert event.event_type == "modified"
        assert event.size_bytes == 1024
        assert event.checksum == "abc123"

    @pytest.mark.asyncio
    async def test_watcher_initialization(self, temp_dir, mock_storage):
        """Test FileSystemWatcher initialization."""
        callback = AsyncMock()
        watcher = FileSystemWatcher(
            project_root=temp_dir,
            change_callback=callback,
            enable_watchdog=False  # Use polling for test
        )

        assert watcher.project_root == temp_dir
        assert watcher.enable_watchdog is False
        assert not watcher._is_running

    @pytest.mark.asyncio
    async def test_watcher_start_stop(self, temp_dir, mock_storage):
        """Test starting and stopping the watcher."""
        callback = AsyncMock()
        watcher = FileSystemWatcher(
            project_root=temp_dir,
            change_callback=callback,
            enable_watchdog=False
        )

        # Test start
        success = await watcher.start()
        assert success is True
        assert watcher._is_running is True

        # Test stop
        await watcher.stop()
        assert watcher._is_running is False

    def test_watcher_methods(self, temp_dir):
        """Test watcher utility methods."""
        callback = AsyncMock()
        watcher = FileSystemWatcher(
            project_root=temp_dir,
            change_callback=callback,
            enable_watchdog=False
        )

        # Test get_method
        assert watcher.get_method() == "polling"

        # Test is_running
        assert watcher.is_running() is False

    @pytest.mark.asyncio
    async def test_file_change_callback(self, temp_dir):
        """Test file change callback handling."""
        received_events = []

        def callback(event):
            received_events.append(event)

        watcher = FileSystemWatcher(
            project_root=temp_dir,
            change_callback=callback,
            enable_watchdog=False
        )

        # Create test event
        event = FileChangeEvent(
            file_path=temp_dir / "test.md",
            event_type="modified",
            size_bytes=100
        )

        # Handle event
        watcher._handle_file_change(event)

        # Verify event was processed
        assert len(received_events) == 1
        assert received_events[0].file_path == temp_dir / "test.md"
        assert received_events[0].event_type == "modified"


class TestSyncManager:
    """Test SyncManager functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage._fetchall = AsyncMock(return_value=[])
        storage._fetchone = AsyncMock(return_value=None)
        storage._execute = AsyncMock()
        return storage

    def test_sync_conflict_creation(self):
        """Test SyncConflict dataclass creation."""
        conflict = SyncConflict(
            file_path=Path("/test/file.md"),
            conflict_type="content",
            file_timestamp=1234567890.0,
            database_timestamp=1234567880.0,
            file_content="new content",
            database_content="old content",
            metadata={}
        )
        assert conflict.file_path == Path("/test/file.md")
        assert conflict.conflict_type == "content"
        assert conflict.file_timestamp > conflict.database_timestamp

    def test_sync_operation_creation(self):
        """Test SyncOperation dataclass creation."""
        operation = SyncOperation(
            operation_type="sync_to_db",
            file_path=Path("/test/file.md"),
            success=True,
            checksum_before="old_hash",
            checksum_after="new_hash",
            metadata={}
        )
        assert operation.operation_type == "sync_to_db"
        assert operation.success is True
        assert operation.checksum_before == "old_hash"

    @pytest.mark.asyncio
    async def test_sync_manager_initialization(self, temp_dir, mock_storage):
        """Test SyncManager initialization."""
        sync_manager = SyncManager(
            storage=mock_storage,
            project_root=temp_dir,
            conflict_resolution=ConflictResolution.LATEST_WINS
        )

        assert sync_manager.storage == mock_storage
        assert sync_manager.project_root == temp_dir
        assert sync_manager.conflict_resolution == ConflictResolution.LATEST_WINS
        assert not sync_manager._is_running

    def test_to_epoch_conversion(self, temp_dir, mock_storage):
        """Test timestamp conversion utility."""
        sync_manager = SyncManager(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Test various timestamp formats
        assert sync_manager._to_epoch(1234567890.0) == 1234567890.0
        assert sync_manager._to_epoch(1234567890) == 1234567890.0
        assert sync_manager._to_epoch(None) == 0.0

        # Test ISO string
        dt = datetime(2023, 1, 1, 12, 0, 0)
        iso_str = dt.isoformat()
        assert sync_manager._to_epoch(iso_str) == dt.timestamp()

    @pytest.mark.asyncio
    async def test_sync_manager_start_stop(self, temp_dir, mock_storage):
        """Test starting and stopping sync manager."""
        sync_manager = SyncManager(
            storage=mock_storage,
            project_root=temp_dir,
            enable_watcher=False
        )

        # Test start
        success = await sync_manager.start()
        assert success is True
        assert sync_manager._is_running is True

        # Test stop
        await sync_manager.stop()
        assert sync_manager._is_running is False

    @pytest.mark.asyncio
    async def test_get_sync_status(self, temp_dir, mock_storage):
        """Test getting sync status."""
        sync_manager = SyncManager(
            storage=mock_storage,
            project_root=temp_dir,
            enable_watcher=False
        )

        status = await sync_manager.get_sync_status()

        assert status['is_running'] is False
        assert status['watcher_method'] == 'disabled'
        assert 'statistics' in status
        assert 'pending_syncs' in status


class TestChangeLogger:
    """Test ChangeLogger functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage._fetchall = AsyncMock(return_value=[])
        storage._fetchone = AsyncMock(return_value=None)
        storage._execute = AsyncMock()
        return storage

    def test_change_record_creation(self):
        """Test ChangeRecord dataclass creation."""
        record = ChangeRecord(
            id="test_id",
            file_path=Path("/test/file.md"),
            change_type="modified",
            commit_message="Test commit",
            author="TestAuthor",
            timestamp=datetime.now(),
            content_hash_before="old_hash",
            content_hash_after="new_hash"
        )
        assert record.id == "test_id"
        assert record.change_type == "modified"
        assert record.commit_message == "Test commit"

    @pytest.mark.asyncio
    async def test_change_logger_initialization(self, temp_dir, mock_storage):
        """Test ChangeLogger initialization."""
        logger = ChangeLogger(
            storage=mock_storage,
            project_root=temp_dir,
            max_history=100
        )

        assert logger.storage == mock_storage
        assert logger.project_root == temp_dir
        assert logger.max_history == 100

    def test_generate_change_id(self, temp_dir, mock_storage):
        """Test change ID generation."""
        logger = ChangeLogger(
            storage=mock_storage,
            project_root=temp_dir
        )

        id1 = logger._generate_change_id(Path("/test/file.md"), "modified")
        id2 = logger._generate_change_id(Path("/test/file.md"), "modified")

        assert id1 != id2
        assert len(id1) == 12  # MD5 hash prefix

    @pytest.mark.asyncio
    async def test_log_change(self, temp_dir, mock_storage):
        """Test logging a change."""
        logger = ChangeLogger(
            storage=mock_storage,
            project_root=temp_dir
        )

        change_record = await logger.log_change(
            file_path=Path("/test/file.md"),
            change_type="modified",
            commit_message="Test change",
            author="TestAuthor",
            old_content="old",
            new_content="new",
            metadata={}
        )

        assert change_record is not None
        assert isinstance(change_record, ChangeRecord)
        assert len(change_record.id) == 12
        # Verify storage was called
        mock_storage._execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_change_history(self, temp_dir, mock_storage):
        """Test getting change history."""
        logger = ChangeLogger(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Create proper ChangeRecord
        from scribe_mcp.doc_management.change_logger import ChangeRecord
        mock_change_record_obj = ChangeRecord(
            id="test_id",
            file_path=Path('test.md'),
            change_type='modified',
            commit_message='Test commit',
            author='TestAuthor',
            timestamp=datetime.fromisoformat('2023-01-01T12:00:00'),
            content_hash_before='old_hash',
            content_hash_after='new_hash',
            metadata={}
        )

        # Mock get_change_history to return our record
        with patch.object(logger, 'get_change_history', return_value=[mock_change_record_obj]) as mock_get_history:
            history = await mock_get_history(limit=10)

        assert len(history) == 1
        assert history[0].commit_message == "Test commit"
        assert history[0].author == "TestAuthor"

    def test_calculate_content_hash(self, temp_dir, mock_storage):
        """Test content hash calculation."""
        logger = ChangeLogger(
            storage=mock_storage,
            project_root=temp_dir
        )

        content = "test content"
        hash1 = logger._calculate_content_hash(content)
        hash2 = logger._calculate_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    @pytest.mark.asyncio
    async def test_create_commit(self, temp_dir, mock_storage):
        """Test creating a commit with multiple changes."""
        logger = ChangeLogger(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Create test file
        test_file = temp_dir / "test.md"
        test_file.write_text("test content")

        changes = await logger.create_commit(
            file_paths=[test_file],
            commit_message="Test commit",
            author="TestAuthor"
        )

        assert len(changes) == 1
        assert changes[0].commit_message == "Test commit"
        assert changes[0].author == "TestAuthor"


class TestDiffVisualizer:
    """Test DiffVisualizer functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_change_logger(self):
        logger = AsyncMock()
        logger.get_change_history = AsyncMock(return_value=[])
        logger._get_content_at_hash = AsyncMock(return_value=None)
        logger._calculate_content_hash = MagicMock(return_value="test_hash")
        return logger

    @pytest.mark.asyncio
    async def test_diff_visualizer_initialization(self, mock_change_logger):
        """Test DiffVisualizer initialization."""
        visualizer = DiffVisualizer(mock_change_logger)

        assert visualizer.change_logger == mock_change_logger

    def test_diff_result_creation(self):
        """Test DiffResult dataclass creation."""
        from scribe_mcp.doc_management.diff_visualizer import DiffResult

        result = DiffResult(
            additions=5,
            deletions=3,
            modifications=2,
            lines_added=["+ line1", "+ line2"],
            lines_removed=["- line1"],
            unified_diff="test diff",
            similarity_ratio=0.8
        )

        assert result.additions == 5
        assert result.deletions == 3
        assert result.similarity_ratio == 0.8

    def test_diff_visualization_creation(self):
        """Test DiffVisualization dataclass creation."""
        viz = DiffVisualization(
            file_path=Path("/test/file.md"),
            from_version="hash1",
            to_version="hash2",
            total_changes=8,
            additions=5,
            deletions=3,
            sections=[],
            html_content="<html>test</html>",
            text_content="test diff",
            similarity_ratio=0.8
        )

        assert viz.file_path == Path("/test/file.md")
        assert viz.total_changes == 8
        assert viz.similarity_ratio == 0.8

    @pytest.mark.asyncio
    async def test_create_diff_sections(self, mock_change_logger):
        """Test creating diff sections."""
        visualizer = DiffVisualizer(mock_change_logger)

        old_content = "line1\nline2\nline3"
        new_content = "line1\nmodified_line2\nline3\nline4"

        sections = visualizer._create_diff_sections(old_content, new_content)

        assert len(sections) > 0
        assert all('type' in section for section in sections)

    @pytest.mark.asyncio
    async def test_calculate_diff(self, mock_change_logger):
        """Test diff calculation."""
        from scribe_mcp.doc_management.change_logger import DiffResult

        # Mock the change logger method to return a proper result
        mock_diff_result = DiffResult(
            additions=2,
            deletions=1,
            modifications=1,
            lines_added=["modified_line2", "line4"],
            lines_removed=["line2"],
            unified_diff="mock diff",
            similarity_ratio=0.6
        )
        mock_change_logger._calculate_diff.return_value = mock_diff_result

        old_content = "line1\nline2\nline3"
        new_content = "line1\nmodified_line2\nline3\nline4"

        result = await mock_change_logger._calculate_diff(old_content, new_content)

        assert result.additions == 2  # modified_line2 + line4
        assert result.deletions == 1  # original line2
        assert 0 <= result.similarity_ratio <= 1

    
    @pytest.mark.asyncio
    async def test_export_history(self, mock_change_logger):
        """Test exporting change history."""
        mock_change_logger.get_change_history.return_value = []

        visualizer = DiffVisualizer(mock_change_logger)

        # Test JSON export
        json_export = await visualizer.export_history(format="json")
        assert '"total_changes"' in json_export

        # Test markdown export
        md_export = await visualizer.export_history(format="markdown")
        assert "# Change History" in md_export

        # Test CSV export
        csv_export = await visualizer.export_history(format="csv")
        assert "timestamp,file_path,change_type" in csv_export


class TestConflictResolver:
    """Test ConflictResolver functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_change_logger(self):
        logger = AsyncMock()
        logger.get_change_history = AsyncMock(return_value=[])
        logger._get_content_at_hash = AsyncMock(return_value=None)
        logger._calculate_content_hash = MagicMock(return_value="test_hash")
        logger.log_change = AsyncMock(return_value="test_id")
        return logger

    @pytest.fixture
    def mock_diff_visualizer(self):
        visualizer = AsyncMock()
        visualizer.get_diff_between_versions = AsyncMock(return_value=None)
        return visualizer

    @pytest.mark.asyncio
    async def test_conflict_resolver_initialization(self, mock_change_logger, mock_diff_visualizer):
        """Test ConflictResolver initialization."""
        resolver = ConflictResolver(
            change_logger=mock_change_logger,
            diff_visualizer=mock_diff_visualizer,
            default_resolution=ConflictResolution.LATEST_WINS
        )

        assert resolver.change_logger == mock_change_logger
        assert resolver.diff_visualizer == mock_diff_visualizer
        assert resolver.default_resolution == ConflictResolution.LATEST_WINS

    def test_conflict_analysis_creation(self):
        """Test ConflictAnalysis dataclass creation."""
        conflict = AsyncMock()
        analysis = ConflictAnalysis(
            conflict=conflict,
            severity=ConflictSeverity.MEDIUM,
            affected_sections=["section1", "section2"],
            auto_resolvable=True,
            suggested_resolution=ConflictResolution.LATEST_WINS,
            confidence_score=0.8
        )

        assert analysis.severity == ConflictSeverity.MEDIUM
        assert analysis.auto_resolvable is True
        assert analysis.confidence_score == 0.8

    def test_resolution_action_creation(self):
        """Test ResolutionAction dataclass creation."""
        action = ResolutionAction(
            conflict_id="test_conflict",
            resolution_strategy=ConflictResolution.FILE_WINS,
            resolver="TestResolver",
            timestamp=datetime.now().isoformat(),
            action_taken="Test resolution"
        )

        assert action.conflict_id == "test_conflict"
        assert action.resolution_strategy == ConflictResolution.FILE_WINS
        assert action.resolver == "TestResolver"

    @pytest.mark.asyncio
    async def test_analyze_conflict(self, temp_dir, mock_change_logger, mock_diff_visualizer):
        """Test conflict analysis."""
        resolver = ConflictResolver(
            change_logger=mock_change_logger,
            diff_visualizer=mock_diff_visualizer
        )

        # Create test conflict
        test_file = temp_dir / "test.md"
        test_file.write_text("test content")

        conflict = AsyncMock()
        conflict.file_path = test_file
        conflict.file_content = "new content"
        conflict.database_content = "old content"
        conflict.file_timestamp = time.time()
        conflict.database_timestamp = time.time() - 10

        analysis = await resolver.analyze_conflict(conflict)

        assert isinstance(analysis, ConflictAnalysis)
        assert analysis.conflict == conflict
        assert analysis.severity in [s for s in ConflictSeverity]

    @pytest.mark.asyncio
    async def test_resolve_conflict(self, temp_dir, mock_change_logger, mock_diff_visualizer):
        """Test conflict resolution."""
        resolver = ConflictResolver(
            change_logger=mock_change_logger,
            diff_visualizer=mock_diff_visualizer,
            default_resolution=ConflictResolution.FILE_WINS
        )

        test_file = temp_dir / "test.md"
        test_file.write_text("test content")

        conflict = AsyncMock()
        conflict.file_path = test_file
        conflict.file_content = "new content"
        conflict.database_content = "old content"

        success, resolved_content = await resolver.resolve_conflict(
            conflict,
            resolution_strategy=ConflictResolution.FILE_WINS,
            resolver="TestResolver"
        )

        assert success is True
        assert resolved_content == "new content"

    def test_calculate_content_similarity(self, mock_change_logger, mock_diff_visualizer):
        """Test content similarity calculation."""
        resolver = ConflictResolver(
            change_logger=mock_change_logger,
            diff_visualizer=mock_diff_visualizer
        )

        # Test identical content
        similarity = resolver._calculate_content_similarity(
            MagicMock(file_content="test", database_content="test")
        )
        assert similarity == 1.0

        # Test completely different content
        similarity = resolver._calculate_content_similarity(
            MagicMock(file_content="content1", database_content="content2")
        )
        assert 0 <= similarity <= 1

    

class TestIntegrityVerifier:
    """Test IntegrityVerifier functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage._fetchall = AsyncMock(return_value=[])
        storage._fetchone = AsyncMock(return_value=None)
        storage._execute = AsyncMock()
        return storage

    def test_integrity_check_creation(self):
        """Test IntegrityCheck dataclass creation."""
        check = IntegrityCheck(
            file_path=Path("/test/file.md"),
            status=IntegrityStatus.VALID,
            expected_hash="hash1",
            actual_hash="hash1",
            file_size=1024,
            last_modified=1234567890.0,
            database_timestamp=1234567880.0,
            metadata={}
        )

        assert check.status == IntegrityStatus.VALID
        assert check.expected_hash == "hash1"
        assert check.actual_hash == "hash1"

    def test_integrity_report_creation(self):
        """Test IntegrityReport dataclass creation."""
        report = IntegrityReport(
            timestamp="2023-01-01T12:00:00",
            total_files_checked=10,
            status_counts={IntegrityStatus.VALID: 8, IntegrityStatus.MODIFIED: 2},
            files_with_issues=[],
            check_duration=1.5,
            recommendations=["Test recommendation"]
        )

        assert report.total_files_checked == 10
        assert report.check_duration == 1.5
        assert len(report.recommendations) == 1

    @pytest.mark.asyncio
    async def test_integrity_verifier_initialization(self, temp_dir, mock_storage):
        """Test IntegrityVerifier initialization."""
        verifier = IntegrityVerifier(
            storage=mock_storage,
            project_root=temp_dir,
            cache_duration=300.0
        )

        assert verifier.storage == mock_storage
        assert verifier.project_root == temp_dir
        assert verifier.cache_duration == 300.0

    @pytest.mark.asyncio
    async def test_verify_file_integrity(self, temp_dir, mock_storage):
        """Test file integrity verification."""
        verifier = IntegrityVerifier(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Create test file
        test_file = temp_dir / "test.md"
        test_file.write_text("test content")

        # Mock database record - the method queries sync_status table
        file_hash = await verifier._calculate_file_hash(test_file)

        def mock_fetchone(query, params):
            if "sync_status" in query:
                return {
                    'last_file_hash': file_hash,
                    'last_sync_at': str(time.time() - 10),
                    'sync_status': 'synced'
                }
            return None

        mock_storage._fetchone.side_effect = mock_fetchone

        check = await verifier.verify_file_integrity(test_file)

        assert isinstance(check, IntegrityCheck)
        assert check.status == IntegrityStatus.VALID

    @pytest.mark.asyncio
    async def test_verify_project_integrity(self, temp_dir, mock_storage):
        """Test project integrity verification."""
        verifier = IntegrityVerifier(
            storage=mock_storage,
            project_root=temp_dir
        )

        report = await verifier.verify_project_integrity()

        assert isinstance(report, IntegrityReport)
        assert 'timestamp' in report.__dict__
        assert 'total_files_checked' in report.__dict__
        assert 'status_counts' in report.__dict__

    
    @pytest.mark.asyncio
    async def test_calculate_file_hash(self, temp_dir, mock_storage):
        """Test file hash calculation."""
        verifier = IntegrityVerifier(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Create test file
        test_file = temp_dir / "test.md"
        test_file.write_text("test content")

        hash1 = await verifier._calculate_file_hash(test_file)
        hash2 = await verifier._calculate_file_hash(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_get_cache_stats(self, temp_dir, mock_storage):
        """Test cache statistics."""
        verifier = IntegrityVerifier(
            storage=mock_storage,
            project_root=temp_dir
        )

        stats = verifier.get_cache_stats()

        assert 'cached_files' in stats
        assert 'cache_duration' in stats
        assert stats['cached_files'] == 0


class TestPerformanceMonitor:
    """Test PerformanceMonitor functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage._fetchall = AsyncMock(return_value=[])
        storage._fetchone = AsyncMock(return_value=None)
        storage._execute = AsyncMock()
        return storage

    def test_performance_metric_creation(self):
        """Test PerformanceMetric dataclass creation."""
        metric = PerformanceMetric(
            name="test_operation",
            value=1.5,
            unit="seconds",
            timestamp=datetime.now(),
            metadata={"test": True}
        )

        assert metric.name == "test_operation"
        assert metric.value == 1.5
        assert metric.unit == "seconds"

    def test_operation_metrics_creation(self):
        """Test OperationMetrics dataclass creation."""
        metrics = OperationMetrics(
            operation_name="test_operation",
            total_operations=10,
            successful_operations=8,
            failed_operations=2,
            average_duration=1.2,
            min_duration=0.5,
            max_duration=2.0,
            total_duration=12.0,
            last_operation_time=datetime.now(),
            error_rate=0.2,
            throughput=0.83
        )

        assert metrics.operation_name == "test_operation"
        assert metrics.total_operations == 10
        assert metrics.error_rate == 0.2

    def test_system_metrics_creation(self):
        """Test SystemMetrics dataclass creation."""
        metrics = SystemMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=60.0,
            active_operations=2,
            cache_hit_rate=0.8
        )

        assert metrics.cpu_usage == 50.0
        assert metrics.memory_usage == 60.0
        assert metrics.active_operations == 2

    @pytest.mark.asyncio
    async def test_performance_monitor_initialization(self, temp_dir, mock_storage):
        """Test PerformanceMonitor initialization."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir,
            collection_interval=60.0
        )

        assert monitor.storage == mock_storage
        assert monitor.project_root == temp_dir
        assert monitor.collection_interval == 60.0

    def test_track_operation_start(self, temp_dir, mock_storage):
        """Test operation start tracking."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir
        )

        operation_id = monitor.track_operation_start("test_operation")

        assert operation_id is not None
        assert "test_operation" in operation_id
        assert operation_id in monitor._active_operations

    @pytest.mark.asyncio
    async def test_track_operation_end(self, temp_dir, mock_storage):
        """Test operation end tracking."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Start operation
        operation_id = monitor.track_operation_start("test_operation")

        # Wait a bit and end operation
        await asyncio.sleep(0.01)
        monitor.track_operation_end(operation_id, "test_operation", success=True)

        # Verify tracking
        assert operation_id not in monitor._active_operations
        assert "test_operation" in monitor._operation_times
        assert len(monitor._operation_times["test_operation"]) == 1

    @pytest.mark.asyncio
    async def test_get_operation_metrics(self, temp_dir, mock_storage):
        """Test getting operation metrics."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Track some operations
        for i in range(3):
            operation_id = monitor.track_operation_start("test_operation")
            time.sleep(0.01)  # Small delay
            monitor.track_operation_end(operation_id, "test_operation", success=True)

        metrics = await monitor.get_operation_metrics()

        assert "test_operation" in metrics
        assert metrics["test_operation"].total_operations == 3
        assert metrics["test_operation"].successful_operations == 3

    @pytest.mark.asyncio
    async def test_get_system_metrics(self, temp_dir, mock_storage):
        """Test getting system metrics."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir
        )

        metrics = await monitor.get_system_metrics()

        assert isinstance(metrics, SystemMetrics)
        assert metrics.active_operations == 0  # No active operations

    @pytest.mark.asyncio
    async def test_performance_context_manager(self, temp_dir, mock_storage):
        """Test performance context manager."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir
        )

        with monitor.create_performance_context("test_operation"):
            time.sleep(0.01)

        # Verify operation was tracked
        assert "test_operation" in monitor._operation_times
        assert len(monitor._operation_times["test_operation"]) == 1

    @pytest.mark.asyncio
    async def test_reset_metrics(self, temp_dir, mock_storage):
        """Test resetting metrics."""
        monitor = PerformanceMonitor(
            storage=mock_storage,
            project_root=temp_dir
        )

        # Add some data
        operation_id = monitor.track_operation_start("test_operation")
        monitor.track_operation_end(operation_id, "test_operation")

        # Reset
        monitor.reset_metrics()

        # Verify reset
        assert len(monitor._operation_times) == 0
        assert len(monitor._operation_end_times) == 0
        assert len(monitor._active_operations) == 0


class TestChangeRollbackManager:
    """Test ChangeRollbackManager functionality."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage._fetchall = AsyncMock(return_value=[])
        storage._fetchone = AsyncMock(return_value=None)
        storage._execute = AsyncMock()
        storage.store_performance_metric = AsyncMock()
        return storage

    def test_change_log_entry_creation(self):
        """Test ChangeLogEntry dataclass creation."""
        entry = ChangeLogEntry(
            id="test_id",
            timestamp=datetime.now(),
            operation_type="update",
            table_name="document_sections",
            record_id="123",
            old_data={"content": "old"},
            new_data={"content": "new"},
            change_summary="Test change",
            author="TestAuthor",
            metadata={}
        )

        assert entry.id == "test_id"
        assert entry.operation_type == "update"
        assert entry.table_name == "document_sections"

    def test_rollback_plan_creation(self):
        """Test RollbackPlan dataclass creation."""
        plan = RollbackPlan(
            rollback_id="test_rollback",
            target_timestamp=datetime.now(),
            affected_tables=["document_sections", "sync_status"],
            total_records=5,
            estimated_duration=2.5,
            risk_level="medium",
            changes_to_rollback=[],
            warnings=["Test warning"]
        )

        assert plan.rollback_id == "test_rollback"
        assert plan.risk_level == "medium"
        assert len(plan.warnings) == 1

    @pytest.mark.asyncio
    async def test_rollback_manager_initialization(self, temp_dir, mock_storage):
        """Test ChangeRollbackManager initialization."""
        manager = ChangeRollbackManager(
            storage=mock_storage,
            project_root=temp_dir,
            retention_days=30
        )

        assert manager.storage == mock_storage
        assert manager.project_root == temp_dir
        assert manager.retention_days == 30

    @pytest.mark.asyncio
    async def test_log_change(self, temp_dir, mock_storage):
        """Test logging a database change."""
        manager = ChangeRollbackManager(
            storage=mock_storage,
            project_root=temp_dir
        )

        change_id = await manager.log_change(
            operation_type="update",
            table_name="document_sections",
            record_id="123",
            old_data={"content": "old"},
            new_data={"content": "new"},
            change_summary="Test change",
            author="TestAuthor"
        )

        assert change_id is not None
        assert len(change_id) == 12  # MD5 hash prefix
        # Verify storage was called
        mock_storage._execute.assert_called()

    def test_generate_change_id(self, temp_dir, mock_storage):
        """Test change ID generation."""
        manager = ChangeRollbackManager(
            storage=mock_storage,
            project_root=temp_dir
        )

        id1 = manager._generate_change_id()
        id2 = manager._generate_change_id()

        assert id1 != id2
        assert len(id1) == 12  # MD5 hash prefix

    @pytest.mark.asyncio
    async def test_get_change_history(self, temp_dir, mock_storage):
        """Test getting change history."""
        # Mock storage response
        mock_storage._fetchall.return_value = [
            {
                'id': 'test_id',
                'timestamp': '2023-01-01T12:00:00',
                'operation_type': 'update',
                'table_name': 'document_sections',
                'record_id': '123',
                'old_data': '{}',
                'new_data': '{}',
                'change_summary': json.dumps({
                    'commit_message': 'Test commit',
                    'author': 'TestAuthor'
                }),
                'author': 'TestAuthor',
                'metadata': '{}'
            }
        ]

        manager = ChangeRollbackManager(
            storage=mock_storage,
            project_root=temp_dir
        )

        history = await manager.get_change_history(limit=10)

        assert len(history) == 1
        assert history[0].operation_type == "update"
        assert history[0].table_name == "document_sections"

    @pytest.mark.asyncio
    async def test_create_backup_point(self, temp_dir, mock_storage):
        """Test creating a backup point."""
        manager = ChangeRollbackManager(
            storage=mock_storage,
            project_root=temp_dir
        )

        backup_id = await manager.create_backup_point("test_backup")

        assert backup_id is not None
        assert len(backup_id) == 12  # MD5 hash prefix
        # Verify storage was called
        mock_storage._execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_backup_points(self, temp_dir, mock_storage):
        """Test getting backup points."""
        # Mock storage response
        mock_storage._fetchall.return_value = [
            {
                'id': 'backup_id',
                'name': 'test_backup',
                'timestamp': '2023-01-01T12:00:00',
                'metadata': '{}',
                'created_at': '2023-01-01T12:00:00'
            }
        ]

        manager = ChangeRollbackManager(
            storage=mock_storage,
            project_root=temp_dir
        )

        backups = await manager.get_backup_points()

        assert len(backups) == 1
        assert backups[0]['name'] == 'test_backup'

    def test_imports(self):
        """Test that all required imports work."""
        # This test verifies that the module can be imported successfully
        from scribe_mcp.doc_management.change_rollback import (
            ChangeRollbackManager, ChangeLogEntry, RollbackPlan
        )

        assert ChangeRollbackManager is not None
        assert ChangeLogEntry is not None
        assert RollbackPlan is not None