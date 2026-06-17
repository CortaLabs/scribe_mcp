#!/usr/bin/env python3
"""Clean-room install verification for the ``scribe-mcp`` wheel.

This script proves that the *built artifact* (not the dev working tree) installs
correctly and projects its vendored assets. It exists to catch packaging gaps
automatically — for example, the plugin bundles shipping only one skill — before
they reach an operator after release.

What it does (in a fresh, isolated environment):

1. Build the wheel via the existing :mod:`build_release_dists.sh` (reuse-first;
   no parallel build system).
2. Create a throwaway virtualenv and ``pip install`` the *built wheel*
   (not ``-e``, not the repo working tree). This exercises package-data /
   MANIFEST inclusion the same way a real ``pip install scribe-mcp`` would.
3. Assert the runtime version surface (``python -m scribe_mcp --version``)
   matches the package metadata version.
4. Assert the vendored assets resolve from the INSTALLED package (site-packages),
   via :func:`scribe_mcp.config.paths` helpers — the plugin bundles + onboarding
   skill — and that the EXPECTED SKILL SET ships in both plugin channels.
5. Assert ``scribe install --commit --yes --project-codex`` projects the Codex
   plugin into a temp ``CODEX_HOME`` and lands the expected agent/skill files
   on disk.

Coverage boundary (kept honest):
  This verifies the PACKAGING SURFACE — install path, asset projection from
  site-packages, version truth, and shipped-skill presence. It does NOT spin up
  a Postgres runtime; the MCP server is not booted against a live database here.
  Those runtime concerns are covered elsewhere; this check is scoped to what a
  fresh ``pip install`` actually delivers on disk.

Exit code is non-zero on any failed assertion, with a clear message.

Usage (also runnable locally)::

    python scripts/cleanroom_install_check.py
    python scripts/cleanroom_install_check.py --keep   # keep the temp workdir
    python scripts/cleanroom_install_check.py --wheel /path/to/prebuilt.whl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_release_dists.sh"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# ---------------------------------------------------------------------------
# Expected shipped skill set — KEEP IN SYNC with the package-1 sync rule
# (scripts/sync_plugin_skills.py: glob ``scribe-*`` minus ``scribe-rag-workflow``,
# which is owned by Knowledge MCP). Editing this single list is how the contract
# is kept truthful when the shipped skills change.
# ---------------------------------------------------------------------------
EXPECTED_PLUGIN_SKILLS: frozenset[str] = frozenset(
    {
        "scribe-mcp-usage",
        "scribe-onboarding",
        "scribe-integration",
    }
)
# Explicitly NOT shipped in the Scribe plugin bundles (owner: knowledge-mcp).
EXCLUDED_PLUGIN_SKILLS: frozenset[str] = frozenset({"scribe-rag-workflow"})

PLUGIN_CHANNELS: tuple[str, ...] = ("claude", "codex")


class CleanRoomError(RuntimeError):
    """Raised when a clean-room assertion fails."""


def _log(msg: str) -> None:
    print(f"[cleanroom] {msg}", flush=True)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Run a command, streaming nothing; return stdout. Raise on non-zero."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise CleanRoomError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


def _read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise CleanRoomError(f"could not parse version from {PYPROJECT}")
    return match.group(1)


def build_wheel(out_dir: Path) -> Path:
    """Build the wheel via the existing release build script; return its path."""
    _log(f"building distributions via {BUILD_SCRIPT.name} -> {out_dir}")
    _run(["bash", str(BUILD_SCRIPT), str(out_dir)])
    wheels = sorted(out_dir.glob("scribe_mcp-*.whl"))
    if not wheels:
        wheels = sorted(out_dir.glob("*.whl"))
    if not wheels:
        raise CleanRoomError(f"no wheel produced in {out_dir}")
    if len(wheels) > 1:
        raise CleanRoomError(f"expected exactly one wheel, found: {[w.name for w in wheels]}")
    _log(f"built wheel: {wheels[0].name}")
    return wheels[0]


def make_venv(venv_dir: Path) -> Path:
    """Create a fresh venv with pip; return the venv python executable path."""
    _log(f"creating fresh venv at {venv_dir}")
    venv.EnvBuilder(with_pip=True, clear=True).create(str(venv_dir))
    if os.name == "nt":
        py = venv_dir / "Scripts" / "python.exe"
    else:
        py = venv_dir / "bin" / "python"
    if not py.exists():
        raise CleanRoomError(f"venv python not found at {py}")
    # Make sure pip is modern enough to honor wheel package-data.
    _run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    return py


def install_wheel(py: Path, wheel: Path) -> None:
    """Install the built wheel (NOT editable, NOT from the working tree)."""
    _log(f"pip install {wheel.name} (from artifact, not -e)")
    _run([str(py), "-m", "pip", "install", str(wheel)])


def assert_version(py: Path, expected: str) -> None:
    out = _run([str(py), "-m", "scribe_mcp", "--version"]).strip()
    _log(f"runtime version surface: {out!r}")
    if expected not in out:
        raise CleanRoomError(
            f"version mismatch: `python -m scribe_mcp --version` -> {out!r} "
            f"does not contain package version {expected!r}"
        )


# Probe executed inside the clean venv to introspect the INSTALLED package only.
# It must not import anything from the repo working tree.
_ASSET_PROBE = r"""
import json
import sys
from pathlib import Path

