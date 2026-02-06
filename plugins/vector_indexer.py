"""Vector Indexer Plugin for Scribe MCP

This plugin provides automatic vector indexing for Scribe log entries,
enabling semantic search capabilities while maintaining repository isolation.

Features:
- Background embedding generation with asyncio queue
- Repository-scoped FAISS index management
- Deterministic UUID-based entry indexing
- Graceful fallback when dependencies unavailable
- Atomic index updates with rollback capability
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import threading

# Suppress HuggingFace progress bars that pollute stdout (breaks MCP JSON-RPC)
import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# Vector processing imports — lazy loaded in _load_vector_deps() to avoid
# 8+ second startup penalty from torch/transformers/faiss/numpy.
FAISS_AVAILABLE: bool = False
faiss = None
np = None
SentenceTransformer = None


def _load_vector_deps() -> bool:
    """Lazy-load heavy vector dependencies. Returns True if available."""
    global FAISS_AVAILABLE, faiss, np, SentenceTransformer
    if FAISS_AVAILABLE:
        return True
    try:
        import faiss as _faiss
        import numpy as _np
        from sentence_transformers import SentenceTransformer as _ST
        faiss = _faiss
        np = _np
        SentenceTransformer = _ST
        FAISS_AVAILABLE = True
        return True
    except ImportError:
        return False

from scribe_mcp.plugins.registry import HookPlugin
from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.config.vector_config import load_vector_config
from scribe_mcp.storage.models import VectorShardMetadata
from scribe_mcp.utils.time import utcnow

# Setup logging
plugin_logger = logging.getLogger(__name__)


class VectorIndexer(HookPlugin):
    """Vector indexing plugin for Scribe log entries."""

    name = "vector_indexer"
    version = "1.0.0"
    description = "Automatic vector indexing for semantic search"
    author = "VectorIndexAgent"

    def __init__(self):
        self.repo_config: Optional[RepoConfig] = None
        self.repo_root: Optional[Path] = None
        self.repo_slug: Optional[str] = None
        self.vector_config: Optional[VectorConfig] = None

        # Vector processing components
        self.embedding_model: Optional[SentenceTransformer] = None
        self.vector_index: Optional[faiss.Index] = None
        self.index_metadata: Optional[VectorShardMetadata] = None

        # Background processing
        self.embedding_queue: Optional[asyncio.Queue] = None
        self.queue_worker_task: Optional[asyncio.Task] = None
        self.queue_lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()
        self._owns_loop = False

        # Database connection for mapping
        self.mapping_db_path: Optional[Path] = None
        self._db_lock = threading.Lock()

        # State tracking
        self.initialized = False
        self.enabled = False  # Will be set from config
        self._shutdown_event = threading.Event()

    def initialize(self, config: RepoConfig) -> None:
        """Initialize the vector indexer plugin."""
        # Load configuration
        self.vector_config = load_vector_config(config.repo_root)
        self.enabled = self.vector_config.enabled

        if not self.enabled:
            plugin_logger.info("Vector indexing disabled via configuration")
            return

        # Lazy-load heavy deps only when plugin is actually enabled
        if not _load_vector_deps():
            plugin_logger.warning("FAISS dependencies not available, vector indexing disabled")
            self.enabled = False
            return

        try:
            self.repo_config = config
            self.repo_root = config.repo_root
            self.repo_slug = config.repo_slug or self._get_repo_slug(self.repo_root)

            # Initialize vector components
            self._init_embedding_model()
            self._init_vector_index()
            self._init_mapping_database()
            self._init_background_queue()

            self.initialized = True
            plugin_logger.info(f"VectorIndexer initialized for repository: {self.repo_slug}")

        except Exception as e:
            plugin_logger.error(f"Failed to initialize VectorIndexer: {e}", exc_info=True)
            self.enabled = False

    def cleanup(self) -> None:
        """Cleanup plugin resources."""
        if not self.initialized:
            return

        try:
            # Signal shutdown
            self._shutdown_event.set()

            # Cancel background worker
            if self.queue_worker_task:
                if self._owns_loop and self._loop:
                    def _cancel_task() -> None:
                        if not self.queue_worker_task.done():
                            self.queue_worker_task.cancel()

                    self._loop.call_soon_threadsafe(_cancel_task)
                elif not self.queue_worker_task.done():
                    self.queue_worker_task.cancel()

            # Stop dedicated event loop if we own it
            if self._owns_loop and self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._loop_thread and self._loop_thread.is_alive():
                    self._loop_thread.join(timeout=5)
                self._loop = None
                self._loop_thread = None
                self.embedding_queue = None
                self.queue_lock = None
                self._owns_loop = False

            # Close database connection
            with self._db_lock:
                if hasattr(self, '_db_conn') and self._db_conn:
                    self._db_conn.close()

            plugin_logger.info("VectorIndexer cleanup completed")

        except Exception as e:
            plugin_logger.error(f"Error during VectorIndexer cleanup: {e}")

    def post_append(self, entry_data: Dict[str, Any]) -> None:
        """Called after an entry is appended - queue for vector indexing."""
        if not self.initialized or not self.enabled:
            plugin_logger.debug("Vector indexer inactive, skipping entry")
            return

        if self._shutdown_event.is_set():
            plugin_logger.warning("Vector indexer shutting down, skipping entry")
            return

        if not self.embedding_queue or not self._loop:
            plugin_logger.warning("Embedding queue not available, skipping entry")
            return

        try:
            # Schedule the coroutine as a task on the background loop
            self._loop.call_soon_threadsafe(
                lambda: self._loop.create_task(self._queue_entry_for_embedding(entry_data))
            )
        except Exception as e:
            plugin_logger.error(f"Failed to queue entry for vector indexing: {e}")

    def enqueue_entry(
        self,
        entry_data: Dict[str, Any],
        *,
        wait: bool = False,
        timeout: Optional[float] = None,
    ) -> bool:
        """Queue an entry for vector indexing, optionally waiting for space."""
        if not self.initialized or not self.enabled:
            return False

        if not self.embedding_queue or not self._loop:
            plugin_logger.warning("Embedding queue not available, skipping entry")
            return False

        if not wait:
            self.post_append(entry_data)
            return True

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._queue_entry_for_embedding_wait(entry_data, timeout),
                self._loop,
            )
            return bool(future.result(timeout=timeout if timeout else None))
        except Exception as exc:
            plugin_logger.error(f"Failed to enqueue entry with backpressure: {exc}")
            return False

    @staticmethod
    def _log_async_error(future: asyncio.Future) -> None:
        """Log exceptions from background scheduling."""
        try:
            future.result()
        except Exception as exc:
            plugin_logger.error(f"Vector queue scheduling error: {exc}")

    def _get_repo_slug(self, repo_root: Path) -> str:
        """Generate repository slug from root path."""
        import re
        repo_name = repo_root.name
        slug = re.sub(r'[^a-zA-Z0-9_-]', '-', repo_name.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug or "unknown-repo"

    def _init_embedding_model(self) -> None:
        """Initialize the sentence transformer model."""
        try:
            model_name = self.vector_config.model
            self.embedding_model = SentenceTransformer(model_name)
            plugin_logger.info(f"Loaded embedding model: {model_name}")
        except Exception as e:
            plugin_logger.error(f"Failed to load embedding model: {e}")
            raise

    def _init_vector_index(self) -> None:
        """Initialize or load the FAISS index."""
        try:
            vectors_dir = self.repo_root / ".scribe_vectors"
            vectors_dir.mkdir(exist_ok=True)

            index_path = vectors_dir / f"{self.repo_slug}.faiss"
            metadata_path = vectors_dir / f"{self.repo_slug}.meta.json"

            # Load or create index
            if index_path.exists() and metadata_path.exists():
                self._load_existing_index(index_path, metadata_path)
            else:
                self._create_new_index(index_path, metadata_path)

            plugin_logger.info(f"Vector index ready: {self.index_metadata.total_entries} entries")

        except Exception as e:
            plugin_logger.error(f"Failed to initialize vector index: {e}")
            raise

    def _load_existing_index(self, index_path: Path, metadata_path: Path) -> None:
        """Load existing FAISS index and metadata."""
        # Load metadata
        with open(metadata_path, 'r') as f:
            metadata_dict = json.load(f)

        self.index_metadata = VectorShardMetadata(
            repo_slug=metadata_dict['repo_slug'],
            dimension=metadata_dict['dimension'],
            model=metadata_dict['model'],
            scope=metadata_dict['scope'],
            created_at=datetime.fromisoformat(metadata_dict['created_at']),
            backend=metadata_dict['backend'],
            index_type=metadata_dict['index_type'],
            total_entries=metadata_dict['total_entries'],
            last_updated=datetime.fromisoformat(metadata_dict['last_updated']) if metadata_dict.get('last_updated') else None,
            embedding_model_version=metadata_dict.get('embedding_model_version'),
            index_size_bytes=index_path.stat().st_size if index_path.exists() else None
        )

        # Validate configuration compatibility
        if (self.index_metadata.dimension != self.vector_config.dimension or
            self.index_metadata.model != self.vector_config.model):
            plugin_logger.warning(
                f"Index configuration mismatch. Index: dim={self.index_metadata.dimension}, "
                f"model={self.index_metadata.model}. Settings: dim={self.vector_config.dimension}, "
                f"model={self.vector_config.model}. Consider rebuilding index."
            )

        # Load FAISS index
        self.vector_index = faiss.read_index(str(index_path))

        # Load GPU if enabled
        if self.vector_config.gpu and hasattr(faiss, 'StandardGpuResources'):
            try:
                res = faiss.StandardGpuResources()
                self.vector_index = faiss.index_cpu_to_gpu(res, 0, self.vector_index)
                plugin_logger.info("GPU acceleration enabled for vector index")
            except Exception as e:
                plugin_logger.warning(f"Failed to enable GPU acceleration: {e}")

    def _create_new_index(self, index_path: Path, metadata_path: Path) -> None:
        """Create new FAISS index and metadata."""
        dimension = self.vector_config.dimension

        # Create FAISS index (IndexFlatIP for inner product)
        self.vector_index = faiss.IndexFlatIP(dimension)

        # Create metadata
        self.index_metadata = VectorShardMetadata(
            repo_slug=self.repo_slug,
            dimension=dimension,
            model=self.vector_config.model,
            scope="repo-local",
            created_at=utcnow(),
            backend="faiss",
            index_type="IndexFlatIP",
            total_entries=0,
            last_updated=utcnow(),
            embedding_model_version=getattr(self.embedding_model, 'version', 'unknown')
        )

        # Save index and metadata
        faiss.write_index(self.vector_index, str(index_path))
        self._save_index_metadata(metadata_path)
        plugin_logger.info(f"Created new vector index: {dimension}D")

    def _init_mapping_database(self) -> None:
        """Initialize the SQLite database for UUID mapping."""
        vectors_dir = self.repo_root / ".scribe_vectors"
        self.mapping_db_path = vectors_dir / "mapping.sqlite"

        with self._db_lock:
            self._db_conn = sqlite3.connect(str(self.mapping_db_path), check_same_thread=False)
            self._db_conn.row_factory = sqlite3.Row

            # Create tables
            self._db_conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT UNIQUE NOT NULL,
                    project_slug TEXT NOT NULL,
                    repo_slug TEXT NOT NULL,
                    vector_rowid INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    agent_name TEXT,
                    timestamp_utc TEXT NOT NULL,
                    metadata_json TEXT,
                    embedding_model TEXT,
                    vector_dimension INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_id ON vector_entries(entry_id)")
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_project_slug ON vector_entries(project_slug)")
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON vector_entries(timestamp_utc)")

            self._db_conn.commit()

    def _init_background_queue(self) -> None:
        """Initialize the background embedding processing queue."""
        maxsize = self.vector_config.queue_max

        plugin_logger.info("Starting dedicated background loop for vector processing")
        self._owns_loop = True
        self._loop = asyncio.new_event_loop()
        self._loop_ready.clear()

        self._loop_thread = threading.Thread(
            target=self._start_background_loop,
            args=(maxsize,),
            name=f"VectorIndexerLoop-{self.repo_slug}",
            daemon=True
        )
        self._loop_thread.start()

        if not self._loop_ready.wait(timeout=5):
            raise RuntimeError("Timed out waiting for vector background loop to start")

        plugin_logger.info(f"Background queue initialized on dedicated loop (maxsize: {maxsize})")

    def _start_background_loop(self, maxsize: int) -> None:
        """Run a dedicated asyncio loop for vector processing."""
        if not self._loop:
            return

        asyncio.set_event_loop(self._loop)
        self.embedding_queue = asyncio.Queue(maxsize=maxsize)
        self.queue_lock = asyncio.Lock()
        self.queue_worker_task = self._loop.create_task(self._queue_worker())
        self._loop_ready.set()

        try:
            self._loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self._loop)
            for task in tasks:
                task.cancel()
            if tasks:
                self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()
            asyncio.set_event_loop(None)

    async def _queue_entry_for_embedding(self, entry_data: Dict[str, Any]) -> None:
        """Queue an entry for background embedding processing."""
        if not self.embedding_queue:
            return

        try:
            embedding_task = self._prepare_embedding_task(entry_data)

            # Add to queue (non-blocking)
            self.embedding_queue.put_nowait(embedding_task)

        except asyncio.QueueFull:
            plugin_logger.warning(f"Vector embedding queue full, dropping entry: {entry_data.get('entry_id')}")
        except Exception as e:
            plugin_logger.error(f"Failed to queue entry for embedding: {e}")

    async def _queue_entry_for_embedding_wait(
        self,
        entry_data: Dict[str, Any],
        timeout: Optional[float],
    ) -> bool:
        """Queue an entry for embedding, waiting for available capacity."""
        if not self.embedding_queue:
            return False

        try:
            embedding_task = self._prepare_embedding_task(entry_data)
            if timeout:
                await asyncio.wait_for(self.embedding_queue.put(embedding_task), timeout=timeout)
            else:
                await self.embedding_queue.put(embedding_task)
            return True
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            plugin_logger.error(f"Failed to queue entry with backpressure: {e}")
            return False

    def _prepare_embedding_task(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'entry_id': entry_data.get('entry_id'),
            'project_slug': entry_data.get('project_name', '').lower().replace(' ', '-'),
            'text_content': entry_data.get('message', ''),
            'agent_name': entry_data.get('agent', ''),
            'timestamp_utc': entry_data.get('timestamp', ''),
            'metadata_json': json.dumps(entry_data.get('meta', {})),
            'embedding_model': self.vector_config.model,
            'vector_dimension': self.vector_config.dimension,
            'retry_count': 0,
            'queued_at': utcnow()
        }

    async def _queue_worker(self) -> None:
        """Background worker for processing embedding queue."""
        batch_size = self.vector_config.batch_size
        plugin_logger.info(f"Vector embedding worker started (batch_size: {batch_size})")

        while not self._shutdown_event.is_set():
            try:
                # Collect batch of entries
                batch = []
                timeout = 1.0  # Wait up to 1 second for first item

                while len(batch) < batch_size and not self._shutdown_event.is_set():
                    try:
                        item = await asyncio.wait_for(self.embedding_queue.get(), timeout=timeout)
                        batch.append(item)
                        timeout = 0.1  # Short timeout for subsequent items
                    except asyncio.TimeoutError:
                        if batch:  # Process if we have items
                            break
                        continue  # Continue waiting for first item

                if batch and not self._shutdown_event.is_set():
                    await self._process_embedding_batch(batch)

            except Exception as e:
                plugin_logger.error(f"Error in embedding queue worker: {e}")
                await asyncio.sleep(1)  # Brief pause before retry

        plugin_logger.info("Vector embedding worker stopped")

    async def _process_embedding_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Process a batch of entries for embedding."""
        try:
            # Extract texts for batch embedding
            texts = [item['text_content'] for item in batch]

            # Generate embeddings
            embeddings = self.embedding_model.encode(
                texts,
                batch_size=len(texts),
                convert_to_numpy=True
            )

            # Normalize embeddings for cosine similarity
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

            # Store embeddings and mapping data
            await self._store_embeddings_batch(batch, embeddings)

            plugin_logger.debug(f"Processed embedding batch: {len(batch)} entries")

        except Exception as e:
            plugin_logger.error(f"Failed to process embedding batch: {e}")

            # Retry failed items
            for item in batch:
                item['retry_count'] += 1
                if item['retry_count'] < 3:  # Max 3 retries
                    await asyncio.sleep(2 ** item['retry_count'])  # Exponential backoff
                    await self._queue_entry_for_embedding(item)

    async def _store_embeddings_batch(self, batch: List[Dict[str, Any]], embeddings: np.ndarray) -> None:
        """Store embeddings and update mapping database."""
        if not self.queue_lock:
            raise RuntimeError("Queue lock not initialized")

        async with self.queue_lock:
            try:
                start_rowid = self.vector_index.ntotal

                # Add embeddings to FAISS index
                self.vector_index.add(embeddings)

                # Save FAISS index
                vectors_dir = self.repo_root / ".scribe_vectors"
                index_path = vectors_dir / f"{self.repo_slug}.faiss"
                faiss.write_index(self.vector_index, str(index_path))

                # Update mapping database
                with self._db_lock:
                    for i, item in enumerate(batch):
                        vector_rowid = start_rowid + i

                        self._db_conn.execute("""
                            INSERT OR REPLACE INTO vector_entries
                            (entry_id, project_slug, repo_slug, vector_rowid, text_content,
                             agent_name, timestamp_utc, metadata_json, embedding_model, vector_dimension)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item['entry_id'],
                            item['project_slug'],
                            self.repo_slug,
                            vector_rowid,
                            item['text_content'],
                            item['agent_name'],
                            item['timestamp_utc'],
                            item['metadata_json'],
                            item['embedding_model'],
                            item['vector_dimension']
                        ))

                    self._db_conn.commit()

                # Update metadata
                self.index_metadata.total_entries = self.vector_index.ntotal
                self.index_metadata.last_updated = utcnow()
                self.index_metadata.index_size_bytes = index_path.stat().st_size

                metadata_path = vectors_dir / f"{self.repo_slug}.meta.json"
                self._save_index_metadata(metadata_path)

                plugin_logger.debug(f"Stored {len(batch)} embeddings, total: {self.index_metadata.total_entries}")

            except Exception as e:
                plugin_logger.error(f"Failed to store embeddings batch: {e}")
                raise

    def _save_index_metadata(self, metadata_path: Path) -> None:
        """Save index metadata to JSON file."""
        metadata_dict = {
            'repo_slug': self.index_metadata.repo_slug,
            'dimension': self.index_metadata.dimension,
            'model': self.index_metadata.model,
            'scope': self.index_metadata.scope,
            'created_at': self.index_metadata.created_at.isoformat(),
            'backend': self.index_metadata.backend,
            'index_type': self.index_metadata.index_type,
            'total_entries': self.index_metadata.total_entries,
            'last_updated': self.index_metadata.last_updated.isoformat() if self.index_metadata.last_updated else None,
            'embedding_model_version': self.index_metadata.embedding_model_version
        }

        # Atomic write
        temp_path = metadata_path.with_suffix('.json.tmp')
        with open(temp_path, 'w') as f:
            json.dump(metadata_dict, f, indent=2)
        temp_path.rename(metadata_path)

    # Public API methods for MCP tools
    def get_index_status(self) -> Dict[str, Any]:
        """Get current index status and statistics."""
        if not self.initialized:
            return {
                'initialized': False,
                'enabled': self.enabled,
                'error': 'Plugin not initialized'
            }

        return {
            'initialized': True,
            'enabled': self.enabled,
            'repo_slug': self.repo_slug,
            'model': self.vector_config.model,
            'dimension': self.vector_config.dimension,
            'total_entries': self.index_metadata.total_entries if self.index_metadata else 0,
            'last_updated': self.index_metadata.last_updated.isoformat() if self.index_metadata and self.index_metadata.last_updated else None,
            'queue_depth': self.embedding_queue.qsize() if self.embedding_queue else 0,
            'queue_max': self.vector_config.queue_max,
            'gpu_enabled': self.vector_config.gpu,
            'faiss_available': FAISS_AVAILABLE
        }

    def search_similar(self, query: str, k: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for similar entries using vector similarity."""
        if not self.initialized or not self.vector_index or not self.embedding_model:
            return []

        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])
            query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)

            total = int(self.vector_index.ntotal)
            if total <= 0:
                return []

            def _search_with_k(search_k: int) -> List[Dict[str, Any]]:
                distances, rowids = self.vector_index.search(query_embedding, search_k)
                results: List[Dict[str, Any]] = []
                with self._db_lock:
                    for i, rowid in enumerate(rowids[0]):
                        distance = float(distances[0][i])
                        cursor = self._db_conn.execute("""
                            SELECT entry_id, project_slug, text_content, agent_name,
                                   timestamp_utc, metadata_json
                            FROM vector_entries
                            WHERE vector_rowid = ? AND repo_slug = ?
                        """, (int(rowid), self.repo_slug))
                        row = cursor.fetchone()
                        if not row:
                            continue
                        if filters and not self._apply_filters(row, filters):
                            continue
                        results.append({
                            'entry_id': row['entry_id'],
                            'project_slug': row['project_slug'],
                            'text_content': row['text_content'],
                            'agent_name': row['agent_name'],
                            'timestamp_utc': row['timestamp_utc'],
                            'metadata_json': row['metadata_json'],
                            'similarity_score': distance,
                            'vector_rowid': int(rowid)
                        })
                return results

            # Default behavior: no filters, standard top-k
            if not filters:
                search_k = min(max(1, int(k)), total)
                return _search_with_k(search_k)

            # Filtered search: overfetch to avoid starving filtered results
            target_k = max(1, int(k))
            search_k = min(total, max(target_k, 50))
            while True:
                results = _search_with_k(search_k)
                if len(results) >= target_k or search_k >= total:
                    return results[:target_k]
                search_k = min(total, max(search_k * 2, search_k + 50))

        except Exception as e:
            plugin_logger.error(f"Vector search failed: {e}")
            return []

    def retrieve_by_uuid(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve entry by UUID."""
        if not self.initialized:
            return None

        try:
            with self._db_lock:
                cursor = self._db_conn.execute("""
                    SELECT entry_id, project_slug, text_content, agent_name,
                           timestamp_utc, metadata_json, vector_rowid
                    FROM vector_entries
                    WHERE entry_id = ? AND repo_slug = ?
                """, (entry_id, self.repo_slug))

                row = cursor.fetchone()
                if row:
                    return {
                        'entry_id': row['entry_id'],
                        'project_slug': row['project_slug'],
                        'text_content': row['text_content'],
                        'agent_name': row['agent_name'],
                        'timestamp_utc': row['timestamp_utc'],
                        'metadata_json': row['metadata_json'],
                        'vector_rowid': row['vector_rowid']
                    }

            return None

        except Exception as e:
            plugin_logger.error(f"Failed to retrieve entry by UUID: {e}")
            return None

    def _apply_filters(self, row: sqlite3.Row, filters: Dict[str, Any]) -> bool:
        """Apply filters to search results."""
        try:
            # Project filter
            if 'project_slugs' in filters:
                if row['project_slug'] not in set(filters['project_slugs']):
                    return False
            elif 'project_slug_prefix' in filters:
                if not row['project_slug'].startswith(filters['project_slug_prefix']):
                    return False
            elif 'project_slug' in filters:
                if row['project_slug'] != filters['project_slug']:
                    return False

            meta = {}
            needs_meta = any(key in filters for key in ('content_type', 'doc_type', 'file_path'))
            metadata_json = None
            if needs_meta:
                try:
                    metadata_json = row['metadata_json']
                except Exception:
                    metadata_json = None
                if metadata_json:
                    try:
                        meta = json.loads(metadata_json)
                    except (TypeError, json.JSONDecodeError):
                        meta = {}

            # Time range filter
            if 'time_range' in filters:
                time_range = filters['time_range']
                if isinstance(time_range, dict):
                    start = time_range.get('start')
                    end = time_range.get('end')

                    timestamp = datetime.fromisoformat(row['timestamp_utc'].replace(' UTC', ''))

                    if start and timestamp < datetime.fromisoformat(start):
                        return False
                    if end and timestamp > datetime.fromisoformat(end):
                        return False

            # Agent filter
            if 'agent_name' in filters:
                if row['agent_name'] != filters['agent_name']:
                    return False

            # Content type filter (log/doc)
            if 'content_type' in filters:
                if meta.get('content_type') != filters['content_type']:
                    return False

            if 'doc_type' in filters:
                if meta.get('doc_type') != filters['doc_type']:
                    return False

            if 'file_path' in filters:
                if meta.get('file_path') != filters['file_path']:
                    return False

            return True

        except Exception as e:
            plugin_logger.warning(f"Filter application failed: {e}")
            return False  # Default to exclude if filtering fails

    def rebuild_index(self) -> Dict[str, Any]:
        """Rebuild the entire vector index from scratch."""
        if not self.initialized or not self.enabled:
            raise RuntimeError("Vector indexer not initialized or enabled")

        plugin_logger.info("Starting vector index rebuild")
        rebuild_start = time.time()

        try:
            # Stop background processing
            self._stop_background_processing()

            # Get old statistics
            old_entries = self.index_metadata.total_entries if self.index_metadata else 0

            # Clear existing index
            self.vector_index.reset()
            if self._db_conn:
                with self._db_lock:
                    self._db_conn.execute("DELETE FROM vector_entries WHERE repo_slug = ?", (self.repo_slug,))
                    self._db_conn.commit()

            # Reset metadata
            if self.index_metadata:
                self.index_metadata.total_entries = 0
                self.index_metadata.last_updated = utcnow()

            # Restart background processing
            self._start_background_processing()

            rebuild_time = time.time() - rebuild_start

            plugin_logger.info(f"Vector index rebuilt successfully in {rebuild_time:.2f}s")

            return {
                "success": True,
                "rebuild_time_seconds": round(rebuild_time, 2),
                "old_entries_count": old_entries,
                "new_entries_count": 0,
                "message": "Index cleared and ready for new entries"
            }

        except Exception as e:
            plugin_logger.error(f"Failed to rebuild vector index: {e}")
            raise RuntimeError(f"Vector index rebuild failed: {str(e)}") from e

    def _stop_background_processing(self) -> None:
        """Stop background queue processing."""
        if not self.queue_worker_task:
            plugin_logger.info("Background processing stopped")
            return

        task = self.queue_worker_task
        if task.done():
            self.queue_worker_task = None
            plugin_logger.info("Background processing stopped")
            return

        import asyncio
        import concurrent.futures

        if self._owns_loop and self._loop and not self._loop.is_closed():
            def _cancel() -> None:
                if not task.done():
                    task.cancel()

            self._loop.call_soon_threadsafe(_cancel)

            async def _await_task() -> None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            try:
                future = asyncio.run_coroutine_threadsafe(_await_task(), self._loop)
                future.result(timeout=5)
            except (concurrent.futures.TimeoutError, RuntimeError, asyncio.CancelledError):
                pass
            except Exception:
                pass
        else:
            task.cancel()
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(task)
            except (asyncio.CancelledError, RuntimeError):
                pass

        self.queue_worker_task = None
        plugin_logger.info("Background processing stopped")

    def _start_background_processing(self) -> None:
        """Start background queue processing if not already running."""
        if self.queue_worker_task and not self.queue_worker_task.done():
            return
        if self._owns_loop and self._loop:
            def _start() -> None:
                if not self.queue_worker_task or self.queue_worker_task.done():
                    self.queue_worker_task = self._loop.create_task(self._queue_worker())
            self._loop.call_soon_threadsafe(_start)
            plugin_logger.info("Background processing started (dedicated loop)")
            return
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            self.queue_worker_task = loop.create_task(self._queue_worker())
            plugin_logger.info("Background processing started")
        except RuntimeError:
            plugin_logger.warning("No event loop available, background processing disabled")
