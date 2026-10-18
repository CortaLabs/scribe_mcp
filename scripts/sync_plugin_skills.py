#!/usr/bin/env python3
"""Sync Scribe-owned generated skills into the shipped plugin trees.

The Claude/Codex plugins (``plugins/{claude,codex}/skills``) and the
wheel-vendored mirror (``src/scribe_mcp/plugins_bundle/{claude,codex}/skills``)
must ship every Scribe-relevant generated skill. Those skills are generated into
``.claude/skills`` and ``.codex/skills`` by ``council update``; without this
    script the plugin copies are hand-maintained and drift.

This module is the single, reusable source of truth for *which* skills ship and
*where* they ship. The shipped set is defined as a rule — glob ``scribe-*`` from
the canonical generated source minus a documented exclusion list — so a newly
added ``scribe-*`` skill ships automatically.

Conventions preserved from the existing plugin bundle:

* Plugin skills ship the *entire* generated skill directory. If a shipped skill
  carries ``assets/``, ``references/`` or ``scripts/`` and links them from
  ``SKILL.md``, those files ship with it so plugin links stay live. Skills whose
  generated source is ``SKILL.md``-only (e.g. ``scribe-onboarding``,
  ``scribe-integration``) naturally ship just that file.
* ``plugins_bundle/{claude,codex}`` stays byte-identical to ``plugins/{claude,
  codex}`` — the P6.6 drift guard (``tests/test_plugin_bundles.py``) enforces it.
  This is a copy into the bundle, not a move.

Usage::

    python scripts/sync_plugin_skills.py            # write/sync (default)
    python scripts/sync_plugin_skills.py --check     # verify only (CI/tests)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical generated skill sources (produced by ``council update``).
GENERATED_SKILL_DIRS: dict[str, Path] = {
    "claude": REPO_ROOT / ".claude" / "skills",
    "codex": REPO_ROOT / ".codex" / "skills",
}

# Shipped plugin destinations.
PLUGIN_SKILL_DIRS: dict[str, Path] = {
    "claude": REPO_ROOT / "plugins" / "claude" / "skills",
    "codex": REPO_ROOT / "plugins" / "codex" / "skills",
}

# Wheel-vendored mirror (byte-identical to the plugin trees above).
BUNDLE_SKILL_DIRS: dict[str, Path] = {
    "claude": REPO_ROOT / "src" / "scribe_mcp" / "plugins_bundle" / "claude" / "skills",
    "codex": REPO_ROOT / "src" / "scribe_mcp" / "plugins_bundle" / "codex" / "skills",
}

# The shipped skill set is the rule: every generated ``scribe-*`` skill EXCEPT
# the documented exclusions below ships into the plugins. Adding a new
# ``scribe-*`` skill to the generated source ships it automatically.
SHIPPED_SKILL_GLOB = "scribe-*"

# Explicitly not shipped in the standalone Scribe plugin:
#
# * scribe-rag-workflow is owned by Knowledge MCP (frontmatter ``owner:
#   knowledge-mcp``) and exported FROM Knowledge MCP. It is hard-coupled to
#   ``knowledge_mcp.operator_cli``, ``.knowledge/knowledge.yaml`` datasets, and
#   ``KNOWLEDGE_*`` environment variables.
# * scribe-mcp-usage is legacy broad-form usage documentation. The plugin
#   surface is intentionally kept lean; scribe-integration, scribe-onboarding,
#   and repository docs cover the supported shipped guidance.
EXCLUDED_SKILLS: frozenset[str] = frozenset({"scribe-mcp-usage", "scribe-rag-workflow"})

# A shipped skill must have this entry file in its source. The whole skill
# directory (every file beneath it) is what ships, not just this file.
SKILL_MANIFEST_FILE = "SKILL.md"


def _generated_source_available(channel: str) -> bool:
    """Return True when generated skills exist in this checkout.

    Clean CI checkouts intentionally do not track ``.claude``/``.codex`` because
    they are generated surfaces. In that environment the tracked plugin tree is
    the only available source for bundle parity checks.
    """

    source_dir = GENERATED_SKILL_DIRS[channel]
    if not source_dir.exists():
        return False
    return any(
        skill_dir.is_dir()
        and skill_dir.name not in EXCLUDED_SKILLS
        and (skill_dir / SKILL_MANIFEST_FILE).is_file()
        for skill_dir in source_dir.glob(SHIPPED_SKILL_GLOB)
    )


def _skill_names_from_source(source_dir: Path) -> list[str]:
    names: list[str] = []
    for skill_dir in sorted(source_dir.glob(SHIPPED_SKILL_GLOB)):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in EXCLUDED_SKILLS:
            continue
        if not (skill_dir / SKILL_MANIFEST_FILE).is_file():
            continue
        names.append(skill_dir.name)
    return names


def shipped_skill_names(channel: str) -> list[str]:
    """Return the sorted skill slugs that must ship for ``channel``.

    Normal developer checkouts use every generated ``scribe-*`` skill directory
    that has a ``SKILL.md`` and is not in :data:`EXCLUDED_SKILLS`.

    Clean CI checkouts do not have generated ``.claude``/``.codex`` surfaces, so
    they fall back to the tracked plugin tree and validate that the wheel bundle
    mirrors those committed assets instead of planning an empty shipped set.
    """

    if _generated_source_available(channel):
        return _skill_names_from_source(GENERATED_SKILL_DIRS[channel])
    return _skill_names_from_source(PLUGIN_SKILL_DIRS[channel])


def _planned_files(channel: str) -> dict[Path, bytes]:
    """Map every shipped destination file to its canonical source bytes.

    The full skill subtree ships: every file under ``<source>/<skill>/`` is
    mirrored (preserving structure) into both the plugin tree and the
    wheel-vendored bundle. SKILL.md-only generated skills naturally ship just
    that file.
    """

    plugin_dir = PLUGIN_SKILL_DIRS[channel]
    bundle_dir = BUNDLE_SKILL_DIRS[channel]
    generated_available = _generated_source_available(channel)
    source_dir = GENERATED_SKILL_DIRS[channel] if generated_available else plugin_dir

    planned: dict[Path, bytes] = {}
    for name in shipped_skill_names(channel):
        skill_source = source_dir / name
        for source_file in sorted(skill_source.rglob("*")):
            if not source_file.is_file():
                continue
            rel = source_file.relative_to(skill_source)
            source_bytes = source_file.read_bytes()
            if generated_available:
                planned[plugin_dir / name / rel] = source_bytes
            else:
                # In clean CI the tracked plugin file is the source of truth for
                # bundle parity. Include it in planned paths so it is not pruned.
                planned[source_file] = source_bytes
            planned[bundle_dir / name / rel] = source_bytes
    return planned


def _existing_skill_files(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path for path in directory.rglob("*") if path.is_file()}


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def sync(*, check: bool) -> int:
    """Sync (or verify) plugin + bundle skill trees against the generated source.

    Returns the number of files that are out of sync. In ``check`` mode nothing
    is written; in write mode files are created/updated and stale files pruned.
    """

    drift = 0
    for channel in GENERATED_SKILL_DIRS:
        planned = _planned_files(channel)
        planned_paths = set(planned)

        # Detect + apply additions/updates.
        for target, source_bytes in sorted(planned.items()):
            current = target.read_bytes() if target.exists() else None
            if current == source_bytes:
                continue
            drift += 1
            verb = "update" if current is not None else "create"
            print(f"[{channel}] {verb}: {_display_path(target)}")
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source_bytes)

        # Detect + prune stale skill files (e.g. a skill that was excluded or
        # renamed). Only the plugin + bundle skill trees are managed here.
        for managed_dir in (PLUGIN_SKILL_DIRS[channel], BUNDLE_SKILL_DIRS[channel]):
            for existing in sorted(_existing_skill_files(managed_dir)):
                if existing in planned_paths:
                    continue
                drift += 1
                print(f"[{channel}] prune: {_display_path(existing)}")
                if not check:
                    existing.unlink()
                    # Clean up now-empty directories up to (but not including)
                    # the managed skills dir — full subtrees may leave nested
                    # empty dirs (e.g. references/bridges/).
                    parent = existing.parent
                    while parent != managed_dir and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent

    if check and drift:
        print(
            f"\n{drift} plugin skill file(s) out of sync. "
            "Run: python scripts/sync_plugin_skills.py",
            file=sys.stderr,
        )
    elif not check and drift:
        print(f"\nSynced {drift} plugin skill file(s).")
    else:
        print("Plugin skills already in sync.")
    return drift


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync-plugin-skills",
        description=(
            "Sync Scribe-owned generated skills (scribe-* minus documented "
            "exclusions) into plugins/{claude,codex}/skills and the wheel-"
            "vendored plugins_bundle mirror. The full skill subtree ships "
            "(SKILL.md + references/scripts/assets); the bundle stays "
            "byte-identical to the plugin trees."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify sync without writing; exit non-zero if out of sync (CI/tests).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    drift = sync(check=args.check)
    return 1 if (args.check and drift) else 0


if __name__ == "__main__":
    raise SystemExit(main())
