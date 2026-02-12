#!/usr/bin/env python3
"""
Bridge Registry System - Comprehensive Test Suite

Tests for Phases 1-4:
- Phase 1: Core Bridge Registry (manifest, plugin, registry, storage)
- Phase 2: Bridge Hooks (API, policy, hook manager, security)
- Phase 3: Bridge-Managed Projects (namespacing, ownership, access control)
- Phase 4: Tool Extension (wrapper, registry, custom tools)
"""

import asyncio
import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone

from scribe_mcp.bridges.manifest import (
    BridgeManifest,
    BridgeState,
    LogTypeConfig,
    HookConfig,
    BridgeProjectConfig,
    BridgeValidationConfig,
)
from scribe_mcp.bridges.plugin import BridgePlugin
from scribe_mcp.bridges.registry import BridgeRegistry
from scribe_mcp.bridges.api import BridgeToScribeAPI
from scribe_mcp.bridges.policy import BridgePolicyPlugin
from scribe_mcp.bridges.hooks import BridgeHookManager, get_hook_manager
from scribe_mcp.bridges.security import BridgeSecurityManager
from scribe_mcp.bridges.tools import BridgeToolWrapper, BridgeToolRegistry, get_tool_registry
from scribe_mcp.storage.sqlite import SQLiteStorage


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

class DummyBridgePlugin(BridgePlugin):
    """Simple test bridge implementation."""

    def __init__(self, manifest: BridgeManifest):
        super().__init__(manifest)
        self.pre_append_called = False
        self.post_append_called = False
        self.pre_rotate_called = False
        self.post_rotate_called = False

    async def on_activate(self) -> None:
        """Activation hook."""
        pass

    async def on_deactivate(self) -> None:
        """Deactivation hook."""
        pass

    async def health_check(self) -> dict:
        """Health check."""
        return {
            "healthy": True,
            "message": "Test bridge operational",
            "latency_ms": 5
        }

    async def pre_append(self, entry_data: dict) -> dict:
        """Modify entry before append."""
        self.pre_append_called = True
        entry_data["meta"] = entry_data.get("meta", {})
        entry_data["meta"]["modified_by_bridge"] = self.bridge_id
        return entry_data

    async def post_append(self, entry_data: dict) -> None:
        """Notify after append."""
        self.post_append_called = True

    async def pre_rotate(self, log_type: str) -> None:
        """Called before rotation."""
        self.pre_rotate_called = True

    async def post_rotate(self, log_type: str, archive_path: str) -> None:
        """Called after rotation."""
        self.post_rotate_called = True


@pytest.fixture
def basic_manifest():
    """Create a basic bridge manifest for testing."""
    return BridgeManifest(
        bridge_id="test_bridge",
        name="Test Bridge",
        version="1.0.0",
        description="A test bridge",
        author="Test Author"
    )


@pytest.fixture
def full_manifest():
    """Create a full-featured bridge manifest for testing."""
    return BridgeManifest(
        bridge_id="full_test_bridge",
        name="Full Test Bridge",
        version="1.0.0",
        description="A fully-configured test bridge",
        author="Test Author",
        permissions=["read:all_projects", "write:own_projects", "create:projects"],
        hooks={
            "pre_append": HookConfig(hook_name="pre_append", timeout_ms=1000, critical=False),
            "post_append": HookConfig(hook_name="post_append", timeout_ms=1000, critical=False),
            "pre_rotate": HookConfig(hook_name="pre_rotate", timeout_ms=1000, critical=False),
            "post_rotate": HookConfig(hook_name="post_rotate", timeout_ms=1000, critical=False),
        },
        project_config=BridgeProjectConfig(
            can_create_projects=True,
            project_prefix="test_",
            auto_tag=["automated", "test-bridge"]
        ),
        validation=BridgeValidationConfig(mode="lenient")
    )


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


# =============================================================================
# PHASE 1: Core Bridge Registry Tests
# =============================================================================