from scribe_mcp.config import paths

site_pkg = Path(paths.package_root()).resolve()

# Guard: the resolved package root must be the INSTALLED copy (site-packages),
# never the repo working tree under src/. If this is the dev tree the clean-room
# guarantee is void.
result = {"package_root": str(site_pkg)}

bundle = Path(paths.plugins_bundle_dir())
codex_root = Path(paths.resolve_codex_plugin_root())
onboarding = Path(paths.onboarding_skill_path())

result["plugins_bundle_dir"] = str(bundle)
result["codex_plugin_root"] = str(codex_root)
result["onboarding_skill_path"] = str(onboarding)
result["onboarding_skill_exists"] = onboarding.is_file()
result["codex_manifest_exists"] = (codex_root / ".codex-plugin" / "plugin.json").is_file()

channels = {}
for channel in ("claude", "codex"):
    skills_dir = bundle / channel / "skills"
    shipped = []
    if skills_dir.is_dir():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                shipped.append(d.name)
    channels[channel] = shipped
result["plugin_skills"] = channels

print(json.dumps(result))
"""


def probe_installed_assets(py: Path) -> dict:
    """Introspect the installed package's asset projection from site-packages."""
    out = _run([str(py), "-c", _ASSET_PROBE])
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise CleanRoomError(f"could not parse asset probe output: {exc}\n{out}") from exc
    return data


def assert_assets_from_installed_package(data: dict) -> None:
    pkg_root = Path(data["package_root"])
    _log(f"installed package_root: {pkg_root}")

    # Must be site-packages, not the repo src tree.
    try:
        pkg_root.relative_to(REPO_ROOT)
        in_repo = True
    except ValueError:
        in_repo = False
    if in_repo:
        raise CleanRoomError(
            f"package_root resolved INSIDE the repo working tree ({pkg_root}); "
            "clean-room install did not exercise the installed artifact"
        )
    if "site-packages" not in str(pkg_root):
        _log(f"WARNING: package_root is not under site-packages ({pkg_root}); continuing")

    # Onboarding skill must project from the installed package.
    if not data.get("onboarding_skill_exists"):
        raise CleanRoomError(
            f"onboarding skill missing from installed package: {data.get('onboarding_skill_path')}"
        )
    _log(f"onboarding skill present: {data['onboarding_skill_path']}")

    # Codex plugin root must resolve to the packaged bundle with a manifest.
    if not data.get("codex_manifest_exists"):
        raise CleanRoomError(
            f"codex plugin manifest missing under resolved root: {data.get('codex_plugin_root')}"
        )
    codex_root = Path(data["codex_plugin_root"])
    if Path(data["package_root"]) not in [codex_root, *codex_root.parents]:
        raise CleanRoomError(
            f"codex plugin root {codex_root} does not resolve from installed package "
            f"{data['package_root']} (would fall back to a repo clone)"
        )
    _log(f"codex plugin root resolves from package: {codex_root}")

    # Expected skill set must ship in BOTH channels.
    failures: list[str] = []
    for channel in PLUGIN_CHANNELS:
        shipped = set(data["plugin_skills"].get(channel, []))
        _log(f"plugin channel {channel!r} ships skills: {sorted(shipped)}")
        missing = EXPECTED_PLUGIN_SKILLS - shipped
        if missing:
            failures.append(
                f"channel {channel!r} is MISSING expected skills: {sorted(missing)} "
                f"(shipped: {sorted(shipped)})"
            )
        leaked = EXCLUDED_PLUGIN_SKILLS & shipped
        if leaked:
            failures.append(
                f"channel {channel!r} ships EXCLUDED skills it must not: {sorted(leaked)}"
            )
    if failures:
        raise CleanRoomError(
            "shipped plugin skill set is wrong:\n  - " + "\n  - ".join(failures)
        )
    _log(
        "expected skill set ships in both channels: "
        f"{sorted(EXPECTED_PLUGIN_SKILLS)}"
    )


