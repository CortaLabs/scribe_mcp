import json
import os
import sys
import tempfile
from pathlib import Path

pytest_plugins = ("fixtures.storage", "fixtures.projects")

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
LEGACY_IMPORT_ROOT = SRC_ROOT / "scribe_mcp"

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
os.environ.setdefault("SCRIBE_STATE_PATH", str(_state_path))
