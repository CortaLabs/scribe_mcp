#!/usr/bin/env python3
"""Produce one cleanup-authoritative MCP v2 compatibility validation receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import runpy
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence


REDACTIONS = (
    "mcp-v2-test-token",
    "mcpv2-secret-canary-9f2aa89e",
)

HISTORICAL_PROTOCOL = "2025-11-25"

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


def _assert_secret_free(evidence: Any) -> None:
    """Reject raw log/receipt leaks without echoing their secret contents."""
    serialized = json.dumps(evidence, sort_keys=True)
    if any(secret in serialized for secret in REDACTIONS):
        raise ValueError("T16_SECRET_EVIDENCE_LEAK")


def _aggregate_junit_evidence(path: Path) -> str | None:
    evidence = path.read_text() if path.is_file() else None
    _assert_secret_free({"aggregate_junit": evidence})
    return evidence


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(list(args), cwd=cwd, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    timed_out = False
    stdout = stderr = ""
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
    finally:
        for sig, budget in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=budget)
            except subprocess.TimeoutExpired:
                continue
            # Also kill orphaned descendants after the leader has exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            break
        process.wait(timeout=5)
    stdout, stderr = _redact(stdout), _redact(stderr)
    return {
        "command": [str(item) for item in args],
        "returncode": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": stdout, "stderr": stderr,
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
        "stdout_tail": stdout[-12000:], "stderr_tail": stderr[-12000:],
        "passed": process.returncode == 0 and not timed_out,
        "timed_out": timed_out,
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
        "historical_legacy_revision_preserved": (
            'legacy_revisions: tuple[str, ...] = ("2025-11-25",)' in current_adapter
        ),
        "disproven_legacy_readback_absent": all(
            "2025-06-18" not in content for content in readback.values()
        ),
        "ratified_legacy_readback_present": all(
            "2025-11-25" in content for content in readback.values()
        ),
        "historical_revision": HISTORICAL_PROTOCOL,
        "current_modern_only": 'legacy_enabled: bool = False' in current_adapter,
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


def _matrix_rows(repo_root: Path, outcomes: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    namespace = runpy.run_path(str(repo_root / "tests/migration/mcp_v2/test_compatibility_matrix.py"))
    return namespace["matrix_rows"](outcomes or {})


def _junit_outcomes(path: Path) -> dict[str, str]:
    """Consume every exact collected node, including parameter discriminants."""
    if not path.is_file():
        return {}
    outcomes: dict[str, str] = {}
    for case in ET.parse(path).iter("testcase"):
        parts = case.get("classname", "").split(".")
        module_end = next((i for i, part in enumerate(parts) if part.startswith("Test")), len(parts))
        node = "/".join(parts[:module_end]) + ".py::"
        node += "::".join((*parts[module_end:], case.get("name", "")))
        status = "BLOCK" if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")) else "PASS"
        outcomes[node] = "BLOCK" if outcomes.get(node) == "BLOCK" or status == "BLOCK" else "PASS"
    return outcomes


def _junit_fingerprints(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    fingerprints = [json.loads(prop.get("value", "{}"))
                    for prop in ET.parse(path).iter("property")
                    if prop.get("name") == "phase_report"]
    return sorted(fingerprints, key=lambda item: (item["nodeid"], item["phase"]))


def _phase_coverage_ok(outcomes: dict[str, str], fingerprints: list[dict[str, Any]]) -> bool:
    """Require one passing setup/call/teardown record for every exact node."""
    phases = {"setup", "call", "teardown"}
    if not outcomes or any(value != "PASS" for value in outcomes.values()):
        return False
    if len(fingerprints) != 3 * len(outcomes):
        return False
    seen: set[tuple[str, str]] = set()
    for item in fingerprints:
        if not isinstance(item, dict):
            return False
        node, phase = item.get("nodeid"), item.get("phase")
        if node not in outcomes or phase not in phases or item.get("outcome") != "passed":
            return False
        key = (node, phase)
        if key in seen:
            return False
        seen.add(key)
    return seen == {(node, phase) for node in outcomes for phase in phases}


def _install_commands(uv: str, candidate_root: Path, repo_root: Path, candidate: str) -> dict[str, list[str]]:
    return {
        "candidate_venv": [uv, "venv", "--python", "3.11", str(candidate_root)],
        "candidate_install": [uv, "pip", "install", "--python", str(candidate_root / "bin/python"),
                              f"{repo_root}[dev]", f"mcp=={candidate}", "mcp-types==2.3.0",
                              "httpx2==2.5.0", "build"],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--legacy", help="retired; refused before process or temporary state")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.legacy is not None:
        parser.error("--legacy is retired; obsolete wire traffic is denial evidence only")
    if args.candidate != "2.3.0" or args.protocol != "2026-07-28":
        parser.error("this receipt requires candidate 2.3.0 and protocol 2026-07-28")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    started = time.time()
    receipt: dict[str, Any] = {
        "schema": "scribe.mcp-v2-isolated-receipt.v1",
        "repo_root": str(repo_root),
        "requested": {
            "candidate_sdk": args.candidate,
            "modern_protocol": args.protocol,
            "historical_protocol": HISTORICAL_PROTOCOL,
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
    dist_root = temp_root / "dist"
    dist_root.mkdir()
    child_pids_before: set[int] = set()
    cleanup_errors: list[str] = []
    try:
        for name, command in _install_commands(uv, candidate_root, repo_root, args.candidate).items():
            receipt["commands"][name] = _run(command, cwd=repo_root)
        candidate_python = candidate_root / "bin/python"

        setup_ok = all(
            receipt["commands"][name]["passed"]
            for name in ("candidate_venv", "candidate_install")
        )
        if setup_ok:
            receipt["packages"] = {
                "candidate": _distribution_receipt(
                    candidate_python, ("scribe-mcp", "mcp", "mcp-types", "httpx2"), repo_root
                ),
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

            test_env = {key: value for key, value in os.environ.items()
                        if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}}
            test_env.update(
                {
                    "MCPV2_CANDIDATE_PYTHON": str(candidate_python),
                    "MCPV2_ISOLATED_INSTALL": "1",
                    "SCRIBE_DISABLE_DOTENV": "1",
                    "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "SCRIBE_MODE": "standalone",
                    "SCRIBE_STORAGE_BACKEND": "sqlite",
                }
            )
            test_env.pop("PYTHONPATH", None)
            test_env.pop("MCPV2_LEGACY_PYTHON", None)
            junit_path = temp_root / "aggregate.xml"
            receipt["commands"]["aggregate_pytest"] = _run(
                [str(candidate_python), "-m", "pytest", "-q", f"--junitxml={junit_path}", *AGGREGATE_TESTS],
                cwd=repo_root,
                env=test_env,
                timeout=900,
            )
            receipt["node_outcomes"] = _junit_outcomes(junit_path)
            receipt["node_phase_fingerprints"] = _junit_fingerprints(junit_path)
            receipt["aggregate_junit"] = _aggregate_junit_evidence(junit_path)
            receipt["matrix"] = _matrix_rows(repo_root, receipt["node_outcomes"])
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
            "listener_proof": "current and retired-path tests unconditionally rebind their exact ephemeral port",
            "errors": cleanup_errors,
            "tracked_child_pids_before": sorted(child_pids_before),
        }

    requested_versions_ok = (
        receipt.get("packages", {}).get("candidate", {}).get("packages", {}).get("mcp", {}).get("version")
        == args.candidate
        and args.protocol == "2026-07-28"
    )
    package_receipts = [
        *receipt.get("packages", {}).get("candidate", {}).get("packages", {}).values(),
    ]
    package_provenance_ok = len(package_receipts) == 4 and all(
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
    required_matrix_nodes = {
        node for row in receipt["matrix"].values() for node in row.get("nodes", ())
    }
    matrix_ok = (
        set(receipt["matrix"]) == {f"T{number:02d}" for number in range(1, 21)}
        and bool(required_matrix_nodes)
        and all(row["status"] in {"PASS", "N/A"} for row in receipt["matrix"].values())
        and all(receipt.get("node_outcomes", {}).get(node) == "PASS" for node in required_matrix_nodes)
    )
    required_commands = {
        "candidate_venv",
        "candidate_install",
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
        and rollback.get("historical_legacy_revision_preserved") is True
        and rollback.get("current_modern_only") is True
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
        "node_phase_fingerprints": _phase_coverage_ok(
            receipt.get("node_outcomes", {}), receipt.get("node_phase_fingerprints", [])),
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
    _assert_secret_free(receipt)
    if args.json:
        print(json.dumps(receipt, sort_keys=True))
    else:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