class TestPhase1CoreRegistry:
    """Phase 1: Core Bridge Registry tests."""

    def test_manifest_creation(self, basic_manifest):
        """Test basic manifest creation."""
        assert basic_manifest.bridge_id == "test_bridge"
        assert basic_manifest.name == "Test Bridge"
        assert basic_manifest.version == "1.0.0"

    def test_manifest_validation_success(self, basic_manifest):
        """Test manifest validation passes for valid manifest."""
        errors = basic_manifest.validate()
        assert len(errors) == 0

    def test_manifest_validation_fails_empty_id(self):
        """Test manifest validation fails without bridge_id."""
        manifest = BridgeManifest(
            bridge_id="",
            name="Test",
            version="1.0.0",
            description="Test",
            author="Test"
        )
        errors = manifest.validate()
        assert any("bridge_id" in e for e in errors)

    def test_manifest_validation_fails_invalid_chars(self):
        """Test manifest validation fails with invalid characters."""
        manifest = BridgeManifest(
            bridge_id="test@bridge!",
            name="Test",
            version="1.0.0",
            description="Test",
            author="Test"
        )
        errors = manifest.validate()
        assert any("alphanumeric" in e for e in errors)

    def test_manifest_to_json(self, basic_manifest):
        """Test manifest JSON serialization."""
        json_str = basic_manifest.to_json()
        assert "test_bridge" in json_str
        assert "Test Bridge" in json_str

    def test_manifest_from_dict(self):
        """Test manifest creation from dictionary."""
        data = {
            "bridge_id": "dict_bridge",
            "name": "Dict Bridge",
            "version": "2.0.0",
            "description": "Created from dict",
            "author": "Test"
        }
        manifest = BridgeManifest.from_dict(data)
        assert manifest.bridge_id == "dict_bridge"
        assert manifest.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_registry_register_bridge(self, basic_manifest, temp_db_path):
        """Test bridge registration."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)
        bridge_id = await registry.register_bridge(basic_manifest, DummyBridgePlugin)
        assert bridge_id == "test_bridge"
        assert registry.get_manifest(bridge_id) is not None

    @pytest.mark.asyncio
    async def test_registry_activate_bridge(self, basic_manifest, temp_db_path):
        """Test bridge activation."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)
        await registry.register_bridge(basic_manifest, DummyBridgePlugin)
        await registry.activate_bridge("test_bridge")

        bridge = registry.get_bridge("test_bridge")
        assert bridge.state == BridgeState.ACTIVE

    @pytest.mark.asyncio
    async def test_registry_deactivate_bridge(self, basic_manifest, temp_db_path):
        """Test bridge deactivation."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)
        await registry.register_bridge(basic_manifest, DummyBridgePlugin)
        await registry.activate_bridge("test_bridge")
        await registry.deactivate_bridge("test_bridge")

        bridge = registry.get_bridge("test_bridge")
        assert bridge.state == BridgeState.INACTIVE

    @pytest.mark.asyncio
    async def test_registry_unregister_bridge(self, basic_manifest, temp_db_path):
        """Test bridge unregistration."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)
        await registry.register_bridge(basic_manifest, DummyBridgePlugin)
        await registry.unregister_bridge("test_bridge")

        assert registry.get_manifest("test_bridge") is None

    @pytest.mark.asyncio
    async def test_registry_list_bridges(self, basic_manifest, temp_db_path):
        """Test listing bridges."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)
        await registry.register_bridge(basic_manifest, DummyBridgePlugin)

        bridges = await registry.list_bridges()
        assert len(bridges) == 1
        assert bridges[0]["bridge_id"] == "test_bridge"

    @pytest.mark.asyncio
    async def test_registry_health_check(self, basic_manifest, temp_db_path):
        """Test health check execution."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)
        await registry.register_bridge(basic_manifest, DummyBridgePlugin)
        await registry.activate_bridge("test_bridge")

        results = await registry.health_check_all()
        assert "test_bridge" in results
        assert results["test_bridge"]["healthy"] is True


# =============================================================================
# PHASE 2: Bridge Hooks Tests
# =============================================================================

