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
import logging
import os
import time

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

from scribe_mcp.config.settings import settings
from scribe_mcp.config.paths import config_data_dir, package_root


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
    source: Optional[str] = None
    recommended_action: Optional[str] = None
    available_actions: List[str] = field(default_factory=list)
    suggested_tool: Optional[str] = None
    blocker_codes: List[str] = field(default_factory=list)


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
        """Resolve reminder config path with robust fallbacks.

        Search order:
        1. repo_root/.scribe/config/reminder_config.json (repo override)
        2. <settings.project_root>/config/reminder_config.json (workspace override)
        3. packaged config/reminder_config.json (always-available default)
        """
        # 1) Repo override under .scribe/config
        try:
            from scribe_mcp.config.repo_config import RepoDiscovery

            repo_root = RepoDiscovery.find_repo_root()
            if repo_root:
                repo_config = repo_root / ".scribe" / "config" / "reminder_config.json"
                if repo_config.exists():
                    return str(repo_config)
        except Exception:
            pass

        # 2) Workspace override under settings.project_root/config
        project_root = getattr(settings, "project_root", None)
        if isinstance(project_root, Path):
            workspace_root = project_root
        elif isinstance(project_root, str) and project_root:
            workspace_root = Path(project_root)
        else:
            workspace_root = None

        if workspace_root is not None:
            workspace_config = workspace_root / "config" / "reminder_config.json"
            if workspace_config.exists():
                return str(workspace_config)

        # 3) Packaged defaults under src/scribe_mcp/config
        packaged_config = config_data_dir() / "reminder_config.json"
        if packaged_config.exists():
            return str(packaged_config)

        # Last-resort fallback for compatibility with unusual test harnesses.
        return str(package_root() / "config" / "reminder_config.json")

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
            logger.warning("Failed to load reminder configuration: %s", e)
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

    async def get_reminder_history(
        self,
        *,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return reminder history from storage when available."""
        normalized_limit = max(1, min(int(limit), 200))

        if self.storage and hasattr(self.storage, "get_reminder_history"):
            try:
                history = await self.storage.get_reminder_history(
                    project_root=project_root,
                    agent_id=agent_id,
                    category=category,
                    limit=normalized_limit,
                )
                if isinstance(history, list) and history:
                    return history
            except Exception:
                # Fall back to in-memory snapshots when storage is unavailable.
                pass

        # In-memory fallback is hash-only and cannot represent full metadata.
        items: List[Dict[str, Any]] = []
        for reminder_hash, shown_at in sorted(
            self.history.reminder_hashes.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:normalized_limit]:
            items.append(
                {
                    "reminder_hash": reminder_hash,
                    "shown_at": shown_at.isoformat(),
                    "source": "memory",
                }
            )
        return items

    async def reset_history(
        self,
        *,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> int:
        """Clear reminder history rows, preferring backend storage."""
        deleted_db = 0
        if self.storage and hasattr(self.storage, "clear_reminder_history"):
            try:
                deleted_db = int(
                    await self.storage.clear_reminder_history(
                        project_root=project_root,
                        agent_id=agent_id,
                    )
                )
            except Exception:
                pass

        cleared_memory = len(self.history.reminder_hashes)
        self.history.reminder_hashes.clear()
        self.history.teaching_sessions.clear()
        if deleted_db > 0:
            return deleted_db
        return cleared_memory

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

    def _resolve_cooldown_minutes(self, reminder: ReminderInstance) -> int:
        """Resolve effective cooldown minutes for a reminder."""
        cooldown_minutes = reminder.cooldown_minutes
        if cooldown_minutes <= 0 and reminder.category == "teaching":
            cooldown_minutes = int(self.config.get("behavior", {}).get("default_teaching_cooldown_minutes", 10))

        # Per-project cooldown floor (configure_reminders contract): when an
        # operator sets cooldown_minutes for a project, it applies as a minimum
        # so the same reminder is not re-emitted within that window, even for
        # rules whose own cooldown is 0.
        project_cooldown = reminder.variables.get("main_reminder_cooldown_minutes")
        if isinstance(project_cooldown, int) and project_cooldown > 0:
            cooldown_minutes = max(cooldown_minutes, project_cooldown)

        return cooldown_minutes

    def _is_in_memory_cooldown(self, reminder_hash: str, cooldown_minutes: int) -> bool:
        """Check in-memory cooldown cache."""
        last_shown = self.history.reminder_hashes.get(reminder_hash)
        if not last_shown:
            return False
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        return last_shown > cooldown_cutoff

    def _teaching_limit_reached(self, reminder: ReminderInstance, context: ReminderContext) -> bool:
        """Check whether teaching session quota has been exhausted."""
        if reminder.category != "teaching":
            return False
        session_key = f"{context.tool_name}:{reminder.key}"
        sessions_used = self.history.teaching_sessions.get(session_key, 0)
        max_sessions = self.config.get("behavior", {}).get("max_teaching_reminders_per_session", 3)
        return sessions_used >= max_sessions

    def _should_show_reminder(self, reminder: ReminderInstance, context: ReminderContext) -> bool:
        """Synchronous compatibility check used by tests and in-memory flows."""
        if context.tool_name in reminder.tools_suppressed:
            return False

        is_failure = context.operation_status == "failure"
        if not is_failure:
            cooldown_minutes = self._resolve_cooldown_minutes(reminder)
            if cooldown_minutes > 0:
                reminder_hash = self._get_reminder_hash(reminder.key, reminder.variables)
                if self._is_in_memory_cooldown(reminder_hash, cooldown_minutes):
                    return False

            if self._teaching_limit_reached(reminder, context):
                return False

        return True

    async def _should_show_reminder_async(self, reminder: ReminderInstance, context: ReminderContext) -> bool:
        """Async variant that uses DB-backed cooldown checks when storage is available."""
        if context.tool_name in reminder.tools_suppressed:
            return False

        is_failure = context.operation_status == "failure"
        if not is_failure:
            cooldown_minutes = self._resolve_cooldown_minutes(reminder)
            if cooldown_minutes > 0:
                reminder_hash = self._get_reminder_hash(reminder.key, reminder.variables)

                if self.storage:
                    session_id = reminder.variables.get("session_id", "")
                    in_cooldown = await self.storage.check_reminder_cooldown(
                        session_id=session_id,
                        reminder_hash=reminder_hash,
                        cooldown_minutes=cooldown_minutes,
                    )
                    if in_cooldown:
                        return False
                elif self._is_in_memory_cooldown(reminder_hash, cooldown_minutes):
                    return False

            if self._teaching_limit_reached(reminder, context):
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

    # Maps a doc-status condition keyword to the docs_status key it inspects.
    _DOC_STATUS_CONDITIONS: Dict[str, str] = {
        "architecture": "architecture",
        "phase_plan": "phase_plan",
        "checklist": "checklist",
    }

    def _resolve_numeric_value(self, name: str, context: ReminderContext) -> Optional[float]:
        """Resolve the left-hand side of a ``<var> > N`` condition.

        Pulls only from existing ReminderContext data: dedicated fields first,
        then the free-form ``variables`` dict that tool callers populate.
        Returns ``None`` when the variable is absent so the comparison fails
        closed rather than firing on a missing value.
        """
        if name == "minutes_since_log":
            return context.minutes_since_log
        if name in ("log_entries", "total_entries"):
            return context.total_entries
        raw = context.variables.get(name)
        if isinstance(raw, bool) or raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _resolve_flag_value(self, name: str, context: ReminderContext) -> str:
        """Resolve a ``key=value`` flag's actual value as a lowercase string.

        Reads only from ``context.variables``. ``no_project`` falls back to the
        dedicated ``project_name`` field so the "no active project" teaching
        reminder fires without requiring callers to duplicate the flag.
        """
        if name in context.variables:
            actual = context.variables.get(name)
        elif name == "no_project":
            actual = not context.project_name
        else:
            return ""
        if isinstance(actual, bool):
            return "true" if actual else "false"
        return str(actual).strip().lower()

    def _evaluate_condition(self, condition: str, context: ReminderContext) -> bool:
        """Evaluate a condition string against context."""
        # Simple condition evaluation (can be extended)
        if condition == "no_log_entries":
            return context.total_entries == 0
        elif condition == "always":
            return True
        elif condition == "docs_missing":
            return any(status == "missing" for status in context.docs_status.values())
        elif condition == "docs_changed":
            return len(context.docs_changed) > 0
        elif condition.endswith("_complete") and condition[:-len("_complete")] in self._DOC_STATUS_CONDITIONS:
            doc_key = self._DOC_STATUS_CONDITIONS[condition[:-len("_complete")]]
            return context.docs_status.get(doc_key) == "complete"
        elif condition.endswith("_incomplete") and condition[:-len("_incomplete")] in self._DOC_STATUS_CONDITIONS:
            doc_key = self._DOC_STATUS_CONDITIONS[condition[:-len("_incomplete")]]
            return context.docs_status.get(doc_key) != "complete"
        elif " > " in condition:
            name, _, raw_threshold = condition.partition(" > ")
            try:
                threshold = float(raw_threshold.strip())
            except ValueError:
                return False
            value = self._resolve_numeric_value(name.strip(), context)
            return value is not None and value > threshold
        elif condition.startswith("tool="):
            return context.tool_name == condition.split("=", 1)[1]
        elif condition.startswith("action="):
            return context.variables.get("action") == condition.split("=", 1)[1]
        elif condition.startswith("scaffold="):
            expected = condition.split("=", 1)[1].strip().lower()
            actual = context.variables.get("scaffold")
            if isinstance(actual, bool):
                actual_value = "true" if actual else "false"
            else:
                actual_value = str(actual).strip().lower()
            return actual_value == expected
        elif "=" in condition:
            # Generic boolean/string flag resolved from context.variables
            # (e.g. not_compact=true, has_pagination=false, no_filter=true,
            # no_project=true, no_meta=true). Fires only when the flag is
            # present and matches; absent flags fail closed.
            name, _, raw_expected = condition.partition("=")
            name = name.strip()
            if name not in context.variables and name != "no_project":
                return False
            return self._resolve_flag_value(name, context) == raw_expected.strip().lower()

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

        # Per-project enabled gate (configure_reminders contract): when an
        # operator disables reminders for a project, the whole main engine is
        # silenced — no condition, teaching, or selected reminders are produced.
        if context.variables.get("main_reminder_enabled", True) is False:
            return []

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
            cooldown_minutes=rule_data.get("cooldown_minutes", 0),
            source=reminder_templates.get("source") or rule_data.get("source"),
            recommended_action=reminder_templates.get("recommended_action") or rule_data.get("recommended_action"),
            available_actions=self._coerce_string_list(
                reminder_templates.get("available_actions") or rule_data.get("available_actions")
            ),
            suggested_tool=reminder_templates.get("suggested_tool") or rule_data.get("suggested_tool"),
            blocker_codes=self._coerce_string_list(
                reminder_templates.get("blocker_codes") or rule_data.get("blocker_codes")
            ),
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
                if reminder and await self._should_show_reminder_async(reminder, context):
                    teaching.append(reminder)

        return teaching

    async def _select_reminders(self, candidates: List[ReminderInstance], context: ReminderContext) -> List[ReminderInstance]:
        """Select the best reminders based on priority and rules."""
        if not candidates:
            return []

        # Filter out suppressed reminders
        filtered = []
        for r in candidates:
            if await self._should_show_reminder_async(r, context):
                filtered.append(r)

        # Sort by priority
        priority_order = self.config.get("selection", {}).get("priority_order", [])
        category_weights = self.config.get("selection", {}).get("category_weights", {})

        def get_priority(reminder: ReminderInstance) -> Tuple[int, float, float]:
            # Explicit priority_order by reminder key wins (ascending index).
            if reminder.key in priority_order:
                return (0, float(priority_order.index(reminder.key)), 0.0)
            # Fall back to category weight, keyed on the reminder CATEGORY
            # (the category_weights keys: missing_docs/teaching/context/...).
            # Higher weight = higher priority, so negate for ascending sort.
            # level is the secondary tiebreak (urgent/warning/info also appear
            # in category_weights); unknown categories/levels sort last.
            category_weight = category_weights.get(reminder.category, 0)
            level_weight = category_weights.get(reminder.level, 0)
            return (1, -float(category_weight), -float(level_weight))

        filtered.sort(key=get_priority)

        # Apply tool-specific limits
        tool_limits = self.config.get("selection", {}).get("tool_specific_limits", {})
        tool_config = tool_limits.get(context.tool_name, {})
        max_total = tool_config.get("max_total", self.config.get("behavior", {}).get("max_reminders_per_call", 2))
        allowed_categories = tool_config.get("categories", ["all"])

        if allowed_categories != ["all"]:
            filtered = [r for r in filtered if r.category in allowed_categories]

        # Per-project category filter (configure_reminders contract): when an
        # operator restricts categories for a project, only those categories are
        # produced. Applied after the tool filter and before the cap so the
        # whitelist narrows (never widens) the tool-allowed set.
        project_categories = context.variables.get("main_reminder_categories")
        if isinstance(project_categories, (list, tuple)) and project_categories:
            allowed = {str(cat).strip().lower() for cat in project_categories}
            filtered = [r for r in filtered if r.category.lower() in allowed]

        return filtered[:max_total]

    @staticmethod
    def _coerce_string_list(value: Any) -> List[str]:
        """Return a compact list of non-empty strings from config/runtime data."""
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = [value]
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            return []
        return [str(item).strip() for item in raw_items if str(item).strip()]

    def _derive_guidance(self, reminder: ReminderInstance) -> Dict[str, Any]:
        """Build core-owned action guidance for a reminder instance."""
        recommended_action = reminder.recommended_action
        available_actions = list(reminder.available_actions)
        suggested_tool = reminder.suggested_tool
        blocker_codes = list(reminder.blocker_codes)

        if not recommended_action:
            if reminder.key.startswith("quality.") or reminder.category.startswith(("scaffold_", "frontmatter_", "release_", "stale_", "runtime_")):
                recommended_action = "Run managed-doc diagnostics and clear the named blocker before claiming done."
                suggested_tool = suggested_tool or "manage_docs"
                available_actions = available_actions or ["manage_docs quality_check", "manage_docs quality_handoff_check"]
            elif reminder.category == "logging":
                recommended_action = "Record the current work state with a reasoning trace."
                suggested_tool = suggested_tool or "append_entry"
                available_actions = available_actions or ["append_entry"]
            elif reminder.category == "docs":
                recommended_action = "Update or verify the relevant managed planning document."
                suggested_tool = suggested_tool or "manage_docs"
                available_actions = available_actions or ["manage_docs quality_check", "manage_docs apply_patch", "manage_docs replace_section"]
            elif reminder.category == "workflow":
                recommended_action = "Follow the active Scribe planning workflow before advancing."
                suggested_tool = suggested_tool or "manage_docs"
                available_actions = available_actions or ["manage_docs", "read_recent"]
            elif reminder.category == "teaching":
                recommended_action = "Apply this Scribe usage guidance to the current tool call."
                if reminder.key.startswith("teaching.manage_docs_"):
                    suggested_tool = suggested_tool or "manage_docs"
                    available_actions = available_actions or ["manage_docs"]
            elif reminder.category == "context":
                recommended_action = "Continue using the resolved project context for subsequent Scribe calls."
                available_actions = available_actions or ["append_entry", "read_recent", "manage_docs"]

        if reminder.key.startswith("quality.") and not blocker_codes:
            blocker_codes = self._coerce_string_list(reminder.variables.get("blocker_codes"))

        guidance: Dict[str, Any] = {}
        if recommended_action:
            guidance["recommended_action"] = recommended_action
        if available_actions:
            guidance["available_actions"] = available_actions
        if suggested_tool:
            guidance["suggested_tool"] = suggested_tool
        if blocker_codes:
            guidance["blocker_codes"] = blocker_codes
        return guidance

    def to_dict_list(self, reminders: List[ReminderInstance]) -> List[Dict[str, Any]]:
        """Convert reminder instances to dictionary format for API response."""
        # Per-project tone (configure_reminders contract): each reminder carries
        # the project's configured tone in its variables (threaded via
        # ReminderContext); fall back to "neutral" when unset.
        payload: List[Dict[str, Any]] = []
        for reminder in reminders:
            item: Dict[str, Any] = {
                "key": reminder.key,
                "level": reminder.level,
                "score": reminder.score,
                "emoji": reminder.emoji,
                "message": reminder.message,
                "category": reminder.category,
                "tone": str(reminder.variables.get("main_reminder_tone") or "neutral"),
                "source": reminder.source or f"core.{reminder.category}",
            }
            if reminder.context:
                item["context"] = reminder.context
            item.update(self._derive_guidance(reminder))
            payload.append(item)
        return payload
