"""Migrate existing Scribe documents to a remote object store.

Usage::

    # Dry run (default) — preview what would be uploaded
    scribe-migrate-objects

    # Execute migration
    scribe-migrate-objects --confirm

    # Specific project only
    scribe-migrate-objects --project my_project --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

from scribe_mcp.config.settings import Settings
from scribe_mcp.object_store.keys import path_to_key, should_sync


async def _run(args: argparse.Namespace) -> int:
    settings = Settings.load()
    repo_root = settings.project_root

    if not getattr(settings, "object_store_url", None):
        print("ERROR: SCRIBE_OBJECT_STORE_URL is not set. Nothing to migrate to.")
        return 1

    from scribe_mcp.object_store import create_document_store
    from scribe_mcp.object_store.hybrid import HybridStore

    store = create_document_store(settings)
    if not isinstance(store, HybridStore):
        print("ERROR: Object store resolved to a local-only store. Set SCRIBE_OBJECT_STORE_URL.")
        return 1

    await store.setup()

    # Collect eligible files.
    scan_dirs: list[Path] = [
        repo_root / ".scribe" / "docs",
        repo_root / ".scribe" / "backups",
        repo_root / "docs" / "bugs",
    ]

    # Narrow to a specific project if requested.
    if args.project:
        scan_dirs = [repo_root / ".scribe" / "docs" / "dev_plans" / args.project]

    files: list[Path] = []
    for d in scan_dirs:
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and should_sync(p, repo_root):
                files.append(p)

    if not files:
        print("No eligible files found to migrate.")
        await store.close()
        return 0

    print(f"Found {len(files)} file(s) eligible for migration.\n")

    # Try bulk check for CortaStore.
    keys = [path_to_key(f, repo_root) for f in files]
    missing_keys: set[str] | None = None
    try:
        missing_list = await store._remote.bulk_check(keys)
        missing_keys = set(missing_list)
        print(f"Bulk check: {len(missing_keys)} missing on remote, {len(keys) - len(missing_keys)} already exist.\n")
    except Exception:
        pass  # Fall through to per-file check.

    uploaded = 0
    skipped = 0
    already_exists = 0
    failed = 0

    for fp in files:
        key = path_to_key(fp, repo_root)
        content = fp.read_text(encoding="utf-8")

        # Skip if already on remote (and we know).
        if missing_keys is not None and key not in missing_keys:
            already_exists += 1
            if not args.quiet:
                print(f"  SKIP (exists) {key}")
            continue

        if args.dry_run:
            skipped += 1
            size_kb = len(content.encode()) / 1024
            print(f"  WOULD UPLOAD  {key}  ({size_kb:.1f} KB)")
            continue

        try:
            await store._remote.put(key, content)
            uploaded += 1
            if not args.quiet:
                print(f"  UPLOADED      {key}")
        except Exception as exc:
            failed += 1
            print(f"  FAILED        {key}: {exc}")

    print(f"\n{'DRY RUN ' if args.dry_run else ''}Summary:")
    print(f"  Uploaded:       {uploaded}")
    print(f"  Already exists: {already_exists}")
    print(f"  Skipped:        {skipped}")
    print(f"  Failed:         {failed}")

    await store.close()
    return 1 if failed > 0 else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate Scribe documents to remote object store.",
    )
    parser.add_argument("--confirm", action="store_true", help="Execute migration (default is dry run)")
    parser.add_argument("--project", type=str, default=None, help="Migrate only this project")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress per-file output")
    args = parser.parse_args()
    args.dry_run = not args.confirm

    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
