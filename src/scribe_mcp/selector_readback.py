"""Public-safe selector/readback labels for private Scribe context selection."""

from __future__ import annotations

SelectorReadbackPayload = dict[str, str | bool]

PRIVATE_SELECTOR_CLASS_LABEL = (
    "approved_operator_private_local_disposable_test_scribe_postgres_selector_class_no_raw_value_recorded"
)
TARGET_FINGERPRINT_BINDING_LABEL = (
    "selected_private_target_matches_30av_approved_fingerprint_label_no_raw_value_recorded"
)
RUNTIME_ROLE_LABEL = "selected_non_active_scribe_runtime_non_canonical_non_shared_local_disposable_test_target"
DEFAULT_CONTEXT_BYPASS_LABEL = "reviewed_private_selector_used_instead_of_ambient_default_scribe_runtime_context"
ACTIVE_RUNTIME_EXCLUSION_LABEL = (
    "true_only_from_scribe_owned_public_safe_selector_readback_without_active_runtime_contact_or_raw_private_inspection"
)
SOURCE_AUTHORITY_LABEL = "scribe_owned_source_backed_selector_readback_not_council_db_primitive"
READBACK_STATUS_LABEL = "scribe_owned_public_safe_readback_emitted_required_selector_status_labels"

BLOCKED_PRIVATE_SELECTOR_CLASS_LABEL = "blocked_private_selector_class_label_not_public_safe"
BLOCKED_TARGET_FINGERPRINT_BINDING_LABEL = "blocked_target_fingerprint_binding_label_not_public_safe"
BLOCKED_RUNTIME_ROLE_LABEL = "blocked_runtime_role_label_not_public_safe"
BLOCKED_DEFAULT_CONTEXT_BYPASS_LABEL = "blocked_default_context_bypass_or_override_label_not_public_safe"
BLOCKED_ACTIVE_RUNTIME_EXCLUSION_LABEL = "blocked_active_runtime_contamination_excluded_label_not_public_safe"
BLOCKED_SOURCE_AUTHORITY_LABEL = "blocked_selected_context_source_authority_label_not_scribe_owned"
BLOCKED_STATUS_MISSING_LABEL = "blocked_missing_required_selector_readback_label"
BLOCKED_STATUS_DEFAULT_CONTEXT_DEPENDENT = "blocked_default_context_dependent_selector_readback"
BLOCKED_STATUS_SOURCE_NOT_SCRIBE_OWNED = "blocked_selector_readback_source_authority_not_scribe_owned"
BLOCKED_STATUS_ACTIVE_RUNTIME_DEPENDENT = "blocked_active_runtime_dependent_selector_readback"
BLOCKED_STATUS_UNSAFE_LABEL = "blocked_unsafe_selector_readback_label"

_EXPECTED_INPUT_LABELS = {
    "selector_class_label": PRIVATE_SELECTOR_CLASS_LABEL,
    "target_fingerprint_binding_label": TARGET_FINGERPRINT_BINDING_LABEL,
    "runtime_role_label": RUNTIME_ROLE_LABEL,
    "default_context_bypass_label": DEFAULT_CONTEXT_BYPASS_LABEL,
    "active_runtime_exclusion_label": ACTIVE_RUNTIME_EXCLUSION_LABEL,
    "source_authority_label": SOURCE_AUTHORITY_LABEL,
}


def _blocked_payload(status_label: str) -> SelectorReadbackPayload:
    return {
        "private_selector_class_label": BLOCKED_PRIVATE_SELECTOR_CLASS_LABEL,
        "selected_target_fingerprint_binding_label": BLOCKED_TARGET_FINGERPRINT_BINDING_LABEL,
        "selected_runtime_role_label": BLOCKED_RUNTIME_ROLE_LABEL,
        "default_context_bypass_or_override_label": BLOCKED_DEFAULT_CONTEXT_BYPASS_LABEL,
        "active_runtime_contamination_excluded_label": BLOCKED_ACTIVE_RUNTIME_EXCLUSION_LABEL,
        "selected_context_source_authority_label": BLOCKED_SOURCE_AUTHORITY_LABEL,
        "selected_context_readback_status_label": status_label,
        "private_values_recorded": False,
        "train_local_db_g_technical_pass_earned": False,
        "train_02g2_b_routing_authorized": False,
    }


def _status_for_invalid_label(label_name: str, value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        return BLOCKED_STATUS_MISSING_LABEL
    if label_name == "default_context_bypass_label":
        return BLOCKED_STATUS_DEFAULT_CONTEXT_DEPENDENT
    if label_name == "source_authority_label":
        return BLOCKED_STATUS_SOURCE_NOT_SCRIBE_OWNED
    if label_name == "active_runtime_exclusion_label":
        return BLOCKED_STATUS_ACTIVE_RUNTIME_DEPENDENT
    if "target_agnostic" in normalized or "target-agnostic" in normalized:
        return BLOCKED_STATUS_UNSAFE_LABEL
    return BLOCKED_STATUS_UNSAFE_LABEL


def build_selector_readback_labels(
    selector_class_label: str,
    target_fingerprint_binding_label: str,
    runtime_role_label: str,
    default_context_bypass_label: str,
    active_runtime_exclusion_label: str,
    source_authority_label: str,
) -> SelectorReadbackPayload:
    """Build public-safe selector/readback labels for the accepted 30AW contract."""
    provided_labels = {
        "selector_class_label": selector_class_label,
        "target_fingerprint_binding_label": target_fingerprint_binding_label,
        "runtime_role_label": runtime_role_label,
        "default_context_bypass_label": default_context_bypass_label,
        "active_runtime_exclusion_label": active_runtime_exclusion_label,
        "source_authority_label": source_authority_label,
    }

    for label_name, expected_value in _EXPECTED_INPUT_LABELS.items():
        raw_value = provided_labels[label_name]
        if raw_value != expected_value:
            return _blocked_payload(_status_for_invalid_label(label_name, raw_value))

    return {
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


def scribe_private_context_selector_readback(
    selector_class_label: str,
    target_fingerprint_binding_label: str,
    runtime_role_label: str,
    default_context_bypass_label: str,
    active_runtime_exclusion_label: str,
    source_authority_label: str,
) -> SelectorReadbackPayload:
    """Return public-safe selected-context labels without runtime or target contact."""
    return build_selector_readback_labels(
        selector_class_label=selector_class_label,
        target_fingerprint_binding_label=target_fingerprint_binding_label,
        runtime_role_label=runtime_role_label,
        default_context_bypass_label=default_context_bypass_label,
        active_runtime_exclusion_label=active_runtime_exclusion_label,
        source_authority_label=source_authority_label,
    )
