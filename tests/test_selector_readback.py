from __future__ import annotations

from scribe_mcp.selector_readback import (
    ACTIVE_RUNTIME_EXCLUSION_LABEL,
    BLOCKED_STATUS_ACTIVE_RUNTIME_DEPENDENT,
    BLOCKED_STATUS_DEFAULT_CONTEXT_DEPENDENT,
    BLOCKED_STATUS_MISSING_LABEL,
    BLOCKED_STATUS_SOURCE_NOT_SCRIBE_OWNED,
    DEFAULT_CONTEXT_BYPASS_LABEL,
    PRIVATE_SELECTOR_CLASS_LABEL,
    READBACK_STATUS_LABEL,
    RUNTIME_ROLE_LABEL,
    SOURCE_AUTHORITY_LABEL,
    TARGET_FINGERPRINT_BINDING_LABEL,
    build_selector_readback_labels,
    scribe_private_context_selector_readback,
)

EXPECTED_KEYS = {
    "private_selector_class_label",
    "selected_target_fingerprint_binding_label",
    "selected_runtime_role_label",
    "default_context_bypass_or_override_label",
    "active_runtime_contamination_excluded_label",
    "selected_context_source_authority_label",
    "selected_context_readback_status_label",
    "private_values_recorded",
    "train_local_db_g_technical_pass_earned",
    "train_02g2_b_routing_authorized",
}


def _accepted_labels() -> dict[str, str]:
    return {
        "selector_class_label": PRIVATE_SELECTOR_CLASS_LABEL,
        "target_fingerprint_binding_label": TARGET_FINGERPRINT_BINDING_LABEL,
        "runtime_role_label": RUNTIME_ROLE_LABEL,
        "default_context_bypass_label": DEFAULT_CONTEXT_BYPASS_LABEL,
        "active_runtime_exclusion_label": ACTIVE_RUNTIME_EXCLUSION_LABEL,
        "source_authority_label": SOURCE_AUTHORITY_LABEL,
    }


def test_successful_public_label_emission_for_accepted_30aw_set() -> None:
    payload = build_selector_readback_labels(**_accepted_labels())

    assert set(payload) == EXPECTED_KEYS
    assert payload == {
        "private_selector_class_label": PRIVATE_SELECTOR_CLASS_LABEL,
        "selected_target_fingerprint_binding_label": TARGET_FINGERPRINT_BINDING_LABEL,
        "selected_runtime_role_label": RUNTIME_ROLE_LABEL,
        "default_context_bypass_or_override_label": DEFAULT_CONTEXT_BYPASS_LABEL,
        "active_runtime_contamination_excluded_label": ACTIVE_RUNTIME_EXCLUSION_LABEL,
        "selected_context_source_authority_label": SOURCE_AUTHORITY_LABEL,
        "selected_context_readback_status_label": READBACK_STATUS_LABEL,
        "private_values_recorded": False,
        "train_local_db_g_technical_pass_earned": False,
        "train_02g2_b_routing_authorized": False,
    }


def test_wrapper_returns_same_public_readback_payload() -> None:
    assert scribe_private_context_selector_readback(**_accepted_labels()) == build_selector_readback_labels(
        **_accepted_labels()
    )


def test_blocked_output_when_any_required_label_is_missing() -> None:
    labels = _accepted_labels()
    labels["selector_class_label"] = ""

    payload = build_selector_readback_labels(**labels)

    assert set(payload) == EXPECTED_KEYS
    assert payload["selected_context_readback_status_label"] == BLOCKED_STATUS_MISSING_LABEL
    assert payload["private_values_recorded"] is False
    assert payload["train_local_db_g_technical_pass_earned"] is False
    assert payload["train_02g2_b_routing_authorized"] is False


def test_blocked_output_when_label_indicates_default_context_dependence() -> None:
    labels = _accepted_labels()
    labels["default_context_bypass_label"] = "ambient_default_scribe_runtime_context_required"

    payload = build_selector_readback_labels(**labels)

    assert payload["selected_context_readback_status_label"] == BLOCKED_STATUS_DEFAULT_CONTEXT_DEPENDENT


def test_blocked_output_when_source_authority_is_not_scribe_owned() -> None:
    labels = _accepted_labels()
    labels["source_authority_label"] = "council_owned_db_primitive_synthesized_label"

    payload = build_selector_readback_labels(**labels)

    assert payload["selected_context_readback_status_label"] == BLOCKED_STATUS_SOURCE_NOT_SCRIBE_OWNED


def test_blocked_output_when_active_runtime_contact_would_be_required() -> None:
    labels = _accepted_labels()
    labels["active_runtime_exclusion_label"] = "requires_active_runtime_contact_to_compare_target"

    payload = build_selector_readback_labels(**labels)

    assert payload["selected_context_readback_status_label"] == BLOCKED_STATUS_ACTIVE_RUNTIME_DEPENDENT


def test_no_leak_output_contains_only_public_labels_booleans_and_blocked_statuses() -> None:
    labels = _accepted_labels()
    labels["target_fingerprint_binding_label"] = "raw_selector_coordinate_input"

    payload = build_selector_readback_labels(**labels)

    assert set(payload) == EXPECTED_KEYS
    for value in payload.values():
        assert isinstance(value, (str, bool))
        if isinstance(value, str):
            assert value == READBACK_STATUS_LABEL or value.startswith(
                ("approved_", "selected_", "reviewed_", "true_", "scribe_", "blocked_")
            )
            assert "raw_selector_coordinate_input" not in value
