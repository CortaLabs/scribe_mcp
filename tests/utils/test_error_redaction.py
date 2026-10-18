"""Regression tests for Package 4.2 error redaction."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from scribe_mcp.doc_management.manager import _render_content
from scribe_mcp.utils.error_handler import (
    ErrorHandler,
    ExceptionHealer,
    sanitize_error_message,
)
from scribe_mcp.utils.tool_logger import log_tool_call


def test_sanitize_error_message_redacts_secret_tokens() -> None:
    raw = (
        "bridge failed: api_key=abc123 token:xyz789 "
        "Authorization=Bearer super-secret-value sk-abcdef123456"
    )
    sanitized = sanitize_error_message(raw)

    assert "abc123" not in sanitized
    assert "xyz789" not in sanitized
    assert "super-secret-value" not in sanitized
    assert "sk-abcdef123456" not in sanitized
    assert "[REDACTED]" in sanitized


def test_error_handler_storage_error_redacts_payload() -> None:
    result = ErrorHandler.create_storage_error(
        operation="persist bridge health",
        error=RuntimeError("write failed token=my-sensitive-token"),
    )

    assert result["ok"] is False
    assert "my-sensitive-token" not in result["error"]
    assert "[REDACTED]" in result["error"]


def test_tool_logger_redacts_error_message_before_writing_jsonl(tmp_path: Path) -> None:
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("", encoding="utf-8")

    log_tool_call(
        tool_name="bridge_health_check",
        session_id="sess-4-2",
        status="error",
        error_message="health check failed api_key=very-secret-key",
        repo_root=str(tmp_path),
        progress_log_path=str(progress_log),
    )

    tool_log_path = progress_log.parent / "TOOL_LOG.jsonl"
    lines = tool_log_path.read_text(encoding="utf-8").strip().splitlines()
    entry = json.loads(lines[-1])

    assert entry["status"] == "error"
    assert "very-secret-key" not in entry["error_message"]
    assert "[REDACTED]" in entry["error_message"]


def test_error_handler_handle_safe_operation_redacts_context_error() -> None:
    context: dict[str, str] = {"seed": "value"}

    def _fail():
        raise RuntimeError("operation failed api_key=context-secret")

    success, result = ErrorHandler.handle_safe_operation(
        operation_name="unsafe_op",
        operation_func=_fail,
        error_context=context,
        fallback_result={"ok": False},
    )

    assert success is False
    assert result == {"ok": False}
    assert context["operation"] == "unsafe_op"
    assert "context-secret" not in context["error"]
    assert context["error"] == "operation failed api_key=[REDACTED]"


def test_exception_healer_operation_specific_redacts_failure_payloads() -> None:
    class BadOperationContext:
        def __str__(self) -> str:
            raise RuntimeError("context formatting failed token=inner-secret")

    result = ExceptionHealer.heal_operation_specific_error(
        exception=RuntimeError("test exception token=outer-secret"),
        operation_context=BadOperationContext(),
        fallback_strategy="operation_fallback",
    )

    assert result["success"] is True
    assert result["ok"] is True
    assert result["result"]["fallback_operation"] is True
    assert result["result"]["message"] == "Generic fallback applied for [REDACTED]"
    assert "outer-secret" not in result["original_exception"]
    assert result["original_exception"] == "test exception token=[REDACTED]"
    assert result["healing_messages"][0].startswith("Healed [REDACTED] error")


def test_doc_manager_inline_jinja_fallback_log_redacts_exception(monkeypatch) -> None:
    class ExplodingEngine:
        def __init__(self, **kwargs):
            pass

        def render_string(self, *_args, **_kwargs):
            raise RuntimeError("inline failure token=inline-secret")

    logged: list[str] = []

    def _capture_error(message: str) -> None:
        logged.append(message)

    monkeypatch.setattr("scribe_mcp.template_engine.Jinja2TemplateEngine", ExplodingEngine)
    monkeypatch.setattr("scribe_mcp.doc_management.manager.doc_logger.error", _capture_error)

    rendered = asyncio.run(
        _render_content(
            project={"root": ".", "name": "redaction-test"},
            content="{{ value }}",
            template_name=None,
            metadata={},
        )
    )
    assert rendered == "{{ value }}"
    assert logged
    assert "inline-secret" not in logged[-1]
    assert "[REDACTED]" in logged[-1]
