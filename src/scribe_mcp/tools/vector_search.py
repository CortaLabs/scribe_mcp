"""Vector search MCP tool for Scribe entries.

Provides semantic search capabilities using the VectorIndexer plugin.
Tools are only registered when the VectorIndexer plugin is active.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.agent_project_utils import get_agent_project_data
import logging

# For backward compatibility with tests
server = server_module


def _get_vector_indexer():
    """Get the vector indexer plugin instance."""
    try:
        from scribe_mcp.plugins.registry import get_plugin_registry
        registry = get_plugin_registry()

        # Find the vector indexer plugin
        for plugin in registry.plugins.values():
            if plugin.name == "vector_indexer" and plugin.initialized:
                return plugin

        return None
    except Exception:
        return None


def register_vector_tools():
    """Register vector search tools if VectorIndexer plugin is active.

    This function should be called after plugin loading is complete.
    Returns True if tools were registered, False otherwise.
    """

    try:
        # Check if vector indexer is available and initialized
        indexer = _get_vector_indexer()
        if indexer and getattr(indexer, 'initialized', False):
            # Register the tools
            app.tool()(vector_search)
            app.tool()(semantic_search)
            app.tool()(retrieve_by_uuid)
            app.tool()(vector_index_status)
            app.tool()(rebuild_vector_index)
            logging.debug("Vector tools registered successfully")
            return True
        else:
            logging.debug("Vector tools not registered: vector indexer plugin not available or not initialized")
            return False
    except Exception as e:
        # Silently fail - tools just won't be available
        logging.warning(f"Vector tools not registered due to exception: {e}")
        return False


async def vector_search(
    query: str,
    k: int = 10,
    project_slug: Optional[str] = None,
    project_slugs: Optional[List[str]] = None,
    project_slug_prefix: Optional[str] = None,
    agent_name: Optional[str] = None,
    content_type: Optional[str] = None,
    doc_type: Optional[str] = None,
    file_path: Optional[str] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    min_similarity: Optional[float] = None
) -> Dict[str, Any]:
    """Search for semantically similar log entries using vector embeddings.

    Args:
        query: Search query text
        k: Maximum number of results to return (default: 10)
        project_slug: Filter by project slug (optional)
        agent_name: Filter by agent name (optional)
        time_start: Start of time range in ISO format (optional)
        time_end: End of time range in ISO format (optional)
        min_similarity: Minimum similarity score threshold (0-1, optional)

    Returns:
        Dictionary with search results and metadata
    """
    state_snapshot = await server_module.state_manager.record_tool("vector_search")

    # Get vector indexer plugin
    vector_indexer = _get_vector_indexer()
    if not vector_indexer:
        return {
            "ok": False,
            "error": "Vector indexing plugin not available",
            "suggestion": "Ensure vector indexing is enabled and dependencies are installed"
        }

    if not vector_indexer.initialized:
        return {
            "ok": False,
            "error": "Vector indexing not initialized",
            "suggestion": "Check plugin logs for initialization errors"
        }

    try:
        # Build filters
        filters = {}
        if project_slugs:
            normalized = []
            for slug in project_slugs:
                if not slug:
                    continue
                normalized.append(str(slug).lower().replace(" ", "-"))
            if normalized:
                filters["project_slugs"] = normalized
        elif project_slug_prefix:
            filters["project_slug_prefix"] = str(project_slug_prefix).lower().replace(" ", "-")
        elif project_slug:
            filters["project_slug"] = project_slug.lower().replace(" ", "-")
        if agent_name:
            filters["agent_name"] = agent_name
        if content_type:
            filters["content_type"] = content_type
        if doc_type:
            filters["doc_type"] = doc_type
        if file_path:
            filters["file_path"] = file_path
        if time_start or time_end:
            filters["time_range"] = {}
            if time_start:
                filters["time_range"]["start"] = time_start
            if time_end:
                filters["time_range"]["end"] = time_end

        # Perform search
        results = vector_indexer.search_similar(query, k, filters)

        # Apply similarity threshold if specified
        if min_similarity is not None:
            results = [r for r in results if r["similarity_score"] >= min_similarity]

        # Sort by similarity score (descending)
        results.sort(key=lambda x: x["similarity_score"], reverse=True)

        return {
            "ok": True,
            "query": query,
            "results_count": len(results),
            "results": results,
            "filters_applied": filters,
            "max_results_requested": k,
            "similarity_threshold": min_similarity
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"Vector search failed: {str(e)}",
            "suggestion": "Check query format and try again"
        }


async def retrieve_by_uuid(
    entry_id: str
) -> Dict[str, Any]:
    """Retrieve a specific log entry by its UUID.

    Args:
        entry_id: The UUID of the entry to retrieve

    Returns:
        Dictionary with entry data or error information
    """
    state_snapshot = await server_module.state_manager.record_tool("retrieve_by_uuid")

    # Get vector indexer plugin
    vector_indexer = _get_vector_indexer()
    if not vector_indexer:
        return {
            "ok": False,
            "error": "Vector indexing plugin not available",
            "suggestion": "Ensure vector indexing is enabled and dependencies are installed"
        }

    if not vector_indexer.initialized:
        return {
            "ok": False,
            "error": "Vector indexing not initialized",
            "suggestion": "Check plugin logs for initialization errors"
        }

    try:
        # Retrieve entry
        result = vector_indexer.retrieve_by_uuid(entry_id)

        if result:
            return {
                "ok": True,
                "entry": result
            }
        else:
            return {
                "ok": False,
                "error": f"Entry with ID '{entry_id}' not found",
                "suggestion": "Verify the entry ID is correct and exists in the current repository"
            }

    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to retrieve entry: {str(e)}",
            "suggestion": "Check entry ID format and try again"
        }


async def vector_index_status() -> Dict[str, Any]:
    """Get the current status and statistics of the vector index.

    Returns:
        Dictionary with index status, statistics, and health information
    """
    state_snapshot = await server_module.state_manager.record_tool("vector_index_status")

    # Get vector indexer plugin
    vector_indexer = _get_vector_indexer()
    if not vector_indexer:
        return {
            "ok": False,
            "error": "Vector indexing plugin not available",
            "suggestion": "Ensure vector indexing is enabled and dependencies are installed"
        }

    try:
        # Get status from plugin
        status = vector_indexer.get_index_status()

        # Add additional context
        status.update({
            "tool_name": "vector_index_status",
            "repository_root": str(vector_indexer.repo_root) if vector_indexer.repo_root else None,
            "index_files_exist": _check_index_files(vector_indexer)
        })

        return {
            "ok": True,
            "status": status
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to get vector index status: {str(e)}",
            "suggestion": "Check plugin logs and configuration"
        }


def _check_index_files(vector_indexer) -> Dict[str, bool]:
    """Check if index files exist and are accessible."""
    if not vector_indexer.repo_root:
        return {"faiss_index": False, "metadata": False, "mapping_db": False}

    vectors_dir = vector_indexer.repo_root / ".scribe_vectors"
    repo_slug = getattr(vector_indexer, 'repo_slug', 'unknown')

    return {
        "faiss_index": (vectors_dir / f"{repo_slug}.faiss").exists(),
        "metadata": (vectors_dir / f"{repo_slug}.meta.json").exists(),
        "mapping_db": (vectors_dir / "mapping.sqlite").exists()
    }


def rebuild_vector_index() -> Dict[str, Any]:
    """
    Rebuild the entire vector index from scratch.

    This function will:
    1. Backup the existing index (if it exists)
    2. Delete the current index files
    3. Re-initialize empty index structures
    4. Optionally, re-index existing log entries (if implemented)

    Returns:
        Dict with success status, backup information, and new index status
    """
    vector_indexer = get_vector_indexer()
    if not vector_indexer:
        return {
            "ok": False,
            "error": "Vector indexing plugin not available",
            "suggestion": "Ensure vector indexing is enabled and dependencies are installed"
        }

    try:
        # Get current status before rebuilding
        old_status = vector_indexer.get_index_status()
        backup_info = {}

        # Create backup of existing index if it exists
        if old_status.get("total_entries", 0) > 0:
            backup_info = _backup_existing_index(vector_indexer)

        # Perform the rebuild
        rebuild_result = vector_indexer.rebuild_index()

        # Get new status
        new_status = vector_indexer.get_index_status()

        return {
            "ok": True,
            "message": "Vector index rebuilt successfully",
            "backup_info": backup_info,
            "old_status": old_status,
            "new_status": new_status,
            "rebuild_details": rebuild_result
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to rebuild vector index: {str(e)}",
            "suggestion": "Check plugin logs, configuration, and available disk space"
        }


def _backup_existing_index(vector_indexer) -> Dict[str, Any]:
    """Create a backup of existing index files before rebuilding."""
    import shutil
    from datetime import datetime

    if not vector_indexer.repo_root:
        return {"backup_created": False, "reason": "No repository root available"}

    vectors_dir = vector_indexer.repo_root / ".scribe_vectors"
    repo_slug = getattr(vector_indexer, 'repo_slug', 'unknown')

    # Check if index files exist
    index_files = {
        "faiss_index": vectors_dir / f"{repo_slug}.faiss",
        "metadata": vectors_dir / f"{repo_slug}.meta.json",
        "mapping_db": vectors_dir / "mapping.sqlite"
    }

    existing_files = {name: path for name, path in index_files.items() if path.exists()}

    if not existing_files:
        return {"backup_created": False, "reason": "No existing index files found"}

    # Create backup directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = vectors_dir / "backups" / f"{repo_slug}_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backed_up_files = []
    total_size_bytes = 0

    try:
        for name, source_path in existing_files.items():
            backup_path = backup_dir / source_path.name
            shutil.copy2(source_path, backup_path)
            backed_up_files.append({
                "file": name,
                "source": str(source_path),
                "backup": str(backup_path),
                "size_bytes": backup_path.stat().st_size
            })
            total_size_bytes += backup_path.stat().st_size

        return {
            "backup_created": True,
            "backup_directory": str(backup_dir),
            "files_backed_up": backed_up_files,
            "total_size_bytes": total_size_bytes,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2)
        }

    except Exception as e:
        # Cleanup partial backup if it failed
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        return {
            "backup_created": False,
            "reason": f"Backup failed: {str(e)}",
            "attempted_directory": str(backup_dir)
        }


# Also add a semantic_search alias for better naming convention
async def semantic_search(
    query: str,
    k: int = 10,
    project_slug: Optional[str] = None,
    project_slugs: Optional[List[str]] = None,
    project_slug_prefix: Optional[str] = None,
    agent_name: Optional[str] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    min_similarity: Optional[float] = None
) -> Dict[str, Any]:
    """Alias for vector_search with more intuitive naming.

    Provides semantic search capabilities using vector embeddings.
    """
    return await vector_search(
        query=query,
        k=k,
        project_slug=project_slug,
        project_slugs=project_slugs,
        project_slug_prefix=project_slug_prefix,
        agent_name=agent_name,
        time_start=time_start,
        time_end=time_end,
        min_similarity=min_similarity
    )
