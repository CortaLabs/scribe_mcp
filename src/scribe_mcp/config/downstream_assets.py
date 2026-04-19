"""Repo-local downstream asset seeding/adoption lifecycle helpers."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from scribe_mcp.config.paths import (
    downstream_seed_manifest_path,
    package_root,
    packaged_config_asset,
    packaged_template_asset,
)
from scribe_mcp.config.settings import PUBLIC_STORAGE_SETTINGS_CONTRACT

logger = logging.getLogger(__name__)

_SEED_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class DownstreamAsset:
    asset_id: str
    kind: str
    target: str
    seed_version: str
    source: Optional[str] = None
    generated_from: Optional[str] = None


@dataclass(frozen=True)
class SeedResult:
    seeded: int
    adopted: int
    refreshed: int
    skipped: int
    customized: int
    errors: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _seed_registry_path(repo_root: Path) -> Path:
    return repo_root / ".scribe" / "config" / "seed_registry.json"


def _load_manifest() -> List[DownstreamAsset]:
    manifest_path = downstream_seed_manifest_path()
    with open(manifest_path, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        return []

    result: List[DownstreamAsset] = []
    for raw_asset in assets:
        if not isinstance(raw_asset, dict):
            continue
        asset_id = str(raw_asset.get("asset_id") or "").strip()
        kind = str(raw_asset.get("kind") or "").strip()
        target = str(raw_asset.get("target") or "").strip()
        seed_version = str(raw_asset.get("seed_version") or "").strip()
        if not all((asset_id, kind, target, seed_version)):
            continue
        result.append(
            DownstreamAsset(
                asset_id=asset_id,
                kind=kind,
                target=target,
                seed_version=seed_version,
                source=raw_asset.get("source"),
                generated_from=raw_asset.get("generated_from"),
            )
        )
    return result


def _render_env_example() -> bytes:
    grouped_entries: Dict[str, List[str]] = {}
    for entry in PUBLIC_STORAGE_SETTINGS_CONTRACT:
        grouped_entries.setdefault(entry.classification, []).append(entry.name)

    ordered_classifications = [
        "canonical",
        "compatibility",
        "advanced/public",
        "advanced/non-release",
        "bootstrap-only",
    ]

    section_labels = {
        "canonical": "Canonical Runtime Settings",
        "compatibility": "Compatibility Aliases",
        "advanced/public": "Advanced Public Runtime Settings",
        "advanced/non-release": "Advanced Non-Release Settings",
        "bootstrap-only": "Bootstrap-Only Settings",
    }

    lines = [
        "# Auto-seeded from scribe_mcp settings contract.",
        "# Repo-specific runtime overrides belong in repo root .env.",
        "# Shared defaults belong in user/global runtime.env.",
        "# Runtime never auto-loads .scribe/.env.example.",
        "",
    ]
    for classification in ordered_classifications:
        names = grouped_entries.get(classification, [])
        if not names:
            continue
        lines.append(f"# [{section_labels[classification]}]")
        lines.append("")
        for entry in PUBLIC_STORAGE_SETTINGS_CONTRACT:
            if entry.classification != classification:
                continue
            lines.append(f"# {entry.description}")
            lines.append(f"{entry.name}=")
            lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _source_bytes(asset: DownstreamAsset) -> bytes:
    if asset.generated_from == "settings_contract":
        return _render_env_example()
    if not asset.source:
        raise ValueError(f"Asset '{asset.asset_id}' missing source")

    source = asset.source
    if source.startswith("templates/"):
        source_path = packaged_template_asset(source[len("templates/") :])
    elif source.startswith("config/"):
        source_path = packaged_config_asset(source[len("config/") :])
    else:
        source_path = (package_root() / source).resolve()

    with open(source_path, "rb") as handle:
        return handle.read()


def _load_registry(repo_root: Path) -> Dict[str, object]:
    registry_path = _seed_registry_path(repo_root)
    if not registry_path.exists():
        return {"version": _SEED_REGISTRY_VERSION, "assets": {}}

    try:
        with open(registry_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {"version": _SEED_REGISTRY_VERSION, "assets": {}}

    assets = payload.get("assets")
    if not isinstance(assets, dict):
        assets = {}

    return {"version": _SEED_REGISTRY_VERSION, "assets": assets}


def _write_registry(repo_root: Path, registry: Dict[str, object]) -> None:
    registry_path = _seed_registry_path(repo_root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, sort_keys=True)
        handle.write("\n")


def ensure_downstream_seed_assets(
    repo_root: Path,
    *,
    refresh: bool = False,
    force: bool = False,
    asset_ids: Optional[Iterable[str]] = None,
) -> SeedResult:
    """Seed/adopt/refresh downstream repo-owned assets.

    This helper is safe by default: existing customized files are not overwritten
    unless ``force=True``.
    """
    repo_root = repo_root.resolve()
    manifest_assets = _load_manifest()
    allowed_ids = set(asset_ids) if asset_ids else None
    assets = [a for a in manifest_assets if allowed_ids is None or a.asset_id in allowed_ids]

    registry = _load_registry(repo_root)
    registry_assets = registry.setdefault("assets", {})
    if not isinstance(registry_assets, dict):
        registry_assets = {}
        registry["assets"] = registry_assets

    seeded = adopted = refreshed = skipped = customized = errors = 0

    for asset in assets:
        target_path = (repo_root / asset.target).resolve()
        key = asset.target

        try:
            source_bytes = _source_bytes(asset)
            source_hash = _sha256(source_bytes)
        except Exception as exc:
            errors += 1
            logger.warning("Failed loading source for asset '%s': %s", asset.asset_id, exc)
            continue

        record_obj = registry_assets.get(key)
        record = record_obj if isinstance(record_obj, dict) else None

        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as handle:
                handle.write(source_bytes)
            applied_hash = source_hash
            registry_assets[key] = {
                "asset_id": asset.asset_id,
                "kind": asset.kind,
                "seed_version": asset.seed_version,
                "source_sha256": source_hash,
                "applied_sha256": applied_hash,
                "last_seeded_at": _now_iso(),
                "status": "seeded",
            }
            seeded += 1
            continue

        with open(target_path, "rb") as handle:
            current_bytes = handle.read()
        current_hash = _sha256(current_bytes)

        if record is None:
            status = "adopted" if current_hash == source_hash else "customized"
            registry_assets[key] = {
                "asset_id": asset.asset_id,
                "kind": asset.kind,
                "seed_version": asset.seed_version,
                "source_sha256": source_hash,
                "applied_sha256": current_hash,
                "last_seeded_at": _now_iso(),
                "status": status,
            }
            if status == "adopted":
                adopted += 1
            else:
                customized += 1
            continue

        applied_hash = str(record.get("applied_sha256") or "")
        current_matches_applied = bool(applied_hash and current_hash == applied_hash)

        if force or (refresh and current_matches_applied and current_hash != source_hash):
            with open(target_path, "wb") as handle:
                handle.write(source_bytes)
            registry_assets[key] = {
                "asset_id": asset.asset_id,
                "kind": asset.kind,
                "seed_version": asset.seed_version,
                "source_sha256": source_hash,
                "applied_sha256": source_hash,
                "last_seeded_at": _now_iso(),
                "status": "refreshed" if not force else "forced_refresh",
            }
            refreshed += 1
            continue

        if refresh and not current_matches_applied:
            # Preserve the last known applied baseline when classifying a file as customized.
            # This ensures future refreshes keep skipping local customizations unless force=True.
            next_applied_hash = applied_hash or current_hash
            registry_assets[key] = {
                "asset_id": asset.asset_id,
                "kind": asset.kind,
                "seed_version": asset.seed_version,
                "source_sha256": source_hash,
                "applied_sha256": next_applied_hash,
                "last_seeded_at": _now_iso(),
                "status": "customized",
            }
            customized += 1
            continue

        skipped += 1

    _write_registry(repo_root, registry)
    return SeedResult(
        seeded=seeded,
        adopted=adopted,
        refreshed=refreshed,
        skipped=skipped,
        customized=customized,
        errors=errors,
    )


__all__ = ["SeedResult", "ensure_downstream_seed_assets"]
