from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow.sdk import Variable, dag, task
from common.callbacks import persist_failure_alert

LOGGER = logging.getLogger(__name__)

LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
DATA_DIRECTORY = Path("/opt/airflow/data/jobs")
MAX_FAILURE_RATE = 0.10
DEFAULT_MIN_FETCH_RATIO = 0.80
DEFAULT_MIN_FETCH_COUNT = 1

COUNT_FIELDS = (
    "fetched_count",
    "normalized_count",
    "failed_count",
    "inserted_count",
    "updated_count",
    "unchanged_count",
)

METRIC_FIELDS = (
    "source",
    "batch_id",
    *COUNT_FIELDS,
    "raw_file_path",
    "current_cursor",
    "next_cursor",
)


@dataclass(frozen=True, slots=True)
class SourceSchedule:
    source: str
    schedule: str
    limit: int
    uses_cursor: bool
    min_fetch_ratio: float = DEFAULT_MIN_FETCH_RATIO
    min_fetch_count: int = DEFAULT_MIN_FETCH_COUNT


SOURCE_SCHEDULES = (
    SourceSchedule(
        source="himalayas",
        schedule="20 0,5,14 * * *",
        limit=20,
        uses_cursor=True,
    ),
    SourceSchedule(
        source="arbeitnow",
        schedule="10 2,10,18 * * *",
        limit=20,
        uses_cursor=True,
    ),
    SourceSchedule(
        source="topdev",
        schedule="30 7 * * *",
        limit=15,
        uses_cursor=True,
    ),
    SourceSchedule(
        source="remotive",
        schedule="30 12 * * *",
        limit=10,
        uses_cursor=False,
    ),
    SourceSchedule(
        source="jobicy",
        schedule="30 16 * * *",
        limit=10,
        uses_cursor=False,
    ),
    SourceSchedule(
        source="itviec",
        schedule="30 21 * * *",
        limit=20,
        uses_cursor=True,
        min_fetch_ratio=0.40,
    ),
)


def _read_cursor(variable_name: str, *, enabled: bool) -> str | None:
    if not enabled:
        return None

    stored_cursor = Variable.get(variable_name, default=None)

    if not isinstance(stored_cursor, str):
        return None

    normalized = stored_cursor.strip()
    return normalized or None


def _validate_metrics(
    metrics: dict[str, Any],
    *,
    expected_limit: int,
    min_fetch_ratio: float,
    min_fetch_count: int,
) -> dict[str, Any]:
    if not 0 <= min_fetch_ratio <= 1:
        raise ValueError(
            f"min_fetch_ratio must be between 0 and 1, got {min_fetch_ratio!r}"
        )

    if min_fetch_count < 1:
        raise ValueError(
            f"min_fetch_count must be greater than zero, got {min_fetch_count!r}"
        )

    for field in COUNT_FIELDS:
        value = metrics.get(field)

        if type(value) is not int or value < 0:
            raise ValueError(
                f"{field} must be a non-negative integer, got {value!r}"
            )

    fetched = metrics["fetched_count"]
    normalized = metrics["normalized_count"]
    failed = metrics["failed_count"]

    if fetched != normalized + failed:
        raise ValueError(
            "Invalid processing totals: "
            f"fetched={fetched}, normalized={normalized}, failed={failed}"
        )

    written_total = sum(
        metrics[field]
        for field in (
            "inserted_count",
            "updated_count",
            "unchanged_count",
        )
    )

    if written_total != normalized:
        raise ValueError(
            "Invalid repository totals: "
            f"normalized={normalized}, written_total={written_total}"
        )

    minimum_fetched = max(
        min_fetch_count,
        int(expected_limit * min_fetch_ratio),
    )

    if fetched < min_fetch_count:
        raise ValueError(
            "Fetched count is below the required minimum: "
            f"fetched={fetched}, minimum={min_fetch_count}"
        )

    failure_rate = failed / fetched

    if failure_rate > MAX_FAILURE_RATE:
        raise ValueError(
            "Failure rate exceeded threshold: "
            f"{failure_rate:.2%} > {MAX_FAILURE_RATE:.2%}"
        )

    raw_path = Path(str(metrics.get("raw_file_path") or ""))

    if not raw_path.is_absolute():
        raw_path = Path("/opt/airflow") / raw_path

    if not raw_path.is_file() or raw_path.stat().st_size == 0:
        raise ValueError(f"Raw batch file is missing or empty: {raw_path}")

    quality_status = "passed"

    if fetched < minimum_fetched:
        quality_status = "low_fetch_warning"
        LOGGER.warning(
            "Fetched count is below the source target but above the hard "
            "minimum: fetched=%s, target=%s, hard_minimum=%s",
            fetched,
            minimum_fetched,
            min_fetch_count,
        )

    return {
        **metrics,
        "failure_rate": failure_rate,
        "minimum_fetched": minimum_fetched,
        "quality_status": quality_status,
    }


