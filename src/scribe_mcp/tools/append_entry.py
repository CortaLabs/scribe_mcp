"""Tool for appending structured entries to the progress log."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List, Union
import time

logger = logging.getLogger(__name__)

import asyncio

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import additive_local_tool
from scribe_mcp.utils.bulk_processor import BulkProcessor, ParallelBulkProcessor
from scribe_mcp.utils.estimator import BulkProcessingCalculator
from scribe_mcp.tools.agent_project_utils import (
    ensure_agent_session,
    validate_agent_session,
)
from scribe_mcp import reminders
from scribe_mcp.utils.files import append_line, rotate_file
from scribe_mcp.utils.time import format_utc, utcnow
from scribe_mcp.utils.sentinel_logs import append_sentinel_event
from scribe_mcp.shared.logging_utils import (
    ProjectResolutionError,
    compose_log_line as shared_compose_line,
    default_status_emoji,
    ensure_metadata_requirements,
    normalize_metadata,
    resolve_log_definition as shared_resolve_log_definition,
    resolve_logging_context,
)
from scribe_mcp.shared.log_enums import (
    LogPriority,
    LogCategory,
    validate_priority,
    validate_category,
    infer_priority_from_status,
)
from scribe_mcp.utils.parameter_validator import ToolValidator, BulletproofParameterCorrector
from scribe_mcp.utils.config_manager import ConfigManager, resolve_fallback_chain
from scribe_mcp.utils.error_handler import ErrorHandler, ExceptionHealer
from scribe_mcp.security.sandbox import PermissionError as SandboxPermissionError
from scribe_mcp.utils.response import default_formatter

# Bridge hooks integration (graceful fallback if bridges module unavailable)
try:
    from scribe_mcp.bridges.hooks import get_hook_manager
    BRIDGE_HOOKS_AVAILABLE = True
except ImportError:
    BRIDGE_HOOKS_AVAILABLE = False
    get_hook_manager = None

# Import validation helpers for backwards-compatible test globals.
from . import manage_docs_validation as _manage_docs_validation  # noqa: F401
from scribe_mcp.tools.config.append_entry_config import AppendEntryConfig
from scribe_mcp.shared.project_registry import ProjectRegistry

_RATE_TRACKER: Dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCKS: Dict[str, asyncio.Lock] = {}
_RATE_MAP_LOCK = asyncio.Lock()

# Global configuration manager for parameter handling
_CONFIG_MANAGER = ConfigManager("append_entry")

# Global bulk processing calculator
_BULK_CALCULATOR = BulkProcessingCalculator()

# Global parallel bulk processor for Phase 1 integration
_PARALLEL_PROCESSOR = ParallelBulkProcessor()

# Phase 3 Enhanced utilities integration
_PARAMETER_CORRECTOR = BulletproofParameterCorrector()
_EXCEPTION_HEALER = ExceptionHealer()
_PROJECT_REGISTRY = ProjectRegistry()


def _sanitize_message(message: str) -> str:
    """Sanitize message for MCP protocol compatibility."""
    if not message:
        return message

    # Replace literal newlines with escaped newlines for MCP protocol
    # This allows multiline content to pass through validation
    sanitized = message.replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n')
    return sanitized


def _get_repo_slug(project_root: str) -> str:
    """Extract repository slug from project root path."""
    from pathlib import Path
    import re

    # Convert to Path object and get the name of the directory
    path = Path(project_root)
    repo_name = path.name

    # Clean up the name to be URL-friendly
    # Replace spaces and special characters with hyphens
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', repo_name.lower())

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    # Ensure it's not empty
    if not slug:
        slug = "unknown-repo"

    return slug


def _generate_deterministic_entry_id(
    repo_slug: str,
    project_slug: str,
    timestamp: str,
    agent: str,
    message: str,
    meta: Dict[str, Any]
) -> str:
    """Generate deterministic UUID for a log entry.

    Algorithm: sha256(repo_slug|project_slug|timestamp|agent|message|meta_sha)[:32]
    This ensures the same content always generates the same UUID across rebuilds.
    """
    # Create a deterministic hash of metadata
    meta_items = []
    for key, value in sorted(meta.items()):
        meta_items.append(f"{key}={value}")
    meta_str = "|".join(meta_items)
    meta_sha = hashlib.sha256(meta_str.encode("utf-8")).hexdigest()

    # Combine all components for deterministic hashing
    components = [
        repo_slug,
        project_slug,
        timestamp,
        agent,
        message,
        meta_sha
    ]
    combined = "|".join(components)
    full_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    # Use first 32 characters as deterministic UUID
    return full_hash[:32]


def _validate_and_prepare_parameters(
    message: str,
    status: Optional[str],
    emoji: Optional[str],
    agent: Optional[str],
    meta: Optional[Any],
    timestamp_utc: Optional[str],
    items: Optional[str],
    items_list: Optional[List[Dict[str, Any]]],
    auto_split: bool,
    split_delimiter: str,
    stagger_seconds: int,
    agent_id: Optional[str],
    log_type: Optional[str],
    priority: Optional[str],
    category: Optional[str],
    tags: Optional[List[str]],
    confidence: Optional[float],
    config: Optional[AppendEntryConfig]
) -> Tuple[AppendEntryConfig, Dict[str, Any]]:
    """
    Validate and prepare parameters using enhanced Phase 3 utilities.

    This function replaces the monolithic parameter handling section of append_entry
    with bulletproof parameter validation and healing.
    """
    try:
        # Apply Phase 1 BulletproofParameterCorrector for initial parameter healing
        healed_params = {}
        healing_applied = False

        if message:
            healed_message = _PARAMETER_CORRECTOR.correct_message_parameter(message)
            if healed_message != message:
                healed_params["message"] = healed_message
                healing_applied = True

        if status:
            healed_status = _PARAMETER_CORRECTOR.correct_enum_parameter(
                status, {"info", "success", "warn", "error", "bug", "plan"}, field_name="status"
            )
            if healed_status != status:
                healed_params["status"] = healed_status
                healing_applied = True

        if emoji:
            healed_emoji = _PARAMETER_CORRECTOR.correct_message_parameter(emoji)
            if healed_emoji != emoji:
                healed_params["emoji"] = healed_emoji
                healing_applied = True

        if agent:
            healed_agent = _PARAMETER_CORRECTOR.correct_message_parameter(agent)
            if healed_agent != agent:
                healed_params["agent"] = healed_agent
                healing_applied = True

        # Only apply metadata healing to dict/string payloads; sequence-of-pairs
        # metadata (e.g. [("k","v")]) is handled downstream by `normalize_metadata`
        # and should not be collapsed into a single {"value": "..."} blob.
        if meta and isinstance(meta, (dict, str)):
            healed_meta = _PARAMETER_CORRECTOR.correct_metadata_parameter(meta)
            if healed_meta != meta:
                healed_params["meta"] = healed_meta
                healing_applied = True

        if timestamp_utc:
            healed_timestamp = _PARAMETER_CORRECTOR.correct_timestamp_parameter(timestamp_utc)
            if healed_timestamp != timestamp_utc:
                healed_params["timestamp_utc"] = healed_timestamp
                healing_applied = True

        if log_type:
            healed_log_type = _PARAMETER_CORRECTOR.correct_message_parameter(log_type)
            if healed_log_type != log_type:
                healed_params["log_type"] = healed_log_type
                healing_applied = True

        # Apply fallbacks for corrected parameters
        # NOTE: healed_params already contains best-effort corrected values; do not
        # call the per-parameter fallback resolver with a dict payload (it expects
        # a single param + context dict). Any missing keys are handled below via
        # `.get(..., original)` fallbacks.

        # Update parameters with healed values
        final_message = healed_params.get("message", message)
        final_status = healed_params.get("status", status)
        final_emoji = healed_params.get("emoji", emoji)
        final_agent = healed_params.get("agent", agent)
        final_meta = healed_params.get("meta", meta)
        final_timestamp_utc = healed_params.get("timestamp_utc", timestamp_utc)
        final_log_type = healed_params.get("log_type", log_type)

        # Validate and normalize priority/category parameters
        final_priority = priority
        final_category = category
        final_tags = tags
        final_confidence = confidence

        # Validate priority
        if final_priority:
            try:
                validated_priority = validate_priority(final_priority)
                final_priority = validated_priority.value if validated_priority else "medium"
            except ValueError:
                # Invalid priority → default to medium
                final_priority = "medium"
        elif final_status:
            # Auto-infer from status if not provided
            inferred = infer_priority_from_status(final_status)
            final_priority = inferred.value
        else:
            final_priority = "medium"

        # Validate category
        if final_category:
            try:
                validated_category = validate_category(final_category)
                final_category = validated_category.value if validated_category else None
            except ValueError:
                # Invalid category → None
                final_category = None

        # Validate confidence
        if final_confidence is not None:
            if not isinstance(final_confidence, (int, float)) or not (0.0 <= final_confidence <= 1.0):
                final_confidence = 1.0  # Out of range → default

        # Create configuration using dual parameter support
        if config is not None:
            legacy_config = AppendEntryConfig.from_legacy_params(
                message=final_message,
                status=final_status,
                emoji=final_emoji,
                agent=final_agent,
                meta=final_meta,
                timestamp_utc=final_timestamp_utc,
                items=items,
                items_list=items_list,
                auto_split=auto_split,
                split_delimiter=split_delimiter,
                stagger_seconds=stagger_seconds,
                agent_id=agent_id,
                log_type=final_log_type,
                priority=final_priority,
                category=final_category,
                tags=final_tags,
                confidence=final_confidence
            )

            config_dict = config.to_dict()
            legacy_dict = legacy_config.to_dict()

            explicit_overrides = {
                "message": message not in (None, ""),
                "status": status is not None,
                "emoji": emoji is not None,
                "agent": agent not in (None, "", "Codex"),
                "meta": meta is not None,
                "timestamp_utc": timestamp_utc is not None,
                "items": items is not None,
                "items_list": items_list is not None,
                "auto_split": auto_split is not True,
                "split_delimiter": split_delimiter != "\n",
                "stagger_seconds": stagger_seconds != 1,
                "agent_id": agent_id is not None,
                "log_type": log_type not in (None, "progress"),
                "priority": priority is not None,
                "category": category is not None,
                "tags": tags not in (None, []),
                "confidence": confidence is not None,
            }

            for key, value in legacy_dict.items():
                if explicit_overrides.get(key, False):
                    config_dict[key] = value

            final_config = AppendEntryConfig(**config_dict)
        else:
            final_config = AppendEntryConfig.from_legacy_params(
                message=final_message,
                status=final_status,
                emoji=final_emoji,
                agent=final_agent,
                meta=final_meta,
                timestamp_utc=final_timestamp_utc,
                items=items,
                items_list=items_list,
                auto_split=auto_split,
                split_delimiter=split_delimiter,
                stagger_seconds=stagger_seconds,
                agent_id=agent_id,
                log_type=final_log_type,
                priority=final_priority,
                category=final_category,
                tags=final_tags,
                confidence=final_confidence
            )

        return final_config, {"healing_applied": healing_applied, "healed_params": healed_params}

    except Exception as e:
        # Fail cleanly - no emergency fallbacks
        raise ValueError(f"Config validation failed: {e}") from e


async def _process_single_entry(
    final_config: AppendEntryConfig,
    context,
    project: Dict[str, Any],
    recent: List[Dict[str, Any]],
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    meta_pairs: Tuple[Tuple[str, str], ...],
) -> Dict[str, Any]:
    """
    Process a single log entry with enhanced error handling and fallbacks.

    This function extracts the single entry processing logic from the monolithic
    append_entry function and adds bulletproof error handling.
    """
    try:
        message = final_config.message
        status = final_config.status
        emoji = final_config.emoji
        agent = final_config.agent
        timestamp_utc = final_config.timestamp_utc
        agent_id = final_config.agent_id
        base_log_type = (final_config.log_type or "progress").lower()

        # Extract new priority/category fields
        priority = final_config.priority
        category = final_config.category
        tags = final_config.tags
        confidence = final_config.confidence

        # Validate message content - fail if invalid
        validation_error = _validate_message(message)
        if validation_error:
            return {"ok": False, "error": f"Message validation failed: {validation_error}"}

        # Rate limiting removed; logging must never be blocked.

        # Resolve emoji, agent, and timestamp with fallbacks
        try:
            resolved_emoji = _resolve_emoji(emoji, status, project)
        except Exception as emoji_error:
            healed_emoji = _EXCEPTION_HEALER.heal_parameter_validation_error(
                emoji_error, {"emoji": emoji, "status": status}
            )
            resolved_emoji = healed_emoji["healed_values"].get("emoji", "ℹ️") if healed_emoji["success"] else "ℹ️"

        defaults = project.get("defaults") or {}
        try:
            resolved_agent = _sanitize_identifier(resolve_fallback_chain(agent, defaults.get("agent"), "Scribe"))
        except Exception as agent_error:
            healed_agent = _EXCEPTION_HEALER.heal_parameter_validation_error(
                agent_error, {"agent": agent, "default_agent": defaults.get("agent")}
            )
            resolved_agent = healed_agent["healed_values"].get("agent", "Scribe") if healed_agent["success"] else "Scribe"

        try:
            timestamp_dt, timestamp, timestamp_warning = _resolve_timestamp(timestamp_utc)
        except Exception as timestamp_error:
            healed_timestamp = _EXCEPTION_HEALER.heal_parameter_validation_error(
                timestamp_error, {"timestamp_utc": timestamp_utc}
            )
            timestamp = healed_timestamp["healed_values"].get("timestamp_utc", format_utc(utcnow())) if healed_timestamp["success"] else format_utc(utcnow())
            timestamp_dt = utcnow()
            timestamp_warning = "Timestamp was healed due to error"

        # Process metadata
        meta_payload = {key: value for key, value in meta_pairs}
        entry_log_type = base_log_type

        # Add priority/category/tags/confidence to metadata for storage
        if priority:
            meta_payload["priority"] = priority
        if category:
            meta_payload["category"] = category
        if tags:
            meta_payload["tags"] = json.dumps(tags) if isinstance(tags, list) else tags
        if confidence is not None:
            meta_payload["confidence"] = confidence

        try:
            log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)
        except Exception as log_error:
            healed_log = _EXCEPTION_HEALER.heal_document_operation_error(
                log_error, {"log_type": entry_log_type, "project": project}
            )
            if healed_log["success"]:
                entry_log_type = healed_log["healed_values"].get("log_type", "progress")
                log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)
            else:
                # Fallback to progress log
                entry_log_type = "progress"
                log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)

        requirement_error = _validate_log_requirements(log_definition, meta_payload)
        if requirement_error:
            return {"ok": False, "error": f"Log requirements not met: {requirement_error}"}

        meta_payload.setdefault("log_type", entry_log_type)
        meta_payload.setdefault("content_type", "log")

        # Generate deterministic entry_id with error handling
        try:
            repo_slug = _get_repo_slug(project["root"])
            project_slug = project["name"].lower().replace(" ", "-").replace("_", "-")
            entry_id = _generate_deterministic_entry_id(
                repo_slug=repo_slug,
                project_slug=project_slug,
                timestamp=timestamp,
                agent=resolved_agent,
                message=message,
                meta=meta_payload
            )
        except Exception as id_error:
            # Generate fallback ID
            entry_id = f"fallback-{uuid.uuid4().hex[:16]}"
            meta_payload["fallback_id"] = True

        # Compose and write line with enhanced error handling
        line = None  # Initialize to prevent UnboundLocalError
        repo_root = Path(project.get("root") or settings.project_root).resolve()
        log_context = {"component": "logs", "project_name": project.get("name")}
        try:
            # Convert meta dict to meta_pairs tuple for _compose_line
            meta_pairs = tuple(meta_payload.items()) if meta_payload else ()

            line = _compose_line(
                emoji=resolved_emoji,
                message=message,
                timestamp=timestamp,
                agent=resolved_agent,
                project_name=project.get("name", "unknown"),
                meta_pairs=meta_pairs
            )

            # Auto-rotate oversized logs for single-entry writes as well (bulk
            # mode already does this).
            await _rotate_if_needed(log_path, repo_root=repo_root)

            line_id = await append_line(
                log_path,
                line,
                repo_root=repo_root,
                context=log_context,
            )

        except Exception as write_error:
            if isinstance(write_error, SandboxPermissionError):
                return {
                    "ok": False,
                    "error": str(write_error),
                    "suggestion": "Ensure sandbox permissions allow append and include project_name in context.",
                    "recent_projects": list(recent),
                    "debug_path": "append_permission_denied",
                }
            # Try to heal write errors
            healed_write = _EXCEPTION_HEALER.heal_document_operation_error(
                write_error, {"log_path": str(log_path), "line": line or "FAILED_TO_CREATE"}
            )

            if healed_write["success"]:
                # Try alternative write method
                try:
                    alternative_line = healed_write["healed_values"].get("line", line)
                    line_id = await append_line(
                        log_path,
                        alternative_line,
                        repo_root=repo_root,
                        context=log_context,
                    )
                except Exception:
                    # Emergency fallback - write to emergency log
                    emergency_root = repo_root
                    emergency_log_path = emergency_root / "emergency_entries.log"
                    emergency_line = f"[{timestamp}] [Agent: {resolved_agent}] {message}\n"
                    line_id = await append_line(
                        emergency_log_path,
                        emergency_line,
                        repo_root=repo_root,
                        context=log_context,
                    )
                    meta_payload["emergency_write"] = True
            else:
                # Ultimate fallback
                raise write_error

        tee_paths: List[str] = []
        tee_reminders: List[Dict[str, Any]] = []
        try:
            primary_log_type = entry_log_type

            wants_bug = _should_tee_to_bug(status, resolved_emoji)
            wants_security = _should_tee_to_security(meta_payload, resolved_emoji)

            # Ensure bug/security entries still land in progress for canonical timeline.
            wants_progress = primary_log_type in {"bugs", "security"} or wants_bug or wants_security

            if wants_progress and primary_log_type != "progress":
                progress_path, missing = await _tee_entry_to_log_type(
                    project=project,
                    repo_root=repo_root,
                    log_type="progress",
                    message=message,
                    emoji=resolved_emoji,
                    timestamp=timestamp,
                    agent=resolved_agent,
                    meta_payload=meta_payload,
                    log_cache=log_cache,
                )
                if progress_path:
                    tee_paths.append(str(progress_path))
                if missing:
                    tee_reminders.append(_make_missing_meta_reminder(target_log_type="progress", missing_keys=missing))

            if wants_bug and primary_log_type != "bugs":
                bug_path, missing = await _tee_entry_to_log_type(
                    project=project,
                    repo_root=repo_root,
                    log_type="bugs",
                    message=message,
                    emoji=resolved_emoji,
                    timestamp=timestamp,
                    agent=resolved_agent,
                    meta_payload=meta_payload,
                    log_cache=log_cache,
                )
                if bug_path:
                    tee_paths.append(str(bug_path))
                if missing:
                    tee_reminders.append(_make_missing_meta_reminder(target_log_type="bugs", missing_keys=missing))

            if wants_security and primary_log_type != "security":
                sec_path, missing = await _tee_entry_to_log_type(
                    project=project,
                    repo_root=repo_root,
                    log_type="security",
                    message=message,
                    emoji=resolved_emoji,
                    timestamp=timestamp,
                    agent=resolved_agent,
                    meta_payload=meta_payload,
                    log_cache=log_cache,
                )
                if sec_path:
                    tee_paths.append(str(sec_path))
                if missing:
                    tee_reminders.append(_make_missing_meta_reminder(target_log_type="security", missing_keys=missing))
        except Exception:
            # Tee failures should never block logging.
            pass

        # Mirror entry into database-backed storage when available, without
        # impacting the primary file append path.
        backend = server_module.storage_backend
        db_mirror: Dict[str, Any] = {
            "enabled": bool(backend),
            "backend": type(backend).__name__ if backend else None,
            "status": "disabled",
            "error": None,
        }
        if backend:
            db_mirror["status"] = "pending"
            try:
                timeout = settings.storage_timeout_seconds
                # Ensure project row exists
                async with asyncio.timeout(timeout):
                    record = await backend.fetch_project(project["name"])
                if not record:
                    async with asyncio.timeout(timeout):
                        record = await backend.upsert_project(
                            name=project["name"],
                            repo_root=project.get("root", str(Path("."))),
                            progress_log_path=str(log_path),
                        )

                # Prepare and insert mirrored entry
                sha_value = hashlib.sha256((line or "").encode("utf-8")).hexdigest()
                ts_dt = timestamp_dt or utcnow()
                async with asyncio.timeout(timeout):
                    await backend.insert_entry(
                        entry_id=entry_id,
                        project=record,
                        ts=ts_dt,
                        emoji=resolved_emoji,
                        agent=resolved_agent,
                        message=message,
                        meta=meta_payload,
                        raw_line=line or "",
                        sha256=sha_value,
                        log_type=entry_log_type,
                    )
                db_mirror["status"] = "ok"
            except Exception as db_exc:
                # Database mirror failures should never block logging.
                db_mirror["status"] = "error"
                db_mirror["error"] = str(db_exc)
                logger.warning("append_entry database mirror failed: %s", db_exc)

        # Update project state with exception handling
        try:
            await server_module.state_manager.update_project_activity(
                project["name"], entry_id, message, len(line)
            )
            # Touch Project Registry entry for this project (best-effort).
            try:
                _PROJECT_REGISTRY.touch_entry(project["name"], log_type=final_config.log_type)
            except Exception:
                pass
        except Exception as state_error:
            # Log state error but don't fail the operation
            pass

        # Prepare response
        response = {
            "ok": True,
            "id": entry_id,
            # Backwards-compatible convenience: many clients/tests expect the exact
            # rendered line that was appended to the primary log path.
            "written_line": line,
            "meta": meta_payload,
            "path": str(log_path),
            "paths": sorted({str(log_path), *tee_paths}),
            "line_id": line_id,
            "project_name": project["name"],  # For concurrent session clarity
            "recent_projects": list(recent),
            "reminders": list(getattr(context, "reminders", []) or []) + tee_reminders,
            "db_mirror": db_mirror,
        }

        if timestamp_warning:
            response["warning"] = timestamp_warning

        return response

    except Exception as e:
        # Fail cleanly - no emergency entries
        return {
            "ok": False,
            "error": f"Failed to process entry: {str(e)}",
            "recent_projects": list(recent),
        }


async def _process_bulk_entries(
    final_config: AppendEntryConfig,
    context,
    project: Dict[str, Any],
    recent: List[Dict[str, Any]],
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    meta_pairs: Tuple[Tuple[str, str], ...]
) -> Dict[str, Any]:
    """
    Process bulk entries with enhanced error handling and intelligent fallbacks.

    This function extracts the bulk processing logic from the monolithic append_entry
    function and adds bulletproof error handling with intelligent recovery.
    """
    try:
        items = final_config.items
        items_list = final_config.items_list
        auto_split = final_config.auto_split
        split_delimiter = final_config.split_delimiter
        stagger_seconds = final_config.stagger_seconds
        agent_id = final_config.agent_id
        base_log_type = (final_config.log_type or "progress").lower()

        # Enhanced bulk mode handling with multiple input formats
        bulk_items = None

        if items_list is not None:
            if not isinstance(items_list, list):
                # Try to heal the items_list parameter
                healed_items = _EXCEPTION_HEALER.heal_parameter_validation_error(
                    ValueError("items_list must be a list of dictionaries"),
                    {"items_list": items_list}
                )

                if healed_items["success"]:
                    bulk_items = healed_items["healed_values"].get("items_list", [])
                else:
                    bulk_items = []
            else:
                bulk_items = items_list.copy()

        elif items is not None:
            try:
                parsed_items = json.loads(items)
                if not isinstance(parsed_items, list):
                    # Try to heal the parsed items
                    healed_parsed = _EXCEPTION_HEALER.heal_parameter_validation_error(
                        ValueError("Items parameter must be a JSON array"),
                        {"items": items, "parsed_items": parsed_items}
                    )

                    if healed_parsed["success"]:
                        bulk_items = healed_parsed["healed_values"].get("items", [])
                    else:
                        bulk_items = []
                else:
                    bulk_items = parsed_items

            except json.JSONDecodeError as json_error:
                # Try to heal JSON parsing error
                healed_json = _EXCEPTION_HEALER.heal_parameter_validation_error(
                    json_error, {"items": items, "error_type": "json_decode"}
                )

                if healed_json["success"]:
                    healed_items_str = healed_json["healed_values"].get("items", "[]")
                    bulk_items = json.loads(healed_items_str)
                else:
                    return {
                        "ok": False,
                        "error": f"Invalid JSON in items parameter: {str(json_error)}",
                        "suggestion": "Use items_list parameter for direct list support",
                        "recent_projects": list(recent),
                    }

        # Auto-detect multiline messages if auto_split=True
        if not bulk_items and auto_split and final_config.message:
            try:
                bulk_items = _split_multiline_message(final_config.message, split_delimiter)
            except Exception as split_error:
                # Try to heal message splitting
                healed_split = _EXCEPTION_HEALER.heal_bulk_processing_error(
                    split_error, {"message": final_config.message, "delimiter": split_delimiter}
                )

                if healed_split["success"]:
                    bulk_items = healed_split["healed_values"].get("bulk_items", [final_config.message])
                else:
                    # Fallback to single entry
                    bulk_items = [final_config.message]

        # Apply inherited metadata and prepare items
        try:
            inherited_meta = {key: value for key, value in meta_pairs}
            normalized_bulk: List[Dict[str, Any]] = []
            for raw_item in bulk_items or []:
                if isinstance(raw_item, dict):
                    item = dict(raw_item)
                else:
                    item = {"message": str(raw_item)}

                item_meta_pairs = _normalise_meta(item.get("meta"))
                item_meta_dict = {key: value for key, value in item_meta_pairs}
                merged_meta = dict(inherited_meta)
                merged_meta.update(item_meta_dict)
                item["meta"] = merged_meta
                normalized_bulk.append(item)

            bulk_items = _prepare_bulk_items_with_timestamps(
                normalized_bulk, final_config.timestamp_utc, stagger_seconds
            )
        except Exception as prep_error:
            # Fail cleanly
            return {
                "ok": False,
                "error": f"Bulk preparation failed: {str(prep_error)}",
                "recent_projects": list(recent),
            }

        # Process bulk items with enhanced error handling
        try:
            # Check if we should use parallel processing
            use_parallel = len(bulk_items) > 10

            if use_parallel:
                results = await _process_large_bulk_chunked(bulk_items, project, log_cache)
            else:
                results = []
                for item in bulk_items:
                    try:
                        item_config = AppendEntryConfig.from_legacy_params(
                            message=item.get("message", ""),
                            status=item.get("status", final_config.status),
                            emoji=item.get("emoji", final_config.emoji),
                            agent=item.get("agent", final_config.agent),
                            meta=item.get("meta", {}),
                            timestamp_utc=item.get("timestamp_utc"),
                            agent_id=agent_id,
                            log_type=base_log_type,
                            priority=item.get("priority", final_config.priority),
                            category=item.get("category", final_config.category),
                            tags=item.get("tags", final_config.tags),
                            confidence=item.get("confidence", final_config.confidence)
                        )

                        result = await _process_single_entry(
                            item_config, context, project, recent, log_cache, _normalise_meta(item.get("meta"))
                        )
                        results.append(result)

                    except Exception as item_error:
                        # Try to heal individual item processing error
                        healed_item = _EXCEPTION_HEALER.heal_bulk_processing_error(
                            item_error, {"item": item, "bulk_index": len(results)}
                        )

                        if healed_item["success"]:
                            # Add healed item to results
                            healed_result = {
                                "ok": True,
                                "id": f"healed-{uuid.uuid4().hex[:16]}",
                                "healed": True,
                                "original_error": str(item_error)
                            }
                            results.append(healed_result)
                        else:
                            # Add error result but continue processing
                            error_result = {
                                "ok": False,
                                "error": f"Failed to process bulk item {len(results)}: {str(item_error)}",
                                "item_failed": True
                            }
                            results.append(error_result)

        except Exception as bulk_error:
            # Apply comprehensive bulk exception healing
            healed_bulk = _EXCEPTION_HEALER.heal_bulk_processing_error(
                bulk_error, {"bulk_items": bulk_items, "project": project}
            )

            if healed_bulk.get("success"):
                # Try alternative bulk processing
                alternative_items = healed_bulk.get("healed_values", {}).get("bulk_items", bulk_items[:1])
                results = []

                for item in alternative_items:
                    try:
                        item_config = AppendEntryConfig.from_legacy_params(
                            message=item.get("message", "Bulk item processed after error"),
                            status=item.get("status", "info"),
                            emoji=item.get("emoji", "ℹ️"),
                            agent=item.get("agent", final_config.agent),
                            meta=item.get("meta", {"bulk_healing": True}),
                            timestamp_utc=item.get("timestamp_utc", final_config.timestamp_utc),
                            agent_id=agent_id,
                            log_type=base_log_type,
                            priority=item.get("priority", final_config.priority),
                            category=item.get("category", final_config.category),
                            tags=item.get("tags", final_config.tags),
                            confidence=item.get("confidence", final_config.confidence)
                        )

                        result = await _process_single_entry(
                            item_config, context, project, recent, log_cache, _normalise_meta(item.get("meta"))
                        )
                        results.append(result)

                    except Exception as item_error:
                        # Fail cleanly - report the error for this item
                        results.append({
                            "ok": False,
                            "error": f"Failed to process bulk item: {str(item_error)}",
                            "item_index": i
                        })
            else:
                # No items to process - return clean error
                return {
                    "ok": False,
                    "error": f"Bulk processing failed: {str(bulk_error)}",
                    "suggestion": "Check items format and try again",
                    "recent_projects": list(recent),
                }

        # Prepare bulk response
        successful_results = [r for r in results if r.get("ok", False)]
        failed_results = [r for r in results if not r.get("ok", False)]

        response = {
            "ok": len(successful_results) > 0,
            "bulk_mode": True,
            "processed": len(results),
            "successful": len(successful_results),
            "failed": len(failed_results),
            "results": results,
            "recent_projects": list(recent),
        }

        # Backwards-compatible bulk response fields.
        written_lines = [r.get("written_line") for r in successful_results if r.get("written_line")]
        failed_items = failed_results
        paths_accum = sorted({str(r.get("path")) for r in successful_results if r.get("path")})
        response.update(
            {
                "written_count": len(written_lines),
                "failed_count": len(failed_items),
                "written_lines": written_lines,
                "failed_items": failed_items,
                "path": paths_accum[0] if paths_accum else project.get("progress_log"),
                "paths": paths_accum or ([project.get("progress_log")] if project.get("progress_log") else []),
            }
        )

        if failed_results:
            response["warning"] = f"{len(failed_results)} items failed to process"

        return response

    except Exception as e:
        # Fail cleanly - no emergency fallbacks
        return {
            "ok": False,
            "error": f"Bulk processing failed: {str(e)}",
            "suggestion": "Try processing items individually or check parameters",
            "recent_projects": list(recent),
        }


def _should_use_bulk_mode(message: str, items: Optional[str] = None, items_list: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Detect if content should be processed as bulk entries using BulkProcessor utility."""
    return BulkProcessor.detect_bulk_mode(message, items, items_list, length_threshold=500)


