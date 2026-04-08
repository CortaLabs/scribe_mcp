"""Shared MCP tool contract helpers for explicit public-surface metadata."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Iterable, Literal

ToolSurface = Literal["operator", "admin"]
TaskSupport = Literal["forbidden", "optional", "required"]


class ToolTrustTier(IntEnum):
    """Risk-oriented trust tiers for Scribe's public MCP tools."""

    LOCAL_READ_ONLY = 0
    LOCAL_ADDITIVE_WRITE = 1
    LOCAL_STATEFUL_WRITE = 2
    LOCAL_DESTRUCTIVE_ADMIN = 3
    OPEN_WORLD = 4


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = str(tag).strip().lower().replace(" ", "-")
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _tool_contract(
    *,
    title: str,
    trust_tier: ToolTrustTier,
    risk_class: str,
    surface: ToolSurface,
    tags: Iterable[str],
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
    task_support: TaskSupport | None = None,
) -> dict[str, Any]:
    normalized_tags = _normalize_tags(tags)
    kwargs: dict[str, Any] = {
        "title": title,
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": open_world,
        },
        "_meta": {
            "scribe": {
                "trustTier": int(trust_tier),
                "trustLabel": trust_tier.name.lower(),
                "riskClass": risk_class,
                "surface": surface,
                "locality": "open_world" if open_world else "local",
            }
        },
    }
    if normalized_tags:
        kwargs["tags"] = normalized_tags
        kwargs["_meta"]["scribe"]["tags"] = normalized_tags
    if task_support is not None:
        kwargs["execution"] = {"taskSupport": task_support}
    return kwargs


def read_only_local_tool(
    *,
    title: str,
    tags: Iterable[str] = (),
    surface: ToolSurface = "operator",
    task_support: TaskSupport | None = None,
) -> dict[str, Any]:
    return _tool_contract(
        title=title,
        trust_tier=ToolTrustTier.LOCAL_READ_ONLY,
        risk_class="local_read_only",
        surface=surface,
        tags=tags,
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
        task_support=task_support,
    )


def additive_local_tool(
    *,
    title: str,
    tags: Iterable[str] = (),
    surface: ToolSurface = "operator",
    task_support: TaskSupport | None = None,
) -> dict[str, Any]:
    return _tool_contract(
        title=title,
        trust_tier=ToolTrustTier.LOCAL_ADDITIVE_WRITE,
        risk_class="local_additive_write",
        surface=surface,
        tags=tags,
        read_only=False,
        destructive=False,
        idempotent=False,
        open_world=False,
        task_support=task_support,
    )


def stateful_local_tool(
    *,
    title: str,
    tags: Iterable[str] = (),
    surface: ToolSurface = "operator",
    task_support: TaskSupport | None = None,
) -> dict[str, Any]:
    return _tool_contract(
        title=title,
        trust_tier=ToolTrustTier.LOCAL_STATEFUL_WRITE,
        risk_class="local_stateful_write",
        surface=surface,
        tags=tags,
        read_only=False,
        destructive=False,
        idempotent=False,
        open_world=False,
        task_support=task_support,
    )


def destructive_local_tool(
    *,
    title: str,
    tags: Iterable[str] = (),
    surface: ToolSurface = "admin",
    task_support: TaskSupport | None = None,
) -> dict[str, Any]:
    return _tool_contract(
        title=title,
        trust_tier=ToolTrustTier.LOCAL_DESTRUCTIVE_ADMIN,
        risk_class="local_destructive_admin",
        surface=surface,
        tags=tags,
        read_only=False,
        destructive=True,
        idempotent=False,
        open_world=False,
        task_support=task_support,
    )
