import atexit
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

pytest_plugins = ("fixtures.storage", "fixtures.projects")

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
LEGACY_IMPORT_ROOT = SRC_ROOT / "scribe_mcp"
CORE_TEST_ROOT = REPO_ROOT / "tests" / "core"
INTEGRATION_TEST_ROOT = REPO_ROOT / "tests" / "integration"
STORAGE_INTEGRATION_TEST_ROOT = INTEGRATION_TEST_ROOT / "storage"

for path in (SRC_ROOT, LEGACY_IMPORT_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

_state_dir = Path(tempfile.mkdtemp(prefix="scribe-tests-state-"))
_state_path = _state_dir / "state.json"
_default_project_name = "pytest_default_project"
_default_docs_dir = _state_dir / "dev_plans" / _default_project_name
_default_docs_dir.mkdir(parents=True, exist_ok=True)
_default_progress_log = _default_docs_dir / "PROGRESS_LOG.md"
_default_progress_log.touch(exist_ok=True)

_default_state = {
    "current_project": _default_project_name,
    "projects": {
        _default_project_name: {
            "name": _default_project_name,
            "root": str(_state_dir),
            "progress_log": str(_default_progress_log),
            "docs_dir": str(_default_docs_dir),
            "docs": {
                "architecture": str(_default_docs_dir / "ARCHITECTURE_GUIDE.md"),
                "phase_plan": str(_default_docs_dir / "PHASE_PLAN.md"),
                "checklist": str(_default_docs_dir / "CHECKLIST.md"),
                "progress_log": str(_default_progress_log),
            },
            "defaults": {"agent": "Codex"},
        }
    },
    "recent_projects": [_default_project_name],
}
_state_path.write_text(json.dumps(_default_state, indent=2) + "\n", encoding="utf-8")
os.environ["SCRIBE_STATE_PATH"] = str(_state_path)
# Every pytest process, including each xdist worker, gets its own SQLite file.
# This keeps the suite hermetic and prevents workers from contending with one
# another or with a developer's live Scribe database.
os.environ["SCRIBE_DB_PATH"] = str(_state_dir / "scribe_projects.db")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _cleanup_state_dir() -> None:
    shutil.rmtree(_state_dir, ignore_errors=True)


atexit.register(_cleanup_state_dir)


@pytest.fixture
def test_agent() -> str:
    """Return the canonical persona used by hermetic tests."""
    return "test-agent"


@pytest.fixture(autouse=True)
def _restore_server_globals() -> None:
    """Prevent direct module-global test doubles from leaking into later tests."""
    try:
        from scribe_mcp import server as server_module
    except Exception:
        yield
        return

    names = (
        "state_manager",
        "storage_backend",
        "get_execution_context",
        "get_agent_identity",
        "router_context_manager",
    )
    originals = {name: getattr(server_module, name, None) for name in names}
    present = {name: hasattr(server_module, name) for name in names}
    yield
    for name, value in originals.items():
        if present[name]:
            setattr(server_module, name, value)
        elif hasattr(server_module, name):
            delattr(server_module, name)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config) -> int:
    """Cap automatic parallelism at a portable, SQLite-friendly worker count."""
    _ = config
    return max(1, min(os.cpu_count() or 1, 8))


def pytest_collection_modifyitems(items) -> None:
    """Apply the bounded shipped-test markers from the path contract."""
    for item in items:
        item_path = Path(str(item.fspath)).resolve()
        if _is_within(item_path, STORAGE_INTEGRATION_TEST_ROOT):
            item.add_marker("integration")
            continue
        if _is_within(item_path, INTEGRATION_TEST_ROOT):
            item.add_marker("integration")
            continue
        if _is_within(item_path, CORE_TEST_ROOT):
            item.add_marker("core")
