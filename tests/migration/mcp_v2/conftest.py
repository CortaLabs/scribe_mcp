from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "regression: permanent behavioral regression guard")
    config.addinivalue_line("markers", "mcp_v2: MCP SDK v2 migration compatibility lane")


@dataclass(frozen=True)
class ProbeResult:
    returncode: int
    payload: dict[str, Any]
    stderr: str


@pytest.fixture(scope="session")
def mcp_v2_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def candidate_python(mcp_v2_repo_root: Path) -> Path:
    configured = os.environ.get("MCPV2_CANDIDATE_PYTHON")
    python = Path(configured).absolute() if configured else Path(sys.executable).absolute()
    result = subprocess.run(
        [str(python), "-c", "from importlib.metadata import version; print(version('mcp'))"],
        cwd=mcp_v2_repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "2.0.0"
    return python


@pytest.fixture(scope="session")
def legacy_python(tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("MCPV2_LEGACY_PYTHON")
    if configured:
        return Path(configured).absolute()
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required to create the exact mcp==1.26.0 client environment")
    root = tmp_path_factory.mktemp("mcp-v2-legacy-client")
    subprocess.run([uv, "venv", "--python", "3.11", str(root)], check=True)
    python = root / "bin" / "python"
    subprocess.run(
        [uv, "pip", "install", "--python", str(python), "mcp==1.26.0"],
        check=True,
    )
    return python


@pytest.fixture
def isolated_runtime_env(
    tmp_path: Path,
    mcp_v2_repo_root: Path,
    test_agent: str,
) -> dict[str, str]:
    runtime = tmp_path / "runtime"
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    for path in (runtime, repo_a / ".git", repo_b / ".git"):
        path.mkdir(parents=True)
    env = os.environ.copy()
    env.update(
        {
            "SCRIBE_DISABLE_DOTENV": "1",
            "SCRIBE_LOAD_REPO_DOTENV": "0",
            "SCRIBE_MODE": "standalone",
            "SCRIBE_STORAGE_BACKEND": "sqlite",
            "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
            "SCRIBE_STATE_PATH": str(runtime / "state.json"),
            "SCRIBE_ROOT": str(runtime),
            "SCRIBE_REPO_ROOT": str(repo_a),
            "SCRIBE_TRUSTED_REPO_ROOTS": os.pathsep.join((str(repo_a), str(repo_b))),
            "SCRIBE_TRANSPORT_ALLOWED_ORIGINS": "https://trusted.example",
            "SCRIBE_TRANSPORT_AUTH_TOKEN": "mcp-v2-test-token",
            "MCPV2_REPO_A": str(repo_a),
            "MCPV2_REPO_B": str(repo_b),
            "MCPV2_TEST_AGENT": test_agent,
        }
    )
    if os.environ.get("MCPV2_ISOLATED_INSTALL") == "1":
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = str(mcp_v2_repo_root / "src")
    return env


def run_json_probe(
    python: Path,
    code: str,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 90,
) -> ProbeResult:
    completed = subprocess.run(
        [str(python), "-c", code],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    payload: dict[str, Any] = {}
    if stdout_lines:
        payload = json.loads(stdout_lines[-1])
    return ProbeResult(completed.returncode, payload, completed.stderr)


@pytest.fixture
def json_probe():
    return run_json_probe
