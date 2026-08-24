from __future__ import annotations

import asyncio
import logging
from datetime import timedelta, UTC, datetime
from pathlib import Path
from typing import Any
import json
import re

import pendulum
from airflow.sdk import Variable, dag, task

from common.callbacks import persist_failure_alert


LOGGER = logging.getLogger(__name__)

CURSOR_VARIABLE = "job_crawl_cursor_himalayas"
DATA_DIRECTORY = Path("/opt/airflow/data/jobs")

MAX_FAILURE_RATE = 0.10

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

@dag(
    dag_id="job_crawling_pipeline",
    description="Crawl and normalize remote jobs from Himalayas",
    schedule="0 */3 * * *",
    start_date=pendulum.datetime(2026, 8, 24, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    on_failure_callback=persist_failure_alert,
    tags=["jobs", "crawling", "himalayas"],
)

def job_crawling_pipeline() -> None:
    @task(
        task_id="crawl_himalayas_jobs",
        retries=3,
        retry_delay=timedelta(minutes=10),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(hours=1),
        execution_timeout=timedelta(minutes=10)
    )
    def crawl_himalayas_jobs() -> dict[str, Any]:
        from app.cli.crawl_jobs import crawl_jobs

        stored_cursor = Variable.get(CURSOR_VARIABLE, default=None)

        cursor = (
            stored_cursor.strip()
            if isinstance(stored_cursor, str)
            and stored_cursor.strip()
            else None
        )

        result = asyncio.run(
            crawl_jobs(
                source_name="himalayas",
                limit=20,
                cursor=cursor,
                data_dir=DATA_DIRECTORY,
                timeout_seconds=30.0,
            )
        )

        metrics = {
            field: result.get(field)
            for field in METRIC_FIELDS
        }

        LOGGER.info(
            "Himalayas crawl completed: %s",
            metrics,
        )

        return metrics

    @task(
        task_id="validate_crawl_quality",
        retries=0,
        execution_timeout=timedelta(minutes=2),
    )
    def validate_crawl_quality(metrics: dict[str, Any]) -> dict[str, Any]:
        for field in COUNT_FIELDS:
            value = metrics.get(field)

            if not isinstance(value, int):
                raise ValueError(
                    f"{field} must be an integer, got {value!r}"
                )

            if value < 0:
                raise ValueError(
                    f"{field} cannot be negative"
                )

        fetched = metrics["fetched_count"]
        normalized = metrics["normalized_count"]
        failed = metrics["failed_count"]

        inserted = metrics["inserted_count"]
        updated = metrics["updated_count"]
        unchanged = metrics["unchanged_count"]

        if fetched != normalized + failed:
            raise ValueError(
                "Invalid processing totals: "
                f"fetched={fetched}, "
                f"normalized={normalized}, "
                f"failed={failed}"
            )

        written_total = inserted + updated + unchanged

        if written_total != normalized:
            raise ValueError(
                "Invalid repository totals: "
                f"normalized={normalized}, "
                f"written_total={written_total}"
            )

        failure_rate = failed / fetched if fetched > 0 else 0.0

        if failure_rate > MAX_FAILURE_RATE:
            raise ValueError(
                "Failure rate exceeded threshold: "
                f"{failure_rate:.2%} > "
                f"{MAX_FAILURE_RATE:.2%}"
            )

        raw_file_path = metrics.get("raw_file_path")

        if fetched > 0:
            if not raw_file_path:
                raise ValueError(
                    "raw_file_path is missing"
                )

            raw_path = Path(str(raw_file_path))

            if not raw_path.is_absolute():
                raw_path = Path("/opt/airflow") / raw_path

            if not raw_path.is_file():
                raise ValueError(
                    f"Raw batch file does not exist: {raw_path}"
                )

            if raw_path.stat().st_size == 0:
                raise ValueError(
                    f"Raw batch file is empty: {raw_path}"
                )

        validated_metrics = {
            **metrics,
            "failure_rate": failure_rate,
            "quality_status": "passed",
        }

        if failed > 0:
            LOGGER.warning(
                "Batch passed with %s failed jobs "
                "(failure rate %.2f%%)",
                failed,
                failure_rate * 100,
            )
        else:
            LOGGER.info(
                "Data-quality validation passed: %s",
                validated_metrics,
            )

        return validated_metrics

    @task(
        task_id="commit_himalayas_cursor",
        retries=2,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=2),
    )
    def commit_himalayas_cursor( validated_metrics: dict[str, Any]) -> dict[str, Any]:
        next_cursor = validated_metrics.get("next_cursor")

        Variable.set(
            CURSOR_VARIABLE,
            next_cursor or "",
            description=(
                "Pagination cursor for Himalayas job crawler"
            ),
        )

        LOGGER.info(
            "Committed Himalayas cursor: %s",
            next_cursor or "<feed completed>",
        )

        return {
            **validated_metrics,
            "committed_cursor": next_cursor,
        }

    @task(
        task_id="record_crawl_metrics",
        retries=2,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=2),
    )
    def record_crawl_metrics(committed_metrics: dict[str, Any]) -> dict[str, Any]:
        recorded_at = datetime.now(UTC)

        source = str(committed_metrics.get("source", "unknown"))
        batch_id = str(
            committed_metrics.get(
                "batch_id",
                "unknown_batch",
            )
        )

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
            **committed_metrics,
            "recorded_at": recorded_at.isoformat(),
        }

        temporary_path.write_text(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(metrics_path)

        LOGGER.info(
            "Crawl metrics persisted to %s",
            metrics_path,
        )

        return {
            "source": source,
            "batch_id": batch_id,
            "metrics_file_path": str(metrics_path),
            "recorded_at": recorded_at.isoformat(),
        }

    crawl_metrics = crawl_himalayas_jobs()
    validated_metrics = validate_crawl_quality(crawl_metrics)
    committed_metrics = commit_himalayas_cursor(validated_metrics)
    record_crawl_metrics (committed_metrics)

job_crawling_pipeline()
