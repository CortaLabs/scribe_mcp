#!/usr/bin/env python3
"""Reindex Scribe-managed docs and logs into the vector indexer.

This script queues entries for embedding in the background (non-blocking).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from scribe_mcp.config.paths import repo_root


ROOT_DIR = repo_root()
REPO_ROOT = ROOT_DIR

def _apply_safe_env() -> None:
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["SCRIBE_VECTOR_BATCH_SIZE"] = "8"
    os.environ["SCRIBE_VECTOR_QUEUE_MAX"] = "256"
    os.environ["SCRIBE_VECTOR_MODEL_DEVICE"] = "cpu"


SAFE_MODE = "--safe" in sys.argv or os.environ.get("SCRIBE_VECTOR_SAFE_MODE") == "1"
if SAFE_MODE:
    _apply_safe_env()

# Ensure Scribe sees this repo as its root and keeps state under the repo
# instead of ~/.scribe when the CLI is used.
os.environ.setdefault("SCRIBE_ROOT", str(REPO_ROOT))
os.environ.setdefault("SCRIBE_STATE_PATH", str(REPO_ROOT / "tmp_state_cli.json"))

from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.config.log_config import load_log_config, resolve_log_path
from scribe_mcp.plugins.registry import get_plugin_registry, initialize_plugins
from scribe_mcp.tools.manage_docs import _index_doc_for_vector
from scribe_mcp.utils.logs import parse_log_line, read_all_lines


SKIP_DOC_FILENAMES = {
    "PROGRESS_LOG.md",
    "DOC_LOG.md",
    "SECURITY_LOG.md",
    "BUG_LOG.md",
    "GLOBAL_PROGRESS_LOG.md",
}


def _iter_doc_roots(repo_root: Path, config_dev_plans: Path) -> List[Path]:
    candidates = [
        repo_root / ".scribe" / "docs" / "dev_plans",
        config_dev_plans,
    ]
    roots = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_dir():
            roots.append(resolved)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        unique.append(root)
    return unique


def _iter_project_dirs(root: Path) -> Iterable[Path]:
    for project_dir in sorted(root.iterdir()):
        if project_dir.is_dir():
            yield project_dir


def _iter_doc_files(project_dir: Path) -> Iterable[Path]:
    for path in sorted(project_dir.rglob("*.md")):
        if path.name in SKIP_DOC_FILENAMES or path.name.endswith("_LOG.md"):
            continue
        yield path


def _load_registry_docs(repo_root: Path) -> Dict[str, Dict[str, str]]:
    state_path = repo_root / ".scribe" / "state.json"
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    projects = data.get("projects", {})
    registry_docs: Dict[str, Dict[str, str]] = {}
    if isinstance(projects, dict):
        for project_name, project_data in projects.items():
            if not isinstance(project_data, dict):
                continue
            docs = project_data.get("docs")
            if isinstance(docs, dict) and docs:
                registry_docs[str(project_name)] = {
                    str(doc_key): str(path) for doc_key, path in docs.items()
                }
    return registry_docs


def _is_rotated_log_filename(name: str) -> bool:
    upper = name.upper()
    for base in SKIP_DOC_FILENAMES:
        if upper.startswith(f"{base.upper()}."):
            return True
    return False


def _should_skip_doc_path(doc_key: str, path: Path) -> bool:
    upper = path.name.upper()
    if doc_key.lower() in {"progress_log", "doc_log", "security_log", "bug_log"}:
        return True
    if path.name in SKIP_DOC_FILENAMES:
        return True
    if upper.endswith("_LOG.MD"):
        return True
    if _is_rotated_log_filename(path.name):
        return True
    return False


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _entry_id_from_log(project_slug: str, parsed: dict) -> str:
    raw_line = parsed.get("raw_line", "")
    payload = f"{project_slug}|{parsed.get('ts','')}|{parsed.get('agent','')}|{parsed.get('message','')}|{raw_line}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _project_filter_match(
    project_name: str,
    project_slug: str,
    project_exact: Optional[str],
    project_prefix: Optional[str],
) -> bool:
    if project_exact and project_name != project_exact and project_slug != project_exact:
        return False
    if project_prefix and not project_slug.startswith(project_prefix):
        return False
    return True


def _get_vector_indexer():
    registry = get_plugin_registry()
    for plugin in registry.plugins.values():
        if getattr(plugin, "name", None) == "vector_indexer" and getattr(plugin, "initialized", False):
            return plugin
    return None


def _get_mapping_count(db_path: Path, repo_slug: str) -> int:
    attempts = 5
    for _ in range(attempts):
        try:
            conn = sqlite3.connect(db_path, timeout=2.0)
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM vector_entries WHERE repo_slug = ?",
                (repo_slug,),
            )
            count = cur.fetchone()[0] or 0
            conn.close()
            return int(count)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                time.sleep(0.1)
                continue
            return 0
        except Exception:
            return 0
    return 0


def _wait_for_embedding_drain(
    *,
    vector_indexer,
    baseline_count: int,
    expected_new: int,
    timeout: Optional[float],
    poll_seconds: float,
) -> Tuple[bool, int]:
    if not vector_indexer:
        return False, baseline_count
    mapping_path = vector_indexer.mapping_db_path
    repo_slug = vector_indexer.repo_slug
    if not mapping_path or not repo_slug:
        return False, baseline_count

    target = baseline_count + expected_new
    start = time.time()
    last_report = start
    while True:
        current = _get_mapping_count(mapping_path, repo_slug)
        meta_entries = 0
        if getattr(vector_indexer, "index_metadata", None):
            try:
                meta_entries = int(vector_indexer.index_metadata.total_entries or 0)
            except Exception:
                meta_entries = 0
        effective = max(current, meta_entries)
        queue_depth = None
        if getattr(vector_indexer, "embedding_queue", None):
            try:
                queue_depth = vector_indexer.embedding_queue.qsize()
            except Exception:
                queue_depth = None
        now = time.time()
        if effective >= target:
            return True, effective
        if timeout is not None and (now - start) >= timeout:
            return False, effective
        if now - last_report >= 5:
            pending = max(0, target - effective)
            print(
                f"[drain] indexed={effective} pending≈{pending} target={target} "
                f"queue_depth={queue_depth} meta_entries={meta_entries}"
            )
            last_report = now
        time.sleep(poll_seconds)


async def _reindex_docs(
    *,
    repo_root: Path,
    config_dev_plans: Path,
    project_exact: Optional[str],
    project_prefix: Optional[str],
    vector_indexer,
    wait_for_queue: bool,
    queue_timeout: Optional[float],
    progress_every: int,
) -> tuple[int, int]:
    indexed = 0
    skipped = 0
    last_report = time.time()
    start_time = last_report
    registry_docs = _load_registry_docs(repo_root)
    if not registry_docs:
        print("No registry-managed docs found in .scribe/state.json; skipping doc indexing.")
        return indexed, skipped
    for project_name, docs in registry_docs.items():
        project_slug = project_name.lower().replace(" ", "-")
        if not _project_filter_match(project_name, project_slug, project_exact, project_prefix):
            continue
        for doc_key, raw_path in docs.items():
            path = Path(raw_path)
            if not path.is_absolute():
                path = (repo_root / path).resolve()
            if not path.exists():
                skipped += 1
                continue
            if _should_skip_doc_path(doc_key, path):
                skipped += 1
                continue
            try:
                content = await asyncio.to_thread(path.read_bytes)
            except OSError:
                skipped += 1
                continue
            after_hash = _hash_bytes(content)
            await _index_doc_for_vector(
                project={"name": project_name, "root": str(repo_root)},
                doc=doc_key,
                change_path=path,
                after_hash=after_hash,
                agent_id="reindex_vector",
                metadata=None,
                wait_for_queue=wait_for_queue,
                queue_timeout=queue_timeout,
            )
            indexed += 1
            if progress_every and indexed % progress_every == 0:
                queue_depth = vector_indexer.embedding_queue.qsize() if vector_indexer.embedding_queue else None
                elapsed = max(0.001, time.time() - start_time)
                rate = indexed / elapsed
                print(f"[docs] queued={indexed} skipped={skipped} queue_depth={queue_depth} rate={rate:.1f}/s")
                last_report = time.time()
            elif progress_every and (time.time() - last_report) > 30:
                queue_depth = vector_indexer.embedding_queue.qsize() if vector_indexer.embedding_queue else None
                elapsed = max(0.001, time.time() - start_time)
                rate = indexed / elapsed
                print(f"[docs] queued={indexed} skipped={skipped} queue_depth={queue_depth} rate={rate:.1f}/s")
                last_report = time.time()
    return indexed, skipped


async def _reindex_logs(
    *,
    repo_root: Path,
    config_dev_plans: Path,
    project_exact: Optional[str],
    project_prefix: Optional[str],
    vector_indexer,
    wait_for_queue: bool,
    queue_timeout: Optional[float],
    progress_every: int,
) -> tuple[int, int]:
    indexed = 0
    skipped = 0
    last_report = time.time()
    start_time = last_report
    log_config = load_log_config()
    log_types = [name for name in log_config.keys() if name != "global"]
    for doc_root in _iter_doc_roots(repo_root, config_dev_plans):
        for project_dir in _iter_project_dirs(doc_root):
            project_name = project_dir.name
            project_slug = project_name.lower().replace(" ", "-")
            if not _project_filter_match(project_name, project_slug, project_exact, project_prefix):
                continue
            project_ctx = {
                "name": project_name,
                "root": str(repo_root),
                "docs_dir": str(project_dir),
                "progress_log": str(project_dir / "PROGRESS_LOG.md"),
            }
            for log_type in log_types:
                definition = log_config.get(log_type, {})
                log_path = resolve_log_path(project_ctx, definition)
                if not log_path.exists():
                    continue
                lines = await read_all_lines(log_path)
                for line in lines:
                    parsed = parse_log_line(line)
                    if not parsed:
                        skipped += 1
                        continue
                    meta = dict(parsed.get("meta") or {})
                    meta.setdefault("log_type", log_type)
                    meta.setdefault("content_type", "log")
                    meta.setdefault("file_path", str(log_path))
                    entry_id = _entry_id_from_log(project_slug, parsed)
                    entry = {
                        "entry_id": entry_id,
                        "project_name": parsed.get("project", project_name),
                        "message": parsed.get("message", ""),
                        "agent": parsed.get("agent", ""),
                        "timestamp": parsed.get("ts", ""),
                        "meta": meta,
                    }
                    if wait_for_queue:
                        vector_indexer.enqueue_entry(entry, wait=True, timeout=queue_timeout)
                    else:
                        vector_indexer.post_append(entry)
                    indexed += 1
                    if progress_every and indexed % progress_every == 0:
                        queue_depth = vector_indexer.embedding_queue.qsize() if vector_indexer.embedding_queue else None
                        elapsed = max(0.001, time.time() - start_time)
                        rate = indexed / elapsed
                        print(f"[logs] queued={indexed} skipped={skipped} queue_depth={queue_depth} rate={rate:.1f}/s")
                        last_report = time.time()
                    elif progress_every and (time.time() - last_report) > 30:
                        queue_depth = vector_indexer.embedding_queue.qsize() if vector_indexer.embedding_queue else None
                        elapsed = max(0.001, time.time() - start_time)
                        rate = indexed / elapsed
                        print(f"[logs] queued={indexed} skipped={skipped} queue_depth={queue_depth} rate={rate:.1f}/s")
                        last_report = time.time()
    return indexed, skipped


async def _run_reindex(
    repo_root: Path,
    *,
    include_docs: bool,
    include_logs: bool,
    project_exact: Optional[str],
    project_prefix: Optional[str],
    wait_for_queue: bool,
    queue_timeout: Optional[float],
    progress_every: int,
    rebuild: bool,
    wait_for_drain: bool,
    drain_timeout: Optional[float],
    drain_poll: float,
) -> int:
    config = RepoDiscovery.load_config(repo_root)
    if not (config.plugin_config or {}).get("enabled", False):
        print("Plugin loading is disabled (plugin_config.enabled=false).")
        return 1

    initialize_plugins(config)
    vector_indexer = _get_vector_indexer()
    if not vector_indexer:
        print("Vector indexer plugin not available or not initialized.")
        return 1
    baseline_count = 0
    if wait_for_drain:
        mapping_path = vector_indexer.mapping_db_path
        repo_slug = vector_indexer.repo_slug
        if mapping_path and repo_slug:
            baseline_count = _get_mapping_count(mapping_path, repo_slug)
    if rebuild:
        try:
            rebuild_result = vector_indexer.rebuild_index()
            message = rebuild_result.get("message") if isinstance(rebuild_result, dict) else None
            if message:
                print(message)
        except Exception as exc:
            print(f"Failed to rebuild vector index: {exc}")
            return 1
        baseline_count = 0

    docs_enabled = bool(config.vector_index_docs)
    logs_enabled = bool(config.vector_index_logs)

    if include_docs and not docs_enabled:
        print("Doc vector indexing is disabled (vector_index_docs=false). Skipping docs.")
        include_docs = False
    if include_logs and not logs_enabled:
        print("Log vector indexing is disabled (vector_index_logs=false). Skipping logs.")
        include_logs = False
    if not include_docs and not include_logs:
        print("Nothing to index (both docs/logs disabled or filtered).")
        return 1

    docs_indexed = docs_skipped = 0
    logs_indexed = logs_skipped = 0
    if include_docs:
        docs_indexed, docs_skipped = await _reindex_docs(
            repo_root=repo_root,
            config_dev_plans=config.dev_plans_dir,
            project_exact=project_exact,
            project_prefix=project_prefix,
            vector_indexer=vector_indexer,
            wait_for_queue=wait_for_queue,
            queue_timeout=queue_timeout,
            progress_every=progress_every,
        )
    if include_logs:
        logs_indexed, logs_skipped = await _reindex_logs(
            repo_root=repo_root,
            config_dev_plans=config.dev_plans_dir,
            project_exact=project_exact,
            project_prefix=project_prefix,
            vector_indexer=vector_indexer,
            wait_for_queue=wait_for_queue,
            queue_timeout=queue_timeout,
            progress_every=progress_every,
        )

    print(
        "Reindex queued.",
        f"Docs indexed={docs_indexed}, skipped={docs_skipped}.",
        f"Logs indexed={logs_indexed}, skipped={logs_skipped}.",
    )
    if wait_for_drain:
        expected_new = docs_indexed + logs_indexed
        ok, current = _wait_for_embedding_drain(
            vector_indexer=vector_indexer,
            baseline_count=baseline_count,
            expected_new=expected_new,
            timeout=drain_timeout,
            poll_seconds=drain_poll,
        )
        if ok:
            print(f"[drain] complete: indexed={current}")
        else:
            print(f"[drain] timeout: indexed={current}")
    return 0


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Queue Scribe-managed docs/logs for vector reindexing."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to use (defaults to current scribe_mcp root).",
    )
    parser.add_argument("--docs", action="store_true", help="Reindex docs only.")
    parser.add_argument("--logs", action="store_true", help="Reindex logs only.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Reindex docs and logs (default when no scope flags are provided).",
    )
    parser.add_argument(
        "--safe",
        action="store_true",
        help="Enable safe mode (single-threaded embeddings, smaller batch/queue).",
    )
    parser.add_argument("--project", help="Restrict to a single dev_plan project name/slug.")
    parser.add_argument("--project-prefix", help="Restrict to dev_plan projects matching prefix.")
    parser.add_argument(
        "--wait-for-queue",
        action="store_true",
        help="Block reindex until queue has capacity instead of dropping entries.",
    )
    parser.add_argument(
        "--queue-timeout",
        type=float,
        default=None,
        help="Max seconds to wait for queue capacity per entry (default: no timeout).",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print progress every N queued entries (default: 500).",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear the vector index before reindexing (destructive).",
    )
    parser.add_argument(
        "--wait-for-drain",
        action="store_true",
        help="Wait for embeddings to finish writing before exiting.",
    )
    parser.add_argument(
        "--drain-timeout",
        type=float,
        default=300.0,
        help="Max seconds to wait for embedding drain (default: 300).",
    )
    parser.add_argument(
        "--drain-poll",
        type=float,
        default=0.5,
        help="Seconds between drain checks (default: 0.5).",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    if args.safe and not SAFE_MODE:
        _apply_safe_env()
        print("Safe mode enabled: forcing single-threaded embeddings with small batch/queue.")
    repo_root = args.repo_root.resolve()
    include_docs = args.docs
    include_logs = args.logs
    if not include_docs and not include_logs:
        include_docs = True
        include_logs = True
    if args.all:
        include_docs = True
        include_logs = True
    project_prefix = args.project_prefix
    if project_prefix:
        project_prefix = project_prefix.lower().replace(" ", "-")
    return asyncio.run(
        _run_reindex(
            repo_root,
            include_docs=include_docs,
            include_logs=include_logs,
            project_exact=args.project,
            project_prefix=project_prefix,
            wait_for_queue=args.wait_for_queue,
            queue_timeout=args.queue_timeout,
            progress_every=args.progress_every,
            rebuild=args.rebuild,
            wait_for_drain=args.wait_for_drain,
            drain_timeout=args.drain_timeout,
            drain_poll=args.drain_poll,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
