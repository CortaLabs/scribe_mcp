#!/usr/bin/env python3
"""Debug test to understand vector processing issues."""

import tempfile
import json
import sqlite3
import time
from pathlib import Path

import os

# Set SCRIBE_ROOT for proper imports
os.environ['SCRIBE_ROOT'] = str(Path(__file__).parent.parent.parent)

# Try to import vector dependencies
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    VECTOR_DEPS_AVAILABLE = True
except ImportError:
    VECTOR_DEPS_AVAILABLE = False
    print("❌ Vector dependencies not available")
    exit(1)

from scribe_mcp.plugins.vector_indexer import VectorIndexer
from scribe_mcp.config.repo_config import RepoConfig

def debug_vector_processing():
    """Debug vector processing step by step."""

    print("🔍 Starting vector processing debug...")

    # Create temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)
        print(f"📁 Created temp repo: {repo_path}")

        # Create necessary directories
        (repo_path / ".scribe_vectors").mkdir(exist_ok=True)
        (repo_path / "plugins").mkdir(exist_ok=True)

        # Create vector config
        vector_config = {
            "enabled": True,
            "backend": "faiss",
            "dimension": 384,
            "model": "all-MiniLM-L6-v2",
            "gpu": False,
            "queue_max": 10,
            "batch_size": 2,
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

        print("✅ Created vector config")

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

        # Copy plugin file
        import shutil
        current_plugin = Path(__file__).parent.parent / "plugins" / "vector_indexer.py"
        shutil.copy(current_plugin, repo_path / "plugins" / "vector_indexer.py")

        print("✅ Created plugin manifest and copied plugin")

        # Initialize vector indexer
        config = RepoConfig(
            repo_slug="debug-test",
            repo_root=repo_path,
            plugins_dir=repo_path / "plugins",
            plugin_config={"enabled": True}
        )

        print("🚀 Initializing vector indexer...")
        vector_indexer = VectorIndexer()
        vector_indexer.initialize(config)

        print(f"✅ Vector indexer initialized: {vector_indexer.initialized}")
        print(f"✅ Vector indexer enabled: {vector_indexer.enabled}")
        print(f"✅ Vector config: enabled={vector_indexer.vector_config.enabled}, model={vector_indexer.vector_config.model}")

        # Create test entry
        test_entry = {
            'entry_id': 'debug01' + 'a' * 24,
            'project_name': 'Debug Test',
            'message': 'This is a debug test entry for vector processing',
            'agent': 'DebugAgent',
            'timestamp': '2025-10-26 12:00:00 UTC',
            'meta': {'test': 'debug', 'phase': 'testing'}
        }

        print("📝 Adding test entry to vector indexer...")
        vector_indexer.post_append(test_entry)
        print("✅ Entry added to queue")

        # Check if warning was logged
        print("🔍 Checking if warnings were logged...")
        if vector_indexer.embedding_queue:
            print(f"📊 Queue exists and type: {type(vector_indexer.embedding_queue)}")
            queue_size = vector_indexer.embedding_queue.qsize()
            print(f"📊 Queue size: {queue_size}")
        else:
            print("❌ Queue is None!")

        # Check queue status
        if vector_indexer.embedding_queue:
            queue_size = vector_indexer.embedding_queue.qsize()
            print(f"📊 Queue size after adding entry: {queue_size}")
        else:
            print("❌ Embedding queue is None!")

        # Check worker task
        if vector_indexer.queue_worker_task:
            print(f"🔄 Worker task status: {vector_indexer.queue_worker_task}")
            print(f"🔄 Worker task done: {vector_indexer.queue_worker_task.done()}")
        else:
            print("❌ Worker task is None!")

        # Wait and check processing
        print("⏳ Waiting for processing...")
        for i in range(10):  # Wait up to 10 seconds
            time.sleep(1)
            status = vector_indexer.get_index_status()
            print(f"📊 Status after {i+1}s: entries={status['total_entries']}, queue_depth={status['queue_depth']}")

            if status['total_entries'] > 0:
                print("✅ Entry processed successfully!")
                break
        else:
            print("❌ Entry was not processed after 10 seconds")

        # Final status
        final_status = vector_indexer.get_index_status()
        print(f"📋 Final status: {final_status}")

        # Check database
        mapping_db_path = repo_path / ".scribe_vectors" / "mapping.sqlite"
        if mapping_db_path.exists():
            conn = sqlite3.connect(str(mapping_db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM vector_entries")
            db_count = cursor.fetchone()[0]
            print(f"💾 Database entries: {db_count}")
            conn.close()
        else:
            print("❌ Mapping database doesn't exist!")

        # Check index file
        index_file = repo_path / ".scribe_vectors" / "debug-test.faiss"
        if index_file.exists():
            print(f"📁 Index file exists: {index_file.stat().st_size} bytes")
        else:
            print("❌ Index file doesn't exist!")

        # Test search
        print("🔍 Testing search...")
        search_results = vector_indexer.search_similar("debug test", k=5)
        print(f"🔍 Search results: {len(search_results)} items")

        # Cleanup
        print("🧹 Cleaning up...")
        vector_indexer.cleanup()
        print("✅ Cleanup complete")

if __name__ == "__main__":
    debug_vector_processing()