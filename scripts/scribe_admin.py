#!/usr/bin/env python3
"""Scribe Admin CLI for bridge management.

Commands:
    scribe-admin bridge list                    List all bridges with state
    scribe-admin bridge register --manifest <path>  Register a new bridge
    scribe-admin bridge activate <bridge_id>    Activate a bridge
    scribe-admin bridge deactivate <bridge_id>  Deactivate a bridge
    scribe-admin bridge status <bridge_id>      Detailed bridge status
    scribe-admin bridge health [bridge_id]      Run health check(s)
    scribe-admin bridge logs <bridge_id>        View bridge-related logs

    scribe-admin health status                  Health monitor status
    scribe-admin health start                   Start health monitor
    scribe-admin health stop                    Stop health monitor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup path
ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT_DIR.parent

os.environ.setdefault("SCRIBE_ROOT", str(ROOT_DIR))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.bridges import (
    BridgeRegistry,
    BridgeState,
    BridgeHealthMonitor,
    get_health_monitor,
    create_health_monitor,
)


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


STATE_COLORS = {
    "registered": Colors.BLUE,
    "active": Colors.GREEN,
    "inactive": Colors.GRAY,
    "error": Colors.RED,
    "unregistered": Colors.GRAY,
}

STATE_SYMBOLS = {
    "registered": "○",
    "active": "●",
    "inactive": "◌",
    "error": "✗",
    "unregistered": "—",
}


def colorize(text: str, color: str) -> str:
    """Apply ANSI color to text."""
    return f"{color}{text}{Colors.RESET}"


def format_state(state: str) -> str:
    """Format bridge state with color and symbol."""
    symbol = STATE_SYMBOLS.get(state, "?")
    color = STATE_COLORS.get(state, Colors.RESET)
    return colorize(f"{symbol} {state.upper()}", color)


def format_timestamp(ts: Optional[str]) -> str:
    """Format timestamp for display."""
    if not ts:
        return colorize("never", Colors.GRAY)
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return str(ts)[:16]


async def get_storage() -> SQLiteStorage:
    """Get initialized storage backend."""
    db_path = os.environ.get(
        "SCRIBE_DB_PATH",
        str(ROOT_DIR / "data" / "scribe_projects.db")
    )
    storage = SQLiteStorage(db_path)
    await storage._initialise()
    return storage


async def get_registry() -> BridgeRegistry:
    """Get initialized bridge registry."""
    storage = await get_storage()
    config_dir = ROOT_DIR / ".scribe" / "config" / "bridges"
    return BridgeRegistry(storage, config_dir)


# ============================================================================
# BRIDGE COMMANDS
# ============================================================================

async def cmd_bridge_list(args: argparse.Namespace) -> int:
    """List all registered bridges."""
    registry = await get_registry()
    bridges = await registry.list_bridges(state=args.state)

    if not bridges:
        print(colorize("No bridges registered.", Colors.GRAY))
        return 0

    # Header
    print()
    print(colorize("BRIDGE REGISTRY", Colors.BOLD))
    print("=" * 80)

    # Table header
    header = f"{'ID':<25} {'NAME':<20} {'VERSION':<10} {'STATE':<15} {'LAST CHECK':<18}"
    print(colorize(header, Colors.CYAN))
    print("-" * 80)

    # Rows
    for bridge in bridges:
        bridge_id = bridge.get("bridge_id", "?")[:24]
        name = bridge.get("name", "?")[:19]
        version = bridge.get("version", "?")[:9]
        state = bridge.get("state", "unknown")
        last_check = format_timestamp(bridge.get("last_health_check"))

        state_display = format_state(state)

        print(f"{bridge_id:<25} {name:<20} {version:<10} {state_display:<15} {last_check:<18}")

    print()
    print(colorize(f"Total: {len(bridges)} bridge(s)", Colors.GRAY))

    return 0


async def cmd_bridge_register(args: argparse.Namespace) -> int:
    """Register a new bridge from manifest."""
    manifest_path = Path(args.manifest)

    if not manifest_path.exists():
        print(colorize(f"Error: Manifest file not found: {manifest_path}", Colors.RED))
        return 1

    registry = await get_registry()

    try:
        manifest = registry.load_manifest(manifest_path)
        bridge_id = await registry.register_bridge(manifest)
        print(colorize(f"✓ Registered bridge: {bridge_id}", Colors.GREEN))
        print(f"  Name: {manifest.name}")
        print(f"  Version: {manifest.version}")
        print(f"  Permissions: {', '.join(manifest.permissions)}")
        return 0
    except ValueError as e:
        print(colorize(f"Error: {e}", Colors.RED))
        return 1
    except Exception as e:
        print(colorize(f"Failed to register bridge: {e}", Colors.RED))
        return 1


async def cmd_bridge_activate(args: argparse.Namespace) -> int:
    """Activate a bridge."""
    registry = await get_registry()

    try:
        await registry.activate_bridge(args.bridge_id)
        print(colorize(f"✓ Activated bridge: {args.bridge_id}", Colors.GREEN))
        return 0
    except ValueError as e:
        print(colorize(f"Error: {e}", Colors.RED))
        return 1
    except RuntimeError as e:
        print(colorize(f"Activation failed: {e}", Colors.RED))
        return 1


async def cmd_bridge_deactivate(args: argparse.Namespace) -> int:
    """Deactivate a bridge."""
    registry = await get_registry()

    try:
        await registry.deactivate_bridge(args.bridge_id)
        print(colorize(f"✓ Deactivated bridge: {args.bridge_id}", Colors.GREEN))
        return 0
    except ValueError as e:
        print(colorize(f"Error: {e}", Colors.RED))
        return 1


async def cmd_bridge_status(args: argparse.Namespace) -> int:
    """Show detailed bridge status."""
    storage = await get_storage()
    bridges = await storage.list_bridges()

    bridge = next((b for b in bridges if b.get("bridge_id") == args.bridge_id), None)

    if not bridge:
        print(colorize(f"Error: Bridge not found: {args.bridge_id}", Colors.RED))
        return 1

    print()
    print(colorize(f"BRIDGE: {bridge['bridge_id']}", Colors.BOLD))
    print("=" * 60)

    # Basic info
    print(f"  Name:           {bridge.get('name', '?')}")
    print(f"  Version:        {bridge.get('version', '?')}")
    print(f"  State:          {format_state(bridge.get('state', 'unknown'))}")

    # Timestamps
    print(f"  Registered:     {format_timestamp(bridge.get('registered_at'))}")
    print(f"  Last Health:    {format_timestamp(bridge.get('last_health_check'))}")

    # Health status
    health_json = bridge.get("health_status")
    if health_json:
        try:
            health = json.loads(health_json)
            is_healthy = health.get("healthy", False)
            health_color = Colors.GREEN if is_healthy else Colors.RED
            print(f"  Healthy:        {colorize(str(is_healthy), health_color)}")
            if health.get("message"):
                print(f"  Message:        {health['message']}")
            if health.get("latency_ms"):
                print(f"  Latency:        {health['latency_ms']}ms")
        except json.JSONDecodeError:
            pass

    # Last error
    if bridge.get("last_error"):
        print(f"  Last Error:     {colorize(bridge['last_error'], Colors.RED)}")

    # Manifest details
    manifest_json = bridge.get("manifest_json")
    if manifest_json:
        try:
            manifest = json.loads(manifest_json)
            print()
            print(colorize("  MANIFEST:", Colors.CYAN))
            print(f"    Author:       {manifest.get('author', '?')}")
            print(f"    Description:  {manifest.get('description', '?')[:50]}")
            print(f"    Permissions:  {', '.join(manifest.get('permissions', []))}")

            hooks = manifest.get("hooks", {})
            if hooks:
                print(f"    Hooks:        {', '.join(hooks.keys())}")

            project_cfg = manifest.get("project_config", {})
            if project_cfg.get("can_create_projects"):
                prefix = project_cfg.get("project_prefix", "")
                print(f"    Project Prefix: {prefix or '(none)'}")

        except json.JSONDecodeError:
            pass

    print()
    return 0


async def cmd_bridge_health(args: argparse.Namespace) -> int:
    """Run health check on bridge(s)."""
    registry = await get_registry()

    if args.bridge_id:
        # Single bridge health check
        bridge = registry.get_bridge(args.bridge_id)
        if not bridge:
            print(colorize(f"Error: Bridge not found or no plugin: {args.bridge_id}", Colors.RED))
            return 1

        try:
            health = await bridge.health_check()
            is_healthy = health.get("healthy", False)

            print()
            print(colorize(f"HEALTH CHECK: {args.bridge_id}", Colors.BOLD))
            print("-" * 40)

            health_status = colorize("HEALTHY", Colors.GREEN) if is_healthy else colorize("UNHEALTHY", Colors.RED)
            print(f"  Status:     {health_status}")

            for key, value in health.items():
                if key != "healthy":
                    print(f"  {key.title()}: {value}")

            return 0 if is_healthy else 1

        except Exception as e:
            print(colorize(f"Health check failed: {e}", Colors.RED))
            return 1
    else:
        # All bridges health check
        results = await registry.health_check_all()

        if not results:
            print(colorize("No active bridges to check.", Colors.GRAY))
            return 0

        print()
        print(colorize("HEALTH CHECK RESULTS", Colors.BOLD))
        print("=" * 60)

        healthy_count = 0
        for bridge_id, health in results.items():
            is_healthy = health.get("healthy", False)
            if is_healthy:
                healthy_count += 1

            status = colorize("✓ HEALTHY", Colors.GREEN) if is_healthy else colorize("✗ UNHEALTHY", Colors.RED)
            message = health.get("message", health.get("error", ""))

            print(f"  {bridge_id:<30} {status} {message}")

        print()
        print(colorize(f"Summary: {healthy_count}/{len(results)} healthy", Colors.GRAY))

        return 0 if healthy_count == len(results) else 1


async def cmd_bridge_logs(args: argparse.Namespace) -> int:
    """View bridge-related logs."""
    storage = await get_storage()

    # Query entries with bridge metadata
    entries = await storage.query_entries(
        meta_filters={"bridge_id": args.bridge_id},
        limit=args.limit
    )

    if not entries:
        print(colorize(f"No log entries found for bridge: {args.bridge_id}", Colors.GRAY))
        return 0

    print()
    print(colorize(f"LOGS FOR: {args.bridge_id}", Colors.BOLD))
    print("=" * 80)

    for entry in entries:
        ts = format_timestamp(entry.get("timestamp_utc"))
        status = entry.get("status", "info")
        message = entry.get("message", "")[:60]

        status_colors = {
            "info": Colors.BLUE,
            "success": Colors.GREEN,
            "warn": Colors.YELLOW,
            "error": Colors.RED,
            "bug": Colors.RED,
        }
        status_color = status_colors.get(status, Colors.RESET)

        print(f"  {ts}  {colorize(status.upper()[:7], status_color):<10}  {message}")

    print()
    return 0


# ============================================================================
# HEALTH MONITOR COMMANDS
# ============================================================================

async def cmd_health_status(args: argparse.Namespace) -> int:
    """Show health monitor status."""
    monitor = get_health_monitor()

    if not monitor:
        print(colorize("Health monitor not initialized.", Colors.GRAY))
        print("Use 'scribe-admin health start' to start monitoring.")
        return 0

    status = monitor.get_status()

    print()
    print(colorize("HEALTH MONITOR STATUS", Colors.BOLD))
    print("=" * 50)

    running_status = colorize("RUNNING", Colors.GREEN) if status["running"] else colorize("STOPPED", Colors.GRAY)
    print(f"  Status:              {running_status}")
    print(f"  Check Interval:      {status['check_interval_seconds']}s")
    print(f"  Unhealthy Threshold: {status['unhealthy_threshold']} failures")
    print(f"  Recovery Threshold:  {status['recovery_threshold']} successes")
    print(f"  Last Check:          {format_timestamp(status['last_check_time'])}")

    if status["last_results"]:
        print()
        print(colorize("  LAST RESULTS:", Colors.CYAN))
        for bridge_id, result in status["last_results"].items():
            is_healthy = result.get("healthy", False)
            health_color = Colors.GREEN if is_healthy else Colors.RED
            print(f"    {bridge_id}: {colorize('healthy' if is_healthy else 'unhealthy', health_color)}")

    if status["failure_counts"]:
        print()
        print(colorize("  FAILURE COUNTS:", Colors.YELLOW))
        for bridge_id, count in status["failure_counts"].items():
            if count > 0:
                print(f"    {bridge_id}: {count}")

    print()
    return 0


async def cmd_health_start(args: argparse.Namespace) -> int:
    """Start health monitoring."""
    monitor = get_health_monitor()

    if monitor and monitor._running:
        print(colorize("Health monitor already running.", Colors.YELLOW))
        return 0

    registry = await get_registry()

    interval = args.interval or BridgeHealthMonitor.DEFAULT_CHECK_INTERVAL

    await create_health_monitor(
        registry,
        check_interval=interval,
        auto_start=True
    )

    print(colorize(f"✓ Started health monitor (interval: {interval}s)", Colors.GREEN))
    return 0


async def cmd_health_stop(args: argparse.Namespace) -> int:
    """Stop health monitoring."""
    monitor = get_health_monitor()

    if not monitor:
        print(colorize("Health monitor not running.", Colors.GRAY))
        return 0

    await monitor.stop()
    print(colorize("✓ Stopped health monitor", Colors.GREEN))
    return 0


# ============================================================================
# MAIN
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="scribe-admin",
        description="Scribe Admin CLI for bridge management"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command group")

    # Bridge commands
    bridge_parser = subparsers.add_parser("bridge", help="Bridge management")
    bridge_sub = bridge_parser.add_subparsers(dest="bridge_cmd", help="Bridge command")

    # bridge list
    list_p = bridge_sub.add_parser("list", help="List all bridges")
    list_p.add_argument("--state", choices=["registered", "active", "inactive", "error"],
                       help="Filter by state")

    # bridge register
    reg_p = bridge_sub.add_parser("register", help="Register a bridge")
    reg_p.add_argument("--manifest", "-m", required=True, help="Path to manifest YAML")

    # bridge activate
    act_p = bridge_sub.add_parser("activate", help="Activate a bridge")
    act_p.add_argument("bridge_id", help="Bridge ID")

    # bridge deactivate
    deact_p = bridge_sub.add_parser("deactivate", help="Deactivate a bridge")
    deact_p.add_argument("bridge_id", help="Bridge ID")

    # bridge status
    stat_p = bridge_sub.add_parser("status", help="Detailed bridge status")
    stat_p.add_argument("bridge_id", help="Bridge ID")

    # bridge health
    health_p = bridge_sub.add_parser("health", help="Run health check")
    health_p.add_argument("bridge_id", nargs="?", help="Bridge ID (optional, checks all if not provided)")

    # bridge logs
    logs_p = bridge_sub.add_parser("logs", help="View bridge logs")
    logs_p.add_argument("bridge_id", help="Bridge ID")
    logs_p.add_argument("--limit", "-n", type=int, default=20, help="Number of entries")

    # Health monitor commands
    health_parser = subparsers.add_parser("health", help="Health monitor management")
    health_sub = health_parser.add_subparsers(dest="health_cmd", help="Health command")

    # health status
    health_sub.add_parser("status", help="Show monitor status")

    # health start
    start_p = health_sub.add_parser("start", help="Start monitoring")
    start_p.add_argument("--interval", "-i", type=int, help="Check interval in seconds")

    # health stop
    health_sub.add_parser("stop", help="Stop monitoring")

    return parser


async def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to command handler
    if args.command == "bridge":
        if not args.bridge_cmd:
            parser.parse_args(["bridge", "--help"])
            return 1

        handlers = {
            "list": cmd_bridge_list,
            "register": cmd_bridge_register,
            "activate": cmd_bridge_activate,
            "deactivate": cmd_bridge_deactivate,
            "status": cmd_bridge_status,
            "health": cmd_bridge_health,
            "logs": cmd_bridge_logs,
        }
        handler = handlers.get(args.bridge_cmd)
        if handler:
            return await handler(args)

    elif args.command == "health":
        if not args.health_cmd:
            parser.parse_args(["health", "--help"])
            return 1

        handlers = {
            "status": cmd_health_status,
            "start": cmd_health_start,
            "stop": cmd_health_stop,
        }
        handler = handlers.get(args.health_cmd)
        if handler:
            return await handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
