from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

PUBLIC_SAFE_AGENT_SLUGS = (
    "scribe-architect",
    "scribe-bug-hunter",
    "scribe-coder",
    "scribe-doc-writer",
    "scribe-research-analyst",
    "scribe-review-agent",
    "scribe-security-agent",
)
PRIVATE_PUBLIC_ASSET_MARKERS = (
    "ask agent",
    "ask council",
    "ask self",
    "council",
    "council only",
    "coordinator wait loop",
    "end session",
    "hidden internal authority",
    "internal authority",
    "internal orchestration",
    "internal workflow",
    "open session",
    "operator escalation",
    "orchestration loop",
    "orchestrator",
    "private agent",
    "private escalation",
    "private internal",
    "seshat",
    "store memory",
    "team escalation",
    "teamcreate",
    "unpublished tool",
    "wait loop",
)


class CodexPluginProjectionError(ValueError):
    """Raised when the shipped public Codex plugin bundle is invalid."""


def _default_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def _quote_key(key: str) -> str:
    if key.replace("-", "").replace("_", "").isalnum():
        return key
    return json.dumps(key, ensure_ascii=False)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value: {type(value)!r}")


def _emit_table(lines: list[str], mapping: dict[str, Any], prefix: str | None = None) -> None:
    scalars: list[tuple[str, Any]] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    array_tables: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in mapping.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            array_tables.append((key, value))
        else:
            scalars.append((key, value))

    if prefix is not None and scalars:
        lines.append(f"[{prefix}]")

    for key, value in scalars:
        lines.append(f"{_quote_key(key)} = {_format_value(value)}")

    if scalars and (prefix is not None or tables or array_tables):
        lines.append("")

    for key, value in tables:
        child_prefix = f"{prefix}.{_quote_key(key)}" if prefix else _quote_key(key)
        before = len(lines)
        _emit_table(lines, value, child_prefix)
        if len(lines) > before and lines[-1] != "":
            lines.append("")

    for key, items in array_tables:
        child_prefix = f"{prefix}.{_quote_key(key)}" if prefix else _quote_key(key)
        for item in items:
            lines.append(f"[[{child_prefix}]]")
            for item_key, item_value in item.items():
                if isinstance(item_value, (dict, list)):
                    raise TypeError("Nested tables inside array tables are not supported in projection output")
                lines.append(f"{_quote_key(item_key)} = {_format_value(item_value)}")
            lines.append("")


def _dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    _emit_table(lines, data, None)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _load_catalog(plugin_root: Path) -> dict[str, Any]:
    catalog_path = plugin_root / "assets" / "agents.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodexPluginProjectionError(f"invalid Codex plugin catalog: {exc}") from exc

    if not isinstance(catalog, dict):
        raise CodexPluginProjectionError("invalid Codex plugin catalog: expected a JSON object")

    defaults = catalog.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise CodexPluginProjectionError("invalid Codex plugin catalog: 'defaults' must be an object")

    agents = catalog.get("agents")
    if not isinstance(agents, list):
        raise CodexPluginProjectionError("invalid Codex plugin catalog: 'agents' must be a list")

    seen: set[str] = set()
    normalized_agents: list[dict[str, str]] = []
    for entry in agents:
        if not isinstance(entry, dict):
            raise CodexPluginProjectionError("invalid Codex plugin catalog: each agent entry must be an object")

        name = entry.get("name")
        description = entry.get("description")
        if name not in PUBLIC_SAFE_AGENT_SLUGS:
            raise CodexPluginProjectionError(f"invalid Codex plugin catalog: unsupported public agent '{name}'")
        if name in seen:
            raise CodexPluginProjectionError(f"invalid Codex plugin catalog: duplicate agent '{name}'")
        if not isinstance(description, str) or not description.strip():
            raise CodexPluginProjectionError(
                f"invalid Codex plugin catalog: agent '{name}' is missing a non-empty description"
            )
        normalized_description = description.strip()
        _validate_public_asset_text(
            normalized_description,
            label=f"invalid Codex plugin catalog: agent description '{name}'",
        )

        seen.add(name)
        normalized_agents.append({"name": name, "description": normalized_description})

    missing = [name for name in PUBLIC_SAFE_AGENT_SLUGS if name not in seen]
    if missing:
        raise CodexPluginProjectionError(
            "invalid Codex plugin catalog: missing public agent entries: " + ", ".join(missing)
        )

    return {"defaults": defaults, "agents": normalized_agents}


