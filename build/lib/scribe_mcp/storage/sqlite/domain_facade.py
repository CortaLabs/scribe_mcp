"""Extended SQLiteStorage facade methods split from __init__."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from scribe_mcp.storage.models import (
    BenchmarkRecord,
    DevPlanRecord,
    PerformanceMetricsRecord,
    PhaseRecord,
)

from . import entries as entry_ops
from . import planning as planning_ops
from . import sessions as session_ops
from . import telemetry as telemetry_ops


SLOW_QUERY_THRESHOLD_MS = 25.0
LOGGER = logging.getLogger(__name__)


class SQLiteDomainFacadeMixin:
    """Additional domain methods for the SQLite storage facade."""

    async def upsert_dev_plan(
        self,
        *,
        project_id: int,
        project_name: str,
        plan_type: str,
        file_path: str,
        version: str = "1.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DevPlanRecord:
        return await planning_ops.upsert_dev_plan(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            project_id=project_id,
            project_name=project_name,
            plan_type=plan_type,
            file_path=file_path,
            version=version,
            metadata=metadata,
        )

    async def upsert_phase(
        self,
        *,
        project_id: int,
        dev_plan_id: int,
        phase_number: int,
        phase_name: str,
        status: str = "planned",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        deliverables_count: int = 0,
        deliverables_completed: int = 0,
        confidence_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PhaseRecord:
        return await planning_ops.upsert_phase(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            project_id=project_id,
            dev_plan_id=dev_plan_id,
            phase_number=phase_number,
            phase_name=phase_name,
            status=status,
            start_date=start_date,
            end_date=end_date,
            deliverables_count=deliverables_count,
            deliverables_completed=deliverables_completed,
            confidence_score=confidence_score,
            metadata=metadata,
        )

    async def store_benchmark(
        self,
        *,
        project_id: int,
        benchmark_type: str,
        test_name: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        test_parameters: Optional[Dict[str, Any]] = None,
        environment_info: Optional[Dict[str, Any]] = None,
        requirement_target: Optional[float] = None,
    ) -> BenchmarkRecord:
        return await planning_ops.store_benchmark(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            project_id=project_id,
            benchmark_type=benchmark_type,
            test_name=test_name,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
            test_parameters=test_parameters,
            environment_info=environment_info,
            requirement_target=requirement_target,
        )

    async def get_project_benchmarks(
        self,
        *,
        project_id: int,
        benchmark_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[BenchmarkRecord]:
        return await planning_ops.get_project_benchmarks(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
            project_id=project_id,
            benchmark_type=benchmark_type,
            limit=limit,
        )

    async def store_performance_metric(
        self,
        *,
        project_id: int,
        metric_category: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        baseline_value: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PerformanceMetricsRecord:
        return await planning_ops.store_performance_metric(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            project_id=project_id,
            metric_category=metric_category,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
            baseline_value=baseline_value,
            metadata=metadata,
        )

    async def upsert_agent_session(
        self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]
    ) -> None:
        await session_ops.upsert_agent_session(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata,
        )

    async def upsert_session(
        self,
        *,
        session_id: str,
        transport_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        repo_root: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        await session_ops.upsert_session(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            session_id=session_id,
            transport_session_id=transport_session_id,
            agent_id=agent_id,
            repo_root=repo_root,
            mode=mode,
        )

    async def set_session_mode(self, session_id: str, mode: str) -> None:
        await session_ops.set_session_mode(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            session_id=session_id,
            mode=mode,
        )

    async def get_session_mode(self, session_id: str) -> Optional[str]:
        return await session_ops.get_session_mode(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            session_id=session_id,
        )

    async def set_session_project(
        self, session_id: str, project_name: Optional[str]
    ) -> None:
        await session_ops.set_session_project(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            session_id=session_id,
            project_name=project_name,
        )

    async def get_session_project(self, session_id: str) -> Optional[str]:
        return await session_ops.get_session_project(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            session_id=session_id,
        )

    async def get_session_by_transport(
        self, transport_session_id: str
    ) -> Optional[Dict[str, Any]]:
        return await session_ops.get_session_by_transport(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            transport_session_id=transport_session_id,
        )

    async def upsert_agent_recent_project(
        self, agent_id: str, project_name: str
    ) -> None:
        await session_ops.upsert_agent_recent_project(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            agent_id=agent_id,
            project_name=project_name,
        )

    async def heartbeat_session(self, session_id: str) -> None:
        await session_ops.heartbeat_session(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            session_id=session_id,
        )

    async def end_session(self, session_id: str) -> None:
        await session_ops.end_session(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            session_id=session_id,
        )

    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return await session_ops.get_agent_project(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            agent_id=agent_id,
        )

    async def set_agent_project(
        self,
        agent_id: str,
        project_name: Optional[str],
        expected_version: Optional[int],
        updated_by: str,
        session_id: str,
    ) -> Dict[str, Any]:
        return await session_ops.set_agent_project(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            agent_id=agent_id,
            project_name=project_name,
            expected_version=expected_version,
            updated_by=updated_by,
            session_id=session_id,
        )

    async def update_session_activity(
        self,
        session_id: str,
        tool_name: str,
        timestamp: str,
    ) -> None:
        await session_ops.update_session_activity(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            session_id=session_id,
            tool_name=tool_name,
            timestamp=timestamp,
        )

    async def get_session_activity(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await session_ops.get_session_activity(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            session_id=session_id,
        )

    async def get_or_create_agent_session(
        self,
        identity_key: str,
        agent_name: str,
        agent_key: str,
        repo_root: str,
        mode: str,
        scope_key: str,
        ttl_hours: int = 24,
    ) -> str:
        return await session_ops.get_or_create_agent_session(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            identity_key=identity_key,
            agent_name=agent_name,
            agent_key=agent_key,
            repo_root=repo_root,
            mode=mode,
            scope_key=scope_key,
            ttl_hours=ttl_hours,
        )

    async def cleanup_expired_sessions(self, batch_size: int = 100) -> int:
        return await session_ops.cleanup_expired_sessions(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            batch_size=batch_size,
        )

    async def record_reminder_shown(
        self,
        session_id: str,
        reminder_hash: str,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        reminder_key: Optional[str] = None,
        operation_status: str = "neutral",
        context_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        await telemetry_ops.record_reminder_shown(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            logger=LOGGER,
            slow_query_threshold_ms=SLOW_QUERY_THRESHOLD_MS,
            session_id=session_id,
            reminder_hash=reminder_hash,
            project_root=project_root,
            agent_id=agent_id,
            tool_name=tool_name,
            reminder_key=reminder_key,
            operation_status=operation_status,
            context_metadata=context_metadata,
        )

    async def check_reminder_cooldown(
        self,
        session_id: str,
        reminder_hash: str,
        cooldown_minutes: int = 15,
    ) -> bool:
        return await telemetry_ops.check_reminder_cooldown(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            logger=LOGGER,
            slow_query_threshold_ms=SLOW_QUERY_THRESHOLD_MS,
            session_id=session_id,
            reminder_hash=reminder_hash,
            cooldown_minutes=cooldown_minutes,
        )

    async def cleanup_reminder_history(self, cutoff_hours: int = 168) -> int:
        return await telemetry_ops.cleanup_reminder_history(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            connect_fn=self._connect,
            logger=LOGGER,
            cutoff_hours=cutoff_hours,
        )

    async def record_tool_call(
        self,
        session_id: str,
        tool_name: str,
        duration_ms: Optional[float] = None,
        status: str = "success",
        format_requested: Optional[str] = None,
        project_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
        response_size_bytes: Optional[int] = None,
        repo_root: Optional[str] = None,
    ) -> None:
        await telemetry_ops.record_tool_call(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            logger=LOGGER,
            session_id=session_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            format_requested=format_requested,
            project_name=project_name,
            agent_id=agent_id,
            error_message=error_message,
            response_size_bytes=response_size_bytes,
            repo_root=repo_root,
        )

    def record_tool_call_sync(
        self,
        session_id: str,
        tool_name: str,
        duration_ms: Optional[float] = None,
        status: str = "success",
        format_requested: Optional[str] = None,
        project_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
        response_size_bytes: Optional[int] = None,
        repo_root: Optional[str] = None,
    ) -> None:
        telemetry_ops.record_tool_call_sync(
            db_path=self._path,
            logger=LOGGER,
            session_id=session_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            format_requested=format_requested,
            project_name=project_name,
            agent_id=agent_id,
            error_message=error_message,
            response_size_bytes=response_size_bytes,
            repo_root=repo_root,
        )

    async def get_session_tool_calls(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return await telemetry_ops.get_session_tool_calls(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
            session_id=session_id,
            limit=limit,
        )

    async def get_tool_metrics(
        self,
        tool_name: Optional[str] = None,
        project_name: Optional[str] = None,
        time_range_hours: Optional[int] = 24,
    ) -> Dict[str, Any]:
        return await telemetry_ops.get_tool_metrics(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            tool_name=tool_name,
            project_name=project_name,
            time_range_hours=time_range_hours,
        )

    async def insert_bridge(
        self,
        bridge_id: str,
        name: str,
        version: str,
        manifest_json: str,
        state: str,
    ) -> None:
        await telemetry_ops.insert_bridge(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            bridge_id=bridge_id,
            name=name,
            version=version,
            manifest_json=manifest_json,
            state=state,
        )

    async def update_bridge_state(self, bridge_id: str, state: str) -> None:
        await telemetry_ops.update_bridge_state(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            bridge_id=bridge_id,
            state=state,
        )

    async def update_bridge_health(
        self,
        bridge_id: str,
        health_json: str,
        error: Optional[str] = None,
    ) -> None:
        await telemetry_ops.update_bridge_health(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            bridge_id=bridge_id,
            health_json=health_json,
            error=error,
        )

    async def fetch_bridge(self, bridge_id: str) -> Optional[Dict[str, Any]]:
        return await telemetry_ops.fetch_bridge(
            initialise_fn=self._initialise,
            fetchone_fn=self._fetchone,
            bridge_id=bridge_id,
        )

    async def list_bridges(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        return await telemetry_ops.list_bridges(
            initialise_fn=self._initialise,
            fetchall_fn=self._fetchall,
            state=state,
        )

    async def delete_bridge(self, bridge_id: str) -> None:
        await telemetry_ops.delete_bridge(
            initialise_fn=self._initialise,
            execute_fn=self._execute,
            bridge_id=bridge_id,
        )

    async def cleanup_old_entries(
        self,
        project_id: Optional[int] = None,
        retention_days: int = 90,
        archive: bool = True,
    ) -> int:
        return await entry_ops.cleanup_old_entries(
            initialise_fn=self._initialise,
            write_lock=self._write_lock,
            execute_fn=self._execute,
            fetchone_fn=self._fetchone,
            project_id=project_id,
            retention_days=retention_days,
            archive=archive,
        )
