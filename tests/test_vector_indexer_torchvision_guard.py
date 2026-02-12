"""Unit tests for torchvision compatibility guard in vector indexer."""

from __future__ import annotations

from types import SimpleNamespace

from scribe_mcp.plugins import vector_indexer


def test_disable_broken_torchvision_marks_backend_unavailable() -> None:
    import_utils_module = SimpleNamespace(_torchvision_available=True)

    def _broken_import() -> object:
        raise RuntimeError("torchvision import failed")

    changed = vector_indexer._disable_broken_torchvision(
        import_utils_module=import_utils_module,
        torchvision_importer=_broken_import,
    )

    assert changed is True
    assert import_utils_module._torchvision_available is False


def test_disable_broken_torchvision_noop_when_import_succeeds() -> None:
    import_utils_module = SimpleNamespace(_torchvision_available=True)

    changed = vector_indexer._disable_broken_torchvision(
        import_utils_module=import_utils_module,
        torchvision_importer=lambda: object(),
    )

    assert changed is False
    assert import_utils_module._torchvision_available is True


def test_disable_broken_torchvision_skips_import_when_already_unavailable() -> None:
    import_utils_module = SimpleNamespace(_torchvision_available=False)
    called = False

    def _importer() -> object:
        nonlocal called
        called = True
        return object()

    changed = vector_indexer._disable_broken_torchvision(
        import_utils_module=import_utils_module,
        torchvision_importer=_importer,
    )

    assert changed is False
    assert called is False
