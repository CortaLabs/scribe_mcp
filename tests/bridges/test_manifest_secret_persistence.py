"""Regression tests for bridge manifest secret persistence hardening."""

import json
import logging
import os
import tempfile

import pytest

from scribe_mcp.bridges.manifest import BridgeManifest
from scribe_mcp.bridges.plugin import BridgePlugin
from scribe_mcp.bridges.registry import BridgeRegistry
from scribe_mcp.storage.sqlite import SQLiteStorage


class CaptureSecretPlugin(BridgePlugin):
    """Bridge plugin that records runtime-resolved api_key on activation."""

    def __init__(self, manifest: BridgeManifest) -> None:
        super().__init__(manifest)
        self.seen_api_key = None

    async def on_activate(self) -> None:
        self.seen_api_key = self.manifest.api_key

    async def on_deactivate(self) -> None:
        return None

    async def health_check(self):
        return {"healthy": True}


class FailingHealthPlugin(BridgePlugin):
    """Bridge plugin with health check failure carrying secret-like text."""

    async def on_activate(self) -> None:
        return None

    async def on_deactivate(self) -> None:
        return None

    async def health_check(self):
        raise RuntimeError("health endpoint failed api_key=super-secret-token")


class FailingActivatePlugin(BridgePlugin):
    """Bridge plugin with activation failure carrying secret-like text."""

    async def on_activate(self) -> None:
        raise RuntimeError("activation failed token=activate-secret-token")

    async def on_deactivate(self) -> None:
        return None

    async def health_check(self):
        return {"healthy": True}


class FailingDeactivatePlugin(BridgePlugin):
    """Bridge plugin with deactivation failure carrying secret-like text."""

    async def on_activate(self) -> None:
        return None

    async def on_deactivate(self) -> None:
        raise RuntimeError("deactivation failed token=deactivate-secret-token")

    async def health_check(self):
        return {"healthy": True}


