"""Standardized tool result format for consistent responses across all Scribe MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union


class ToolResult:
    """
    Standardized result format for Scribe MCP tools.

    Provides consistent structure for success/error responses across all tools,
    enabling predictable error handling and response formatting.
    """

    def __init__(
        self,
        ok: bool,
        data: Optional[Any] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        suggestion: Optional[str] = None,
        warnings: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.ok = ok
        self.data = data
        self.error = error
        self.error_code = error_code
        self.suggestion = suggestion
        self.warnings = warnings or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for MCP response."""
        result = {
            "ok": self.ok,
        }

        if self.ok:
            if self.data is not None:
                result.update(self.data if isinstance(self.data, dict) else {"result": self.data})
            if self.warnings:
                result["warnings"] = self.warnings
            if self.metadata:
                result.update(self.metadata)
        else:
            if self.error:
                result["error"] = self.error
            if self.error_code:
                result["error_code"] = self.error_code
            if self.suggestion:
                result["suggestion"] = self.suggestion

        return result

    @classmethod
    def success(cls, data: Optional[Any] = None, **kwargs) -> 'ToolResult':
        """Create a successful result."""
        return cls(ok=True, data=data, **kwargs)

    @classmethod
    def error(cls, error: str, suggestion: Optional[str] = None, **kwargs) -> 'ToolResult':
        """Create an error result."""
        return cls(ok=False, error=error, suggestion=suggestion, **kwargs)

    @classmethod
    def validation_error(cls, errors: Dict[str, str]) -> 'ToolResult':
        """Create a validation error result."""
        error_msg = "Validation failed: " + "; ".join(f"{k}: {v}" for k, v in errors.items())
        return cls(
            ok=False,
            error=error_msg,
            error_code="VALIDATION_ERROR",
            suggestion="Check parameter types and formats",
            metadata={"validation_errors": errors}
        )

    @classmethod
    def parameter_error(cls, param_name: str, param_value: Any, expected_type: str) -> 'ToolResult':
        """Create a parameter type error result."""
        error_msg = f"Parameter '{param_name}' expects {expected_type}, got {type(param_value).__name__}"
        return cls(
            ok=False,
            error=error_msg,
            error_code="PARAMETER_TYPE_ERROR",
            suggestion=f"Ensure {param_name} is correct type",
            metadata={"param_name": param_name, "expected_type": expected_type, "actual_type": type(param_value).__name__}
        )