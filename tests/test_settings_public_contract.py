from __future__ import annotations

import scribe_mcp.config.settings as settings_module


def test_public_storage_modes_publish_the_three_release_modes() -> None:
    assert settings_module.PUBLIC_STORAGE_MODES == (
        "sqlite",
        "postgres",
    )
    assert settings_module.NON_RELEASE_STORAGE_MODES == ("remote/client",)


def test_public_storage_contract_labels_runtime_aliases_and_bootstrap_envs() -> None:
    contract = settings_module.PUBLIC_STORAGE_SETTINGS_BY_NAME

    assert contract["SCRIBE_DB_PATH"].classification == "canonical"
    assert contract["SCRIBE_SQLITE_PATH"].classification == "compatibility"
    assert contract["SCRIBE_SQLITE_PATH"].canonical_name == "SCRIBE_DB_PATH"
    assert contract["SCRIBE_DB_SCHEMA"].classification == "compatibility"
    assert contract["SCRIBE_DB_SCHEMA"].canonical_name == "SCRIBE_POSTGRES_SCHEMA"

    assert contract["SCRIBE_POSTGRES_POOL_MAX_SIZE"].classification == "advanced/public"
    assert contract["SCRIBE_REMOTE_URL"].classification == "canonical"
    assert contract["SCRIBE_REMOTE_FALLBACK"].classification == "advanced/non-release"
    assert contract["SCRIBE_RELEASE_PROFILE"].classification == "canonical"

    assert contract["SCRIBE_POSTGRES_ADMIN_*"].scope == "bootstrap-only"
    assert contract["SCRIBE_POSTGRES_APP_*"].scope == "bootstrap-only"
    assert contract["SCRIBE_POSTGRES_SUPERUSER_*"].scope == "bootstrap-only"