class TestPhase2BridgeHooks:
    """Phase 2: Bridge Hooks tests."""

    def test_policy_read_permission(self):
        """Test policy read permission checking."""
        manifest = BridgeManifest(
            bridge_id="policy_bridge",
            name="Policy Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["read:all_projects"]
        )
        policy = BridgePolicyPlugin(manifest)
        assert policy.can_read_entries("any_project") is True

    def test_policy_write_denied_without_permission(self):
        """Test policy denies write without permission."""
        manifest = BridgeManifest(
            bridge_id="readonly_bridge",
            name="Readonly Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["read:all_projects"]  # No write permission
        )
        policy = BridgePolicyPlugin(manifest)
        assert policy.can_append_entry("any_project") is False

    def test_policy_create_denied_without_permission(self):
        """Test policy denies create without permission."""
        manifest = BridgeManifest(
            bridge_id="no_create_bridge",
            name="No Create Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["read:all_projects"],
            project_config=BridgeProjectConfig(can_create_projects=False)
        )
        policy = BridgePolicyPlugin(manifest)
        assert policy.can_create_projects() is False

    def test_policy_log_type_validation(self):
        """Test policy validates log types."""
        manifest = BridgeManifest(
            bridge_id="log_bridge",
            name="Log Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=[]
        )
        policy = BridgePolicyPlugin(manifest)
        assert policy._can_use_log_type("progress") is True
        assert policy._can_use_log_type("invalid_log_type") is False

    @pytest.mark.asyncio
    async def test_hook_manager_pre_append(self, full_manifest):
        """Test hook manager pre_append execution."""
        bridge = DummyBridgePlugin(full_manifest)
        bridge.state = BridgeState.ACTIVE

        manager = BridgeHookManager()
        manager.register_bridge(bridge)

        entry_data = {"message": "Test", "meta": {}}
        result = await manager.execute_pre_append(entry_data)

        assert result["meta"].get("modified_by_bridge") == full_manifest.bridge_id
        assert bridge.pre_append_called is True

    @pytest.mark.asyncio
    async def test_hook_manager_post_append(self, full_manifest):
        """Test hook manager post_append execution."""
        bridge = DummyBridgePlugin(full_manifest)
        bridge.state = BridgeState.ACTIVE

        manager = BridgeHookManager()
        manager.register_bridge(bridge)

        await manager.execute_post_append({"message": "Test"})
        assert bridge.post_append_called is True

    @pytest.mark.asyncio
    async def test_hook_manager_pre_rotate(self, full_manifest):
        """Test hook manager pre_rotate execution."""
        bridge = DummyBridgePlugin(full_manifest)
        bridge.state = BridgeState.ACTIVE

        manager = BridgeHookManager()
        manager.register_bridge(bridge)

        await manager.execute_pre_rotate("progress")
        assert bridge.pre_rotate_called is True

    @pytest.mark.asyncio
    async def test_hook_manager_post_rotate(self, full_manifest):
        """Test hook manager post_rotate execution."""
        bridge = DummyBridgePlugin(full_manifest)
        bridge.state = BridgeState.ACTIVE

        manager = BridgeHookManager()
        manager.register_bridge(bridge)

        await manager.execute_post_rotate("progress", "/tmp/archive.md")
        assert bridge.post_rotate_called is True

    @pytest.mark.asyncio
    async def test_hook_manager_unregister(self, full_manifest):
        """Test hook manager unregistration."""
        bridge = DummyBridgePlugin(full_manifest)
        bridge.state = BridgeState.ACTIVE

        manager = BridgeHookManager()
        manager.register_bridge(bridge)
        manager.unregister_bridge(full_manifest.bridge_id)

        # Pre-append should not modify since bridge is unregistered
        entry_data = {"message": "Test", "meta": {}}
        result = await manager.execute_pre_append(entry_data)
        assert "modified_by_bridge" not in result.get("meta", {})

    def test_global_hook_manager_singleton(self):
        """Test global hook manager is singleton."""
        manager1 = get_hook_manager()
        manager2 = get_hook_manager()
        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_security_timeout_enforcement(self):
        """Test security manager timeout enforcement."""
        async def slow_function():
            await asyncio.sleep(2.0)
            return "completed"

        with pytest.raises(asyncio.TimeoutError):
            await BridgeSecurityManager.execute_with_timeout(slow_function, timeout_ms=100)

    @pytest.mark.asyncio
    async def test_security_error_isolation(self):
        """Test security manager error isolation."""
        @BridgeSecurityManager.isolate_errors
        async def failing_function():
            raise ValueError("Test error")

        result = await failing_function()
        assert result is None

    @pytest.mark.asyncio
    async def test_security_safe_execute(self):
        """Test security manager safe execute."""
        async def slow_function():
            await asyncio.sleep(2.0)
            return "completed"

        result = await BridgeSecurityManager.safe_execute(
            slow_function, timeout_ms=100, default="default_value"
        )
        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_api_structure(self, full_manifest):
        """Test API structure and initialization."""
        class MockStorage:
            async def insert_entry(self, **kwargs):
                return {"ok": True}
            async def upsert_project(self, **kwargs):
                return {"ok": True}
            async def fetch_recent_entries(self, project_name, limit, filters):
                return []

        storage = MockStorage()
        policy = BridgePolicyPlugin(full_manifest)
        api = BridgeToScribeAPI(full_manifest.bridge_id, full_manifest, storage, policy)

        assert api.bridge_id == full_manifest.bridge_id


