"""Tests for session project caching feature."""
import pytest
from scribe_mcp.shared.execution_context import RouterContextManager


@pytest.fixture
def router_manager():
    """Create a fresh RouterContextManager for testing."""
    return RouterContextManager()


@pytest.mark.asyncio
async def test_cache_project_binding_stores_value(router_manager):
    """Test that cache_project_binding stores the value."""
    await router_manager.cache_project_binding("session_123", "my_project")
    result = await router_manager.get_cached_project("session_123")
    assert result == "my_project"


@pytest.mark.asyncio
async def test_cache_project_binding_overwrites_on_update(router_manager):
    """Test that subsequent bindings overwrite previous ones."""
    await router_manager.cache_project_binding("session_123", "project_a")
    await router_manager.cache_project_binding("session_123", "project_b")
    result = await router_manager.get_cached_project("session_123")
    assert result == "project_b"


@pytest.mark.asyncio
async def test_get_cached_project_returns_none_for_unknown(router_manager):
    """Test that unknown session returns None."""
    result = await router_manager.get_cached_project("unknown_session")
    assert result is None


@pytest.mark.asyncio
async def test_cache_project_binding_handles_none_session(router_manager):
    """Test that None session_id doesn't raise."""
    await router_manager.cache_project_binding(None, "project")
    # Should not raise, just return early


@pytest.mark.asyncio
async def test_cache_project_binding_handles_none_project(router_manager):
    """Test that None project_name doesn't raise."""
    await router_manager.cache_project_binding("session", None)
    # Should not raise, just return early
