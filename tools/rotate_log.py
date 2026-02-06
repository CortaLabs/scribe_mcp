"""Flexible log rotation tools leveraging shared logging utilities."""

from __future__ import annotations

import asyncio
import json
import logging
import re

logger = logging.getLogger(__name__)
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from scribe_mcp.utils.integrity import count_file_lines
from scribe_mcp.utils.slug import normalize_project_input
from scribe_mcp.utils.time import format_utc, utcnow

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.config.log_config import load_log_config
from scribe_mcp.utils.config_manager import ConfigManager, apply_response_defaults, build_response_payload
from scribe_mcp.utils.bulk_processor import BulkProcessor
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    resolve_log_definition as shared_resolve_log_definition,
    resolve_logging_context,
)
from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError
from scribe_mcp.templates import (
    TEMPLATE_FILENAMES,
    create_rotation_context,
    load_templates,
    substitution_context,
)
from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param
from scribe_mcp.utils.parameter_validator import ToolValidator, BulletproofParameterCorrector
from scribe_mcp.utils.estimator import (
    EntryCountEstimate,
    FileSizeEstimator,
    ThresholdEstimator
)
from scribe_mcp.utils.error_handler import ErrorHandler, HealingErrorHandler, ExceptionHealer
from scribe_mcp.utils.config_manager import ConfigManager, apply_response_defaults, build_response_payload, BulletproofFallbackManager
from scribe_mcp.tools.config.rotate_log_config import RotateLogConfig
from scribe_mcp.utils.audit import get_audit_manager, store_rotation_metadata
from scribe_mcp.utils import audit as audit_utils
from scribe_mcp.utils.files import rotate_file, verify_file_integrity, file_lock
from scribe_mcp.utils.integrity import (
    create_rotation_metadata,
    count_file_lines,
    compute_file_hash,
)
from scribe_mcp.utils.rotation_state import (
    get_next_sequence_number,
    get_state_manager,
    generate_rotation_id,
    update_project_state,
)
from scribe_mcp.utils.time import format_utc
from scribe_mcp import reminders

DEFAULT_AUTO_THRESHOLD_ENTRIES = 500
DEFAULT_BYTES_PER_LINE = 80.0
MIN_BYTES_PER_LINE = 16.0
MAX_BYTES_PER_LINE = 512.0
EMA_SMOOTHING_ALPHA = 0.2
ESTIMATION_BAND_RATIO = 0.1
ESTIMATION_BAND_MIN = 250
TAIL_SAMPLE_BYTES = 1024 * 1024
_SUFFIX_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


class _RotateLogHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module
        self.parameter_corrector = BulletproofParameterCorrector()
        self.error_handler = ErrorHandler()
        self.healing_error_handler = HealingErrorHandler()


_ROTATE_HELPER = _RotateLogHelper()


async def verify_rotation_integrity(rotation_id: str, project: str | None = None) -> Dict[str, Any]:
    """
    Verify archive integrity for a prior rotation.

    Backwards compatible helper for CLI/tests that import from `scribe_mcp.tools.rotate_log`.
    (Not an MCP tool entry-point.)
    """
    state = await server_module.state_manager.load()
    project_name = project or state.current_project
    if not project_name:
        return {"ok": False, "error": "No project configured"}

    try:
        integrity_ok, message = audit_utils.verify_rotation_integrity(project_name, rotation_id)
        return {
            "ok": True,
            "project": project_name,
            "rotation_id": rotation_id,
            "integrity_valid": bool(integrity_ok),
            "message": message,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc), "project": project_name, "rotation_id": rotation_id}


async def get_rotation_history(limit: int | None = None, project: str | None = None) -> Dict[str, Any]:
    """
    Return recent rotation history for the current (or explicit) project.

    Backwards compatible helper for CLI/tests that import from `scribe_mcp.tools.rotate_log`.
    (Not an MCP tool entry-point.)
    """
    state = await server_module.state_manager.load()
    project_name = project or state.current_project
    if not project_name:
        return {"ok": False, "error": "No project configured"}

    try:
        rotations = audit_utils.get_rotation_history(project_name, limit=limit)
        return {
            "ok": True,
            "project": project_name,
            "rotation_count": len(rotations),
            "rotations": rotations,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc), "project": project_name}

# Global configuration manager for parameter handling
_CONFIG_MANAGER = ConfigManager("rotate_log")

# Phase 3 Enhanced utilities integration
_EXCEPTION_HEALER = ExceptionHealer()
_FALLBACK_MANAGER = BulletproofFallbackManager()


def _heal_rotate_log_parameters(
    suffix: Optional[str] = None,
    custom_metadata: Optional[Dict[str, Any]] = None,
    confirm: bool = False,
    dry_run: bool = False,
    dry_run_mode: str = "estimate",
    log_type: Optional[str] = None,
    log_types: Optional[List[str]] = None,
    rotate_all: bool = False,
    auto_threshold: bool = False,
    threshold_entries: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None
) -> tuple[dict, bool, List[str]]:
    """Heal rotate_log parameters using Phase 1 exception handling."""
    healing_messages = []
    healing_applied = False

    # Define valid values for enum parameters
    valid_dry_run_modes = {"estimate", "precise"}
    valid_log_types = {"progress", "doc_updates", "security", "bugs"}

    healed_params = {}

    # Heal suffix parameter (string normalization)
    if suffix is not None:
        original_suffix = suffix
        healed_suffix = str(suffix).strip()
        # Sanitize suffix using existing regex
        healed_suffix = _SUFFIX_SANITIZER.sub('_', healed_suffix)
        if healed_suffix != original_suffix:
            healing_applied = True
            healing_messages.append(f"Auto-corrected suffix from '{original_suffix}' to '{healed_suffix}'")
        healed_params["suffix"] = healed_suffix
    else:
        healed_params["suffix"] = None

    # Heal custom_metadata parameter using Phase 1 corrector
    healed_metadata = BulletproofParameterCorrector.correct_metadata_parameter(custom_metadata)
    if healed_metadata != custom_metadata:
        healing_applied = True
        healing_messages.append(f"Auto-corrected custom_metadata parameter to valid dict")
    healed_params["custom_metadata"] = healed_metadata

    # Heal confirm parameter
    original_confirm = confirm
    healed_confirm = bool(confirm)
    if isinstance(confirm, str):
        healed_confirm = confirm.lower() in ("true", "1", "yes")
        if healed_confirm != confirm:
            healing_applied = True
            healing_messages.append(f"Auto-corrected confirm from '{confirm}' to {healed_confirm}")
    elif healed_confirm != original_confirm:
        healing_applied = True
        healing_messages.append(f"Auto-corrected confirm to boolean {healed_confirm}")
    healed_params["confirm"] = healed_confirm

    # Heal dry_run parameter
    original_dry_run = dry_run
    healed_dry_run = bool(dry_run)
    if isinstance(dry_run, str):
        healed_dry_run = dry_run.lower() in ("true", "1", "yes")
        if healed_dry_run != dry_run:
            healing_applied = True
            healing_messages.append(f"Auto-corrected dry_run from '{dry_run}' to {healed_dry_run}")
    elif healed_dry_run != original_dry_run:
        healing_applied = True
        healing_messages.append(f"Auto-corrected dry_run to boolean {healed_dry_run}")
    healed_params["dry_run"] = healed_dry_run

    # Heal dry_run_mode parameter
    if dry_run_mode is not None:
        original_dry_run_mode = dry_run_mode
        healed_dry_run_mode = BulletproofParameterCorrector.correct_enum_parameter(
            original_dry_run_mode, valid_dry_run_modes, "dry_run_mode", "estimate"
        )
        if healed_dry_run_mode != original_dry_run_mode:
            healing_applied = True
            healing_messages.append(f"Auto-corrected dry_run_mode from '{original_dry_run_mode}' to '{healed_dry_run_mode}'")
        healed_params["dry_run_mode"] = healed_dry_run_mode
    else:
        healed_params["dry_run_mode"] = "estimate"

    # Heal log_type parameter
    if log_type is not None:
        original_log_type = log_type
        healed_log_type = BulletproofParameterCorrector.correct_enum_parameter(
            original_log_type, valid_log_types, "log_type", "progress"
        )
        if healed_log_type != original_log_type:
            healing_applied = True
            healing_messages.append(f"Auto-corrected log_type from '{original_log_type}' to '{healed_log_type}'")
        healed_params["log_type"] = healed_log_type
    else:
        healed_params["log_type"] = None

    # Heal log_types array parameter
    if log_types is not None:
        original_log_types = log_types
        healed_log_types = BulletproofParameterCorrector.correct_list_parameter(
            original_log_types, "log_types"
        )
        if healed_log_types != original_log_types:
            healing_applied = True
            healing_messages.append(f"Auto-corrected log_types parameter from {original_log_types} to {healed_log_types}")
        healed_params["log_types"] = healed_log_types
    else:
        healed_params["log_types"] = None

    # Heal rotate_all parameter
    original_rotate_all = rotate_all
    healed_rotate_all = bool(rotate_all)
    if isinstance(rotate_all, str):
        healed_rotate_all = rotate_all.lower() in ("true", "1", "yes")
        if healed_rotate_all != rotate_all:
            healing_applied = True
            healing_messages.append(f"Auto-corrected rotate_all from '{rotate_all}' to {healed_rotate_all}")
    elif healed_rotate_all != original_rotate_all:
        healing_applied = True
        healing_messages.append(f"Auto-corrected rotate_all to boolean {healed_rotate_all}")
    healed_params["rotate_all"] = healed_rotate_all

    # Heal auto_threshold parameter
    original_auto_threshold = auto_threshold
    healed_auto_threshold = bool(auto_threshold)
    if isinstance(auto_threshold, str):
        healed_auto_threshold = auto_threshold.lower() in ("true", "1", "yes")
        if healed_auto_threshold != auto_threshold:
            healing_applied = True
            healing_messages.append(f"Auto-corrected auto_threshold from '{auto_threshold}' to {healed_auto_threshold}")
    elif healed_auto_threshold != original_auto_threshold:
        healing_applied = True
        healing_messages.append(f"Auto-corrected auto_threshold to boolean {healed_auto_threshold}")
    healed_params["auto_threshold"] = healed_auto_threshold

    # Heal threshold_entries parameter
    if threshold_entries is not None:
        original_threshold_entries = threshold_entries
        healed_threshold_entries = BulletproofParameterCorrector.correct_numeric_parameter(
            original_threshold_entries, 1, 10000, "threshold_entries", 500
        )
        if healed_threshold_entries != original_threshold_entries:
            healing_applied = True
            healing_messages.append(f"Auto-corrected threshold_entries from '{original_threshold_entries}' to '{healed_threshold_entries}'")
        healed_params["threshold_entries"] = healed_threshold_entries
    else:
        healed_params["threshold_entries"] = None

    # Heal config parameter - preserve RotateLogConfig objects if provided
    if config is not None:
        if isinstance(config, RotateLogConfig):
            # Config object is already valid, don't convert to dict
            healed_config = config
        else:
            # For non-RotateLogConfig objects, use basic healing but don't use correct_metadata_parameter
            # as it will convert objects to {"value": "string_representation"}
            if isinstance(config, dict):
                # Dict is already in good shape, just heal the values within it
                healed_config = {}
                for key, value in config.items():
                    if key in ["suffix", "custom_metadata", "dry_run_mode", "log_type"]:
                        # String parameters
                        if value is not None:
                            healed_config[key] = str(value).strip()
                        else:
                            healed_config[key] = value
                    elif key in ["confirm", "dry_run", "rotate_all", "auto_threshold"]:
                        # Boolean parameters
                        if isinstance(value, str):
                            healed_config[key] = value.lower() in ("true", "1", "yes")
                        else:
                            healed_config[key] = bool(value) if value is not None else value
                    elif key in ["threshold_entries"]:
                        # Numeric parameters
                        try:
                            healed_config[key] = int(value) if value is not None else value
                        except (ValueError, TypeError):
                            healed_config[key] = 500  # default
                    elif key in ["log_types"]:
                        # List parameters
                        if isinstance(value, str):
                            healed_config[key] = [item.strip() for item in value.split(",") if item.strip()]
                        elif isinstance(value, list):
                            healed_config[key] = value
                        else:
                            healed_config[key] = None
                    else:
                        healed_config[key] = value
                healing_applied = True
                healing_messages.append(f"Auto-corrected config parameter dictionary values")
            else:
                # Convert other types to dict structure
                healed_config = BulletproofParameterCorrector.correct_metadata_parameter(config)
                healing_applied = True
                healing_messages.append(f"Auto-corrected config parameter to valid dict")

            # Try to convert healed dict to RotateLogConfig if it has the right structure
            try:
                if isinstance(healed_config, dict):
                    healed_config = RotateLogConfig.from_legacy_params(**healed_config)
                    healing_messages.append(f"Converted healed config dict to RotateLogConfig object")
            except Exception as conversion_error:
                healing_messages.append(f"Failed to convert healed config to RotateLogConfig: {conversion_error}, using dict")
        healed_params["config"] = healed_config
    else:
        healed_params["config"] = None

    return healed_params, healing_applied, healing_messages


