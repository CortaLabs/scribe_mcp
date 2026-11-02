import json
import hashlib
import builtins
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from scribe_mcp import server as server_module
import scribe_mcp.tools.read_file as read_file_module
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import _DEFAULT_MAX_MATCHES, _FULL_MODE_TOKEN_LIMIT, read_file
import scribe_mcp.utils.tokens as token_utils
from test_estimator import _deny_upstream, _run_native_oracle, _NATIVE_CORPUS, _resource_streams

pytestmark = pytest.mark.usefixtures("test_agent")


@pytest.fixture(scope="module")
def shared_native_reader_encoder():
    """Native expected-value object, never registered or injected into subject."""
    import tiktoken
    with pytest.MonkeyPatch.context() as patch:
        _deny_upstream(patch)
        encoder = token_utils._load_packaged_encoder("cl100k_base", tiktoken)
    assert isinstance(encoder, tiktoken.Encoding)
    return encoder


@pytest.fixture(autouse=True)
def native_reader_encoder(monkeypatch, shared_native_reader_encoder):
    """Every subject first-use must construct independently from packaged bytes."""
    _, seen = _deny_upstream(monkeypatch)
    monkeypatch.setattr(read_file_module, "_tiktoken_encoder", None)
    yield shared_native_reader_encoder
    assert seen == []


@pytest.mark.regression
@pytest.mark.parametrize("text", ["ordinary alpha beta", "café 漢字 😀\n", "<|endoftext|>", "<|fim_prefix|>文<|fim_middle|>😀<|fim_suffix|><|endofprompt|>"])
def test_reader_counts_literal_data_with_native_encoder(native_reader_encoder, text, test_agent):
    assert read_file_module._count_tokens(text) == len(native_reader_encoder.encode_ordinary(text))


@pytest.mark.core
@pytest.mark.regression
def test_reader_packaged_native_matches_independent_oracle(tmp_path, monkeypatch):
    import tiktoken
    oracle = _run_native_oracle(tmp_path / "oracle-cache")["encodings"]["cl100k_base"]
    original = token_utils._load_packaged_encoder
    calls = []
    def construct(name, module):
        calls.append(name)
        return original(name, module)
    monkeypatch.setattr(token_utils, "_load_packaged_encoder", construct)
    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(pool.map(read_file_module._count_tokens, [_NATIVE_CORPUS[1]] * 16))
    assert counts == [len(oracle["ids"][1])] * 16
    assert calls == ["cl100k_base"]
    encoder = read_file_module._get_tiktoken_encoder()
    assert isinstance(encoder, tiktoken.Encoding)
    assert read_file_module._get_tiktoken_encoder() is encoder
    for text, ids in zip(_NATIVE_CORPUS, oracle["ids"]):
        assert encoder.encode(text, disallowed_special=()) == ids
        assert read_file_module._count_tokens(text) == len(ids)
    assert encoder.encode("|".join(oracle["specials"]), disallowed_special=()) == oracle["literal_specials"]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("error", [ImportError, KeyError, FileNotFoundError, ValueError])
def test_reader_adapter_failure_retries_then_publishes_once(monkeypatch, error):
    import tiktoken
    original = token_utils._load_packaged_encoder
    calls = []
    def transient(name, module):
        calls.append(name)
        if len(calls) <= 2:
            raise error("reader adapter failure")
        return original(name, module)
    monkeypatch.setattr(token_utils, "_load_packaged_encoder", transient)
    for _ in range(2):
        with pytest.raises(error, match="reader adapter failure"):
            read_file_module._count_tokens("alpha beta gamma")
        assert read_file_module._tiktoken_encoder is None
    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(pool.map(read_file_module._count_tokens, ["alpha beta gamma"] * 16))
    assert counts == [3] * 16
    assert len(calls) == 3
    assert isinstance(read_file_module._tiktoken_encoder, tiktoken.Encoding)


