#!/usr/bin/env python3
"""Report whether the target package version should publish to PyPI."""

from __future__ import annotations

import json
import os
import tomllib
import urllib.error
import urllib.request
from argparse import ArgumentParser, Namespace
from pathlib import Path


def _parse_args() -> Namespace:
    parser = ArgumentParser(
        description=(
            "Check whether the package version in pyproject.toml is already "
            "published on PyPI."
        )
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "pyproject.toml",
        help="Path to the pyproject.toml to inspect.",
    )
    return parser.parse_args()


def _write_github_outputs(*, should_publish: bool, reason: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return

    output_path = Path(github_output)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"should_publish={'true' if should_publish else 'false'}\n")
        handle.write(f"reason={reason}\n")


def _write_github_summary(message: str) -> None:
    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not github_summary:
        return

    summary_path = Path(github_summary)
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def main() -> int:
    args = _parse_args()
    pyproject_path = args.pyproject.resolve()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data["project"]
    package_name = str(project["name"])
    version = str(project["version"])

    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            message = (
                f"PyPI package {package_name!r} does not exist yet; "
                f"version {version} is available."
            )
            print(message)
            _write_github_outputs(should_publish=True, reason="package_missing")
            _write_github_summary(f"- Publish check: {message}")
            return 0
        raise

    releases = payload.get("releases", {})
    existing_files = releases.get(version) or []
    if existing_files:
        message = (
            f"Skipping PyPI publish: {package_name} {version} already exists. "
            "Bump pyproject.toml to publish a new release."
        )
        print(message)
        _write_github_outputs(should_publish=False, reason="version_exists")
        _write_github_summary(f"- Publish check: {message}")
        return 0

    message = f"PyPI version check passed: {package_name} {version} is not published yet."
    print(message)
    _write_github_outputs(should_publish=True, reason="version_available")
    _write_github_summary(f"- Publish check: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