def _add_healing_info_to_rotate_response(
    response: Dict[str, Any],
    healing_applied: bool,
    healing_messages: List[str]
) -> Dict[str, Any]:
    """Add healing information to rotate_log response if parameters were corrected."""
    if healing_applied and healing_messages:
        response["parameter_healing"] = {
            "applied": True,
            "messages": healing_messages,
            "message": "Parameters auto-corrected using Phase 1 exception healing"
        }
    return response


class RotationTarget(NamedTuple):
    log_type: str
    path: Path
    definition: Dict[str, Any]


# Global estimator instances
_FILE_SIZE_ESTIMATOR = FileSizeEstimator(
    default_bytes_per_line=DEFAULT_BYTES_PER_LINE,
    min_bytes_per_line=MIN_BYTES_PER_LINE,
    max_bytes_per_line=MAX_BYTES_PER_LINE,
    tail_sample_bytes=TAIL_SAMPLE_BYTES
)
_THRESHOLD_ESTIMATOR = ThresholdEstimator()


async def _write_rotated_log_header(path: Path, content: str) -> None:
    """Write rendered rotation template to the freshly rotated log."""

    def _write() -> None:
        with file_lock(path, 'w', timeout=30.0) as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")

    await asyncio.to_thread(_write)


def _validate_rotation_parameters(
    suffix: Optional[str],
    custom_metadata: Optional[str],
    confirm: Optional[bool],
    dry_run: Optional[bool],
    dry_run_mode: Optional[str],
    log_type: Optional[str],
    log_types: Optional[List[str]],
    rotate_all: Optional[bool],
    auto_threshold: Optional[bool],
    threshold_entries: Optional[int],
    config: Optional[RotateLogConfig]
) -> Tuple[RotateLogConfig, Dict[str, Any]]:
    """
    Validate and prepare rotation parameters using enhanced Phase 3 utilities.

    This function replaces the monolithic parameter handling section of rotate_log
    with bulletproof parameter validation and healing.
    """
    try:
        # Apply Phase 1 BulletproofParameterCorrector for initial parameter healing
        healed_params = {}
        healing_applied = False

        # Define valid values for enum parameters
        valid_dry_run_modes = {"estimate", "precise"}
        valid_log_types = {"progress", "doc_updates", "security", "bugs"}

        # Heal suffix parameter
        if suffix:
            healed_suffix = _ROTATE_HELPER.parameter_corrector.correct_message_parameter(suffix)
            if healed_suffix != suffix:
                healed_params["suffix"] = healed_suffix
                healing_applied = True

        # Heal custom_metadata parameter
        if custom_metadata:
            healed_metadata = _ROTATE_HELPER.parameter_corrector.correct_metadata_parameter(custom_metadata)
            if healed_metadata != custom_metadata:
                healed_params["custom_metadata"] = healed_metadata
                healing_applied = True

        # Heal dry_run_mode parameter
        if dry_run_mode:
            healed_dry_run_mode = _ROTATE_HELPER.parameter_corrector.correct_enum_parameter(
                dry_run_mode, valid_dry_run_modes, field_name="dry_run_mode"
            )
            if healed_dry_run_mode != dry_run_mode:
                healed_params["dry_run_mode"] = healed_dry_run_mode
                healing_applied = True

        # Heal log_type parameter
        if log_type:
            healed_log_type = _ROTATE_HELPER.parameter_corrector.correct_enum_parameter(
                log_type, valid_log_types, field_name="log_type"
            )
            if healed_log_type != log_type:
                healed_params["log_type"] = healed_log_type
                healing_applied = True

        # Heal log_types parameter
        if log_types:
            healed_log_types = _ROTATE_HELPER.parameter_corrector.correct_list_parameter(
                log_types, field_name="log_types"
            )
            if healed_log_types != log_types:
                healed_params["log_types"] = healed_log_types
                healing_applied = True

        # Heal threshold_entries parameter
        if threshold_entries:
            healed_threshold = _ROTATE_HELPER.parameter_corrector.correct_numeric_parameter(
                threshold_entries, min_value=1, max_value=1000000, field_name="threshold_entries"
            )
            if healed_threshold != threshold_entries:
                healed_params["threshold_entries"] = healed_threshold
                healing_applied = True

        # Apply fallbacks for corrected parameters
        if healing_applied:
            fallback_params = _FALLBACK_MANAGER.resolve_parameter_fallback(
                "rotate_log", healed_params, context="parameter_validation"
            )
            healed_params.update(fallback_params)

        # Update parameters with healed values
        final_suffix = healed_params.get("suffix", suffix)
        final_custom_metadata = healed_params.get("custom_metadata", custom_metadata)
        final_confirm = healed_params.get("confirm", confirm)
        final_dry_run = healed_params.get("dry_run", dry_run)
        final_dry_run_mode = healed_params.get("dry_run_mode", dry_run_mode)
        final_log_type = healed_params.get("log_type", log_type)
        final_log_types = healed_params.get("log_types", log_types)
        final_rotate_all = healed_params.get("rotate_all", rotate_all)
        final_auto_threshold = healed_params.get("auto_threshold", auto_threshold)
        final_threshold_entries = healed_params.get("threshold_entries", threshold_entries)

        # Create configuration using dual parameter support
        if config is not None:
            # Create configuration from legacy parameters
            legacy_config = RotateLogConfig.from_legacy_params(
                suffix=final_suffix,
                custom_metadata=final_custom_metadata,
                confirm=final_confirm,
                dry_run=final_dry_run,
                dry_run_mode=final_dry_run_mode,
                log_type=final_log_type,
                log_types=final_log_types,
                rotate_all=final_rotate_all,
                auto_threshold=final_auto_threshold,
                threshold_entries=final_threshold_entries
            )

            # Merge with provided config (legacy parameters take precedence)
            config_dict = config.to_dict()
            legacy_dict = legacy_config.to_dict()

            for key, value in legacy_dict.items():
                if value is not None:
                    config_dict[key] = value

            final_config = RotateLogConfig(**config_dict)
        else:
            final_config = RotateLogConfig.from_legacy_params(
                suffix=final_suffix,
                custom_metadata=final_custom_metadata,
                confirm=final_confirm,
                dry_run=final_dry_run,
                dry_run_mode=final_dry_run_mode,
                log_type=final_log_type,
                log_types=final_log_types,
                rotate_all=final_rotate_all,
                auto_threshold=final_auto_threshold,
                threshold_entries=final_threshold_entries
            )

        return final_config, {"healing_applied": healing_applied, "healed_params": healed_params}

    except Exception as e:
        # Apply Phase 2 ExceptionHealer for parameter validation errors
        healed_exception = _EXCEPTION_HEALER.heal_parameter_validation_error(
            e, {
                "suffix": suffix,
                "dry_run_mode": dry_run_mode,
                "log_type": log_type,
                "threshold_entries": threshold_entries
            }
        )

        if healed_exception["success"]:
            # Use healed values from exception recovery
            fallback_params = _FALLBACK_MANAGER.resolve_parameter_fallback(
                "rotate_log", healed_exception["healed_values"], context="exception_healing"
            )

            # Create safe fallback configuration
            safe_config = RotateLogConfig.from_legacy_params(
                suffix=fallback_params.get("suffix", suffix),
                custom_metadata=fallback_params.get("custom_metadata", custom_metadata),
                confirm=fallback_params.get("confirm", confirm),
                dry_run=fallback_params.get("dry_run", dry_run),
                dry_run_mode=fallback_params.get("dry_run_mode", dry_run_mode),
                log_type=fallback_params.get("log_type", log_type),
                log_types=fallback_params.get("log_types", log_types),
                rotate_all=fallback_params.get("rotate_all", rotate_all),
                auto_threshold=fallback_params.get("auto_threshold", auto_threshold),
                threshold_entries=fallback_params.get("threshold_entries", threshold_entries)
            )

            return safe_config, {
                "healing_applied": True,
                "exception_healing": True,
                "healed_params": healed_exception["healed_values"],
                "fallback_used": True
            }
        else:
            # Ultimate fallback - use BulletproofFallbackManager
            fallback_params = _FALLBACK_MANAGER.apply_emergency_fallback("rotate_log", {
                "suffix": suffix,
                "dry_run_mode": dry_run_mode,
                "log_type": log_type,
                "threshold_entries": threshold_entries or 500
            })

            emergency_config = RotateLogConfig.from_legacy_params(
                suffix=fallback_params.get("suffix", suffix),
                custom_metadata=fallback_params.get("custom_metadata", custom_metadata),
                confirm=fallback_params.get("confirm", False),  # Safe default
                dry_run=fallback_params.get("dry_run", True),  # Safe default
                dry_run_mode=fallback_params.get("dry_run_mode", "estimate"),
                log_type=fallback_params.get("log_type", "progress"),
                log_types=fallback_params.get("log_types", log_types),
                rotate_all=fallback_params.get("rotate_all", rotate_all),
                auto_threshold=fallback_params.get("auto_threshold", auto_threshold),
                threshold_entries=fallback_params.get("threshold_entries", 500)
            )

            return emergency_config, {
                "healing_applied": True,
                "emergency_fallback": True,
                "fallback_params": fallback_params
            }


