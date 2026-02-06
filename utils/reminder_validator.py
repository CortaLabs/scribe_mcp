"""Reminder validation and fallback system.

Ensures reminder configuration is valid and provides graceful fallbacks
when configuration files are missing or malformed.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional, Set

from .reminder_engine import ReminderEngine, ReminderInstance


class ReminderValidator:
    """Validates reminder configuration and provides fallbacks."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate main configuration structure."""
        self.errors.clear()
        self.warnings.clear()

        required_keys = ["behavior", "selection"]
        for key in required_keys:
            if key not in config:
                self.errors.append(f"Missing required config section: {key}")

        # Validate behavior section
        if "behavior" in config:
            behavior = config["behavior"]
            if "max_reminders_per_call" in behavior:
                if not isinstance(behavior["max_reminders_per_call"], int) or behavior["max_reminders_per_call"] < 1:
                    self.errors.append("max_reminders_per_call must be a positive integer")

            if "reminder_cooldown_minutes" in behavior:
                if not isinstance(behavior["reminder_cooldown_minutes"], int) or behavior["reminder_cooldown_minutes"] < 0:
                    self.warnings.append("reminder_cooldown_minutes should be a non-negative integer")

        # Validate selection section
        if "selection" in config:
            selection = config["selection"]
            if "priority_order" in selection:
                if not isinstance(selection["priority_order"], list):
                    self.errors.append("priority_order must be a list")

            if "category_weights" in selection:
                if not isinstance(selection["category_weights"], dict):
                    self.errors.append("category_weights must be a dictionary")

        return len(self.errors) == 0

    def validate_reminders(self, reminders: Dict[str, Any]) -> bool:
        """Validate reminder templates structure."""
        if "reminders" not in reminders:
            self.errors.append("Missing 'reminders' section in reminder file")
            return False

        reminder_sections = reminders["reminders"]
        if not isinstance(reminder_sections, dict):
            self.errors.append("'reminders' section must be a dictionary")
            return False

        required_template_fields = ["level", "emoji", "template"]
        valid_levels = {"info", "warning", "urgent", "error", "success"}

        for category, category_data in reminder_sections.items():
            if not isinstance(category_data, dict):
                self.errors.append(f"Category '{category}' must be a dictionary")
                continue

            for name, reminder_data in category_data.items():
                if not isinstance(reminder_data, dict):
                    self.errors.append(f"Reminder '{category}.{name}' must be a dictionary")
                    continue

                # Check required fields
                for field in required_template_fields:
                    if field not in reminder_data:
                        self.errors.append(f"Reminder '{category}.{name}' missing required field: {field}")

                # Validate level
                if "level" in reminder_data and reminder_data["level"] not in valid_levels:
                    self.warnings.append(
                        f"Reminder '{category}.{name}' has invalid level '{reminder_data['level']}'. "
                        f"Valid levels: {valid_levels}"
                    )

                # Check for template variables
                if "template" in reminder_data:
                    template = reminder_data["template"]
                    self._validate_template_variables(template, f"{category}.{name}")

                if "short_template" in reminder_data:
                    template = reminder_data["short_template"]
                    self._validate_template_variables(template, f"{category}.{name}")

        return len(self.errors) == 0

    def _validate_template_variables(self, template: str, reminder_name: str) -> None:
        """Validate template variable syntax."""
        try:
            # Simple validation - check for malformed { } brackets
            open_count = template.count("{")
            close_count = template.count("}")

            if open_count != close_count:
                self.errors.append(
                    f"Template '{reminder_name}' has mismatched braces: {open_count} open, {close_count} close"
                )

            # Check for empty variable names
            import re
            empty_vars = re.findall(r"{}|\{[^a-zA-Z_][^a-zA-Z0-9_]*\}", template)
            if empty_vars:
                self.warnings.append(
                    f"Template '{reminder_name}' has empty or invalid variables: {empty_vars}"
                )

        except Exception as e:
            self.warnings.append(f"Could not validate template '{reminder_name}': {e}")

    def validate_rules(self, rules: Dict[str, Any]) -> bool:
        """Validate reminder rules structure."""
        if "conditions" not in rules:
            self.warnings.append("No 'conditions' section in rules file")
            return True  # Not required

        conditions = rules["conditions"]
        if not isinstance(conditions, dict):
            self.errors.append("'conditions' section must be a dictionary")
            return False

        for rule_name, rule_data in conditions.items():
            if not isinstance(rule_data, dict):
                self.errors.append(f"Rule '{rule_name}' must be a dictionary")
                continue

            if "reminder_key" not in rule_data:
                self.warnings.append(f"Rule '{rule_name}' missing reminder_key")

            if "triggers" in rule_data:
                if not isinstance(rule_data["triggers"], list):
                    self.errors.append(f"Rule '{rule_name}' triggers must be a list")

        return len(self.errors) == 0

    def get_fallback_config(self) -> Dict[str, Any]:
        """Return minimal fallback configuration."""
        return {
            "version": "1.0.0",
            "language": "en-US",
            "fallback_language": "en-US",
            "behavior": {
                "max_reminders_per_call": 2,
                "teaching_enabled": True,
                "deduplication_enabled": True
            },
            "selection": {
                "priority_order": ["urgent", "warning", "info"],
                "category_weights": {
                    "urgent": 1000,
                    "warning": 700,
                    "info": 300
                },
                "tool_specific_limits": {
                    "append_entry": {"max_total": 1},
                    "list_projects": {"max_total": 2}
                }
            }
        }

    def get_fallback_reminders(self) -> Dict[str, Any]:
        """Return minimal fallback reminders."""
        return {
            "reminders": {
                "logging": {
                    "no_logs_yet": {
                        "level": "info",
                        "emoji": "📝",
                        "template": "No progress logs yet. Use append_entry to start the audit trail.",
                        "category": "logging"
                    },
                    "logging_stale": {
                        "level": "warning",
                        "emoji": "⏰",
                        "template": "It's been {minutes} minutes since the last log entry.",
                        "category": "logging"
                    }
                },
                "context": {
                    "project_context": {
                        "level": "info",
                        "emoji": "🎯",
                        "template": "Project: {project_name}",
                        "category": "context"
                    }
                },
                "teaching": {
                    "append_entry_tip": {
                        "level": "info",
                        "emoji": "💡",
                        "template": "💡 Use append_entry to log your progress and maintain an audit trail.",
                        "short_template": "💡 Log your progress with append_entry.",
                        "category": "teaching"
                    }
                }
            },
            "variables": {
                "time_units": {
                    "minutes": "{minutes} minute{s}",
                    "hours": "{hours} hour{s}"
                }
            },
            "formatting": {
                "date_format": "%Y-%m-%d %H:%M UTC",
                "use_short_templates": True
            }
        }


