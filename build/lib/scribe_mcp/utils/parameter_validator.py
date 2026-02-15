"""
Centralized parameter validation utilities for MCP tools.

This module extracts common validation patterns from monolithic MCP tools
to provide reusable, consistent validation across all tools.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union, Sequence


class ToolValidator:
    """
    Centralized validation utilities for MCP tool parameters.

    Extracts common validation patterns from append_entry.py, query_entries.py,
    and rotate_log.py to eliminate code duplication and ensure consistency.
    """

    @staticmethod
    def validate_message(message: str) -> Optional[str]:
        """
        Validate message content for MCP protocol compatibility.

        Extracted from append_entry.py _validate_message function.

        Args:
            message: Message content to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        if any(ch in message for ch in ("\n", "\r")):
            return "Message cannot contain newline characters."
        if "|" in message:
            return "Message cannot contain pipe characters."  # avoids delimiter collisions
        return None

    @staticmethod
    def validate_enum_value(
        value: str,
        allowed_values: set[str],
        field_name: str = "value"
    ) -> Optional[str]:
        """
        Validate that a value is in the allowed set.

        Extracted from query_entries.py validation patterns.

        Args:
            value: Value to validate
            allowed_values: Set of allowed values
            field_name: Name of the field being validated

        Returns:
            Error message if validation fails, None otherwise
        """
        normalized_value = value.lower() if value else ""
        if normalized_value not in allowed_values:
            return (
                f"Invalid {field_name} '{value}'. Must be one of: "
                f"{', '.join(sorted(allowed_values))}"
            )
        return None

    @staticmethod
    def validate_regex_pattern(pattern: str) -> Optional[str]:
        """
        Validate that a regex pattern is compilable.

        Extracted from query_entries.py regex validation.

        Args:
            pattern: Regex pattern to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"Invalid regex: {exc}"
        return None

    @staticmethod
    def validate_range(
        value: Union[int, float],
        min_val: Optional[Union[int, float]] = None,
        max_val: Optional[Union[int, float]] = None,
        field_name: str = "value"
    ) -> Optional[str]:
        """
        Validate that a numeric value is within the specified range.

        Extracted from query_entries.py relevance_threshold validation.

        Args:
            value: Numeric value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            field_name: Name of the field being validated

        Returns:
            Error message if validation fails, None otherwise
        """
        # Convert string to float if needed
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                return f"{field_name} must be a number, got '{value}'"

        if min_val is not None and value < min_val:
            return f"{field_name} must be at least {min_val}, got {value}"

        if max_val is not None and value > max_val:
            return f"{field_name} must be at most {max_val}, got {value}"

        return None

    @staticmethod
    def validate_timestamp(timestamp_utc: Optional[str]) -> Tuple[Optional[datetime], str, Optional[str]]:
        """
        Validate and parse timestamp string.

        Extracted from append_entry.py _resolve_timestamp function.

        Args:
            timestamp_utc: UTC timestamp string in format "YYYY-MM-DD HH:MM:SS UTC"

        Returns:
            Tuple of (parsed_datetime, normalized_timestamp, warning_message)
        """
        if not timestamp_utc:
            from scribe_mcp.utils.time import format_utc
            current = format_utc()
            return None, current, None

        parsed = ToolValidator._parse_timestamp(timestamp_utc)
        if parsed is None:
            from scribe_mcp.utils.time import format_utc
            fallback = format_utc()
            warning = "timestamp format invalid; using current time"
            return None, fallback, warning

        return parsed, timestamp_utc, None

    @staticmethod
    def _parse_timestamp(value: str) -> Optional[datetime]:
        """
        Parse timestamp string to datetime object.

        Extracted from append_entry.py _parse_timestamp function.

        Args:
            value: Timestamp string to parse

        Returns:
            Datetime object or None if parsing fails
        """
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def sanitize_identifier(value: str) -> str:
        """
        Sanitize identifier strings for safe usage.

        Extracted from append_entry.py _sanitize_identifier function.

        Args:
            value: Identifier string to sanitize

        Returns:
            Sanitized identifier string
        """
        sanitized = value.replace("[", "").replace("]", "").replace("|", "").strip()
        return sanitized or "Scribe"

    @staticmethod
    def validate_json_metadata(
        metadata_str: Optional[str],
        field_name: str = "metadata"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate and parse JSON metadata string.

        Extracted from rotate_log.py _parse_custom_metadata function.

        Args:
            metadata_str: JSON string to parse
            field_name: Name of the field being validated

        Returns:
            Tuple of (parsed_dict, error_message)
        """
        if not metadata_str:
            return None, None

        # Try using parameter_normalizer first (preferred method)
        try:
            from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param
            normalized = normalize_dict_param(metadata_str, field_name)
            if isinstance(normalized, dict):
                return normalized, None
        except (ValueError, ImportError):
            pass

        # Fallback to direct JSON parsing
        try:
            parsed = json.loads(metadata_str)
            if isinstance(parsed, dict):
                return parsed, None
        except json.JSONDecodeError:
            pass

        return None, f"Invalid JSON in {field_name} parameter"

    @staticmethod
    def validate_list_parameter(
        value: Optional[Union[Sequence[str], str]],
        delimiter: str = ","
    ) -> List[str]:
        """
        Normalize and validate list parameters.

        Extracted from rotate_log.py _normalize_log_type_param function.

        Args:
            value: Parameter value to normalize (string or sequence)
            delimiter: Delimiter for splitting strings

        Returns:
            Normalized list of strings
        """
        if value is None:
            return []

        if isinstance(value, str):
            candidates = value.split(delimiter)
        else:
            candidates = value

        result: List[str] = []
        for candidate in candidates:
            text = str(candidate).strip().lower()
            if text:
                result.append(text)

        return result

    @staticmethod
    def validate_document_types(
        document_types: Optional[List[str]],
        allowed_types: set[str]
    ) -> Tuple[Optional[List[str]], Optional[str]]:
        """
        Validate document types against allowed set.

        Extracted from query_entries.py document_types validation.

        Args:
            document_types: List of document types to validate
            allowed_types: Set of allowed document types

        Returns:
            Tuple of (normalized_list, error_message)
        """
        if not document_types:
            return None, None

        normalized_types = ToolValidator.validate_list_parameter(document_types)
        invalid_types = [dt for dt in normalized_types if dt not in allowed_types]

        if invalid_types:
            error_msg = (
                f"Invalid document_types: {', '.join(invalid_types)}. "
                f"Must be one of: {', '.join(sorted(allowed_types))}"
            )
            return None, error_msg

        return normalized_types, None

    @staticmethod
    def validate_parameters_against_schema(
        parameters: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate parameters against a schema definition.

        New utility for comprehensive parameter validation.

        Args:
            parameters: Parameters to validate
            schema: Schema definition with validation rules

        Returns:
            Error message if validation fails, None otherwise
        """
        for field_name, field_schema in schema.items():
            field_value = parameters.get(field_name)

            # Check required fields
            if field_schema.get("required", False) and field_value is None:
                return f"Required parameter '{field_name}' is missing"

            # Skip validation if field is not provided and not required
            if field_value is None:
                continue

            # Type validation
            expected_type = field_schema.get("type")
            if expected_type and not isinstance(field_value, expected_type):
                type_name = expected_type.__name__
                return f"Parameter '{field_name}' must be of type {type_name}, got {type(field_value).__name__}"

            # Enum validation
            allowed_values = field_schema.get("allowed_values")
            if allowed_values:
                error = ToolValidator.validate_enum_value(str(field_value), allowed_values, field_name)
                if error:
                    return error

            # Range validation
            min_val = field_schema.get("min_value")
            max_val = field_schema.get("max_value")
            if min_val is not None or max_val is not None:
                error = ToolValidator.validate_range(field_value, min_val, max_val, field_name)
                if error:
                    return error

            # Regex validation
            regex_pattern = field_schema.get("regex_pattern")
            if regex_pattern and isinstance(field_value, str):
                error = ToolValidator.validate_regex_pattern(regex_pattern)
                if error:
                    return error
                # Test if value matches pattern
                if not re.match(regex_pattern, field_value):
                    return f"Parameter '{field_name}' does not match required pattern"

        return None

    @staticmethod
    def validate_metadata_requirements(
        log_definition: Dict[str, Any],
        meta_payload: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate metadata against log definition requirements.

        Extracted from shared.logging_utils.ensure_metadata_requirements.

        Args:
            log_definition: Log configuration definition
            meta_payload: Metadata payload to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            from scribe_mcp.shared.logging_utils import ensure_metadata_requirements
            return ensure_metadata_requirements(log_definition, meta_payload)
        except ImportError:
            # Fallback validation if shared utility not available
            required_metadata = log_definition.get("required_metadata", {})
            for key, requirement in required_metadata.items():
                if key not in meta_payload:
                    return f"Required metadata field '{key}' is missing"

            return None


class BulletproofParameterCorrector:
    """
    Bulletproof parameter correction system that NEVER fails.

    Provides intelligent auto-correction and fallback mechanisms for
    all parameter validation scenarios. When validation fails, this
    system automatically corrects the issue rather than raising errors.
    """

    @staticmethod
    def correct_message_parameter(message: Any) -> str:
        """
        Correct and sanitize message parameter to always return a valid string.

        Args:
            message: Any input value for message parameter

        Returns:
            Always returns a valid, sanitized message string
        """
        if message is None:
            return "No message provided"

        # Convert to string
        if not isinstance(message, str):
            try:
                message = str(message)
            except Exception:
                return "Invalid message format"

        # Remove problematic characters
        corrected = message.replace("\n", " ").replace("\r", " ").replace("|", ";")

        # Ensure non-empty
        if not corrected.strip():
            return "Empty message"

        # Truncate if too long
        if len(corrected) > 1000:
            corrected = corrected[:997] + "..."

        return corrected.strip()

    @staticmethod
    def correct_enum_parameter(
        value: Any,
        allowed_values: set[str],
        field_name: str = "value",
        fallback_value: Optional[str] = None
    ) -> str:
        """
        Correct enum parameter to always return a valid value from allowed set.

        Args:
            value: Any input value
            allowed_values: Set of allowed values
            field_name: Name of the field (for logging)
            fallback_value: Preferred fallback value if correction needed

        Returns:
            Always returns a valid value from allowed_values
        """
        if value is None:
            return fallback_value if fallback_value in allowed_values else next(iter(allowed_values))

        # Convert to string and normalize
        try:
            str_value = str(value).lower().strip()
        except Exception:
            return fallback_value if fallback_value in allowed_values else next(iter(allowed_values))

        # Check if value is already valid
        if str_value in allowed_values:
            return str_value

        # Try fuzzy matching
        for allowed in allowed_values:
            if str_value in allowed or allowed in str_value:
                return allowed

        # Try to find closest match
        import difflib
        matches = difflib.get_close_matches(str_value, allowed_values, n=1, cutoff=0.6)
        if matches:
            return matches[0]

        # Final fallback
        return fallback_value if fallback_value in allowed_values else next(iter(allowed_values))

    @staticmethod
    def correct_numeric_parameter(
        value: Any,
        min_val: Optional[Union[int, float]] = None,
        max_val: Optional[Union[int, float]] = None,
        field_name: str = "value",
        fallback_value: Union[int, float] = 0
    ) -> Union[int, float]:
        """
        Correct numeric parameter to always return a valid number within range.

        Args:
            value: Any input value
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            field_name: Name of the field (for logging)
            fallback_value: Default value if correction fails

        Returns:
            Always returns a valid numeric value within range
        """
        # Try to convert to number
        if isinstance(value, (int, float)):
            numeric_value = value
        else:
            try:
                if isinstance(value, str):
                    # Handle common numeric string formats
                    value = value.strip().replace(',', '')
                numeric_value = float(value)
            except (ValueError, TypeError):
                numeric_value = fallback_value

        # Apply range constraints
        if min_val is not None and numeric_value < min_val:
            numeric_value = min_val

        if max_val is not None and numeric_value > max_val:
            numeric_value = max_val

        # Return as int if it's effectively an integer
        if isinstance(numeric_value, float) and numeric_value.is_integer():
            return int(numeric_value)

        return numeric_value

    @staticmethod
    def correct_metadata_parameter(metadata: Any) -> Dict[str, Any]:
        """
        Correct metadata parameter to always return a valid dictionary.

        Args:
            metadata: Any input value for metadata

        Returns:
            Always returns a valid metadata dictionary
        """
        if metadata is None:
            return {}

        # If it's already a dict, validate and correct its contents
        if isinstance(metadata, dict):
            corrected_metadata = {}
            for key, value in metadata.items():
                # Correct key
                if not isinstance(key, str):
                    try:
                        key = str(key)
                    except Exception:
                        key = "invalid_key"

                # Sanitize key
                key = key.replace("|", ";").replace("\n", " ").strip()
                if not key:
                    key = "empty_key"

                # Correct value
                if isinstance(value, str):
                    preserve_keys = {"body", "snippet", "content"}
                    if key in preserve_keys:
                        value = value
                    else:
                        # Escape comparison operators and sanitize
                        value = BulletproofParameterCorrector._escape_comparison_operators(value)
                        value = value.replace("\n", " ").replace("\r", " ").replace("|", ";")
                        if len(value) > 500:
                            value = value[:497] + "..."
                elif not isinstance(value, (int, float, bool, list, dict)):
                    try:
                        value = str(value)
                        value = BulletproofParameterCorrector._escape_comparison_operators(value)
                    except Exception:
                        value = "invalid_value"

                corrected_metadata[key] = value

            return corrected_metadata

        # Try to parse JSON string
        if isinstance(metadata, str):
            try:
                parsed = json.loads(metadata)
                if isinstance(parsed, dict):
                    return BulletproofParameterCorrector.correct_metadata_parameter(parsed)
            except json.JSONDecodeError:
                pass

        # Convert to dict with single entry
        try:
            str_value = str(metadata)
            str_value = BulletproofParameterCorrector._escape_comparison_operators(str_value)
            return {"value": str_value[:500]}
        except Exception:
            return {"error": "invalid_metadata"}

    @staticmethod
    def _escape_comparison_operators(value: str) -> str:
        """
        Escape comparison operators in string values to prevent parsing issues.

        Args:
            value: String value to escape

        Returns:
            String with escaped comparison operators
        """
        if not isinstance(value, str):
            return value

        # Check for dangerous numeric comparison patterns
        numeric_comparison_pattern = r'^\s*\d+\.?\d*\s*[><=]+\s*\d+\.?\d*\s*$'
        if re.match(numeric_comparison_pattern, value.strip()):
            return f"'{value}'"  # Quote to prevent interpretation

        # Escape comparison operators
        escaped = value
        dangerous_patterns = [
            (r'(?<!\\)>', r'\>'),  # Escape > symbols
            (r'(?<!\\)<', r'\<'),  # Escape < symbols
        ]

        for pattern, replacement in dangerous_patterns:
            escaped = re.sub(pattern, replacement, escaped)

        return escaped

    @staticmethod
    def correct_list_parameter(
        value: Any,
        delimiter: str = ",",
        max_items: Optional[int] = None
    ) -> List[str]:
        """
        Correct list parameter to always return a valid list of strings.

        Args:
            value: Any input value
            delimiter: Delimiter for splitting strings
            max_items: Maximum number of items allowed

        Returns:
            Always returns a valid list of strings
        """
        if value is None:
            return []

        # If it's already a list, validate and correct items
        if isinstance(value, list):
            corrected_list = []
            for item in value:
                if isinstance(item, str):
                    corrected_item = item.replace("\n", " ").replace("|", ";").strip()
                    if corrected_item:
                        corrected_list.append(corrected_item[:100])  # Limit item length
                else:
                    try:
                        corrected_item = str(item)[:100]
                        corrected_item = corrected_item.replace("\n", " ").replace("|", ";").strip()
                        if corrected_item:
                            corrected_list.append(corrected_item)
                    except Exception:
                        continue

            return corrected_list[:max_items] if max_items else corrected_list

        # Try to split string
        if isinstance(value, str):
            try:
                items = value.split(delimiter)
                corrected_list = []
                for item in items:
                    corrected_item = item.replace("\n", " ").replace("|", ";").strip()
                    if corrected_item:
                        corrected_list.append(corrected_item[:100])

                return corrected_list[:max_items] if max_items else corrected_list
            except Exception:
                return []

        # Convert single item to list
        try:
            str_value = str(value)
            corrected_item = str_value.replace("\n", " ").replace("|", ";").strip()
            if corrected_item:
                return [corrected_item[:100]]
        except Exception:
            pass

        return []

    @staticmethod
    def correct_timestamp_parameter(timestamp_utc: Optional[str]) -> str:
        """
        Correct timestamp parameter to always return a valid timestamp.

        Args:
            timestamp_utc: Input timestamp string

        Returns:
            Always returns a valid UTC timestamp string
        """
        if not timestamp_utc:
            from scribe_mcp.utils.time import format_utc
            return format_utc()

        # Try to parse existing timestamp
        parsed = ToolValidator._parse_timestamp(timestamp_utc)
        if parsed is not None:
            return timestamp_utc

        # Try to fix common timestamp format issues
        try:
            # Add UTC if missing
            if not timestamp_utc.endswith("UTC") and not timezone_info_pattern.search(timestamp_utc):
                timestamp_utc = timestamp_utc.strip() + " UTC"
                parsed = ToolValidator._parse_timestamp(timestamp_utc)
                if parsed is not None:
                    return timestamp_utc
        except Exception:
            pass

        # Fallback to current time
        from scribe_mcp.utils.time import format_utc
        return format_utc()

    @staticmethod
    def ensure_parameter_validity(
        parameters: Dict[str, Any],
        validation_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Ensure all parameters are valid according to schema, correcting as needed.

        Args:
            parameters: Input parameters dictionary
            validation_schema: Schema defining validation rules

        Returns:
            Corrected parameters dictionary with all values valid
        """
        corrected_params = {}

        for field_name, field_schema in validation_schema.items():
            field_value = parameters.get(field_name)
            field_type = field_schema.get("type")

            # Get correction strategy based on field type
            if field_type == str:
                # String correction
                corrected_value = BulletproofParameterCorrector.correct_message_parameter(field_value)

                # Apply enum constraints if specified
                allowed_values = field_schema.get("allowed_values")
                if allowed_values:
                    corrected_value = BulletproofParameterCorrector.correct_enum_parameter(
                        corrected_value, allowed_values, field_name,
                        field_schema.get("default")
                    )

                corrected_params[field_name] = corrected_value

            elif field_type in (int, float):
                # Numeric correction
                corrected_value = BulletproofParameterCorrector.correct_numeric_parameter(
                    field_value,
                    field_schema.get("min_value"),
                    field_schema.get("max_value"),
                    field_name,
                    field_schema.get("default", 0)
                )
                corrected_params[field_name] = corrected_value

            elif field_type == dict:
                # Dictionary (metadata) correction
                corrected_value = BulletproofParameterCorrector.correct_metadata_parameter(field_value)
                corrected_params[field_name] = corrected_value

            elif field_type == list:
                # List correction
                corrected_value = BulletproofParameterCorrector.correct_list_parameter(
                    field_value,
                    field_schema.get("delimiter", ","),
                    field_schema.get("max_items")
                )
                corrected_params[field_name] = corrected_value

            else:
                # Generic correction - convert to string and sanitize
                corrected_value = BulletproofParameterCorrector.correct_message_parameter(field_value)
                corrected_params[field_name] = corrected_value

        return corrected_params

    @staticmethod
    def correct_intelligent_parameter(
        param_name: str,
        invalid_value: Any,
        context: Dict[str, Any]
    ) -> Any:
        """
        Apply intelligent parameter correction using multiple fallback strategies.

        This is the master correction method that applies the most appropriate
        correction strategy based on the parameter type, context, and operation.

        Args:
            param_name: Name of the parameter to correct
            invalid_value: The invalid value that needs correction
            context: Context dictionary with operation type, tool name, and other hints

        Returns:
            Always returns a valid, corrected value
        """
        tool_name = context.get('tool_name', 'unknown')
        operation_type = context.get('operation_type', 'general')

        # Use tool-specific correction if available
        tool_method = f"correct_{tool_name}_parameters"
        if hasattr(BulletproofParameterCorrector, tool_method):
            tool_specific = getattr(BulletproofParameterCorrector, tool_method)
            if callable(tool_specific):
                try:
                    corrected = tool_specific({param_name: invalid_value}, context)
                    return corrected.get(param_name, invalid_value)
                except Exception:
                    # Fallback to general correction if tool-specific fails
                    pass

        # Apply parameter type-specific correction
        if param_name in ['n', 'limit', 'page_size', 'max_results']:
            return BulletproofParameterCorrector.correct_numeric_parameter(
                invalid_value, min_val=1, max_val=1000, fallback_value=50
            )
        elif param_name in ['document_types']:
            return BulletproofParameterCorrector.correct_list_parameter(
                invalid_value, delimiter=",", max_items=10
            )
        elif param_name in ["search_scope"]:
            allowed_scopes = {"project", "global", "all_projects", "research", "bugs", "all"}
            return BulletproofParameterCorrector.correct_enum_parameter(
                invalid_value, allowed_scopes, "search_scope", "project"
            )
        elif param_name in ["output_mode"]:
            allowed_modes = {"project", "global", "all", "research"}  # best-effort, tool-specific enums can override
            return BulletproofParameterCorrector.correct_enum_parameter(
                invalid_value, allowed_modes, "output_mode", "project"
            )
        elif param_name in ['message', 'query', 'action']:
            return BulletproofParameterCorrector.correct_message_parameter(invalid_value)
        elif param_name in ['meta', 'metadata']:
            return BulletproofParameterCorrector.correct_metadata_parameter(invalid_value)
        elif param_name in ['status', 'log_type']:
            allowed_statuses = {'info', 'success', 'warn', 'error', 'bug', 'plan'}
            return BulletproofParameterCorrector.correct_enum_parameter(
                invalid_value, allowed_statuses, param_name, 'info'
            )
        else:
            # Generic correction - convert to string and sanitize
            return BulletproofParameterCorrector.correct_message_parameter(invalid_value)

    @staticmethod
    def correct_fuzzy_parameter_match(
        param_name: str,
        invalid_value: Any,
        valid_options: List[str]
    ) -> Any:
        """
        Use fuzzy string matching for invalid parameters.

        This method applies sophisticated fuzzy matching to find the closest
        valid option when an invalid parameter is provided.

        Args:
            param_name: Name of the parameter to correct
            invalid_value: The invalid value that needs correction
            valid_options: List of valid options to match against

        Returns:
            The closest matching valid option or a sensible default
        """
        if not valid_options:
            return invalid_value

        # Convert to string for comparison
        try:
            str_value = str(invalid_value).lower().strip()
        except Exception:
            return valid_options[0]  # Return first valid option

        # Exact match (case-insensitive)
        for option in valid_options:
            if str_value == option.lower():
                return option

        # Substring match
        for option in valid_options:
            if str_value in option.lower() or option.lower() in str_value:
                return option

        # Fuzzy matching using difflib
        try:
            import difflib
            matches = difflib.get_close_matches(
                str_value, valid_options, n=1, cutoff=0.6
            )
            if matches:
                return matches[0]
        except Exception:
            pass

        # Return the first valid option as final fallback
        return valid_options[0]

    @staticmethod
    def correct_complex_parameter_combination(
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle complex multi-parameter corrections with interdependencies.

        This method analyzes multiple parameters together and applies corrections
        that consider the relationships between parameters.

        Args:
            params: Dictionary of parameters to correct
            context: Context dictionary with operation type and hints

        Returns:
            Corrected parameters dictionary with all interdependencies resolved
        """
        corrected = {}
        tool_name = context.get('tool_name', 'unknown')

        # Handle pagination parameter conflicts
        if 'n' in params and 'page_size' in params:
            n_value = BulletproofParameterCorrector.correct_numeric_parameter(
                params['n'], min_val=1, max_val=1000
            )
            page_size_value = BulletproofParameterCorrector.correct_numeric_parameter(
                params['page_size'], min_val=1, max_val=1000
            )

            # Resolve conflicts: use the smaller value as page_size, calculate pagination
            if n_value < page_size_value:
                corrected['n'] = n_value
                corrected['page_size'] = n_value
                corrected['page'] = 1
            else:
                corrected['page_size'] = page_size_value
                corrected['page'] = max(1, n_value // page_size_value)
                corrected['n'] = None  # Will be calculated from pagination
        else:
            # Apply individual corrections
            for param_name, param_value in params.items():
                corrected[param_name] = BulletproofParameterCorrector.correct_intelligent_parameter(
                    param_name, param_value, context
                )

        # Handle date/time parameter combinations
        if 'start' in params or 'end' in params:
            start_date = BulletproofParameterCorrector._parse_date_parameter(
                params.get('start'), context
            )
            end_date = BulletproofParameterCorrector._parse_date_parameter(
                params.get('end'), context
            )

            # Ensure logical ordering
            if start_date and end_date and start_date > end_date:
                corrected['start'], corrected['end'] = end_date, start_date
            elif start_date:
                corrected['start'] = start_date
            elif end_date:
                corrected['end'] = end_date

        return corrected

    @staticmethod
    def apply_contextual_correction(
        param_name: str,
        invalid_value: Any,
        operation_context: str
    ) -> Any:
        """
        Apply operation-specific parameter corrections.

        This method applies corrections based on the specific operation context,
        such as 'search', 'create', 'update', 'delete', etc.

        Args:
            param_name: Name of the parameter to correct
            invalid_value: The invalid value that needs correction
            operation_context: Context of the operation (search, create, update, etc.)

        Returns:
            Contextually corrected parameter value
        """
        context = {
            'operation_type': operation_context,
            'tool_name': operation_context.split('_')[0] if '_' in operation_context else 'unknown'
        }

        # Search operation corrections
        if operation_context in ['search', 'query', 'filter']:
            if param_name in ['query', 'message', 'search_term']:
                # Escape special characters for search
                corrected = BulletproofParameterCorrector.correct_message_parameter(invalid_value)
                return corrected.replace('"', '\\"').replace("'", "\\'")
            elif param_name in ['relevance_threshold', 'min_score']:
                return BulletproofParameterCorrector.correct_numeric_parameter(
                    invalid_value, min_val=0.0, max_val=1.0, fallback_value=0.5
                )

        # Create operation corrections
        elif operation_context in ['create', 'add', 'append']:
            if param_name in ['message', 'content', 'description']:
                # Ensure content is valid for creation
                corrected = BulletproofParameterCorrector.correct_message_parameter(invalid_value)
                if len(corrected) < 3:
                    return "Default content: " + corrected
                return corrected
            elif param_name in ['status', 'state']:
                default_status = 'info' if operation_context == 'create' else 'success'
                allowed_statuses = {'info', 'success', 'warn', 'error', 'bug', 'plan'}
                return BulletproofParameterCorrector.correct_enum_parameter(
                    invalid_value, allowed_statuses, param_name, default_status
                )

        # Update operation corrections
        elif operation_context in ['update', 'modify', 'edit']:
            if param_name in ['id', 'entry_id']:
                # Ensure ID is valid for updates
                return str(invalid_value) if invalid_value else 'default_id'
            elif param_name in ['version', 'revision']:
                return BulletproofParameterCorrector.correct_numeric_parameter(
                    invalid_value, min_val=1, fallback_value=1
                )

        # Delete operation corrections
        elif operation_context in ['delete', 'remove']:
            if param_name in ['confirm', 'confirmed']:
                return bool(invalid_value) or False  # Default to False for safety
            elif param_name in ['force', 'permanent']:
                return bool(invalid_value) or False  # Default to False for safety

        # Generic correction as fallback
        return BulletproofParameterCorrector.correct_intelligent_parameter(
            param_name, invalid_value, context
        )

    @staticmethod
    def _parse_date_parameter(date_value: Any, context: Dict[str, Any]) -> Optional[str]:
        """
        Parse and validate date parameter with intelligent correction.

        Args:
            date_value: Date value to parse
            context: Context dictionary for correction hints

        Returns:
            Parsed date string or None if parsing fails
        """
        if date_value is None:
            return None

        if isinstance(date_value, str):
            # Try to parse as ISO format or common formats
            from datetime import datetime
            common_formats = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S UTC",
                "%Y-%m-%dT%H:%M:%SZ"
            ]

            for fmt in common_formats:
                try:
                    parsed = datetime.strptime(date_value.strip(), fmt)
                    return parsed.strftime("%Y-%m-%d")
                except ValueError:
                    continue

            # If all formats fail, return the original string
            return date_value.strip()

        # Convert numeric timestamp to date string
        try:
            import time
            if isinstance(date_value, (int, float)):
                return time.strftime("%Y-%m-%d", time.localtime(date_value))
        except Exception:
            pass

        # Fallback to string conversion
        try:
            return str(date_value)
        except Exception:
            return None

    @staticmethod
    def correct_read_recent_parameters(
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Correct read_recent tool parameters to fix type errors and token explosion.

        Addresses Bug #1 and Bug #2 from the confirmed issues:
        - Parameter type error when mixing n parameter types
        - Token explosion from returning too many entries

        Args:
            params: read_recent parameters dictionary
            context: Context dictionary

        Returns:
            Corrected parameters dictionary
        """
        corrected = {}

        # Handle n parameter with type correction
        if 'n' in params:
            corrected['n'] = BulletproofParameterCorrector.correct_numeric_parameter(
                params['n'], min_val=1, max_val=100, fallback_value=20  # Limit to prevent token explosion
            )
        else:
            corrected['n'] = 20  # Safe default

        # Handle filter parameter
        if 'filter' in params:
            filter_value = params['filter']
            if isinstance(filter_value, dict):
                corrected['filter'] = filter_value
            else:
                # Convert to dict if possible
                try:
                    if isinstance(filter_value, str):
                        import json
                        corrected['filter'] = json.loads(filter_value)
                    else:
                        corrected['filter'] = {"status": str(filter_value)}
                except Exception:
                    corrected['filter'] = {"agent": "all"}
        else:
            corrected['filter'] = {}

        # Handle pagination parameters
        if 'page' in params:
            corrected['page'] = BulletproofParameterCorrector.correct_numeric_parameter(
                params['page'], min_val=1, fallback_value=1
            )
        else:
            corrected['page'] = 1

        if 'page_size' in params:
            corrected['page_size'] = BulletproofParameterCorrector.correct_numeric_parameter(
                params['page_size'], min_val=1, max_val=50, fallback_value=20  # Limit for token control
            )
        else:
            corrected['page_size'] = min(corrected['n'], 20)

        # Handle other parameters with intelligent correction
        for param_name, param_value in params.items():
            if param_name not in corrected:
                corrected[param_name] = BulletproofParameterCorrector.correct_intelligent_parameter(
                    param_name, param_value, context
                )

        return corrected

    @staticmethod
    def correct_query_entries_parameters(
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Correct query_entries tool parameters to fix enum validation and array issues.

        Addresses Bug #3 from the confirmed issues:
        - Array parameters rejected with contradictory error messages
        - Enum validation failures for document_types and search_scope

        Args:
            params: query_entries parameters dictionary
            context: Context dictionary

        Returns:
            Corrected parameters dictionary
        """
        corrected = {}

        # Handle document_types parameter with array correction
        if 'document_types' in params:
            doc_types = params['document_types']
            if isinstance(doc_types, str):
                # Split string into array
                corrected['document_types'] = BulletproofParameterCorrector.correct_list_parameter(
                    doc_types, delimiter=",", max_items=10
                )
            elif isinstance(doc_types, list):
                # Validate and correct list items
                corrected['document_types'] = BulletproofParameterCorrector.correct_list_parameter(
                    doc_types, delimiter=",", max_items=10
                )
            else:
                corrected['document_types'] = ["progress"]  # Default
        else:
            corrected['document_types'] = ["progress"]

        # Handle search_scope parameter with enum correction
        if 'search_scope' in params:
            scope_value = params['search_scope']
            allowed_scopes = {'project', 'global', 'all_projects', 'research', 'bugs', 'all'}
            corrected['search_scope'] = BulletproofParameterCorrector.correct_enum_parameter(
                scope_value, allowed_scopes, 'search_scope', 'project'
            )
        else:
            corrected['search_scope'] = 'project'

        # Handle message_mode parameter with enum correction
        if 'message_mode' in params:
            mode_value = params['message_mode']
            allowed_modes = {'substring', 'regex', 'exact'}
            corrected['message_mode'] = BulletproofParameterCorrector.correct_enum_parameter(
                mode_value, allowed_modes, 'message_mode', 'substring'
            )
        else:
            corrected['message_mode'] = 'substring'

        # Handle numeric parameters
        for numeric_param in ['limit', 'page_size', 'max_results', 'relevance_threshold']:
            if numeric_param in params:
                if numeric_param == 'relevance_threshold':
                    corrected[numeric_param] = BulletproofParameterCorrector.correct_numeric_parameter(
                        params[numeric_param], min_val=0.0, max_val=1.0, fallback_value=0.5
                    )
                else:
                    corrected[numeric_param] = BulletproofParameterCorrector.correct_numeric_parameter(
                        params[numeric_param], min_val=1, max_val=1000, fallback_value=50
                    )

        # Handle boolean parameters
        for bool_param in ['case_sensitive', 'compact', 'include_metadata', 'verify_code_references']:
            if bool_param in params:
                corrected[bool_param] = bool(params[bool_param])

        # Handle other parameters with intelligent correction
        for param_name, param_value in params.items():
            if param_name not in corrected:
                corrected[param_name] = BulletproofParameterCorrector.correct_intelligent_parameter(
                    param_name, param_value, context
                )

        return corrected

    @staticmethod
    def correct_manage_docs_parameters(
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Correct manage_docs tool parameters to fix create_research_doc failures.

        Addresses Bug #4 from the confirmed issues:
        - "Invalid arguments" despite correct parameter usage

        Args:
            params: manage_docs parameters dictionary
            context: Context dictionary

        Returns:
            Corrected parameters dictionary
        """
        corrected = {}

        # Handle action parameter with enum correction
        if 'action' in params:
            action_value = params['action']
            allowed_actions = {
                'replace_section', 'append', 'status_update', 'create_research_doc',
                'create_bug_report', 'create_review_report', 'create_agent_report_card',
                'apply_patch', 'replace_range'
            }
            corrected['action'] = BulletproofParameterCorrector.correct_enum_parameter(
                action_value, allowed_actions, 'action', 'append'
            )
        else:
            corrected['action'] = 'append'

        # Handle doc parameter with fuzzy matching
        if 'doc' in params:
            doc_value = params['doc']
            valid_docs = ['architecture', 'phase_plan', 'checklist', 'implementation', 'review']
            corrected['doc'] = BulletproofParameterCorrector.correct_fuzzy_parameter_match(
                'doc', doc_value, valid_docs
            )
        else:
            corrected['doc'] = 'implementation'

        # Handle section parameter for replace_section action
        if corrected['action'] == 'replace_section' and 'section' in params:
            section_value = params['section']
            # Sanitize section ID
            corrected['section'] = BulletproofParameterCorrector.correct_message_parameter(section_value)
            corrected['section'] = corrected['section'].lower().replace(' ', '_').replace('-', '_')
        elif corrected['action'] == 'replace_section':
            corrected['section'] = 'general'  # Default section

        # Handle content parameter
        if 'content' in params:
            corrected['content'] = BulletproofParameterCorrector.correct_message_parameter(params['content'])
            # Ensure content is not empty for certain actions
            if corrected['action'] in ['replace_section', 'append'] and not corrected['content'].strip():
                corrected['content'] = "Default content: No content provided."
        else:
            if corrected['action'] not in ['apply_patch', 'replace_range']:
                corrected['content'] = "Default content: No content provided."

        # Handle metadata parameter for bug reports and research docs
        if 'metadata' in params or 'meta' in params:
            meta_value = params.get('metadata', params.get('meta', {}))
            corrected['metadata'] = BulletproofParameterCorrector.correct_metadata_parameter(meta_value)
        else:
            corrected['metadata'] = {}

        # Handle other parameters with intelligent correction
        for param_name, param_value in params.items():
            if param_name not in corrected:
                corrected[param_name] = BulletproofParameterCorrector.correct_intelligent_parameter(
                    param_name, param_value, context
                )

        return corrected

    @staticmethod
    def correct_append_entry_parameters(
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Correct append_entry tool parameters to fix bulk performance issues.

        Addresses Bug #5 from the confirmed issues:
        - Sequential processing with 1-second delays per item

        Args:
            params: append_entry parameters dictionary
            context: Context dictionary

        Returns:
            Corrected parameters dictionary
        """
        corrected = {}

        # Handle message parameter
        if 'message' in params:
            corrected['message'] = BulletproofParameterCorrector.correct_message_parameter(params['message'])
        else:
            corrected['message'] = "Default log entry: No message provided."

        # Handle items parameter for bulk mode
        if 'items' in params:
            items_value = params['items']
            try:
                if isinstance(items_value, str):
                    import json
                    items_list = json.loads(items_value)
                else:
                    items_list = items_value

                if isinstance(items_list, list):
                    # Limit bulk size for performance
                    max_items = 100  # Performance limit
                    corrected['items'] = items_list[:max_items]
                else:
                    corrected['items'] = []
            except Exception:
                corrected['items'] = []
        else:
            corrected['items'] = []

        # Handle items_list parameter
        if 'items_list' in params:
            items_list_value = params['items_list']
            if isinstance(items_list_value, list):
                # Limit bulk size for performance
                max_items = 100  # Performance limit
                corrected['items_list'] = items_list_value[:max_items]
            else:
                corrected['items_list'] = []
        else:
            corrected['items_list'] = []

        # Handle auto_split parameter
        if 'auto_split' in params:
            corrected['auto_split'] = bool(params['auto_split'])
        else:
            corrected['auto_split'] = True  # Enable auto-splitting for performance

        # Handle stagger_seconds parameter for performance optimization
        if 'stagger_seconds' in params:
            corrected['stagger_seconds'] = BulletproofParameterCorrector.correct_numeric_parameter(
                params['stagger_seconds'], min_val=0, max_val=5, fallback_value=0
            )
        else:
            corrected['stagger_seconds'] = 0  # No delay for performance

        # Handle status parameter with enum correction
        if 'status' in params:
            status_value = params['status']
            allowed_statuses = {'info', 'success', 'warn', 'error', 'bug', 'plan'}
            corrected['status'] = BulletproofParameterCorrector.correct_enum_parameter(
                status_value, allowed_statuses, 'status', 'info'
            )
        else:
            corrected['status'] = 'info'

        # Handle agent parameter
        if 'agent' in params:
            corrected['agent'] = BulletproofParameterCorrector.correct_message_parameter(params['agent'])
        else:
            corrected['agent'] = 'Scribe'

        # Handle emoji parameter
        if 'emoji' in params:
            corrected['emoji'] = BulletproofParameterCorrector.correct_message_parameter(params['emoji'])
        else:
            corrected['emoji'] = ''

        # Handle metadata parameter
        if 'meta' in params or 'metadata' in params:
            meta_value = params.get('meta', params.get('metadata', {}))
            corrected['meta'] = BulletproofParameterCorrector.correct_metadata_parameter(meta_value)
        else:
            corrected['meta'] = {}

        # Handle timestamp parameter
        if 'timestamp_utc' in params:
            corrected['timestamp_utc'] = BulletproofParameterCorrector.correct_timestamp_parameter(
                params['timestamp_utc']
            )
        else:
            corrected['timestamp_utc'] = None  # Will use current time

        # Handle other parameters with intelligent correction
        for param_name, param_value in params.items():
            if param_name not in corrected:
                corrected[param_name] = BulletproofParameterCorrector.correct_intelligent_parameter(
                    param_name, param_value, context
                )

        return corrected

    @staticmethod
    def correct_rotate_log_parameters(
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Correct rotate_log tool parameters to fix rotation parameter validation.

        Addresses rotation parameter conflicts and validation issues.

        Args:
            params: rotate_log parameters dictionary
            context: Context dictionary

        Returns:
            Corrected parameters dictionary
        """
        corrected = {}

        # Handle suffix parameter
        if 'suffix' in params:
            corrected['suffix'] = BulletproofParameterCorrector.correct_message_parameter(params['suffix'])
        else:
            from datetime import datetime
            corrected['suffix'] = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Handle confirm parameter (safety critical)
        if 'confirm' in params:
            corrected['confirm'] = bool(params['confirm'])
        else:
            corrected['confirm'] = False  # Default to False for safety

        # Handle dry_run parameter
        if 'dry_run' in params:
            corrected['dry_run'] = bool(params['dry_run'])
        else:
            corrected['dry_run'] = True  # Default to True for safety

        # Handle log_type parameter with enum correction
        if 'log_type' in params:
            log_type_value = params['log_type']
            allowed_log_types = {'progress', 'doc_updates', 'security', 'bugs', 'global'}
            corrected['log_type'] = BulletproofParameterCorrector.correct_enum_parameter(
                log_type_value, allowed_log_types, 'log_type', 'progress'
            )
        else:
            corrected['log_type'] = 'progress'

        # Handle threshold_entries parameter
        if 'threshold_entries' in params:
            corrected['threshold_entries'] = BulletproofParameterCorrector.correct_numeric_parameter(
                params['threshold_entries'], min_val=10, max_val=10000, fallback_value=500
            )
        else:
            corrected['threshold_entries'] = 500

        # Handle auto_threshold parameter
        if 'auto_threshold' in params:
            corrected['auto_threshold'] = bool(params['auto_threshold'])
        else:
            corrected['auto_threshold'] = True

        # Handle rotate_all parameter
        if 'rotate_all' in params:
            corrected['rotate_all'] = bool(params['rotate_all'])
        else:
            corrected['rotate_all'] = False

        # Handle log_types parameter for multiple log rotation
        if 'log_types' in params:
            log_types_value = params['log_types']
            if isinstance(log_types_value, str):
                corrected['log_types'] = BulletproofParameterCorrector.correct_list_parameter(
                    log_types_value, delimiter=",", max_items=5
                )
            elif isinstance(log_types_value, list):
                corrected['log_types'] = log_types_value[:5]  # Limit to 5 log types
            else:
                corrected['log_types'] = [corrected['log_type']]
        else:
            corrected['log_types'] = [corrected['log_type']]

        # Handle other parameters with intelligent correction
        for param_name, param_value in params.items():
            if param_name not in corrected:
                corrected[param_name] = BulletproofParameterCorrector.correct_intelligent_parameter(
                    param_name, param_value, context
                )

        return corrected


# Regex pattern for timezone information in timestamps
timezone_info_pattern = re.compile(r'[+-]\d{2}:?\d{2}|UTC|GMT|[A-Z]{3,4}$')