# Probe that resolves the Codex plugin root from the INSTALLED package, so the
# projection asserts the wheel-shipped bundle (not a repo clone). Mirrors what
# `scribe install --project-codex` does internally via resolve_codex_plugin_root().
_PLUGIN_ROOT_PROBE = "from scribe_mcp.config import paths; print(paths.resolve_codex_plugin_root())"


def assert_codex_projection(py: Path, workdir: Path) -> None:
    """Project the packaged Codex plugin into a temp CODEX_HOME and assert disk.

    NOTE ON SCOPE: the full ``scribe install --commit --yes --project-codex`` flow
    runs a real DB bootstrap (Postgres by default) and a post-install
    ``scribe_doctor`` verification BEFORE projection. That is a runtime concern,
    not a packaging concern, and CI here has no Postgres. So this check exercises
    the SAME projection code path (``project_codex_plugin`` via
    ``scribe plugins project-codex``) sourced from the INSTALLED package bundle —
    which is exactly what ``--project-codex`` resolves and runs once base install
    succeeds. This faithfully proves the asset projection without faking a green
    DB runtime.
    """
    codex_home = workdir / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    # Keep the flow from touching the real repo / user state.
    install_root = workdir / "install_root"
    install_root.mkdir(parents=True, exist_ok=True)
    env["SCRIBE_ROOT"] = str(install_root)
    # No Postgres runtime in CI: explicitly opt into standalone SQLite so the CLI
    # can import (server constructs a storage backend at import time). This is the
    # documented SQLite opt-out, not a faked runtime.
    env["SCRIBE_MODE"] = "standalone"
    env["SCRIBE_STORAGE_BACKEND"] = "sqlite"
    env["SCRIBE_DB_PATH"] = str(workdir / "cleanroom_scribe.db")

    # Resolve the plugin root from the installed package (site-packages bundle).
    packaged_plugin_root = _run([str(py), "-c", _PLUGIN_ROOT_PROBE], env=env).strip()
    _log(f"projecting packaged Codex plugin root: {packaged_plugin_root}")

    _run(
        [
            str(py),
            "-m",
            "scribe_mcp.cli.main",
            "plugins",
            "project-codex",
            "--plugin-root",
            packaged_plugin_root,
            "--codex-home",
            str(codex_home),
        ],
        cwd=install_root,
        env=env,
    )

    projected_skill = codex_home / "skills" / "scribe-mcp-usage" / "SKILL.md"
    if not projected_skill.is_file():
        raise CleanRoomError(
            f"codex projection did not land the expected skill on disk: {projected_skill}"
        )
    config_toml = codex_home / "config.toml"
    if not config_toml.is_file():
        raise CleanRoomError(f"codex projection did not write config: {config_toml}")
    agents_dir = codex_home / "agents"
    projected_agents = sorted(agents_dir.glob("*.toml")) if agents_dir.is_dir() else []
    if not projected_agents:
        raise CleanRoomError(f"codex projection wrote no agent configs under {agents_dir}")
    _log(
        f"codex projection landed: skill={projected_skill.name}, "
        f"agents={[p.stem for p in projected_agents]}, config=config.toml"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help="Use a pre-built wheel instead of building one.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temporary work directory (for debugging).",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Use a specific work directory instead of a temp dir.",
    )
    args = parser.parse_args(argv)

    expected_version = _read_pyproject_version()
    _log(f"package version (pyproject): {expected_version}")

    tmp_ctx = None
    if args.workdir is not None:
        workdir = args.workdir.resolve()
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="scribe-cleanroom-")
        workdir = Path(tmp_ctx.name)
    if args.keep and tmp_ctx is not None:
        # Detach the cleanup so the dir survives.
        tmp_ctx._finalizer.detach()  # type: ignore[attr-defined]
        _log(f"keeping workdir: {workdir}")

    try:
        if args.wheel is not None:
            wheel = args.wheel.resolve()
            if not wheel.is_file():
                raise CleanRoomError(f"--wheel not found: {wheel}")
            _log(f"using pre-built wheel: {wheel}")
        else:
            wheel = build_wheel(workdir / "dist")

        py = make_venv(workdir / "venv")
        install_wheel(py, wheel)

        assert_version(py, expected_version)
        data = probe_installed_assets(py)
        assert_assets_from_installed_package(data)
        assert_codex_projection(py, workdir)

    except CleanRoomError as exc:
        _log("FAIL")
        print(f"\nCLEAN-ROOM INSTALL CHECK FAILED:\n{exc}", file=sys.stderr)
        return 1
    finally:
        if tmp_ctx is not None and not args.keep:
            tmp_ctx.cleanup()

    _log("PASS — clean-room install verified (version + asset projection + codex projection)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