def _load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    raw = config_path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    config = tomllib.loads(raw)
    if not isinstance(config, dict):
        raise CodexPluginProjectionError("invalid Codex config: expected a TOML table at the document root")
    return config


def _load_table(data: dict[str, Any], key: str, *, source_label: str) -> dict[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CodexPluginProjectionError(f"{source_label}: [{key}] must be a table")
    return dict(value)


def _normalized_policy_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _validate_public_asset_text(text: str, *, label: str) -> None:
    normalized_text = _normalized_policy_text(text)
    found = [
        marker for marker in PRIVATE_PUBLIC_ASSET_MARKERS if _normalized_policy_text(marker) in normalized_text
    ]
    if found:
        raise CodexPluginProjectionError(
            f"{label} contains private/council-only content: {', '.join(sorted(found))}"
        )


def _sync_text_file(*, target_path: Path, source_text: str) -> str:
    if target_path.exists():
        existing_text = target_path.read_text(encoding="utf-8")
        if existing_text == source_text:
            return "unchanged"
        return "preserved_existing"

    target_path.write_text(source_text, encoding="utf-8")
    return "created"


def _write_text_if_changed(*, target_path: Path, source_text: str) -> str:
    if target_path.exists():
        existing_text = target_path.read_text(encoding="utf-8")
        if existing_text == source_text:
            return "unchanged"
        target_path.write_text(source_text, encoding="utf-8")
        return "updated"

    target_path.write_text(source_text, encoding="utf-8")
    return "created"


def render_codex_projection_error(exc: Exception) -> str:
    if isinstance(exc, tomllib.TOMLDecodeError):
        return f"invalid Codex config: {exc}"
    if isinstance(exc, FileNotFoundError):
        return str(exc)
    if isinstance(exc, OSError):
        return f"filesystem failure during Codex projection: {exc}"
    return str(exc)


def _merge_projection(config_data: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config_data)

    features = _load_table(merged, "features", source_label="invalid Codex config")
    defaults = catalog.get("defaults", {})
    if not isinstance(defaults, dict):
        raise CodexPluginProjectionError("invalid Codex plugin catalog: 'defaults' must be an object")
    defaults_features = _load_table(defaults, "features", source_label="invalid Codex plugin catalog")
    for key, value in defaults_features.items():
        features.setdefault(key, value)
    if features:
        merged["features"] = features

    agents_table = _load_table(merged, "agents", source_label="invalid Codex config")
    defaults_agents = _load_table(defaults, "agents", source_label="invalid Codex plugin catalog")

    max_depth = defaults_agents.get("max_depth")
    if isinstance(max_depth, int):
        current_depth = agents_table.get("max_depth")
        agents_table["max_depth"] = max(current_depth, max_depth) if isinstance(current_depth, int) else max_depth

    max_threads = defaults_agents.get("max_threads")
    if isinstance(max_threads, int):
        current_threads = agents_table.get("max_threads")
        agents_table["max_threads"] = (
            max(current_threads, max_threads) if isinstance(current_threads, int) else max_threads
        )

    for agent in catalog.get("agents", []):
        name = agent["name"]
        existing_entry = agents_table.get(name)
        if existing_entry is None:
            agents_table[name] = {
                "config_file": f"agents/{name}.toml",
                "description": agent["description"],
            }
            continue

        if not isinstance(existing_entry, dict):
            raise CodexPluginProjectionError(f"invalid Codex config: [agents.{name}] must be a table")

        preserved_entry = dict(existing_entry)
        preserved_entry.setdefault("config_file", f"agents/{name}.toml")
        preserved_entry.setdefault("description", agent["description"])
        agents_table[name] = preserved_entry

    if agents_table:
        merged["agents"] = agents_table

    return merged


def project_codex_plugin(
    *,
    plugin_root: Path,
    codex_home: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    plugin_root = plugin_root.expanduser().resolve()
    if not (plugin_root / ".codex-plugin" / "plugin.json").exists():
        raise FileNotFoundError(f"Codex plugin manifest not found under {plugin_root}")
    if not (plugin_root / "skills" / "scribe-mcp-usage" / "SKILL.md").exists():
        raise FileNotFoundError(f"Codex plugin skill bundle is incomplete under {plugin_root}")

    codex_home = (codex_home or _default_codex_home()).expanduser().resolve()
    config_path = (config_path or (codex_home / "config.toml")).expanduser().resolve()
    agents_dir = codex_home / "agents"
    skills_dir = codex_home / "skills"
    projected_skill_dir = skills_dir / "scribe-mcp-usage"

    catalog = _load_catalog(plugin_root)

    agents_dir.mkdir(parents=True, exist_ok=True)
    projected_skill_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    projected_agent_configs: list[str] = []
    projected_agent_markdown: list[str] = []
    projected_agent_config_status: dict[str, str] = {}
    projected_agent_markdown_status: dict[str, str] = {}

    for agent in catalog.get("agents", []):
        name = agent["name"]
        template_path = plugin_root / "agents" / f"{name}.toml"
        markdown_path = plugin_root / "assets" / "agents" / f"{name}.md"
        if not template_path.exists():
            raise FileNotFoundError(f"Missing projection template: {template_path}")
        if not markdown_path.exists():
            raise FileNotFoundError(f"Missing agent instructions asset: {markdown_path}")

        target_toml = agents_dir / f"{name}.toml"
        target_md = agents_dir / f"{name}.md"
        template_text = template_path.read_text(encoding="utf-8")
        markdown_text = markdown_path.read_text(encoding="utf-8")
        _validate_public_asset_text(template_text, label=f"agent projection template '{name}'")
        _validate_public_asset_text(markdown_text, label=f"agent instructions asset '{name}'")

        projected_agent_config_status[str(target_toml)] = _sync_text_file(
            target_path=target_toml,
            source_text=template_text,
        )
        projected_agent_markdown_status[str(target_md)] = _sync_text_file(
            target_path=target_md,
            source_text=markdown_text,
        )
        projected_agent_configs.append(str(target_toml))
        projected_agent_markdown.append(str(target_md))

    source_skill = plugin_root / "skills" / "scribe-mcp-usage" / "SKILL.md"
    target_skill = projected_skill_dir / "SKILL.md"
    projected_skill_status = _sync_text_file(
        target_path=target_skill,
        source_text=source_skill.read_text(encoding="utf-8"),
    )

    merged_config = _merge_projection(_load_config(config_path), catalog)
    projected_config_text = _dump_toml(merged_config)
    config_status = _write_text_if_changed(
        target_path=config_path,
        source_text=projected_config_text,
    )

    return {
        "plugin_root": str(plugin_root),
        "codex_home": str(codex_home),
        "config_path": str(config_path),
        "projected_agent_configs": projected_agent_configs,
        "projected_agent_config_status": projected_agent_config_status,
        "projected_agent_markdown": projected_agent_markdown,
        "projected_agent_markdown_status": projected_agent_markdown_status,
        "projected_skills": [str(target_skill)],
        "projected_skill_status": {str(target_skill): projected_skill_status},
        "config_status": config_status,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="project-codex-plugin",
        description="Project the bundled Scribe Codex plugin into native Codex config/agent surfaces.",
    )
    parser.add_argument(
        "--plugin-root",
        type=Path,
        required=True,
        help="Path to the Codex plugin root (the directory containing .codex-plugin/plugin.json).",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=_default_codex_home(),
        help="Target CODEX_HOME directory. Defaults to $CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="Optional config.toml target. Defaults to <codex-home>/config.toml.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = project_codex_plugin(
            plugin_root=args.plugin_root,
            codex_home=args.codex_home,
            config_path=args.config_path,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {render_codex_projection_error(exc)}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
