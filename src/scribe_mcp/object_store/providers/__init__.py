"""Provider registry for remote object store backends."""

from __future__ import annotations

import importlib
from typing import Any

from scribe_mcp.object_store.base import RemoteProvider

# Lazy-loaded provider map: name → "module:ClassName"
_PROVIDERS: dict[str, str] = {
    "corta": "scribe_mcp.object_store.providers.corta:CortaStoreProvider",
    "s3": "scribe_mcp.object_store.providers.s3:S3Provider",
}


def create_provider(provider_name: str, **kwargs: Any) -> RemoteProvider:
    """Instantiate a remote provider by name.

    Raises ``ValueError`` for unknown providers and ``ImportError``
    when the provider module has missing optional dependencies.
    """
    spec = _PROVIDERS.get(provider_name)
    if spec is None:
        known = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unknown object store provider {provider_name!r}. "
            f"Available: {known}"
        )
    module_path, class_name = spec.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(**kwargs)
