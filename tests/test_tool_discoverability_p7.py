"""P7.1 (WS7 Thread 1) tool-discoverability contract tests.

These cover the two host/Codex-facing exposure fixes:
  T1-2: ``append_entry``'s advertised description leads with purpose +
        when-to-use instead of implementation history.
  T1-1: ``health_check`` is registered through the standard
        ``read_only_local_tool`` contract (title, annotations, trust meta,
        tags) like every other read-only tool, not a bare ``@app.tool()``.

Scope is the advertised registration surface only — no behavior is exercised.

``health_check`` is not part of the default loaded tool surface; importing its
module registers it on the shared server singleton. The autouse fixture below
snapshots and restores that singleton so this file does not leak registration
into sibling suites (e.g. the strict default-surface whitelist contract).
"""

from __future__ import annotations

import re

import pytest

from scribe_mcp.server import Server


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# Captured on first fixture setup. The module import (and therefore the
# registration) is cached by Python, so the registry entries must be captured
# the first time before we ever pop them.
_HEALTH_CHECK_ENTRIES: dict[str, object] = {}


@pytest.fixture(autouse=True)
def _isolated_tool_registry():
    """Register health_check only for the duration of each test, then drop it.

    ``health_check`` is not part of the default loaded tool surface; importing
    its module registers it on the shared ``Server`` singleton. We import it
    lazily *inside* the fixture (not at module top-level, which would pollute the
    singleton at pytest collection time) and pop its registry/defs entries on
    teardown, so the registration never leaks into the strict default-surface
    whitelist contract regardless of test execution order.
    """
    import scribe_mcp.tools.health_check  # noqa: F401  (registers the tool)

    registry = getattr(Server, "_scribe_tool_registry", {})
    defs = getattr(Server, "_scribe_tool_defs", {})

    # Capture the registration once (the import is cached after the first run).
    if "func" not in _HEALTH_CHECK_ENTRIES and "health_check" in registry:
        _HEALTH_CHECK_ENTRIES["func"] = registry["health_check"]
        _HEALTH_CHECK_ENTRIES["def"] = defs.get("health_check")

    if _HEALTH_CHECK_ENTRIES.get("func") is not None:
        registry["health_check"] = _HEALTH_CHECK_ENTRIES["func"]
    if _HEALTH_CHECK_ENTRIES.get("def") is not None:
        defs["health_check"] = _HEALTH_CHECK_ENTRIES["def"]
    try:
        yield
    finally:
        registry.pop("health_check", None)
        defs.pop("health_check", None)


def _details() -> dict:
    from scribe_mcp import server

    return server.describe_registered_tools()


def test_append_entry_description_leads_with_purpose_not_implementation():
    """T1-2 KEYSTONE: advertised description is purpose + when-to-use."""
    details = _details()
    description = details["append_entry"]["description"] or ""
    first_line = description.strip().splitlines()[0]
    normalized = _normalize(description)

    # New purpose-led opening is present.
    assert "audit-trail log entry" in first_line
    assert first_line.startswith("Record a Scribe")

    # When-to-use guidance is advertised, not just an arg dump.
    assert "primary logging tool" in normalized
    assert "every 2-3 significant actions" in normalized

    # Old implementation-history phrasing is gone from the advertised text.
    assert "Enhanced append_entry with robust multiline handling" not in description


def test_health_check_registered_via_read_only_local_tool_contract():
    """T1-1: health_check carries the same read-only contract as peer tools."""
    details = _details()
    assert "health_check" in details, "health_check must be a registered tool"
    health = details["health_check"]

    # Standard title + tags from read_only_local_tool(...).
    assert health["title"] == "Health Check"
    assert "diagnostics" in health["tags"]
    assert "read-only" in health["tags"]

    # Read-only annotation profile.
    annotations = health["annotations"]
    assert annotations["readOnlyHint"] is True
    assert annotations["destructiveHint"] is False
    assert annotations["idempotentHint"] is True
    assert annotations["openWorldHint"] is False

    # Trust metadata matches the local read-only tier other tools advertise.
    scribe_meta = health["meta"]["scribe"]
    assert scribe_meta["trustTier"] == 0
    assert scribe_meta["riskClass"] == "local_read_only"
    assert scribe_meta["surface"] == "operator"
    assert scribe_meta["locality"] == "local"


def test_health_check_contract_matches_a_peer_read_only_tool():
    """health_check's contract shape mirrors an existing read-only tool (scribe_doctor)."""
    details = _details()
    health_scribe = details["health_check"]["meta"]["scribe"]
    doctor_scribe = details["scribe_doctor"]["meta"]["scribe"]

    for key in ("trustTier", "trustLabel", "riskClass", "surface", "locality"):
        assert health_scribe[key] == doctor_scribe[key]