def _split_multiline_message(message: str, delimiter: str = "\n") -> List[Dict[str, Any]]:
    """Split multiline message into individual entries using BulkProcessor utility."""
    return BulkProcessor.split_multiline_content(message, delimiter, auto_detect_status=True, auto_detect_emoji=True)


def _prepare_bulk_items_with_timestamps(
    items: List[Dict[str, Any]],
    base_timestamp: Optional[str] = None,
    stagger_seconds: int = 1
) -> List[Dict[str, Any]]:
    """Add individual timestamps to bulk items using BulkProcessor utility."""
    return BulkProcessor.apply_timestamp_staggering(items, base_timestamp, stagger_seconds, "timestamp_utc")


def _apply_inherited_metadata(
    items: List[Dict[str, Any]],
    inherited_meta: Optional[Dict[str, Any]],
    inherited_status: Optional[str] = None,
    inherited_emoji: Optional[str] = None,
    inherited_agent: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Apply inherited metadata and values to all items in bulk using BulkProcessor utility."""
    return BulkProcessor.apply_inherited_metadata(items, inherited_meta, inherited_status, inherited_emoji, inherited_agent, "meta")


async def _process_large_bulk_chunked(
    items: List[Dict[str, Any]],
    project: Dict[str, Any],
    recent: List[str],
    state_snapshot: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    chunk_size: int = 50
) -> Dict[str, Any]:
    """Process large bulk entries in chunks to optimize memory and performance."""
    if len(items) <= chunk_size:
        return await _append_bulk_entries(items, project, recent, state_snapshot, base_log_type, log_cache)

    all_written_lines = []
    all_failed_items = []

    # Calculate chunking parameters using BulkProcessingCalculator
    chunk_calc = _BULK_CALCULATOR.calculate_chunks(len(items), chunk_size)
    total_chunks = chunk_calc.total_chunks

    logger.debug("Processing %d items in %d chunks of %d", len(items), total_chunks, chunk_size)

    last_result: Optional[Dict[str, Any]] = None
    paths_accum: set[str] = set()
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]
        chunk_num = i // chunk_size + 1

        logger.debug("Processing chunk %d/%d (%d items)", chunk_num, total_chunks, len(chunk))

        result = await _append_bulk_entries(chunk, project, recent, state_snapshot, base_log_type, log_cache)
        last_result = result
        for path_str in result.get("paths") or [result.get("path")]:
            if path_str:
                paths_accum.add(path_str)

        all_written_lines.extend(result.get("written_lines", []))
        all_failed_items.extend(result.get("failed_items", []))

        # Small delay between chunks to prevent overwhelming the system
        if i + chunk_size < len(items):
            await asyncio.sleep(0.1)

    reminders_payload = await reminders.get_reminders(
        project, tool_name="append_entry", state=state_snapshot
    )
    primary_path = None
    if last_result:
        primary_path = last_result.get("path")

    return {
        "ok": len(all_failed_items) == 0,
        "written_count": len(all_written_lines),
        "failed_count": len(all_failed_items),
        "written_lines": all_written_lines,
        "failed_items": all_failed_items,
        "path": primary_path or project.get("progress_log"),
        "paths": sorted(paths_accum) or ([project.get("progress_log")] if project.get("progress_log") else []),
        "recent_projects": list(recent),
        "reminders": reminders_payload,
        "chunks_processed": total_chunks,
    }


@app.tool(**additive_local_tool(title="Append Log Entry", tags=("logs", "project", "write")))
async def append_entry(
    agent: str = "Codex",
    message: str = "",
    status: Optional[str] = None,
    emoji: Optional[str] = None,
    meta: Optional[Any] = None,  # Changed to Any to handle MCP interface mangling
    timestamp_utc: Optional[str] = None,
    items: Optional[str] = None,
    items_list: Optional[List[Dict[str, Any]]] = None,
    auto_split: bool = True,
    split_delimiter: str = "\n",
    stagger_seconds: int = 1,
    agent_id: Optional[str] = None,  # Agent identification (auto-detected if not provided)
    log_type: Optional[str] = "progress",
    priority: Optional[str] = None,  # Entry priority (critical|high|medium|low)
    category: Optional[str] = None,  # Entry category (decision|investigation|bug|etc.)
    tags: Optional[List[str]] = None,  # List of tags for entry
    confidence: Optional[float] = None,  # Confidence score 0.0-1.0
    config: Optional[AppendEntryConfig] = None,  # Configuration object for enhanced parameter handling
    format: str = "structured",  # Output format: readable, structured (default), compact
    **_kwargs: Any,  # tolerate unknown kwargs (contract: tools never TypeError)
) -> Union[Dict[str, Any], str]:
    """
    Enhanced append_entry with robust multiline handling and bulk mode support.

    Args:
        message: Log message (auto-splits multiline if auto_split=True)
        status: Status type (info|success|warn|error|bug|plan)
        emoji: Custom emoji override
        agent: Agent identifier
        meta: Metadata dictionary (applied to all entries in bulk/split mode)
        timestamp_utc: UTC timestamp string (base timestamp for bulk/split entries)
        items: JSON string array for bulk mode (backwards compatibility)
        items_list: Direct list of entry dictionaries for bulk mode (NEW)
        auto_split: Automatically split multiline messages into separate entries (default: True)
        split_delimiter: Delimiter for splitting multiline messages (default: newline)
        stagger_seconds: Seconds to stagger timestamps for bulk/split entries (default: 1)
        log_type: Target log identifier (progress/doc_updates/etc.) defined in config/log_config.json
        priority: Entry priority (critical|high|medium|low). Auto-inferred from status if not provided. Default: medium
        category: Entry category (decision|investigation|bug|implementation|test|milestone|config|security|performance|documentation)
        tags: List of tags for entry
        confidence: Confidence score 0.0-1.0. Default: 1.0
        config: Optional AppendEntryConfig object for enhanced parameter handling

    ENHANCED FEATURES:
    - Automatic multiline detection and splitting
    - Direct list support for bulk mode (no JSON string required)
    - Individual timestamps for each entry in bulk/split mode
    - Robust error handling with automatic fallbacks
    - Performance optimized for large content
    - Dual parameter support: Use either legacy parameters OR AppendEntryConfig object
    - Legacy parameter precedence: When both legacy params and config provided, legacy params override

    Single Entry Mode: Auto-detects and handles multiline content
    Bulk Mode: Support both items (JSON string) and items_list (direct list)
    Configuration Mode: Use AppendEntryConfig for structured parameter management
    """
    # Phase 3 Task 3.5: Enhanced Function Decomposition
    # This function now uses decomposed sub-functions with bulletproof error handling

    try:
        state_snapshot = await server_module.state_manager.record_tool("append_entry")
    except Exception:
        state_snapshot = {}

    exec_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            exec_context = server_module.get_execution_context()
        except Exception:
            exec_context = None

    try:
        # === PHASE 3 ENHANCED PARAMETER VALIDATION AND PREPARATION ===
        # Replace monolithic parameter handling with bulletproof validation and healing
        final_config, validation_info = _validate_and_prepare_parameters(
            message=message,
            status=status,
            emoji=emoji,
            agent=agent,
            meta=meta,
            timestamp_utc=timestamp_utc,
            items=items,
            items_list=items_list,
            auto_split=auto_split,
            split_delimiter=split_delimiter,
            stagger_seconds=stagger_seconds,
            agent_id=agent_id,
            log_type=log_type,
            priority=priority,
            category=category,
            tags=tags,
            confidence=confidence,
            config=config
        )

        # Extract normalized parameters from final configuration
        message = final_config.message
        status = final_config.status
        emoji = final_config.emoji
        agent = final_config.agent
        meta = final_config.meta
        timestamp_utc = final_config.timestamp_utc
        items = final_config.items
        items_list = final_config.items_list
        auto_split = final_config.auto_split
        split_delimiter = final_config.split_delimiter
        stagger_seconds = final_config.stagger_seconds
        agent_id = final_config.agent_id
        log_type = final_config.log_type

        # Normalize metadata early for consistent handling throughout the function
        meta_pairs = _normalise_meta(meta)
        meta_payload = {key: value for key, value in meta_pairs}

        # Auto-detect agent ID if not provided
        if agent_id is None:
            agent_identity = server_module.get_agent_identity()
            if agent_identity:
                agent_id = await agent_identity.get_or_create_agent_id()
            else:
                agent_id = "Scribe"  # Fallback

        # Update agent activity tracking
        agent_identity = server_module.get_agent_identity()
        if agent_identity:
            await agent_identity.update_agent_activity(
                agent_id, "append_entry", {"message_length": len(message), "status": status, "bulk_mode": items is not None}
            )

        def _collect_bulk_items(raw_items: Optional[str], raw_items_list: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
            if isinstance(raw_items_list, list):
                return [item for item in raw_items_list if isinstance(item, dict)]
            if isinstance(raw_items, str):
                try:
                    parsed = json.loads(raw_items)
                    if isinstance(parsed, list):
                        return [item for item in parsed if isinstance(item, dict)]
                except Exception:
                    return []
            return []

        def _append_entry_to_sentinel(
            *,
            message_value: str,
            status_value: Optional[str],
            emoji_value: Optional[str],
            agent_value: Optional[str],
            meta_value: Optional[Dict[str, Any]],
            timestamp_override: Optional[str],
            bulk_items: List[Dict[str, Any]],
            split_parts: List[str],
        ) -> Dict[str, Any]:
            if not exec_context:
                return {"ok": False, "error": "ExecutionContext missing"}

            def emit(payload: Dict[str, Any], event_type: str) -> None:
                append_sentinel_event(
                    exec_context,
                    event_type=event_type,
                    data=payload,
                    log_type="sentinel",
                    include_md=True,
                )

            written = 0
            if bulk_items:
                for entry in bulk_items:
                    entry_message = entry.get("message")
                    if not entry_message:
                        continue
                    payload = {
                        "message": entry_message,
                        "status": entry.get("status"),
                        "emoji": entry.get("emoji"),
                        "agent": entry.get("agent"),
                        "meta": entry.get("meta") if isinstance(entry.get("meta"), dict) else None,
                        "timestamp_utc_override": entry.get("timestamp_utc"),
                    }
                    emit(payload, str(entry.get("status") or "info"))
                    written += 1
            else:
                if not message_value:
                    return {"ok": False, "error": "message or items are required"}
                for part in split_parts:
                    payload = {
                        "message": part,
                        "status": status_value,
                        "emoji": emoji_value,
                        "agent": agent_value,
                        "meta": meta_value if isinstance(meta_value, dict) else None,
                        "timestamp_utc_override": timestamp_override,
                    }
                    emit(payload, str(status_value or "info"))
                    written += 1

            return {"ok": True, "written_count": written, "mode": "sentinel"}

        if exec_context and getattr(exec_context, "mode", None) == "sentinel":
            bulk_items = _collect_bulk_items(items, items_list)
            split_parts = (
                [part for part in message.split(split_delimiter) if part]
                if auto_split and split_delimiter and message
                else [message] if message else []
            )
            return _append_entry_to_sentinel(
                message_value=message,
                status_value=status,
                emoji_value=emoji,
                agent_value=agent,
                meta_value=meta_payload,
                timestamp_override=timestamp_utc,
                bulk_items=bulk_items,
                split_parts=split_parts,
            )

        # === CONTEXT RESOLUTION WITH ENHANCED ERROR HANDLING ===
        try:
            context = await resolve_logging_context(
                tool_name="append_entry",
                server_module=server_module,
                agent_id=agent_id,
                require_project=True,
                state_snapshot=state_snapshot,
            )
        except ProjectResolutionError as exc:
            # Apply Phase 2 ExceptionHealer for project resolution errors
            healed_context = _EXCEPTION_HEALER.heal_parameter_validation_error(
                exc, {"tool_name": "append_entry", "agent_id": agent_id}
            )

            if healed_context["success"]:
                # Try with healed context
                try:
                    context = await resolve_logging_context(
                        tool_name="append_entry",
                        server_module=server_module,
                        agent_id=healed_context["healed_values"].get("agent_id", agent_id),
                        require_project=True,
                        state_snapshot=state_snapshot,
                    )
                except Exception:
                    if exec_context:
                        bulk_items = _collect_bulk_items(items, items_list)
                        split_parts = (
                            [part for part in message.split(split_delimiter) if part]
                            if auto_split and split_delimiter and message
                            else [message] if message else []
                        )
                        fallback = _append_entry_to_sentinel(
                            message_value=message,
                            status_value=status,
                            emoji_value=emoji,
                            agent_value=agent,
                            meta_value=meta_payload,
                            timestamp_override=timestamp_utc,
                            bulk_items=bulk_items,
                            split_parts=split_parts,
                        )
                        fallback["warning"] = "project_resolution_failed_fallback_to_sentinel"
                        return fallback
                    # Fallback response
                    error_response = ErrorHandler.create_project_resolution_error(
                        error=exc,
                        tool_name="append_entry",
                        suggestion=f"Invoke set_project with agent_id='{agent_id}' before appending entries"
                    )
                error_response["debug_path"] = "project_resolution_failed_healed"
                return error_response
            else:
                if exec_context:
                    bulk_items = _collect_bulk_items(items, items_list)
                    split_parts = (
                        [part for part in message.split(split_delimiter) if part]
                        if auto_split and split_delimiter and message
                        else [message] if message else []
                    )
                    fallback = _append_entry_to_sentinel(
                        message_value=message,
                        status_value=status,
                        emoji_value=emoji,
                        agent_value=agent,
                        meta_value=meta_payload,
                        timestamp_override=timestamp_utc,
                        bulk_items=bulk_items,
                        split_parts=split_parts,
                    )
                    fallback["warning"] = "project_resolution_failed_fallback_to_sentinel"
                    return fallback
                error_response = ErrorHandler.create_project_resolution_error(
                    error=exc,
                    tool_name="append_entry",
                    suggestion=f"Invoke set_project with agent_id='{agent_id}' before appending entries"
                )
            error_response["debug_path"] = "project_resolution_failed"
            return error_response

        project = context.project or {}
        recent = list(context.recent_projects)
        reminders_payload: List[Dict[str, Any]] = list(context.reminders)

        # === INPUT VALIDATION ===
        # Validate that either message, items, or items_list is provided
        if not items and not items_list and not message:
            fallback_message = None
            if config is not None:
                try:
                    fallback_message = config.message
                except Exception:
                    fallback_message = None
            message = fallback_message or "No message provided"
            if status is None:
                status = "warn"
            final_config.message = message
            final_config.status = status

        log_cache: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
        base_log_type = (log_type or "progress").lower()

        # === ENHANCED PROCESSING MODE SELECTION ===
        # Determine if we should use bulk mode with intelligent detection
        use_bulk_mode = _should_use_bulk_mode(message, items, items_list)

        if use_bulk_mode:
            # === BULK PROCESSING WITH ENHANCED ERROR HANDLING ===
            result = await _process_bulk_entries(
                final_config, context, project, recent, log_cache, meta_pairs
            )
        else:
            # === SINGLE ENTRY PROCESSING WITH ENHANCED ERROR HANDLING ===
            result = await _process_single_entry(
                final_config, context, project, recent, log_cache, meta_pairs
            )

        # Add validation info to result if healing was applied
        if validation_info.get("healing_applied"):
            if "meta" not in result:
                result["meta"] = {}

            if validation_info.get("exception_healing"):
                result["meta"]["parameter_exception_healing"] = True
            elif validation_info.get("emergency_fallback"):
                result["meta"]["parameter_emergency_fallback"] = True
            else:
                result["meta"]["parameter_healing"] = True

        # Route through formatter for readable/structured/compact output
        return await default_formatter.finalize_tool_response(
            data=result,
            format=format,
            tool_name="append_entry"
        )

    except Exception as e:
        # Fail cleanly with error details - no emergency fallbacks
        return {
            "ok": False,
            "error": f"append_entry failed: {str(e)}",
            "suggestion": "Check parameters and try again",
            "recent_projects": [],
        }

def _resolve_emoji(
    explicit: Optional[str],
    status: Optional[str],
    project: Dict[str, Any],
) -> str:
    return default_status_emoji(explicit=explicit, status=status, project=project)


def _validate_comparison_symbols_in_meta(meta: Any) -> Any:
    """Validate and escape comparison symbols in metadata values."""
    if meta is None:
        return None

    if isinstance(meta, dict):
        validated_meta = {}
        for key, value in meta.items():
            if isinstance(value, str):
                # Check for comparison operators that might cause type errors
                if any(op in value for op in ['>', '<', '>=', '<=']):
                    # Escape the comparison operators to prevent type errors
                    escaped_value = value.replace('>', '\\>').replace('<', '\\<')
                    validated_meta[key] = escaped_value
                else:
                    validated_meta[key] = value
            else:
                validated_meta[key] = value
        return validated_meta

    return meta


def _normalise_meta(meta: Optional[Any]) -> tuple[tuple[str, str], ...]:
    """Delegate metadata normalization to the shared logging utility with robust error handling."""
    try:
        # Validate comparison symbols before normalization
        validated_meta = _validate_comparison_symbols_in_meta(meta)
        return normalize_metadata(validated_meta)
    except Exception as exc:
        error_str = str(exc)
        return (("meta_error", f"Metadata normalization failed: {error_str[:50]}"),)


def _compose_line(
    *,
    emoji: str,
    timestamp: str,
    agent: str,
    project_name: str,
    message: str,
    meta_pairs: tuple[tuple[str, str], ...],
    entry_id: Optional[str] = None,
) -> str:
    return shared_compose_line(
        emoji=emoji,
        timestamp=timestamp,
        agent=agent,
        project_name=project_name,
        message=message,
        meta_pairs=meta_pairs,
        entry_id=entry_id,
    )


def _resolve_timestamp(timestamp_utc: Optional[str]) -> Tuple[Optional[datetime], str, Optional[str]]:
    """Delegate timestamp validation to ToolValidator."""
    return ToolValidator.validate_timestamp(timestamp_utc)


def _sanitize_identifier(value: str) -> str:
    """Delegate identifier sanitization to ToolValidator."""
    return ToolValidator.sanitize_identifier(value)


def _validate_message(message: str) -> Optional[str]:
    """Delegate message validation to ToolValidator."""
    return ToolValidator.validate_message(message)


async def _enforce_rate_limit(project_name: str) -> Optional[Dict[str, Any]]:
    return None


def _resolve_log_target(
    project: Dict[str, Any],
    log_type: str,
    cache: Dict[str, Tuple[Path, Dict[str, Any]]],
) -> Tuple[Path, Dict[str, Any]]:
    return shared_resolve_log_definition(project, log_type, cache=cache)


def _validate_log_requirements(definition: Dict[str, Any], meta_payload: Dict[str, Any]) -> Optional[str]:
    """Delegate log requirements validation to ToolValidator."""
    return ToolValidator.validate_metadata_requirements(definition, meta_payload)


BUG_EMOJIS = {"🐛", "🐞", "🪲"}
SECURITY_EMOJIS = {"🔐", "🔒", "🛡️"}


def _missing_required_meta(definition: Dict[str, Any], meta_payload: Dict[str, Any]) -> List[str]:
    required = definition.get("metadata_requirements") or []
    missing: List[str] = []
    for key in required:
        value = meta_payload.get(key)
        if value is None:
            missing.append(key)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(key)
    return missing


def _should_tee_to_bug(status: Optional[str], resolved_emoji: str) -> bool:
    return (status or "").lower() == "bug" or resolved_emoji in BUG_EMOJIS


def _should_tee_to_security(meta_payload: Dict[str, Any], resolved_emoji: str) -> bool:
    security_flag = str(meta_payload.get("security_event", "")).lower() in {"1", "true", "yes"}
    return security_flag or resolved_emoji in SECURITY_EMOJIS


async def _tee_entry_to_log_type(
    *,
    project: Dict[str, Any],
    repo_root: Path,
    log_type: str,
    message: str,
    emoji: str,
    timestamp: str,
    agent: str,
    meta_payload: Dict[str, Any],
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
) -> Tuple[Optional[Path], List[str]]:
    """Best-effort secondary write used to populate auxiliary logs (bugs/security/progress)."""
    log_path, log_definition = _resolve_log_target(project, log_type, log_cache)
    meta_copy = dict(meta_payload)
    meta_copy["log_type"] = log_type
    missing = _missing_required_meta(log_definition, meta_copy)
    if missing:
        return None, missing

    line = _compose_line(
        emoji=emoji,
        message=message,
        timestamp=timestamp,
        agent=agent,
        project_name=project.get("name", "unknown"),
        meta_pairs=tuple(meta_copy.items()),
    )
    await append_line(
        log_path,
        line,
        repo_root=repo_root,
        context={"component": "logs", "project_name": project.get("name")},
    )
    return log_path, []


def _make_missing_meta_reminder(
    *,
    target_log_type: str,
    missing_keys: List[str],
) -> Dict[str, Any]:
    if target_log_type == "bugs":
        example = "meta={severity:high, component:auth, status:open}"
    elif target_log_type == "security":
        example = "meta={severity:high, area:sandbox, impact:path-escape}"
    else:
        example = "meta={...}"

    missing = ", ".join(missing_keys)
    return {
        "level": "info",
        "score": 300,
        "emoji": "🧠",
        "category": "teaching",
        "message": f"To also write this entry to `{target_log_type}` log, include required meta keys: {missing} (example: {example}).",
        "tone": "neutral",
    }


async def _process_bulk_items_parallel(
    items: List[Dict[str, Any]],
    project: Dict[str, Any],
    recent: List[str],
    state_snapshot: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    backend: Any,
) -> Dict[str, Any]:
    """Process bulk items using Phase 1 ParallelBulkProcessor for true parallel execution."""
    import time
    start_time = time.time()

    # Use Phase 1 ParallelBulkProcessor to chunk and process items
    chunk_size = _PARALLEL_PROCESSOR.calculate_optimal_chunk_size(len(items))
    chunks = _PARALLEL_PROCESSOR.create_chunks(items, chunk_size)

    # Process chunks in parallel
    chunk_results = await _PARALLEL_PROCESSOR.process_chunks_parallel(
        chunks,
        process_chunk_func=lambda chunk: _process_chunk_sequential(
            chunk, project, recent, state_snapshot, base_log_type, log_cache, backend
        )
    )

    # Aggregate results from all chunks
    all_written_lines = []
    all_failed_items = []
    all_paths_used = []

    for chunk_result in chunk_results:
        if chunk_result["success"]:
            all_written_lines.extend(chunk_result["written_lines"])
            all_failed_items.extend(chunk_result["failed_items"])
            all_paths_used.extend(chunk_result["paths_used"])
        else:
            # If chunk failed completely, add all items as failed
            chunk_index = chunk_results.index(chunk_result)
            for i, item in enumerate(chunk_result.get("items", [])):
                all_failed_items.append({
                    "index": chunk_index * chunk_size + i,
                    "error": f"Chunk processing failed: {chunk_result.get('error', 'Unknown error')}",
                    "item": item
                })

    processing_time = time.time() - start_time

    return {
        "written_lines": all_written_lines,
        "failed_items": all_failed_items,
        "paths_used": all_paths_used,
        "chunks_used": len(chunks),
        "processing_time": processing_time,
        "success": True
    }


async def _process_chunk_sequential(
    chunk: List[Dict[str, Any]],
    project: Dict[str, Any],
    recent: List[str],
    state_snapshot: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    backend: Any,
) -> Dict[str, Any]:
    """Process a single chunk of items sequentially."""
    written_lines: List[str] = []
    failed_items: List[Dict[str, Any]] = []
    paths_used: List[str] = []
    rotated_paths: set[Path] = set()

    # Process items in this chunk using the same logic as sequential processing
    for i, item in enumerate(chunk):
        try:
            # Reuse the existing item processing logic
            result = await _process_single_item(
                item, i, project, base_log_type, log_cache, rotated_paths, backend
            )

            if result["success"]:
                written_lines.append(result["written_line"])
                if result["path_used"] not in paths_used:
                    paths_used.append(result["path_used"])
            else:
                failed_items.append(result["failed_item"])

        except Exception as exc:
            failed_items.append({
                "index": i,
                "error": f"Item processing failed: {str(exc)}",
                "item": item
            })

    return {
        "success": True,
        "written_lines": written_lines,
        "failed_items": failed_items,
        "paths_used": paths_used,
        "items": chunk
    }


async def _process_single_item(
    item: Dict[str, Any],
    index: int,
    project: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
    rotated_paths: set[Path],
    backend: Any,
) -> Dict[str, Any]:
    """Process a single bulk item - extracted from original loop for reuse."""
    # This function contains the core item processing logic
    # extracted from the original sequential loop

    # Validate required fields
    if "message" not in item:
        return {
            "success": False,
            "failed_item": {
                "index": index,
                "error": "Missing required 'message' field",
                "item": item
            }
        }

    item_message = item["message"]
    if not item_message.strip():
        return {
            "success": False,
            "failed_item": {
                "index": index,
                "error": "Message cannot be empty",
                "item": item
            }
        }

    # Enhanced message validation with auto-sanitization
    validation_error = _validate_message(item_message)
    if validation_error:
        if "newline" in validation_error:
            item_message = _sanitize_message(item_message)
            item["message"] = item_message
        else:
            return {
                "success": False,
                "failed_item": {
                    "index": index,
                    "error": validation_error,
                    "item": item
                }
            }

    # Extract item properties with defaults
    item_status = item.get("status")
    item_emoji = item.get("emoji")
    item_agent = item.get("agent")
    item_meta = item.get("meta")
    item_timestamp = item.get("timestamp_utc")

    # Resolve values similar to single entry
    resolved_emoji = _resolve_emoji(item_emoji, item_status, project)
    defaults = project.get("defaults") or {}
    resolved_agent = _sanitize_identifier(resolve_fallback_chain(item_agent, defaults.get("agent"), "Scribe"))
    timestamp_dt, timestamp, timestamp_warning = _resolve_timestamp(item_timestamp)
    meta_pairs = _normalise_meta(item_meta)
    meta_payload = {key: value for key, value in meta_pairs}

    entry_log_type = (item.get("log_type") or base_log_type).lower()
    log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)

    # Rotate if needed (only once per path)
    if log_path not in rotated_paths:
        await _rotate_if_needed(log_path, repo_root=Path(project.get("root") or settings.project_root).resolve())
        rotated_paths.add(log_path)

    requirement_error = _validate_log_requirements(log_definition, meta_payload)
    if requirement_error:
        return {
            "success": False,
            "failed_item": {
                "index": index,
                "error": requirement_error,
                "item": item
            }
        }

    meta_payload.setdefault("log_type", entry_log_type)

    # Compose the log line
    repo_slug = _get_repo_slug(project["root"])
    project_slug = project["name"]
    entry_id = _generate_deterministic_entry_id(
        repo_slug, project_slug, timestamp, resolved_agent, item_message, meta_payload
    )

    log_line = shared_compose_line(
        message=item_message,
        emoji=resolved_emoji,
        agent=resolved_agent,
        meta=meta_payload,
        timestamp=timestamp,
        entry_id=entry_id,
        log_type=entry_log_type,
        log_definition=log_definition,
    )

    # Write to file
    try:
        await append_line(
            log_path,
            log_line,
            repo_root=Path(project.get("root") or settings.project_root).resolve(),
            context={"component": "logs", "project_name": project.get("name")},
        )
        return {
            "success": True,
            "written_line": log_line,
            "path_used": str(log_path)
        }
    except Exception as exc:
        return {
            "success": False,
            "failed_item": {
                "index": index,
                "error": f"Failed to write entry: {str(exc)}",
                "item": item
            }
        }


async def _append_bulk_entries(
    items: List[Dict[str, Any]],
    project: Dict[str, Any],
    recent: List[str],
    state_snapshot: Dict[str, Any],
    base_log_type: str,
    log_cache: Dict[str, Tuple[Path, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Enhanced bulk entry processing with robust error handling and optimizations."""
    if not items:
        return {
            "ok": False,
            "error": "Items list cannot be empty",
            "recent_projects": list(recent),
        }

    written_lines: List[str] = []
    failed_items = []
    paths_used: List[str] = []
    rotated_paths: set[Path] = set()

    # Batch database operations for better performance
    backend = server_module.storage_backend
    batch_db_entries = []

    # Ensure project exists in database
    if backend:
        try:
            timeout = settings.storage_timeout_seconds
            async with asyncio.timeout(timeout):
                record = await backend.fetch_project(project["name"])
            if not record:
                async with asyncio.timeout(timeout):
                    record = await backend.upsert_project(
                        name=project["name"],
                        repo_root=project["root"],
                        progress_log_path=project["progress_log"],
                    )
        except Exception as exc:
            logger.warning("Database setup failed: %s", exc)
            backend = None  # Disable database for this batch

    # Determine if parallel processing should be used (Phase 1 optimization)
    use_parallel_processing = len(items) >= 10  # Use parallel for 10+ items

    if use_parallel_processing:
        # Use Phase 1 ParallelBulkProcessor for large batches
        try:
            parallel_result = await _process_bulk_items_parallel(
                items, project, recent, state_snapshot, base_log_type, log_cache, backend
            )

            # Merge results from parallel processing
            written_lines.extend(parallel_result["written_lines"])
            failed_items.extend(parallel_result["failed_items"])
            paths_used.extend(parallel_result["paths_used"])

            # Add parallel processing info to response
            processing_info = {
                "parallel_processing": True,
                "items_processed": len(items),
                "parallel_chunks": parallel_result.get("chunks_used", 1),
                "processing_time": parallel_result.get("processing_time", 0)
            }

        except Exception as parallel_error:
            # Fallback to sequential processing if parallel fails
            logger.warning("Parallel processing failed, falling back to sequential: %s", parallel_error)
            use_parallel_processing = False

    if not use_parallel_processing:
        # Process each item with enhanced error handling (sequential)
        processing_info = {"parallel_processing": False, "items_processed": len(items)}

    # Execute pre_append hooks on all items before processing
    if BRIDGE_HOOKS_AVAILABLE and get_hook_manager:
        try:
            hook_manager = get_hook_manager()
            # Call pre_append hook for each item to allow bridges to modify entries
            for i, item in enumerate(items):
                try:
                    items[i] = await hook_manager.execute_pre_append(item)
                except Exception as hook_error:
                    # Critical hooks will raise RuntimeError, others are logged
                    logger.warning("Pre-append hook failed for item %d: %s", i, hook_error)
                    # If it's a RuntimeError (critical hook failure), propagate it
                    if isinstance(hook_error, RuntimeError):
                        raise
        except Exception as hooks_error:
            # If hooks are completely broken, log but continue
            logger.warning("Bridge hooks unavailable or failed: %s", hooks_error)

    for i, item in enumerate(items):
        try:
            # Validate required fields
            if "message" not in item:
                failed_items.append({
                    "index": i,
                    "error": "Missing required 'message' field",
                    "item": item
                })
                continue

            item_message = item["message"]
            if not item_message.strip():
                failed_items.append({
                    "index": i,
                    "error": "Message cannot be empty",
                    "item": item
                })
                continue

            # Enhanced message validation with auto-sanitization
            validation_error = _validate_message(item_message)
            if validation_error:
                # Try to auto-fix common issues
                if "newline" in validation_error:
                    # Sanitize newlines for this item
                    item_message = _sanitize_message(item_message)
                    item["message"] = item_message  # Update for later processing
                else:
                    failed_items.append({
                        "index": i,
                        "error": validation_error,
                        "item": item
                    })
                    continue

            # Extract item properties with defaults
            item_status = item.get("status")
            item_emoji = item.get("emoji")
            item_agent = item.get("agent")
            item_meta = item.get("meta")
            item_timestamp = item.get("timestamp_utc")

            # Resolve values similar to single entry
            resolved_emoji = _resolve_emoji(item_emoji, item_status, project)
            defaults = project.get("defaults") or {}
            resolved_agent = _sanitize_identifier(resolve_fallback_chain(item_agent, defaults.get("agent"), "Scribe"))
            timestamp_dt, timestamp, timestamp_warning = _resolve_timestamp(item_timestamp)
            meta_pairs = _normalise_meta(item_meta)
            meta_payload = {key: value for key, value in meta_pairs}

            entry_log_type = (item.get("log_type") or base_log_type).lower()
            log_path, log_definition = _resolve_log_target(project, entry_log_type, log_cache)
            if log_path not in rotated_paths:
                await _rotate_if_needed(log_path, repo_root=Path(project.get("root") or settings.project_root).resolve())
                rotated_paths.add(log_path)

            requirement_error = _validate_log_requirements(log_definition, meta_payload)
            if requirement_error:
                failed_items.append({
                    "index": i,
                    "error": requirement_error,
                    "item": item
                })
                continue
            meta_payload.setdefault("log_type", entry_log_type)

            # Generate deterministic entry_id for bulk item
            repo_slug = _get_repo_slug(project["root"])
            project_slug = project["name"].lower().replace(" ", "-").replace("_", "-")
            entry_id = _generate_deterministic_entry_id(
                repo_slug=repo_slug,
                project_slug=project_slug,
                timestamp=timestamp,
                agent=resolved_agent,
                message=item_message,
                meta=meta_payload
            )

            # Compose line
            line = _compose_line(
                emoji=resolved_emoji,
                timestamp=timestamp,
                agent=resolved_agent,
                project_name=project["name"],
                message=item_message,
                meta_pairs=meta_pairs,
                entry_id=entry_id,
            )

            # Write to file immediately (ensures order)
            await append_line(
                log_path,
                line,
                repo_root=Path(project.get("root") or settings.project_root).resolve(),
                context={"component": "logs", "project_name": project.get("name")},
            )
            written_lines.append(line)
            paths_used.append(str(log_path))

            # Touch Project Registry entry (best-effort, without blocking bulk flow).
            try:
                _PROJECT_REGISTRY.touch_entry(project["name"], log_type=entry_log_type)
            except Exception:
                pass

            # Prepare database entry for batch processing
            if backend:
                sha_value = hashlib.sha256(line.encode("utf-8")).hexdigest()
                ts_dt = timestamp_dt or utcnow()

                batch_db_entries.append({
                    "entry_id": entry_id,
                    "record": record,
                    "ts": ts_dt,
                    "emoji": resolved_emoji,
                    "agent": resolved_agent,
                    "message": item_message,
                    "meta": meta_payload,
                    "raw_line": line,
                    "sha256": sha_value,
                    "log_type": entry_log_type,
                    "index": i
                })

        except Exception as exc:
            failed_items.append({
                "index": i,
                "error": f"Processing error: {exc}",
                "item": item
            })

    # Batch database write for performance
    if backend and batch_db_entries:
        try:
            timeout = settings.storage_timeout_seconds
            async with asyncio.timeout(timeout):
                for db_entry in batch_db_entries:
                    await backend.insert_entry(
                        entry_id=db_entry["entry_id"],
                        project=db_entry["record"],
                        ts=db_entry["ts"],
                        emoji=db_entry["emoji"],
                        agent=db_entry["agent"],
                        message=db_entry["message"],
                        meta=db_entry["meta"],
                        raw_line=db_entry["raw_line"],
                        sha256=db_entry["sha256"],
                        log_type=db_entry.get("log_type", "progress"),
                    )

            # Execute post_append hooks after successful database write
            if BRIDGE_HOOKS_AVAILABLE and get_hook_manager:
                try:
                    hook_manager = get_hook_manager()
                    # Notify bridges of successful entries (fire-and-forget)
                    for db_entry in batch_db_entries:
                        try:
                            await hook_manager.execute_post_append(db_entry)
                        except Exception as hook_error:
                            # Post hooks are non-blocking, just log errors
                            logger.warning("Post-append hook failed: %s", hook_error)
                except Exception as hooks_error:
                    # If hooks are completely broken, log but continue
                    logger.warning("Bridge post hooks unavailable or failed: %s", hooks_error)

        except Exception as exc:
            # Mark all items in this batch as failed
            for db_entry in batch_db_entries:
                failed_items.append({
                    "index": db_entry["index"],
                    "error": f"Database error: {exc}",
                    "retry_possible": True
                })
            logger.warning("Batch database write failed: %s", exc)

    # Get reminders
    reminders_payload = await reminders.get_reminders(
        project,
        tool_name="append_entry",
        state=state_snapshot,
    )

    # Build comprehensive result
    unique_paths = sorted(set(paths_used))
    result = {
        "ok": len(failed_items) == 0,
        "written_count": len(written_lines),
        "failed_count": len(failed_items),
        "written_lines": written_lines,
        "failed_items": failed_items,
        "path": unique_paths[0] if unique_paths else project.get("progress_log"),
        "paths": unique_paths,
        "recent_projects": list(recent),
        "reminders": reminders_payload,
    }

    # Add performance metrics for large operations
    if len(items) > 10:
        # Include Phase 1 parallel processing information
        if 'processing_info' in locals():
            result["performance"] = {
                "total_items": len(items),
                "items_per_second": len(items) / 1.0,  # Approximate
                "database_batch_size": len(batch_db_entries) if backend else 0,
                "phase1_parallel_processing": processing_info
            }
        else:
            result["performance"] = {
                "total_items": len(items),
                "items_per_second": len(items) / 1.0,  # Approximate
                "database_batch_size": len(batch_db_entries) if backend else 0,
            }

    return result


async def _rotate_if_needed(path: Path, repo_root: Optional[Path] = None) -> None:
    max_bytes = settings.log_max_bytes
    if max_bytes <= 0:
        return
    if not path.exists():
        return
    size = await asyncio.to_thread(lambda: path.stat().st_size)
    if size < max_bytes:
        return
    suffix = utcnow().strftime("%Y%m%d%H%M%S")
    await rotate_file(path, suffix, confirm=True, repo_root=repo_root)
