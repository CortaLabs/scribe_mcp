"""Bridge health monitoring system."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Awaitable

from .manifest import BridgeState
from .registry import BridgeRegistry

logger = logging.getLogger(__name__)


class BridgeHealthMonitor:
    """
    Monitors bridge health and manages state transitions.

    Runs periodic health checks on all active bridges, transitioning
    unhealthy bridges to ERROR state and recovering healthy ones back
    to ACTIVE state.
    """

    DEFAULT_CHECK_INTERVAL = 300  # 5 minutes
    DEFAULT_UNHEALTHY_THRESHOLD = 3  # 3 consecutive failures before ERROR
    DEFAULT_RECOVERY_THRESHOLD = 2  # 2 consecutive successes before recovery

    def __init__(
        self,
        registry: BridgeRegistry,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        unhealthy_threshold: int = DEFAULT_UNHEALTHY_THRESHOLD,
        recovery_threshold: int = DEFAULT_RECOVERY_THRESHOLD,
        on_state_change: Optional[Callable[[str, BridgeState, BridgeState], Awaitable[None]]] = None
    ):
        """
        Initialize health monitor.

        Args:
            registry: BridgeRegistry to monitor
            check_interval: Seconds between health checks (default: 300/5min)
            unhealthy_threshold: Consecutive failures before ERROR transition
            recovery_threshold: Consecutive successes before ACTIVE recovery
            on_state_change: Optional callback for state changes
        """
        self._registry = registry
        self._check_interval = check_interval
        self._unhealthy_threshold = unhealthy_threshold
        self._recovery_threshold = recovery_threshold
        self._on_state_change = on_state_change

        # Track consecutive failures/successes per bridge
        self._failure_counts: Dict[str, int] = {}
        self._success_counts: Dict[str, int] = {}

        # Monitor task
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # Last check results
        self._last_check_time: Optional[datetime] = None
        self._last_results: Dict[str, Dict[str, Any]] = {}

    async def start(self) -> None:
        """Start the health monitoring loop."""
        if self._running:
            logger.warning("Health monitor already running")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._run_periodic_checks())
        logger.info(
            f"Started bridge health monitor "
            f"(interval={self._check_interval}s, "
            f"unhealthy_threshold={self._unhealthy_threshold}, "
            f"recovery_threshold={self._recovery_threshold})"
        )

    async def stop(self) -> None:
        """Stop the health monitoring loop."""
        if not self._running:
            return

        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("Stopped bridge health monitor")

    async def _run_periodic_checks(self) -> None:
        """Background task that runs periodic health checks."""
        while self._running:
            try:
                await self.check_all_bridges()
            except Exception as e:
                logger.error(f"Error in periodic health check: {e}")

            # Wait for next interval
            try:
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break

    async def check_bridge_health(self, bridge_id: str) -> Dict[str, Any]:
        """
        Check health of a single bridge and handle state transitions.

        Args:
            bridge_id: Bridge to check

        Returns:
            Health check result dict with at least {healthy: bool}
        """
        bridge = self._registry.get_bridge(bridge_id)
        if not bridge:
            return {"healthy": False, "error": "Bridge not found"}

        # Store current state for comparison
        previous_state = bridge.state

        try:
            # Run health check
            health = await bridge.health_check()
            is_healthy = health.get("healthy", False)

            # Track consecutive results
            if is_healthy:
                self._failure_counts[bridge_id] = 0
                self._success_counts[bridge_id] = self._success_counts.get(bridge_id, 0) + 1

                # Handle recovery: ERROR -> ACTIVE
                if bridge.state == BridgeState.ERROR:
                    if self._success_counts[bridge_id] >= self._recovery_threshold:
                        await self._transition_to_active(bridge_id, previous_state)
            else:
                self._success_counts[bridge_id] = 0
                self._failure_counts[bridge_id] = self._failure_counts.get(bridge_id, 0) + 1

                # Handle degradation: ACTIVE -> ERROR
                if bridge.state == BridgeState.ACTIVE:
                    if self._failure_counts[bridge_id] >= self._unhealthy_threshold:
                        await self._transition_to_error(
                            bridge_id,
                            previous_state,
                            health.get("error", "Health check returned unhealthy")
                        )

            return health

        except Exception as e:
            logger.error(f"Health check exception for {bridge_id}: {e}")

            # Track as failure
            self._success_counts[bridge_id] = 0
            self._failure_counts[bridge_id] = self._failure_counts.get(bridge_id, 0) + 1

            # Handle degradation
            if bridge.state == BridgeState.ACTIVE:
                if self._failure_counts[bridge_id] >= self._unhealthy_threshold:
                    await self._transition_to_error(bridge_id, previous_state, str(e))

            return {"healthy": False, "error": str(e)}

    async def check_all_bridges(self) -> Dict[str, Dict[str, Any]]:
        """
        Check health of all bridges that should be monitored.

        Checks ACTIVE and ERROR state bridges. INACTIVE and REGISTERED
        bridges are skipped as they're not expected to be running.

        Returns:
            Dict mapping bridge_id to health result
        """
        results = {}
        self._last_check_time = datetime.now(timezone.utc)

        for bridge_id in list(self._registry._bridges.keys()):
            bridge = self._registry.get_bridge(bridge_id)
            if not bridge:
                continue

            # Only check ACTIVE and ERROR bridges
            if bridge.state not in (BridgeState.ACTIVE, BridgeState.ERROR):
                continue

            results[bridge_id] = await self.check_bridge_health(bridge_id)

        self._last_results = results

        # Log summary
        healthy_count = sum(1 for r in results.values() if r.get("healthy"))
        unhealthy_count = len(results) - healthy_count
        logger.info(
            f"Health check complete: {healthy_count} healthy, "
            f"{unhealthy_count} unhealthy out of {len(results)} bridges"
        )

        return results

    async def _transition_to_error(
        self,
        bridge_id: str,
        previous_state: BridgeState,
        error: str
    ) -> None:
        """Transition bridge to ERROR state."""
        bridge = self._registry.get_bridge(bridge_id)
        if not bridge:
            return

        bridge.state = BridgeState.ERROR
        await self._registry._storage.update_bridge_state(
            bridge_id, BridgeState.ERROR.value
        )
        await self._registry._storage.update_bridge_health(
            bridge_id,
            '{"healthy": false}',
            error=error
        )

        logger.warning(
            f"Bridge {bridge_id} transitioned to ERROR: {error} "
            f"(failures: {self._failure_counts.get(bridge_id, 0)})"
        )

        if self._on_state_change:
            try:
                await self._on_state_change(bridge_id, previous_state, BridgeState.ERROR)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    async def _transition_to_active(
        self,
        bridge_id: str,
        previous_state: BridgeState
    ) -> None:
        """Transition bridge from ERROR back to ACTIVE."""
        bridge = self._registry.get_bridge(bridge_id)
        if not bridge:
            return

        bridge.state = BridgeState.ACTIVE
        await self._registry._storage.update_bridge_state(
            bridge_id, BridgeState.ACTIVE.value
        )

        logger.info(
            f"Bridge {bridge_id} recovered to ACTIVE "
            f"(successes: {self._success_counts.get(bridge_id, 0)})"
        )

        if self._on_state_change:
            try:
                await self._on_state_change(bridge_id, previous_state, BridgeState.ACTIVE)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Get health monitor status.

        Returns:
            Dict with monitor state, last check time, and results
        """
        return {
            "running": self._running,
            "check_interval_seconds": self._check_interval,
            "unhealthy_threshold": self._unhealthy_threshold,
            "recovery_threshold": self._recovery_threshold,
            "last_check_time": self._last_check_time.isoformat() if self._last_check_time else None,
            "last_results": self._last_results,
            "failure_counts": dict(self._failure_counts),
            "success_counts": dict(self._success_counts)
        }

    def reset_counts(self, bridge_id: Optional[str] = None) -> None:
        """
        Reset failure/success counts.

        Args:
            bridge_id: Specific bridge to reset, or None for all
        """
        if bridge_id:
            self._failure_counts.pop(bridge_id, None)
            self._success_counts.pop(bridge_id, None)
        else:
            self._failure_counts.clear()
            self._success_counts.clear()


# Global health monitor instance
_health_monitor: Optional[BridgeHealthMonitor] = None


def get_health_monitor() -> Optional[BridgeHealthMonitor]:
    """Get the global health monitor instance."""
    return _health_monitor


def set_health_monitor(monitor: BridgeHealthMonitor) -> None:
    """Set the global health monitor instance."""
    global _health_monitor
    _health_monitor = monitor


async def create_health_monitor(
    registry: BridgeRegistry,
    check_interval: float = BridgeHealthMonitor.DEFAULT_CHECK_INTERVAL,
    auto_start: bool = True,
    **kwargs
) -> BridgeHealthMonitor:
    """
    Create and optionally start a health monitor.

    Args:
        registry: BridgeRegistry to monitor
        check_interval: Seconds between checks
        auto_start: Whether to start monitoring immediately
        **kwargs: Additional arguments for BridgeHealthMonitor

    Returns:
        Configured BridgeHealthMonitor instance
    """
    monitor = BridgeHealthMonitor(
        registry,
        check_interval=check_interval,
        **kwargs
    )

    if auto_start:
        await monitor.start()

    set_health_monitor(monitor)
    return monitor
