"""Parameter normalization utilities for consistent MCP tool parameter handling.

This module provides robust parameter parsing and validation to handle
the MCP framework's JSON serialization of dict and list parameters.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union


def normalize_dict_param(
    param: Optional[Union[Dict[str, Any], str]],
    param_name: str = "parameter"
) -> Optional[Dict[str, Any]]:
    """
    Normalize a dict parameter that may be JSON-serialized by MCP framework.

    The MCP framework serializes dict parameters as JSON strings when passed from
    external clients. This function intelligently handles both dict and string formats,
    similar to the proven pattern in append_entry.py.

    Args:
        param: The parameter value (dict or JSON string)
        param_name: Name of parameter for error messages

    Returns:
        Normalized dict or None if param is None/empty

    Examples:
        normalize_dict_param({"key": "value"})  # -> {"key": "value"}
        normalize_dict_param('{"key": "value"}')  # -> {"key": "value"}
        normalize_dict_param(None)  # -> None

    Raises:
        ValueError: If parameter is invalid JSON string
    """
    if not param:
        return None

    # If already a dict, return as-is
    if isinstance(param, dict):
        return param

    # If string, try to parse as JSON
    if isinstance(param, str):
        try:
            parsed = json.loads(param)
            if isinstance(parsed, dict):
                return parsed
            else:
                raise ValueError(f"{param_name} parameter JSON parsed but didn't return dict")
        except json.JSONDecodeError:
            # Handle common CLI patterns like "key=value,key2=value2"
            if '=' in param:
                try:
                    result = {}
                    # Try comma-separated first
                    if ',' in param:
                        delimiter = ','
                    else:
                        delimiter = ' '

                    for pair in param.split(delimiter):
                        pair = pair.strip()
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            result[key.strip()] = value.strip()
                        else:
                            # If no equals, treat as message
                            result['message'] = pair.strip()
                    return result
                except Exception:
                    raise ValueError(f"Could not parse {param_name} parameter as key=value pairs")
            else:
                raise ValueError(f"{param_name} parameter is not valid JSON")

    # Invalid type
    raise ValueError(f"{param_name} parameter has unsupported type: {type(param)}")


def normalize_list_param(
    param: Optional[Union[List[Any], str]],
    param_name: str = "parameter"
) -> Optional[List[Any]]:
    """
    Normalize a list parameter that may be JSON-serialized by MCP framework.

    Args:
        param: The parameter value (list or JSON string)
        param_name: Name of parameter for error messages

    Returns:
        Normalized list or None if param is None/empty

    Raises:
        ValueError: If parameter is invalid JSON string
    """
    if not param:
        return None

    if isinstance(param, list):
        return param

    if isinstance(param, str):
        try:
            parsed = json.loads(param)
            if isinstance(parsed, list):
                return parsed
            else:
                raise ValueError(f"{param_name} parameter JSON parsed but didn't return list")
        except json.JSONDecodeError:
            raise ValueError(f"{param_name} parameter is not valid JSON")

    raise ValueError(f"{param_name} parameter has unsupported type: {type(param)}")


def safe_get_nested(data: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary values.

    Args:
        data: Dictionary to get value from
        keys: Keys to traverse in order
        default: Default value if any key is missing

    Returns:
        Value at nested key path or default
    """
    if not data:
        return default

    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def validate_param_types(
    params_dict: Dict[str, Any],
    expected_types: Dict[str, type]
) -> Dict[str, str]:
    """
    Validate parameter types and return error messages.

    Args:
        params_dict: Parameters to validate
        expected_types: Mapping of parameter names to expected types

    Returns:
        Dictionary of validation errors (empty if all valid)
    """
    errors = {}
    for param_name, expected_type in expected_types.items():
        if param_name in params_dict:
            value = params_dict[param_name]
            if not isinstance(value, expected_type):
                errors[param_name] = f"Expected {expected_type.__name__}, got {type(value).__name__}"
    return errors