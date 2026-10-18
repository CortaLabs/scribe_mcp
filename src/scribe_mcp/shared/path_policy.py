"""Repo-owned path policy helpers for public-safe structured metadata."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, Mapping


PathPolicyScope = Literal["append", "projection"]
PathPolicyUnresolvedMode = Literal["reject", "non_exportable"]
PathPolicyRuleSource = Literal["explicit", "active_project_root"]
PathPolicyViolationReason = Literal[
    "unmapped_absolute_path",
    "invalid_label",
    "global_policy_ignored",
]


@dataclass(frozen=True)
class PathPolicyRule:
    label: str
    private_prefix: str | None
    source: PathPolicyRuleSource = "explicit"
    scopes: tuple[str, ...] = ("append", "projection")


@dataclass(frozen=True)
class PathPolicyConfig:
    enabled: bool
    unresolved: PathPolicyUnresolvedMode
    detect_absolute_unknown_keys: bool
    generated_keys: tuple[str, ...]
    rules: tuple[PathPolicyRule, ...]


@dataclass(frozen=True)
class PathPolicyViolation:
    key: str
    scope: PathPolicyScope
    reason: PathPolicyViolationReason
    line_number: int | None = None
    safe_descriptor: str | None = None
    value_sha256_prefix: str | None = None


@dataclass(frozen=True)
class PathPolicyResult:
    mapped: dict[str, object]
    violations: tuple[PathPolicyViolation, ...]


_LOCAL_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:[\\/]")
_WINDOWS_DRIVE_FRAGMENT_RE = re.compile(r"[a-zA-Z]:")
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_DEFAULT_GENERATED_KEYS = ("path", "file_path", "target_repo")


def load_path_policy(repo_config: object, project: Mapping[str, object]) -> PathPolicyConfig:
    raw_policy = getattr(repo_config, "path_policy", {})
    if not isinstance(raw_policy, Mapping):
        raw_policy = {}

    enabled = bool(raw_policy.get("enabled", False))
    unresolved = _parse_unresolved(raw_policy.get("unresolved", "reject"))
    detect_unknown = bool(raw_policy.get("detect_absolute_unknown_keys", False))
    generated_keys = _parse_string_tuple(raw_policy.get("generated_keys", _DEFAULT_GENERATED_KEYS))
    raw_rules = raw_policy.get("rules", ())
    rules = _parse_rules(raw_rules, project)

    return PathPolicyConfig(
        enabled=enabled,
        unresolved=unresolved,
        detect_absolute_unknown_keys=detect_unknown,
        generated_keys=generated_keys,
        rules=rules,
    )


def validate_public_label(label: str, *, private_prefix: str | None = None) -> None:
    if not label or not label.strip():
        raise ValueError("Path policy label is invalid.")
    if "/" in label or "\\" in label or not _SAFE_LABEL_RE.fullmatch(label):
        raise ValueError("Path policy label is invalid.")

    lowered = label.lower()
    forbidden_fragments = ("~", "home", "users", "user", "file:", "localhost")
    if any(fragment in lowered for fragment in forbidden_fragments):
        raise ValueError("Path policy label is invalid.")
    if _WINDOWS_DRIVE_FRAGMENT_RE.search(label) or _LOCAL_URI_RE.match(label):
        raise ValueError("Path policy label is invalid.")

    if private_prefix:
        normalized_prefix = _normalize_prefix(private_prefix).lower()
        if normalized_prefix and normalized_prefix in lowered:
            raise ValueError("Path policy label is invalid.")


def apply_path_policy(
    meta: Mapping[str, object],
    *,
    policy: PathPolicyConfig,
    scope: PathPolicyScope,
) -> PathPolicyResult:
    mapped: dict[str, str] = {}
    violations: list[PathPolicyViolation] = []
    if not policy.enabled:
        return PathPolicyResult(mapped=dict(meta), violations=())

    generated_keys = set(policy.generated_keys)
    for key, value in meta.items():
        if isinstance(value, str):
            mapped_value, violation = _map_string_value(
                key,
                value,
                policy=policy,
                scope=scope,
                should_inspect=key in generated_keys or policy.detect_absolute_unknown_keys,
            )
            if violation is not None:
                mapped[key] = _redacted_unmapped_value(violation)
                violations.append(violation)
            else:
                mapped[key] = mapped_value
        else:
            mapped[key] = value
    return PathPolicyResult(mapped=mapped, violations=tuple(violations))


def looks_like_local_absolute_path(value: str) -> bool:
    if value.startswith("/"):
        return PurePosixPath(value).is_absolute()
    if value.startswith("\\\\"):
        return True
    return PureWindowsPath(value).is_absolute() or bool(_WINDOWS_DRIVE_RE.match(value))


def render_projection(meta: Mapping[str, object], *, policy: PathPolicyConfig) -> PathPolicyResult:
    return apply_path_policy(meta, policy=policy, scope="projection")


def _parse_unresolved(raw_value: object) -> PathPolicyUnresolvedMode:
    if raw_value in ("reject", "non_exportable"):
        return raw_value
    raise ValueError("Path policy unresolved mode is invalid.")


def _parse_string_tuple(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, (list, tuple)):
        raise ValueError("Path policy string list is invalid.")
    values: list[str] = []
    for item in raw_value:
        if not isinstance(item, str) or not item:
            raise ValueError("Path policy string list is invalid.")
        values.append(item)
    return tuple(values)


def _parse_rules(raw_rules: object, project: Mapping[str, object]) -> tuple[PathPolicyRule, ...]:
    if raw_rules is None:
        return ()
    if not isinstance(raw_rules, (list, tuple)):
        raise ValueError("Path policy rules are invalid.")

    parsed: list[PathPolicyRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, Mapping):
            raise ValueError("Path policy rule is invalid.")
        label = raw_rule.get("label")
        if not isinstance(label, str):
            raise ValueError("Path policy label is invalid.")
        source = _parse_source(raw_rule.get("source", "explicit"))
        private_prefix = _resolve_private_prefix(raw_rule, source, project)
        validate_public_label(label, private_prefix=private_prefix)
        scopes = _parse_string_tuple(raw_rule.get("scopes", ("append", "projection")))
        parsed.append(
            PathPolicyRule(
                label=label,
                private_prefix=_normalize_prefix(private_prefix) if private_prefix else None,
                source=source,
                scopes=scopes,
            )
        )
    return tuple(parsed)


def _parse_source(raw_value: object) -> PathPolicyRuleSource:
    if raw_value in ("explicit", "active_project_root"):
        return raw_value
    raise ValueError("Path policy rule source is invalid.")


def _resolve_private_prefix(
    raw_rule: Mapping[str, object],
    source: PathPolicyRuleSource,
    project: Mapping[str, object],
) -> str | None:
    if source == "active_project_root":
        project_root = (
            project.get("active_project_root")
            or project.get("repo_root")
            or project.get("root")
        )
        if not isinstance(project_root, str) or not project_root:
            raise ValueError("Path policy active project root is unavailable.")
        return project_root

    private_prefix = raw_rule.get("private_prefix")
    if not isinstance(private_prefix, str) or not private_prefix:
        raise ValueError("Path policy private prefix is invalid.")
    return private_prefix


def _map_string_value(
    key: str,
    value: str,
    *,
    policy: PathPolicyConfig,
    scope: PathPolicyScope,
    should_inspect: bool,
) -> tuple[str, PathPolicyViolation | None]:
    if _looks_already_safe_label(value):
        return value, None
    if not should_inspect or not looks_like_local_absolute_path(value):
        return value, None

    normalized_value = _normalize_prefix(value)
    for rule in _ordered_rules(policy.rules, scope):
        if rule.private_prefix is None:
            continue
        mapped_value = _apply_rule(normalized_value, rule)
        if mapped_value is not None:
            return mapped_value, None

    return value, _safe_violation(key, value, scope)


def _ordered_rules(rules: tuple[PathPolicyRule, ...], scope: PathPolicyScope) -> tuple[PathPolicyRule, ...]:
    indexed = [
        (index, rule)
        for index, rule in enumerate(rules)
        if scope in rule.scopes and rule.private_prefix is not None
    ]
    indexed.sort(key=lambda item: (-len(item[1].private_prefix or ""), item[0]))
    return tuple(rule for _, rule in indexed)


def _apply_rule(value: str, rule: PathPolicyRule) -> str | None:
    private_prefix = rule.private_prefix
    if private_prefix is None:
        return None
    if value != private_prefix and not value.startswith(f"{private_prefix}/"):
        return None
    suffix = value.removeprefix(private_prefix).lstrip("/")
    return rule.label if not suffix else f"{rule.label}/{suffix}"


def _normalize_prefix(value: str) -> str:
    expanded = value.replace("\\", "/").rstrip("/")
    if _WINDOWS_DRIVE_RE.match(expanded):
        return expanded
    if expanded.startswith("//"):
        return f"//{expanded.lstrip('/')}"
    return str(PurePosixPath(expanded))


def _looks_already_safe_label(value: str) -> bool:
    if looks_like_local_absolute_path(value):
        return False
    if _LOCAL_URI_RE.match(value):
        return False
    return bool(value and _SAFE_LABEL_RE.fullmatch(value.split("/", 1)[0]))


def _safe_violation(key: str, value: str, scope: PathPolicyScope) -> PathPolicyViolation:
    return PathPolicyViolation(
        key=key,
        scope=scope,
        reason="unmapped_absolute_path",
        safe_descriptor="local_absolute_path",
        value_sha256_prefix=hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
    )


def _redacted_unmapped_value(violation: PathPolicyViolation) -> str:
    digest = violation.value_sha256_prefix or "unknown"
    return f"unmapped_local_absolute_path:{digest}"
