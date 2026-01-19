#!/usr/bin/env python3
"""Tests for ExecutionContext session identity requirements."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.shared.execution_context import RouterContextManager


@pytest.mark.asyncio
async def test_execution_context_requires_session_id():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
    }
    with pytest.raises(ValueError, match="transport_session_id or session_id"):
        await router.build_execution_context(payload)


@pytest.mark.asyncio
async def test_execution_context_transport_session_id_is_stable():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "transport_session_id": "conn-1",
    }
    first = await router.build_execution_context(payload)
    second = await router.build_execution_context(payload)
    assert first.session_id == second.session_id
    assert first.transport_session_id == "conn-1"


@pytest.mark.asyncio
async def test_execution_context_accepts_explicit_session_id():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "session_id": "session-explicit",
    }
    ctx = await router.build_execution_context(payload)
    assert ctx.session_id == "session-explicit"
