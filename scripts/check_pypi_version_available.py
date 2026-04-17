#!/usr/bin/env python3
"""Fail release publishing when the target package version already exists on PyPI."""

from __future__ import annotations

import json
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject_path = repo_root / "pyproject.toml"
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
            print(f"PyPI package {package_name!r} does not exist yet; version {version} is available.")
            return 0
        raise

    releases = payload.get("releases", {})
    existing_files = releases.get(version) or []
    if existing_files:
        print(
            f"Refusing to publish duplicate PyPI release: {package_name} {version} already exists.",
            file=sys.stderr,
        )
        print(
            "Bump pyproject.toml to a new version before pushing a release-bound change.",
            file=sys.stderr,
        )
        return 1

    print(f"PyPI version check passed: {package_name} {version} is not published yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