# =============================================================================
# PHASE 3: Bridge-Managed Projects Tests
# =============================================================================

class TestPhase3BridgeManagedProjects:
    """Phase 3: Bridge-Managed Projects tests."""

    @pytest.mark.asyncio
    async def test_project_creation_with_prefix(self, temp_db_path):
        """Test project creation applies prefix."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        manifest = BridgeManifest(
            bridge_id="prefix_bridge",
            name="Prefix Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="pfx_",
                auto_tag=["auto-tagged"]
            )
        )

        policy = BridgePolicyPlugin(manifest, storage)
        api = BridgeToScribeAPI(manifest.bridge_id, manifest, storage, policy)

        result = await api.create_project("myproject", description="Test")

        assert result["ok"] is True
        assert result["project_name"] == "pfx_myproject"
        assert result["original_name"] == "myproject"
        assert result["bridge_managed"] is True

    @pytest.mark.asyncio
    async def test_project_auto_tags(self, temp_db_path):
        """Test project creation applies auto-tags."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        manifest = BridgeManifest(
            bridge_id="tag_bridge",
            name="Tag Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="tag_",
                auto_tag=["automated", "test-tag"]
            )
        )

        policy = BridgePolicyPlugin(manifest, storage)
        api = BridgeToScribeAPI(manifest.bridge_id, manifest, storage, policy)

        result = await api.create_project("tagged", description="Test")

        assert "automated" in result["tags"]
        assert "test-tag" in result["tags"]
        assert "bridge:tag_bridge" in result["tags"]

    @pytest.mark.asyncio
    async def test_project_ownership_stored(self, temp_db_path):
        """Test project ownership is stored in database."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        manifest = BridgeManifest(
            bridge_id="owner_bridge",
            name="Owner Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="own_"
            )
        )

        policy = BridgePolicyPlugin(manifest, storage)
        api = BridgeToScribeAPI(manifest.bridge_id, manifest, storage, policy)

        await api.create_project("owned", description="Test")

        project = await storage.fetch_project("own_owned")
        assert project.bridge_id == "owner_bridge"
        assert project.bridge_managed is True

    @pytest.mark.asyncio
    async def test_owner_can_modify_own_project(self, temp_db_path):
        """Test bridge can modify its own projects."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        manifest = BridgeManifest(
            bridge_id="modify_bridge",
            name="Modify Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="mod_"
            )
        )

        policy = BridgePolicyPlugin(manifest, storage)
        api = BridgeToScribeAPI(manifest.bridge_id, manifest, storage, policy)

        await api.create_project("myproj", description="Test")

        can_modify = await policy.can_modify_project("mod_myproj")
        assert can_modify is True

    @pytest.mark.asyncio
    async def test_other_bridge_cannot_modify(self, temp_db_path):
        """Test bridge cannot modify other bridge's projects."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        # Bridge A creates project
        manifest_a = BridgeManifest(
            bridge_id="bridge_a",
            name="Bridge A",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="a_"
            )
        )

        policy_a = BridgePolicyPlugin(manifest_a, storage)
        api_a = BridgeToScribeAPI(manifest_a.bridge_id, manifest_a, storage, policy_a)
        await api_a.create_project("shared", description="Test")

        # Bridge B tries to modify
        manifest_b = BridgeManifest(
            bridge_id="bridge_b",
            name="Bridge B",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["write:own_projects"],
            project_config=BridgeProjectConfig(can_create_projects=False)
        )

        policy_b = BridgePolicyPlugin(manifest_b, storage)
        can_modify = await policy_b.can_modify_project("a_shared")
        assert can_modify is False

    @pytest.mark.asyncio
    async def test_write_all_bypasses_ownership(self, temp_db_path):
        """Test write:all_projects permission bypasses ownership."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        # Bridge A creates project
        manifest_a = BridgeManifest(
            bridge_id="bridge_a",
            name="Bridge A",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="a_"
            )
        )

        policy_a = BridgePolicyPlugin(manifest_a, storage)
        api_a = BridgeToScribeAPI(manifest_a.bridge_id, manifest_a, storage, policy_a)
        await api_a.create_project("protected", description="Test")

        # Bridge C has write:all_projects
        manifest_c = BridgeManifest(
            bridge_id="bridge_c",
            name="Bridge C (Super)",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["write:all_projects"],
            project_config=BridgeProjectConfig(can_create_projects=False)
        )

        policy_c = BridgePolicyPlugin(manifest_c, storage)
        can_modify = await policy_c.can_modify_project("a_protected")
        assert can_modify is True

    @pytest.mark.asyncio
    async def test_non_bridge_projects_accessible(self, temp_db_path):
        """Test non-bridge-managed projects accessible to all bridges."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        # Create non-bridge project directly
        await storage.upsert_project(
            name="regular_project",
            repo_root=".",
            progress_log_path=".scribe/docs/dev_plans/regular_project/PROGRESS_LOG.md"
        )

        manifest = BridgeManifest(
            bridge_id="any_bridge",
            name="Any Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["write:own_projects"],
            project_config=BridgeProjectConfig(can_create_projects=False)
        )

        policy = BridgePolicyPlugin(manifest, storage)
        can_modify = await policy.can_modify_project("regular_project")
        assert can_modify is True

    @pytest.mark.asyncio
    async def test_can_append_to_project_combines_checks(self, temp_db_path):
        """Test can_append_to_project combines log_type and ownership."""
        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()

        manifest = BridgeManifest(
            bridge_id="append_bridge",
            name="Append Bridge",
            version="1.0.0",
            description="Test",
            author="Test",
            permissions=["create:projects", "write:own_projects"],
            project_config=BridgeProjectConfig(
                can_create_projects=True,
                project_prefix="app_"
            )
        )

        policy = BridgePolicyPlugin(manifest, storage)
        api = BridgeToScribeAPI(manifest.bridge_id, manifest, storage, policy)

        await api.create_project("appendable", description="Test")

        can_append = await policy.can_append_to_project("app_appendable", "progress")
        assert can_append is True


# =============================================================================
# PHASE 4: Tool Extension Tests
# =============================================================================

class TestPhase4ToolExtension:
    """Phase 4: Tool Extension tests."""

    @pytest.mark.asyncio
    async def test_tool_wrapper_basic(self):
        """Test basic tool wrapping."""
        async def original_tool(message: str, count: int = 1) -> str:
            return f"Original: {message} x{count}"

        wrapper = BridgeToolWrapper("test_bridge", "test_tool", original_tool)
        result = await wrapper(message="Hello", count=3)

        assert "Original: Hello x3" in result

    @pytest.mark.asyncio
    async def test_tool_wrapper_pre_hook(self):
        """Test tool wrapper pre-hook modification."""
        async def original_tool(message: str, count: int = 1) -> str:
            return f"Original: {message} x{count}"

        wrapper = BridgeToolWrapper("test_bridge", "test_tool", original_tool)

        async def pre_hook(args, kwargs):
            kwargs["count"] = kwargs.get("count", 1) * 2
            return args, kwargs

        wrapper.add_pre_hook(pre_hook)
        result = await wrapper(message="Hello", count=3)

        assert "x6" in result  # count doubled

    @pytest.mark.asyncio
    async def test_tool_wrapper_post_hook(self):
        """Test tool wrapper post-hook modification."""
        async def original_tool(message: str) -> str:
            return f"Original: {message}"

        wrapper = BridgeToolWrapper("test_bridge", "test_tool", original_tool)

        async def post_hook(result, args, kwargs):
            return f"[WRAPPED] {result}"

        wrapper.add_post_hook(post_hook)
        result = await wrapper(message="Hello")

        assert result.startswith("[WRAPPED]")

    @pytest.mark.asyncio
    async def test_tool_wrapper_multiple_hooks(self):
        """Test tool wrapper with multiple hooks."""
        async def original_tool(count: int = 1) -> str:
            return f"Count: {count}"

        wrapper = BridgeToolWrapper("test_bridge", "test_tool", original_tool)

        async def pre_hook_1(args, kwargs):
            kwargs["count"] = kwargs.get("count", 1) + 1
            return args, kwargs

        async def pre_hook_2(args, kwargs):
            kwargs["count"] = kwargs.get("count", 1) * 2
            return args, kwargs

        wrapper.add_pre_hook(pre_hook_1).add_pre_hook(pre_hook_2)
        result = await wrapper(count=2)

        # (2 + 1) * 2 = 6
        assert "6" in result

    @pytest.mark.asyncio
    async def test_tool_wrapper_error_isolation(self):
        """Test tool wrapper isolates hook errors."""
        async def original_tool(message: str) -> str:
            return f"Original: {message}"

        def failing_pre_hook(args, kwargs):
            raise ValueError("Hook failure")

        wrapper = BridgeToolWrapper("test_bridge", "test_tool", original_tool)
        wrapper.add_pre_hook(failing_pre_hook)

        # Tool should still execute despite failing hook
        result = await wrapper(message="Error")
        assert "Original: Error" in result

    def test_tool_registry_wrap_tool(self):
        """Test tool registry wrap_tool."""
        async def original_tool():
            return "original"

        registry = BridgeToolRegistry()
        wrapped = registry.wrap_tool("bridge_a", "test_tool", original_tool)

        assert wrapped is not None
        assert registry.get_wrapped_tool("bridge_a", "test_tool") is wrapped

    @pytest.mark.asyncio
    async def test_tool_registry_custom_tool(self):
        """Test tool registry custom tool registration."""
        async def custom_tool(project: str) -> dict:
            return {"project": project, "custom": True}

        registry = BridgeToolRegistry()
        registry.register_custom_tool(
            "bridge_a",
            "custom_audit",
            custom_tool,
            schema={"project": "string"},
            description="Custom audit tool"
        )

        tool = registry.get_custom_tool("bridge_a", "custom_audit")
        result = await tool(project="test")

        assert result["custom"] is True

    def test_tool_registry_list_bridge_tools(self):
        """Test listing bridge tools."""
        async def tool1():
            return "1"
        async def tool2():
            return "2"

        registry = BridgeToolRegistry()
        registry.wrap_tool("bridge_a", "wrapped_tool", tool1)
        registry.register_custom_tool("bridge_a", "custom_tool", tool2)

        tools = registry.list_bridge_tools("bridge_a")

        assert "wrapped_tool" in tools["wrapped"]
        assert "custom_tool" in tools["custom"]

    def test_tool_registry_list_all_custom_tools(self):
        """Test listing all custom tools for MCP."""
        async def tool_a():
            return "a"
        async def tool_b():
            return "b"

        registry = BridgeToolRegistry()
        registry.register_custom_tool("bridge_a", "tool_a", tool_a, description="Tool A")
        registry.register_custom_tool("bridge_b", "tool_b", tool_b, description="Tool B")

        all_tools = registry.list_all_custom_tools()

        assert len(all_tools) == 2
        names = [t["full_name"] for t in all_tools]
        assert "bridge_a:tool_a" in names
        assert "bridge_b:tool_b" in names

    def test_tool_registry_unregister(self):
        """Test unregistering bridge tools."""
        async def tool():
            return "test"

        registry = BridgeToolRegistry()
        registry.wrap_tool("bridge_a", "wrapped", tool)
        registry.register_custom_tool("bridge_a", "custom", tool)

        registry.unregister_bridge_tools("bridge_a")

        tools = registry.list_bridge_tools("bridge_a")
        assert len(tools["wrapped"]) == 0
        assert len(tools["custom"]) == 0

    def test_tool_registry_get_nonexistent(self):
        """Test getting non-existent tools returns None."""
        registry = BridgeToolRegistry()

        assert registry.get_wrapped_tool("fake", "tool") is None
        assert registry.get_custom_tool("fake", "tool") is None

    def test_global_tool_registry_singleton(self):
        """Test global tool registry is singleton."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is registry2


