#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT_DIR/dist/pypi}"

# Build from a clean local tree so stale tracked build outputs cannot leak into
# public artifacts.
rm -rf "$ROOT_DIR/build" "$ROOT_DIR/dist" "$ROOT_DIR/src/scribe_mcp.egg-info"
find "$ROOT_DIR/src" -type d -name '__pycache__' -prune -exec rm -rf {} +

mkdir -p "$OUT_DIR"

# Ensure the shipped plugin skill set (and its wheel-vendored mirror) is current
# before building, so the wheel always carries every Scribe-owned generated
# skill. --check fails the build if the trees drifted from the generated source;
# run `python scripts/sync_plugin_skills.py` to repair.
python "$ROOT_DIR/scripts/sync_plugin_skills.py" --check

python -m build --sdist --wheel --outdir "$OUT_DIR" "$ROOT_DIR"
python -m twine check "$OUT_DIR"/*

python - "$OUT_DIR" <<'PY'
from pathlib import Path
from zipfile import ZipFile

out_dir = Path(__import__("sys").argv[1])
for wheel in out_dir.glob("*.whl"):
    with ZipFile(wheel) as zf:
        names = zf.namelist()
    forbidden = [
        name for name in names
        if "__pycache__/" in name
        or name.endswith(".pyc")
        or "scribe_mcp/council_templates/skills/" in name
        or "scribe_mcp/council_templates/rules/" in name
    ]
    if forbidden:
        raise SystemExit(
            f"Forbidden release payload found in {wheel.name}: " + ", ".join(forbidden)
        )
PY