@pytest.mark.core
@pytest.mark.regression
def test_reader_only_import_unavailable_is_cheap_and_retryable(monkeypatch):
    original_import = builtins.__import__
    calls = []
    def unavailable(name, *args, **kwargs):
        if name == "tiktoken":
            calls.append(name)
            raise ImportError("unavailable")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    assert read_file_module._count_tokens("alpha beta gamma") == 4
    assert read_file_module._count_tokens("alpha beta gamma") == 4
    assert calls == ["tiktoken"] * 2
    assert read_file_module._tiktoken_encoder is None
    monkeypatch.setattr(builtins, "__import__", original_import)
    assert read_file_module._count_tokens("alpha beta gamma") == 3


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("damage", ["missing", "flip", "truncate", "append", "crlf"])
def test_reader_resource_failures_precede_parser_and_recover(monkeypatch, damage):
    filename = "cl100k_base.tiktoken"
    data = (Path(token_utils.__file__).parent / "token_data" / filename).read_bytes()
    changed = {"missing": None, "flip": bytes([data[0] ^ 1]) + data[1:], "truncate": data[:-1], "append": data + b"x", "crlf": data.replace(b"\n", b"\r\n")}[damage]
    with pytest.MonkeyPatch.context() as patch:
        _resource_streams(patch, {filename: changed})
        patch.setattr(token_utils, "_parse_token_ranks", lambda *a: pytest.fail("corrupt resource parsed"))
        for _ in range(2):
            with pytest.raises(FileNotFoundError if damage == "missing" else ValueError, match=filename):
                read_file_module._count_tokens("alpha beta gamma")
            assert read_file_module._tiktoken_encoder is None
    assert read_file_module._count_tokens("alpha beta gamma") == 3


@pytest.mark.core
@pytest.mark.regression
def test_reader_wrong_version_precedes_resource_io(monkeypatch):
    import tiktoken
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tiktoken, "__version__", "0.14.1")
        patch.setattr(token_utils, "_read_token_resource", lambda *a: pytest.fail("unsupported version read resources"))
        with pytest.raises(RuntimeError, match="0.14.0"):
            read_file_module._count_tokens("alpha beta gamma")
        assert read_file_module._tiktoken_encoder is None
    assert read_file_module._count_tokens("alpha beta gamma") == 3


