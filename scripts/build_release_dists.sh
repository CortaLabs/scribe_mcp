#!/usr/bin/env bash
set -euo pipefail

# Resolve from the script rather than the caller's working directory.
python - "${BASH_SOURCE[0]}" "${1:-}" <<'PY'
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from zipfile import ZipFile

from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename
from packaging.version import Version

root = Path(sys.argv[1]).resolve().parents[1]
out = Path(sys.argv[2]).resolve() if sys.argv[2] else root / "dist" / "pypi"
project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
name, version = canonicalize_name(project["name"]), Version(project["version"])

# Refuse before creating directories or running hooks, preserving retained releases.
if out.exists():
    for path in out.iterdir():
        try:
            if path.name.endswith(".whl"):
                artifact_name, artifact_version, _, _ = parse_wheel_filename(path.name)
            elif path.name.endswith((".tar.gz", ".zip")):
                artifact_name, artifact_version = parse_sdist_filename(path.name)
            else:
                continue
        except ValueError:
            continue
        if artifact_name == name and artifact_version == version:
            raise SystemExit(f"Release output collision: {path}")

env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
with tempfile.TemporaryDirectory(prefix="scribe-release-") as temporary:
    workspace = Path(temporary)
    source, staged = workspace / "source", workspace / "dist"
    source.mkdir()
    # Snapshot tracked working-tree bytes, including local release fixes. Never
    # copy stale build products, untracked input, private audit or generated state.
    tracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    private = {".git", ".council", ".claude", ".codex", ".scribe", ".agents", ".venv"}
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if relative.parts[0] in private or any(
            part in {"build", "dist", "__pycache__"} or part.endswith(".egg-info")
            for part in relative.parts
        ) or relative.suffix in {".pyc", ".pyo", ".pyd"}:
            continue
        original = root / relative
        if original.is_symlink():
            raise SystemExit(f"Release source symlink refused: {relative}")
        if original.is_file():
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)

    # Preserve the plugin-sync gate in disposable source. Default build makes
    # the wheel from its fresh sdist; use existing requirements without downloads.
    subprocess.run([sys.executable, str(source / "scripts/sync_plugin_skills.py"), "--check"], check=True, env=env)
    subprocess.run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(staged), str(source)], check=True, env=env)
    artifacts = sorted(staged.iterdir())
    if len(artifacts) != 2 or sum(p.suffix == ".whl" for p in artifacts) != 1 or sum(p.name.endswith(".tar.gz") for p in artifacts) != 1:
        raise SystemExit("Expected exactly one wheel and one sdist")
    # Twine's metadata and README validation remain mandatory before publication.
    subprocess.run([sys.executable, "-m", "twine", "check", *map(str, artifacts)], check=True, env=env)

    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with ZipFile(artifact) as archive:
                names = archive.namelist()
        else:
            with tarfile.open(artifact) as archive:
                names = [m.name.split("/", 1)[-1] for m in archive.getmembers()]
        forbidden = [n for n in names if private.intersection(PurePosixPath(n).parts)
                     or "__pycache__" in PurePosixPath(n).parts
                     or n.endswith((".pyc", ".pyo", ".pyd"))
                     or "scribe_mcp/council_templates/skills/" in n
                     or "scribe_mcp/council_templates/rules/" in n]
        if forbidden:
            raise SystemExit(f"Forbidden release payload in {artifact.name}: {forbidden}")

    out.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        # Exclusive create also protects a collision appearing during build.
        with (out / artifact.name).open("xb") as destination, artifact.open("rb") as stream:
            shutil.copyfileobj(stream, destination)
        print(out / artifact.name, flush=True)
PY
