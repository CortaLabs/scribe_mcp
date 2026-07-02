#!/usr/bin/env python3
"""Probe repo-local Scribe plugin loading with and without trusted opt-in.

This is an internal operator smoke test for generated `.scribe/plugins/**`
overlays. It does not enable trust globally and it does not affect package data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.plugins.registry import (
    PluginRegistry,
    trusted_plugin_runtime_opt_in_vars,
)
from scribe_mcp.tools.doctor import _build_plugin_diagnostics


@contextmanager
def _temporary_trust_env(enabled: bool) -> Iterator[None]:
    trust_vars = trusted_plugin_runtime_opt_in_vars()
    previous = {name: os.environ.get(name) for name in trust_vars}
    try:
        for name in trust_vars:
            os.environ.pop(name, None)
        if enabled:
            os.environ[trust_vars[0]] = "1"
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _probe_once(repo_root: Path, *, trust_enabled: bool) -> dict[str, Any]:
    with _temporary_trust_env(trust_enabled):
        config = RepoConfig.from_directory(repo_root)
        registry = PluginRegistry(repo_root=repo_root)
        registry.load_plugins(config)
        loaded_plugins = sorted(registry.plugins.keys())
        diagnostics = _build_plugin_diagnostics(config, loaded_plugins)
        loader_diagnostics = dict(getattr(registry, "last_load_diagnostics", {}) or {})
        return {
            "trust_env_applied": trust_enabled,
            "loaded_plugins": loaded_plugins,
            "loaded_count": len(loaded_plugins),
            "diagnostics": diagnostics,
            "loader_diagnostics": loader_diagnostics,
        }


def _apply_import_roots(import_roots: list[Path]) -> list[str]:
    applied: list[str] = []
    for import_root in import_roots:
        resolved = str(import_root.expanduser().resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
        applied.append(resolved)
    return applied


def probe_repo_plugins(repo_root: Path, *, import_roots: list[Path] | None = None) -> dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    applied_import_roots = _apply_import_roots(import_roots or [])
    return {
        "repo_root": str(repo_root),
        "applied_import_roots": applied_import_roots,
        "trusted_opt_in_vars": list(trusted_plugin_runtime_opt_in_vars()),
        "blocked_without_opt_in": _probe_once(repo_root, trust_enabled=False),
        "trusted_opt_in": _probe_once(repo_root, trust_enabled=True),
        "operator_workflow": {
            "start_runtime_env": {
                "SCRIBE_ROOT": str(repo_root),
                trusted_plugin_runtime_opt_in_vars()[0]: "1",
            },
            "import_roots": applied_import_roots,
            "restart_required": True,
            "doctor_check": "Run scribe_doctor and require plugins.loaded to include the expected repo-local stems.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe repo-local Scribe plugins without changing production defaults."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing .scribe/config/scribe.yaml and .scribe/plugins.",
    )
    parser.add_argument(
        "--require-loaded",
        action="store_true",
        help="Exit non-zero unless the trusted pass loads at least one plugin.",
    )
    parser.add_argument(
        "--import-root",
        type=Path,
        action="append",
        default=[],
        help="Extra source root to prepend to sys.path before loading repo plugins.",
    )
    args = parser.parse_args(argv)

    result = probe_repo_plugins(args.repo_root, import_roots=args.import_root)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")

    if args.require_loaded and result["trusted_opt_in"]["loaded_count"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
