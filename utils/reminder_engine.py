"""Advanced reminder engine with localization and intelligent selection.

This module provides a sophisticated reminder system that:
- Loads reminders from configurable JSON files
- Supports multiple languages with fallbacks
- Implements intelligent reminder selection and deduplication
- Provides progressive teaching with cooldown periods
- Uses variable substitution for dynamic content
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

from scribe_mcp.config.settings import settings


@dataclass
class ReminderInstance:
    """A single reminder instance with metadata."""
    key: str
    level: str
    emoji: str
    message: str
    context: Optional[str] = None
    category: str = "general"
    score: int = 3
    variables: Dict[str, Any] = field(default_factory=dict)
    tools_suppressed: List[str] = field(default_factory=list)
    cooldown_minutes: int = 0
    last_shown: Optional[datetime] = None


@dataclass
class ReminderContext:
    """Context for reminder generation."""
    tool_name: str
    project_name: Optional[str]
    project_root: Optional[str]
    agent_id: Optional[str]
    session_id: Optional[str] = None
    total_entries: int = 0
    minutes_since_log: Optional[float] = None
    last_log_time: Optional[datetime] = None
    docs_status: Dict[str, str] = field(default_factory=dict)
    docs_changed: List[str] = field(default_factory=list)
    current_phase: Optional[str] = None
    session_age_minutes: Optional[float] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    operation_status: Optional[str] = None  # "success", "failure", or None for neutral


@dataclass
class ReminderHistory:
    """Tracks recently shown reminders for deduplication."""
    reminder_hashes: Dict[str, datetime] = field(default_factory=dict)
    teaching_sessions: Dict[str, int] = field(default_factory=dict)
    last_cleanup: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ReminderEngine:
    """Advanced reminder engine with localization and intelligent selection."""

    def __init__(self, config_path: Optional[str] = None, storage: Optional[Any] = None):
        # Resolve config path: try repo .scribe/config/ first, fallback to package config/
        if config_path is None:
            config_path = self._resolve_config_path()
        self.config_path = config_path
        self.reminders_path: Optional[Path] = None
        self.rules_path: Optional[Path] = None

        self.config: Dict[str, Any] = {}
        self.reminders: Dict[str, Any] = {}
        self.rules: Dict[str, Any] = {}
        self.variables: Dict[str, Any] = {}
        self.formatting: Dict[str, Any] = {}

        self.language = "en-US"
        self.fallback_language = "en-US"

        self.history = ReminderHistory()
        self.storage = storage  # Injected storage backend for DB-based cooldown tracking

        self._load_configuration()

    def _resolve_config_path(self) -> str:
        """Resolve reminder config path with repo .scribe/config/ priority.

        Search order:
        1. repo_root/.scribe/config/reminder_config.json (repo-specific)
        2. package config/reminder_config.json (package defaults)
        """
        # Try repo .scribe/config/ first
        try:
            from scribe_mcp.config.repo_config import RepoDiscovery
            repo_root = RepoDiscovery.find_repo_root()
            if repo_root:
                repo_config = repo_root / ".scribe" / "config" / "reminder_config.json"
                if repo_config.exists():
                    return str(repo_config)
        except Exception:
            pass  # Fall through to package default

        # Fallback to package config (resolved relative to package, not CWD)
        package_config = settings.project_root / "config" / "reminder_config.json"
        return str(package_config)

    def _load_configuration(self) -> None:
        """Load all configuration files."""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                self.config = json.loads(config_file.read_text(encoding="utf-8"))
                self.language = self.config.get("language", "en-US")
                self.fallback_language = self.config.get("fallback_language", "en-US")

                base_path = config_file.parent
                self.reminders_path = base_path / self.config.get("reminder_paths", {}).get("templates", "reminders")
                self.rules_path = base_path / self.config.get("reminder_paths", {}).get("rules", "reminder_rules.json")

            self._load_reminders()
            self._load_rules()

        except Exception as e:
            print(f"Warning: Failed to load reminder configuration: {e}")
            self._load_fallback_reminders()

    def _load_reminders(self) -> None:
        """Load reminder templates for current language."""
        if not self.reminders_path:
            return

        # Try to load preferred language
        lang_file = self.reminders_path / f"{self.language}.json"
        if lang_file.exists():
            self.reminders = json.loads(lang_file.read_text(encoding="utf-8"))
            self.variables = self.reminders.get("variables", {})
            self.formatting = self.reminders.get("formatting", {})
            return

        # Fallback to default language
        fallback_file = self.reminders_path / f"{self.fallback_language}.json"
        if fallback_file.exists():
            self.reminders = json.loads(fallback_file.read_text(encoding="utf-8"))
            self.variables = self.reminders.get("variables", {})
            self.formatting = self.reminders.get("formatting", {})

    def _load_rules(self) -> None:
        """Load reminder selection rules."""
        if not self.rules_path or not self.rules_path.exists():
            return

        self.rules = json.loads(self.rules_path.read_text(encoding="utf-8"))

    def _load_fallback_reminders(self) -> None:
        """Load minimal fallback reminders."""
        self.reminders = {
            "reminders": {
                "logging": {
                    "no_logs_yet": {
                        "level": "info",
                        "emoji": "📝",
                        "template": "No progress logs yet. Use append_entry to start the audit trail.",
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
                }
            }
        }
        self.config = {
            "behavior": {"max_reminders_per_call": 2},
            "selection": {"priority_order": ["urgent", "warning", "info"]}
        }

    def _cleanup_history(self) -> None:
        """Clean up old reminder history."""
        now = datetime.now(timezone.utc)
        cleanup_after_hours = self.config.get("tracking", {}).get("cleanup_after_hours", 24)
        cutoff = now - timedelta(hours=cleanup_after_hours)

        # Remove old reminder hashes
        self.history.reminder_hashes = {
            h: t for h, t in self.history.reminder_hashes.items()
            if t > cutoff
        }

        # Remove old teaching sessions
        self.history.teaching_sessions = {
            k: v for k, v in self.history.teaching_sessions.items()
            if v > 0  # Sessions reset when count reaches 0
        }

        self.history.last_cleanup = now

    def reset_cooldowns(self, *, project_root: str, agent_id: Optional[str] = None) -> int:
        prefix = f"{project_root}|"
        if agent_id:
            prefix = f"{project_root}|{agent_id}|"

        keys = [k for k in self.history.reminder_hashes.keys() if k.startswith(prefix)]
        for key in keys:
            self.history.reminder_hashes.pop(key, None)
        return len(keys)

    def _get_reminder_hash(self, reminder_key: str, variables: Dict[str, Any]) -> str:
        """Generate hash for reminder deduplication.

        Uses session_id when use_session_aware_hashes flag is enabled.
        Falls back to legacy format for backward compatibility.
        """
        use_session_hash = getattr(settings, 'use_session_aware_hashes', False)
        session_id = str(variables.get("session_id") or "")

        if use_session_hash and session_id:
            # Session-aware hash (new behavior)
            parts = [
                session_id,
                str(variables.get("project_root") or ""),
                str(variables.get("agent_id") or ""),
                str(variables.get("tool_name") or ""),
                reminder_key
            ]
        else:
            # Legacy hash (backward compatible)
            parts = [
                str(variables.get("project_root") or ""),
                str(variables.get("agent_id") or ""),
                str(variables.get("tool_name") or ""),
                reminder_key
            ]

        return hashlib.md5("|".join(parts).encode()).hexdigest()

    async def _should_show_reminder(self, reminder: ReminderInstance, context: ReminderContext) -> bool:
        """Check if reminder should be shown based on rules.

        Failure-priority logic: When operation_status == "failure", cooldowns are bypassed
        to ensure critical reminders are shown on tool failures.
        """

        # Tool suppression
        if context.tool_name in reminder.tools_suppressed:
            return False

        # Failure-priority logic: bypass cooldowns on failures
        is_failure = context.operation_status == "failure"

        # Cooldown check (bypassed for failures)
        if not is_failure:
            cooldown_minutes = reminder.cooldown_minutes
            if cooldown_minutes <= 0 and reminder.category == "teaching":
                cooldown_minutes = int(self.config.get("behavior", {}).get("default_teaching_cooldown_minutes", 10))

            if cooldown_minutes > 0:
                reminder_hash = self._get_reminder_hash(reminder.key, reminder.variables)

                # Use DB if available, fallback to in-memory
                if self.storage:
                    session_id = reminder.variables.get("session_id", "")
                    in_cooldown = await self.storage.check_reminder_cooldown(
                        session_id=session_id,
                        reminder_hash=reminder_hash,
                        cooldown_minutes=cooldown_minutes
                    )
                    if in_cooldown:
                        return False
                else:
                    # Fallback to in-memory (legacy)
                    last_shown = self.history.reminder_hashes.get(reminder_hash)
                    if last_shown:
                        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
                        if last_shown > cooldown_cutoff:
                            return False

        # Teaching session limits (bypassed for failures)
        if not is_failure and reminder.category == "teaching":
            session_key = f"{context.tool_name}:{reminder.key}"
            sessions_used = self.history.teaching_sessions.get(session_key, 0)
            max_sessions = self.config.get("behavior", {}).get("max_teaching_reminders_per_session", 3)
            if sessions_used >= max_sessions:
                return False

        return True

    def _format_reminder(self, reminder: ReminderInstance, use_short: bool = True) -> ReminderInstance:
        """Apply variable substitution and formatting to reminder."""
        # Choose template
        template_key = "short_template" if use_short and "short_template" in reminder.variables else "template"
        template = reminder.variables.get(template_key, reminder.message)

        # Variable substitution
        try:
            formatted_message = template.format(**reminder.variables)
            if reminder.context:
                formatted_context = reminder.context.format(**reminder.variables)
                reminder.context = formatted_context
        except KeyError as e:
            # Fallback to original template if variable missing
            formatted_message = reminder.message

        reminder.message = formatted_message
        return reminder

    def _evaluate_condition(self, condition: str, context: ReminderContext) -> bool:
        """Evaluate a condition string against context."""
        # Simple condition evaluation (can be extended)
        if condition == "no_log_entries":
            return context.total_entries == 0
        elif condition.startswith("minutes_since_log > "):
            threshold = int(condition.split()[-1])
            return (context.minutes_since_log or 0) > threshold
        elif condition == "docs_missing":
            return any(status == "missing" for status in context.docs_status.values())
        elif condition.startswith("tool="):
            return context.tool_name == condition.split("=")[1]
        elif condition.startswith("action="):
            return context.variables.get("action") == condition.split("=")[1]
        elif condition.startswith("scaffold="):
            expected = condition.split("=")[1].strip().lower()
            actual = context.variables.get("scaffold")
            if isinstance(actual, bool):
                actual_value = "true" if actual else "false"
            else:
                actual_value = str(actual).strip().lower()
            return actual_value == expected
        elif condition == "always":
            return True

        return False

    def _build_variables(self, context: ReminderContext) -> Dict[str, Any]:
        """Build variable dictionary for template substitution."""
        now_utc = datetime.now(timezone.utc)
        date_format = self.formatting.get("date_format", "%Y-%m-%d %H:%M UTC")

        variables = {
            "project_name": context.project_name or "No project",
            "project_root": context.project_root or "",
            "agent_id": context.agent_id or "",
            "session_id": context.session_id or "",
            "tool_name": context.tool_name,
            "total_entries": context.total_entries,
            "minutes": int(context.minutes_since_log or 0),
            "hours": int((context.minutes_since_log or 0) / 60),
            "days": int((context.minutes_since_log or 0) / 1440),
            "now_utc": now_utc.strftime(date_format),
            "now_iso_utc": now_utc.isoformat(),
            "date_utc": now_utc.strftime("%Y-%m-%d"),
            "time_utc": now_utc.strftime("%H:%M:%S UTC"),
        }

        # Time formatting
        if context.last_log_time:
            variables["last_log"] = context.last_log_time.strftime(
                date_format
            )
        else:
            variables["last_log"] = "no logs yet"

        # Session info
        if context.session_age_minutes is not None:
            variables["session_age"] = f"{context.session_age_minutes:.1f} min"
        else:
            variables["session_age"] = ""

        # Phase info
        if context.current_phase:
            variables["current_phase"] = context.current_phase
            variables["phase_info"] = f" | Phase: {context.current_phase}"
            variables["phase_suffix"] = f" (Phase: {context.current_phase})"
        else:
            variables["phase_info"] = ""
            variables["phase_suffix"] = ""

        # Documentation info
        missing_docs = [name for name, status in context.docs_status.items() if status == "missing"]
        if missing_docs:
            variables["missing_docs"] = ", ".join(missing_docs[:3])
            if len(missing_docs) > 3:
                variables["missing_docs"] += f" (+{len(missing_docs) - 3} more)"

        if context.docs_changed:
            variables["changed_docs"] = ", ".join(context.docs_changed[:3])

        # Merge with context variables
        variables.update(context.variables)

        return variables

    async def generate_reminders(self, context: ReminderContext) -> List[ReminderInstance]:
        """Generate relevant reminders for the given context."""
        self._cleanup_history()

        candidates = []

        # Evaluate conditions and generate reminder candidates
        if "conditions" in self.rules:
            for rule_name, rule_data in self.rules["conditions"].items():
                if self._evaluate_rule_conditions(rule_data.get("triggers", []), context):
                    reminder = self._create_reminder_from_rule(rule_name, rule_data, context)
                    if reminder:
                        candidates.append(reminder)

        # Add teaching reminders
        teaching_reminders = await self._generate_teaching_reminders(context)
        candidates.extend(teaching_reminders)

        # Filter and select best reminders
        selected = await self._select_reminders(candidates, context)

        # Track shown reminders
        for reminder in selected:
            reminder_hash = self._get_reminder_hash(reminder.key, reminder.variables)

            # Use DB if available (best-effort; reminders should never block tool execution)
            if self.storage:
                session_id = reminder.variables.get("session_id", "")
                project_root = reminder.variables.get("project_root", "")
                agent_id = reminder.variables.get("agent_id", "")
                tool_name = reminder.variables.get("tool_name", "")

                try:
                    await self.storage.record_reminder_shown(
                        session_id=session_id,
                        reminder_hash=reminder_hash,
                        project_root=project_root,
                        agent_id=agent_id,
                        tool_name=tool_name,
                        reminder_key=reminder.key,
                        operation_status=context.operation_status or "neutral",
                    )
                except Exception:
                    # Fallback to in-memory (legacy) on storage errors.
                    self.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc)
            else:
                # Fallback to in-memory (legacy)
                self.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc)

            if reminder.category == "teaching":
                session_key = f"{context.tool_name}:{reminder.key}"
                self.history.teaching_sessions[session_key] = self.history.teaching_sessions.get(session_key, 0) + 1

        # Apply formatting
        use_short = self.config.get("formatting", {}).get("use_short_templates", True)
        selected = [self._format_reminder(r, use_short) for r in selected]

        return selected

    def _evaluate_rule_conditions(self, triggers: List[str], context: ReminderContext) -> bool:
        """Evaluate if all trigger conditions are met."""
        for trigger in triggers:
            if not self._evaluate_condition(trigger, context):
                return False
        return True

    def _create_reminder_from_rule(self, rule_name: str, rule_data: Dict[str, Any], context: ReminderContext) -> Optional[ReminderInstance]:
        """Create a reminder instance from rule data."""
        reminder_key = rule_data.get("reminder_key")
        if not reminder_key:
            return None

        # Navigate reminder structure
        category, name = reminder_key.split(".", 1) if "." in reminder_key else ("general", reminder_key)
        reminder_templates = self.reminders.get("reminders", {}).get(category, {}).get(name)

        if not reminder_templates:
            return None

        variables = self._build_variables(context)
        variable_mapping = rule_data.get("variable_mapping", {})
        for key, source in variable_mapping.items():
            variables[key] = variables.get(source, "")

        return ReminderInstance(
            key=reminder_key,
            level=reminder_templates.get("level", "info"),
            emoji=reminder_templates.get("emoji", "ℹ️"),
            message=reminder_templates.get("template", ""),
            context=reminder_templates.get("context"),
            category=reminder_templates.get("category", "general"),
            variables=variables,
            tools_suppressed=reminder_templates.get("tools_suppressed", []),
            cooldown_minutes=rule_data.get("cooldown_minutes", 0)
        )

    async def _generate_teaching_reminders(self, context: ReminderContext) -> List[ReminderInstance]:
        """Generate teaching reminders based on context."""
        teaching = []

        if not self.config.get("behavior", {}).get("teaching_enabled", True):
            return teaching

        teaching_rules = self.rules.get("teaching_rules", {})
        for rule_name, rule_data in teaching_rules.items():
            if self._evaluate_rule_conditions(rule_data.get("triggers", []), context):
                reminder = self._create_reminder_from_rule(rule_name, rule_data, context)
                if reminder and await self._should_show_reminder(reminder, context):
                    teaching.append(reminder)

        return teaching

    async def _select_reminders(self, candidates: List[ReminderInstance], context: ReminderContext) -> List[ReminderInstance]:
        """Select the best reminders based on priority and rules."""
        if not candidates:
            return []

        # Filter out suppressed reminders
        filtered = []
        for r in candidates:
            if await self._should_show_reminder(r, context):
                filtered.append(r)

        # Sort by priority
        priority_order = self.config.get("selection", {}).get("priority_order", [])
        category_weights = self.config.get("selection", {}).get("category_weights", {})

        def get_priority(reminder: ReminderInstance) -> int:
            # Try priority order first
            if reminder.key in priority_order:
                return priority_order.index(reminder.key)
            # Fall back to category weight
            return category_weights.get(reminder.level, 999)

        filtered.sort(key=get_priority)

        # Apply tool-specific limits
        tool_limits = self.config.get("selection", {}).get("tool_specific_limits", {})
        tool_config = tool_limits.get(context.tool_name, {})
        max_total = tool_config.get("max_total", self.config.get("behavior", {}).get("max_reminders_per_call", 2))
        allowed_categories = tool_config.get("categories", ["all"])

        if allowed_categories != ["all"]:
            filtered = [r for r in filtered if r.category in allowed_categories]

        return filtered[:max_total]

    def to_dict_list(self, reminders: List[ReminderInstance]) -> List[Dict[str, Any]]:
        """Convert reminder instances to dictionary format for API response."""
        return [
            {
                "level": r.level,
                "score": r.score,
                "emoji": r.emoji,
                "message": r.message,
                "category": r.category,
                "tone": "neutral",  # Can be made configurable
            } | ({"context": r.context} if r.context else {})
            for r in reminders
        ]
