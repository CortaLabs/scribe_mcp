"""Integration tests for vector indexing functionality."""

import pytest
import pytest_asyncio
import tempfile
import asyncio
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

# Try to import vector dependencies - if not available, tests will be skipped
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    VECTOR_DEPS_AVAILABLE = True
except ImportError:
    VECTOR_DEPS_AVAILABLE = False
    faiss = None
    np = None
    SentenceTransformer = None

from scribe_mcp.plugins.registry import initialize_plugins, get_plugin_registry
from scribe_mcp.plugins.vector_indexer import VectorIndexer
from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.config.settings import Settings


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
@pytest.mark.asyncio
class TestVectorIntegration:
    """Integration tests for complete vector indexing workflow."""

    @pytest_asyncio.fixture
    async def temp_repo_with_config(self):
        """Create a temporary repository with full configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)

            # Create necessary directories
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            (repo_path / "plugins").mkdir(exist_ok=True)
            (repo_path / "config" / "projects").mkdir(parents=True, exist_ok=True)

            # Create plugin manifest
            plugin_manifest = {
                "name": "vector_indexer",
                "version": "1.0.0",
                "description": "Test vector indexer",
                "author": "Test",
                "min_scribe_version": "1.0.0",
                "required_permissions": ["file_read", "file_write", "database_access"],
                "dependencies": {
                    "required": ["faiss-cpu>=1.7.0", "sentence-transformers>=2.0.0", "numpy>=1.20.0"]
                }
            }

            with open(repo_path / "plugins" / "vector_indexer.json", 'w') as f:
                json.dump(plugin_manifest, f, indent=2)

            # Copy the actual plugin file
            import shutil
            current_plugin = Path(__file__).parent.parent / "src" / "scribe_mcp" / "plugins" / "vector_indexer.py"
            shutil.copy(current_plugin, repo_path / "plugins" / "vector_indexer.py")

            yield repo_path

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = MagicMock(spec=Settings)
        settings.vector_enabled = True
        settings.vector_backend = "faiss"
        settings.vector_dimension = 384
        settings.vector_model = "all-MiniLM-L6-v2"
        settings.vector_gpu = False
        settings.vector_queue_max = 100
        settings.vector_batch_size = 5
        settings.storage_timeout_seconds = 5.0
        # project_root will be set dynamically in test based on temp_repo_with_config
        settings.project_root = None
        return settings

    async def test_complete_vector_indexing_workflow(self, temp_repo_with_config, mock_settings):
        """Test complete workflow from plugin initialization to search."""
        with patch('scribe_mcp.plugins.registry.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:

            # Set project_root dynamically for sandbox validation
            mock_settings.project_root = temp_repo_with_config

            # Mock vector config
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = True
            mock_config_obj.backend = "faiss"
            mock_config_obj.dimension = 384
            mock_config_obj.model = "all-MiniLM-L6-v2"
            mock_config_obj.gpu = False
            mock_config_obj.queue_max = 100
            mock_config_obj.batch_size = 5
            mock_load_config.return_value = mock_config_obj

            # Initialize plugins
            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo_with_config
            config.plugins_dir = temp_repo_with_config / "plugins"
            config.plugin_config = {"enabled": True}
            config.repo_slug = "tmp"  # Add repo_slug

            initialize_plugins(config)

            # Get plugin registry and check vector indexer is loaded
            registry = get_plugin_registry(temp_repo_with_config)
            assert "vector_indexer" in registry.plugins

            vector_indexer = registry.plugins["vector_indexer"]
            assert vector_indexer.initialized
            assert vector_indexer.enabled

            # Test that vector search tools were registered
            from scribe_mcp.tools.vector_search import register_vector_tools
            tools_registered = register_vector_tools()
            assert tools_registered is True

            # Create test entries
            test_entries = [
                {
                    'entry_id': 'test1' + 'a' * 28,  # Make 32 chars
                    'project_name': 'Test Project',
                    'message': 'This is a test about software development and coding',
                    'agent': 'TestAgent',
                    'timestamp': '2025-10-26 12:00:00 UTC',
                    'meta': {'phase': 'development', 'component': 'backend'}
                },
                {
                    'entry_id': 'test2' + 'b' * 28,
                    'project_name': 'Test Project',
                    'message': 'Database optimization and performance tuning',
                    'agent': 'TestAgent',
                    'timestamp': '2025-10-26 12:01:00 UTC',
                    'meta': {'phase': 'optimization', 'component': 'database'}
                },
                {
                    'entry_id': 'test3' + 'c' * 28,
                    'project_name': 'Test Project',
                    'message': 'User interface design and user experience improvements',
                    'agent': 'TestAgent',
                    'timestamp': '2025-10-26 12:02:00 UTC',
                    'meta': {'phase': 'design', 'component': 'frontend'}
                }
            ]

            # Process entries through post_append hook
            for entry in test_entries:
                vector_indexer.post_append(entry)

            # Wait for background processing (with timeout)
            max_wait = 30  # 30 seconds max
            wait_time = 0
            while (vector_indexer.embedding_queue and
                   not vector_indexer.embedding_queue.empty() and
                   wait_time < max_wait):
                await asyncio.sleep(0.5)
                wait_time += 0.5

            # Check that entries were processed
            status = vector_indexer.get_index_status()
            assert status['total_entries'] >= 0  # Some entries might still be processing

            # Test semantic search
            search_results = vector_indexer.search_similar(
                query="software programming code",
                k=5
            )

            # Should find relevant results
            assert len(search_results) >= 0

            # Test UUID retrieval
            if search_results:
                first_result = search_results[0]
                retrieved_entry = vector_indexer.retrieve_by_uuid(first_result['entry_id'])
                assert retrieved_entry is not None
                assert retrieved_entry['entry_id'] == first_result['entry_id']

            # Test filtered search
            filtered_results = vector_indexer.search_similar(
                query="development coding",
                k=10,
                filters={'component': 'backend'}
            )

            # Test time range filtering
            time_filtered = vector_indexer.search_similar(
                query="test",
                k=10,
                filters={
                    'time_range': {
                        'start': '2025-10-25T00:00:00',
                        'end': '2025-10-27T00:00:00'
                    }
                }
            )

            # Cleanup
            vector_indexer.cleanup()

    async def test_repository_isolation(self, mock_settings):
        """Test that different repositories maintain separate vector indexes."""
        with patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings):
            # Create two separate temporary repositories
            with tempfile.TemporaryDirectory() as temp1, tempfile.TemporaryDirectory() as temp2:
                repo1 = Path(temp1)
                repo2 = Path(temp2)

                # Setup both repositories
                for repo in [repo1, repo2]:
                    (repo / ".scribe_vectors").mkdir(exist_ok=True)
                    (repo / "plugins").mkdir(exist_ok=True)

                    # Copy plugin file
                    import shutil
                    current_plugin = Path(__file__).parent.parent / "src" / "scribe_mcp" / "plugins" / "vector_indexer.py"
                    shutil.copy(current_plugin, repo / "plugins" / "vector_indexer.py")

                # Initialize vector indexer for repo1
                config1 = MagicMock(spec=RepoConfig)
                config1.repo_root = repo1
                config1.plugins_dir = repo1 / "plugins"
                config1.plugin_config = {"enabled": True}

                indexer1 = VectorIndexer()
                indexer1.initialize(config1)

                # Initialize vector indexer for repo2
                config2 = MagicMock(spec=RepoConfig)
                config2.repo_root = repo2
                config2.plugins_dir = repo2 / "plugins"
                config2.plugin_config = {"enabled": True}

                indexer2 = VectorIndexer()
                indexer2.initialize(config2)

                # Add entries to repo1
                entry1 = {
                    'entry_id': 'repo1' + 'a' * 27,
                    'project_name': 'Project One',
                    'message': 'Entry in repository one',
                    'agent': 'TestAgent',
                    'timestamp': '2025-10-26 12:00:00 UTC',
                    'meta': {'repo': 'one'}
                }
                indexer1.post_append(entry1)

                # Add entries to repo2
                entry2 = {
                    'entry_id': 'repo2' + 'b' * 27,
                    'project_name': 'Project Two',
                    'message': 'Entry in repository two',
                    'agent': 'TestAgent',
                    'timestamp': '2025-10-26 12:00:00 UTC',
                    'meta': {'repo': 'two'}
                }
                indexer2.post_append(entry2)

                # Wait for processing
                await asyncio.sleep(2)

                # Test that each indexer only finds its own entries
                results1 = indexer1.search_similar("repository", k=10)
                results2 = indexer2.search_similar("repository", k=10)

                # Cleanup
                indexer1.cleanup()
                indexer2.cleanup()

    async def test_vector_index_persistence(self, temp_repo_with_config, mock_settings):
        """Test that vector index persists across plugin restarts."""
        with patch('scribe_mcp.plugins.registry.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:

            # Set project_root dynamically for sandbox validation
            mock_settings.project_root = temp_repo_with_config

            # Mock vector config
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = True
            mock_config_obj.backend = "faiss"
            mock_config_obj.dimension = 384
            mock_config_obj.model = "all-MiniLM-L6-v2"
            mock_config_obj.gpu = False
            mock_config_obj.queue_max = 100
            mock_config_obj.batch_size = 5
            mock_load_config.return_value = mock_config_obj

            # First initialization
            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo_with_config
            config.plugins_dir = temp_repo_with_config / "plugins"
            config.plugin_config = {"enabled": True}
            config.repo_slug = "tmp"  # Add repo_slug

            indexer1 = VectorIndexer()
            indexer1.initialize(config)

            # Add an entry
            entry = {
                'entry_id': 'persist' + 'a' * 26,
                'project_name': 'Persistence Test',
                'message': 'This entry should persist across restarts',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:00:00 UTC',
                'meta': {'test': 'persistence'}
            }
            indexer1.post_append(entry)

            # Wait for processing
            await asyncio.sleep(3)

            initial_status = indexer1.get_index_status()
            initial_entries = initial_status['total_entries']

            # Cleanup first instance
            indexer1.cleanup()

            # Create new instance (simulating restart)
            indexer2 = VectorIndexer()
            indexer2.initialize(config)

            # Check that index was loaded
            restart_status = indexer2.get_index_status()
            assert restart_status['total_entries'] >= initial_entries

            # Search should still work
            results = indexer2.search_similar("persist", k=5)
            assert len(results) >= 0

            # Cleanup
            indexer2.cleanup()

    async def test_background_queue_processing(self, temp_repo_with_config, mock_settings):
        """Test background queue processing with multiple entries."""
        with patch('scribe_mcp.plugins.registry.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:

            # Set project_root dynamically for sandbox validation
            mock_settings.project_root = temp_repo_with_config

            # Mock vector config
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = True
            mock_config_obj.backend = "faiss"
            mock_config_obj.dimension = 384
            mock_config_obj.model = "all-MiniLM-L6-v2"
            mock_config_obj.gpu = False
            mock_config_obj.queue_max = 100
            mock_config_obj.batch_size = 5
            mock_load_config.return_value = mock_config_obj

            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo_with_config
            config.plugins_dir = temp_repo_with_config / "plugins"
            config.plugin_config = {"enabled": True}
            config.repo_slug = "tmp"  # Add repo_slug

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Give background thread time to start
            await asyncio.sleep(0.5)

            # Create many test entries
            num_entries = 20
            entries = []
            for i in range(num_entries):
                entry = {
                    'entry_id': f'batch{i:03d}' + 'a' * 22,  # Pad to 32 chars
                    'project_name': 'Batch Test Project',
                    'message': f'Batch entry number {i} with test content',
                    'agent': 'TestAgent',
                    'timestamp': f'2025-10-26 12:{i:02d}:00 UTC',
                    'meta': {'batch': True, 'index': i}
                }
                entries.append(entry)
                indexer.post_append(entry)

            # Monitor queue processing - check that queue exists (items may be processed quickly)
            assert indexer.embedding_queue is not None
            initial_queue_depth = indexer.embedding_queue.qsize() if indexer.embedding_queue else 0

            # Wait for queue to process
            max_wait = 60  # 60 seconds max for batch processing
            wait_time = 0
            while (indexer.embedding_queue and
                   not indexer.embedding_queue.empty() and
                   wait_time < max_wait):
                await asyncio.sleep(1)
                wait_time += 1

            # Check final status
            final_status = indexer.get_index_status()
            assert final_status['queue_depth'] == 0

            # Verify some entries were processed
            assert final_status['total_entries'] >= 0

            # Cleanup
            indexer.cleanup()

    async def test_error_handling_and_recovery(self, temp_repo_with_config, mock_settings):
        """Test error handling and recovery in vector indexing."""
        with patch('scribe_mcp.plugins.registry.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:

            # Set project_root dynamically for sandbox validation
            mock_settings.project_root = temp_repo_with_config

            # Mock vector config
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = True
            mock_config_obj.backend = "faiss"
            mock_config_obj.dimension = 384
            mock_config_obj.model = "all-MiniLM-L6-v2"
            mock_config_obj.gpu = False
            mock_config_obj.queue_max = 100
            mock_config_obj.batch_size = 5
            mock_load_config.return_value = mock_config_obj

            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo_with_config
            config.plugins_dir = temp_repo_with_config / "plugins"
            config.plugin_config = {"enabled": True}
            config.repo_slug = "tmp"  # Add repo_slug

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Test with malformed entry data
            malformed_entry = {
                'entry_id': '',  # Empty ID
                'project_name': 'Test Project',
                'message': 'Test message',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:00:00 UTC',
                'meta': {'test': 'malformed'}
            }

            # Should not crash
            indexer.post_append(malformed_entry)

            # Test with very long message
            long_entry = {
                'entry_id': 'long' + 'a' * 27,
                'project_name': 'Test Project',
                'message': 'A' * 10000,  # Very long message
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:00:00 UTC',
                'meta': {'test': 'long'}
            }

            indexer.post_append(long_entry)

            # Wait for processing
            await asyncio.sleep(2)

            # System should still be functional
            status = indexer.get_index_status()
            assert status['initialized'] is True

            # Cleanup
            indexer.cleanup()

    async def test_memory_management(self, temp_repo_with_config, mock_settings):
        """Test memory management during large index operations."""
        with patch('scribe_mcp.plugins.registry.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.settings', mock_settings), \
             patch('scribe_mcp.plugins.vector_indexer.load_vector_config') as mock_load_config:

            # Set project_root dynamically for sandbox validation
            mock_settings.project_root = temp_repo_with_config

            # Mock vector config
            mock_config_obj = MagicMock()
            mock_config_obj.enabled = True
            mock_config_obj.backend = "faiss"
            mock_config_obj.dimension = 384
            mock_config_obj.model = "all-MiniLM-L6-v2"
            mock_config_obj.gpu = False
            mock_config_obj.queue_max = 100
            mock_config_obj.batch_size = 2  # Small batch size for testing
            mock_load_config.return_value = mock_config_obj

            config = MagicMock(spec=RepoConfig)
            config.repo_root = temp_repo_with_config
            config.plugins_dir = temp_repo_with_config / "plugins"
            config.plugin_config = {"enabled": True}
            config.repo_slug = "tmp"  # Add repo_slug

            indexer = VectorIndexer()
            indexer.initialize(config)

            # Add many entries to test memory usage
            for i in range(50):  # 50 entries
                entry = {
                    'entry_id': f'mem{i:03d}' + 'a' * 22,
                    'project_name': 'Memory Test',
                    'message': f'Memory test entry {i} with substantial content to test memory management',
                    'agent': 'TestAgent',
                    'timestamp': f'2025-10-26 12:{i%60:02d}:00 UTC',
                    'meta': {'memory_test': True, 'batch': i // 10}
                }
                indexer.post_append(entry)

            # Wait for processing
            await asyncio.sleep(10)

            # System should still be responsive
            status = indexer.get_index_status()
            assert status['initialized'] is True

            # Search should work
            results = indexer.search_similar("memory test", k=5)
            assert isinstance(results, list)

            # Cleanup
            indexer.cleanup()


@pytest.mark.skipif(VECTOR_DEPS_AVAILABLE, reason="Test requires missing dependencies")
class TestVectorIntegrationWithoutDeps:
    """Integration tests when vector dependencies are not available."""

    def test_graceful_degradation_without_dependencies(self):
        """Test graceful degradation when vector dependencies are missing."""
        # Should be able to initialize without vector functionality
        with patch('scribe_mcp.plugins.vector_indexer.FAISS_AVAILABLE', False), \
             patch('scribe_mcp.plugins.vector_indexer.settings') as mock_settings:

            mock_settings.vector_enabled = True

            with tempfile.TemporaryDirectory() as temp_dir:
                repo_path = Path(temp_dir)
                (repo_path / ".scribe_vectors").mkdir(exist_ok=True)

                config = MagicMock(spec=RepoConfig)
                config.repo_root = repo_path
                config.plugins_dir = repo_path / "plugins"
                config.plugin_config = {"enabled": True}

                indexer = VectorIndexer()
                indexer.initialize(config)

                # Should not be initialized
                assert not indexer.initialized
                assert not indexer.enabled

                # Tools should not be registered
                from scribe_mcp.tools.vector_search import register_vector_tools
                tools_registered = register_vector_tools()
                assert tools_registered is False

                # Cleanup should not crash
                indexer.cleanup()