@pytest.fixture
def temp_db_path():
    """Create temporary SQLite path for bridge persistence tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "bridge-secret-persistence.db")


def _manifest_with_api_key(value: str) -> BridgeManifest:
    return BridgeManifest(
        bridge_id="secret_bridge",
        name="Secret Bridge",
        version="1.0.0",
        description="Bridge used to verify secret persistence",
        author="Security Tests",
        api_key=value,
    )


def test_manifest_persistence_json_keeps_reference_not_resolved_secret(monkeypatch):
    monkeypatch.setenv("BRIDGE_TEST_API_KEY", "runtime-secret-value")
    manifest = _manifest_with_api_key("${BRIDGE_TEST_API_KEY}")

    manifest.expand_env_vars()
    persisted_json = manifest.to_json(for_persistence=True)
    persisted_data = json.loads(persisted_json)

    assert manifest.api_key == "runtime-secret-value"
    assert persisted_data["api_key"] == "${BRIDGE_TEST_API_KEY}"
    assert "runtime-secret-value" not in persisted_json


@pytest.mark.asyncio
async def test_registry_persists_redacted_or_reference_only_but_runtime_resolution_works(
    monkeypatch,
    temp_db_path,
):
    monkeypatch.setenv("BRIDGE_TEST_API_KEY", "runtime-secret-value")
    manifest = _manifest_with_api_key("${BRIDGE_TEST_API_KEY}")
    manifest.expand_env_vars()

    storage = SQLiteStorage(temp_db_path)
    await storage._initialise()
    registry = BridgeRegistry(storage)

    bridge_id = await registry.register_bridge(manifest, CaptureSecretPlugin)
    persisted_bridge = await storage.fetch_bridge(bridge_id)
    persisted_manifest = json.loads(persisted_bridge["manifest_json"])

    assert persisted_manifest["api_key"] == "${BRIDGE_TEST_API_KEY}"
    assert persisted_manifest["api_key"] != "runtime-secret-value"

    await registry.activate_bridge(bridge_id)
    plugin = registry.get_bridge(bridge_id)

    assert plugin is not None
    assert plugin.seen_api_key == "runtime-secret-value"


@pytest.mark.asyncio
async def test_registry_health_check_redacts_error_in_logs_payload_and_persistence(
    temp_db_path,
    caplog,
):
    manifest = BridgeManifest(
        bridge_id="failing_health_bridge",
        name="Failing Health Bridge",
        version="1.0.0",
        description="Bridge used to verify health-check redaction",
        author="Security Tests",
    )

    storage = SQLiteStorage(temp_db_path)
    await storage._initialise()
    registry = BridgeRegistry(storage)

    bridge_id = await registry.register_bridge(manifest, FailingHealthPlugin)
    await registry.activate_bridge(bridge_id)

    caplog.set_level(logging.ERROR)
    results = await registry.health_check_all()
    persisted_bridge = await storage.fetch_bridge(bridge_id)

    assert "super-secret-token" not in results[bridge_id]["error"]
    assert results[bridge_id]["error"] == "health endpoint failed api_key=[REDACTED]"
    assert persisted_bridge is not None
    assert persisted_bridge["last_error"] == "health endpoint failed api_key=[REDACTED]"
    assert "super-secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_registry_activate_bridge_redacts_error_in_log_raise_and_persistence(
    temp_db_path,
    caplog,
):
    manifest = BridgeManifest(
        bridge_id="failing_activate_bridge",
        name="Failing Activate Bridge",
        version="1.0.0",
        description="Bridge used to verify activate redaction",
        author="Security Tests",
    )

    storage = SQLiteStorage(temp_db_path)
    await storage._initialise()
    registry = BridgeRegistry(storage)

    bridge_id = await registry.register_bridge(manifest, FailingActivatePlugin)

    caplog.set_level(logging.ERROR)
    with pytest.raises(RuntimeError, match=r"token=\[REDACTED\]"):
        await registry.activate_bridge(bridge_id)

    persisted_bridge = await storage.fetch_bridge(bridge_id)
    assert persisted_bridge is not None
    assert persisted_bridge["last_error"] == "activation failed token=[REDACTED]"
    assert "activate-secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_registry_deactivate_bridge_redacts_error_in_logs(
    temp_db_path,
    monkeypatch,
):
    manifest = BridgeManifest(
        bridge_id="failing_deactivate_bridge",
        name="Failing Deactivate Bridge",
        version="1.0.0",
        description="Bridge used to verify deactivate redaction",
        author="Security Tests",
    )

    storage = SQLiteStorage(temp_db_path)
    await storage._initialise()
    registry = BridgeRegistry(storage)

    bridge_id = await registry.register_bridge(manifest, FailingDeactivatePlugin)
    await registry.activate_bridge(bridge_id)

    captured_errors: list[str] = []

    def _capture_error(message: str, *args, **kwargs):
        rendered = message % args if args else message
        captured_errors.append(rendered)

    monkeypatch.setattr("scribe_mcp.bridges.registry.logger.error", _capture_error)
    await registry.deactivate_bridge(bridge_id)
    combined_logs = "\n".join(captured_errors)

    assert "deactivation failed token=[REDACTED]" in combined_logs
    assert "deactivate-secret-token" not in combined_logs


@pytest.mark.asyncio
async def test_registry_load_all_manifests_redacts_load_error(monkeypatch, temp_db_path):
    storage = SQLiteStorage(temp_db_path)
    await storage._initialise()
    registry = BridgeRegistry(storage)

    registry.discover_manifests = lambda: [registry._config_dir / "bad.yaml"]

    def _raise_manifest_error(_path):
        raise RuntimeError("manifest parse failed api_key=manifest-secret")

    registry.load_manifest = _raise_manifest_error
    captured_errors: list[str] = []

    def _capture_error(message: str, *args, **kwargs):
        rendered = message % args if args else message
        captured_errors.append(rendered)

    monkeypatch.setattr("scribe_mcp.bridges.registry.logger.error", _capture_error)
    manifests = await registry.load_all_manifests()
    combined_logs = "\n".join(captured_errors)

    assert manifests == []
    assert "manifest parse failed api_key=[REDACTED]" in combined_logs
    assert "manifest-secret" not in combined_logs
