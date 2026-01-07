#!/usr/bin/env python3
"""Debug script to test path resolution logic."""

import sys
import asyncio
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.storage.sqlite import SQLiteStorage

async def main():
    # Initialize storage
    db_path = Path(__file__).parent / ".scribe" / "scribe.db"
    storage = SQLiteStorage(db_path=str(db_path))

    # Fetch project from database
    project_record = await storage.fetch_project("manage_docs_testing_playground")

    if not project_record:
        print("❌ Project not found in database")
        return

    print(f"✅ Project found in database:")
    print(f"   name: {project_record.name}")
    print(f"   repo_root: {project_record.repo_root}")
    print(f"   progress_log_path: {project_record.progress_log_path}")
    print()

    # Simulate what manage_docs would receive
    project_dict = {
        "name": project_record.name,
        "root": project_record.repo_root,
        "progress_log": project_record.progress_log_path
    }

    print(f"Project dict passed to _resolve_custom_doc_path:")
    for k, v in project_dict.items():
        print(f"   {k}: {v}")
    print()

    # Test path resolution logic
    progress_log = project_dict.get("progress_log")
    if not progress_log:
        print("❌ No progress_log in project dict")
        return

    docs_dir = Path(progress_log).parent
    print(f"docs_dir: {docs_dir}")
    print(f"docs_dir exists: {docs_dir.exists()}")
    print()

    # Test research doc resolution
    doc_type = "research"
    doc_name = "RESEARCH_CONTEXT_HYDRATION_20260107"

    research_dir = docs_dir / "research"
    print(f"research_dir: {research_dir}")
    print(f"research_dir exists: {research_dir.exists()}")
    print()

    candidate = research_dir / f"{doc_name}.md"
    print(f"candidate: {candidate}")
    print(f"candidate exists: {candidate.exists()}")
    print()

    if candidate.exists():
        print("✅ Path resolution SHOULD WORK!")
    else:
        print("❌ Path resolution WILL FAIL!")

if __name__ == "__main__":
    asyncio.run(main())
