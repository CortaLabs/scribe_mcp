import json
from dataclasses import replace

import pytest

from scribe_mcp import server as server_module
import scribe_mcp.tools.read_file as read_file_module
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


def _set_transport_policy(policy: dict[str, object]) -> object:
    old_policy = getattr(server_module.app.state, "transport_policy", None)
    server_module.app.state.transport_policy = policy
    return old_policy


def _restore_transport_policy(old_policy: object) -> None:
    if old_policy is None:
        try:
            delattr(server_module.app.state, "transport_policy")
        except AttributeError:
            pass
        return
    server_module.app.state.transport_policy = old_policy


def _transport_policy(
    *,
    transport: str = "stdio",
    bind_host: str = "stdio",
    network_exposed: bool = False,
    auth_required: bool = False,
    auth_configured: bool = False,
    allow_outside_repo_reads: bool = False,
) -> dict[str, object]:
    return {
        "transport": transport,
        "bind_host": bind_host,
        "port": 8200,
        "network_exposed": network_exposed,
        "auth_required": auth_required,
        "auth_configured": auth_configured,
        "allow_outside_repo_reads": allow_outside_repo_reads,
    }


def _override_read_file_settings(monkeypatch: pytest.MonkeyPatch, **changes) -> None:
    monkeypatch.setattr(
        read_file_module,
        "settings",
        replace(read_file_module.settings, **changes),
    )


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


# ---------------------------------------------------------------------------
# Security: Path Traversal Tests (Task 2.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_blocks_dotdot_path_escape(tmp_path):
    """Verify that ../../etc/passwd style paths are blocked."""
    token = _install_execution_context(tmp_path)
    try:
        # Create a file inside the repo
        target = tmp_path / "safe.txt"
        target.write_text("safe content", encoding="utf-8")

        # Attempt to escape using ..
        result = await read_file(
            agent="test_agent",
            path="../../etc/passwd",
            format="structured",
        )
        assert result["ok"] is False
        assert "denied" in result.get("error", "") or "boundary" in str(result).lower()
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_blocks_symlink_escape(tmp_path):
    """Verify that symlinks pointing outside the repo are blocked."""
    import os

    token = _install_execution_context(tmp_path)
    try:
        # Create a symlink inside the repo that points outside
        symlink_path = tmp_path / "escape_link"
        try:
            os.symlink("/etc/hostname", str(symlink_path))
        except OSError:
            pytest.skip("Cannot create symlinks on this platform")

        result = await read_file(
            agent="test_agent",
            path="escape_link",
            format="structured",
        )
        assert result["ok"] is False
        reason = result.get("reason", "")
        error = result.get("error", "")
        assert "symlink_escape_blocked" in reason or "denied" in error or "denylist_match" in reason
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_allows_normal_relative_paths(tmp_path):
    """Verify normal relative paths within the repo still work."""
    token = _install_execution_context(tmp_path)
    try:
        subdir = tmp_path / "src"
        subdir.mkdir()
        target = subdir / "module.py"
        target.write_text("# test module", encoding="utf-8")

        result = await read_file(
            agent="test_agent",
            path="src/module.py",
            mode="full",
            format="structured",
        )
        assert result["ok"] is True
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_allows_requested_outside_repo_reads_for_trusted_stdio(
    tmp_path,
    monkeypatch,
):
    token = _install_execution_context(tmp_path)
    old_policy = _set_transport_policy(_transport_policy())
    outside_file = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside_file.write_text("trusted stdio outside repo", encoding="utf-8")
    _override_read_file_settings(monkeypatch, force_disable_outside_repo_reads=False)
    try:
        result = await read_file(
            agent="test_agent",
            path=str(outside_file),
            mode="full",
            allow_outside_repo=True,
            format="structured",
        )

        assert result["ok"] is True
        assert "trusted stdio outside repo" in result["chunk"]["content"]
    finally:
        _restore_transport_policy(old_policy)
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_global_force_disable_beats_trusted_stdio_default_allow(
    tmp_path,
    monkeypatch,
):
    token = _install_execution_context(tmp_path)
    old_policy = _set_transport_policy(_transport_policy())
    outside_file = tmp_path.parent / f"{tmp_path.name}-disabled.txt"
    outside_file.write_text("force disabled", encoding="utf-8")
    _override_read_file_settings(monkeypatch, force_disable_outside_repo_reads=True)
    try:
        result = await read_file(
            agent="test_agent",
            path=str(outside_file),
            mode="full",
            allow_outside_repo=True,
            format="structured",
        )

        assert result["ok"] is False
        assert result["reason"] == "outside_repo_reads_disabled_by_global_policy"
    finally:
        _restore_transport_policy(old_policy)
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_frontmatter_datetime_values_are_json_safe(tmp_path):
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "dated_frontmatter.md"
        target.write_text(
            "---\n"
            "updated_utc: 2026-02-11 10:04:00+00:00\n"
            "release_date: 2026-02-11\n"
            "nested:\n"
            "  emitted_at: 2026-02-11 10:05:00+00:00\n"
            "---\n"
            "# Heading\n",
            encoding="utf-8",
        )

        result = await read_file(
            agent="test_agent",
            path=str(target),
            mode="scan_only",
            format="structured",
        )

        assert result["ok"] is True
        frontmatter = result.get("frontmatter", {})
        assert isinstance(frontmatter.get("updated_utc"), str)
        assert isinstance(frontmatter.get("release_date"), str)
        assert isinstance(frontmatter.get("nested", {}).get("emitted_at"), str)

        # Regression guard: response payload must remain JSON serializable.
        json.dumps(result)
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
