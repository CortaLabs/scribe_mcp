from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "INSTALL_AND_BOOTSTRAP.md",
    REPO_ROOT / "docs" / "TOUR.md",
    REPO_ROOT / "docs" / "Scribe_Usage.md",
    REPO_ROOT / "docs" / "REMOTE_CLIENT.md",
    REPO_ROOT / "docs" / "mcp_server_guide.md",
]


CLI_MAIN = (REPO_ROOT / "src" / "scribe_mcp" / "cli" / "main.py").read_text(encoding="utf-8")
INSTALL_WIZARD = (REPO_ROOT / "src" / "scribe_mcp" / "install_wizard.py").read_text(encoding="utf-8")
DOC_TEXTS = {path.name: path.read_text(encoding="utf-8") for path in DOCS}
ALL_DOCS_TEXT = "\n".join(DOC_TEXTS.values())


def test_install_code_contract_flags_exist() -> None:
    assert "--commit" in CLI_MAIN
    assert "--yes" in CLI_MAIN
    assert "--project-codex" in CLI_MAIN
    assert "internal-remote" in CLI_MAIN
    assert "allow_advanced_profile" in CLI_MAIN

    assert "profile 'internal-remote' is advanced/default-off" in INSTALL_WIZARD
    assert "projection_execution" in INSTALL_WIZARD
    assert "optional_projection" in INSTALL_WIZARD


def test_docs_prefer_install_path_and_not_bootstrap_as_primary_wizard_flow() -> None:
    assert "use `scribe install` as the preferred setup path" in DOC_TEXTS["Scribe_Usage.md"]
    assert "preferred path is `scribe install`" in DOC_TEXTS["TOUR.md"]
    assert "Install wizard with `scribe install`" in DOC_TEXTS["INSTALL_AND_BOOTSTRAP.md"]


def test_docs_state_preview_non_mutation_and_no_projection_for_base_flow() -> None:
    assert "Preview mode is default and performs no DB mutation, no `.env` mutation, and no projection." in DOC_TEXTS[
        "INSTALL_AND_BOOTSTRAP.md"
    ]
    assert "default install is preview-only (no DB mutation, no `.env` mutation, no projection)" in DOC_TEXTS["TOUR.md"]
    assert "default install is preview-only and does not mutate DB, `.env`, or projection state" in DOC_TEXTS[
        "Scribe_Usage.md"
    ]
    assert "Base install never touches `CODEX_HOME` unless you explicitly request projection." in DOC_TEXTS[
        "INSTALL_AND_BOOTSTRAP.md"
    ]


def test_docs_cover_commit_yes_project_codex_and_advanced_internal_remote() -> None:
    assert "scribe install --commit" in ALL_DOCS_TEXT
    assert "scribe install --commit --yes" in ALL_DOCS_TEXT
    assert "--project-codex" in ALL_DOCS_TEXT
    assert "internal-remote" in ALL_DOCS_TEXT
    assert "advanced/default-off" in ALL_DOCS_TEXT or "advanced and default-off" in ALL_DOCS_TEXT


def test_docs_include_redaction_expectations_and_no_plaintext_secret_examples_as_preferred_flow() -> None:
    assert "must not emit plaintext secrets" in DOC_TEXTS["REMOTE_CLIENT.md"]
    assert "keep credential material redacted" in DOC_TEXTS["REMOTE_CLIENT.md"]

    # Placeholders are acceptable in reference docs, but docs should not prefer
    # inline credential shell flags for onboarding flows.
    assert "--superuser-password '<password>'" not in DOC_TEXTS["INSTALL_AND_BOOTSTRAP.md"]
    assert "--superuser-password '<password>'" not in DOC_TEXTS["TOUR.md"]
