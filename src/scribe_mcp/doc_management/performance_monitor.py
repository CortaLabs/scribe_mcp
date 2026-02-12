"""Performance monitoring and metrics collection for document management."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.utils.time import utcnow


@dataclass
class PerformanceMetric:
    """Individual performance metric measurement."""
    name: str
    value: float
    unit: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationMetrics:
    """Metrics for a specific operation."""
    operation_name: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    average_duration: float
    min_duration: float
    max_duration: float
    total_duration: float
    last_operation_time: Optional[datetime]
    error_rate: float
    throughput: float  # operations per second


@dataclass
class SystemMetrics:
    """Overall system performance metrics."""
    timestamp: datetime
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    active_operations: int = 0
    queued_operations: int = 0
    cache_hit_rate: float = 0.0
    database_connections: int = 0


class PerformanceMonitor:
    """Comprehensive performance monitoring for document management operations."""

    def __init__(
        self,
        storage: StorageBackend,
        project_root: Path,
        collection_interval: float = 60.0,
        metrics_retention_hours: int = 24
    ):
        self.storage = storage
        self.project_root = Path(project_root)
        self.collection_interval = collection_interval
        self.metrics_retention_hours = metrics_retention_hours

        self._logger = logging.getLogger(__name__)
        self._is_collecting = False
        self._collection_task: Optional[asyncio.Task] = None

        # Performance tracking
        self._operation_metrics: Dict[str, List[float]] = {}
        self._operation_errors: Dict[str, List[Exception]] = {}
        self._operation_times: Dict[str, List[float]] = {}          # durations (s)
        self._operation_end_times: Dict[str, List[float]] = {}       # epoch seconds
        self._active_operations: Dict[str, float] = {}
        self._custom_metrics: List[PerformanceMetric] = []

        # Callbacks for custom metrics
        self._metric_callbacks: List[Callable[[], List[PerformanceMetric]]] = []

    async def start_collection(self) -> bool:
        """Start automatic metrics collection."""
        if self._is_collecting:
            self._logger.warning("Performance monitoring is already running")
            return True

        try:
            self._is_collecting = True
            self._collection_task = asyncio.create_task(self._collection_loop())
            self._logger.info("Performance monitoring started")
            return True

        except Exception as e:
            self._logger.error(f"Failed to start performance monitoring: {e}")
            return False

    async def stop_collection(self):
        """Stop metrics collection."""
        if not self._is_collecting:
            return

        self._is_collecting = False

        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
            self._collection_task = None

        self._logger.info("Performance monitoring stopped")

    def track_operation_start(self, operation_name: str, operation_id: Optional[str] = None) -> str:
        """Track the start of an operation."""
        operation_id = operation_id or f"{operation_name}_{time.time()}"
        start_time = time.time()

        self._active_operations[operation_id] = start_time

        self._logger.debug(f"Started tracking operation: {operation_name} ({operation_id})")
        return operation_id

    def track_operation_end(
        self,
        operation_id: str,
        operation_name: str,
        success: bool = True,
        error: Optional[Exception] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Track the end of an operation."""
        end_time = time.time()

        if operation_id not in self._active_operations:
            self._logger.warning(f"Operation {operation_id} was not tracked as active")
            return

        start_time = self._active_operations.pop(operation_id)
        duration = end_time - start_time

        # Record duration + end timestamp
        if operation_name not in self._operation_times:
            self._operation_times[operation_name] = []
        self._operation_times[operation_name].append(duration)

        if operation_name not in self._operation_end_times:
            self._operation_end_times[operation_name] = []
        self._operation_end_times[operation_name].append(end_time)

        # Record success/failure
        if operation_name not in self._operation_metrics:
            self._operation_metrics[operation_name] = []
        self._operation_metrics[operation_name].append(1.0 if success else 0.0)

        # Record errors
        if not success and error:
            if operation_name not in self._operation_errors:
                self._operation_errors[operation_name] = []
            self._operation_errors[operation_name].append(error)

        # Store in database periodically
        asyncio.create_task(self._store_operation_metric(
            operation_name, duration, success, metadata
        ))

        self._logger.debug(f"Completed operation: {operation_name} in {duration:.3f}s")

    async def _store_operation_metric(
        self,
        operation_name: str,
        duration: float,
        success: bool,
        metadata: Optional[Dict[str, Any]]
    ):
        """Store operation metric in database."""
        try:
            # Store in performance_metrics table
            await self.storage.store_performance_metric(
                project_id=await self._get_project_id(),
                metric_category="document_management",
                metric_name=f"{operation_name}_duration",
                metric_value=duration,
                metric_unit="seconds",
                metadata=metadata or {}
            )

            if success:
                await self.storage.store_performance_metric(
                    project_id=await self._get_project_id(),
                    metric_category="document_management",
                    metric_name=f"{operation_name}_success",
                    metric_value=1.0,
                    metric_unit="boolean",
                    metadata=metadata or {}
                )

        except Exception as e:
            self._logger.debug(f"Failed to store operation metric: {e}")

    async def _get_project_id(self) -> int:
        """Get project ID for metrics storage."""
        try:
            project = await self.storage.fetch_project(self.project_root.name)
            if project:
                return project.id
        except Exception:
            pass

        # Fallback - create or get project
        project = await self.storage.upsert_project(
            name=self.project_root.name,
            repo_root=str(self.project_root),
            progress_log_path=str(self.project_root / "PROGRESS_LOG.md")
        )
        return project.id

    def add_custom_metric(self, metric: PerformanceMetric):
        """Add a custom performance metric."""
        self._custom_metrics.append(metric)

        # Store in database asynchronously
        asyncio.create_task(self._store_custom_metric(metric))

    async def _store_custom_metric(self, metric: PerformanceMetric):
        """Store custom metric in database."""
        try:
            await self.storage.store_performance_metric(
                project_id=await self._get_project_id(),
                metric_category="custom",
                metric_name=metric.name,
                metric_value=metric.value,
                metric_unit=metric.unit,
                metadata=metric.metadata
            )
        except Exception as e:
            self._logger.debug(f"Failed to store custom metric: {e}")

    def register_metric_callback(self, callback: Callable[[], List[PerformanceMetric]]):
        """Register a callback for collecting custom metrics."""
        self._metric_callbacks.append(callback)

    async def get_operation_metrics(self, operation_name: Optional[str] = None) -> Dict[str, OperationMetrics]:
        """Get metrics for operations."""
        metrics = {}

        operations = [operation_name] if operation_name else list(self._operation_times.keys())

        for op_name in operations:
            if op_name not in self._operation_times:
                continue

            durations = self._operation_times[op_name]
            ends = self._operation_end_times.get(op_name, [])
            successes = self._operation_metrics.get(op_name, [])

            if not durations:
                continue

            total_ops = len(durations)
            successful_ops = sum(successes)
            failed_ops = total_ops - successful_ops

            avg = sum(durations) / len(durations)
            total = sum(durations)
            window = (max(ends) - min(ends)) if len(ends) > 1 else sum(durations)
            tp = (total_ops / window) if window > 0 else 0.0

            metrics[op_name] = OperationMetrics(
                operation_name=op_name,
                total_operations=total_ops,
                successful_operations=successful_ops,
                failed_operations=failed_ops,
                average_duration=avg,
                min_duration=min(durations),
                max_duration=max(durations),
                total_duration=total,
                last_operation_time=datetime.fromtimestamp(max(ends)) if ends else None,
                error_rate=failed_ops / total_ops if total_ops > 0 else 0.0,
                throughput=tp
            )

        return metrics

    async def get_system_metrics(self) -> SystemMetrics:
        """Get current system metrics."""
        try:
            # Basic system metrics
            import psutil

            cpu_usage = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(str(self.project_root))

            return SystemMetrics(
                timestamp=utcnow(),
                cpu_usage=cpu_usage,
                memory_usage=memory.percent,
                disk_usage=disk.percent,
                active_operations=len(self._active_operations),
                queued_operations=0,  # Could be implemented with a queue
                cache_hit_rate=0.0,  # Could be calculated from cache stats
                database_connections=1  # Simplified
            )

        except ImportError:
            # psutil not available, return basic metrics
            return SystemMetrics(
                timestamp=utcnow(),
                active_operations=len(self._active_operations)
            )
        except Exception as e:
            self._logger.warning(f"Failed to collect system metrics: {e}")
            return SystemMetrics(
                timestamp=utcnow(),
                active_operations=len(self._active_operations)
            )

    async def get_performance_summary(
        self,
        time_range_hours: int = 1
    ) -> Dict[str, Any]:
        """Get performance summary for the specified time range."""
        try:
            # Get recent metrics from database
            start_time = utcnow() - timedelta(hours=time_range_hours)

            # This would need to be implemented in the storage backend
            # For now, return in-memory metrics
            operation_metrics = await self.get_operation_metrics()
            system_metrics = await self.get_system_metrics()

            # Calculate summary statistics
            total_operations = sum(m.total_operations for m in operation_metrics.values())
            total_errors = sum(m.failed_operations for m in operation_metrics.values())
            overall_error_rate = total_errors / total_operations if total_operations > 0 else 0.0

            # Find slowest operations
            slowest_operations = sorted(
                operation_metrics.items(),
                key=lambda x: x[1].average_duration,
                reverse=True
            )[:5]

            # Find highest error rates
            highest_error_rates = sorted(
                operation_metrics.items(),
                key=lambda x: x[1].error_rate,
                reverse=True
            )[:5]

            return {
                'time_range_hours': time_range_hours,
                'summary_timestamp': utcnow().isoformat(),
                'total_operations': total_operations,
                'total_errors': total_errors,
                'overall_error_rate': overall_error_rate,
                'active_operations': len(self._active_operations),
                'system_metrics': {
                    'cpu_usage': system_metrics.cpu_usage,
                    'memory_usage': system_metrics.memory_usage,
                    'disk_usage': system_metrics.disk_usage
                },
                'slowest_operations': [
                    {
                        'operation': name,
                        'average_duration': metrics.average_duration,
                        'total_operations': metrics.total_operations
                    }
                    for name, metrics in slowest_operations
                ],
                'highest_error_rates': [
                    {
                        'operation': name,
                        'error_rate': metrics.error_rate,
                        'failed_operations': metrics.failed_operations
                    }
                    for name, metrics in highest_error_rates
                ],
                'operation_metrics': {
                    name: {
                        'total_operations': m.total_operations,
                        'average_duration': m.average_duration,
                        'error_rate': m.error_rate,
                        'throughput': m.throughput
                    }
                    for name, m in operation_metrics.items()
                }
            }

        except Exception as e:
            self._logger.error(f"Failed to generate performance summary: {e}")
            return {'error': str(e)}

    async def _collection_loop(self):
        """Main metrics collection loop."""
        while self._is_collecting:
            try:
                # Collect custom metrics from callbacks
                for callback in self._metric_callbacks:
                    try:
                        custom_metrics = callback()
                        for metric in custom_metrics:
                            self.add_custom_metric(metric)
                    except Exception as e:
                        self._logger.warning(f"Custom metric callback failed: {e}")

                # Cleanup old metrics
                await self._cleanup_old_metrics()

                # Sleep until next collection
                await asyncio.sleep(self.collection_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in metrics collection loop: {e}")
                await asyncio.sleep(self.collection_interval)

    async def _cleanup_old_metrics(self):
        """Clean up old metrics to prevent memory buildup."""
        cutoff_time = time.time() - (self.metrics_retention_hours * 3600)

        # Clean up using **end timestamps**, keep aligned durations by index
        for op_name in list(self._operation_end_times.keys()):
            ends = self._operation_end_times[op_name]
            durs = self._operation_times.get(op_name, [])
            keep = [i for i, ts in enumerate(ends) if ts >= cutoff_time]
            self._operation_end_times[op_name] = [ends[i] for i in keep]
            self._operation_times[op_name] = [durs[i] for i in keep] if durs else []
            if not self._operation_end_times[op_name]:
                self._operation_end_times.pop(op_name, None)
                self._operation_times.pop(op_name, None)

        # Clean up operation success/failure vectors to match remaining samples
        for op_name in list(self._operation_metrics.keys()):
            if op_name not in self._operation_times:
                self._operation_metrics.pop(op_name, None)
                continue
            keep_count = len(self._operation_times[op_name])
            self._operation_metrics[op_name] = self._operation_metrics[op_name][-keep_count:]

        # Clean up custom metrics
        cutoff_datetime = datetime.fromtimestamp(cutoff_time)
        self._custom_metrics = [
            m for m in self._custom_metrics
            if m.timestamp > cutoff_datetime
        ]

    def reset_metrics(self):
        """Reset all collected metrics."""
        self._operation_metrics.clear()
        self._operation_errors.clear()
        self._operation_times.clear()
        self._operation_end_times.clear()
        self._custom_metrics.clear()
        self._active_operations.clear()

        self._logger.info("Performance metrics reset")

    async def export_metrics(
        self,
        format: str = "json",
        output_path: Optional[Path] = None,
        time_range_hours: int = 24
    ) -> str:
        """Export performance metrics in various formats."""
        try:
            summary = await self.get_performance_summary(time_range_hours)

            if format == "json":
                result = json.dumps(summary, indent=2, default=str)

            elif format == "csv":
                lines = ["metric_name,value,unit,timestamp"]

                # Add operation metrics
                for op_name, metrics in (await self.get_operation_metrics()).items():
                    lines.extend([
                        f"{op_name}_duration,{metrics.average_duration},seconds,{utcnow().isoformat()}",
                        f"{op_name}_operations,{metrics.total_operations},count,{utcnow().isoformat()}",
                        f"{op_name}_error_rate,{metrics.error_rate},ratio,{utcnow().isoformat()}"
                    ])

                result = "\n".join(lines)

            elif format == "prometheus":
                # Prometheus metrics format
                lines = []

                for op_name, metrics in (await self.get_operation_metrics()).items():
                    safe_name = op_name.replace(" ", "_").replace("-", "_").lower()
                    lines.extend([
                        f"scribe_operation_duration_seconds{{operation=\"{op_name}\"}} {metrics.average_duration}",
                        f"scribe_operations_total{{operation=\"{op_name}\"}} {metrics.total_operations}",
                        f"scribe_operation_errors_total{{operation=\"{op_name}\"}} {metrics.failed_operations}",
                        f"scribe_operation_error_rate{{operation=\"{op_name}\"}} {metrics.error_rate}"
                    ])

                result = "\n".join(lines)

            else:
                raise ValueError(f"Unsupported export format: {format}")

            # Save to file if path provided
            if output_path:
                output_path.write_text(result, encoding='utf-8')
                self._logger.info(f"Exported metrics to {output_path}")

            return result

        except Exception as e:
            self._logger.error(f"Failed to export metrics: {e}")
            return ""

    def create_performance_context(self, operation_name: str):
        """Create a context manager for tracking operations."""
        return PerformanceContext(self, operation_name)


class PerformanceContext:
    """Context manager for tracking operation performance."""

    def __init__(self, monitor: PerformanceMonitor, operation_name: str):
        self.monitor = monitor
        self.operation_name = operation_name
        self.operation_id: Optional[str] = None
        self.success = True
        self.error: Optional[Exception] = None

    def __enter__(self):
        self.operation_id = self.monitor.track_operation_start(self.operation_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.success = False
            self.error = exc_val

        if self.operation_id:
            self.monitor.track_operation_end(
                self.operation_id,
                self.operation_name,
                self.success,
                self.error
            )

        return False  # Don't suppress exceptions