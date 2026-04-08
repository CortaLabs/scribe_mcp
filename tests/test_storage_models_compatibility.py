"""Focused regression coverage for Phase 4.1-D storage-model cleanup."""

import importlib


def test_storage_models_omit_vector_residue_symbols() -> None:
    """storage.models keeps active core records only after vector cleanup."""
    models = importlib.import_module("scribe_mcp.storage.models")

    assert hasattr(models, "ProjectRecord")
    assert not hasattr(models, "VectorIndexRecord")
    assert not hasattr(models, "VectorShardMetadata")
