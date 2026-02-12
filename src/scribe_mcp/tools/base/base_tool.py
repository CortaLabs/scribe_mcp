"""Abstract base class for unified Scribe MCP tool development."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, Optional

from .parameter_normalizer import normalize_dict_param, normalize_list_param, validate_param_types
from .tool_result import ToolResult


class BaseTool(ABC):
    """
    Abstract base class providing unified infrastructure for all Scribe MCP tools.

    This class handles:
    - Consistent parameter normalization and validation
    - Standardized error handling and responses
    - MCP tool registration and lifecycle
    - State management integration
    """

    def __init__(self, server_module):
        """Initialize base tool with server module reference."""
        self.server_module = server_module
        self.tool_name = self.__class__.__name__

    async def __call__(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Main entry point that handles parameter normalization and validation.

        This method provides consistent parameter handling before delegating
        to the具体的 tool implementation.
        """
        # Get the actual tool implementation method
        implementation = getattr(self, self._get_implementation_method_name())

        # Normalize and validate parameters
        normalized_params = self._normalize_parameters(kwargs)
        validation_errors = self._validate_parameters(normalized_params)

        if validation_errors:
            return ToolResult.validation_error(validation_errors).to_dict()

        try:
            # Record tool state
            state_snapshot = await self.server_module.state_manager.record_tool(self.tool_name)

            # Call the actual implementation
            result = await implementation(*args, **normalized_params)

            # Ensure result is in standard format
            if not isinstance(result, dict) or "ok" not in result:
                return ToolResult.success(data=result).to_dict()

            return result

        except Exception as e:
            return ToolResult.error(
                error=f"{self.tool_name} failed: {str(e)}",
                suggestion="Check parameters and try again"
            ).to_dict()

    def _get_implementation_method_name(self) -> str:
        """Get the name of the actual tool implementation method."""
        # By convention, tools implement their logic in an async method
        # with the same name as the class but without 'Tool' suffix
        class_name = self.__class__.__name__
        if class_name.endswith('Tool'):
            return class_name[:-4].lower()
        return class_name.lower()

    def _normalize_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize parameters using the parameter normalizer utilities.
        """
        # Get parameter expectations from the implementation method signature
        sig = inspect.signature(getattr(self, self._get_implementation_method_name()))
        param_types = {
            name: param.annotation
            for name, param in sig.parameters.items()
            if param.annotation != inspect.Parameter.empty
        }

        normalized = {}
        for param_name, param_value in params.items():
            if param_name in param_types:
                expected_type = param_types[param_name]

                # Handle Union types (dict parameters)
                if hasattr(expected_type, '__origin__') and hasattr(expected_type, '__args__'):
                    if dict in expected_type.__args__:
                        try:
                            normalized[param_name] = normalize_dict_param(
                                param_value,
                                param_name
                            )
                        except ValueError as e:
                            # Will be caught by validation
                            normalized[param_name] = param_value
                    elif list in expected_type.__args__:
                        try:
                            normalized[param_name] = normalize_list_param(
                                param_value,
                                param_name
                            )
                        except ValueError:
                            normalized[param_name] = param_value
                else:
                    normalized[param_name] = param_value
            else:
                normalized[param_name] = param_value

        return normalized

    def _validate_parameters(self, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate normalized parameters against their type annotations.
        """
        # Get parameter expectations from the implementation method signature
        sig = inspect.signature(getattr(self, self._get_implementation_method_name()))
        expected_types = {
            name: param.annotation
            for name, param in sig.parameters.items()
            if param.annotation != inspect.Parameter.empty
        }

        return validate_param_types(params, expected_types)

    @abstractmethod
    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Abstract method for the actual tool implementation.

        This method should be implemented by concrete tool classes.
        """
        pass

    @classmethod
    def register(cls, server_app):
        """
        Register this tool with the MCP server application.
        """
        tool_instance = cls(server_app.server_module if hasattr(server_app, 'server_module') else None)

        # Register the __call__ method as the tool
        server_app.tool()(tool_instance)

        return tool_instance