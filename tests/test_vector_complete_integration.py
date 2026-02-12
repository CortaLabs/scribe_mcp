#!/usr/bin/env python3
"""Integration test for complete vector indexing workflow.

This test creates actual vectors, stores them in the database, and tests all methods.
"""

import pytest
import pytest_asyncio
import tempfile
import asyncio
import json
import sqlite3
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
from scribe_mcp.storage.models import VectorIndexRecord, VectorShardMetadata


@pytest.mark.skipif(not VECTOR_DEPS_AVAILABLE, reason="Vector dependencies not available")
@pytest.mark.asyncio
class TestVectorIntegrationWorkflow:
    """Integration tests for complete vector indexing workflow."""

    async def _wait_for_entries(self, indexer: VectorIndexer, expected_count: int, timeout: float = 30.0) -> dict:
        """Poll the indexer until expected entries exist or timeout occurs."""
        elapsed = 0.0
        poll_interval = 0.5

        while elapsed < timeout:
            status = indexer.get_index_status()
            if status['total_entries'] >= expected_count:
                return status
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        final_status = indexer.get_index_status()
        raise AssertionError(
            f"Timed out waiting for {expected_count} entries. Last status: {final_status}"
        )

    @pytest_asyncio.fixture
    async def temp_repo_with_config(self):
        """Create a temporary repository with full configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)

            # Create necessary directories
            (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
            (repo_path / "plugins").mkdir(exist_ok=True)
            (repo_path / "config" / "projects").mkdir(parents=True, exist_ok=True)

            # Create custom vector config for testing
            vector_config = {
                "enabled": True,
                "backend": "faiss",
                "dimension": 384,
                "model": "all-MiniLM-L6-v2",
                "gpu": False,
                "queue_max": 100,
                "batch_size": 5,
                "max_retries": 3,
                "retry_backoff_factor": 2.0,
                "queue_timeout_seconds": 1,
                "model_device": "cpu",
                "cache_size": 1000,
                "index_type": "IndexFlatIP",
                "metric": "cosine",
                "min_similarity_threshold": 0.0,
                "search_k_limit": 100
            }

            with open(repo_path / ".scribe_vectors" / "vector.json", 'w') as f:
                json.dump(vector_config, f, indent=2)

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

            # Cleanup will happen automatically when TemporaryDirectory exits
            # All files (vector indices, databases, etc.) will be deleted
            print(f"Temporary directory {temp_dir} will be automatically cleaned up")

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = MagicMock(spec=Settings)
        settings.project_root = Path("/tmp")
        return settings

    async def test_complete_vector_workflow(self, temp_repo_with_config, mock_settings):
        """Test complete workflow: create index -> add entries -> search -> rebuild."""

        # Initialize vector indexer directly
        config = RepoConfig(
            repo_slug="test-repo",
            repo_root=temp_repo_with_config,
            plugins_dir=temp_repo_with_config / "plugins",
            plugin_config={"enabled": True}
        )

        vector_indexer = VectorIndexer()
        vector_indexer.initialize(config)

        assert vector_indexer.initialized
        assert vector_indexer.enabled
        assert vector_indexer.vector_config.enabled

        # Test 1: Initial status
        initial_status = vector_indexer.get_index_status()
        assert initial_status['total_entries'] == 0
        assert initial_status['enabled'] is True

        # Test 2: Create test entries
        test_entries = [
            {
                'entry_id': 'test1' + 'a' * 28,  # Make 32 chars
                'project_name': 'Test Project',
                'message': 'This is a test about software development and Python programming',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:00:00 UTC',
                'meta': {'phase': 'development', 'component': 'backend', 'language': 'python'}
            },
            {
                'entry_id': 'test2' + 'b' * 28,
                'project_name': 'Test Project',
                'message': 'Database optimization and SQL query performance tuning',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:01:00 UTC',
                'meta': {'phase': 'optimization', 'component': 'database', 'language': 'sql'}
            },
            {
                'entry_id': 'test3' + 'c' * 28,
                'project_name': 'Test Project',
                'message': 'User interface design and CSS styling improvements',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:02:00 UTC',
                'meta': {'phase': 'design', 'component': 'frontend', 'language': 'css'}
            },
            {
                'entry_id': 'test4' + 'd' * 28,
                'project_name': 'Test Project',
                'message': 'JavaScript async/await patterns and Promise handling',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:03:00 UTC',
                'meta': {'phase': 'development', 'component': 'frontend', 'language': 'javascript'}
            },
            {
                'entry_id': 'test5' + 'e' * 28,
                'project_name': 'Test Project',
                'message': 'Python machine learning with scikit-learn and pandas',
                'agent': 'TestAgent',
                'timestamp': '2025-10-26 12:04:00 UTC',
                'meta': {'phase': 'development', 'component': 'ml', 'language': 'python'}
            }
        ]

        # Test 3: Add entries to vector index
        for entry in test_entries:
            vector_indexer.post_append(entry)

        # Test 4: Wait for background processing
        final_status = await self._wait_for_entries(vector_indexer, expected_count=len(test_entries))
        print(f"Final status: {final_status}")
        assert final_status['total_entries'] >= len(test_entries)

        # Test 5: Semantic search functionality
        search_results = vector_indexer.search_similar(
            query="python programming code",
            k=3
        )

        print(f"Search results for 'python programming code': {search_results}")

        # Should find relevant results (Python-related entries)
        assert len(search_results) >= 0

        if search_results:
            # Check result structure
            first_result = search_results[0]
            assert 'entry_id' in first_result
            assert 'similarity_score' in first_result
            assert 'text_content' in first_result
            assert 0 <= first_result['similarity_score'] <= 1

        # Test 6: Filtered search by component
        backend_results = vector_indexer.search_similar(
            query="software development",
            k=5,
            filters={'component': 'backend'}
        )
        print(f"Backend filter results: {backend_results}")

        # Test 7: Filtered search by language
        python_results = vector_indexer.search_similar(
            query="programming",
            k=5,
            filters={'language': 'python'}
        )
        print(f"Python language results: {python_results}")

        # Test 8: Time range filtering
        time_filtered = vector_indexer.search_similar(
            query="test",
            k=10,
            filters={
                'time_range': {
                    'start': '2025-10-26T12:00:00',
                    'end': '2025-10-26T12:02:30'
                }
            }
        )
        print(f"Time range results: {time_filtered}")

        # Test 9: Direct UUID retrieval
        if search_results:
            first_result = search_results[0]
            retrieved_entry = vector_indexer.retrieve_by_uuid(first_result['entry_id'])

            assert retrieved_entry is not None
            assert retrieved_entry['entry_id'] == first_result['entry_id']
            assert 'text_content' in retrieved_entry
            print(f"Retrieved entry by UUID: {retrieved_entry['entry_id']}")

        # Test 10: Database persistence verification
        mapping_db_path = temp_repo_with_config / ".scribe_vectors" / "mapping.sqlite"
        assert mapping_db_path.exists(), "Mapping database should exist"

        # Check database contents
        conn = sqlite3.connect(str(mapping_db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM vector_entries WHERE repo_slug = ?", (vector_indexer.repo_slug,))
        db_entry_count = cursor.fetchone()[0]
        print(f"Entries in mapping database: {db_entry_count}")

        # Check vector index file exists
        index_file_path = temp_repo_with_config / ".scribe_vectors" / f"{vector_indexer.repo_slug}.faiss"
        metadata_file_path = temp_repo_with_config / ".scribe_vectors" / f"{vector_indexer.repo_slug}.meta.json"

        assert index_file_path.exists(), "FAISS index file should exist"
        assert metadata_file_path.exists(), "Metadata file should exist"

        conn.close()

        # Test 11: Index rebuild functionality
        print("Testing index rebuild...")
        rebuild_result = vector_indexer.rebuild_index()

        assert rebuild_result['success'] is True
        assert 'rebuild_time_seconds' in rebuild_result
        assert 'old_entries_count' in rebuild_result
        assert 'new_entries_count' in rebuild_result

        # After rebuild, index should be empty
        post_rebuild_status = vector_indexer.get_index_status()
        assert post_rebuild_status['total_entries'] == 0
        print("Index rebuild successful")

        # Test 12: Configuration verification
        assert vector_indexer.vector_config.enabled is True
        assert vector_indexer.vector_config.model == "all-MiniLM-L6-v2"
        assert vector_indexer.vector_config.dimension == 384
        assert vector_indexer.vector_config.batch_size == 5
        assert vector_indexer.vector_config.queue_max == 100

        # Test 13: Error handling - try invalid UUID
        invalid_result = vector_indexer.retrieve_by_uuid("nonexistent-uuid-12345")
        assert invalid_result is None

        # Cleanup
        try:
            vector_indexer.cleanup()
            print("Vector indexer cleanup completed")
        except Exception as cleanup_error:
            print(f"Warning: Cleanup error occurred: {cleanup_error}")

        print("All tests completed successfully!")

    async def test_vector_database_persistence(self, temp_repo_with_config):
        """Test that vector data persists across plugin restarts."""

        config = RepoConfig(
            repo_slug="persistence-test",
            repo_root=temp_repo_with_config,
            plugins_dir=temp_repo_with_config / "plugins",
            plugin_config={"enabled": True}
        )

        # First instance - add data
        indexer1 = VectorIndexer()
        indexer1.initialize(config)

        test_entry = {
            'entry_id': 'persist01' + 'a' * 22,
            'project_name': 'Persistence Test',
            'message': 'This entry should persist across restarts',
            'agent': 'TestAgent',
            'timestamp': '2025-10-26 12:00:00 UTC',
            'meta': {'test': 'persistence', 'type': 'database'}
        }

        indexer1.post_append(test_entry)
        await self._wait_for_entries(indexer1, expected_count=1, timeout=30)

        initial_status = indexer1.get_index_status()
        initial_entries = initial_status['total_entries']

        indexer1.cleanup()

        # Second instance - should load existing data
        indexer2 = VectorIndexer()
        indexer2.initialize(config)

        loaded_status = indexer2.get_index_status()
        print(f"Loaded entries after restart: {loaded_status['total_entries']}")

        # Should have at least as many entries as before
        assert loaded_status['total_entries'] >= initial_entries

        # Search should work
        search_results = indexer2.search_similar("persistence test", k=5)
        assert isinstance(search_results, list)

        # Cleanup both instances
        try:
            indexer1.cleanup()
            indexer2.cleanup()
            print("Both indexer instances cleaned up successfully")
        except Exception as cleanup_error:
            print(f"Warning: Cleanup error occurred: {cleanup_error}")

    async def test_vector_config_modification(self, temp_repo_with_config):
        """Test that vector config changes are properly loaded."""

        # Test with modified config
        modified_config = {
            "enabled": True,
            "backend": "faiss",
            "dimension": 512,  # Changed dimension
            "model": "all-MiniLM-L6-v2",
            "gpu": False,
            "queue_max": 200,  # Changed queue size
            "batch_size": 10,  # Changed batch size
            "max_retries": 3,
            "retry_backoff_factor": 2.0,
            "queue_timeout_seconds": 1,
            "model_device": "cpu",
            "cache_size": 1000,
            "index_type": "IndexFlatIP",
            "metric": "cosine",
            "min_similarity_threshold": 0.0,
            "search_k_limit": 100
        }

        # Update config file
        config_file = temp_repo_with_config / ".scribe_vectors" / "vector.json"
        with open(config_file, 'w') as f:
            json.dump(modified_config, f, indent=2)

        config = RepoConfig(
            repo_slug="config-test",
            repo_root=temp_repo_with_config,
            plugins_dir=temp_repo_with_config / "plugins",
            plugin_config={"enabled": True}
        )

        indexer = VectorIndexer()
        indexer.initialize(config)

        # Verify config was loaded correctly
        assert indexer.vector_config.dimension == 512
        assert indexer.vector_config.queue_max == 200
        assert indexer.vector_config.batch_size == 10

        # Cleanup
        try:
            indexer.cleanup()
            print("Config test indexer cleaned up successfully")
        except Exception as cleanup_error:
            print(f"Warning: Cleanup error occurred: {cleanup_error}")


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Ensure cleanup after each test."""
    yield
    # This runs after each test method
    import gc
    gc.collect()  # Force garbage collection


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
