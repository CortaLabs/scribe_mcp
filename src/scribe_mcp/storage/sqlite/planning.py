"""Planning-domain operations for the SQLite storage backend."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp.storage.models import (
    BenchmarkRecord,
    DevPlanRecord,
    PerformanceMetricsRecord,
    PhaseRecord,
)
from scribe_mcp.utils.time import utcnow


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...] | tuple], Awaitable[List[Any]]]
AsyncInitialise = Callable[[], Awaitable[None]]


async def upsert_dev_plan(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    project_id: int,
    project_name: str,
    plan_type: str,
    file_path: str,
    version: str = "1.0",
    metadata: Optional[Dict[str, Any]] = None,
) -> DevPlanRecord:
    await initialise_fn()
    meta_json = json.dumps(metadata or {}, sort_keys=True)
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO dev_plans (project_id, project_name, plan_type, file_path, version, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, plan_type)
            DO UPDATE SET file_path = excluded.file_path,
                          version = excluded.version,
                          metadata = excluded.metadata,
                          updated_at = excluded.updated_at;
            """,
            (project_id, project_name, plan_type, file_path, version, meta_json, utcnow().isoformat()),
        )
    row = await fetchone_fn(
        """
        SELECT id, project_id, project_name, plan_type, file_path, version, created_at, updated_at, metadata
        FROM dev_plans
        WHERE project_id = ? AND plan_type = ?;
        """,
        (project_id, plan_type),
    )
    return DevPlanRecord(
        id=row["id"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        plan_type=row["plan_type"],
        file_path=row["file_path"],
        version=row["version"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
    )


async def upsert_phase(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
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
    await initialise_fn()
    meta_json = json.dumps(metadata or {}, sort_keys=True)
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO phases (project_id, dev_plan_id, phase_number, phase_name, status,
                             start_date, end_date, deliverables_count, deliverables_completed,
                             confidence_score, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, phase_number)
            DO UPDATE SET phase_name = excluded.phase_name,
                          status = excluded.status,
                          start_date = excluded.start_date,
                          end_date = excluded.end_date,
                          deliverables_count = excluded.deliverables_count,
                          deliverables_completed = excluded.deliverables_completed,
                          confidence_score = excluded.confidence_score,
                          metadata = excluded.metadata;
            """,
            (
                project_id,
                dev_plan_id,
                phase_number,
                phase_name,
                status,
                start_date,
                end_date,
                deliverables_count,
                deliverables_completed,
                confidence_score,
                meta_json,
            ),
        )
    row = await fetchone_fn(
        """
        SELECT id, project_id, dev_plan_id, phase_number, phase_name, status,
               start_date, end_date, deliverables_count, deliverables_completed,
               confidence_score, metadata
        FROM phases
        WHERE project_id = ? AND phase_number = ?;
        """,
        (project_id, phase_number),
    )
    return PhaseRecord(
        id=row["id"],
        project_id=row["project_id"],
        dev_plan_id=row["dev_plan_id"],
        phase_number=row["phase_number"],
        phase_name=row["phase_name"],
        status=row["status"],
        start_date=datetime.fromisoformat(row["start_date"]) if row["start_date"] else None,
        end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
        deliverables_count=row["deliverables_count"],
        deliverables_completed=row["deliverables_completed"],
        confidence_score=row["confidence_score"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
    )


async def store_benchmark(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
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
    await initialise_fn()
    test_params_json = json.dumps(test_parameters or {}, sort_keys=True)
    env_info_json = json.dumps(environment_info or {}, sort_keys=True)
    requirement_met = (
        requirement_target is not None
        and (
            (benchmark_type in ["throughput", "hash_performance"] and metric_value >= requirement_target)
            or (benchmark_type in ["latency", "time"] and metric_value <= requirement_target)
            or (requirement_target > 0 and metric_value <= requirement_target)
            or (requirement_target < 0 and metric_value >= requirement_target)
        )
    )

    row = await fetchone_fn(
        """
        INSERT INTO benchmarks (project_id, benchmark_type, test_name, metric_name,
                               metric_value, metric_unit, test_parameters, environment_info,
                               requirement_target, requirement_met)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id, project_id, benchmark_type, test_name, metric_name, metric_value,
                metric_unit, test_parameters, environment_info, test_timestamp,
                requirement_target, requirement_met;
        """,
        (
            project_id,
            benchmark_type,
            test_name,
            metric_name,
            metric_value,
            metric_unit,
            test_params_json,
            env_info_json,
            requirement_target,
            requirement_met,
        ),
    )
    return BenchmarkRecord(
        id=row["id"],
        project_id=row["project_id"],
        benchmark_type=row["benchmark_type"],
        test_name=row["test_name"],
        metric_name=row["metric_name"],
        metric_value=row["metric_value"],
        metric_unit=row["metric_unit"],
        test_parameters=json.loads(row["test_parameters"]) if row["test_parameters"] else None,
        environment_info=json.loads(row["environment_info"]) if row["environment_info"] else None,
        test_timestamp=datetime.fromisoformat(row["test_timestamp"]),
        requirement_target=row["requirement_target"],
        requirement_met=bool(row["requirement_met"]),
    )


async def get_project_benchmarks(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
    project_id: int,
    benchmark_type: Optional[str] = None,
    limit: int = 100,
) -> List[BenchmarkRecord]:
    await initialise_fn()
    params: List[Any] = [project_id]
    query = """
        SELECT id, project_id, benchmark_type, test_name, metric_name, metric_value,
               metric_unit, test_parameters, environment_info, test_timestamp,
               requirement_target, requirement_met
        FROM benchmarks
        WHERE project_id = ?
    """
    if benchmark_type:
        query += " AND benchmark_type = ?"
        params.append(benchmark_type)
    query += " ORDER BY test_timestamp DESC LIMIT ?"
    params.append(limit)

    rows = await fetchall_fn(query, tuple(params))
    return [
        BenchmarkRecord(
            id=row["id"],
            project_id=row["project_id"],
            benchmark_type=row["benchmark_type"],
            test_name=row["test_name"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit=row["metric_unit"],
            test_parameters=json.loads(row["test_parameters"]) if row["test_parameters"] else None,
            environment_info=json.loads(row["environment_info"]) if row["environment_info"] else None,
            test_timestamp=datetime.fromisoformat(row["test_timestamp"]),
            requirement_target=row["requirement_target"],
            requirement_met=bool(row["requirement_met"]),
        )
        for row in rows
    ]


async def store_performance_metric(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    project_id: int,
    metric_category: str,
    metric_name: str,
    metric_value: float,
    metric_unit: str,
    baseline_value: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> PerformanceMetricsRecord:
    await initialise_fn()
    meta_json = json.dumps(metadata or {}, sort_keys=True)
    improvement_percentage = None
    if baseline_value is not None and baseline_value != 0:
        improvement_percentage = ((metric_value - baseline_value) / abs(baseline_value)) * 100

    row = await fetchone_fn(
        """
        INSERT INTO performance_metrics (project_id, metric_category, metric_name,
                                       metric_value, metric_unit, baseline_value,
                                       improvement_percentage, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id, project_id, metric_category, metric_name, metric_value, metric_unit,
                baseline_value, improvement_percentage, collection_timestamp, metadata;
        """,
        (
            project_id,
            metric_category,
            metric_name,
            metric_value,
            metric_unit,
            baseline_value,
            improvement_percentage,
            meta_json,
        ),
    )
    return PerformanceMetricsRecord(
        id=row["id"],
        project_id=row["project_id"],
        metric_category=row["metric_category"],
        metric_name=row["metric_name"],
        metric_value=row["metric_value"],
        metric_unit=row["metric_unit"],
        baseline_value=row["baseline_value"],
        improvement_percentage=row["improvement_percentage"],
        collection_timestamp=datetime.fromisoformat(row["collection_timestamp"]),
        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
    )
