#!/usr/bin/env python3
"""Copy the two authored public skills into plugin and wheel bundle trees."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SKILL_DIR = REPO_ROOT / "skills"
SHIPPED_SKILLS = ("scribe-integration", "scribe-onboarding")

PLUGIN_SKILL_DIRS: dict[str, Path] = {
    "claude": REPO_ROOT / "plugins" / "claude" / "skills",
    "codex": REPO_ROOT / "plugins" / "codex" / "skills",
}
BUNDLE_SKILL_DIRS: dict[str, Path] = {
    "claude": REPO_ROOT / "src" / "scribe_mcp" / "plugins_bundle" / "claude" / "skills",
    "codex": REPO_ROOT / "src" / "scribe_mcp" / "plugins_bundle" / "codex" / "skills",
}
SKILL_MANIFEST_FILE = "SKILL.md"


def _reject_symlinks(root: Path, label: str, *, descendants: bool = True) -> None:
    """Reject a managed root or any descendant that can escape its boundary."""
    try:
        relative = root.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError(f"{label} is outside the repository: {root}") from exc
    current = REPO_ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} contains a symlinked path: {current}")
    if root.exists() and not root.is_dir():
        raise ValueError(f"{label} must be a directory: {root}")
    if descendants and root.is_dir():
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"{label} contains a symlink: {path}")


def _source_files() -> dict[str, dict[Path, bytes]]:
    """Validate and read every canonical skill before a destination is planned."""
    _reject_symlinks(SOURCE_SKILL_DIR, "canonical skill root", descendants=False)
    if not SOURCE_SKILL_DIR.is_dir():
        raise ValueError(f"canonical skill root is missing: {SOURCE_SKILL_DIR}")

    sources: dict[str, dict[Path, bytes]] = {}
    for slug in SHIPPED_SKILLS:
        skill_dir = SOURCE_SKILL_DIR / slug
        _reject_symlinks(skill_dir, f"canonical skill {slug}")
        if not skill_dir.is_dir():
            raise ValueError(f"canonical skill directory is missing: {skill_dir}")
        manifest = skill_dir / SKILL_MANIFEST_FILE
        if not manifest.is_file():
            raise ValueError(f"required skill manifest is missing: {manifest}")
        files: dict[Path, bytes] = {}
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                files[path.relative_to(skill_dir)] = path.read_bytes()
        sources[slug] = files
    return sources


def shipped_skill_names(channel: str) -> list[str]:
    """Return the fixed public skill set for a supported destination channel."""
    if channel not in PLUGIN_SKILL_DIRS:
        raise ValueError(f"unsupported plugin channel: {channel}")
    _source_files()
    return list(SHIPPED_SKILLS)


def _planned_files(channel: str, sources: dict[str, dict[Path, bytes]]) -> dict[Path, bytes]:
    if channel not in PLUGIN_SKILL_DIRS:
        raise ValueError(f"unsupported plugin channel: {channel}")
    planned: dict[Path, bytes] = {}
    for slug in SHIPPED_SKILLS:
        for relative, content in sources[slug].items():
            planned[PLUGIN_SKILL_DIRS[channel] / slug / relative] = content
            planned[BUNDLE_SKILL_DIRS[channel] / slug / relative] = content
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
    """Plan all four mirrors, then check or apply changes without source fallback."""
    sources = _source_files()
    plans: dict[str, dict[Path, bytes]] = {}
    for channel in PLUGIN_SKILL_DIRS:
        for managed_dir in (PLUGIN_SKILL_DIRS[channel], BUNDLE_SKILL_DIRS[channel]):
            _reject_symlinks(managed_dir, "managed plugin skill destination")
        plans[channel] = _planned_files(channel, sources)

    planned_paths = set().union(*(set(plan) for plan in plans.values()))
    managed_dirs = [*PLUGIN_SKILL_DIRS.values(), *BUNDLE_SKILL_DIRS.values()]
    stale: set[Path] = set()
    for managed_dir in managed_dirs:
        stale.update(_existing_skill_files(managed_dir) - planned_paths)

    drift = 0
    for plan in plans.values():
        for target, source_bytes in sorted(plan.items()):
            current = target.read_bytes() if target.exists() else None
            if current != source_bytes:
                drift += 1
                verb = "update" if current is not None else "create"
                print(f"[{verb}] {_display_path(target)}")
    for path in sorted(stale):
        drift += 1
        print(f"[prune] {_display_path(path)}")

    if check or drift == 0:
        if check and drift:
            print(f"\n{drift} plugin skill file(s) out of sync.", file=sys.stderr)
        elif not drift:
            print("Plugin skills already in sync.")
        return drift

    for plan in plans.values():
        for target, source_bytes in sorted(plan.items()):
            if target.exists() and target.read_bytes() == source_bytes:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes)
    for path in sorted(stale):
        path.unlink()
        parent = path.parent
        while parent not in managed_dirs and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    print(f"\nSynced {drift} plugin skill file(s).")
    return drift


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync-plugin-skills",
        description="Sync authored public Scribe skills into plugin and wheel bundle trees.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify sync without writing; exit non-zero if out of sync.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        drift = sync(check=args.check)
    except (OSError, ValueError) as exc:
        print(f"Cannot sync plugin skills: {exc}", file=sys.stderr)
        return 2
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
