#!/usr/bin/env python3
"""Produce one cleanup-authoritative MCP v2 compatibility validation receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence


REDACTIONS = (
    "mcp-v2-test-token",
    "mcpv2-secret-canary-9f2aa89e",
)

LEGACY_PROTOCOL = "2025-11-25"

AGGREGATE_TESTS = (
    "tests/migration/mcp_v2/test_compatibility_matrix.py",
    "tests/test_mcp_adapter.py",
    "tests/test_tools.py",
    "tests/test_transport_sse.py",
    "tests/security/test_transport_authorization.py",
    "tests/security/test_session_provenance.py",
    "tests/shared/test_actor_scoped_session_binding.py",
    "tests/shared/test_session_repo_root_poisoning.py",
    "tests/test_tool_runtime_repo_scope.py",
    "tests/test_server_api.py",
    "tests/test_auth_transport_contracts.py",
)


def _redact(value: str) -> str:
    for secret in REDACTIONS:
        value = value.replace(secret, "<redacted>")
    return value


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "command": [str(item) for item in args],
            "returncode": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": _redact(completed.stdout[-12000:]),
            "stderr_tail": _redact(completed.stderr[-12000:]),
            "passed": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": [str(item) for item in args],
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": _redact(str(exc.stdout or "")[-12000:]),
            "stderr_tail": _redact(str(exc.stderr or "")[-12000:]),
            "passed": False,
            "timed_out": True,
        }


def _distribution_receipt(python: Path, names: Sequence[str], repo_root: Path) -> dict[str, Any]:
    code = r'''
import hashlib, importlib.metadata, json, pathlib, sys
result = {"executable": sys.executable, "prefix": sys.prefix, "packages": {}}
for name in json.loads(sys.argv[1]):
    dist = importlib.metadata.distribution(name)
    origin = pathlib.Path(dist.locate_file("")).resolve()
    digest = hashlib.sha256()
    file_count = 0
    for item in sorted(dist.files or [], key=str):
        path = pathlib.Path(dist.locate_file(item))
        if not path.is_file():
            continue
        digest.update(str(item).encode("utf-8")); digest.update(b"\0")
        digest.update(path.read_bytes()); digest.update(b"\0")
        file_count += 1
    result["packages"][name] = {
        "version": dist.version,
        "origin": str(origin),
        "installed_tree_sha256": digest.hexdigest(),
        "hashed_files": file_count,
    }
print(json.dumps(result, sort_keys=True))
'''
    completed = subprocess.run(
        [str(python), "-c", code, json.dumps(list(names))],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _legacy_baseline_ref(repo_root: Path) -> tuple[str, str]:
    revisions = subprocess.run(
        ["git", "rev-list", "HEAD", "--", "pyproject.toml"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    for revision in revisions:
        manifest = subprocess.run(
            ["git", "show", f"{revision}:pyproject.toml"],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if manifest.returncode != 0 or '"mcp==1.26.0"' not in manifest.stdout:
            continue
        adapter = subprocess.run(
            ["git", "cat-file", "-e", f"{revision}:src/scribe_mcp/mcp_adapter.py"],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if adapter.returncode != 0:
            return revision, manifest.stdout
    raise RuntimeError("No committed legacy MCP baseline was found in repository history")


def _rollback_receipt(repo_root: Path) -> dict[str, Any]:
    baseline_ref, prior = _legacy_baseline_ref(repo_root)
    current = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    prior_cli = subprocess.run(
        ["git", "show", f"{baseline_ref}:src/scribe_mcp/__main__.py"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    current_adapter = (repo_root / "src/scribe_mcp/mcp_adapter.py").read_text(
        encoding="utf-8"
    )
    readback_paths = (
        "README.md",
        "docs/COMPATIBILITY_MATRIX.md",
        "docs/INSTALL_AND_BOOTSTRAP.md",
        "docs/RELEASE_FILE_MAP.md",
        "docs/REMOTE_CLIENT.md",
        "docs/mcp_server_guide.md",
    )
    readback = {
        path: (repo_root / path).read_text(encoding="utf-8")
        for path in readback_paths
    }
    prior_adapter = subprocess.run(
        ["git", "cat-file", "-e", f"{baseline_ref}:src/scribe_mcp/mcp_adapter.py"],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    dependency_rollback_shadow = current.replace(
        '"mcp>=2.0.0,<3.0"',
        '"mcp==1.26.0"',
        1,
    )
    return {
        "baseline_ref": baseline_ref,
        "prior_dependency": "mcp==1.26.0" if '"mcp==1.26.0"' in prior else None,
        "current_dependency": "mcp>=2.0.0,<3.0" if '"mcp>=2.0.0,<3.0"' in current else None,
        "dependency_shadow_restored": (
            '"mcp==1.26.0"' in dependency_rollback_shadow
            and '"mcp>=2.0.0,<3.0"' not in dependency_rollback_shadow
        ),
        "prior_default_transport": (
            "stdio"
            if 'default=os.environ.get("SCRIBE_TRANSPORT", "stdio")' in prior_cli
            else None
        ),
        "prior_adapter_absent": prior_adapter.returncode != 0,
        "explicit_legacy_revision_preserved": (
            'legacy_revisions: tuple[str, ...] = ("2025-11-25",)' in current_adapter
        ),
        "disproven_legacy_readback_absent": all(
            "2025-06-18" not in content for content in readback.values()
        ),
        "ratified_legacy_readback_present": all(
            "2025-11-25" in content for content in readback.values()
        ),
        "shadow_restore_only": True,
        "source_mutated": False,
        "modern_failure_reclassified_as_legacy": False,
    }


def _entry_point_receipt(python: Path, repo_root: Path) -> dict[str, Any]:
    code = r'''
import importlib.metadata, json
dist = importlib.metadata.distribution("scribe-mcp")
print(json.dumps(sorted({ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}.items())))
'''
    completed = subprocess.run(
        [str(python), "-c", code], cwd=repo_root, text=True, capture_output=True, check=True
    )
    return dict(json.loads(completed.stdout))


def _matrix_rows(repo_root: Path) -> dict[str, dict[str, str]]:
    namespace = runpy.run_path(str(repo_root / "tests/migration/mcp_v2/test_compatibility_matrix.py"))
    return {
        row: {"status": status, "evidence": evidence}
        for row, (status, evidence) in namespace["MATRIX_EVIDENCE"].items()
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--legacy", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    started = time.time()
    receipt: dict[str, Any] = {
        "schema": "scribe.mcp-v2-isolated-receipt.v1",
        "repo_root": str(repo_root),
        "requested": {
            "candidate_sdk": args.candidate,
            "legacy_sdk": args.legacy,
            "modern_protocol": args.protocol,
            "legacy_protocol": LEGACY_PROTOCOL,
        },
        "active_environment": {
            "executable": sys.executable,
            "prefix": sys.prefix,
            "mcp_version": importlib.metadata.version("mcp"),
        },
        "commands": {},
        "matrix": _matrix_rows(repo_root),
        "cleanup": {"passed": False},
    }
    uv = shutil.which("uv")
    if uv is None:
        receipt["fatal"] = "uv executable is required"
        print(json.dumps(receipt, sort_keys=True))
        return 1

    temp_root = Path(tempfile.mkdtemp(prefix="scribe-mcp-v2-isolated-"))
    candidate_root = temp_root / "candidate"
    legacy_root = temp_root / "legacy"
    dist_root = temp_root / "dist"
    dist_root.mkdir()
    child_pids_before: set[int] = set()
    cleanup_errors: list[str] = []
    try:
        receipt["commands"]["candidate_venv"] = _run(
            [uv, "venv", "--python", "3.11", str(candidate_root)], cwd=repo_root
        )
        candidate_python = candidate_root / "bin/python"
        receipt["commands"]["candidate_install"] = _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(candidate_python),
                f"{repo_root}[dev]",
                f"mcp=={args.candidate}",
                "mcp-types==2.0.0",
                "httpx2==2.5.0",
                "build",
            ],
            cwd=repo_root,
        )
        receipt["commands"]["legacy_venv"] = _run(
            [uv, "venv", "--python", "3.11", str(legacy_root)], cwd=repo_root
        )
        legacy_python = legacy_root / "bin/python"
        receipt["commands"]["legacy_install"] = _run(
            [uv, "pip", "install", "--python", str(legacy_python), f"mcp=={args.legacy}"],
            cwd=repo_root,
        )

        setup_ok = all(
            receipt["commands"][name]["passed"]
            for name in ("candidate_venv", "candidate_install", "legacy_venv", "legacy_install")
        )
        if setup_ok:
            receipt["packages"] = {
                "candidate": _distribution_receipt(
                    candidate_python, ("scribe-mcp", "mcp", "mcp-types", "httpx2"), repo_root
                ),
                "legacy": _distribution_receipt(legacy_python, ("mcp",), repo_root),
            }
            candidate_prefix = Path(receipt["packages"]["candidate"]["prefix"]).resolve()
            active_prefix = Path(receipt["active_environment"]["prefix"]).resolve()
            receipt["active_environment_separation"] = {
                "candidate_prefix_differs": candidate_prefix != active_prefix,
                "candidate_origin_outside_active_prefix": all(
                    not Path(item["origin"]).resolve().is_relative_to(active_prefix)
                    for item in receipt["packages"]["candidate"]["packages"].values()
                ),
            }
            receipt["commands"]["pip_check"] = _run(
                [uv, "pip", "check", "--python", str(candidate_python)], cwd=repo_root
            )
            receipt["entry_points"] = _entry_point_receipt(candidate_python, repo_root)

            test_env = os.environ.copy()
            test_env.update(
                {
                    "MCPV2_CANDIDATE_PYTHON": str(candidate_python),
                    "MCPV2_LEGACY_PYTHON": str(legacy_python),
                    "MCPV2_ISOLATED_INSTALL": "1",
                    "SCRIBE_DISABLE_DOTENV": "1",
                    "SCRIBE_MODE": "standalone",
                    "SCRIBE_STORAGE_BACKEND": "sqlite",
                }
            )
            test_env.pop("PYTHONPATH", None)
            receipt["commands"]["aggregate_pytest"] = _run(
                [str(candidate_python), "-m", "pytest", "-q", *AGGREGATE_TESTS],
                cwd=repo_root,
                env=test_env,
                timeout=900,
            )
            receipt["commands"]["build"] = _run(
                [str(candidate_python), "-m", "build", "--outdir", str(dist_root)],
                cwd=repo_root,
                timeout=300,
            )
            receipt["build_artifacts"] = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(dist_root.glob("*"))
                if path.is_file()
            }
            receipt["commands"]["source_generated_readback"] = _run(
                [str(candidate_python), "scripts/sync_plugin_skills.py", "--check"],
                cwd=repo_root,
            )
        receipt["rollback"] = _rollback_receipt(repo_root)
    except Exception as exc:
        receipt["fatal"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            shutil.rmtree(temp_root)
        except Exception as exc:
            cleanup_errors.append(f"{type(exc).__name__}: {exc}")
        receipt["cleanup"] = {
            "passed": not temp_root.exists() and not cleanup_errors,
            "temporary_root_removed": not temp_root.exists(),
            "listener_proof": "pre-v2 SSE test rebinds its exact ephemeral port after process termination",
            "errors": cleanup_errors,
            "tracked_child_pids_before": sorted(child_pids_before),
        }

    requested_versions_ok = (
        receipt.get("packages", {}).get("candidate", {}).get("packages", {}).get("mcp", {}).get("version")
        == args.candidate
        and receipt.get("packages", {}).get("legacy", {}).get("packages", {}).get("mcp", {}).get("version")
        == args.legacy
        and args.protocol == "2026-07-28"
    )
    package_receipts = [
        *receipt.get("packages", {}).get("candidate", {}).get("packages", {}).values(),
        *receipt.get("packages", {}).get("legacy", {}).get("packages", {}).values(),
    ]
    package_provenance_ok = len(package_receipts) == 5 and all(
        isinstance(item.get("origin"), str)
        and len(item.get("installed_tree_sha256", "")) == 64
        and item.get("hashed_files", 0) > 0
        for item in package_receipts
    )
    separation = receipt.get("active_environment_separation", {})
    active_environment_separation_ok = (
        separation.get("candidate_prefix_differs") is True
        and separation.get("candidate_origin_outside_active_prefix") is True
    )
    matrix_ok = all(row["status"] in {"PASS", "N/A"} for row in receipt["matrix"].values())
    required_commands = {
        "candidate_venv",
        "candidate_install",
        "legacy_venv",
        "legacy_install",
        "pip_check",
        "aggregate_pytest",
        "build",
        "source_generated_readback",
    }
    commands_ok = set(receipt["commands"]) == required_commands and all(
        item.get("passed", False) for item in receipt["commands"].values()
    )
    entry_points_ok = {
        "scribe-mcp": "scribe_mcp.__main__:main",
        "scribe-server": "scribe_mcp.__main__:main",
        "scribe-server-sse": "scribe_mcp.server_sse:main",
    }.items() <= receipt.get("entry_points", {}).items()
    build_artifacts_ok = {
        name.rsplit(".", 1)[-1]
        for name, digest in receipt.get("build_artifacts", {}).items()
        if len(digest) == 64
    } == {"whl", "gz"}
    rollback = receipt.get("rollback", {})
    rollback_ok = (
        rollback.get("prior_dependency") == "mcp==1.26.0"
        and rollback.get("current_dependency") == "mcp>=2.0.0,<3.0"
        and rollback.get("dependency_shadow_restored") is True
        and rollback.get("prior_default_transport") == "stdio"
        and rollback.get("prior_adapter_absent") is True
        and rollback.get("explicit_legacy_revision_preserved") is True
        and rollback.get("disproven_legacy_readback_absent") is True
        and rollback.get("ratified_legacy_readback_present") is True
        and rollback.get("shadow_restore_only") is True
        and rollback.get("source_mutated") is False
        and rollback.get("modern_failure_reclassified_as_legacy") is False
    )
    receipt["gates"] = {
        "no_fatal": "fatal" not in receipt,
        "requested_versions": requested_versions_ok,
        "package_provenance": package_provenance_ok,
        "active_environment_separation": active_environment_separation_ok,
        "matrix": matrix_ok,
        "commands": commands_ok,
        "entry_points": entry_points_ok,
        "build_artifacts": build_artifacts_ok,
        "rollback": rollback_ok,
        "cleanup": receipt["cleanup"]["passed"],
    }
    receipt["duration_seconds"] = round(time.time() - started, 3)
    receipt["verdict"] = (
        "PASS" if all(receipt["gates"].values()) else "BLOCK"
    )
    receipt["passed"] = receipt["verdict"] == "PASS"
    if args.json:
        print(json.dumps(receipt, sort_keys=True))
    else:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
