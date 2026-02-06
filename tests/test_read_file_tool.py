import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import _DEFAULT_MAX_MATCHES, _FULL_MODE_TOKEN_LIMIT, read_file


def _install_execution_context(tmp_path) -> object:
    context = ExecutionContext(
        repo_root=str(tmp_path),
        mode="sentinel",
        session_id="session-1",
        execution_id="exec-1",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="agent-1",
            sub_id=None,
            display_name=None,
        ),
        intent="read_file_tests",
        timestamp_utc="2026-01-02T00:00:00+00:00",
        affected_dev_projects=[],
        sentinel_day="2026-01-02",
    )
    return server_module.router_context_manager.set_current(context)


@pytest.mark.asyncio
async def test_read_file_search_default_max_matches(tmp_path):
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "sample.txt"
        target.write_text("\n".join("needle" for _ in range(_DEFAULT_MAX_MATCHES + 25)), encoding="utf-8")

        result = await read_file(agent="test_agent", path=str(target), mode="search", search="needle", format="structured")

        assert result["ok"] is True
        assert len(result["matches"]) == _DEFAULT_MAX_MATCHES
        assert result["max_matches"] == _DEFAULT_MAX_MATCHES
        assert "reminders" in result
        assert isinstance(result["reminders"], list)
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_invalid_regex_returns_error(tmp_path):
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "sample.txt"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

        result = await read_file(agent="test_agent", path=str(target), mode="search", search="(", search_mode="regex", format="structured")

        assert result["ok"] is False
        assert result["error"] == "invalid regex"
        assert "reminders" in result
        assert isinstance(result["reminders"], list)
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_full_mode_small_file(tmp_path):
    """Test mode='full' reads entire small file."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "small.txt"
        content = "\n".join(f"line {i}" for i in range(100))
        target.write_text(content, encoding="utf-8")

        result = await read_file(agent="test_agent", path=str(target), mode="full", format="structured")

        assert result["ok"] is True
        assert result["mode"] == "full"
        assert result["full_file"] is True
        assert "chunk" in result
        assert result["chunk"]["line_start"] == 1
        assert result["chunk"]["line_end"] == 100
        assert "line 0" in result["chunk"]["content"]
        assert "line 99" in result["chunk"]["content"]
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_full_mode_large_file_auto_truncated(tmp_path):
    """Test mode='full' auto-truncates large files (>20k tokens)."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "large.txt"
        # Create file that exceeds token limit
        # Each line is ~60 chars ≈ 15 tokens, so 2000 lines ≈ 30k tokens
        content = "\n".join(f"line {i:04d} - padding to make lines longer for token testing here" for i in range(2000))
        target.write_text(content, encoding="utf-8")

        result = await read_file(agent="test_agent", path=str(target), mode="full", format="structured")

        assert result["ok"] is True
        assert result["mode"] == "full"
        assert result["full_file"] is False
        assert result["auto_truncated"] is True
        assert "lines_shown" in result
        assert "total_lines" in result
        assert result["total_lines"] == 2000
        assert result["lines_shown"] < result["total_lines"]  # Should have truncated
        assert "tokens_shown" in result
        assert result["tokens_shown"] <= _FULL_MODE_TOKEN_LIMIT
        assert "large_file_warning" in result
        assert "remaining_lines" in result["large_file_warning"]
        # Should have truncated to fit token limit
        assert result["chunk"]["line_start"] == 1
        assert result["chunk"]["line_end"] == result["lines_shown"]
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_full_mode_include_full_content_bypasses_truncation(tmp_path):
    """Test mode='full' with include_full_content=True returns entire file without truncation."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "large_full.txt"
        # Create file that exceeds token limit
        content = "\n".join(f"line {i:04d} - padding to make lines longer for token testing here" for i in range(2000))
        target.write_text(content, encoding="utf-8")

        result = await read_file(
            agent="test_agent",
            path=str(target),
            mode="full",
            format="structured",
            include_full_content=True  # Bypass truncation
        )

        assert result["ok"] is True
        assert result["mode"] == "full"
        assert result["full_file"] is True  # Should be True because we bypassed truncation
        assert result.get("auto_truncated") is not True  # Should NOT be truncated
        assert result.get("include_full_content") is True  # Track that bypass was used
        assert "full_content_warning" in result  # Should have warning since it exceeds normal limit
        assert "chunk" in result
        # Should have all 2000 lines
        assert result["chunk"]["line_end"] == 2000
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_unsupported_mode_error_includes_valid_modes(tmp_path):
    """Test unsupported mode error includes helpful info."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.txt"
        target.write_text("test content", encoding="utf-8")

        result = await read_file(agent="test_agent", path=str(target), mode="invalid_mode", format="structured")

        assert result["ok"] is False
        assert "Unsupported read mode" in result["error"]
        assert "valid_modes" in result
        assert "full" in result["valid_modes"]
        assert "page" in result["valid_modes"]
        assert "mode_descriptions" in result
        assert "suggestion" in result
    finally:
        server_module.router_context_manager.reset(token)