# =============================================================================
# Phase 5: Advanced Features Tests
# =============================================================================

class TestPhase5BridgeHealthMonitor:
    """Tests for BridgeHealthMonitor (Phase 5)."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test.db")

    @pytest.fixture
    def full_manifest(self):
        """Create a full-featured bridge manifest for testing."""
        return BridgeManifest(
            bridge_id="health_test_bridge",
            name="Health Test Bridge",
            version="1.0.0",
            description="A test bridge for health monitoring",
            author="Test Author",
            permissions=["read:all_projects", "write:own_projects"],
        )

    @pytest.mark.asyncio
    async def test_health_monitor_creation(self, temp_db_path, full_manifest):
        """Test health monitor can be created."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        monitor = BridgeHealthMonitor(
            registry,
            check_interval=1.0,
            unhealthy_threshold=2,
            recovery_threshold=1
        )

        assert monitor._check_interval == 1.0
        assert monitor._unhealthy_threshold == 2
        assert monitor._recovery_threshold == 1
        assert not monitor._running

    @pytest.mark.asyncio
    async def test_health_monitor_start_stop(self, temp_db_path, full_manifest):
        """Test health monitor start and stop."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        monitor = BridgeHealthMonitor(registry, check_interval=0.1)

        await monitor.start()
        assert monitor._running

        # Give it time to run at least once
        await asyncio.sleep(0.2)

        await monitor.stop()
        assert not monitor._running

    @pytest.mark.asyncio
    async def test_health_monitor_check_single_bridge(self, temp_db_path, full_manifest):
        """Test health check on a single bridge."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(full_manifest, DummyBridgePlugin)
        await registry.activate_bridge(full_manifest.bridge_id)

        monitor = BridgeHealthMonitor(registry)

        result = await monitor.check_bridge_health(full_manifest.bridge_id)

        assert result["healthy"] is True
        assert "message" in result

    @pytest.mark.asyncio
    async def test_health_monitor_check_all_bridges(self, temp_db_path, full_manifest):
        """Test health check on all bridges."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(full_manifest, DummyBridgePlugin)
        await registry.activate_bridge(full_manifest.bridge_id)

        monitor = BridgeHealthMonitor(registry)

        results = await monitor.check_all_bridges()

        assert full_manifest.bridge_id in results
        assert results[full_manifest.bridge_id]["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_monitor_get_status(self, temp_db_path, full_manifest):
        """Test getting health monitor status."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(full_manifest, DummyBridgePlugin)
        await registry.activate_bridge(full_manifest.bridge_id)

        monitor = BridgeHealthMonitor(registry, check_interval=60.0)
        await monitor.check_all_bridges()

        status = monitor.get_status()

        assert "running" in status
        assert "check_interval_seconds" in status
        assert "last_check_time" in status
        assert "last_results" in status
        assert status["check_interval_seconds"] == 60.0

    @pytest.mark.asyncio
    async def test_health_monitor_state_transition_to_error(self, temp_db_path):
        """Test bridge transitions to ERROR after failures."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        class UnhealthyBridge(BridgePlugin):
            async def on_activate(self):
                pass

            async def on_deactivate(self):
                pass

            async def health_check(self):
                return {"healthy": False, "error": "Always unhealthy"}

        manifest = BridgeManifest(
            bridge_id="unhealthy_bridge",
            name="Unhealthy Bridge",
            version="1.0.0",
            description="Always fails health checks",
            author="Test"
        )

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(manifest, UnhealthyBridge)
        await registry.activate_bridge(manifest.bridge_id)

        # Set threshold to 2 failures
        monitor = BridgeHealthMonitor(registry, unhealthy_threshold=2)

        # First failure - still ACTIVE
        await monitor.check_bridge_health(manifest.bridge_id)
        bridge = registry.get_bridge(manifest.bridge_id)
        assert bridge.state == BridgeState.ACTIVE

        # Second failure - should transition to ERROR
        await monitor.check_bridge_health(manifest.bridge_id)
        assert bridge.state == BridgeState.ERROR

    @pytest.mark.asyncio
    async def test_health_monitor_recovery_to_active(self, temp_db_path):
        """Test bridge recovers from ERROR to ACTIVE."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        class RecoveringBridge(BridgePlugin):
            def __init__(self, manifest):
                super().__init__(manifest)
                self.fail_count = 0

            async def on_activate(self):
                pass

            async def on_deactivate(self):
                pass

            async def health_check(self):
                # Fail first two times, then recover
                self.fail_count += 1
                if self.fail_count <= 2:
                    return {"healthy": False, "error": "Temporary failure"}
                return {"healthy": True, "message": "Recovered"}

        manifest = BridgeManifest(
            bridge_id="recovering_bridge",
            name="Recovering Bridge",
            version="1.0.0",
            description="Recovers after failures",
            author="Test"
        )

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(manifest, RecoveringBridge)
        await registry.activate_bridge(manifest.bridge_id)

        monitor = BridgeHealthMonitor(
            registry,
            unhealthy_threshold=2,
            recovery_threshold=2
        )

        bridge = registry.get_bridge(manifest.bridge_id)

        # Two failures -> ERROR
        await monitor.check_bridge_health(manifest.bridge_id)
        await monitor.check_bridge_health(manifest.bridge_id)
        assert bridge.state == BridgeState.ERROR

        # First success - still ERROR
        await monitor.check_bridge_health(manifest.bridge_id)
        assert bridge.state == BridgeState.ERROR

        # Second success - should recover to ACTIVE
        await monitor.check_bridge_health(manifest.bridge_id)
        assert bridge.state == BridgeState.ACTIVE

    @pytest.mark.asyncio
    async def test_health_monitor_reset_counts(self, temp_db_path, full_manifest):
        """Test resetting failure/success counts."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(full_manifest, DummyBridgePlugin)
        await registry.activate_bridge(full_manifest.bridge_id)

        monitor = BridgeHealthMonitor(registry)
        await monitor.check_bridge_health(full_manifest.bridge_id)

        # Counts should exist
        assert full_manifest.bridge_id in monitor._success_counts

        # Reset specific bridge
        monitor.reset_counts(full_manifest.bridge_id)
        assert full_manifest.bridge_id not in monitor._success_counts

    @pytest.mark.asyncio
    async def test_health_monitor_state_change_callback(self, temp_db_path):
        """Test state change callback is invoked."""
        from scribe_mcp.bridges.health import BridgeHealthMonitor

        class AlwaysUnhealthy(BridgePlugin):
            async def on_activate(self):
                pass

            async def on_deactivate(self):
                pass

            async def health_check(self):
                return {"healthy": False}

        callback_invoked = {"called": False, "bridge_id": None, "old_state": None, "new_state": None}

        async def on_state_change(bridge_id, old_state, new_state):
            callback_invoked["called"] = True
            callback_invoked["bridge_id"] = bridge_id
            callback_invoked["old_state"] = old_state
            callback_invoked["new_state"] = new_state

        manifest = BridgeManifest(
            bridge_id="callback_test",
            name="Callback Test",
            version="1.0.0",
            description="Tests callbacks",
            author="Test"
        )

        storage = SQLiteStorage(temp_db_path)
        await storage._initialise()
        registry = BridgeRegistry(storage)

        await registry.register_bridge(manifest, AlwaysUnhealthy)
        await registry.activate_bridge(manifest.bridge_id)

        monitor = BridgeHealthMonitor(
            registry,
            unhealthy_threshold=1,
            on_state_change=on_state_change
        )

        await monitor.check_bridge_health(manifest.bridge_id)

        assert callback_invoked["called"] is True
        assert callback_invoked["bridge_id"] == manifest.bridge_id
        assert callback_invoked["new_state"] == BridgeState.ERROR

    def test_global_health_monitor_functions(self):
        """Test global health monitor getter/setter."""
        from scribe_mcp.bridges.health import (
            get_health_monitor,
            set_health_monitor,
            BridgeHealthMonitor
        )

        # Initially None or from previous tests
        original = get_health_monitor()

        # Set a mock monitor
        mock_monitor = object()
        set_health_monitor(mock_monitor)
        assert get_health_monitor() is mock_monitor

        # Restore
        set_health_monitor(original)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
