#!/usr/bin/env python3
"""Health check for vector indexing configuration and artifacts."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

from scribe_mcp.config.paths import repo_root


ROOT_DIR = repo_root()
REPO_ROOT = ROOT_DIR

from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.config.vector_config import load_vector_config
from scribe_mcp.plugins.registry import get_plugin_registry, initialize_plugins


def _read_raw_config(repo_root: Path) -> Optional[str]:
    path = repo_root / ".scribe" / "config" / "scribe.yaml"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _count_vector_entries(db_path: Path) -> Optional[int]:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("select count(*) from vector_entries")
    count = cur.fetchone()[0]
    conn.close()
    return count


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check vector index configuration, plugin status, and artifacts."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to use (defaults to current scribe_mcp root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()

    config = RepoDiscovery.load_config(repo_root)
    vector_config = load_vector_config(repo_root)

    print("repo_root:", repo_root)
    print("repo_slug:", config.repo_slug)
    print("plugin_config.enabled:", bool((config.plugin_config or {}).get("enabled", False)))
    print("vector_index_docs:", bool(config.vector_index_docs))
    print("vector_index_logs:", bool(config.vector_index_logs))
    print("vector.json enabled:", bool(vector_config.enabled))

    raw_config = _read_raw_config(repo_root)
    if raw_config and "plugin_config:" in raw_config and not (config.plugin_config or {}):
        print("warning: plugin_config not detected at top-level; check YAML indentation.")

    initialize_plugins(config)
    registry = get_plugin_registry(repo_root)
    plugin = registry.plugins.get("vector_indexer")
    if not plugin:
        print("vector_indexer: NOT LOADED")
    else:
        print("vector_indexer: LOADED")
        print("vector_indexer.initialized:", getattr(plugin, "initialized", None))
        print("vector_indexer.enabled:", getattr(plugin, "enabled", None))
        queue_depth = plugin.embedding_queue.qsize() if plugin.embedding_queue else None
        print("vector_indexer.queue_depth:", queue_depth)

    vectors_dir = repo_root / ".scribe_vectors"
    meta_path = vectors_dir / f"{config.repo_slug}.meta.json"
    faiss_path = vectors_dir / f"{config.repo_slug}.faiss"
    mapping_path = vectors_dir / "mapping.sqlite"

    print("faiss_index_exists:", faiss_path.exists())
    print("meta_exists:", meta_path.exists())
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print("meta.total_entries:", meta.get("total_entries"))
        print("meta.last_updated:", meta.get("last_updated"))
    mapping_count = _count_vector_entries(mapping_path)
    print("mapping.sqlite.exists:", mapping_path.exists())
    if mapping_count is not None:
        print("mapping.total_entries:", mapping_count)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
