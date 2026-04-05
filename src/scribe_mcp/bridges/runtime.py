"""Shared helpers for binding bridge manifests to live runtime plugins."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Callable, Optional, Type

from .api import BridgeToScribeAPI
from .manifest import BridgeManifest
from .plugin import BridgePlugin
from .policy import BridgePolicyPlugin


@dataclass(frozen=True)
class BridgeRuntimeBinding:
    """Resolved runtime objects for one bridge registration."""

    plugin: BridgePlugin
    policy: BridgePolicyPlugin
    owner_package: str
    plugin_reference: str | None


def _resolve_plugin_target(
    manifest: BridgeManifest,
    plugin_class: Optional[Type[BridgePlugin]] = None,
):
    """Resolve the callable or class used to instantiate the bridge plugin."""
    if plugin_class is not None:
        return plugin_class, plugin_class.__module__, None

    plugin_reference = manifest.plugin_factory
    if not plugin_reference:
        raise ValueError(
            f"Bridge {manifest.bridge_id} does not define a runtime plugin. "
            "Set manifest.plugin_factory or pass plugin_class explicitly."
        )

    module_name, separator, attr_name = plugin_reference.partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(
            f"Bridge {manifest.bridge_id} plugin_factory must use 'module:attribute' syntax"
        )

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - exercised via higher-level tests
        raise ValueError(
            f"Bridge {manifest.bridge_id} could not import plugin module '{module_name}': {exc}"
        ) from exc

    try:
        target = getattr(module, attr_name)
    except AttributeError as exc:
        raise ValueError(
            f"Bridge {manifest.bridge_id} plugin_factory target '{plugin_reference}' was not found"
        ) from exc

    return target, module_name, plugin_reference


def bind_bridge_runtime(
    manifest: BridgeManifest,
    storage_backend,
    plugin_class: Optional[Type[BridgePlugin]] = None,
) -> BridgeRuntimeBinding:
    """Instantiate a bridge plugin and bind its API/policy/runtime metadata."""
    target, module_name, plugin_reference = _resolve_plugin_target(manifest, plugin_class)

    policy = BridgePolicyPlugin(manifest, storage_backend)
    api = BridgeToScribeAPI(manifest.bridge_id, manifest, storage_backend, policy)

    if inspect.isclass(target):
        if not issubclass(target, BridgePlugin):
            raise ValueError(
                f"Bridge {manifest.bridge_id} plugin target '{target.__name__}' is not a BridgePlugin subclass"
            )
        plugin = target(manifest)
    elif callable(target):
        plugin = target(manifest)
    else:
        raise ValueError(
            f"Bridge {manifest.bridge_id} plugin target '{plugin_reference or target}' is not callable"
        )

    if not isinstance(plugin, BridgePlugin):
        raise ValueError(
            f"Bridge {manifest.bridge_id} plugin target did not return a BridgePlugin instance"
        )

    owner_package = module_name.split(".", 1)[0]
    plugin.bind_runtime(
        api=api,
        policy=policy,
        owner_package=owner_package,
        plugin_reference=plugin_reference,
    )
    return BridgeRuntimeBinding(
        plugin=plugin,
        policy=policy,
        owner_package=owner_package,
        plugin_reference=plugin_reference,
    )