def _persist_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    recorded_at = pendulum.now(LOCAL_TIMEZONE)
    source = str(metrics.get("source", "unknown"))
    batch_id = str(metrics.get("batch_id", "unknown_batch"))
    safe_source = re.sub(r"[^a-zA-Z0-9_.-]+", "_", source)
    safe_batch_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", batch_id)
    metrics_directory = (
        DATA_DIRECTORY
        / "metrics"
        / safe_source
        / recorded_at.date().isoformat()
    )
    metrics_directory.mkdir(parents=True, exist_ok=True)

    metrics_path = metrics_directory / f"{safe_batch_id}.json"
    temporary_path = metrics_path.with_suffix(".tmp")
    record = {
        **metrics,
        "recorded_at": recorded_at.isoformat(),
    }

    temporary_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(metrics_path)

    return {
        "source": source,
        "batch_id": batch_id,
        "metrics_file_path": str(metrics_path),
        "recorded_at": recorded_at.isoformat(),
    }


def build_source_dag(configuration: SourceSchedule) -> Any:
    source_name = configuration.source
    cursor_variable = f"job_crawl_cursor_{source_name}"

    @dag(
        dag_id=f"job_crawl_{source_name}",
        description=f"Crawl and normalize jobs from {source_name}",
        schedule=configuration.schedule,
        start_date=pendulum.datetime(
            2026,
            8,
            24,
            tz=LOCAL_TIMEZONE,
        ),
        catchup=False,
        max_active_runs=1,
        on_failure_callback=persist_failure_alert,
        tags=["jobs", "crawling", source_name],
    )
    def source_pipeline() -> None:
        @task(
            task_id=f"crawl_{source_name}_jobs",
            retries=3,
            retry_delay=timedelta(minutes=10),
            retry_exponential_backoff=True,
            max_retry_delay=timedelta(hours=1),
            execution_timeout=timedelta(minutes=15),
        )
        def crawl_source_jobs() -> dict[str, Any]:
            from app.cli.crawl_jobs import crawl_jobs

            cursor = _read_cursor(
                cursor_variable,
                enabled=configuration.uses_cursor,
            )
            result = asyncio.run(
                crawl_jobs(
                    source_name=source_name,
                    limit=configuration.limit,
                    cursor=cursor,
                    data_dir=DATA_DIRECTORY,
                    timeout_seconds=45.0,
                )
            )
            metrics = {
                field: result.get(field)
                for field in METRIC_FIELDS
            }
            LOGGER.info("%s crawl completed: %s", source_name, metrics)
            return metrics

        @task(
            task_id="validate_crawl_quality",
            retries=0,
            execution_timeout=timedelta(minutes=2),
        )
        def validate_crawl_quality(
            metrics: dict[str, Any],
        ) -> dict[str, Any]:
            return _validate_metrics(
                metrics,
                expected_limit=configuration.limit,
                min_fetch_ratio=configuration.min_fetch_ratio,
                min_fetch_count=configuration.min_fetch_count,
            )

        @task(
            task_id="commit_source_cursor",
            retries=2,
            retry_delay=timedelta(minutes=1),
            execution_timeout=timedelta(minutes=2),
        )
        def commit_source_cursor(
            metrics: dict[str, Any],
        ) -> dict[str, Any]:
            next_cursor = metrics.get("next_cursor")

            if configuration.uses_cursor:
                Variable.set(
                    cursor_variable,
                    next_cursor or "",
                    description=(
                        f"Pagination cursor for {source_name} job crawler"
                    ),
                )

            return {
                **metrics,
                "committed_cursor": next_cursor,
            }

        @task(
            task_id="record_crawl_metrics",
            retries=2,
            retry_delay=timedelta(minutes=1),
            execution_timeout=timedelta(minutes=2),
        )
        def record_crawl_metrics(
            metrics: dict[str, Any],
        ) -> dict[str, Any]:
            return _persist_metrics(metrics)

        crawl_metrics = crawl_source_jobs()
        validated_metrics = validate_crawl_quality(crawl_metrics)
        committed_metrics = commit_source_cursor(validated_metrics)
        record_crawl_metrics(committed_metrics)

    return source_pipeline()


for source_configuration in SOURCE_SCHEDULES:
    globals()[f"job_crawl_{source_configuration.source}"] = build_source_dag(
        source_configuration
    )