@pytest.mark.core
@pytest.mark.regression
def test_reader_import_and_estimator_cheap_path_do_not_read_token_resources():
    script = r'''
import os, sys
def audit(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if "/token_data/" in path or "/.scribe_metrics/" in path:
            raise RuntimeError("lazy path opened tokenizer resource/metrics")
    if event.startswith("socket.") and event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("lazy path attempted network")
sys.addaudithook(audit)
import scribe_mcp.tools.read_file as reader
from scribe_mcp.utils.tokens import TokenEstimator
estimator = TokenEstimator()
if estimator.estimate_tokens("alpha beta gamma", exact=False) != 4:
    raise RuntimeError("cheap count changed")
if "tiktoken" in sys.modules or reader._tiktoken_encoder is not None or estimator._encoder_initialized:
    raise RuntimeError("lazy path initialized tokenizer")
print("reader/constructor/cheap: tokenizer and resource lazy")
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "reader/constructor/cheap: tokenizer and resource lazy"


@pytest.mark.regression
def test_reader_preserves_native_reserved_token_default(native_reader_encoder, test_agent):
    # Reader policy must not change the engine/public estimator's default policy.
    with pytest.raises(ValueError, match="disallowed special token"):
        native_reader_encoder.encode("<|endoftext|>")


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("character,cut", [("é", 1), ("漢", 1), ("漢", 2), ("😀", 1), ("😀", 2), ("😀", 3)])
async def test_full_read_utf8_sample_boundary_and_truncated_eof(tmp_path, character, cut, test_agent):
    token = _install_execution_context(tmp_path)
    try:
        encoded = character.encode("utf-8")
        prefix = b"a" * (4096 - cut)
        for label, raw, encoding in [
            ("sample", prefix + encoded + b"tail", "utf-8"),
            ("exact-eof", prefix + encoded[:cut], "latin-1"),
            ("short-eof", encoded[:cut], "latin-1"),
        ]:
            target = tmp_path / f"{label}.txt"
            target.write_bytes(raw)
            before = target.stat().st_mtime_ns
            result = await read_file(agent=test_agent, path=str(target), mode="full", include_full_content=True, format="structured")
            assert result["ok"] is True
            assert result["scan"]["encoding"] == encoding
            assert result["scan"]["sha256"] == hashlib.sha256(raw).hexdigest()
            assert result["chunk"]["content"].encode(encoding) == raw
            assert target.read_bytes() == raw
            assert target.stat().st_mtime_ns == before
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.regression
@pytest.mark.parametrize("raw,encoding", [
    (b"plain ascii", "utf-8"),
    ("café 漢字 😀".encode("utf-8"), "utf-8"),
    (b"a" * 4094 + "é".encode("utf-8"), "utf-8"),
    (b"caf\xe9", "latin-1"),
    (b"a" * 4094 + b"\xc3(" + b"tail", "latin-1"),
    (b"a" * 4095 + b"\xff" + b"tail", "latin-1"),
], ids=["ascii", "unicode", "complete-exact-eof", "latin1", "malformed", "invalid-boundary"])
def test_reader_encoding_controls(tmp_path, raw, encoding, test_agent):
    target = tmp_path / "encoding.txt"
    target.write_bytes(raw)
    assert read_file_module._scan_file(target)["encoding"] == encoding


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("text,shown", [
    ("word " * 13000, 0),
    ("漢😀" * 5000, 0),
    ("\n\n" + "word " * 13000 + "\ntail", 2),
    ("short\n" + "word " * 13000 + "\ntail", 1),
    ("<|endoftext|>😀" * 3000, 0),
], ids=["ascii-first-line", "unicode-first-line", "blank-prefix", "short-prefix", "reserved-first-line"])
async def test_full_read_native_budget_and_explicit_complete_bytes(tmp_path, native_reader_encoder, text, shown, test_agent):
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "oversized.txt"
        raw = text.encode("utf-8")
        target.write_bytes(raw)
        before = target.stat()
        total = len(text.splitlines())
        assert len(native_reader_encoder.encode_ordinary(text)) > _FULL_MODE_TOKEN_LIMIT
        result = await read_file(agent=test_agent, path=str(target), mode="full", format="structured")
        assert result["ok"] is True
        assert result["full_file"] is False
        assert result["auto_truncated"] is True
        assert result["lines_shown"] == shown
        assert result["total_lines"] == total
        chunk = result["chunk"]
        assert chunk["content"] == "".join(text.splitlines(keepends=True)[:shown])
        assert chunk["line_start"] == 1
        assert chunk["line_end"] == shown
        assert chunk["byte_start"] == 0
        assert chunk["byte_end"] == len(chunk["content"].encode("utf-8"))
        assert result["tokens_shown"] == len(native_reader_encoder.encode_ordinary(chunk["content"]))
        assert result["tokens_shown"] <= result["token_limit"] == _FULL_MODE_TOKEN_LIMIT
        warning = result["large_file_warning"]
        assert warning["remaining_lines"] == total - shown
        assert f"start_line={shown + 1}" in warning["examples"][0]
        complete = await read_file(agent=test_agent, path=str(target), mode="full", include_full_content=True, format="structured")
        assert complete["ok"] is True
        assert complete["full_file"] is True
        assert complete["include_full_content"] is True
        assert complete.get("auto_truncated") is not True
        assert complete["chunk"]["content"].encode("utf-8") == raw
        assert complete["token_count"] == len(native_reader_encoder.encode_ordinary(text))
        assert "full_content_warning" in complete
        assert result["scan"]["sha256"] == complete["scan"]["sha256"] == hashlib.sha256(raw).hexdigest()
        assert target.read_bytes() == raw
        assert target.stat().st_mtime_ns == before.st_mtime_ns
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_full_read_native_reserved_literals(tmp_path, native_reader_encoder, explicit, test_agent):
    token = _install_execution_context(tmp_path)
    try:
        text = "ordinary café 漢字 😀\n<|endoftext|> <|fim_prefix|> <|fim_middle|> <|fim_suffix|> <|endofprompt|>\n"
        target = tmp_path / "literal.txt"
        target.write_text(text, encoding="utf-8")
        result = await read_file(agent=test_agent, path=str(target), mode="full", include_full_content=explicit, format="structured")
        assert result["ok"] is True
        assert result["full_file"] is True
        assert result["chunk"]["content"] == text
        assert result["token_count"] == len(native_reader_encoder.encode_ordinary(text))
        assert target.read_text(encoding="utf-8") == text
    finally:
        server_module.router_context_manager.reset(token)


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