def validate_and_load_engine(config_path: Optional[str] = None) -> ReminderEngine:
    """Validate configuration and return a working reminder engine."""
    validator = ReminderValidator()
    engine = ReminderEngine(config_path)

    # Try to validate loaded configuration
    try:
        config_valid = validator.validate_config(engine.config)
        reminders_valid = validator.validate_reminders(engine.reminders)
        rules_valid = validator.validate_rules(engine.rules)

        if not config_valid or not reminders_valid:
            logger.warning("REMINDER CONFIGURATION VALIDATION FAILED - USING FALLBACKS")
            logger.warning("Configuration valid: %s", config_valid)
            logger.warning("Reminders valid: %s", reminders_valid)
            logger.warning("Rules valid: %s", rules_valid)

            if validator.errors:
                logger.warning("ERRORS FOUND:")
                for i, error in enumerate(validator.errors, 1):
                    logger.warning("  %d. %s", i, error)

            if validator.warnings:
                logger.warning("WARNINGS:")
                for i, warning in enumerate(validator.warnings, 1):
                    logger.warning("  %d. %s", i, warning)

            # Load fallback configuration
            logger.info("Loading fallback reminder configuration...")
            fallback_config = validator.get_fallback_config()
            fallback_reminders = validator.get_fallback_reminders()

            engine.config = fallback_config
            engine.reminders = fallback_reminders
            engine.variables = fallback_reminders.get("variables", {})
            engine.formatting = fallback_reminders.get("formatting", {})

            logger.warning("New project tutorial reminders will be limited due to configuration errors")
        else:
            logger.info("Reminder configuration loaded successfully")
            if validator.warnings:
                logger.warning("%d warnings found", len(validator.warnings))
                for i, warning in enumerate(validator.warnings, 1):
                    logger.warning("  %d. %s", i, warning)

    except Exception as e:
        logger.warning("Failed to validate reminder configuration: %s", e)
        logger.warning("Using minimal fallback configuration")

        # Emergency fallback
        engine.config = validator.get_fallback_config()
        engine.reminders = validator.get_fallback_reminders()
        engine.variables = engine.reminders.get("variables", {})
        engine.formatting = engine.reminders.get("formatting", {})

    return engine