def _prepare_rotation_operation(
    final_config: RotateLogConfig,
    context,
    project: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Prepare rotation operation with enhanced error handling and validation.

    This function extracts the rotation preparation logic from the monolithic
    rotate_log function and adds bulletproof error handling.
    """
    try:
        # Extract parameters from config
        suffix = final_config.suffix
        custom_metadata = final_config.custom_metadata
        confirm = final_config.confirm
        dry_run = final_config.dry_run
        dry_run_mode = final_config.dry_run_mode
        log_type = final_config.log_type
        log_types = final_config.log_types
        rotate_all = final_config.rotate_all
        auto_threshold = final_config.auto_threshold
        threshold_entries = final_config.threshold_entries

        # Determine which log types to rotate
        try:
            if rotate_all:
                # Rotate all configured log types
                log_config = load_log_config(project["root"])
                target_log_types = list(log_config.keys())
            elif log_types:
                # Use specified log types
                target_log_types = log_types
            elif log_type:
                # Use single log type
                target_log_types = [log_type]
            else:
                # Default to progress log
                target_log_types = ["progress"]

        except Exception as log_type_error:
            # Try to heal log type determination error
            healed_log_types = _EXCEPTION_HEALER.heal_parameter_validation_error(
                log_type_error, {"rotate_all": rotate_all, "log_type": log_type, "log_types": log_types}
            )

            if healed_log_types["success"]:
                target_log_types = healed_log_types["healed_values"].get("target_log_types", ["progress"])
            else:
                # Apply fallback log types
                fallback_log_types = _FALLBACK_MANAGER.apply_context_aware_defaults(
                    "rotate_log", {"operation": "determine_log_types", "project": project}
                )
                target_log_types = fallback_log_types.get("target_log_types", ["progress"])

        # Validate log types
        valid_log_types = {"progress", "doc_updates", "security", "bugs"}
        validated_log_types = []
        for lt in target_log_types:
            if lt in valid_log_types:
                validated_log_types.append(lt)
            else:
                # Try to heal invalid log type
                healed_lt = _ROTATE_HELPER.parameter_corrector.correct_enum_parameter(
                    lt, valid_log_types, field_name="log_type"
                )
                if healed_lt in valid_log_types:
                    validated_log_types.append(healed_lt)

        if not validated_log_types:
            validated_log_types = ["progress"]  # Fallback to progress log

        # Process custom metadata
        processed_metadata = {}
        try:
            if custom_metadata:
                # Try to parse as JSON
                try:
                    processed_metadata = json.loads(custom_metadata)
                except json.JSONDecodeError:
                    # Try to heal JSON parsing
                    healed_json = _EXCEPTION_HEALER.heal_parameter_validation_error(
                        ValueError("Invalid JSON in custom_metadata"),
                        {"custom_metadata": custom_metadata, "error_type": "json_decode"}
                    )

                    if healed_json["success"]:
                        metadata_str = healed_json["healed_values"].get("custom_metadata", "{}")
                        processed_metadata = json.loads(metadata_str)
                    else:
                        # Fallback to string metadata
                        processed_metadata = {"custom_metadata": custom_metadata, "json_parse_failed": True}
        except Exception as metadata_error:
            # Apply fallback metadata handling
            fallback_metadata = _FALLBACK_MANAGER.apply_context_aware_defaults(
                "rotate_log", {"custom_metadata": custom_metadata, "operation": "metadata_processing"}
            )
            processed_metadata = fallback_metadata.get("processed_metadata", {"error": str(metadata_error)})

        # Determine rotation mode
        if confirm is None:
            final_confirm = auto_threshold or False
        else:
            final_confirm = confirm

        if dry_run is None:
            final_dry_run = not final_confirm
        else:
            final_dry_run = dry_run

        # Validate dry run mode
        if dry_run_mode and dry_run_mode not in {"estimate", "precise"}:
            healed_mode = _ROTATE_HELPER.parameter_corrector.correct_enum_parameter(
                dry_run_mode, {"estimate", "precise"}, field_name="dry_run_mode"
            )
            final_dry_run_mode = healed_mode if healed_mode else "estimate"
        else:
            final_dry_run_mode = dry_run_mode or "estimate"

        # Set up rotation parameters for each log type
        rotation_operations = []
        for log_type_name in validated_log_types:
            try:
                # Get log file path (always normalize to Path)
                if log_type_name == "progress":
                    log_path = Path(project["progress_log"])
                else:
                    log_root = Path(project["root"])
                    log_path = log_root / f"{log_type_name}.log"

                # Check if log file exists
                if not log_path.exists():
                    # Skip non-existent logs with warning
                    rotation_operations.append({
                        "log_type": log_type_name,
                        "log_path": log_path,
                        "status": "skipped",
                        "reason": "file_not_found",
                        "warning": f"Log file {log_path} does not exist"
                    })
                    continue

                # Get entry count for threshold checking
                try:
                    if final_dry_run_mode == "precise":
                        # Precise count
                        entry_count = count_file_lines(log_path)
                    else:
                        # Estimate count
                        estimator = EntryCountEstimate()
                        entry_count = estimator.estimate(log_path)
                except Exception as count_error:
                    # Try to heal counting error
                    healed_count = _EXCEPTION_HEALER.heal_document_operation_error(
                        count_error, {"log_path": str(log_path), "operation": "count_entries"}
                    )

                    if healed_count["success"]:
                        entry_count = healed_count["healed_values"].get("entry_count", 0)
                    else:
                        # Apply fallback estimation
                        entry_count = 100  # Safe fallback estimate

                # Check auto threshold
                should_rotate = True
                threshold_reason = None

                if auto_threshold and threshold_entries:
                    if entry_count < threshold_entries:
                        should_rotate = False
                        threshold_reason = f"Below threshold: {entry_count} < {threshold_entries}"

                # Prepare operation details
                operation = {
                    "log_type": log_type_name,
                    "log_path": log_path,
                    "entry_count": entry_count,
                    "should_rotate": should_rotate,
                    "threshold_reason": threshold_reason,
                    "confirm": final_confirm,
                    "dry_run": final_dry_run,
                    "dry_run_mode": final_dry_run_mode,
                    "suffix": suffix,
                    "metadata": processed_metadata.copy()
                }

                if should_rotate:
                    rotation_operations.append(operation)

            except Exception as op_error:
                # Add error operation but continue with other log types
                error_operation = {
                    "log_type": log_type_name,
                    "status": "error",
                    "error": str(op_error),
                    "warning": f"Failed to prepare rotation for {log_type_name}: {str(op_error)}",
                    # Provide a best-effort log_path when available so execution
                    # logic can still reason about this operation without crashing.
                    "log_path": Path(project["progress_log"]) if log_type_name == "progress" else None,
                }
                rotation_operations.append(error_operation)

        # Return preparation results
        return {
            "rotation_operations": rotation_operations,
            "validated_log_types": validated_log_types,
            "final_confirm": final_confirm,
            "final_dry_run": final_dry_run,
            "final_dry_run_mode": final_dry_run_mode,
            "processed_metadata": processed_metadata,
            "preparation_complete": True
        }

    except Exception as e:
        # Apply comprehensive exception healing for rotation preparation
        healed_result = _EXCEPTION_HEALER.heal_complex_exception_combination(
            e, {
                "operation": "prepare_rotation_operation",
                "config": final_config.to_dict(),
                "project": project
            }
        )

        if healed_result and healed_result.get("success") and "healed_values" in healed_result:
            # Create emergency rotation operation; best-effort log_path for progress.
            emergency_params = _FALLBACK_MANAGER.apply_emergency_fallback(
                "rotate_log", healed_result["healed_values"]
            )

            try:
                emergency_log_path = Path(project.get("progress_log", ""))
            except Exception:
                emergency_log_path = None

            return {
                "rotation_operations": [{
                    "log_type": "progress",
                    "status": "emergency_fallback",
                    "error": str(e),
                    "emergency_params": emergency_params,
                    "log_path": emergency_log_path,
                }],
                "validated_log_types": ["progress"],
                "final_confirm": False,
                "final_dry_run": True,
                "final_dry_run_mode": "estimate",
                "processed_metadata": {"emergency_fallback": True, "error": str(e)},
                "preparation_complete": True,
                "emergency_fallback": True
            }
        else:
            return {
                "rotation_operations": [],
                "validated_log_types": [],
                "final_confirm": False,
                "final_dry_run": True,
                "final_dry_run_mode": "estimate",
                "processed_metadata": {"preparation_failed": True, "error": str(e)},
                "preparation_complete": False,
                "error": str(e)
            }


async def _execute_rotation_with_fallbacks(
    rotation_prep: Dict[str, Any],
    final_config: RotateLogConfig,
    context,
    project: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute rotation operations with comprehensive error handling and intelligent fallbacks.

    This function extracts the rotation execution logic from the monolithic rotate_log
    function and adds bulletproof error handling with multiple fallback strategies.
    """
    try:
        rotation_operations = rotation_prep["rotation_operations"]
        final_confirm = rotation_prep["final_confirm"]
        final_dry_run = rotation_prep["final_dry_run"]
        processed_metadata = rotation_prep["processed_metadata"]

        execution_results = []
        successful_rotations = []
        failed_rotations = []
        skipped_rotations = []

        # Process each rotation operation
        for operation in rotation_operations:
            try:
                log_type = operation.get("log_type", "unknown")
                log_path = operation.get("log_path")

                # If we don't have a log_path (e.g., emergency/errored prep),
                # record a structured failure and skip execution for this entry.
                if log_path is None:
                    error_result = {
                        "log_type": log_type,
                        "status": "failed",
                        "error": "Missing log_path for rotation operation",
                        "operation_level_error": True,
                    }
                    failed_rotations.append(error_result)
                    execution_results.append(error_result)
                    continue

                # Check if operation should be skipped
                if not operation.get("should_rotate", True):
                    skipped_result = {
                        "log_type": log_type,
                        "status": "skipped",
                        "reason": operation.get("threshold_reason", "Unknown reason"),
                        "entry_count": operation.get("entry_count", 0)
                    }
                    skipped_rotations.append(skipped_result)
                    execution_results.append(skipped_result)
                    continue

                # Prepare rotation details
                rotation_details = {
                    "log_path": log_path,
                    "suffix": operation.get("suffix"),
                    "dry_run": final_dry_run,
                    "dry_run_mode": operation.get("dry_run_mode", "estimate"),
                    "metadata": operation.get("metadata", {}),
                    "entry_count": operation.get("entry_count", 0)
                }

                # Execute rotation with error handling
                try:
                    if final_dry_run:
                        # Dry run execution
                        if operation.get("dry_run_mode") == "precise":
                            # Precise dry run: full line count
                            entry_count = count_file_lines(str(log_path))
                        else:
                            # Lightweight estimate based on file size
                            try:
                                size_bytes = log_path.stat().st_size if log_path.exists() else 0
                            except OSError:
                                size_bytes = 0
                            # Simple heuristic: avoid pulling in the full estimator stack here
                            entry_count = int(size_bytes / DEFAULT_BYTES_PER_LINE) if size_bytes > 0 else 0

                        dry_run_result = {
                            "log_type": log_type,
                            "status": "dry_run_complete",
                            "dry_run": True,
                            "entry_count": entry_count,
                            "estimated_size": log_path.stat().st_size if log_path.exists() else 0,
                            "would_rotate": entry_count > 0
                        }
                        execution_results.append(dry_run_result)
                        successful_rotations.append(dry_run_result)

                    else:
                        # Actual rotation execution
                        try:
                            rotation_id = generate_rotation_id(project["name"])
                            sequence_number = get_next_sequence_number(project["name"])
                            rotation_timestamp = format_utc(utcnow())

                            # Execute file rotation
                            repo_root = Path(project.get("root") or settings.project_root).resolve()

                            # Get hash chain info and compute current file hash for proper template
                            state_manager = get_state_manager()
                            hash_chain_info = state_manager.get_hash_chain_info(project["name"])
                            previous_hash = hash_chain_info.get("last_hash")

                            # Compute hash of current log before rotation (for hash chain)
                            current_log_hash = ""
                            current_entry_count = operation.get("entry_count", 0)
                            try:
                                if log_path.exists():
                                    current_log_hash = compute_file_hash(log_path)
                                    if current_entry_count == 0:
                                        current_entry_count = count_file_lines(str(log_path))
                            except Exception:
                                pass  # Best effort - hash chain will work without this

                            # Build rotation context with hash chain info
                            rotation_context = create_rotation_context(
                                rotation_id=rotation_id,
                                rotation_timestamp=rotation_timestamp,
                                previous_log_path=str(log_path),
                                previous_log_hash=current_log_hash,
                                previous_log_entries=str(current_entry_count),
                                current_sequence=str(sequence_number),
                                total_rotations=str(sequence_number),
                                hash_chain_previous=previous_hash or "",
                                hash_chain_sequence=str(sequence_number),
                                hash_chain_root=hash_chain_info.get("root_hash") or "",
                            )

                            # Generate proper template content with Jinja2 and hash chain info
                            template_content = await _build_template_content(log_type, project, rotation_context)

                            rotation_started = time.monotonic()
                            archive_path = await rotate_file(
                                log_path,
                                suffix=operation.get("suffix"),
                                confirm=True,
                                repo_root=repo_root,
                                template_content=template_content,  # Pass the full template!
                            )
                            rotation_duration = time.monotonic() - rotation_started

                            # Verify rotation integrity
                            archive_info = verify_file_integrity(archive_path, repo_root=repo_root)
                            integrity_ok = bool(archive_info.get("exists")) and not archive_info.get("error")

                            rotation_metadata = create_rotation_metadata(
                                archived_file_path=str(archive_path),
                                rotation_uuid=rotation_id,
                                rotation_timestamp=rotation_timestamp,
                                sequence_number=sequence_number,
                                log_type=log_type,
                            )
                            audit_success = store_rotation_metadata(project["name"], rotation_metadata)
                            state_success = update_project_state(project["name"], rotation_metadata)

                            rotation_result = {
                                "log_type": log_type,
                                "status": "rotated" if integrity_ok else "rotated_with_warnings",
                                "dry_run": False,
                                "original_path": str(log_path),
                                "archive_path": str(archive_path),
                                "entry_count": rotation_metadata.get("entry_count", operation.get("entry_count", 0)),
                                "rotation_id": rotation_id,
                                "sequence_number": sequence_number,
                                "rotation_completed": True,
                                "rotation_duration_seconds": rotation_duration,
                                "archive_hash": rotation_metadata.get("file_hash"),
                                "archive_sha256": rotation_metadata.get("file_hash"),
                                "archive_size_bytes": rotation_metadata.get("file_size"),
                                "integrity_verified": integrity_ok,
                                "audit_trail_stored": bool(audit_success),
                                "state_updated": bool(state_success),
                            }

                            if not integrity_ok:
                                rotation_result["warning"] = "Archive integrity verification failed"

                            execution_results.append(rotation_result)
                            successful_rotations.append(rotation_result)

                        except Exception as rotation_error:
                            # Try to heal rotation execution error
                            healed_rotation = _EXCEPTION_HEALER.heal_rotation_error(
                                rotation_error, {
                                    "log_path": str(log_path),
                                    "log_type": log_type,
                                    "operation": "file_rotation"
                                }
                            )

                            if healed_rotation["success"]:
                                # Try alternative rotation method
                                try:
                                    # Simple rotation fallback: rename current log and
                                    # create a fresh file with rotation header.
                                    fallback_suffix = operation.get(
                                        "suffix",
                                        f"rotated-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                                    )
                                    archive_path = log_path.with_suffix(
                                        f".{fallback_suffix}{log_path.suffix}"
                                    )

                                    # Move current log to archive
                                    await asyncio.to_thread(lambda: log_path.rename(archive_path))

                                    # Write rotation header into the new log file
                                    # Try to use proper template if rotation_context exists, otherwise fallback
                                    try:
                                        # rotation_context was created before the failure, use it
                                        if 'rotation_context' in dir() and rotation_context:
                                            header = await _build_template_content(log_type, project, rotation_context)
                                        else:
                                            # Emergency fallback: create basic context
                                            fallback_rotation_id = generate_rotation_id(project["name"])
                                            fallback_timestamp = format_utc(utcnow())
                                            fallback_context = create_rotation_context(
                                                rotation_id=fallback_rotation_id,
                                                rotation_timestamp=fallback_timestamp,
                                                previous_log_path=str(archive_path),
                                            )
                                            header = await _build_template_content(log_type, project, fallback_context)
                                        await asyncio.to_thread(lambda: log_path.write_text(header))
                                    except Exception:
                                        # If template generation fails, use minimal header
                                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
                                        project_name = project.get("name", "Unknown Project")
                                        header = (
                                            "# Progress Log\n\n"
                                            "## Rotation Notice (Fallback)\n"
                                            f"Previous log was archived to: {archive_path.name}\n\n"
                                            f"Rotation Time: {timestamp}\n"
                                            f"Project: {project_name}\n"
                                            f"Note: Full template generation failed, using minimal header.\n\n"
                                            "---\n\n"
                                        )
                                        await asyncio.to_thread(lambda: log_path.write_text(header))

                                    fallback_result = {
                                        "log_type": log_type,
                                        "status": "rotated_fallback",
                                        "dry_run": False,
                                        "original_path": str(log_path),
                                        "archive_path": str(archive_path),
                                        "fallback_method": True,
                                        "healed_error": True
                                    }
                                    execution_results.append(fallback_result)
                                    successful_rotations.append(fallback_result)

                                except Exception:
                                    # Fallback failed
                                    error_result = {
                                        "log_type": log_type,
                                        "status": "failed",
                                        "error": str(rotation_error),
                                        "healing_attempted": True,
                                        "healing_failed": True
                                    }
                                    failed_rotations.append(error_result)
                                    execution_results.append(error_result)
                            else:
                                # Rotation failed completely
                                error_result = {
                                    "log_type": log_type,
                                    "status": "failed",
                                    "error": str(rotation_error),
                                    "healing_attempted": True
                                }
                                failed_rotations.append(error_result)
                                execution_results.append(error_result)

                except Exception as execution_error:
                    # Handle execution-level errors
                    healed_execution = _EXCEPTION_HEALER.heal_document_operation_error(
                        execution_error, {"operation": "rotation_execution", "log_type": log_type}
                    )

                    if healed_execution["success"]:
                        # Create minimal success result
                        minimal_result = {
                            "log_type": log_type,
                            "status": "completed_with_fallback",
                            "dry_run": final_dry_run,
                            "healed_execution": True,
                            "original_error": str(execution_error)
                        }
                        execution_results.append(minimal_result)
                        successful_rotations.append(minimal_result)
                    else:
                        # Execution failed
                        error_result = {
                            "log_type": log_type,
                            "status": "failed",
                            "error": str(execution_error),
                            "execution_level_error": True
                        }
                        failed_rotations.append(error_result)
                        execution_results.append(error_result)

            except Exception as operation_error:
                # Handle operation-level errors
                error_result = {
                    "log_type": operation.get("log_type", "unknown"),
                    "status": "failed",
                    "error": str(operation_error),
                    "operation_level_error": True
                }
                failed_rotations.append(error_result)
                execution_results.append(error_result)

        # Prepare final response
        response = {
            "ok": len(successful_rotations) > 0 or len(skipped_rotations) > 0,
            "rotation_executed": not final_dry_run,
            "dry_run": final_dry_run,
            "dry_run_mode": rotation_prep.get("final_dry_run_mode"),
            "processed_log_types": rotation_prep["validated_log_types"],
            "results": execution_results,
            "summary": {
                "total_operations": len(rotation_operations),
                "successful": len(successful_rotations),
                "failed": len(failed_rotations),
                "skipped": len(skipped_rotations)
            }
        }

        # Backwards-compat: historically rotate_log returned a single-file shape with
        # `archived_to` + a few top-level counters. When exactly one rotation
        # produced an archive path, mirror those fields for callers/tests.
        try:
            primary = None
            for item in execution_results:
                if isinstance(item, dict) and (item.get("archive_path") or item.get("archived_to")):
                    primary = item
                    break
            if primary is None:
                for item in execution_results:
                    if isinstance(item, dict):
                        primary = item
                        break
            if primary:
                archived_to = primary.get("archived_to") or primary.get("archive_path")
                if archived_to:
                    response.setdefault("archived_to", archived_to)
                    response.setdefault("archive_path", archived_to)

                response.setdefault("rotation_id", primary.get("rotation_id"))
                response.setdefault("estimated_entry_count", primary.get("estimated_entry_count"))
                response.setdefault(
                    "entry_count",
                    primary.get("entry_count")
                    or primary.get("rotated_entry_count")
                    or primary.get("estimated_entry_count"),
                )
                response.setdefault("rotation_completed", primary.get("rotation_completed"))
                response.setdefault("archive_hash", primary.get("archive_hash") or primary.get("archive_sha256") or primary.get("file_hash"))
                response.setdefault("archive_sha256", primary.get("archive_sha256") or primary.get("archive_hash") or primary.get("file_hash"))
                response.setdefault("integrity_verified", primary.get("integrity_verified"))
                response.setdefault("audit_trail_stored", primary.get("audit_trail_stored"))
                response.setdefault("state_updated", primary.get("state_updated"))
                response.setdefault("rotation_duration_seconds", primary.get("rotation_duration_seconds"))
                response.setdefault("sequence_number", primary.get("sequence_number"))
                response.setdefault(
                    "entry_count_method",
                    primary.get("entry_count_method") or primary.get("estimated_entry_count_method") or "unknown",
                )

                mode = (response.get("dry_run_mode") or "estimate").lower()
                if response.get("dry_run") is True:
                    response.setdefault("entry_count_approximate", mode != "precise")
                    response["entry_count_method"] = "full_count" if mode == "precise" else response.get("entry_count_method")
                    response.setdefault("file_hash", primary.get("file_hash"))
                    response.setdefault("sequence_number", 0)
        except Exception:
            pass

        # Add warnings if any operations failed
        if failed_rotations:
            response["warnings"] = [f"Failed to rotate {r['log_type']}: {r.get('error', 'Unknown error')}" for r in failed_rotations]

        return response

    except Exception as e:
        # Apply ultimate exception healing for rotation execution
        healed_result = _EXCEPTION_HEALER.heal_emergency_exception(
            e, {"operation": "rotation_execution", "project": project.get("name", "unknown")}
        )

        if healed_result and healed_result.get("success") and "healed_values" in healed_result:
            # Create emergency rotation result
            emergency_params = _FALLBACK_MANAGER.apply_emergency_fallback(
                "rotate_log", healed_result["healed_values"]
            )

            return {
                "ok": True,
                "rotation_executed": False,
                "dry_run": True,
                "emergency_fallback": True,
                "processed_log_types": ["progress"],
                "results": [{
                    "log_type": "progress",
                    "status": "emergency_fallback",
                    "error": str(e),
                    "emergency_params": emergency_params
                }],
                "summary": {
                    "total_operations": 1,
                    "successful": 0,
                    "failed": 0,
                    "skipped": 1
                },
                "original_error": str(e)
            }
        else:
            return {
                "ok": False,
                "error": f"Critical rotation error: {str(e)}",
                "suggestion": "Check system configuration and try again",
                "rotation_executed": False,
                "dry_run": True,
                "processed_log_types": [],
                "results": [],
                "summary": {
                    "total_operations": 0,
                    "successful": 0,
                    "failed": 0,
                    "skipped": 0
                }
            }


def _format_readable(response: Dict[str, Any], project_name: str) -> str:
    """
    Format rotation response as clean readable output.

    Args:
        response: Rotation response dict
        project_name: Project name

    Returns:
        Formatted readable string
    """
    lines = []

    # Check if rotation was successful
    if not response.get("ok"):
        lines.append(f"❌ Rotation failed: {project_name}")
        if "error" in response:
            lines.append(f"   Error: {response['error']}")
        return "\n".join(lines)

    # Get rotation details
    results = response.get("results", [])
    dry_run = response.get("dry_run", False)

    if dry_run:
        lines.append(f"📋 Dry run: {project_name}")
    else:
        lines.append(f"✅ Log rotated: {project_name}")

    # Process each result
    for result in results:
        status = result.get("status", "unknown")
        log_type = result.get("log_type", "unknown")

        if status == "rotated":
            # Successful rotation
            original_path = Path(result.get("original_path", ""))
            archive_path = Path(result.get("archive_path", ""))
            original_size = result.get("original_size_bytes", 0)

            # Format size in KB
            size_kb = original_size / 1024 if original_size > 0 else 0

            lines.append(f"   Original: {original_path.name} ({size_kb:.1f} KB)")
            lines.append(f"   Archived: {archive_path.name}")
            lines.append(f"   New log: {original_path.name} (empty)")

        elif status == "dry_run_complete":
            # Dry run result
            entry_count = result.get("entry_count", 0)
            estimated_size = result.get("estimated_size", 0)
            size_kb = estimated_size / 1024 if estimated_size > 0 else 0

            lines.append(f"   Would rotate: {log_type}")
            lines.append(f"   Entries: {entry_count}")
            lines.append(f"   Size: {size_kb:.1f} KB")

        elif status == "skipped":
            # Skipped rotation
            reason = result.get("reason", "Unknown reason")
            lines.append(f"   Skipped: {log_type} - {reason}")

        elif status == "failed":
            # Failed rotation
            error = result.get("error", "Unknown error")
            lines.append(f"   Failed: {log_type} - {error}")

    return "\n".join(lines)


@app.tool()
async def rotate_log(
    agent: str,
    project: Optional[str] = None,
    suffix: Optional[str] = None,
    custom_metadata: Optional[str] = None,
    confirm: Optional[bool] = None,
    dry_run: Optional[bool] = None,
    dry_run_mode: Optional[str] = None,
    log_type: Optional[str] = None,
    log_types: Optional[List[str]] = None,
    rotate_all: Optional[bool] = None,
    auto_threshold: Optional[bool] = None,
    threshold_entries: Optional[int] = None,
    config: Optional[RotateLogConfig] = None,  # Configuration object for enhanced parameter handling
    format: str = "structured",  # Output format - "readable", "structured", "compact"
    **_kwargs: Any,  # tolerate unknown kwargs (contract: tools never TypeError)
) -> Dict[str, Any]:
    """
    Rotate one or more project log files with integrity guarantees.

    Args:
        project: Optional project name override (defaults to active project context).
        suffix: Optional suffix for archive filenames.
        custom_metadata: Optional JSON metadata appended to rotation record.
        confirm: When True, perform actual rotation (required unless auto-threshold triggers).
        dry_run: If True, preview rotation without changing files. Defaults to safe preview when confirm=False.
        dry_run_mode: Controls dry-run accuracy. \"estimate\" (default) returns approximate counts; \"precise\" forces a full line count.
        log_type: Single log type to rotate (e.g., "progress", "doc_updates").
        log_types: List of log types to rotate.
        rotate_all: When True, rotate every configured log type for the project.
        auto_threshold: When True, only rotate logs whose entry count exceeds a threshold.
        threshold_entries: Optional override for entry threshold (defaults to definition or 500).
        config: Optional RotateLogConfig object for enhanced parameter handling.
        format: Output format - "readable" (human-friendly), "structured" (full JSON), "compact" (minimal)

    ENHANCED FEATURES:
    - Dual parameter support: Use either legacy parameters OR RotateLogConfig object
    - Configuration Mode: Use RotateLogConfig for structured parameter management
    - Legacy Mode: Pass individual parameters as before (fully backward compatible)
    - Legacy parameters take precedence over config object when both provided

    Configuration Mode: Use RotateLogConfig for structured parameter management
    Legacy Mode: Pass individual parameters as before (maintains backward compatibility)
    """
    # Phase 3 Task 3.5: Enhanced Function Decomposition
    # This function now uses decomposed sub-functions with bulletproof error handling

    try:
        state_snapshot = await server_module.state_manager.record_tool("rotate_log")
    except Exception:
        state_snapshot = {}

    try:
        # === PHASE 3 ENHANCED PARAMETER VALIDATION AND PREPARATION ===
        # Replace monolithic parameter handling with bulletproof validation and healing
        final_config, validation_info = _validate_rotation_parameters(
            suffix=suffix,
            custom_metadata=custom_metadata,
            confirm=confirm,
            dry_run=dry_run,
            dry_run_mode=dry_run_mode,
            log_type=log_type,
            log_types=log_types,
            rotate_all=rotate_all,
            auto_threshold=auto_threshold,
            threshold_entries=threshold_entries,
            config=config
        )

        # === NORMALIZE PROJECT INPUT ===
        # Apply normalization to accept hyphenated, underscored, or mixed-case project names
        normalized_project = normalize_project_input(project)

        # === CONTEXT RESOLUTION WITH ENHANCED ERROR HANDLING ===
        try:
            context = await _ROTATE_HELPER.prepare_context(
                tool_name="rotate_log",
                agent_id=None,
                explicit_project=normalized_project,
                require_project=True,
                state_snapshot=state_snapshot,
            )
        except ProjectResolutionError as exc:
            # Apply Phase 2 ExceptionHealer for project resolution errors
            healed_context = _EXCEPTION_HEALER.heal_parameter_validation_error(
                exc, {"tool_name": "rotate_log", "operation": "project_resolution"}
            )

            if healed_context["success"]:
                # Try with healed context
                try:
                    context = await _ROTATE_HELPER.prepare_context(
                        tool_name="rotate_log",
                        agent_id=None,
                        require_project=True,
                        state_snapshot=state_snapshot,
                    )
                except Exception:
                    # Fallback response
                    payload = _ROTATE_HELPER.translate_project_error(exc)
                    payload = apply_response_defaults(payload, {
                        "suggestion": "Invoke set_project before rotating logs"
                    })
                    return payload
            else:
                payload = _ROTATE_HELPER.translate_project_error(exc)
                payload = apply_response_defaults(payload, {
                    "suggestion": "Invoke set_project before rotating logs"
                })
                return payload

        project = context.project or {}

        # === ENHANCED ROTATION OPERATION PREPARATION ===
        rotation_prep = _prepare_rotation_operation(final_config, context, project)

        if not rotation_prep.get("preparation_complete", False):
            # If preparation failed, try to continue with emergency rotation
            if rotation_prep.get("emergency_fallback"):
                # Execute emergency rotation
                rotation_result = _execute_rotation_with_fallbacks(
                    rotation_prep, final_config, context, project
                )
                rotation_result["parameter_healing"] = True
                rotation_result["emergency_fallback"] = True
                rotation_result["preparation_failed"] = True
                return rotation_result
            else:
                # Return error if preparation completely failed
                return {
                    "ok": False,
                    "error": "Failed to prepare rotation operation",
                    "details": rotation_prep.get("error", "Unknown preparation error"),
                    "suggestion": "Try with simpler rotation parameters"
                }

        # === ENHANCED ROTATION EXECUTION WITH FALLBACKS ===
        rotation_result = await _execute_rotation_with_fallbacks(
            rotation_prep, final_config, context, project
        )

        # Add validation info to result if healing was applied
        if validation_info.get("healing_applied"):
            rotation_result["parameter_healing"] = True

            if validation_info.get("exception_healing"):
                rotation_result["parameter_exception_healing"] = True
            elif validation_info.get("emergency_fallback"):
                rotation_result["parameter_emergency_fallback"] = True
            else:
                rotation_result["parameter_healing_applied"] = True

        # Add preparation warnings if any
        if rotation_prep.get("emergency_fallback"):
            if "warnings" not in rotation_result:
                rotation_result["warnings"] = []
            rotation_result["warnings"].append("Emergency fallback applied during preparation")

        # Handle readable format
        if format == "readable":
            from scribe_mcp.utils.response import default_formatter

            project_name = context.project.get("name") if context.project else "unknown"
            readable_content = _format_readable(rotation_result, project_name)

            payload = {
                "ok": rotation_result.get("ok", False),
                "rotation_executed": rotation_result.get("rotation_executed", False),
                "readable_content": readable_content,
                **rotation_result  # Include all original data
            }

            return await default_formatter.finalize_tool_response(
                payload,
                format="readable",
                tool_name="rotate_log"
            )

        return rotation_result

    except Exception as e:
        # === ULTIMATE EXCEPTION HANDLING AND FALLBACK ===
        # Apply Phase 2 ExceptionHealer for unexpected errors
        healed_result = _EXCEPTION_HEALER.heal_emergency_exception(
            e, {
                "operation": "rotate_log_main",
                "project": project,
                "tool": "rotate_log"
            }
        )

        if healed_result and healed_result.get("success") and "healed_values" in healed_result:
            # Create emergency rotation with healed parameters
            emergency_params = _FALLBACK_MANAGER.apply_emergency_fallback(
                "rotate_log", healed_result["healed_values"]
            )

            return {
                "ok": True,
                "rotation_executed": False,
                "dry_run": True,
                "emergency_fallback": True,
                "processed_log_types": ["progress"],
                "results": [{
                    "log_type": "progress",
                    "status": "emergency_fallback",
                    "error": str(e),
                    "emergency_params": emergency_params
                }],
                "summary": {
                    "total_operations": 1,
                    "successful": 0,
                    "failed": 0,
                    "skipped": 1
                },
                "original_error": str(e)
            }
        else:
            return {
                "ok": False,
                "error": f"Critical error in rotate_log: {str(e)}",
                "emergency_healing_failed": True,
                "suggestion": "Check system configuration and try again",
                "rotation_executed": False,
                "dry_run": True,
                "processed_log_types": [],
                "results": []
            }
    return sanitized[:64] or "log"


def _build_archive_suffix(suffix: Optional[str], log_type: str, rotation_id: str) -> str:
    safe_rotation_id = rotation_id.replace("-", "")[:8]
    base = _sanitize_suffix(suffix) if suffix else f"{log_type}_archive"
    return f"{base}_{safe_rotation_id}"


async def _build_template_content(
    log_type: str,
    project: Dict[str, Any],
    rotation_context: Dict[str, Any],
) -> str:
    if log_type != "progress":
        timestamp = rotation_context.get("rotation_timestamp_utc", "Unknown time")
        rotation_id = rotation_context.get("rotation_id", "unknown")
        project_name = project.get("name", "Unknown Project")
        return (
            f"# {log_type.replace('_', ' ').title()} Log\n\n"
            f"Log rotated on {timestamp} (rotation id {rotation_id}) for project {project_name}.\n\n"
        )

    template_context = substitution_context(
        project_name=project["name"],
        author=project.get("defaults", {}).get("agent", "Scribe"),
        rotation_context=rotation_context,
    )

    template_engine = None
    try:
        project_root = Path(project.get("root", "")) if project.get("root") else Path.cwd()
        template_engine = Jinja2TemplateEngine(
            project_root=project_root,
            project_name=project["name"],
            security_mode="sandbox",
        )
    except Exception as engine_error:  # pragma: no cover - defensive path
        logger.warning("Failed to initialize Jinja2 template engine for rotation: %s", engine_error)

    template_name = f"documents/{TEMPLATE_FILENAMES['progress_log']}"
    if template_engine:
        try:
            rendered = template_engine.render_template(template_name, metadata=template_context)
            if rendered:
                return rendered
        except TemplateEngineError as render_error:
            logger.warning("Jinja2 rendering failed for %s: %s", template_name, render_error)

    from scribe_mcp.tools.generate_doc_templates import _render_template

    templates = await load_templates()
    template_body = templates.get("progress_log", "")
    try:
        rendered = _render_template(template_body, template_context)
        if rendered:
            return rendered
    except Exception as template_error:  # pragma: no cover - defensive
        logger.warning("Template generation failed: %s", template_error)

    rotation_id = rotation_context.get("rotation_id", "unknown")
    timestamp = rotation_context.get("rotation_timestamp_utc", "Unknown")
    project_name = project.get("name", "Unknown Project")
    author = project.get("defaults", {}).get("agent", "Scribe")

    return (
        "# Progress Log\n\n"
        "## Rotation Notice\n"
        f"Previous log was archived with rotation ID: {rotation_id}\n\n"
        f"Created: {timestamp}\n"
        f"Project: {project_name}\n"
        f"Author: {author}\n\n"
        "---\n\n"
    )


async def _rotate_single_log(
    *,
    project: Dict[str, Any],
    context: LoggingContext,
    state_manager,
    audit_manager,
    log_type: str,
    log_path: Path,
    definition: Dict[str, Any],
    suffix: Optional[str],
    parsed_metadata: Optional[Dict[str, Any]],
    confirm: Optional[bool],
    dry_run: Optional[bool],
    dry_run_mode: Optional[str],
    auto_threshold: bool,
    threshold_entries: Optional[int],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"log_type": log_type}

    if not log_path.exists():
        result.update({
            "ok": False,
            "error": f"Log file not found: {log_path}",
            "suggestion": "Create initial log entries before rotating",
        })
        return result

    normalized_mode = (dry_run_mode or "estimate").lower()
    if normalized_mode not in {"estimate", "precise"}:
        result.update({
            "ok": False,
            "error": f"Invalid dry_run_mode '{dry_run_mode}'. Use 'estimate' or 'precise'.",
            "suggestion": "Set dry_run_mode to 'estimate' (default) or 'precise' for exact counts.",
        })
        return result

    try:
        snapshot = _snapshot_file_state(log_path)
    except OSError as snapshot_error:
        result.update({
            "ok": False,
            "error": f"Unable to inspect log file: {snapshot_error}",
            "suggestion": "Verify file permissions and that the log path is readable.",
        })
        return result

    cached_stats = state_manager.get_log_stats(project["name"], log_type)
    cached_ema = cached_stats.get("ema_bytes_per_line") if cached_stats else None
    cached_initialized = cached_stats.get("initialized") if cached_stats else False
    entry_estimate = _estimate_entry_count(snapshot, cached_stats)

    threshold_limit = _rotation_threshold_for_definition(definition, threshold_entries)
    if auto_threshold and threshold_limit is None:
        threshold_limit = DEFAULT_AUTO_THRESHOLD_ENTRIES

    estimation_band = _compute_estimation_band(threshold_limit)
    estimation_decision: Optional[str] = None

    if auto_threshold and threshold_limit:
        estimation_decision = _classify_estimate(entry_estimate.count, threshold_limit, estimation_band)
        if estimation_decision == "undecided":
            refined_estimate = _refine_entry_estimate(log_path, snapshot, entry_estimate)
            if refined_estimate:
                entry_estimate = refined_estimate
                if not refined_estimate.approximate:
                    observed_bpl = _compute_bytes_per_line(snapshot["size_bytes"], refined_estimate.count)
                    state_manager.update_log_stats(
                        project["name"],
                        log_type,
                        size_bytes=snapshot["size_bytes"],
                        line_count=refined_estimate.count,
                        ema_bytes_per_line=observed_bpl,
                        mtime_ns=snapshot.get("mtime_ns"),
                        inode=snapshot.get("inode"),
                        source="tail_sample",
                        initialized=True,
                    )
                estimation_decision = _classify_estimate(entry_estimate.count, threshold_limit, estimation_band)

        if estimation_decision == "undecided" and normalized_mode == "precise":
            precise_count = count_file_lines(str(log_path))
            observed_bpl = _compute_bytes_per_line(snapshot["size_bytes"], precise_count)
            state_manager.update_log_stats(
                project["name"],
                log_type,
                size_bytes=snapshot["size_bytes"],
                line_count=precise_count,
                ema_bytes_per_line=observed_bpl,
                mtime_ns=snapshot.get("mtime_ns"),
                inode=snapshot.get("inode"),
                source="precise_dry_run",
                initialized=True,
            )
            entry_estimate = EntryCountEstimate(
                count=precise_count,
                approximate=False,
                method="full_count",
                details={**snapshot, "bytes_per_line": observed_bpl},
            )
            estimation_decision = _classify_estimate(entry_estimate.count, threshold_limit, estimation_band)

    if auto_threshold and threshold_limit and estimation_decision == "below":
        result.update({
            "ok": True,
            "rotation_skipped": True,
            "reason": "threshold_not_reached",
            "entry_count": entry_estimate.count,
            "entry_count_approximate": entry_estimate.approximate,
            "entry_count_method": entry_estimate.method,
            "threshold_entries": threshold_limit,
            "estimation_band": estimation_band,
            "estimation_details": dict(entry_estimate.details),
            "current_log_path": str(log_path),
            "auto_threshold_triggered": False,
            "estimation_decision": "below",
        })
        return result

    auto_triggered = bool(auto_threshold and threshold_limit and estimation_decision == "above")
    confirm_requested = bool(confirm)
    should_rotate = confirm_requested or auto_triggered
    dry_run_flag = dry_run if dry_run is not None else not should_rotate

    if dry_run_flag and normalized_mode == "precise" and entry_estimate.approximate:
        precise_count = count_file_lines(str(log_path))
        observed_bpl = _compute_bytes_per_line(snapshot["size_bytes"], precise_count)
        state_manager.update_log_stats(
            project["name"],
            log_type,
            size_bytes=snapshot["size_bytes"],
            line_count=precise_count,
            ema_bytes_per_line=observed_bpl,
            mtime_ns=snapshot.get("mtime_ns"),
            inode=snapshot.get("inode"),
            source="precise_dry_run",
            initialized=True,
        )
        entry_estimate = EntryCountEstimate(
            count=precise_count,
            approximate=False,
            method="full_count",
            details={**snapshot, "bytes_per_line": observed_bpl},
        )

    sequence_number = get_next_sequence_number(project["name"])
    hash_chain_info = state_manager.get_hash_chain_info(project["name"])
    previous_hash = hash_chain_info.get("last_hash")
    rotation_id = generate_rotation_id(project["name"])
    rotation_timestamp = format_utc()

    if dry_run_flag:
        archive_suffix = _build_archive_suffix(suffix, log_type, rotation_id)
        potential_archive = await rotate_file(
            log_path,
            archive_suffix,
            confirm=should_rotate,
            dry_run=True,
            repo_root=Path(project.get("root") or settings.project_root).resolve(),
        )
        current_size_mb = round(snapshot["size_bytes"] / (1024 * 1024), 3) if snapshot["size_bytes"] else 0.0
        estimation_decision_label = estimation_decision or ("rotate" if should_rotate else "manual")
        result.update({
            "ok": True,
            "dry_run": True,
            "rotation_id": rotation_id,
            "rotation_timestamp_utc": rotation_timestamp,
            "rotation_timestamp": rotation_timestamp,
            "project": project["name"],
            "log_type": log_type,
            "current_file_path": str(log_path),
            "current_log_path": str(log_path),
            "current_file_size_bytes": snapshot["size_bytes"],
            "current_file_size_mb": current_size_mb,
            "current_file_line_count": entry_estimate.count,
            "current_file_sha256": cached_stats.get("sha256") if cached_stats else None,
            "current_file_hash": cached_stats.get("sha256") if cached_stats else None,
            "file_hash": cached_stats.get("sha256") if cached_stats else None,
            "entry_count": entry_estimate.count,
            "entry_count_approximate": entry_estimate.approximate,
            "entry_count_method": entry_estimate.method,
            "estimation_band": estimation_band,
            "estimation_details": dict(entry_estimate.details),
            "estimation_decision": estimation_decision_label,
            "sequence_number": sequence_number,
            "hash_chain_previous": previous_hash,
            "hash_chain_root": hash_chain_info.get("root_hash"),
            "hash_chain_sequence": sequence_number,
            "archived_to": str(potential_archive),
            "requires_confirmation": not should_rotate,
            "auto_threshold_triggered": auto_triggered,
        })
        if threshold_limit:
            result["threshold_entries"] = threshold_limit

        return result

    if not should_rotate:
        result.update({
            "ok": False,
            "error": "Rotation requires explicit confirmation. Add confirm=true to proceed.",
            "suggestion": "Use confirm=true to perform rotation, or dry_run=true to preview changes",
        })
        return result

    rotation_start_time = datetime.utcnow()

    archive_suffix = _build_archive_suffix(suffix, log_type, rotation_id)

    archive_path = await rotate_file(
        log_path,
        archive_suffix,
        confirm=True,
        dry_run=False,
        template_content=None,
        repo_root=Path(project.get("root") or settings.project_root).resolve(),
    )

    archive_info = verify_file_integrity(
        archive_path,
        repo_root=Path(project.get("root") or settings.project_root).resolve(),
    )
    archive_hash = archive_info.get("sha256")
    archive_size = archive_info.get("size_bytes")
    rotated_entries = archive_info.get("line_count")
    entry_count_method = "archive_scan"
    entry_count_approximate = False
    if rotated_entries is None:
        rotated_entries = entry_estimate.count
        entry_count_method = entry_estimate.method
        entry_count_approximate = entry_estimate.approximate

    rotation_context = create_rotation_context(
        rotation_id=rotation_id,
        rotation_timestamp=rotation_timestamp,
        previous_log_path=str(archive_path),
        previous_log_hash=archive_hash or "",
        previous_log_entries=str(rotated_entries),
        current_sequence=str(sequence_number),
        total_rotations=str(sequence_number),
        hash_chain_previous=previous_hash or "",
        hash_chain_sequence=str(sequence_number),
        hash_chain_root=hash_chain_info.get("root_hash") or "",
    )

    rendered_template = await _build_template_content(log_type, project, rotation_context)

    try:  # Best-effort WAL entry
        from scribe_mcp.utils.files import WriteAheadLog

        wal = WriteAheadLog(archive_path)
        rotation_journal_entry = {
            "op": "rotate",
            "from": str(log_path),
            "to": str(archive_path),
            "rotation_id": rotation_id,
            "timestamp": rotation_timestamp,
            "sequence": str(sequence_number),
            "entries_rotated": str(rotated_entries),
            "log_type": log_type,
        }
        wal.write_entry(rotation_journal_entry)
    except Exception as wal_error:  # pragma: no cover - defensive
        logger.warning("Failed to write rotation journal entry: %s", wal_error)

    rotation_metadata = create_rotation_metadata(
        archived_file_path=str(archive_path),
        rotation_uuid=rotation_id,
        rotation_timestamp=rotation_timestamp,
        sequence_number=sequence_number,
        previous_hash=previous_hash,
        log_type=log_type,
    )
    if rotated_entries is not None:
        rotation_metadata["entry_count"] = rotated_entries

    if parsed_metadata:
        rotation_metadata.update(parsed_metadata)

    audit_success = store_rotation_metadata(project["name"], rotation_metadata)
    state_success = update_project_state(project["name"], rotation_metadata)

    rotation_duration = max(
        0.0, (datetime.utcnow() - rotation_start_time).total_seconds()
    )

    if rendered_template:
        await _write_rotated_log_header(log_path, rendered_template)

    observed_bpl = None if entry_count_approximate else _compute_bytes_per_line(archive_size, rotated_entries)
    try:
        new_snapshot = _snapshot_file_state(log_path)
    except OSError:
        new_snapshot = {"size_bytes": 0, "mtime_ns": None, "inode": None}

    new_log_line_count = rendered_template.count("\n") if rendered_template else 0
    ema_value = cached_ema
    ema_source = "post_rotation"
    initialized_flag = cached_initialized
    if not entry_count_approximate:
        observed_bpl = _compute_bytes_per_line(archive_size, rotated_entries)
        if observed_bpl:
            ema_value = _blend_ema(cached_ema, observed_bpl, EMA_SMOOTHING_ALPHA)
            ema_source = "post_rotation_precise"
            initialized_flag = True
    else:
        approx_bpl = _compute_bytes_per_line(archive_size, entry_estimate.count)
        if approx_bpl:
            ema_value = _blend_ema(cached_ema, approx_bpl, EMA_SMOOTHING_ALPHA / 2)
            ema_source = "post_rotation_estimate"

    state_manager.update_log_stats(
        project["name"],
        log_type,
        size_bytes=new_snapshot.get("size_bytes"),
        line_count=new_log_line_count,
        ema_bytes_per_line=ema_value,
        mtime_ns=new_snapshot.get("mtime_ns"),
        inode=new_snapshot.get("inode"),
        source=ema_source,
        initialized=initialized_flag,
    )

    result.update({
        "ok": True,
        "rotation_completed": True,
        "rotation_id": rotation_id,
        "rotation_timestamp_utc": rotation_timestamp,
        "rotation_timestamp": rotation_timestamp,
        "project": project["name"],
        "log_type": log_type,
        "sequence_number": sequence_number,
        "current_log_path": str(log_path),
        "archive_path": str(archive_path),
        "archived_to": str(archive_path),
        "archive_sha256": archive_hash,
        "archive_hash": archive_hash,
        "archive_size_bytes": archive_size,
        "archive_size_mb": archive_info.get("size_mb"),
        "rotated_entry_count": rotated_entries,
        "entry_count": rotated_entries,
        "entry_count_approximate": entry_count_approximate,
        "entry_count_method": entry_count_method,
        "estimated_entry_count": entry_estimate.count,
        "estimated_entry_count_method": entry_estimate.method,
        "estimated_entry_count_approximate": entry_estimate.approximate,
        "estimation_band": estimation_band,
        "estimation_details": dict(entry_estimate.details),
        "estimation_decision": estimation_decision or "rotate",
        "rotation_duration_seconds": rotation_duration,
        "hash_chain_previous": previous_hash,
        "hash_chain_root": hash_chain_info.get("root_hash"),
        "hash_chain_sequence": sequence_number,
        "audit_trail_stored": audit_success,
        "state_updated": state_success,
        "auto_threshold_triggered": auto_triggered,
        "template_generated": bool(rendered_template),
        "integrity_verified": archive_hash is not None,
    })
    if threshold_limit:
        result["threshold_entries"] = threshold_limit

    if parsed_metadata:
        result["custom_metadata_applied"] = True
        result["custom_metadata"] = parsed_metadata

    return result


def _merge_single_rotation_response(summary: Dict[str, Any], rotation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Merge rotation result into summary using ConfigManager utilities."""
    merged = build_response_payload(summary, **rotation_result)
    merged.setdefault("rotations", summary.get("rotations", [rotation_result]))
    return merged


def _snapshot_file_state(path: Path) -> Dict[str, Any]:
    stat_result = path.stat()
    inode = getattr(stat_result, "st_ino", None)
    if not inode:
        inode = None

    return {
        "size_bytes": stat_result.st_size,
        "mtime_ns": getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000)),
        "inode": inode,
    }


def _estimate_entry_count(snapshot: Dict[str, Any], cached_stats: Optional[Dict[str, Any]]) -> EntryCountEstimate:
    """Estimate entry count using FileSizeEstimator."""
    size_bytes = snapshot.get("size_bytes", 0) or 0
    mtime_ns = snapshot.get("mtime_ns")

    # Add cached_initialized to details if available
    if cached_stats and cached_stats.get("initialized"):
        # We'll modify the details after estimation
        pass

    estimate = _FILE_SIZE_ESTIMATOR.estimate_entry_count_with_cache(
        size_bytes, cached_stats, mtime_ns
    )

    # Add cached_initialized flag if it was in the original cached stats
    if cached_stats and cached_stats.get("initialized") and "cached_initialized" not in estimate.details:
        estimate.details["cached_initialized"] = cached_stats.get("initialized")

    return estimate


def _refine_entry_estimate(log_path: Path, snapshot: Dict[str, Any], estimate: EntryCountEstimate) -> Optional[EntryCountEstimate]:
    """Refine entry count estimate using FileSizeEstimator."""
    size_bytes = snapshot.get("size_bytes", 0)
    return _FILE_SIZE_ESTIMATOR.refine_estimate_with_sampling(log_path, size_bytes, estimate)


def _compute_estimation_band(threshold: Optional[int]) -> Optional[int]:
    """Compute estimation band using ThresholdEstimator."""
    return _THRESHOLD_ESTIMATOR.compute_estimation_band(threshold)


def _classify_estimate(value: int, threshold: int, band: Optional[int]) -> str:
    """Classify estimate using ThresholdEstimator with compatible return values."""
    classification = _THRESHOLD_ESTIMATOR.classify_estimate(value, threshold, band)

    # Map to original return values for backward compatibility
    mapping = {
        "well_below_threshold": "below",
        "well_above_threshold": "above",
        "near_threshold": "undecided",
        "below_threshold": "below",
        "above_threshold": "above"
    }

    return mapping.get(classification, "undecided")


def _compute_bytes_per_line(size_bytes: Optional[int], line_count: Optional[int]) -> Optional[float]:
    """Compute bytes per line using FileSizeEstimator."""
    return _FILE_SIZE_ESTIMATOR.compute_bytes_per_line(size_bytes, line_count)


def _clamp_bytes_per_line(value: float) -> float:
    """Clamp bytes-per-line value within reasonable bounds."""
    from scribe_mcp.utils.estimator import FileSizeEstimator
    estimator = FileSizeEstimator()
    return estimator.clamp_bytes_per_line(value)


def _blend_ema(current: Optional[float], observed: Optional[float], smoothing: float) -> Optional[float]:
    if observed is None:
        return current
    observed = _clamp_bytes_per_line(observed)
    smoothing = max(0.0, min(1.0, smoothing))
    if current is None:
        return observed
    current = _clamp_bytes_per_line(current)
    blended = (1.0 - smoothing) * current + smoothing * observed
    return _clamp_bytes_per_line(blended)
