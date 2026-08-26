"""Regression coverage for packaged reminder templates and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib

import pytest

from scribe_mcp.utils.reminder_validator import (
    ReminderValidator,
    validate_and_load_engine,
)
from scribe_mcp.utils import reminder_validator


pytestmark = pytest.mark.regression


def test_package_data_includes_nested_reminder_templates() -> None:
    """The wheel manifest must include locale JSON below config/reminders/."""
    repo_root = Path(__file__).resolve().parent.parent
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))

    package_data = project["tool"]["setuptools"]["package-data"]["scribe_mcp"]

    assert "config/reminders/*.json" in package_data


def test_missing_templates_report_selected_paths_and_independent_rules_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A template failure must not make an independently valid rules file false."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "reminder_config.json"
    rules_path = config_dir / "reminder_rules.json"
    template_path = config_dir / "reminders" / "en-US.json"

    config_path.write_text(
        json.dumps(
            {
                "language": "en-US",
                "fallback_language": "en-US",
                "behavior": {},
                "selection": {},
                "reminder_paths": {
                    "templates": "reminders",
                    "rules": rules_path.name,
                },
            }
        ),
        encoding="utf-8",
    )
    rules_path.write_text(json.dumps({"conditions": {}}), encoding="utf-8")

    messages: list[str] = []

    def capture_warning(message: str, *args: object) -> None:
        messages.append(message % args if args else message)

    monkeypatch.setattr(reminder_validator.logger, "warning", capture_warning)

    engine = validate_and_load_engine(str(config_path))
    package_origin = Path(__file__).resolve().parent.parent / "src" / "scribe_mcp"

    assert "Configuration valid: True" in messages
    assert "Reminders valid: False" in messages
    assert "Rules valid: True" in messages
    assert any(f"Configuration path: {config_path}" == message for message in messages)
    assert any(f"Template path: {template_path}" == message for message in messages)
    assert any(f"Rules path: {rules_path}" == message for message in messages)
    assert any(f"Package origin: {package_origin}" == message for message in messages)
    assert engine.reminders == ReminderValidator().get_fallback_reminders()
